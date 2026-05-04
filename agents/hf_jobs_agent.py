"""Hugging Face Jobs wrapper for conference deadlines agent.

Packages local `agents/`, `.claude/`, and `README.md` into a tarball, uploads to a
private Hugging Face model repo, then runs one HF Job per conference — matching
Modal's sequential per-container model. See community-science/HF_JOBS_PATTERN.md.

Usage:

```bash
# Single conference (blocks, streams logs)
uv run --env-file keys.env python -m agents.hf_jobs_agent --conference-name neurips

# All conferences, sequential
uv run --env-file keys.env python -m agents.hf_jobs_agent --all-conferences

# Iterate without re-uploading code
uv run --env-file keys.env python -m agents.hf_jobs_agent --conference-name neurips --skip-upload
```

Setup:
1. Install HF CLI: curl -LsSf https://hf.co/cli/install.sh | bash
2. Authenticate: hf auth login
3. Create `keys.env` with: HF_TOKEN, ANTHROPIC_API_KEY, GH_TOKEN (repo scope), EXA_API_KEY

For uploading ``code.tar.gz``, the launcher uses ``HF_UPLOAD_TOKEN`` if set, otherwise the
token from ``hf auth login`` (via ``get_token()``). The ``HF_TOKEN`` in ``keys.env`` is still
forwarded to the remote job for downloading that file; it can be a read-only token if the
upload token owns the private code repo.
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from huggingface_hub import HfApi, get_token

# Target GitHub repo (YAML data + git push target)
REPO_URL = "https://github.com/huggingface/ai-deadlines.git"
REPO_DIR = "/home/agent/ai-deadlines"
APP_DIR = "/home/agent/app"
CONFERENCES_DIR = "src/data/conferences"

HF_CODE_REPO_SUFFIX = "ai-deadlines-agent-code"
SECRET_NAMES = ("HF_TOKEN", "ANTHROPIC_API_KEY", "GH_TOKEN", "EXA_API_KEY")
TAR_INCLUDE = ("agents", ".claude", "README.md")

DEFAULT_IMAGE = "python:3.11-slim"
DEFAULT_FLAVOR = "cpu-basic"
DEFAULT_TIMEOUT = "30m"

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _resolve_write_hub_token() -> str:
    """Token with ``repo.write`` + ``job.write`` (upload + ``hf jobs run``).

    ``HF_TOKEN`` in ``keys.env`` is often read-only; use ``HF_UPLOAD_TOKEN`` or the
    token from ``hf auth login`` (see ``get_token()``).
    """
    t = os.environ.get("HF_UPLOAD_TOKEN")
    if t:
        return t
    backup = os.environ.pop("HF_TOKEN", None)
    try:
        t = get_token()
    finally:
        if backup is not None:
            os.environ["HF_TOKEN"] = backup
    if not t:
        raise ValueError(
            "No Hub token for upload/jobs: set HF_UPLOAD_TOKEN or run `hf auth login`."
        )
    return t


def _upload_api() -> HfApi:
    """Hub API client for tarball upload and ``whoami``."""
    return HfApi(token=_resolve_write_hub_token())


def get_conferences(base_dir: str | Path) -> list[str]:
    """List conference names from ``src/data/conferences/*.yml`` under ``base_dir``."""
    conferences_path = Path(base_dir) / CONFERENCES_DIR
    if not conferences_path.exists():
        raise FileNotFoundError(f"Conferences directory not found: {conferences_path}")
    conferences = [f.stem for f in conferences_path.glob("*.yml")]
    return sorted(conferences)


def load_env_file(path: Path) -> dict[str, str]:
    """Parse a simple KEY=value env file (comments and blank lines ignored)."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key:
            out[key] = val
    return out


def _tar_filter(ti: tarfile.TarInfo) -> tarfile.TarInfo | None:
    """Exclude junk from nested paths (mirrors HF_JOBS_PATTERN idea)."""
    name = Path(ti.name).name
    if name in {".venv", "__pycache__", ".git", "node_modules", "dist"}:
        return None
    if name.endswith(".pyc") or name == ".DS_Store":
        return None
    return ti


def sync_code_to_hf(api: HfApi, *, code_repo_id: str, skip_upload: bool) -> str:
    """Create private model repo if needed, tarball whitelist paths, upload ``code.tar.gz``."""
    if skip_upload:
        print(
            f"Skipping upload; using existing code.tar.gz in {code_repo_id}",
            flush=True,
        )
        return code_repo_id

    api.create_repo(code_repo_id, repo_type="model", private=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        tarball_path = tmp.name

    try:
        with tarfile.open(tarball_path, "w:gz") as tar:
            for name in TAR_INCLUDE:
                p = PROJECT_ROOT / name
                if not p.exists():
                    raise FileNotFoundError(f"Required path for tarball missing: {p}")
                tar.add(str(p), arcname=name, filter=_tar_filter)

        size_mb = os.path.getsize(tarball_path) / (1024 * 1024)
        print(f"Packed code tarball: {tarball_path} ({size_mb:.3f} MiB)", flush=True)

        api.upload_file(
            path_or_fileobj=tarball_path,
            path_in_repo="code.tar.gz",
            repo_id=code_repo_id,
            repo_type="model",
            commit_message="Sync code for HF Jobs run",
        )
        print(
            f"Uploaded code.tar.gz to https://huggingface.co/{code_repo_id}",
            flush=True,
        )
    finally:
        os.unlink(tarball_path)

    return code_repo_id


def build_remote_command(
    code_repo_id: str,
    conference_name: str,
    num_retrieval_agents: int,
    *,
    enable_exa_mcp: bool,
) -> str:
    """Single bash -c script run inside the HF Job container (as root, then ``su agent``)."""
    # URL for authenticated download inside the container
    hf_url = f"https://huggingface.co/{code_repo_id}/resolve/main/code.tar.gz"
    # Escape for embedding in bash single-quoted Python -c (use repr in Python)
    py_download = (
        "import os, urllib.request; "
        f"url={hf_url!r}; "
        "req=urllib.request.Request(url, headers={'Authorization': 'Bearer ' + os.environ['HF_TOKEN']}); "
        "r=urllib.request.urlopen(req); "
        "open('/tmp/code.tar.gz','wb').write(r.read())"
    )

    env_exports = [
        "HOME=/home/agent",
        "USER=agent",
        "LOGNAME=agent",
        f"PYTHONPATH={APP_DIR}",
        "USE_CWD_AS_PROJECT_ROOT=1",
    ]
    if not enable_exa_mcp:
        env_exports.append("DISABLE_EXA_MCP=1")

    env_prefix = " ".join(f"export {e}" for e in env_exports)

    inner_cmd = (
        f"cd {REPO_DIR} && {env_prefix} && "
        f"python -m agents.agent --conference_name {shlex.quote(conference_name)} "
        f"--num-retrieval-agents {int(num_retrieval_agents)}"
    )

    # gh install (same as modal_agent.py)
    gh_block = (
        "curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg "
        "| dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg && "
        "chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg && "
        'echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] '
        'https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null && '
        "apt-get update -qq && apt-get install -y -qq gh"
    )

    lines = [
        "set -euxo pipefail",
        "export DEBIAN_FRONTEND=noninteractive",
        "apt-get update -qq",
        "apt-get install -y -qq git curl ca-certificates gnupg",
        gh_block,
        "python -m pip install --no-cache-dir --break-system-packages -q "
        "'claude-agent-sdk>=0.1.18' 'aiofiles>=24.1.0'",
        "id -u agent >/dev/null 2>&1 || useradd -m -s /bin/bash agent",
        'git config --global user.email "agent@hf-jobs.com"',
        'git config --global user.name "HF Jobs Conference Agent"',
        "git config --global credential.helper store",
        "test -n \"${GH_TOKEN:-}\"",
        "printf 'https://x-access-token:%s@github.com\\n' \"$GH_TOKEN\" > /root/.git-credentials",
        "chmod 600 /root/.git-credentials",
        f"rm -rf {shlex.quote(REPO_DIR)}",
        f"git clone {shlex.quote(REPO_URL)} {shlex.quote(REPO_DIR)}",
        f"python -c {shlex.quote(py_download)}",
        f"mkdir -p {shlex.quote(APP_DIR)}",
        f"tar xzf /tmp/code.tar.gz -C {shlex.quote(APP_DIR)}",
        "rm -rf /home/agent/.claude",
        f"cp -r {shlex.quote(APP_DIR)}/.claude /home/agent/.claude",
        "cp /root/.gitconfig /home/agent/.gitconfig",
        "cp /root/.git-credentials /home/agent/.git-credentials",
        f"chown -R agent:agent {shlex.quote(str(Path(REPO_DIR).parent))}",
        f"su agent -c {shlex.quote(inner_cmd)}",
    ]
    return " && ".join(lines)


def _write_secrets_file(
    env: dict[str, str],
    path: Path,
    *,
    hf_token: str | None = None,
) -> None:
    """Write only whitelisted secrets for ``hf jobs run --secrets-file``."""
    lines = []
    for name in SECRET_NAMES:
        if name == "HF_TOKEN" and hf_token is not None:
            val = hf_token
        elif name in env and env[name]:
            val = env[name]
        else:
            raise ValueError(f"Missing required secret in environment: {name}")
        val = val.replace("\n", "").replace("\r", "")
        lines.append(f"{name}={val}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_single_conference_job(
    *,
    code_repo_id: str,
    conference_name: str,
    num_retrieval_agents: int,
    image: str,
    flavor: str,
    timeout: str,
    secrets_file: Path,
    detach: bool,
    enable_exa_mcp: bool,
    process_env: dict[str, str] | None = None,
) -> int:
    """Run ``hf jobs run`` blocking; logs stream to stdout/stderr.

    ``process_env`` is merged into the subprocess environment (e.g. set ``HF_TOKEN``
    to a token with ``job.write`` — the CLI uses it to authorize the job launch, not
    only the ``--secrets-file`` payload).
    """
    cmd = _build_hf_jobs_argv(
        image=image,
        flavor=flavor,
        timeout=timeout,
        secrets_file=secrets_file,
        detach=detach,
        remote_bash=build_remote_command(
            code_repo_id,
            conference_name,
            num_retrieval_agents,
            enable_exa_mcp=enable_exa_mcp,
        ),
    )
    print("Running:", " ".join(shlex.quote(c) for c in cmd))
    env = {**os.environ, **(process_env or {})}
    r = subprocess.run(cmd, check=False, env=env)
    return r.returncode


def _build_hf_jobs_argv(
    *,
    image: str,
    flavor: str,
    timeout: str,
    secrets_file: Path,
    detach: bool,
    remote_bash: str,
) -> list[str]:
    argv: list[str] = [
        "hf",
        "jobs",
        "run",
        "--secrets-file",
        str(secrets_file),
        "--flavor",
        flavor,
        "--timeout",
        timeout,
    ]
    if detach:
        argv.append("--detach")
    argv.extend([image, "bash", "-c", remote_bash])
    return argv


def run_all_conferences(
    *,
    code_repo_id: str,
    conferences: list[str],
    num_retrieval_agents: int,
    image: str,
    flavor: str,
    timeout: str,
    secrets_file: Path,
    enable_exa_mcp: bool,
    process_env: dict[str, str] | None = None,
) -> list[dict]:
    """Run one HF Job per conference sequentially."""
    results: list[dict] = []
    n = len(conferences)
    print(f"\n{'=' * 60}")
    print(f"Processing {n} conferences sequentially")
    print(f"{'=' * 60}")

    for i, name in enumerate(conferences, 1):
        print(f"\n[{i}/{n}] {name}")
        rc = run_single_conference_job(
            code_repo_id=code_repo_id,
            conference_name=name,
            num_retrieval_agents=num_retrieval_agents,
            image=image,
            flavor=flavor,
            timeout=timeout,
            secrets_file=secrets_file,
            detach=False,
            enable_exa_mcp=enable_exa_mcp,
            process_env=process_env,
        )
        status = "ok" if rc == 0 else "error"
        results.append({"conference": name, "exit_code": rc, "status": status})
        if rc != 0:
            print(f"WARNING: Job exited with code {rc} for {name}")

    print(f"\n{'=' * 60}")
    print(f"Completed processing {n} conferences")
    print(f"{'=' * 60}")
    return results


def _resolve_code_repo_id(explicit: str | None, api: HfApi) -> str:
    if explicit:
        return explicit
    user = api.whoami()["name"]
    return f"{user}/{HF_CODE_REPO_SUFFIX}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run conference deadlines agent on Hugging Face Jobs",
    )
    parser.add_argument("--conference-name", type=str, default=None)
    parser.add_argument("--all-conferences", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--num-retrieval-agents", type=int, default=3)
    parser.add_argument("--flavor", type=str, default=DEFAULT_FLAVOR)
    parser.add_argument("--timeout", type=str, default=DEFAULT_TIMEOUT)
    parser.add_argument("--image", type=str, default=DEFAULT_IMAGE)
    parser.add_argument("--env-file", type=Path, default=Path("keys.env"))
    parser.add_argument(
        "--code-repo",
        type=str,
        default=None,
        help=f"HF model repo id for code.tar.gz (default: <user>/{HF_CODE_REPO_SUFFIX})",
    )
    parser.add_argument("--skip-upload", action="store_true")
    parser.add_argument("--enable-exa-mcp", action="store_true")
    parser.add_argument("--detach", action="store_true")

    args = parser.parse_args()

    if args.conference_name and args.all_conferences:
        print("Error: specify either --conference-name or --all-conferences, not both.")
        sys.exit(2)

    env_file = args.env_file
    file_env = load_env_file(env_file)
    for k, v in file_env.items():
        os.environ.setdefault(k, v)

    api = _upload_api()
    code_repo_id = _resolve_code_repo_id(args.code_repo, api)
    write_hf_token = _resolve_write_hub_token()

    secrets_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".secrets.env",
            delete=False,
            encoding="utf-8",
        ) as tmp:
            secrets_path = Path(tmp.name)
        _write_secrets_file(
            dict(os.environ),
            secrets_path,
            hf_token=write_hf_token,
        )
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(2)

    try:
        sync_code_to_hf(api, code_repo_id=code_repo_id, skip_upload=args.skip_upload)

        if args.conference_name:
            print(f"Processing single conference: {args.conference_name}", flush=True)
            rc = run_single_conference_job(
                code_repo_id=code_repo_id,
                conference_name=args.conference_name,
                num_retrieval_agents=args.num_retrieval_agents,
                image=args.image,
                flavor=args.flavor,
                timeout=args.timeout,
                secrets_file=secrets_path,
                detach=args.detach,
                enable_exa_mcp=args.enable_exa_mcp,
                process_env={"HF_TOKEN": write_hf_token},
            )
            print(f"\nResult: exit_code={rc}")
            sys.exit(0 if rc == 0 else 1)

        if not args.all_conferences and args.limit is None:
            args.all_conferences = True

        if args.limit is not None:
            conferences = get_conferences(PROJECT_ROOT)[: args.limit]
        elif args.all_conferences:
            conferences = get_conferences(PROJECT_ROOT)
        else:
            print("Error: specify --conference-name, --all-conferences, or --limit.")
            sys.exit(2)

        print(f"Processing {len(conferences)} conferences sequentially...")
        results = run_all_conferences(
            code_repo_id=code_repo_id,
            conferences=conferences,
            num_retrieval_agents=args.num_retrieval_agents,
            image=args.image,
            flavor=args.flavor,
            timeout=args.timeout,
            secrets_file=secrets_path,
            enable_exa_mcp=args.enable_exa_mcp,
            process_env={"HF_TOKEN": write_hf_token},
        )

        ok = [r for r in results if r["exit_code"] == 0]
        bad = [r for r in results if r["exit_code"] != 0]
        print(f"\n{'=' * 60}")
        print("Summary:")
        print(f"{'=' * 60}")
        print(f"Succeeded: {len(ok)}")
        print(f"Failed: {len(bad)}")
        if bad:
            print("\nFailures:")
            for r in bad:
                print(f"  - {r['conference']}: exit_code={r['exit_code']}")
        sys.exit(0 if not bad else 1)
    finally:
        if secrets_path is not None:
            try:
                secrets_path.unlink(missing_ok=True)
            except OSError:
                pass


if __name__ == "__main__":
    main()

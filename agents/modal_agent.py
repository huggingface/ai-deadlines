"""Modal wrapper for conference deadlines agent.

This module wraps the existing agent functionality to run on Modal's
serverless infrastructure, processing all conferences in parallel.
Each conference gets its own branch and PR pushed directly to huggingface/ai-deadlines.

Usage:

```bash
# Run all conferences in parallel
uv run modal run agents/modal_agent.py

# Run single conference (for testing)
uv run modal run agents/modal_agent.py --conference-name neurips

# Deploy for weekly scheduled runs
uv run modal deploy agents/modal_agent.py
```

Setup:
1. Install Modal: uv add modal
2. Authenticate: uv run modal setup
3. Create secrets:
   uv run modal secret create anthropic ANTHROPIC_API_KEY=<your-api-key>
   uv run modal secret create github-token GH_TOKEN=<token-with-repo-and-pr-scope>
   uv run modal secret create exa EXA_API_KEY=<your-key>

Note: The GH_TOKEN token needs the following scopes:
  - `repo` - for cloning and pushing to the repository
  - `pull_request` or `repo` - for creating pull requests via the GitHub CLI
"""

import os
from pathlib import Path

import modal

# Repository configuration - push directly to huggingface/ai-deadlines
REPO_URL = "https://github.com/huggingface/ai-deadlines.git"
REPO_DIR = "/home/agent/ai-deadlines"
CONFERENCES_DIR = "src/data/conferences"


def get_conferences(base_dir: str = REPO_DIR) -> list[str]:
    """Get list of all conferences by reading yml files from the conferences directory.

    Args:
        base_dir: Base directory of the repository.

    Returns:
        Sorted list of conference names (yml filenames without extension).
    """
    conferences_path = Path(base_dir) / CONFERENCES_DIR
    if not conferences_path.exists():
        raise FileNotFoundError(f"Conferences directory not found: {conferences_path}")

    conferences = [f.stem for f in conferences_path.glob("*.yml")]
    return sorted(conferences)


# Define the Modal image with all required dependencies
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "curl")
    .run_commands(
        # Install GitHub CLI
        "curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg",
        "chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg",
        'echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null',
        "apt-get update",
        "apt-get install -y gh",
    )
    .pip_install(
        "claude-agent-sdk>=0.1.18",
        "aiofiles>=24.1.0",
    )
    .run_commands(
        # Create non-root user (required for claude-agent-sdk bypassPermissions)
        "useradd -m -s /bin/bash agent",
        "mkdir -p /home/agent/.claude",
    )
    # Copy agent code and settings
    .add_local_dir(
        "agents",
        remote_path="/home/agent/app/agents",
        copy=True,
    )
    .add_local_dir(
        ".claude",
        remote_path="/home/agent/.claude",
        copy=True,
    )
    .add_local_file(
        "README.md",
        remote_path="/home/agent/app/README.md",
        copy=True,
    )
    .run_commands("chown -R agent:agent /home/agent")
)

# Create the Modal app
app = modal.App(
    name="conference-deadlines-agent",
    image=image,
    secrets=[
        modal.Secret.from_name("anthropic"),
        modal.Secret.from_name("github-token"),
        modal.Secret.from_name("exa"),
    ],
)


def setup_git_and_clone(conference_name: str) -> str:
    """Configure git, clone the repository, and create a branch for the conference.

    Args:
        conference_name: The name of the conference (used for branch naming).

    Returns:
        The name of the created branch.
    """
    import subprocess

    # Configure git user
    subprocess.run(
        ["git", "config", "--global", "user.email", "agent@modal.com"],
        check=True,
    )
    subprocess.run(
        ["git", "config", "--global", "user.name", "Modal Conference Agent"],
        check=True,
    )

    # Configure credential helper to use the PAT
    subprocess.run(
        ["git", "config", "--global", "credential.helper", "store"],
        check=True,
    )

    github_token = os.environ.get("GH_TOKEN", "")
    if not github_token:
        raise ValueError("GH_TOKEN environment variable is required")

    # Store credentials for git operations
    credentials_file = os.path.expanduser("~/.git-credentials")
    with open(credentials_file, "w") as f:
        f.write(f"https://x-access-token:{github_token}@github.com\n")
    os.chmod(credentials_file, 0o600)

    # Clone the repository if it doesn't exist
    if not os.path.exists(REPO_DIR):
        subprocess.run(
            ["git", "clone", REPO_URL, REPO_DIR],
            check=True,
        )
        print(f"Cloned repository: {REPO_URL}")
    else:
        # Pull latest changes if repo already exists
        subprocess.run(
            ["git", "fetch", "origin"],
            cwd=REPO_DIR,
            check=True,
        )
        subprocess.run(
            ["git", "checkout", "main"],
            cwd=REPO_DIR,
            check=True,
        )
        subprocess.run(
            ["git", "pull", "origin", "main"],
            cwd=REPO_DIR,
            check=True,
        )
        print("Updated repository to latest main")

    # Create a unique branch for this conference
    branch_name = f"update/{conference_name}"

    # Check if branch already exists remotely
    result = subprocess.run(
        ["git", "ls-remote", "--heads", "origin", branch_name],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
    )

    if result.stdout.strip():
        # Branch exists remotely, check it out and update
        print(f"Branch {branch_name} exists remotely, checking out and updating...")
        subprocess.run(
            ["git", "checkout", "-B", branch_name, f"origin/{branch_name}"],
            cwd=REPO_DIR,
            check=True,
        )
        # Rebase on main to get latest changes
        subprocess.run(
            ["git", "rebase", "main"],
            cwd=REPO_DIR,
            check=True,
        )
    else:
        # Create new branch from main
        subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd=REPO_DIR,
            check=True,
        )
        print(f"Created new branch: {branch_name}")

    return branch_name


def push_and_create_pr(conference_name: str, branch_name: str) -> dict:
    """Push the branch and create a PR if there are changes.

    Args:
        conference_name: The name of the conference.
        branch_name: The name of the branch to push.

    Returns:
        A dictionary with PR creation result.
    """
    import subprocess

    # Check if there are any changes to commit
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
    )

    if not result.stdout.strip():
        # Also check if there are unpushed commits
        diff_result = subprocess.run(
            ["git", "log", f"origin/main..{branch_name}", "--oneline"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
        )
        if not diff_result.stdout.strip():
            print(f"No changes for {conference_name}, skipping PR creation")
            return {
                "conference": conference_name,
                "status": "no_changes",
                "branch": branch_name,
            }

    # Push the branch
    print(f"Pushing branch {branch_name}...")
    subprocess.run(
        ["git", "push", "-u", "origin", branch_name, "--force-with-lease"],
        cwd=REPO_DIR,
        check=True,
    )

    # Check if PR already exists for this branch
    github_token = os.environ.get("GH_TOKEN", "")
    env = os.environ.copy()
    env["GH_TOKEN"] = github_token

    pr_list_result = subprocess.run(
        ["gh", "pr", "list", "--head", branch_name, "--json", "number,url"],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        env=env,
    )

    import json

    existing_prs = json.loads(pr_list_result.stdout) if pr_list_result.stdout else []

    if existing_prs:
        # PR already exists, just update it (push was already done)
        pr_url = existing_prs[0]["url"]
        print(f"PR already exists for {conference_name}: {pr_url}")
        return {
            "conference": conference_name,
            "status": "pr_updated",
            "branch": branch_name,
            "pr_url": pr_url,
        }

    # Create a new PR
    pr_title = f"Update {conference_name.upper()} conference deadlines"
    pr_body = f"""This PR updates the deadline information for the {conference_name.upper()} conference.

Updated automatically by the Modal Conference Agent.

---
*This PR was created automatically. Please review the changes before merging.*
"""

    print(f"Creating PR for {conference_name}...")
    pr_result = subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--title",
            pr_title,
            "--body",
            pr_body,
            "--base",
            "main",
            "--head",
            branch_name,
        ],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        env=env,
    )

    if pr_result.returncode != 0:
        print(f"Failed to create PR: {pr_result.stderr}")
        return {
            "conference": conference_name,
            "status": "pr_creation_failed",
            "branch": branch_name,
            "error": pr_result.stderr,
        }

    pr_url = pr_result.stdout.strip()
    print(f"Created PR for {conference_name}: {pr_url}")

    return {
        "conference": conference_name,
        "status": "pr_created",
        "branch": branch_name,
        "pr_url": pr_url,
    }


@app.function(timeout=600)
def process_single_conference(conference_name: str) -> dict:
    """Process a single conference using the Claude Agent SDK.

    The agent will update the conference data. After the agent completes,
    this function pushes the branch and creates a PR.

    Args:
        conference_name: The name of the conference to process.

    Returns:
        A dictionary containing the processing result.
    """
    import asyncio
    import pwd
    import sys

    # Switch to non-root user (required for claude-agent-sdk bypassPermissions)
    agent_user = pwd.getpwnam("agent")
    os.setgid(agent_user.pw_gid)
    os.setuid(agent_user.pw_uid)
    os.environ["HOME"] = agent_user.pw_dir
    os.environ["USER"] = "agent"
    os.environ["LOGNAME"] = "agent"

    # Ensure subprocess inherits correct user context
    os.environ["SHELL"] = "/bin/bash"

    # Disable MCP for now - known issue where MCP causes SDK to exit early on Modal
    # The agent will use built-in WebSearch tool instead
    # See MODAL_DEBUGGING.md for details
    os.environ["DISABLE_EXA_MCP"] = "1"

    # Setup git, clone repo, and create branch for this conference
    branch_name = setup_git_and_clone(conference_name)

    # Add REPO_DIR first, then app directory (last insert is at position 0, so app takes priority)
    # This ensures local mounted code is used instead of cloned repo code
    sys.path.insert(0, REPO_DIR)
    sys.path.insert(0, "/home/agent/app")

    # Change to repo directory so relative paths work
    os.chdir(REPO_DIR)

    # Tell agent.py to use current working directory as PROJECT_ROOT
    # This ensures conference data is read from the cloned repo, not the mounted app directory
    os.environ["USE_CWD_AS_PROJECT_ROOT"] = "1"

    # Import and run the agent (uses /home/agent/app/agents due to sys.path order)
    from agents.agent import find_conference_deadlines

    async def _process():
        try:
            await find_conference_deadlines(conference_name)

            # After agent completes, push branch and create PR
            pr_result = push_and_create_pr(conference_name, branch_name)
            return pr_result

        except Exception as e:
            return {
                "conference": conference_name,
                "status": "error",
                "branch": branch_name,
                "error": str(e),
            }

    return asyncio.run(_process())


@app.function(timeout=600)
def process_all_conferences() -> list[dict]:
    """Process all conferences in parallel.

    Each conference runs in its own Modal container with its own branch.
    After processing, each creates its own PR.

    Returns:
        List of results for each processed conference.
    """
    import pwd

    # Switch to non-root user (required for git operations)
    agent_user = pwd.getpwnam("agent")
    os.setgid(agent_user.pw_gid)
    os.setuid(agent_user.pw_uid)
    os.environ["HOME"] = agent_user.pw_dir

    # Clone repo first to get the list of conferences
    # We use a dummy conference name here since we just need to clone
    import subprocess

    # Configure git (minimal setup just to clone)
    subprocess.run(
        ["git", "config", "--global", "user.email", "agent@modal.com"],
        check=True,
    )
    subprocess.run(
        ["git", "config", "--global", "user.name", "Modal Conference Agent"],
        check=True,
    )

    github_token = os.environ.get("GH_TOKEN", "")
    if github_token:
        credentials_file = os.path.expanduser("~/.git-credentials")
        with open(credentials_file, "w") as f:
            f.write(f"https://x-access-token:{github_token}@github.com\n")
        os.chmod(credentials_file, 0o600)
        subprocess.run(
            ["git", "config", "--global", "credential.helper", "store"],
            check=True,
        )

    if not os.path.exists(REPO_DIR):
        subprocess.run(
            ["git", "clone", REPO_URL, REPO_DIR],
            check=True,
        )

    # Get conferences from yml files in the cloned repo
    conferences = get_conferences()

    print(f"\n{'=' * 60}")
    print(f"Processing {len(conferences)} conferences in parallel")
    print(f"{'=' * 60}")

    # Process all conferences in parallel using Modal's .map()
    results = list(process_single_conference.map(conferences))

    print(f"\n{'=' * 60}")
    print(f"Completed processing {len(conferences)} conferences")
    print(f"{'=' * 60}")

    return results


@app.function(
    timeout=43200,  # 12 hours max
    schedule=modal.Cron("0 0 * * 0"),  # Run weekly on Sunday at midnight UTC
)
def scheduled_run():
    """Scheduled weekly run of all conferences in parallel."""
    print("Starting scheduled weekly conference update...")
    results = process_all_conferences.remote()

    # Summary
    pr_created = sum(1 for r in results if r.get("status") == "pr_created")
    pr_updated = sum(1 for r in results if r.get("status") == "pr_updated")
    no_changes = sum(1 for r in results if r.get("status") == "no_changes")
    errors = sum(1 for r in results if r.get("status") == "error")

    print("\nWeekly run completed:")
    print(f"  - PRs created: {pr_created}")
    print(f"  - PRs updated: {pr_updated}")
    print(f"  - No changes: {no_changes}")
    print(f"  - Errors: {errors}")

    if errors:
        print("\nErrors:")
        for r in results:
            if r.get("status") == "error":
                print(f"  - {r['conference']}: {r.get('error', 'Unknown error')}")

    return results


@app.function(timeout=600)
def process_conferences_subset(conference_names: list[str]) -> list[dict]:
    """Process a subset of conferences in parallel.

    Args:
        conference_names: List of conference names to process.

    Returns:
        List of results for each processed conference.
    """
    print(f"\n{'=' * 60}")
    print(f"Processing {len(conference_names)} conferences in parallel: {conference_names}")
    print(f"{'=' * 60}")

    # Process conferences in parallel using Modal's .map()
    results = list(process_single_conference.map(conference_names))

    print(f"\n{'=' * 60}")
    print(f"Completed processing {len(conference_names)} conferences")
    print(f"{'=' * 60}")

    return results


@app.local_entrypoint()
def main(
    conference_name: str = None,
    all_conferences: bool = False,
    limit: int = None,
):
    """CLI entrypoint for the Modal agent.

    Args:
        conference_name: Single conference name to process (for testing).
        all_conferences: If True, process all conferences in parallel.
        limit: Limit number of conferences to process (for testing).
    """
    if conference_name and all_conferences:
        print("Error: Specify either --conference-name or --all-conferences, not both.")
        return

    if not conference_name and not all_conferences and not limit:
        # Default to processing all conferences
        all_conferences = True

    if conference_name:
        # Process single conference (for testing)
        print(f"Processing single conference: {conference_name}")
        result = process_single_conference.remote(conference_name)
        print(f"\nResult: {result}")

    elif limit:
        # Process limited number of conferences (for testing)
        local_conferences_dir = Path(__file__).parent.parent / CONFERENCES_DIR
        if local_conferences_dir.exists():
            conferences = sorted([f.stem for f in local_conferences_dir.glob("*.yml")])[:limit]
        else:
            print("Error: Cannot find local conferences directory to determine subset.")
            return
        print(f"Processing {len(conferences)} conferences (limited): {conferences}")
        results = process_conferences_subset.remote(conferences)

    elif all_conferences:
        # Process all conferences in parallel
        # Note: We read from local repo here for the count, Modal will read from cloned repo
        local_conferences_dir = Path(__file__).parent.parent / CONFERENCES_DIR
        if local_conferences_dir.exists():
            num_conferences = len(list(local_conferences_dir.glob("*.yml")))
        else:
            num_conferences = "all"
        print(f"Processing {num_conferences} conferences in parallel...")
        results = process_all_conferences.remote()

        print(f"\n{'=' * 60}")
        print("Summary:")
        print(f"{'=' * 60}")

        pr_created = [r for r in results if r.get("status") == "pr_created"]
        pr_updated = [r for r in results if r.get("status") == "pr_updated"]
        no_changes = [r for r in results if r.get("status") == "no_changes"]
        errors = [r for r in results if r.get("status") == "error"]

        print(f"PRs created: {len(pr_created)}")
        print(f"PRs updated: {len(pr_updated)}")
        print(f"No changes: {len(no_changes)}")
        print(f"Errors: {len(errors)}")

        if pr_created:
            print("\nNew PRs:")
            for r in pr_created:
                print(f"  - {r['conference']}: {r.get('pr_url', 'N/A')}")

        if pr_updated:
            print("\nUpdated PRs:")
            for r in pr_updated:
                print(f"  - {r['conference']}: {r.get('pr_url', 'N/A')}")

        if errors:
            print("\nErrors:")
            for r in errors:
                print(f"  - {r['conference']}: {r.get('error', 'Unknown error')}")

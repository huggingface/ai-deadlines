"""Status enum and git mapping: pushed + sha vs no_changes vs error."""

import subprocess
from datetime import date
from pathlib import Path

from agents.pipeline_utils import (
    conference_result_payload,
    get_agent_wall_clock_seconds,
    get_modal_conference_timeout,
    git_commit_conference,
    pipeline_result,
    push_conference_yaml,
    remote_call_error_payload,
    resolve_conference_status,
    write_conference_yaml,
)

CURRENT_YAML = """\
- title: Demo
  year: 2025
  id: demo25
  date: January 1 - 2, 2025
  start: '2025-01-01'
  end: '2025-01-02'
- title: Demo
  year: 2027
  id: demo27
  date: January 1 - 2, 2027
  start: '2027-01-01'
  end: '2027-01-02'
  timezone: AoE
"""

UPDATED_YAML = """\
- title: Demo
  year: 2025
  id: demo25
  date: January 1 - 2, 2025
  start: '2025-01-01'
  end: '2025-01-02'
- title: Demo
  year: 2027
  id: demo27
  date: January 1 - 2, 2027
  start: '2027-01-01'
  end: '2027-01-02'
  timezone: AoE
  city: Paris
"""


def _init_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "agent@test.local"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test Agent"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    return tmp_path


def test_resolve_status_does_not_collapse_error_and_timeout_to_no_changes():
    assert resolve_conference_status(pushed=True) == "pushed"
    assert resolve_conference_status(pushed=False) == "no_changes"
    assert resolve_conference_status(error="boom") == "error"
    assert resolve_conference_status(timed_out=True) == "timeout"
    assert resolve_conference_status(status="pushed") == "pushed"
    assert resolve_conference_status(status="timeout", pushed=False) == "timeout"


def test_payload_passes_commit_sha_on_pushed():
    payload = conference_result_payload(
        "neurips",
        pipeline_result(status="pushed", commit_sha="abc123", reasoning="updated"),
    )
    assert payload["status"] == "pushed"
    assert payload["commit_sha"] == "abc123"
    assert payload["conference"] == "neurips"


def test_payload_error_is_not_no_changes():
    payload = conference_result_payload(
        "aaai",
        pipeline_result(status="error", error="validation failed"),
    )
    assert payload["status"] == "error"
    assert payload["error"] == "validation failed"
    assert "commit_sha" not in payload


def test_remote_timeout_exception_maps_to_timeout():
    class FunctionTimeoutError(Exception):
        pass

    payload = remote_call_error_payload("ecir", FunctionTimeoutError("timeout after 3600s"))
    assert payload["status"] == "timeout"
    assert payload["conference"] == "ecir"


def test_git_commit_returns_sha(tmp_path: Path):
    repo = _init_repo(tmp_path)
    relpath = "src/data/conferences/demo.yml"
    path = repo / relpath
    write_conference_yaml(path, CURRENT_YAML)
    subprocess.run(["git", "add", relpath], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    write_conference_yaml(path, UPDATED_YAML)
    sha = git_commit_conference(repo, relpath, "Update demo deadlines")
    assert sha
    assert len(sha) >= 7
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    assert head.stdout.strip() == sha


def test_git_commit_nothing_to_commit_returns_none(tmp_path: Path):
    repo = _init_repo(tmp_path)
    relpath = "src/data/conferences/demo.yml"
    path = repo / relpath
    write_conference_yaml(path, CURRENT_YAML)
    subprocess.run(["git", "add", relpath], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    sha = git_commit_conference(repo, relpath, "Update demo deadlines")
    assert sha is None


def test_push_conference_yaml_skip_remote_returns_pushed_and_sha(tmp_path: Path):
    repo = _init_repo(tmp_path)
    relpath = "src/data/conferences/demo.yml"
    path = repo / relpath
    write_conference_yaml(path, CURRENT_YAML)
    subprocess.run(["git", "add", relpath], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    result = push_conference_yaml(
        conference_name="demo",
        updated_yaml=UPDATED_YAML,
        current_yaml=CURRENT_YAML,
        project_root=repo,
        today=date(2026, 8, 28),
        skip_remote_push=True,
    )
    assert result["status"] == "pushed"
    assert result["pushed"] is True
    assert result["commit_sha"]
    assert path.read_text(encoding="utf-8").startswith("- title: Demo")


def test_push_rejects_invalid_yaml_without_commit(tmp_path: Path):
    repo = _init_repo(tmp_path)
    result = push_conference_yaml(
        conference_name="demo",
        updated_yaml="this: [unterminated",
        current_yaml=CURRENT_YAML,
        project_root=repo,
        today=date(2026, 8, 28),
        skip_remote_push=True,
    )
    assert result["status"] == "error"
    assert result["pushed"] is False
    assert result["commit_sha"] is None
    assert not (repo / "src/data/conferences/demo.yml").exists()


def test_modal_timeout_env(monkeypatch):
    monkeypatch.delenv("MODAL_CONFERENCE_TIMEOUT", raising=False)
    assert get_modal_conference_timeout() == 3600
    monkeypatch.setenv("MODAL_CONFERENCE_TIMEOUT", "1800")
    assert get_modal_conference_timeout() == 1800


def test_agent_wall_clock_env(monkeypatch):
    monkeypatch.delenv("AGENT_WALL_CLOCK_SECONDS", raising=False)
    monkeypatch.delenv("RETRIEVAL_WALL_CLOCK_SECONDS", raising=False)
    assert get_agent_wall_clock_seconds("retrieval") == 300.0
    monkeypatch.setenv("RETRIEVAL_WALL_CLOCK_SECONDS", "240")
    assert get_agent_wall_clock_seconds("retrieval") == 240.0
    monkeypatch.setenv("RETRIEVAL_WALL_CLOCK_SECONDS", "0")
    assert get_agent_wall_clock_seconds("retrieval") is None

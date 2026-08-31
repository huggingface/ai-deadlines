"""Deterministic helpers for the conference-deadline agent pipeline.

Used by ``agent.py`` (Modal and HF Jobs). Keep this module free of Claude Agent
SDK calls so year labels, validation, git, and status mapping stay unit-testable.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

CONFERENCE_STATUSES = ("pushed", "no_changes", "error", "timeout")

REQUIRED_YEAR_FIELDS = ("title", "year", "id")
FORBIDDEN_TIMEZONES = {
    "utc-12",
    "utc+12",
    "utc-12:00",
    "utc+12:00",
}

BUDGET_EXHAUSTED_MESSAGE = (
    "Your tool-call budget is exhausted. Do not search again. "
    "Return structured output now. If you found no verified upcoming deadlines, "
    "set requires_update: false."
)

BUDGET_EXHAUSTED_FOLLOWUP = (
    "Your tool-call budget is exhausted. Do not search again. "
    "Return structured output now from what you already saw. "
    "If you found no verified upcoming deadlines, set requires_update: false."
)

_MONTH_NAMES = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

_DATE_RANGE_RE = re.compile(
    r"(?P<m1>January|February|March|April|May|June|July|August|September|"
    r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|"
    r"Oct|Nov|Dec)\s+"
    r"(?P<d1>\d{1,2})"
    r"(?:\s*[-–]\s*(?:(?P<m2>January|February|March|April|May|June|July|"
    r"August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|"
    r"Aug|Sept|Sep|Oct|Nov|Dec)\s+)?(?P<d2>\d{1,2}))?"
    r",\s*(?P<year>\d{4})",
    re.IGNORECASE,
)

_YEAR_LINE_RE = re.compile(r"(?m)^  year:\s*['\"]?(\d+)")


class YamlValidationError(ValueError):
    """Updated conference YAML failed a pre-push check."""


class GitPushError(RuntimeError):
    """git add/commit/push failed."""


@dataclass(frozen=True)
class YearLabel:
    year: int
    status: str  # PAST | UPCOMING | MISSING_NEXT_YEAR | UNKNOWN


class ToolBudgetState:
    """Count search-tool uses and decide last-turn nudge / deny."""

    def __init__(self, max_turns: int):
        self.max_turns = max_turns
        self.search_uses = 0
        self.nudge_sent = False

    def on_post_tool_use(self, tool_name: str) -> str | None:
        """Record a completed tool call. Return additionalContext or None."""
        if not is_search_tool(tool_name):
            return None
        self.search_uses += 1
        if self.search_uses >= max(self.max_turns - 1, 1) and not self.nudge_sent:
            self.nudge_sent = True
            return BUDGET_EXHAUSTED_MESSAGE
        return None

    def should_deny_pre_tool_use(self, tool_name: str) -> bool:
        return self.nudge_sent and is_search_tool(tool_name)


def is_search_tool(tool_name: str) -> bool:
    """True for WebSearch, WebFetch, and Exa MCP search/fetch tools."""
    if not tool_name:
        return False
    if tool_name in {"WebSearch", "WebFetch"}:
        return True
    return "exa" in tool_name.lower()


def parse_iso_date(value: Any) -> date | None:
    """Parse YAML ``start``/``end`` values (str, date, or datetime)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip().strip("'\"")
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def parse_date_field_end(value: Any) -> date | None:
    """Parse the end day from a conference ``date`` string like ``August 9 - 13, 2026``."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    match = _DATE_RANGE_RE.search(text)
    if not match:
        return None
    year = int(match.group("year"))
    end_month_name = match.group("m2") or match.group("m1")
    end_day = int(match.group("d2") or match.group("d1"))
    month = _MONTH_NAMES.get(end_month_name.lower())
    if month is None:
        return None
    try:
        return date(year, month, end_day)
    except ValueError:
        return None


def classify_year_entry(entry: dict, today: date) -> str:
    """Classify one YAML year block: PAST, UPCOMING, or UNKNOWN."""
    ref = (
        parse_iso_date(entry.get("end"))
        or parse_iso_date(entry.get("start"))
        or parse_date_field_end(entry.get("date"))
    )
    if ref is None:
        return "UNKNOWN"
    if ref <= today:
        return "PAST"
    return "UPCOMING"


def load_conference_entries(yaml_text: str) -> list[dict]:
    if not yaml_text or not yaml_text.strip():
        return []
    loaded = yaml.safe_load(yaml_text)
    if loaded is None:
        return []
    if isinstance(loaded, dict):
        return [loaded]
    if isinstance(loaded, list):
        return [e for e in loaded if isinstance(e, dict)]
    raise YamlValidationError(f"Conference YAML must be a list of year blocks, got {type(loaded).__name__}")


def classify_conference_years(yaml_text: str, today: date) -> list[YearLabel]:
    """Label each existing year, plus MISSING_NEXT_YEAR when the latest year is PAST."""
    entries = load_conference_entries(yaml_text)
    labels: list[YearLabel] = []
    years_present: list[int] = []
    for entry in entries:
        year = entry.get("year")
        if year is None:
            continue
        year_int = int(year)
        years_present.append(year_int)
        labels.append(YearLabel(year=year_int, status=classify_year_entry(entry, today)))

    labels.sort(key=lambda item: item.year)

    if years_present:
        max_year = max(years_present)
        latest = next(item for item in labels if item.year == max_year)
        if latest.status == "PAST" and (max_year + 1) not in years_present:
            labels.append(YearLabel(year=max_year + 1, status="MISSING_NEXT_YEAR"))

    return labels


def format_year_labels_block(today: date, labels: list[YearLabel]) -> str:
    """Machine-readable today + year labels for retrieval and aggregation user prompts."""
    lines = [
        f"today: {today.isoformat()}",
        "",
        "Year classification (precomputed in Python; do not re-derive):",
    ]
    if not labels:
        lines.append("- (no year blocks found)")
    else:
        for label in labels:
            lines.append(f"- {label.year}: {label.status}")
    lines.extend(
        [
            "",
            "PAST years must be left byte-for-byte unchanged.",
            "Only UPCOMING years may be updated.",
            "MISSING_NEXT_YEAR means no YAML block exists yet — search for it; do not invent dates if unpublished.",
            "UNKNOWN means no end/start/date — search as upcoming, do not invent dates.",
        ]
    )
    return "\n".join(lines)


def year_labels_for_yaml(yaml_text: str, today: date) -> str:
    return format_year_labels_block(today, classify_conference_years(yaml_text, today))


def valid_retrieval_results(retrieval_results: list[dict]) -> list[dict]:
    return [r for r in retrieval_results if r.get("requires_update") is not None]


def any_proposed_update(retrieval_results: list[dict]) -> bool:
    return any(r.get("requires_update") is True for r in retrieval_results)


def any_agent_timeout(results: list[dict]) -> bool:
    return any(r.get("status") == "timeout" for r in results)


def should_skip_aggregation(retrieval_results: list[dict]) -> bool:
    """Skip majority vote unless at least one agent proposed an update."""
    return not any_proposed_update(retrieval_results)


def combine_retrieval_reasoning(retrieval_results: list[dict]) -> str:
    false_results = [
        r
        for r in retrieval_results
        if r.get("requires_update") is False and r.get("reasoning")
    ]
    if not false_results:
        return ""
    return max(false_results, key=lambda r: len(r["reasoning"]))["reasoning"]


def retrieval_short_circuit(
    retrieval_results: list[dict],
    total_cost: float,
) -> dict:
    """Build a pipeline result when aggregation should not run (P6)."""
    valid = valid_retrieval_results(retrieval_results)
    timed_out = any_agent_timeout(retrieval_results)

    if not valid and timed_out:
        return pipeline_result(
            status="timeout",
            reasoning="retrieval timed out before producing structured output",
            total_cost_usd=total_cost,
            skipped_aggregation=True,
            error="retrieval agent wall-clock timeout",
        )

    if not valid:
        reasoning = "retrieval produced no structured output"
    else:
        reasoning = combine_retrieval_reasoning(retrieval_results) or (
            "retrieval agents did not propose an update"
        )

    return pipeline_result(
        status="no_changes",
        reasoning=reasoning,
        total_cost_usd=total_cost,
        skipped_aggregation=True,
    )


def resolve_conference_status(
    *,
    pushed: bool = False,
    error: str | None = None,
    timed_out: bool = False,
    status: str | None = None,
) -> str:
    """Map pipeline flags to the closed status enum (P7)."""
    if status in CONFERENCE_STATUSES:
        return status
    if timed_out:
        return "timeout"
    if error:
        return "error"
    if pushed:
        return "pushed"
    return "no_changes"


def pipeline_result(
    *,
    status: str,
    reasoning: str = "",
    total_cost_usd: float = 0.0,
    pushed: bool | None = None,
    commit_sha: str | None = None,
    updated_yaml: str = "",
    skipped_aggregation: bool = False,
    error: str | None = None,
) -> dict:
    if status not in CONFERENCE_STATUSES:
        raise ValueError(f"invalid conference status: {status!r}")
    if pushed is None:
        pushed = status == "pushed"
    result = {
        "status": status,
        "pushed": pushed,
        "commit_sha": commit_sha,
        "reasoning": reasoning,
        "updated_yaml": updated_yaml,
        "total_cost_usd": total_cost_usd,
        "skipped_aggregation": skipped_aggregation,
        "error": error,
    }
    return result


def conference_result_payload(conference_name: str, agent_result: dict) -> dict:
    """Shape returned by Modal ``process_single_conference``."""
    status = resolve_conference_status(
        pushed=bool(agent_result.get("pushed")),
        error=agent_result.get("error"),
        timed_out=agent_result.get("status") == "timeout",
        status=agent_result.get("status"),
    )
    payload = {
        "conference": conference_name,
        "status": status,
        "skipped_aggregation": agent_result.get("skipped_aggregation", False),
        "total_cost_usd": agent_result.get("total_cost_usd"),
        "error": agent_result.get("error"),
        "reasoning": agent_result.get("reasoning"),
    }
    commit_sha = agent_result.get("commit_sha")
    if commit_sha:
        payload["commit_sha"] = commit_sha
    return payload


def remote_call_error_payload(conference_name: str, exc: BaseException) -> dict:
    """Map a Modal/remote exception to the status enum."""
    name = type(exc).__name__.lower()
    status = "timeout" if "timeout" in name else "error"
    return {
        "conference": conference_name,
        "status": status,
        "error": str(exc),
    }


def get_modal_conference_timeout() -> int:
    return int(os.environ.get("MODAL_CONFERENCE_TIMEOUT", "3600"))


def get_agent_wall_clock_seconds(stage: str) -> float | None:
    """Per-agent wall-clock cap. Default 300s; ``0`` disables the cap."""
    raw = os.environ.get(f"{stage.upper()}_WALL_CLOCK_SECONDS") or os.environ.get(
        "AGENT_WALL_CLOCK_SECONDS"
    )
    if raw is not None:
        value = float(raw)
        return None if value <= 0 else value
    return 300.0


def split_year_blocks(yaml_text: str) -> list[str]:
    """Split conference YAML into raw top-level list-item strings."""
    if not yaml_text:
        return []
    matches = list(re.finditer(r"(?m)^- ", yaml_text))
    if not matches:
        stripped = yaml_text.strip()
        return [yaml_text] if stripped else []
    blocks = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(yaml_text)
        blocks.append(yaml_text[match.start() : end])
    return blocks


def extract_year_blocks(yaml_text: str) -> dict[int, str]:
    blocks: dict[int, str] = {}
    for block in split_year_blocks(yaml_text):
        match = _YEAR_LINE_RE.search(block)
        if match:
            blocks[int(match.group(1))] = block
    return blocks


def _iter_timezone_values(obj: Any, path: str = ""):
    if isinstance(obj, dict):
        for key, value in obj.items():
            child = f"{path}.{key}" if path else str(key)
            if "timezone" in str(key).lower() and isinstance(value, str):
                yield child, value
            else:
                yield from _iter_timezone_values(value, child)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            yield from _iter_timezone_values(item, f"{path}[{i}]")


def _normalize_timezone(value: str) -> str:
    return (
        value.strip()
        .lower()
        .replace(" ", "")
        .replace("−", "-")
        .replace("–", "-")
    )


def _assert_timezone_allowed(path: str, value: str) -> None:
    normalized = _normalize_timezone(value)
    if normalized in FORBIDDEN_TIMEZONES or normalized.startswith("utc-12") or normalized.startswith("utc+12"):
        raise YamlValidationError(
            f"{path}: timezone must be AoE, not {value!r}"
        )


def validate_updated_yaml(
    current_yaml: str,
    updated_yaml: str,
    today: date | None = None,
) -> None:
    """Validate aggregation YAML before git. Raises YamlValidationError."""
    if not updated_yaml or not str(updated_yaml).strip():
        raise YamlValidationError("updated YAML is empty")

    today = today or date.today()

    try:
        entries = load_conference_entries(updated_yaml)
    except yaml.YAMLError as exc:
        raise YamlValidationError(f"updated YAML does not parse: {exc}") from exc

    if not entries:
        raise YamlValidationError("updated YAML has no year blocks")

    for i, entry in enumerate(entries):
        for field in REQUIRED_YEAR_FIELDS:
            if entry.get(field) in (None, ""):
                raise YamlValidationError(
                    f"year block {i} ({entry.get('year', '?')}) missing required field {field!r}"
                )
        for path, tz_value in _iter_timezone_values(entry, f"year {entry.get('year')}"):
            _assert_timezone_allowed(path, tz_value)

    past_years = {
        label.year
        for label in classify_conference_years(current_yaml, today)
        if label.status == "PAST"
    }
    current_blocks = extract_year_blocks(current_yaml)
    updated_blocks = extract_year_blocks(updated_yaml)

    for year in sorted(past_years):
        if year not in current_blocks:
            continue
        if year not in updated_blocks:
            raise YamlValidationError(f"past year {year} is missing from updated YAML")
        if current_blocks[year].rstrip("\n") != updated_blocks[year].rstrip("\n"):
            raise YamlValidationError(
                f"past year {year} was modified; past-year blocks must be byte-for-byte unchanged"
            )


def write_conference_yaml(yaml_path: Path, content: str) -> None:
    text = content if content.endswith("\n") else content + "\n"
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_path.write_text(text, encoding="utf-8")


def git_commit_conference(
    cwd: Path,
    relpath: str,
    commit_message: str,
) -> str | None:
    """git add + commit. Returns commit SHA, or None if there is nothing to commit."""
    add = subprocess.run(
        ["git", "add", relpath],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if add.returncode != 0:
        raise GitPushError(add.stderr.strip() or add.stdout.strip() or "git add failed")

    commit = subprocess.run(
        ["git", "commit", "-m", commit_message],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    combined = f"{commit.stdout}\n{commit.stderr}"
    if commit.returncode != 0:
        if "nothing to commit" in combined.lower():
            return None
        raise GitPushError(commit.stderr.strip() or commit.stdout.strip() or "git commit failed")

    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if sha.returncode != 0:
        raise GitPushError(sha.stderr.strip() or "git rev-parse failed")
    return sha.stdout.strip()


def git_push_main(cwd: Path) -> None:
    push = subprocess.run(
        ["git", "push", "origin", "main"],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if push.returncode != 0:
        raise GitPushError(push.stderr.strip() or push.stdout.strip() or "git push failed")


def push_conference_yaml(
    *,
    conference_name: str,
    updated_yaml: str,
    current_yaml: str,
    project_root: Path,
    today: date | None = None,
    skip_remote_push: bool = False,
    commit_message: str | None = None,
) -> dict:
    """Validate, write YAML, commit, and push. Returns a pipeline status dict."""
    today = today or date.today()
    try:
        validate_updated_yaml(current_yaml, updated_yaml, today=today)
    except YamlValidationError as exc:
        return pipeline_result(
            status="error",
            error=str(exc),
            reasoning=str(exc),
            updated_yaml=updated_yaml,
        )

    relpath = f"src/data/conferences/{conference_name}.yml"
    yaml_path = project_root / relpath
    write_conference_yaml(yaml_path, updated_yaml)

    message = commit_message or f"Update {conference_name} deadlines"
    try:
        commit_sha = git_commit_conference(project_root, relpath, message)
    except GitPushError as exc:
        return pipeline_result(
            status="error",
            error=str(exc),
            reasoning=str(exc),
            updated_yaml=updated_yaml,
        )

    if commit_sha is None:
        return pipeline_result(
            status="no_changes",
            reasoning="validated YAML matches the working tree; nothing to commit",
            updated_yaml=updated_yaml,
        )

    if not skip_remote_push:
        try:
            git_push_main(project_root)
        except GitPushError as exc:
            return pipeline_result(
                status="error",
                error=str(exc),
                reasoning=str(exc),
                commit_sha=commit_sha,
                updated_yaml=updated_yaml,
            )

    return pipeline_result(
        status="pushed",
        commit_sha=commit_sha,
        reasoning="wrote YAML and pushed to main",
        updated_yaml=updated_yaml,
    )

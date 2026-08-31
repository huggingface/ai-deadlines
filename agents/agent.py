"""Agent for finding and editing deadlines of a given conference using the Claude Agent SDK.

Implements a 3-stage pipeline:
1. Retrieval: N agents independently search the web for conference information
2. Aggregation: A majority-vote agent synthesizes the retrieval results
3. Push: Python validates the YAML, writes the file, and git-commits/pushes to main

Usage:

```bash
uv run --env-file keys.env -m agents.agent --conference_name <name> --num-retrieval-agents 5
uv run --env-file keys.env -m agents.agent --conference_name <name> --dry-run
```
"""

import argparse
import asyncio
import json
from datetime import date, datetime
import os
from pathlib import Path

import aiofiles

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    HookMatcher,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)
from claude_agent_sdk.types import McpHttpServerConfig

from agents.pipeline_utils import (
    BUDGET_EXHAUSTED_FOLLOWUP,
    BUDGET_EXHAUSTED_MESSAGE,
    ToolBudgetState,
    any_proposed_update,
    get_agent_wall_clock_seconds,
    pipeline_result,
    push_conference_yaml,
    retrieval_short_circuit,
    valid_retrieval_results,
    year_labels_for_yaml,
)

SCRIPT_DIR = Path(__file__).parent

PROJECT_ROOT = (
    Path(os.getcwd())
    if os.environ.get("USE_CWD_AS_PROJECT_ROOT")
    else SCRIPT_DIR.parent
)

# --- Structured output schemas ---

RETRIEVAL_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "requires_update": {
            "type": "boolean",
            "description": "Whether the conference data needs an update",
        },
        "reasoning": {
            "type": "string",
            "description": "Explanation of why the data does or does not need an update",
        },
        "updated_yaml": {
            "type": "string",
            "description": "The full updated YAML content",
        },
        "source_urls": {
            "type": "array",
            "items": {"type": "string"},
            "description": "URLs used as sources for the information",
        },
    },
    "required": ["requires_update", "reasoning", "updated_yaml", "source_urls"],
}

AGGREGATION_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "reasoning": {
            "type": "string",
            "description": (
                "Explanation of how the majority vote was performed, how the results "
                "were compared, where the colleagues agreed/disagreed, and how the "
                "synthesis was derived"
            ),
        },
        "requires_update": {
            "type": "boolean",
            "description": "Whether the conference data needs updating (based on majority agreement)",
        },
        "updated_yaml": {
            "type": "string",
            "description": "The synthesized updated YAML content",
        },
        "source_urls": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Combined source URLs from the retrieval results that support "
                "the synthesized output"
            ),
        },
    },
    "required": ["reasoning", "requires_update", "updated_yaml", "source_urls"],
}

# --- Utilities ---


def format_date_verbose(dt: datetime) -> str:
    day = dt.day
    suffix = (
        "th"
        if 11 <= day <= 13
        else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    )
    return f"{dt.strftime('%A')}, the {day}{suffix} of {dt.strftime('%B')}, {dt.year}"


async def read_prompt(filename: str) -> str:
    """Read a prompt file from the script directory."""
    filepath = SCRIPT_DIR / filename
    async with aiofiles.open(filepath, "r", encoding="utf-8") as f:
        return await f.read()


async def read_app_readme() -> str:
    """Read the app README.md from the project root."""
    readme_path = PROJECT_ROOT / "README.md"
    async with aiofiles.open(readme_path, "r", encoding="utf-8") as f:
        return await f.read()


async def load_conference_data(conference_name: str) -> str:
    """Load conference data from YAML file."""
    yaml_path = (
        PROJECT_ROOT / "src" / "data" / "conferences" / f"{conference_name}.yml"
    )
    if not yaml_path.exists():
        print(f"Warning: Conference file not found at {yaml_path}")
        return ""
    async with aiofiles.open(yaml_path, "r", encoding="utf-8") as f:
        return await f.read()


def _get_settings_path() -> str:
    """Resolve the settings.local.json path."""
    settings_path = PROJECT_ROOT / ".claude" / "settings.local.json"
    if not settings_path.exists():
        settings_path = Path.home() / ".claude" / "settings.local.json"
    return str(settings_path)


def _get_exa_mcp_servers() -> dict[str, McpHttpServerConfig]:
    """Configure Exa MCP server if API key is available and not disabled."""
    disable_mcp = os.environ.get("DISABLE_EXA_MCP", "").lower() in (
        "1",
        "true",
        "yes",
    )
    exa_api_key = os.environ.get("EXA_API_KEY", "")

    if disable_mcp:
        print("Exa MCP disabled via DISABLE_EXA_MCP environment variable")
        return {}
    elif exa_api_key:
        print(f"EXA_API_KEY found (length: {len(exa_api_key)})")
        return {
            "exa": McpHttpServerConfig(
                type="http",
                url=f"https://mcp.exa.ai/mcp?exaApiKey={exa_api_key}",
            )
        }
    else:
        print("EXA_API_KEY not found, Exa MCP will not be available")
        return {}


# --- Shared agent runner ---


MAX_RETRIES = 3
SILENT_EXIT_THRESHOLD = 2  # message_count <= this with empty result triggers retry

# Per-agent limits (override per stage with e.g. RETRIEVAL_MAX_TURNS)
DEFAULT_MAX_TURNS = 12
DEFAULT_MAX_BUDGET_USD = 1.50
STAGE_LIMIT_DEFAULTS: dict[str, tuple[int, float]] = {
    "retrieval": (12, 1.50),
    "aggregation": (8, 1.00),
    "push": (6, 0.50),
}


def _build_fail_closed_hooks(max_turns: int) -> dict:
    """PostToolUse nudge on the last search result; PreToolUse deny after that."""
    state = ToolBudgetState(max_turns)

    async def post_tool_use(input_data, tool_use_id, context):
        extra = state.on_post_tool_use(input_data.get("tool_name", ""))
        if not extra:
            return {}
        print("[hooks] PostToolUse: tool-call budget exhausted, injecting answer-now context")
        return {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": extra,
            }
        }

    async def pre_tool_use(input_data, tool_use_id, context):
        tool_name = input_data.get("tool_name", "")
        if not state.should_deny_pre_tool_use(tool_name):
            return {}
        print(f"[hooks] PreToolUse: denying {tool_name} (budget exhausted)")
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": BUDGET_EXHAUSTED_MESSAGE,
            }
        }

    return {
        "PostToolUse": [HookMatcher(hooks=[post_tool_use])],
        "PreToolUse": [HookMatcher(hooks=[pre_tool_use])],
    }


def _has_structured_output(result: dict) -> bool:
    return result.get("requires_update") is not None


def _get_stage_limits(stage: str) -> tuple[int, float]:
    """Return (max_turns, max_budget_usd) for a pipeline stage."""
    default_turns, default_budget = STAGE_LIMIT_DEFAULTS.get(
        stage, (DEFAULT_MAX_TURNS, DEFAULT_MAX_BUDGET_USD)
    )

    stage_turns = os.environ.get(f"{stage.upper()}_MAX_TURNS")
    global_turns = os.environ.get("AGENT_MAX_TURNS")
    if stage_turns:
        max_turns = int(stage_turns)
    elif global_turns:
        max_turns = int(global_turns)
    else:
        max_turns = default_turns

    stage_budget = os.environ.get(f"{stage.upper()}_MAX_BUDGET_USD")
    global_budget = os.environ.get("AGENT_MAX_BUDGET_USD")
    if stage_budget:
        max_budget_usd = float(stage_budget)
    elif global_budget:
        max_budget_usd = float(global_budget)
    else:
        max_budget_usd = default_budget

    return max_turns, max_budget_usd


def _consume_agent_messages(
    agent_label: str,
    message,
    subagent_names: dict[str, str],
    tool_names: dict[str, str],
) -> None:
    """Log a single SDK message (shared by the main query and no-tools follow-up)."""
    if isinstance(message, AssistantMessage):
        if message.parent_tool_use_id is None:
            agent_prefix = f"[{agent_label}]"
        else:
            subagent_name = subagent_names.get(
                message.parent_tool_use_id, "subagent"
            )
            agent_prefix = f"[{agent_label}/{subagent_name}]"

        for block in message.content:
            if isinstance(block, TextBlock):
                print(f"{agent_prefix} Claude: {block.text}")
            elif isinstance(block, ToolUseBlock):
                print(f"{agent_prefix} Tool: {block.name}({block.input})")
                tool_names[block.id] = block.name
                if block.name == "Task" and isinstance(block.input, dict):
                    subagent_names[block.id] = block.input.get(
                        "subagent_type", "subagent"
                    )

    elif isinstance(message, UserMessage):
        if isinstance(message.content, list):
            for block in message.content:
                if isinstance(block, ToolResultBlock):
                    tool_name = tool_names.get(block.tool_use_id, "unknown")
                    content_str = str(block.content) if block.content else "(empty)"
                    if len(content_str) > 500:
                        content_str = content_str[:500] + "... (truncated)"
                    error_indicator = " [ERROR]" if block.is_error else ""
                    print(
                        f"[{agent_label}][result]{error_indicator} "
                        f"{tool_name}: {content_str}"
                    )


async def _run_no_tools_followup(
    *,
    system_prompt: str,
    output_schema: dict,
    agent_label: str,
    session_id: str | None,
) -> tuple[dict, float, int]:
    """One no-tools query after error_max_turns with empty structured output."""

    def on_stderr(data: str):
        print(f"[{agent_label}][stderr] {data.strip()}")

    options_kwargs: dict = {
        "system_prompt": system_prompt,
        "permission_mode": "bypassPermissions",
        "settings": _get_settings_path(),
        "stderr": on_stderr,
        "output_format": {
            "type": "json_schema",
            "schema": output_schema,
        },
        "max_turns": 1,
        "tools": [],
    }
    if session_id:
        options_kwargs["resume"] = session_id

    print(
        f"[{agent_label}] error_max_turns with empty structured output; "
        "running no-tools follow-up"
    )
    result: dict = {}
    cost_usd = 0.0
    message_count = 0
    subagent_names: dict[str, str] = {}
    tool_names: dict[str, str] = {}

    try:
        async for message in query(
            prompt=BUDGET_EXHAUSTED_FOLLOWUP,
            options=ClaudeAgentOptions(**options_kwargs),
        ):
            message_count += 1
            print(f"[{agent_label}][follow-up] Message {message_count}: {type(message).__name__}")
            _consume_agent_messages(agent_label, message, subagent_names, tool_names)
            if isinstance(message, ResultMessage):
                if message.total_cost_usd and message.total_cost_usd > 0:
                    cost_usd = message.total_cost_usd
                if message.structured_output:
                    result = message.structured_output
                    print(f"[{agent_label}][follow-up][structured_output] {result}")
    except Exception as e:
        print(f"[{agent_label}] Follow-up error: {type(e).__name__}: {e}")

    return result, cost_usd, message_count


async def _run_agent_once(
    system_prompt: str,
    user_prompt: str,
    output_schema: dict,
    agent_label: str = "agent",
    mcp_servers: dict[str, McpHttpServerConfig] | None = None,
    max_turns: int | None = None,
    max_budget_usd: float | None = None,
    hooks: dict | None = None,
    wall_clock_seconds: float | None = None,
    allow_max_turns_fallback: bool = False,
) -> tuple[dict, float, int]:
    """Run a single agent query attempt.

    Returns:
        A tuple of (structured output dict, cost in USD, message count).
    """

    def on_stderr(data: str):
        print(f"[{agent_label}][stderr] {data.strip()}")

    options_kwargs: dict = {
        "system_prompt": system_prompt,
        "permission_mode": "bypassPermissions",
        "settings": _get_settings_path(),
        "stderr": on_stderr,
        "output_format": {
            "type": "json_schema",
            "schema": output_schema,
        },
    }
    if max_turns is not None:
        options_kwargs["max_turns"] = max_turns
    if max_budget_usd is not None:
        options_kwargs["max_budget_usd"] = max_budget_usd
    if mcp_servers:
        options_kwargs["mcp_servers"] = mcp_servers
    if hooks:
        options_kwargs["hooks"] = hooks

    options = ClaudeAgentOptions(**options_kwargs)
    limits = []
    if max_turns is not None:
        limits.append(f"max_turns={max_turns}")
    if max_budget_usd is not None:
        limits.append(f"max_budget_usd=${max_budget_usd:.2f}")
    if wall_clock_seconds:
        limits.append(f"wall_clock={wall_clock_seconds:.0f}s")
    if limits:
        print(f"[{agent_label}] Limits: {', '.join(limits)}")

    async def _inner() -> tuple[dict, float, int]:
        subagent_names: dict[str, str] = {}
        tool_names: dict[str, str] = {}
        message_count = 0
        result: dict = {}
        cost_usd = 0.0
        session_id: str | None = None
        hit_error_max_turns = False

        try:
            async for message in query(prompt=user_prompt, options=options):
                message_count += 1
                print(f"[{agent_label}] Message {message_count}: {type(message).__name__}")
                _consume_agent_messages(
                    agent_label, message, subagent_names, tool_names
                )

                if isinstance(message, ResultMessage):
                    session_id = message.session_id
                    if message.subtype in ("error_max_turns", "error_max_budget_usd"):
                        print(
                            f"[{agent_label}] Limit reached: {message.subtype} "
                            f"(cost=${message.total_cost_usd or 0:.4f})"
                        )
                    if message.subtype == "error_max_turns":
                        hit_error_max_turns = True
                    if hasattr(message, "error") and message.error:
                        print(f"[{agent_label}][result] ERROR: {message.error}")
                    if message.total_cost_usd and message.total_cost_usd > 0:
                        cost_usd = message.total_cost_usd
                        print(f"[{agent_label}] Cost: ${cost_usd:.4f}")
                    if (
                        hasattr(message, "structured_output")
                        and message.structured_output
                    ):
                        result = message.structured_output
                        print(f"[{agent_label}][structured_output] {result}")

        except Exception as e:
            print(f"[{agent_label}] Error: {type(e).__name__}: {e}")
            import traceback

            traceback.print_exc()
            result["error"] = str(e)

        if (
            allow_max_turns_fallback
            and hit_error_max_turns
            and not _has_structured_output(result)
        ):
            follow_result, follow_cost, follow_count = await _run_no_tools_followup(
                system_prompt=system_prompt,
                output_schema=output_schema,
                agent_label=agent_label,
                session_id=session_id,
            )
            cost_usd += follow_cost
            message_count += follow_count
            if follow_result:
                result = follow_result

        print(f"[{agent_label}] Completed. Total messages: {message_count}")
        return result, cost_usd, message_count

    try:
        if wall_clock_seconds:
            return await asyncio.wait_for(_inner(), timeout=wall_clock_seconds)
        return await _inner()
    except asyncio.TimeoutError:
        print(
            f"[{agent_label}] Wall-clock timeout after {wall_clock_seconds:.0f}s"
        )
        return (
            {
                "status": "timeout",
                "error": f"agent wall-clock timeout after {wall_clock_seconds:.0f}s",
            },
            0.0,
            0,
        )


async def _run_agent(
    system_prompt: str,
    user_prompt: str,
    output_schema: dict,
    agent_label: str = "agent",
    mcp_servers: dict[str, McpHttpServerConfig] | None = None,
    max_turns: int | None = None,
    max_budget_usd: float | None = None,
    hooks: dict | None = None,
    wall_clock_seconds: float | None = None,
    allow_max_turns_fallback: bool = False,
) -> tuple[dict, float]:
    """Run a single agent query with structured output and automatic retries.

    The Claude Agent SDK on Modal can silently exit after only the SystemMessage,
    producing an empty result. This wrapper detects that (low message count with
    an empty result) and retries up to MAX_RETRIES times.

    Wall-clock timeouts are not retried.

    Args:
        system_prompt: The system prompt for the agent.
        user_prompt: The user prompt for the agent.
        output_schema: JSON schema for structured output.
        agent_label: Label for log messages (e.g. "retrieval-1", "aggregation").
        mcp_servers: Optional MCP server configuration.

    Returns:
        A tuple of (structured output dict, cost in USD).
    """
    total_cost = 0.0

    for attempt in range(1, MAX_RETRIES + 1):
        result, cost, message_count = await _run_agent_once(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_schema=output_schema,
            agent_label=agent_label,
            mcp_servers=mcp_servers,
            max_turns=max_turns,
            max_budget_usd=max_budget_usd,
            hooks=hooks,
            wall_clock_seconds=wall_clock_seconds,
            allow_max_turns_fallback=allow_max_turns_fallback,
        )
        total_cost += cost

        if result.get("status") == "timeout":
            return result, total_cost

        is_silent_exit = (
            message_count <= SILENT_EXIT_THRESHOLD
            and not result
        )

        if not is_silent_exit or attempt == MAX_RETRIES:
            if is_silent_exit:
                print(
                    f"[{agent_label}] WARNING: SDK silent exit persisted after "
                    f"{MAX_RETRIES} attempts"
                )
            return result, total_cost

        print(
            f"[{agent_label}] SDK silent exit detected "
            f"({message_count} messages, empty result). "
            f"Retrying ({attempt}/{MAX_RETRIES})..."
        )
        await asyncio.sleep(2 * attempt)

    return result, total_cost


# --- Stage 1: Information Retrieval ---


async def run_retrieval_agent(
    conference_name: str, agent_index: int = 1
) -> tuple[dict, float]:
    """Run a single retrieval agent to search for conference information.

    Args:
        conference_name: Name of the conference.
        agent_index: 1-based index of this agent (for logging).

    Returns:
        Tuple of (structured retrieval result dict, cost in USD).
    """
    conference_data = await load_conference_data(conference_name)
    app_readme = await read_app_readme()
    today = date.today()
    year_labels = year_labels_for_yaml(conference_data, today)

    system_template = await read_prompt("prompts/retrieval_system_prompt.md")
    max_turns, max_budget_usd = _get_stage_limits("retrieval")
    system_prompt = system_template.format(
        conference_name=conference_name,
        date=format_date_verbose(datetime.now()),
        app_readme=app_readme,
        max_turns=max_turns,
    )

    user_template = await read_prompt("prompts/retrieval_user_prompt.md")
    user_prompt = user_template.format(
        conference_name=conference_name,
        conference_data=conference_data if conference_data else "No existing data found.",
        year_labels=year_labels,
        max_turns=max_turns,
    )

    mcp_servers = _get_exa_mcp_servers()

    return await _run_agent(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        output_schema=RETRIEVAL_RESULT_SCHEMA,
        agent_label=f"retrieval-{agent_index}",
        mcp_servers=mcp_servers or None,
        max_turns=max_turns,
        max_budget_usd=max_budget_usd,
        hooks=_build_fail_closed_hooks(max_turns),
        wall_clock_seconds=get_agent_wall_clock_seconds("retrieval"),
        allow_max_turns_fallback=True,
    )


async def run_retrieval_agents(
    conference_name: str, n: int = 3
) -> tuple[list[dict], float]:
    """Run N retrieval agents sequentially.

    Args:
        conference_name: Name of the conference.
        n: Number of retrieval agents to run.

    Returns:
        Tuple of (list of N retrieval result dicts, total cost in USD).
    """
    results = []
    total_cost = 0.0
    for i in range(1, n + 1):
        print(f"\n--- Retrieval Agent {i}/{n} ---")
        result, cost = await run_retrieval_agent(conference_name, agent_index=i)
        results.append(result)
        total_cost += cost
    return results, total_cost


# --- Stage 2: Aggregation (Majority Vote) ---


async def run_aggregation_agent(
    conference_name: str, retrieval_results: list[dict]
) -> tuple[dict, float]:
    """Run the aggregation agent to perform majority vote over retrieval results.

    Uses a dedicated aggregation system prompt and has access to Exa MCP
    for independently verifying factual claims when agents disagree.

    Args:
        conference_name: Name of the conference.
        retrieval_results: List of retrieval result dicts from stage 1.

    Returns:
        Tuple of (aggregated result dict with consensus decision, cost in USD).
    """
    conference_data = await load_conference_data(conference_name)
    today = date.today()
    year_labels = year_labels_for_yaml(conference_data, today)

    system_template = await read_prompt("prompts/aggregation_system_prompt.md")
    max_turns, max_budget_usd = _get_stage_limits("aggregation")
    system_prompt = system_template.format(
        conference_name=conference_name,
        date=format_date_verbose(datetime.now()),
        max_turns=max_turns,
    )

    results_text = ""
    for i, result in enumerate(retrieval_results, 1):
        results_text += f"### Agent {i} result\n\n"
        results_text += f"```json\n{json.dumps(result, indent=2)}\n```\n\n"

    user_template = await read_prompt("prompts/aggregation_user_prompt.md")
    user_prompt = user_template.format(
        conference_name=conference_name,
        conference_data=conference_data if conference_data else "No existing data found.",
        num_agents=len(retrieval_results),
        retrieval_results=results_text,
        year_labels=year_labels,
    )

    mcp_servers = _get_exa_mcp_servers()

    return await _run_agent(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        output_schema=AGGREGATION_RESULT_SCHEMA,
        agent_label="aggregation",
        mcp_servers=mcp_servers or None,
        max_turns=max_turns,
        max_budget_usd=max_budget_usd,
        hooks=_build_fail_closed_hooks(max_turns),
        wall_clock_seconds=get_agent_wall_clock_seconds("aggregation"),
        allow_max_turns_fallback=True,
    )


# --- Stage 3: Push to Main (deterministic; no LLM) ---


def push_verified_yaml(conference_name: str, verified_yaml: str) -> dict:
    """Validate YAML, write the file, and git commit + push on main."""
    yaml_path = (
        PROJECT_ROOT / "src" / "data" / "conferences" / f"{conference_name}.yml"
    )
    current_yaml = yaml_path.read_text(encoding="utf-8") if yaml_path.exists() else ""
    return push_conference_yaml(
        conference_name=conference_name,
        updated_yaml=verified_yaml,
        current_yaml=current_yaml,
        project_root=PROJECT_ROOT,
        today=date.today(),
    )


# --- Orchestrator ---


def _all_agree_update(retrieval_results: list[dict]) -> bool:
    valid = valid_retrieval_results(retrieval_results)
    return len(valid) >= 2 and all(r.get("requires_update") is True for r in valid)


async def find_conference_deadlines(
    conference_name: str,
    num_retrieval_agents: int = 3,
    dry_run: bool = False,
) -> dict:
    """Orchestrate the 3-stage pipeline for a conference.

    Stage 1: Run N retrieval agents sequentially to gather information.
    Stage 2: Run an aggregation agent to perform majority vote (only if some
        agent proposed an update).
    Stage 3: If an update is needed, validate YAML and git push to main.

    Args:
        conference_name: Name of the conference.
        num_retrieval_agents: Number of retrieval agents to run (default 3).
        dry_run: If True, skip pushing and just print the aggregated result.

    Returns:
        Final result dict with status, pushed, commit_sha, reasoning, and cost.
    """
    total_cost = 0.0

    print(f"Processing conference: {conference_name}")
    if dry_run:
        print("DRY RUN: push will be skipped")
    pipeline_suffix = "" if dry_run else " -> push"
    print(
        f"Pipeline: {num_retrieval_agents} retrieval agents "
        f"-> aggregation{pipeline_suffix}"
    )

    # === Stage 1: Information Retrieval ===
    print(f"\n{'=' * 60}")
    print(
        f"=== Stage 1: Information Retrieval "
        f"({num_retrieval_agents} agents) ==="
    )
    print(f"{'=' * 60}")

    retrieval_results, retrieval_cost = await run_retrieval_agents(
        conference_name, n=num_retrieval_agents
    )
    total_cost += retrieval_cost

    for i, result in enumerate(retrieval_results, 1):
        requires_update = result.get("requires_update", "unknown")
        agent_status = result.get("status", "")
        extra = f" status={agent_status}" if agent_status else ""
        print(f"  Agent {i}: requires_update={requires_update}{extra}")
    print(f"  Retrieval stage cost: ${retrieval_cost:.4f}")

    if not any_proposed_update(retrieval_results):
        print(
            "\nNo retrieval agent proposed an update. "
            "Skipping aggregation and push."
        )
        print(f"\nTotal pipeline cost: ${total_cost:.4f}")
        result = retrieval_short_circuit(retrieval_results, total_cost)
        print(f"  Status: {result['status']}")
        return result

    # === Stage 2: Aggregation (Majority Vote) ===
    print(f"\n{'=' * 60}")
    print("=== Stage 2: Aggregation (Majority Vote) ===")
    print(f"{'=' * 60}")

    aggregation_result, aggregation_cost = await run_aggregation_agent(
        conference_name, retrieval_results
    )
    total_cost += aggregation_cost

    if aggregation_result.get("status") == "timeout":
        print("\nAggregation timed out.")
        print(f"\nTotal pipeline cost: ${total_cost:.4f}")
        return pipeline_result(
            status="timeout",
            reasoning="aggregation agent wall-clock timeout",
            total_cost_usd=total_cost,
            error=aggregation_result.get("error", "aggregation timeout"),
        )

    requires_update = aggregation_result.get("requires_update", False)

    # Fallback: if aggregation returned empty (SDK silent exit) but retrieval
    # agents unanimously agreed on an update, use the first retrieval result.
    valid_results = valid_retrieval_results(retrieval_results)
    all_agree_update = _all_agree_update(retrieval_results)
    if not _has_structured_output(aggregation_result) and all_agree_update:
        print(
            "\nWARNING: Aggregation agent returned empty (SDK silent exit). "
            "All retrieval agents unanimously agreed on update — using "
            "first retrieval result as fallback."
        )
        aggregation_result = valid_results[0]
        requires_update = True

    print(f"\nAggregation result: requires_update={requires_update}")
    reasoning_preview = str(aggregation_result.get("reasoning", "N/A"))[:200]
    print(f"Reasoning: {reasoning_preview}")
    print(f"  Aggregation stage cost: ${aggregation_cost:.4f}")

    if not requires_update:
        print("\nNo update needed. Skipping push.")
        print(f"\nTotal pipeline cost: ${total_cost:.4f}")
        return pipeline_result(
            status="no_changes",
            reasoning=aggregation_result.get("reasoning", ""),
            updated_yaml=aggregation_result.get("updated_yaml", ""),
            total_cost_usd=total_cost,
        )

    if dry_run:
        print("\nDRY RUN: Update needed but skipping push.")
        print(f"Updated YAML:\n{aggregation_result.get('updated_yaml', '')}")
        print(f"\nTotal pipeline cost: ${total_cost:.4f}")
        return pipeline_result(
            status="no_changes",
            reasoning=aggregation_result.get("reasoning", ""),
            updated_yaml=aggregation_result.get("updated_yaml", ""),
            total_cost_usd=total_cost,
        )

    # === Stage 3: Validate + git push (no LLM) ===
    print(f"\n{'=' * 60}")
    print("=== Stage 3: Push to Main ===")
    print(f"{'=' * 60}")

    verified_yaml = aggregation_result.get("updated_yaml", "")
    push_result = push_verified_yaml(conference_name, verified_yaml)
    if push_result.get("status") != "error":
        push_result["reasoning"] = aggregation_result.get(
            "reasoning", push_result.get("reasoning", "")
        )
    push_result["total_cost_usd"] = total_cost
    print(f"  Push status: {push_result.get('status')}")
    if push_result.get("commit_sha"):
        print(f"  commit_sha: {push_result['commit_sha']}")
    if push_result.get("error"):
        print(f"  error: {push_result['error']}")

    print(f"\nTotal pipeline cost: ${total_cost:.4f}")
    return push_result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Find conference deadlines using Claude Agent SDK"
    )
    parser.add_argument(
        "--conference_name",
        type=str,
        required=True,
        help="The name of the conference to find the deadlines of",
    )
    parser.add_argument(
        "--num-retrieval-agents",
        type=int,
        default=3,
        help="Number of retrieval agents to run (default: 3)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run retrieval and aggregation only, skip pushing to main",
    )
    args = parser.parse_args()

    result = asyncio.run(
        find_conference_deadlines(
            args.conference_name,
            num_retrieval_agents=args.num_retrieval_agents,
            dry_run=args.dry_run,
        )
    )
    print(f"\nResult: {result}")

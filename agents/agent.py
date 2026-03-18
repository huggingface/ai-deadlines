"""Agent for finding and editing deadlines of a given conference using the Claude Agent SDK.

Implements a 3-stage pipeline:
1. Retrieval: N agents independently search the web for conference information
2. Aggregation: A majority-vote agent synthesizes the retrieval results
3. PR Creation: An agent writes the updated YAML and creates a pull request

Usage:

```bash
http://localhost:8080/ <name>
uv run --env-file keys.env -m agents.agent --conference_name <name> --num-retrieval-agents 5
uv run --env-file keys.env -m agents.agent --conference_name <name> --dry-run
```
"""

import argparse
import asyncio
import json
from datetime import datetime
import os
from pathlib import Path

import aiofiles

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)
from claude_agent_sdk.types import McpHttpServerConfig

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

PR_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "created_pr": {
            "type": "boolean",
            "description": "Whether a PR was created",
        },
        "pr_url": {
            "type": "string",
            "description": "URL of the created PR (if any)",
        },
    },
    "required": ["created_pr"],
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


async def _run_agent(
    system_prompt: str,
    user_prompt: str,
    output_schema: dict,
    agent_label: str = "agent",
    mcp_servers: dict[str, McpHttpServerConfig] | None = None,
) -> tuple[dict, float]:
    """Run a single agent query with structured output.

    Wraps a single ``query()`` call with the message loop, stderr handling,
    logging, and structured output extraction so each stage doesn't duplicate
    this boilerplate.

    Args:
        system_prompt: The system prompt for the agent.
        user_prompt: The user prompt for the agent.
        output_schema: JSON schema for structured output.
        agent_label: Label for log messages (e.g. "retrieval-1", "aggregation").
        mcp_servers: Optional MCP server configuration.

    Returns:
        A tuple of (structured output dict, cost in USD).
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
    if mcp_servers:
        options_kwargs["mcp_servers"] = mcp_servers

    options = ClaudeAgentOptions(**options_kwargs)

    subagent_names: dict[str, str] = {}
    tool_names: dict[str, str] = {}
    message_count = 0
    result: dict = {}
    cost_usd = 0.0

    try:
        async for message in query(prompt=user_prompt, options=options):
            message_count += 1
            msg_type = type(message).__name__
            print(f"[{agent_label}] Message {message_count}: {msg_type}")

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
                            tool_name = tool_names.get(
                                block.tool_use_id, "unknown"
                            )
                            content_str = (
                                str(block.content) if block.content else "(empty)"
                            )
                            if len(content_str) > 500:
                                content_str = content_str[:500] + "... (truncated)"
                            error_indicator = " [ERROR]" if block.is_error else ""
                            print(
                                f"[{agent_label}][result]{error_indicator} "
                                f"{tool_name}: {content_str}"
                            )

            elif isinstance(message, ResultMessage):
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

    print(f"[{agent_label}] Completed. Total messages: {message_count}")
    return result, cost_usd


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

    system_template = await read_prompt("prompts/retrieval_system_prompt.md")
    system_prompt = system_template.format(
        conference_name=conference_name,
        date=format_date_verbose(datetime.now()),
        app_readme=app_readme,
    )

    user_template = await read_prompt("prompts/retrieval_user_prompt.md")
    user_prompt = user_template.format(
        conference_name=conference_name,
        conference_data=conference_data if conference_data else "No existing data found.",
    )

    mcp_servers = _get_exa_mcp_servers()

    return await _run_agent(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        output_schema=RETRIEVAL_RESULT_SCHEMA,
        agent_label=f"retrieval-{agent_index}",
        mcp_servers=mcp_servers or None,
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

    system_template = await read_prompt("prompts/aggregation_system_prompt.md")
    system_prompt = system_template.format(
        conference_name=conference_name,
        date=format_date_verbose(datetime.now()),
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
    )

    mcp_servers = _get_exa_mcp_servers()

    return await _run_agent(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        output_schema=AGGREGATION_RESULT_SCHEMA,
        agent_label="aggregation",
        mcp_servers=mcp_servers or None,
    )


# --- Stage 3: PR Creation ---


async def _get_git_remote_info() -> str:
    """Run ``git remote -v`` and return the output."""
    proc = await asyncio.create_subprocess_exec(
        "git", "remote", "-v",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(PROJECT_ROOT),
    )
    stdout, _ = await proc.communicate()
    return stdout.decode().strip()


async def run_pr_agent(
    conference_name: str,
    verified_yaml: str,
    changes_summary: str,
    branch_name: str,
) -> tuple[dict, float]:
    """Run the PR agent to write YAML and create a pull request.

    Args:
        conference_name: Name of the conference.
        verified_yaml: The verified updated YAML content to write.
        changes_summary: Summary of what changed.
        branch_name: Git branch name to use for the PR.

    Returns:
        Tuple of (PR result dict with created_pr and pr_url, cost in USD).
    """
    current_yaml = await load_conference_data(conference_name)
    git_remotes = await _get_git_remote_info()

    system_template = await read_prompt("prompts/pr_system_prompt.md")
    system_prompt = system_template.format(
        conference_name=conference_name,
        git_remotes=git_remotes,
        branch_name=branch_name,
    )

    user_template = await read_prompt("prompts/pr_user_prompt.md")
    user_prompt = user_template.format(
        conference_name=conference_name,
        updated_yaml=verified_yaml,
        changes_summary=changes_summary,
        current_yaml=current_yaml if current_yaml else "(file does not exist yet)",
        branch_name=branch_name,
    )

    return await _run_agent(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        output_schema=PR_RESULT_SCHEMA,
        agent_label="pr",
        mcp_servers=None,
    )


# --- Orchestrator ---


def _generate_branch_name(conference_name: str) -> str:
    """Generate a unique branch name with a date stamp to avoid collisions."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"feature/update_{conference_name}_{stamp}"


async def _checkout_main() -> None:
    """Switch back to the main branch after PR creation."""
    proc = await asyncio.create_subprocess_exec(
        "git", "checkout", "main",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(PROJECT_ROOT),
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode == 0:
        print("[cleanup] Switched back to main branch")
    else:
        print(f"[cleanup] Warning: could not switch to main: {stderr.decode().strip()}")


async def find_conference_deadlines(
    conference_name: str,
    num_retrieval_agents: int = 3,
    dry_run: bool = False,
) -> dict:
    """Orchestrate the 3-stage pipeline for a conference.

    Stage 1: Run N retrieval agents sequentially to gather information.
    Stage 2: Run an aggregation agent to perform majority vote.
    Stage 3: If an update is needed, run a PR agent to create a pull request.

    Args:
        conference_name: Name of the conference.
        num_retrieval_agents: Number of retrieval agents to run (default 3).
        dry_run: If True, skip PR creation and just print the aggregated result.

    Returns:
        Final result dict with created_pr, pr_url, reasoning, and total_cost_usd.
    """
    total_cost = 0.0

    print(f"Processing conference: {conference_name}")
    if dry_run:
        print("DRY RUN: PR creation will be skipped")
    pipeline_suffix = "" if dry_run else " -> PR"
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
        print(f"  Agent {i}: requires_update={requires_update}")
    print(f"  Retrieval stage cost: ${retrieval_cost:.4f}")

    # === Stage 2: Aggregation (Majority Vote) ===
    print(f"\n{'=' * 60}")
    print("=== Stage 2: Aggregation (Majority Vote) ===")
    print(f"{'=' * 60}")

    aggregation_result, aggregation_cost = await run_aggregation_agent(
        conference_name, retrieval_results
    )
    total_cost += aggregation_cost

    requires_update = aggregation_result.get("requires_update", False)
    print(f"\nAggregation result: requires_update={requires_update}")
    reasoning_preview = aggregation_result.get("reasoning", "N/A")[:200]
    print(f"Reasoning: {reasoning_preview}")
    print(f"  Aggregation stage cost: ${aggregation_cost:.4f}")

    if not requires_update:
        print("\nNo update needed. Skipping PR creation.")
        print(f"\nTotal pipeline cost: ${total_cost:.4f}")
        return {
            "created_pr": False,
            "pr_url": None,
            "reasoning": aggregation_result.get("reasoning", ""),
            "updated_yaml": aggregation_result.get("updated_yaml", ""),
            "total_cost_usd": total_cost,
        }

    if dry_run:
        print("\nDRY RUN: Update needed but skipping PR creation.")
        print(f"Updated YAML:\n{aggregation_result.get('updated_yaml', '')}")
        print(f"\nTotal pipeline cost: ${total_cost:.4f}")
        return {
            "created_pr": False,
            "pr_url": None,
            "reasoning": aggregation_result.get("reasoning", ""),
            "updated_yaml": aggregation_result.get("updated_yaml", ""),
            "total_cost_usd": total_cost,
        }

    # === Stage 3: PR Creation ===
    print(f"\n{'=' * 60}")
    print("=== Stage 3: PR Creation ===")
    print(f"{'=' * 60}")

    verified_yaml = aggregation_result.get("updated_yaml", "")
    changes_summary = aggregation_result.get("reasoning", "")
    branch_name = _generate_branch_name(conference_name)
    print(f"  Branch: {branch_name}")

    pr_result, pr_cost = await run_pr_agent(
        conference_name, verified_yaml, changes_summary, branch_name
    )
    total_cost += pr_cost
    print(f"  PR stage cost: ${pr_cost:.4f}")

    await _checkout_main()

    print(f"\nTotal pipeline cost: ${total_cost:.4f}")

    return {
        "created_pr": pr_result.get("created_pr", False),
        "pr_url": pr_result.get("pr_url"),
        "reasoning": aggregation_result.get("reasoning", ""),
        "total_cost_usd": total_cost,
    }


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
        help="Run retrieval and aggregation only, skip PR creation",
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

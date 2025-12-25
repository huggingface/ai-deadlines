"""Agent for finding and editing deadlines of a given conference using the Claude Agent SDK.

Usage:

```bash
uv run --env-file keys.env -m agents.agent --conference_name <name>
```
"""

import argparse
import asyncio
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

# Script directory for resolving relative paths
SCRIPT_DIR = Path(__file__).parent

# Project root directory (parent of agents/)
PROJECT_ROOT = SCRIPT_DIR.parent


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
    """Load conference data from YAML file.
    
    Args:
        conference_name: The name of the conference (e.g., 'neurips', 'aaai')
        
    Returns:
        The YAML content as a string, or an empty string if file not found.
    """
    yaml_path = PROJECT_ROOT / "src" / "data" / "conferences" / f"{conference_name}.yml"
    
    if not yaml_path.exists():
        print(f"Warning: Conference file not found at {yaml_path}")
        return ""
    
    async with aiofiles.open(yaml_path, "r", encoding="utf-8") as f:
        return await f.read()


def format_user_prompt(template: str, conference_name: str, conference_data: str) -> str:
    """Format the user prompt template with conference name and data.
    
    Args:
        template: The user prompt template with placeholders.
        conference_name: The name of the conference.
        conference_data: The YAML content of the conference data.
        
    Returns:
        The formatted user prompt.
    """
    return template.format(
        conference_name=conference_name,
        conference_data=conference_data if conference_data else "No existing data found.",
    )


async def find_conference_deadlines(conference_name: str) -> None:
    """Find the deadlines of a given conference using the Claude Agent SDK.

    Args:
        conference_name: The name of the conference to find the deadlines of.
    """
    print(f"Processing conference: {conference_name}")

    # Load conference data from YAML file
    conference_data = await load_conference_data(conference_name)
    
    # Read app README for system prompt
    app_readme = await read_app_readme()
    
    # Read and format system prompt
    system_prompt_template = await read_prompt("prompts/system_prompt.md")
    from datetime import datetime

    def format_date_verbose(dt: datetime) -> str:
        # e.g. "Monday, the 1st of April, 2025"
        day = dt.day
        suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        return f"{dt.strftime('%A')}, the {day}{suffix} of {dt.strftime('%B')}, {dt.year}"

    system_prompt = system_prompt_template.format(
        conference_name=conference_name,
        date=format_date_verbose(datetime.now()),
        app_readme=app_readme,
    )

    # User prompt is a simple instruction to find deadlines
    user_prompt_template = await read_prompt("prompts/user_prompt.md")
    user_prompt = format_user_prompt(
        user_prompt_template, conference_name, conference_data
    )

    # Configure the agent
    # See: https://platform.claude.com/docs/en/agent-sdk/subagents
    # Use absolute path for settings to work both locally and in Modal
    settings_path = PROJECT_ROOT / ".claude" / "settings.local.json"
    if not settings_path.exists():
        # Fallback to home directory (for Modal non-root user)
        settings_path = Path.home() / ".claude" / "settings.local.json"
    settings_path = str(settings_path)
    
    # Configure Exa MCP server for web search capabilities
    # See: https://docs.exa.ai/reference/exa-mcp
    exa_api_key = os.environ.get("EXA_API_KEY", "")
    # ?exaApiKey={exa_api_key}
    exa_mcp_url = f"https://mcp.exa.ai/mcp"
    
    mcp_servers: dict[str, McpHttpServerConfig] = {
        "exa": McpHttpServerConfig(
            type="http",
            url=exa_mcp_url,
        )
    }
    
    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        permission_mode="bypassPermissions",
        settings=settings_path,
        mcp_servers=mcp_servers,
    )

    # Run the agent query
    # See: https://platform.claude.com/docs/en/agent-sdk/python
    # Track subagent names by their parent_tool_use_id
    subagent_names: dict[str, str] = {}
    # Track tool names by their tool_use_id for better result logging
    tool_names: dict[str, str] = {}

    print(f"Starting agent query with settings: {settings_path}")
    print(f"Settings path exists: {Path(settings_path).exists()}")
    print(f"System prompt length: {len(system_prompt)}")
    print(f"Conference data loaded: {len(conference_data)} characters")
    print(f"Exa MCP server configured: {'Yes (API key set)' if exa_api_key else 'Yes (no API key)'}")

    message_count = 0
    try:
        async for message in query(
            prompt=user_prompt,
            options=options,
        ):
            message_count += 1
            if isinstance(message, AssistantMessage):
                # Determine which agent is making this call
                if message.parent_tool_use_id is None:
                    agent_prefix = "[main]"
                else:
                    subagent_name = subagent_names.get(
                        message.parent_tool_use_id, "subagent"
                    )
                    agent_prefix = f"[{subagent_name}]"

                for block in message.content:
                    if isinstance(block, TextBlock):
                        print(f"{agent_prefix} Claude: {block.text}")
                    elif isinstance(block, ToolUseBlock):
                        print(f"{agent_prefix} Tool: {block.name}({block.input})")
                        # Track tool names for result logging
                        tool_names[block.id] = block.name
                        # Track Task tool calls to map subagent names
                        if block.name == "Task" and isinstance(block.input, dict):
                            subagent_type = block.input.get("subagent_type", "subagent")
                            subagent_names[block.id] = subagent_type
            elif isinstance(message, UserMessage):
                # UserMessage can contain tool results
                if isinstance(message.content, list):
                    for block in message.content:
                        if isinstance(block, ToolResultBlock):
                            # Get the tool name from our tracking dict
                            tool_name = tool_names.get(block.tool_use_id, "unknown")
                            # Truncate long results for readability
                            content_str = str(block.content) if block.content else "(empty)"
                            if len(content_str) > 500:
                                content_str = content_str[:500] + "... (truncated)"
                            error_indicator = " [ERROR]" if block.is_error else ""
                            print(f"[result]{error_indicator} {tool_name}: {content_str}")
            elif (
                isinstance(message, ResultMessage)
                and message.total_cost_usd
                and message.total_cost_usd > 0
            ):
                print(f"\nCost: ${message.total_cost_usd:.4f}")
    except Exception as e:
        print(f"Error during agent query: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()

    print(f"\nAgent query completed. Total messages received: {message_count}")


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
    args = parser.parse_args()
    conference_name = args.conference_name

    asyncio.run(find_conference_deadlines(conference_name))
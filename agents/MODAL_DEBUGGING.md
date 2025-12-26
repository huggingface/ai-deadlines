# Modal Agent Debugging - SOLVED

## Problem Summary

When running the conference deadline agent on Modal, the `claude-agent-sdk` query only received 1 message (the `SystemMessage` init) and then completed immediately, without any actual Claude response or tool calls.

## Root Causes Found

### 1. ✅ Python Version (Minor Factor)
Changed from Python 3.12 to 3.11 to match the working `github_issues_reply` example.

### 2. ✅ sys.path Order Bug (MAJOR)
The `sys.path.insert()` calls were in the wrong order, causing Python to import the agent code from the **cloned repo** (which had old code) instead of the **mounted local code**.

**Bug:**
```python
sys.path.insert(0, "/home/agent/app")  # Position 0
sys.path.insert(0, REPO_DIR)            # This pushes /home/agent/app to position 1!
```

**Fix:**
```python
sys.path.insert(0, REPO_DIR)            # Position 0
sys.path.insert(0, "/home/agent/app")   # This is now at position 0!
```

### 3. ✅ Missing USE_CWD_AS_PROJECT_ROOT
The `agent.py` uses `PROJECT_ROOT` to find conference YAML files. Without the environment variable, it pointed to `/home/agent/app` instead of the cloned repo where the files actually are.

**Fix in modal_agent.py:**
```python
os.environ["USE_CWD_AS_PROJECT_ROOT"] = "1"
```

**Fix in agent.py:**
```python
PROJECT_ROOT = Path(os.getcwd()) if os.environ.get("USE_CWD_AS_PROJECT_ROOT") else SCRIPT_DIR.parent
```

### 4. ✅ stderr Callback REQUIRED (CRITICAL!)
**This was the key fix discovered on 2025-12-26:** The `stderr` callback MUST be provided for the SDK to work on Modal. Without it, the async generator only yields the SystemMessage and then exits immediately.

**Required configuration:**
```python
def on_stderr(data: str):
    print(f"[stderr] {data.strip()}")

options = ClaudeAgentOptions(
    system_prompt=system_prompt,
    permission_mode="bypassPermissions",
    settings=settings_path,
    stderr=on_stderr,  # REQUIRED for Modal!
)
```

The stderr callback likely helps keep the async event loop properly active in Modal's serverless environment.

### 5. ✅ MCP Servers Disabled
Exa MCP server causes issues on Modal. Set `DISABLE_EXA_MCP=1` to use the built-in WebSearch tool instead.

## Working Configuration

### modal_agent.py Key Points:
- Python 3.11 (matching working example)
- Correct sys.path order (mounted code takes priority)
- Set `USE_CWD_AS_PROJECT_ROOT=1` before importing agent
- Set `DISABLE_EXA_MCP=1` to disable MCP servers

### agent.py Key Points:
- `ClaudeAgentOptions` with system_prompt, permission_mode, settings, AND stderr callback
- Dynamic `PROJECT_ROOT` based on environment variable
- MCP servers only enabled when not on Modal

## Test Command

```bash
uv run modal run agents/modal_agent.py --conference-name neurips
```

Expected: Multiple messages (28+), web searches, file edits, git operations.

## Modal Secrets Required

```bash
uv run modal secret create anthropic ANTHROPIC_API_KEY=<your-key>
uv run modal secret create github-token GH_TOKEN=<token-with-repo-scope>
```

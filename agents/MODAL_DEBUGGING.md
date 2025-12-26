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

### 4. ✅ Overly Complex ClaudeAgentOptions
Removed unnecessary options that might cause issues:
- Removed `mcp_servers` (Exa MCP server)
- Removed `cwd` parameter
- Removed `stderr` callback
- Removed `max_turns`
- Removed `extra_args={"debug-to-stderr": None}`

**Simplified to:**
```python
options = ClaudeAgentOptions(
    system_prompt=system_prompt,
    permission_mode="bypassPermissions",
    settings=settings_path,
)
```

## Working Configuration

### modal_agent.py Key Points:
- Python 3.11 (matching working example)
- Correct sys.path order (mounted code takes priority)
- Set `USE_CWD_AS_PROJECT_ROOT=1` before importing agent
- Minimal secrets: just `anthropic` and `github-token`

### agent.py Key Points:
- Simple `ClaudeAgentOptions` with just system_prompt, permission_mode, settings
- Dynamic `PROJECT_ROOT` based on environment variable

## Test Command

```bash
uv run modal run agents/modal_agent.py --conference-name neurips
```

Expected: Multiple messages (50+), web searches, file edits, git operations.

## Modal Secrets Required

```bash
uv run modal secret create anthropic ANTHROPIC_API_KEY=<your-key>
uv run modal secret create github-token GH_TOKEN=<token-with-repo-scope>
```

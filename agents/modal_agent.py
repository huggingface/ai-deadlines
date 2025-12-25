"""Modal wrapper for conference deadlines agent.

This module wraps the existing agent functionality to run on Modal's
serverless infrastructure, processing all conferences sequentially.
The agent itself handles git add/commit/push via its Bash tool.

Usage:

```bash
# Run all conferences once
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

# Repository configuration
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
    
    conferences = [
        f.stem for f in conferences_path.glob("*.yml")
    ]
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


def setup_git_and_clone():
    """Configure git and clone the repository."""
    import os
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

    github_pat = os.environ.get("GH_TOKEN", "")
    if not github_pat:
        raise ValueError("GH_TOKEN environment variable is required")

    # Store credentials
    credentials_file = os.path.expanduser("~/.git-credentials")
    with open(credentials_file, "w") as f:
        f.write(f"https://x-access-token:{github_pat}@github.com\n")
    os.chmod(credentials_file, 0o600)

    # Clone the repository if it doesn't exist
    if not os.path.exists(REPO_DIR):
        subprocess.run(
            ["git", "clone", REPO_URL, REPO_DIR],
            check=True,
        )
    else:
        # Pull latest changes
        subprocess.run(
            ["git", "pull", "--rebase"],
            cwd=REPO_DIR,
            check=True,
        )


@app.function(timeout=600)
def process_single_conference(conference_name: str) -> dict:
    """Process a single conference using the Claude Agent SDK.
    
    The agent will update the conference data and handle git add/commit/push.

    Args:
        conference_name: The name of the conference to process.

    Returns:
        A dictionary containing the processing result.
    """
    import asyncio
    import os
    import pwd
    import sys

    # Switch to non-root user (required for claude-agent-sdk bypassPermissions)
    agent_user = pwd.getpwnam("agent")
    os.setgid(agent_user.pw_gid)
    os.setuid(agent_user.pw_uid)
    os.environ["HOME"] = agent_user.pw_dir

    # Setup git and clone/pull repo
    setup_git_and_clone()

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
            return {
                "conference": conference_name,
                "status": "completed",
            }
        except Exception as e:
            return {
                "conference": conference_name,
                "status": "error",
                "error": str(e),
            }

    return asyncio.run(_process())


@app.function(timeout=43200)  # 12 hours max for all conferences
def process_all_conferences() -> list[dict]:
    """Process all conferences sequentially.
    
    Each conference is processed one at a time. The agent handles
    git add/commit/push for each conference via its Bash tool.

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
    setup_git_and_clone()
    
    # Get conferences from yml files in the cloned repo
    conferences = get_conferences()
    results = []

    for i, conference in enumerate(conferences):
        print(f"\n{'=' * 60}")
        print(f"Processing conference {i + 1}/{len(conferences)}: {conference}")
        print(f"{'=' * 60}")

        try:
            # Process the conference (agent handles git operations)
            result = process_single_conference.remote(conference)
            results.append(result)
            print(f"Result: {result}")

        except Exception as e:
            print(f"Error processing {conference}: {e}")
            results.append({
                "conference": conference,
                "status": "error",
                "error": str(e),
            })

    print(f"\n{'=' * 60}")
    print(f"Completed processing {len(conferences)} conferences")
    print(f"{'=' * 60}")

    return results


@app.function(
    timeout=43200,
    schedule=modal.Cron("0 0 * * 0"),  # Run weekly on Sunday at midnight UTC
)
def scheduled_run():
    """Scheduled weekly run of all conferences."""
    print("Starting scheduled weekly conference update...")
    results = process_all_conferences.remote()
    
    # Summary
    completed = sum(1 for r in results if r.get("status") == "completed")
    errors = sum(1 for r in results if r.get("status") == "error")
    
    print(f"\nWeekly run completed:")
    print(f"  - Completed: {completed}")
    print(f"  - Errors: {errors}")
    
    return results


@app.local_entrypoint()
def main(
    conference_name: str = None,
    all_conferences: bool = False,
):
    """CLI entrypoint for the Modal agent.

    Args:
        conference_name: Single conference name to process (for testing).
        all_conferences: If True, process all conferences sequentially.
    """
    if conference_name and all_conferences:
        print("Error: Specify either --conference-name or --all-conferences, not both.")
        return

    if not conference_name and not all_conferences:
        # Default to processing all conferences
        all_conferences = True

    if conference_name:
        # Process single conference (for testing)
        print(f"Processing single conference: {conference_name}")
        result = process_single_conference.remote(conference_name)
        print(f"\nResult: {result}")

    elif all_conferences:
        # Process all conferences sequentially
        # Note: We read from local repo here for the count, Modal will read from cloned repo
        local_conferences_dir = Path(__file__).parent.parent / CONFERENCES_DIR
        if local_conferences_dir.exists():
            num_conferences = len(list(local_conferences_dir.glob("*.yml")))
        else:
            num_conferences = "all"
        print(f"Processing {num_conferences} conferences sequentially...")
        results = process_all_conferences.remote()

        print(f"\n{'=' * 60}")
        print("Summary:")
        print(f"{'=' * 60}")
        
        completed = [r for r in results if r.get("status") == "completed"]
        errors = [r for r in results if r.get("status") == "error"]
        
        print(f"Completed: {len(completed)}")
        print(f"Errors: {len(errors)}")
        
        if errors:
            print("\nErrors:")
            for r in errors:
                print(f"  - {r['conference']}: {r.get('error', 'Unknown error')}")

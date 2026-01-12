# Issue: Inaccurate PR Reporting in Modal Agent

## Problem

When running `modal_agent.py` to process all conferences, the final summary reports misleading statistics:

```
PRs created: 0
PRs updated: 1
No changes: 62
Errors: 0
```

However, **30 PRs were actually created on GitHub**. The "No changes: 62" count is incorrect.

## Root Cause

There are **two separate PR creation paths** that conflict:

### Path 1: Inner Agent (`agent.py`)
The Claude agent running inside Modal:
1. Creates its own branch (e.g., `feature/update_aaai`)
2. Makes changes and commits them
3. Pushes the branch to GitHub
4. Creates a PR using `gh pr create`

### Path 2: Outer Wrapper (`modal_agent.py`)
The `push_and_create_pr()` function:
1. Checks the branch created by `setup_git_and_clone()` (e.g., `update/aaai`)
2. Looks for uncommitted changes with `git status --porcelain`
3. If no changes found, reports "No changes for X, skipping PR creation"

### The Mismatch
The inner agent works on `feature/update_X` branches, while the outer wrapper checks `update/X` branches. By the time `push_and_create_pr()` runs, the agent has already:
- Created a different branch
- Committed all changes
- Pushed and created a PR

So `push_and_create_pr()` sees no uncommitted changes on its branch and incorrectly reports "no changes".

## Impact

- **User confusion**: Summary suggests most conferences had no updates, but many PRs exist
- **Duplicate branch creation**: Two branches created per conference (`update/X` and `feature/update_X`)
- **Unreliable metrics**: Cannot trust the summary to know how many PRs were actually created

## Proposed Solutions

### Option 1: Track PRs Created by Agent
Parse the agent's output/messages to extract PR URLs it created, then report those in the summary.

**Pros**: Minimal changes to agent behavior
**Cons**: Requires parsing agent output, fragile

### Option 2: Prevent Agent from Creating Own Branches
Modify `agent.py` or the system prompt to work on the branch created by `setup_git_and_clone()` instead of creating `feature/update_X` branches.

**Pros**: Single source of truth for branches
**Cons**: Requires changes to agent behavior/prompts

### Option 3: Remove Duplicate PR Logic
Remove `push_and_create_pr()` entirely and let the agent handle all git operations. The modal wrapper only provides infrastructure.

**Pros**: Cleaner separation of concerns
**Cons**: Less control over PR format/content from wrapper

### Option 4: Have Agent Return PR Info
Modify `agent.py` to return structured data about PRs created, which `modal_agent.py` can use for accurate reporting.

**Pros**: Clean interface, accurate reporting
**Cons**: Requires agent code changes

## Recommendation

**Option 4** is the cleanest solution. The agent should return structured information about what it did (PR URL, changes made, etc.), and the modal wrapper should aggregate and report this information.

## Temporary Workaround

Until fixed, the accurate PR count can be found by:
1. Checking GitHub directly for new PRs
2. Looking at the detailed agent logs for `gh pr create` outputs
3. Ignoring the summary statistics

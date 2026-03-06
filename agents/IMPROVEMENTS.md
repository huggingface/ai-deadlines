# Improvements

Observations and proposed improvements based on dry runs of the 3-stage pipeline on NeurIPS, COLM, and ACL conferences.

## 1. Backfilling Past Conferences

**Problem**: In the COLM run, Agent 2 proposed adding rebuttal, notification, and camera-ready deadlines to COLM 2025, a conference that already took place (October 2025). The existing prompt says "Only add deadlines which are upcoming" but this wasn't strong enough — the agent found real data and felt compelled to include it.

**Suggestion**: Strengthen the prompt with an explicit rule: "Do NOT backfill or add new deadlines to conference years that have already taken place. Past conferences should be left as-is, even if you find additional deadline information for them. Focus exclusively on upcoming/future conference years." This has been applied to `retrieval_system_prompt.md`.

## 2. Git Remote Confusion in PR Stage

**Problem**: The PR agent pushed to `origin` (huggingface/ai-deadlines) instead of the `nielsrogge` fork on the first attempt, causing a "No commits between" error when creating the PR. It recovered by checking `git remote -v` and pushing to the correct remote, but this cost extra messages and time.

**Suggestion**: The `pr_system_prompt.md` already has explicit instructions, but the agent didn't follow them on the first try. Options:
- Pre-populate the PR agent's prompt with the output of `git remote -v` so it doesn't have to discover the remote layout.
- Alternatively, have the orchestrator in `agent.py` run `git remote -v` before invoking the PR agent and inject the output into the prompt.

## 3. Parallel Retrieval Agents

**Problem**: Retrieval agents run sequentially in a `for` loop. The NeurIPS run took the sum of all 3 agents' wall-clock times.

**Suggestion**: Use `asyncio.gather()` to run all N retrieval agents in parallel. The agents are independent — they don't share state. This would reduce wall-clock time to roughly the duration of the slowest agent. Change `run_retrieval_agents` from:
```python
for i in range(1, n + 1):
    result = await run_retrieval_agent(conference_name, agent_index=i)
    results.append(result)
```
to:
```python
tasks = [run_retrieval_agent(conference_name, agent_index=i) for i in range(1, n + 1)]
results = await asyncio.gather(*tasks)
```

## 4. Cost Tracking

**Problem**: Total cost is only visible by manually summing per-agent costs from logs. The NeurIPS run cost ~$0.72, the COLM run ~$0.44.

**Suggestion**: Track cumulative cost in the orchestrator and print a total at the end of the pipeline run.

## 5. Aggregation Agent Reuses Retrieval System Prompt

**Problem**: The aggregation agent uses the same system prompt as the retrieval agents (`retrieval_system_prompt.md`). This prompt includes instructions about web searching, Exa MCP, URL heuristics, etc. — none of which are relevant to the aggregation task, which is purely analytical.

**Suggestion**: Create a dedicated `aggregation_system_prompt.md` that focuses on the majority-vote task: comparing results, resolving disagreements, evaluating source quality, and synthesizing a consensus. This would reduce prompt size and avoid confusing the agent with irrelevant tool instructions.

## 6. Dry Run Still Modifies Files (NeurIPS)

**Problem**: In the NeurIPS run, the PR agent actually wrote to the YAML file, created a branch, and opened a real PR (#151) — even though the intent was a dry run. The `--dry-run` flag only gates the PR stage invocation in the orchestrator, but the NeurIPS run was apparently not using `--dry-run`.

**Suggestion**: Consider adding a `--dry-run` mode that also prevents the PR agent from being invoked at all, and clearly logs the proposed changes without writing anything to disk. The current implementation already does this correctly; just ensure it's always used during testing.

## 7. Branch Cleanup

**Problem**: After a PR is created, the local branch (`feature/update_neurips`) remains checked out. If the pipeline runs again for the same conference, it may conflict.

**Suggestion**: After PR creation, have the orchestrator (or the PR agent prompt) switch back to the `main` branch and optionally delete the feature branch locally. This prevents stale branches from accumulating.

## 8. Majority Vote Fails on Factual Disagreements (ACL run)

**Problem**: For ACL 2025's venue, all 3 retrieval agents returned different answers:
- Agent 1: "VIECON – Vienna Congress & Convention Center, Messeplatz 1, Vienna"
- Agent 2: "Austria Center Vienna, Bruno-Kreisky-Platz 1, 1220 Wien, Austria" (correct)
- Agent 3: "Messe Wien Exhibition Congress Center, Vienna, Austria"

A naive majority vote would have been useless here since there was no majority at all. The aggregation agent saved correctness only because it happened to have web tools (via the reused retrieval system prompt) and independently verified by fetching `https://2025.aclweb.org/venue/`.

**Suggestion**: This nuances item #5 — don't remove web tools from the aggregation agent entirely. Instead, create a dedicated `aggregation_system_prompt.md` that focuses on the majority-vote task but explicitly instructs: "When retrieval agents disagree on a factual claim (e.g. venue name, dates), verify the claim against the official conference website before accepting any agent's answer." Also consider instructing retrieval agents to always visit the official `/venue/` page when available, to reduce venue disagreements.

## 9. PR Agent Writes Before Reading

**Problem**: In the ACL run, the PR agent attempted to write the updated YAML to `acl.yml` without reading the file first, triggering the error: `File has not been read yet. Read it first before writing to it.` This wasted one message turn and added cost.

**Suggestion**: Add an explicit instruction to `pr_system_prompt.md`: "Always read the target YAML file before writing to it." Alternatively, have the orchestrator pass the current file contents into the PR agent's user prompt so the agent has context without needing to read.

## 10. PR System Prompt Remote Names Don't Match Reality

**Problem**: The `pr_system_prompt.md` states: "The repository is cloned from `nielsrogge/ai-deadlines` (origin)..." but the actual git configuration has `origin` pointing to `huggingface/ai-deadlines` and a separate `nielsrogge` remote for the fork. This mismatch is the root cause of issue #2 — the agent follows the prompt's instruction to push to `origin` but ends up pushing to upstream.

**Suggestion**: Either:
- Fix the prompt to match the actual remote layout: "Push to the `nielsrogge` remote (not `origin`)."
- Or have the orchestrator inject the output of `git remote -v` into the PR agent's prompt so it can see the real layout.
- Or standardize the remote names across environments (rename remotes so `origin` always points to the fork).

## 11. Branch Name Collisions Across Runs

**Problem**: The fixed branch name `feature/update_acl` already existed on both remotes from a previous pipeline run. The PR agent had to delete the remote branch on `origin` and force-push to the `nielsrogge` remote, which is fragile and could discard meaningful work if a previous PR is still open.

**Suggestion**: Use unique branch names that include a timestamp or short hash, e.g. `feature/update_acl_20260306` or `feature/update_acl_$(date +%s)`. This avoids collisions entirely and makes it safe to run the pipeline multiple times for the same conference. The orchestrator could generate the branch name and pass it to the PR agent.

---
name: update-conferences
description: Prioritize and run Modal conference-deadline agents on high-ROI conferences only. Use when updating conference YAML via agents/modal_agent.py, choosing which conferences to refresh, running deadline agents, or avoiding expensive all-conference Modal runs.
disable-model-invocation: true
---

# Update Conferences

Cost-aware workflow for refreshing `src/data/conferences/*.yml` via `agents/modal_agent.py` on Modal. Prefer a short priority list over `--all-conferences`.

## When to use

- User asks to update conference deadlines / run the Modal agent
- User wants conferences “likely to have new data”
- Full-repo runs look too expensive (~$2–4 per conference)

## Selection rules (high ROI only)

Rank by **actionable now**, not “missing next year.”

**Run when:**
- Active cycle: a deadline or milestone falls in the next ~8 weeks
- A milestone just passed and remaining dates may have changed (`venue: TBA`, wrong camera-ready, missing rebuttal/notification)
- YAML is incomplete for a conference **already in flight** (e.g. empty `deadlines: []` while CFP is open)

**Skip when:**
- Far-future CFPs (e.g. CVPR/ICLR 2027 months before CFP typically opens)
- Conference was just successfully updated in a recent run
- Archival gaps only (missing old years) with no imminent news
- Complete past/current year data with no near-term milestones

Do **not** treat “no `year: N+1` block yet” as sufficient reason to run.

### How to build the list

1. Scan `src/data/conferences/*.yml` for signals: `deadlines: []`, `venue: TBA`, `to be announced`, near-term `date:` values, missing fields on an active year.
2. Cross-check typical CFP timing only as a soft prior — YAML + calendar proximity win.
3. Present a short ranked table (conference stem, why now). Aim for ~10–15, not all ~67.
4. Confirm with the user before launching runs.

## Running the agent

Default runner: **Modal** (`agents/modal_agent.py`). Pushes to `huggingface/ai-deadlines` `main`.

```bash
# Prefer one conference at a time
uv run modal run --detach agents/modal_agent.py --conference-name <stem>

# Small smoke test only
uv run modal run --detach agents/modal_agent.py --limit 1

# Avoid unless explicitly requested (expensive)
uv run modal run --detach agents/modal_agent.py --all-conferences
```

There is no `--conferences a,b,c` flag — run sequentially with `--conference-name`, waiting for each to finish (or getting user OK) before the next.

### Preflight

1. Check for already-running apps: `uv run modal app list`
2. Stop stale/stuck runs before starting a new one if the user wants a clean test
3. Required Modal secrets: `anthropic`, `github-token` (`GH_TOKEN` with `repo`), `exa`
4. `anthropic` is HF Inference Providers config (not a raw Anthropic key). Do not replace it with a bare `huggingface` secret that only has `HF_TOKEN`.

### Monitor and report

After each run, report briefly:
- Modal app URL / app id
- Status: `pushed` | `no_changes` | `error` | `timeout`
- `commit_sha` when status is `pushed`
- Cost and approx duration if available
- Concrete YAML changes (or that push was skipped)
- Whether any retrieval agent hit `error_max_turns` / budget limits / wall-clock timeout

Watch logs for: `Result:`, `pushed`, `no_changes`, `timeout`, `commit_sha`, `Total pipeline`, `Limit reached`, `Wall-clock timeout`, `Authentication failed`.

## Data conventions

- Deadline timezone: always **`AoE`**. Never write `UTC-12` or `UTC+12`.
- Conference stem = YAML filename without `.yml` (e.g. `emnlp`, `wacv`, `3dv`)
- Leave past conference years unchanged unless the user asks for archival fixes
- YAML is validated in Python before push (parse, required fields, `AoE`, past years byte-for-byte). Failures return `error` and do not push.

## Timeouts

- Per-conference Modal function timeout: **3600s**, overridable at deploy with `MODAL_CONFERENCE_TIMEOUT`
- Per retrieval/aggregation agent wall-clock: **300s** (`AGENT_WALL_CLOCK_SECONDS`)
- Retrieval agents fail closed: last-turn hook asks for structured output; empty `error_max_turns` gets one no-tools follow-up. Do not treat a hang until the function cap as `no_changes`.

## Cost intuition

- Typical single-conference run: ~$2–4 and ~5–15 minutes
- Prefer confirming the next conference with the user after each successful run when iterating a priority list
- `no_changes` is a success (agents verified; push skipped)

## Troubleshooting

| Symptom | Action |
|---------|--------|
| 401 / wrong Claude model id | Refresh Modal `anthropic` secret (HF router + model env vars); do not switch the app to the plain `huggingface` secret |
| `GH_TOKEN` / push failed | User must refresh Modal `github-token`; do not invent tokens from guesses |
| Hang / no log progress | Check Modal dashboard; local stream can stall while cloud work continues |
| Agents burn all turns | Note it; last-turn hook should force structured `requires_update: false`. Pipeline can still succeed if ≥1 retrieval agent returns structured output |
| Status `timeout` | Per-agent 5 min cap or Modal 3600s function timeout; not the same as `no_changes` |

## Local alternative

Only if the user asks to run locally instead of Modal:

```bash
uv run --env-file keys.env -m agents.agent --conference_name <stem>
```

For HF Jobs debugging, see `agents/README.md` / `agents/hf_jobs_agent.py` — not the default path.

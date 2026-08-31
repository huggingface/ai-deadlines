# Plan: Improve Conference Deadline Agents

Plan for hardening `agents/` after the Aug 2026 priority-list runs (Modal `modal_agent.py` → `agent.py`). Goal: fewer timeouts, accurate status reporting, and earlier exit when there is nothing to update — **before** blindly re-running AAAI / ECIR.

Prompt/status/short-circuit changes live in `agent.py` and apply to **both** Modal and `hf_jobs_agent.py`. Only the function timeout is Modal-specific.

## Context from recent runs

| Conference | Outcome | Notes |
|------------|---------|-------|
| `chi`, `iclr`, `icra`, `emnlp_industry_track`, `emnlp_system_demonstrations_track`, `www` | Pushed | Real YAML updates on `main` |
| `wsdm`, `kdd`, `corl`, `naacl`, `icomp` | `no_changes` | Legitimate or “site unreadable” |
| `aaai`, `ecir` | **Failed** | Modal `FunctionTimeoutError` at **1200s** while still on retrieval agent 1 |

Also observed: successful pushes (CHI, WWW, demos) where the push agent hit `error_max_turns` afterward and Modal reported **`status: no_changes`** even though git push succeeded. `process_single_conference` also drops `commit_sha` even when the agent reports it.

---

## Problems to fix

### P1 — Single-conference Modal timeout (1200s)

**Where:** `agents/modal_agent.py` → `@app.function(timeout=1200)` on `process_single_conference`. Retrieval is **sequential** (`run_retrieval_agents` loops 1→2→3). Silent-exit retries (`MAX_RETRIES = 3` in `agent.py`) can multiply wall time per agent.

**What happens:** Retrieval agent 1 burns the whole budget on fruitless WebSearch/WebFetch (JS-heavy sites: AAAI, ECIR Brizy, CoRL Google Sites). Pipeline never reaches agents 2–3 / aggregation / push. Modal cancels the task. Raising the function timeout alone only lets agent 1 burn longer.

**Fix (all of these; timeout bump is a one-line safety net and should land first):**
1. Raise `process_single_conference` timeout to **3600s** (env-configurable). This is a backstop, not the primary control.
2. Add a **per-agent wall-clock cap** (e.g. 4–6 min). A JS-heavy site must not consume the whole function.
3. Make retrieval **exit early** when evidence is empty (see P2).
4. Optionally **skip remaining retrieval agents** only if an earlier agent already returned *structured* `requires_update: false` with reasoning like “CFP not published.” Do **not** skip on empty / `error_max_turns` — WSDM needed agent 3 after 1–2 failed.

Tune `RETRIEVAL_MAX_TURNS` / budgets only after fail-closed exists (see Phase B).

### P2 — Retrieval agents do not fail closed

**Where:** `STAGE_LIMIT_DEFAULTS["retrieval"] = (12, $1.50)` in `agent.py`; interpolated into `retrieval_system_prompt.md` as `{max_turns}`. Overridable via `RETRIEVAL_MAX_TURNS` / `AGENT_MAX_TURNS`.

**They already know the budget.** The system prompt already has:

> You have at most **{max_turns} tool-use turns** … Plan efficiently … Once you have enough verified information … stop searching and return your result immediately.

`run_retrieval_agent` fills `{max_turns}` with **12**. The user prompt has **no** turn-budget text — only “search the web,” which pulls the other way.

**What actually happens:** Agents treat 12 as “keep searching until it runs out,” then the SDK hard-stops with `error_max_turns` and **no structured output**. WSDM agents 1–2 and AAAI died this way. Spending turn 12 on another WebFetch means they never return `requires_update: false`. Typical empty-CFP patterns:
- WebFetch returns CSS/JS only (no dates)
- WebSearch returns generic / no-results fluff
- Official CFP is genuinely not published yet (AAAI “not yet announced”)

A tighter “you have N turns” line will not fix this — they already see N=12. Prompt work is **when to stop early and still answer**. Prompt-only also will not replace P1’s per-agent wall-clock: AAAI burned ~20 min on agent 1 because each JS-heavy fetch is slow; 12 slow fetches still fit inside 1200s and can eat the whole Modal function before agents 2–3 start. Do **not** lower `max_turns` until the stop rule exists.

**Fix (prefer the last-turn tool-result nudge over more prompt text):**
1. **On the last tool result, tell the model to answer now** (primary, code). `query()` runs tools inside the SDK, so do this with a `PostToolUse` hook (`ClaudeAgentOptions.hooks`) already supported by `claude-agent-sdk`:
   - Count tool uses (WebSearch / WebFetch / Exa). On turn **`max_turns - 1`** (the last result that still gets a model step before the SDK hard-stop), append `additionalContext` (or equivalent) to that tool result:

     `Your tool-call budget is exhausted. Do not search again. Return structured output now. If you found no verified upcoming deadlines, set requires_update: false.`

   - Optional: `PreToolUse` on the next call **deny** with the same reason, so they cannot spend turn 12 on another fetch.
   - Fallback if the hook misses and you still get `error_max_turns` with empty structured output: one **no-tools** follow-up query (“budget exhausted, answer now from what you already saw”). Same pattern helps aggregation if it burns its 8 turns.
2. Rewrite the **Turn budget** section (and mirror a short version in the **user** prompt) so it is a fail-closed rule, not a hint:
   - After **2–3** official-page fetches that yield no deadline content → return `requires_update: false` with reasoning “CFP not published / page unreadable.”
   - **Reserve the last turn** for structured output. Do not spend turn 12 on another search.
   - Do **not** burn remaining turns on CAPTCHA pages or generic search-engine flailing.
   - **One** secondary-source fetch (WikiCFP or similar) as a last resort is allowed — official AAAI/ECIR/CoRL pages were unreadable CSS/JS. Ban thrashing, not the secondary source.
3. Optional extra code signal: N consecutive empty/error fetches → same “answer now” injection even before the last turn (empty CSS/JS pages should not consume all 12).
4. While in the retrieval prompt, fix the timezone contradiction: it currently says use AoE **(UTC+12)** and also “not UTC+12.” AoE is **UTC−12**. Align with `CLAUDE.md`: write `AoE`, never `UTC-12` or `UTC+12`.
5. Tighten “feel free to refactor legacy `deadline:` / `abstract_deadline`”: refactor **only the upcoming year block**. That instruction currently fights “leave past years byte-for-byte.”
6. Lower retrieval `max_turns` (e.g. 8–10) *after* the last-turn nudge exists and is measured — not before, or empty results get worse.

### P3 — Push succeeds but status reports `no_changes`

**Where:**
- `run_push_agent` / `_run_agent` — LLM with 6 turns whose job is write → `git add` → commit → push → return SHA. Structured output is missing if the agent hits `error_max_turns` after a successful `git push`.
- `pr_user_prompt.md` **forces a Read** “to satisfy the tool requirement,” which burns one of six turns before any write.
- `process_single_conference` — `status = "pushed" if agent_result.get("pushed") else "no_changes"`; `commit_sha` is not passed through.

**What happens:** Push agent writes YAML, commits, pushes, then uses extra turns (mandatory read, verify SHA, summarize) and dies on turn limit. `pushed` defaults to `False` → wrong Modal status.

**Fix (primary is code, not prompts):**
1. **Deterministic push in Python** (primary): write the YAML file and run `git add` / `commit` / `push` in `agent.py`. Do not use an LLM for git. Return `pushed` + `commit_sha` from the subprocess result.
2. If the agent path is kept at all: drop the mandatory Read; require structured output immediately after `git push`; add a git-log fallback if structured `pushed` is false.
3. Pass `commit_sha` through `process_single_conference`. Do not bump push `max_turns` as the main fix.

### P4 — Date / “upcoming vs past” mistakes

**Where:** Retrieval/aggregation prompts already document the rule; agents still mis-classify (e.g. KDD 2026 ended Aug 13 treated as upcoming on Aug 26).

**Fix:**
1. In Python, from each YAML year block, precompute labels and inject them into **both** retrieval and aggregation user prompts (same labels, or the two stages will disagree). Example:

   `today: 2026-08-26`  
   `2025: PAST` · `2026: PAST` · `2027: MISSING_NEXT_YEAR`

2. Classification rules:
   - Compare `end`, else `start`, else parse `date`.
   - Missing all three → `UNKNOWN` (treat as upcoming for search, do not invent dates).
   - No `year: N+1` block yet → `MISSING_NEXT_YEAR`, not a fake `UPCOMING` row.
3. Keep prompt text as reinforcement; do not rely on the model alone for calendar math.

### P5 — Weak web tooling on Modal (secondary)

**Where:** `DISABLE_EXA_MCP=1` in `modal_agent.py` (known MCP/SDK issue). Agents use built-in WebSearch/WebFetch only.

**What happens:** JS-rendered conference sites are opaque; Exa (when working) was historically better for some pages.

**Fix (later phase — do not block P1–P4, P6–P8):**
1. Prefetch official `link` HTML text into the retrieval prompt (this is the C item that actually feeds P2: agents then don’t have to discover the official URL).
2. Revisit enabling Exa MCP on Modal behind a flag once SDK stability is confirmed.

`--conferences a,b,c` is nice-to-have; sequential `--conference-name` is fine for now.

### P6 — Aggregation runs when there is nothing to vote on

**Where:** `_all_agree_no_update` requires ≥2 valid results with `requires_update: false`. Empty/`unknown` results force aggregation.

**What happens:** NAACL/ICOMP-style runs: all three agents empty → aggregation concludes `no_changes` anyway (extra cost ~$0.10–0.20). Same waste when 1× `false` + 2× empty.

**Fix:** Skip aggregation unless **at least one** agent proposed `requires_update: true`. That covers:
- zero valid structured results → `no_changes`, reasoning “retrieval produced no structured output”
- all `false` or empty → `no_changes` from retrieval reasoning

Do not pay for a majority vote when nobody proposed an update. Optional: one retry with a tighter prompt only on the all-empty case.

### P7 — Status enum is lossy

**Where:** `process_single_conference` maps everything that isn’t `pushed` to `no_changes`. Timeouts surface as exceptions. Operators (and `update-conferences`) cannot tell timeout vs empty CFP vs successful push with missing structured output.

**Fix:** Return a closed status set and pass details through:

| Status | Meaning |
|--------|---------|
| `pushed` | Commit is on `main`; include `commit_sha` |
| `no_changes` | Agents verified; push skipped |
| `error` | Exception / auth / git failure |
| `timeout` | Modal (or per-agent) deadline hit |

Watch logs / skill reports should use this set.

### P8 — No YAML validation before push to `main`

**Where:** Pipeline writes straight to `huggingface/ai-deadlines` `main`. A bad aggregation can land live.

**Fix:** After aggregation (and before git), Python-validate:
- YAML parses
- required fields present
- timezone is `AoE` (not `UTC-12` / `UTC+12`)
- past-year blocks are byte-for-byte unchanged vs the file that was read

On failure: do not push; return `error` with the validation message. Cheaper and more important than a batch CLI flag.

---

## Recommended phases

### Phase A — Safety net, correctness, reporting (do first)

1. Raise Modal timeout to 3600s, env-configurable (P1.1).
2. Deterministic Python push + pass `commit_sha`; widen status enum (P3, P7).
3. Retrieval fail-closed (P2): they already see `max_turns=12`. Primary: `PostToolUse` hook injects “tool-call budget exhausted, answer now” on the last tool result (optional `PreToolUse` deny + no-tools follow-up on `error_max_turns`). Also rewrite Turn budget / user prompt; fix AoE; no legacy refactor on past years. Do not lower 12 yet.
4. Precomputed year labels into retrieval **and** aggregation prompts (P4).
5. Skip aggregation unless some agent said `requires_update: true` (P6).
6. Validate YAML before push (P8).
7. Per-agent wall-clock cap (P1.2).

**Tests (local first):** unit-test year labels, git/status mapping, empty-retrieval short-circuit, YAML validation. Then `--dry-run` locally. Then **one** Modal empty-CFP (AAAI-like) and **one** conference with a live CFP — not “re-run a conference we already know pushes.”

**Success criteria:** Empty-CFP path finishes with `no_changes` (or `timeout`/`error` if still stuck), not an untyped `FunctionTimeoutError`. A real update reports `pushed` + SHA. Ideally empty-CFP wall time &lt; ~10 min under the new timeout.

### Phase B — Cost tuning & docs

1. Tune `RETRIEVAL_MAX_TURNS` / budgets after observing Phase A.
2. Optional: skip remaining retrieval agents after a *confident* structured no-update (P1.4).
3. Update `agents/README.md` + `.agents/skills/update-conferences/SKILL.md` (timeout, fail-closed, status enum, `commit_sha`).

**Success criteria:** AAAI/ECIR-style “nothing on the site” finishes with `no_changes` (or clear `timeout`/`error`), not a hang until the function cap.

### Phase C — Tooling (optional; after A+B are measured)

1. Prefetch YAML `link` text into retrieval context (feeds P2).
2. Re-enable Exa MCP behind a flag if the SDK is stable.
3. `--conferences a,b,c` only if sequential runs stay painful.

### Phase D — Selective re-runs (only after A+B)

1. Manually check whether AAAI-27 / ECIR 2027 deadlines are live.
2. Re-run **only** if published; otherwise leave on a watch list.
3. Optionally re-check CoRL if notification/camera-ready appear on a non–Google-Sites page.

Do **not** re-run the full priority list.

---

## Out of scope (for this plan)

- Changing the weekly `--all-conferences` scheduled job strategy (still expensive; prefer priority selection via `update-conferences` skill).
- Replacing Claude Agents SDK / Modal entirely.
- Replacing the 3-agent majority vote with a different architecture.
- Archival cleanup of past years.

---

## Implementation checklist

- [x] P1.1: Configurable/higher Modal timeout for `process_single_conference` (3600s)
- [x] P1.2: Per-agent wall-clock cap
- [x] P3: Deterministic Python write + git push; return `pushed` + `commit_sha`
- [x] P7: Status enum `pushed` | `no_changes` | `error` | `timeout`; pass `commit_sha` through Modal
- [x] P2: Last-turn `PostToolUse` “budget exhausted, answer now” (+ optional deny / no-tools follow-up); rewrite Turn budget + user prompt; one WikiCFP last resort; fix AoE; no past-year legacy refactor. Keep `max_turns=12` until measured.
- [x] P4: Precomputed year classification in retrieval **and** aggregation prompts (`PAST` / `UPCOMING` / `MISSING_NEXT_YEAR` / `UNKNOWN`)
- [x] P6: Skip aggregation unless some agent proposed an update
- [x] P8: Validate YAML (parse, required fields, `AoE`, past years unchanged) before push
- [x] Unit tests for year labels, status/git mapping, empty short-circuit, YAML validation
- [x] Docs: README + `update-conferences` skill
- [x] Smoke: Modal `aaai` + `ecir` (29 Aug 2026) — both `pushed` with `commit_sha` (previously `FunctionTimeoutError` at 1200s)
- [x] Conditional AAAI / ECIR re-run (CFPs were live; both updated on `main`)

---

## References

- Modal single-conference timeout: `agents/modal_agent.py` (`MODAL_CONFERENCE_TIMEOUT`, default **3600s**)
- Per-agent wall clock: `AGENT_WALL_CLOCK_SECONDS` (default 300) in `agents/pipeline_utils.py`
- Sequential retrieval + silent-exit retries: `run_retrieval_agents`, `MAX_RETRIES = 3` in `agents/agent.py`
- Pipeline + status: `find_conference_deadlines`, `conference_result_payload` (`pushed` | `no_changes` | `error` | `timeout` + `commit_sha`)
- Helpers: `agents/pipeline_utils.py` (year labels, YAML validation, deterministic git, last-turn hook text)
- Stage limits: `STAGE_LIMIT_DEFAULTS` in `agents/agent.py` (retrieval **12** / $1.50, aggregation 8 / $1.00)
- Last-turn nudge: `ClaudeAgentOptions.hooks` → `PostToolUse` / `PreToolUse` in `_build_fail_closed_hooks`
- Push is Python (`write_and_push_conference`); `pr_*.md` prompts are unused
- Timezone: `CLAUDE.md` and retrieval prompt — write `AoE` only (never `UTC-12` / `UTC+12`)
- Exa disabled on Modal: `DISABLE_EXA_MCP=1` in `modal_agent.py`
- Shared by HF Jobs: `agents/hf_jobs_agent.py` imports the same pipeline
- Operator workflow: `.agents/skills/update-conferences/SKILL.md`
- Tests: `uv run pytest agents/tests`

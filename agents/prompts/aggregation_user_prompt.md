You are reviewing the findings of {num_agents} colleague agents who were each independently asked to research the same conference and determine whether its data needs updating.

## Conference name

Name: {conference_name}

## Current conference data

{conference_data}

## Colleague results

Below are the structured results from each colleague agent. Each result contains their independent assessment of whether an update is needed, their reasoning, proposed YAML content, and source URLs.

{retrieval_results}

## Instructions

Perform a majority vote and synthesis:

1. **Identify upcoming vs past years.** For each year block in the current data above, compare its `end` (or `start`/`date`) field to today's date. Years whose `end`/`start` is on or before today are **past** and must be preserved exactly as-is — reject any proposed change to them, even if multiple agents agree. Only proposals affecting **upcoming** years (or adding a brand-new upcoming year) are eligible for synthesis.

2. **Compare** the results from all colleagues, considering only their proposals for upcoming years. Note where they agree and disagree on:
   - Whether an update is needed (`requires_update`)
   - The specific data changes proposed for upcoming years (dates, deadlines, location, etc.)
   - The source URLs they found

3. **Majority vote**: Determine the consensus on whether an upcoming year needs updating. Proposals targeting past years do not count toward the vote and must be discarded.

4. **Synthesize**: If an update to an upcoming year is needed, produce a single synthesized YAML that represents the best consensus across all agents. Prefer data points that multiple agents agree on. If agents disagree on a specific field, prefer the value supported by more agents or more authoritative sources. **Past-year blocks must be byte-for-byte identical to the current data.**

5. **Return** your findings as structured output with:
   - `reasoning`: detailed explanation of how you compared the results, where agents agreed/disagreed, and how you arrived at the synthesis. Explicitly state which year(s) you treated as upcoming vs past based on today's date, and call out any agent proposals you rejected because they targeted a past year.
   - `requires_update`: the consensus decision (boolean). This must be `false` if the only proposed changes targeted past years.
   - `updated_yaml`: the synthesized YAML content (or current data if no update needed). Past-year blocks must be unchanged.
   - `source_urls`: combined list of source URLs from the results that support the synthesized output

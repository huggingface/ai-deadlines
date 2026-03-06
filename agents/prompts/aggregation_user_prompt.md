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

1. **Compare** the results from all colleagues. Note where they agree and disagree on:
   - Whether an update is needed (`requires_update`)
   - The specific data changes proposed (dates, deadlines, location, etc.)
   - The source URLs they found

2. **Majority vote**: Determine the consensus on whether an update is required. If a majority of agents agree an update is needed, the result should reflect that.

3. **Synthesize**: If an update is needed, produce a single synthesized YAML that represents the best consensus across all agents. Prefer data points that multiple agents agree on. If agents disagree on a specific field, prefer the value supported by more agents or more authoritative sources.

4. **Return** your findings as structured output with:
   - `reasoning`: detailed explanation of how you compared the results, where agents agreed/disagreed, and how you arrived at the synthesis
   - `requires_update`: the consensus decision (boolean)
   - `updated_yaml`: the synthesized YAML content (or current data if no update needed)
   - `source_urls`: combined list of source URLs from the results that support the synthesized output

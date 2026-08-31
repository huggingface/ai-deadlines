Please look at the data for the following conference, search the web for up-to-date information, and return your findings as structured output.

## Conference name

Name: {conference_name}

## Current conference data

Currently, the following data is in place: 

{conference_data}

## Today and year labels

{year_labels}

## Turn budget

You have at most **{max_turns} tool-use turns**. After 2–3 official-page fetches with no deadline content, return `requires_update: false` (CFP not published / page unreadable). Reserve the last turn for structured output. Do not thrash CAPTCHA pages or search-engine results. One WikiCFP (or similar) last-resort fetch is allowed.

## Instructions

1. **Use the precomputed year labels above.** PAST years must not be modified. Only UPCOMING years are eligible for updates. If a year is MISSING_NEXT_YEAR, search for that edition; do not invent dates if unpublished. UNKNOWN years may be searched as upcoming, but do not invent dates.
2. Search the web for the latest information about the **upcoming** year(s) of this conference (dates, deadlines, location, venue, etc.). Do not research past years.
3. Compare what you find with the current data for the upcoming year(s) only.
4. Return your findings as structured output with:
   - `requires_update`: whether the data needs updating (only `true` if there is new, verified information for an **upcoming** year)
   - `reasoning`: explanation of why an update is or isn't needed. Explicitly state which year(s) you considered upcoming vs past based on today's date.
   - `updated_yaml`: the full updated YAML content (include ALL years, not just new ones). Past years must be byte-for-byte identical to the current data. If no update is needed, return the current data as-is.
   - `source_urls`: list of URLs you used as sources

Please look at the data for the following conference, search the web for up-to-date information, and return your findings as structured output.

## Conference name

Name: {conference_name}

## Current conference data

Currently, the following data is in place: 

{conference_data}

## Instructions

1. **First, identify the upcoming year(s).** Inspect each year block in the current data above and compare its `end` (or `start`/`date`) field to today's date. Any year that has already ended is **past** and must not be modified. Only years whose `end`/`start` is after today are **upcoming** and eligible for updates. If no upcoming year is yet listed but a future edition has been announced, you may consider adding it.
2. Search the web for the latest information about the **upcoming** year(s) of this conference (dates, deadlines, location, venue, etc.). Do not research past years.
3. Compare what you find with the current data for the upcoming year(s) only.
4. Return your findings as structured output with:
   - `requires_update`: whether the data needs updating (only `true` if there is new, verified information for an **upcoming** year)
   - `reasoning`: explanation of why an update is or isn't needed. Explicitly state which year(s) you considered upcoming vs past based on today's date.
   - `updated_yaml`: the full updated YAML content (include ALL years, not just new ones). Past years must be byte-for-byte identical to the current data. If no update is needed, return the current data as-is.
   - `source_urls`: list of URLs you used as sources

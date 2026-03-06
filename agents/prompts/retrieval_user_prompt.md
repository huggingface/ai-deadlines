Please look at the data for the following conference, search the web for up-to-date information, and return your findings as structured output.

## Conference name

Name: {conference_name}

## Current conference data

Currently, the following data is in place: 

{conference_data}

## Instructions

1. Search the web for the latest information about this conference (dates, deadlines, location, venue, etc.).
2. Compare what you find with the current data above.
3. Return your findings as structured output with:
   - `requires_update`: whether the data needs updating
   - `reasoning`: explanation of why an update is or isn't needed
   - `updated_yaml`: the full updated YAML content (include ALL years, not just new ones). If no update is needed, return the current data as-is.
   - `source_urls`: list of URLs you used as sources

import yaml
import requests
from datetime import datetime
from typing import Dict, List, Any


def fetch_conference_files() -> List[Dict[str, Any]]:
    """Fetch all conference YAML files from ccfddl repository."""

    # First get the directory listing from GitHub API
    api_url = "https://api.github.com/repos/ccfddl/ccf-deadlines/contents/conference/AI"
    response = requests.get(api_url)
    files = response.json()

    conferences = []
    for file in files:
        if file["name"].endswith(".yml"):
            yaml_content = requests.get(file["download_url"]).text
            conf_data = yaml.safe_load(yaml_content)
            # The data is a list with a single item
            if isinstance(conf_data, list) and len(conf_data) > 0:
                conferences.append(conf_data[0])

    return conferences


def parse_date_range(date_str: str, year: str) -> tuple[str, str]:
    """Parse various date formats and return start and end dates."""
    # Remove the year if it appears at the end of the string
    date_str = date_str.replace(f", {year}", "")

    # Handle various date formats
    try:
        # Split into start and end dates
        if " - " in date_str:
            start, end = date_str.split(" - ")
        elif "-" in date_str:
            start, end = date_str.split("-")
        else:
            # For single date format like "May 19, 2025"
            start = end = date_str

        # Clean up month abbreviations
        month_map = {
            "Sept": "September",  # Handle Sept before Sep
            "Jan": "January",
            "Feb": "February",
            "Mar": "March",
            "Apr": "April",
            "Jun": "June",
            "Jul": "July",
            "Aug": "August",
            "Sep": "September",
            "Oct": "October",
            "Nov": "November",
            "Dec": "December",
        }

        # Create a set of all month names (full and abbreviated)
        all_months = set(month_map.keys()) | set(month_map.values())

        # Handle cases like "April 29-May 4"
        has_month = any(month in end for month in all_months)
        if not has_month:
            # End is just a day number, use start's month
            start_parts = start.split()
            if len(start_parts) >= 1:
                end = f"{start_parts[0]} {end.strip()}"

        # Replace month abbreviations
        for abbr, full in month_map.items():
            start = start.replace(abbr, full)
            end = end.replace(abbr, full)

        # Clean up any extra spaces
        start = " ".join(start.split())
        end = " ".join(end.split())

        # Parse start date
        start_date = datetime.strptime(f"{start}, {year}", "%B %d, %Y")

        # Parse end date
        end_date = datetime.strptime(f"{end}, {year}", "%B %d, %Y")

        return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")

    except Exception as e:
        raise ValueError(f"Could not parse date: {date_str} ({e})")


def transform_conference_data(
    conferences: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Transform ccfddl format to our format."""
    transformed = []
    current_year = datetime.now().year

    for conf in conferences:
        # Get the most recent or upcoming conference instance
        recent_conf = None
        if "confs" in conf:
            for instance in conf["confs"]:
                if instance["year"] >= current_year:
                    recent_conf = instance
                    break

        if not recent_conf:
            continue

        # Transform to our format
        transformed_conf = {
            "title": conf.get("title", ""),
            "year": recent_conf["year"],
            "id": recent_conf["id"],
            "full_name": conf.get("description", ""),
            "link": recent_conf.get("link", ""),
            "deadline": recent_conf.get("timeline", [{}])[0].get("deadline", ""),
            "timezone": recent_conf.get("timezone", ""),
            "date": recent_conf.get("date", ""),
            "tags": [],  # We'll need to maintain a mapping for tags
        }

        # Handle city and country fields instead of place
        place = recent_conf.get("place", "")
        if place:
            # Try to parse the place into city and country if it contains a comma
            if "," in place:
                city, country = place.split(",", 1)
                transformed_conf["city"] = city.strip()
                transformed_conf["country"] = country.strip()
            else:
                # If we can't parse, just set the country
                transformed_conf["country"] = place.strip()

        # Add optional fields
        timeline = recent_conf.get("timeline", [{}])[0]
        if "abstract_deadline" in timeline:
            transformed_conf["abstract_deadline"] = timeline["abstract_deadline"]

        # Parse date range for start/end
        try:
            if transformed_conf["date"]:
                start_date, end_date = parse_date_range(
                    transformed_conf["date"], str(transformed_conf["year"])
                )
                transformed_conf["start"] = start_date
                transformed_conf["end"] = end_date
        except Exception as e:
            print(f"Warning: Could not parse date for {transformed_conf['title']}: {e}")

        # Add rankings as separate field
        if "rank" in conf:
            rankings = []
            for rank_type, rank_value in conf["rank"].items():
                rankings.append(f"{rank_type.upper()}: {rank_value}")
            if rankings:
                transformed_conf["rankings"] = ", ".join(rankings)

        transformed.append(transformed_conf)

    return transformed


def main():
    try:
        # Fetch current conferences.yml
        current_file = "src/data/conferences.yml"
        with open(current_file, "r") as f:
            current_conferences = yaml.safe_load(f)

        # Fetch and transform new data
        new_conferences = fetch_conference_files()
        if not new_conferences:
            print("Warning: No conferences fetched from ccfddl")
            return

        transformed_conferences = transform_conference_data(new_conferences)
        if not transformed_conferences:
            print("Warning: No conferences transformed")
            return

        # Create a dictionary of current conferences by ID
        current_conf_dict = {conf["id"]: conf for conf in current_conferences}

        # Create a set of existing conference title+year combinations to check for duplicates
        existing_conf_keys = {
            (conf["title"], conf["year"]) for conf in current_conferences
        }

        # Update or add new conferences while preserving existing ones
        for new_conf in transformed_conferences:
            # Check if this is a duplicate based on title and year
            conf_key = (new_conf["title"], new_conf["year"])

            # Skip if we already have a conference with this title and year but different ID
            if (
                conf_key in existing_conf_keys
                and new_conf["id"] not in current_conf_dict
            ):
                print(
                    f"Skipping duplicate conference: {new_conf['title']} {new_conf['year']} (ID: {new_conf['id']})"
                )
                continue

            if new_conf["id"] in current_conf_dict:
                # Update existing conference while preserving fields
                curr_conf = current_conf_dict[new_conf["id"]]

                # Preserve existing fields
                preserved_fields = [
                    "tags",
                    "venue",
                    "hindex",
                    "submission_deadline",
                    "timezone_submission",
                    "rebuttal_period_start",
                    "rebuttal_period_end",
                    "final_decision_date",
                    "review_release_date",
                    "commitment_deadline",
                    "start",
                    "end",
                    "note",
                    "city",
                    "country",  # Added city and country to preserved fields
                ]
                for field in preserved_fields:
                    if field in curr_conf:
                        new_conf[field] = curr_conf[field]

                # If start/end not in current conference but we parsed them, keep the parsed ones
                if "start" not in curr_conf and "start" in new_conf:
                    new_conf["start"] = new_conf["start"]
                if "end" not in curr_conf and "end" in new_conf:
                    new_conf["end"] = new_conf["end"]

                # Preserve existing rankings if available
                if "rankings" in curr_conf:
                    new_conf["rankings"] = curr_conf["rankings"]

                # Update the conference in the dictionary
                current_conf_dict[new_conf["id"]] = new_conf
            else:
                # Add new conference to the dictionary
                current_conf_dict[new_conf["id"]] = new_conf
                # Add to our set of existing conference keys
                existing_conf_keys.add(conf_key)

        # Convert back to list and sort by deadline
        all_conferences = list(current_conf_dict.values())
        all_conferences.sort(key=lambda x: x.get("deadline", "9999"))

        # Write back to file with newlines between conferences
        with open(current_file, "w") as f:
            for i, conf in enumerate(all_conferences):
                if i > 0:
                    f.write("\n\n")  # Add two newlines between conferences

                yaml_str = yaml.dump(
                    [conf],
                    allow_unicode=True,
                    sort_keys=False,
                    default_flow_style=False,
                    explicit_start=False,
                    explicit_end=False,
                    width=float("inf"),
                    indent=2,
                    default_style=None,
                )
                f.write(yaml_str.rstrip())  # Remove trailing whitespace

            # Add final newline
            f.write("\n")

        print(f"Successfully updated {len(all_conferences)} conferences")

    except Exception as e:
        print(f"Error: {e}")
        raise


if __name__ == "__main__":
    main()

import yaml
import requests
import os
import re
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


def load_all_current_conferences() -> Dict[str, List[Dict[str, Any]]]:
    """Load all current conferences from individual files."""
    conferences_dir = "src/data/conferences"
    conference_groups = {}

    if not os.path.exists(conferences_dir):
        return {}

    for filename in os.listdir(conferences_dir):
        if filename.endswith(".yml"):
            filepath = os.path.join(conferences_dir, filename)
            with open(filepath, "r") as f:
                conferences = yaml.safe_load(f)
                if conferences:
                    # Extract conference title from the first entry
                    title = conferences[0]["title"]
                    conference_groups[title] = conferences

    return conference_groups


def create_filename_from_title(title: str) -> str:
    """Create a filename-safe version of the conference title."""
    filename = re.sub(r"[^a-zA-Z0-9\s&()-]", "", title.lower())
    filename = re.sub(r"\s+", "_", filename)
    filename = filename.replace("&", "and")
    filename = filename.strip("_")
    return filename


def update_conference_loader():
    """Update the conference loader file with all current conferences."""
    conferences_dir = "src/data/conferences"
    loader_path = "src/utils/conferenceLoader.ts"

    # Get all conference files
    conference_files = []
    if os.path.exists(conferences_dir):
        for filename in sorted(os.listdir(conferences_dir)):
            if filename.endswith(".yml"):
                conference_files.append(filename)

    # Generate import statements
    imports = []
    variable_names = []

    for filename in conference_files:
        # Create variable name from filename
        var_name = filename.replace(".yml", "").replace("-", "_") + "Data"
        variable_names.append(var_name)
        imports.append(f"import {var_name} from '@/data/conferences/{filename}';")

    # Generate the loader file content
    loader_content = f"""import {{ Conference }} from '@/types/conference';

// Import all conference YAML files
{chr(10).join(imports)}

// Combine all conference data into a single array
const allConferencesData: Conference[] = [
{chr(10).join(f"  ...{var_name}," for var_name in variable_names)}
];

export default allConferencesData;"""

    # Write the loader file
    with open(loader_path, "w") as f:
        f.write(loader_content)

    print(f"Updated conference loader with {len(conference_files)} conference files")


def main():
    try:
        # Load current conferences from individual files
        current_conference_groups = load_all_current_conferences()

        # Fetch and transform new data
        new_conferences = fetch_conference_files()
        if not new_conferences:
            print("Warning: No conferences fetched from ccfddl")
            return

        transformed_conferences = transform_conference_data(new_conferences)
        if not transformed_conferences:
            print("Warning: No conferences transformed")
            return

        # Create conferences directory if it doesn't exist
        conferences_dir = "src/data/conferences"
        os.makedirs(conferences_dir, exist_ok=True)

        # Group new conferences by title
        new_conference_groups = {}
        for conf in transformed_conferences:
            title = conf["title"]
            if title not in new_conference_groups:
                new_conference_groups[title] = []
            new_conference_groups[title].append(conf)

        # Update each conference group
        updated_count = 0
        for title, new_confs in new_conference_groups.items():
            filename = create_filename_from_title(title) + ".yml"
            filepath = os.path.join(conferences_dir, filename)

            # Get current conferences for this title
            current_confs = current_conference_groups.get(title, [])
            current_conf_dict = {conf["id"]: conf for conf in current_confs}

            # Update or add new conferences
            for new_conf in new_confs:
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
                        "country",
                        "deadlines",
                    ]
                    for field in preserved_fields:
                        if field in curr_conf:
                            new_conf[field] = curr_conf[field]

                    # Preserve existing rankings if available
                    if "rankings" in curr_conf:
                        new_conf["rankings"] = curr_conf["rankings"]

                    current_conf_dict[new_conf["id"]] = new_conf
                else:
                    # Add new conference
                    current_conf_dict[new_conf["id"]] = new_conf

            # Convert back to list and sort by year
            all_confs = list(current_conf_dict.values())
            all_confs.sort(key=lambda x: x.get("year", 9999))

            # Write to individual file
            with open(filepath, "w") as f:
                yaml.dump(
                    all_confs,
                    f,
                    default_flow_style=False,
                    sort_keys=False,
                    allow_unicode=True,
                )

            updated_count += 1
            print(f"Updated {filename} with {len(all_confs)} entries")

        # Update the conference loader
        update_conference_loader()

        print(f"Successfully updated {updated_count} conference files")

    except Exception as e:
        print(f"Error: {e}")
        raise


if __name__ == "__main__":
    main()

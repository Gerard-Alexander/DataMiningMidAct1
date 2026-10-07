from pathlib import Path

import json
from pathlib import Path
from typing import Any


# Get the folder where this Python script is located.
BASE_DIR = Path(__file__).resolve().parent

# Input folders.
PROJECT_DIR = BASE_DIR.parent.parent
YOUTUBE_DIR = PROJECT_DIR / "Topic Modelling" / "youtube_results"
TIKTOK_DIR = PROJECT_DIR / "Topic Modelling" / "tiktok_results"

# Output file.
OUTPUT_FILE = BASE_DIR / "combined_dataset.json"


def load_json(path: Path) -> Any:
    """Read one normal JSON file."""
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_jsonl(path: Path) -> list:
    """
    Read one JSONL file.

    A JSONL file contains one JSON object per line.
    """
    records = []

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):

            # Remove spaces and line breaks.
            line = line.strip()

            # Skip empty lines.
            if not line:
                continue

            try:
                records.append(json.loads(line))

            except json.JSONDecodeError as error:
                print(
                    f"WARNING: Could not read "
                    f"{path.name}, line {line_number}: {error}"
                )

    return records


def expand_records(data: Any) -> list:
    """
    Convert different JSON structures into a list.

    Supported examples:

    [
        {...},
        {...}
    ]

    {
        "records": [...]
    }

    {
        "data": [...]
    }

    A normal single YouTube record is also supported.
    """

    # If the JSON itself is already a list.
    if isinstance(data, list):
        return data

    # If the JSON is a dictionary.
    if isinstance(data, dict):

        # Previously combined dataset.
        if isinstance(data.get("records"), list):
            return data["records"]

        # Generic data wrapper.
        if isinstance(data.get("data"), list):
            return data["data"]

        # Normal single scraped record.
        return [data]

    # Fallback.
    return [data]


def add_source_info(
    record: Any,
    platform: str,
    source_file: str
):
    """
    Add information about the source.

    Original fields are not removed.
    """

    if isinstance(record, dict):

        # Make a copy so the original object is not changed.
        record = dict(record)

        # Add source information.
        record["_platform"] = platform
        record["_source_file"] = source_file

        return record

    # Fallback if the source record is not a dictionary.
    return {
        "_platform": platform,
        "_source_file": source_file,
        "data": record
    }


def read_youtube_files() -> list:
    """Read all .json files from youtube_results."""

    records = []

    # Check whether the folder exists.
    if not YOUTUBE_DIR.exists():
        print(
            f"WARNING: YouTube folder not found: "
            f"{YOUTUBE_DIR}"
        )
        return records

    # Read only .json files.
    # TXT files are automatically ignored.
    for path in sorted(YOUTUBE_DIR.glob("*.json")):

        try:
            data = load_json(path)

            # One file may contain one or multiple records.
            source_records = expand_records(data)

            for record in source_records:

                records.append(
                    add_source_info(
                        record,
                        "YouTube",
                        path.name
                    )
                )

            print(
                f"YouTube: {path.name} -> "
                f"{len(source_records)} record(s)"
            )

        except Exception as error:

            print(
                f"ERROR reading YouTube file "
                f"{path.name}: {error}"
            )

    return records


def read_tiktok_files() -> list:
    """Read all .jsonl files from tiktok_results."""

    records = []

    # Check whether the folder exists.
    if not TIKTOK_DIR.exists():
        print(
            f"WARNING: TikTok folder not found: "
            f"{TIKTOK_DIR}"
        )
        return records

    # Read only .jsonl files.
    # TXT files are automatically ignored.
    for path in sorted(TIKTOK_DIR.glob("*.jsonl")):

        try:
            source_records = load_jsonl(path)

            for record in source_records:

                records.append(
                    add_source_info(
                        record,
                        "TikTok",
                        path.name
                    )
                )

            print(
                f"TikTok: {path.name} -> "
                f"{len(source_records)} record(s)"
            )

        except Exception as error:

            print(
                f"ERROR reading TikTok file "
                f"{path.name}: {error}"
            )

    return records


def main():

    print("=" * 70)
    print("COMBINING YOUTUBE + TIKTOK DATASETS")
    print("=" * 70)
    print()

    # Read YouTube JSON files.
    youtube_records = read_youtube_files()

    print()

    # Read TikTok JSONL files.
    tiktok_records = read_tiktok_files()

    # Combine both datasets.
    all_records = youtube_records + tiktok_records

    # Create the final dataset structure.
    combined_dataset = {
        "dataset_info": {
            "description": (
                "Raw consolidated YouTube and TikTok "
                "dataset. No preprocessing was performed."
            ),
            "youtube_records": len(youtube_records),
            "tiktok_records": len(tiktok_records),
            "total_records": len(all_records)
        },
        "records": all_records
    }

    # Save the combined dataset.
    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            combined_dataset,
            file,
            ensure_ascii=False,
            indent=2
        )

    # Display summary.
    print()
    print("=" * 70)
    print("COMBINATION COMPLETE")
    print("=" * 70)
    print(f"YouTube records : {len(youtube_records)}")
    print(f"TikTok records  : {len(tiktok_records)}")
    print(f"Total records   : {len(all_records)}")
    print()
    print(f"Output file:")
    print(OUTPUT_FILE)
    print("=" * 70)


# Start the program.
if __name__ == "__main__":
    main()

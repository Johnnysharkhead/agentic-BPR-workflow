"""Export BPR deviation results to CSV for SharePoint list import.

Usage:
    uv run python -m novartis_agentic_demo.export_to_csv

Output: outputs/sharepoint_import.csv
"""

import csv
import json
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent.parent / "outputs"
CSV_FILE = OUTPUT_DIR / "sharepoint_import.csv"
COLUMNS = ["Title", "BatchID", "Severity", "Deviation", "Recommendation"]


def main():
    rows = []
    for path in sorted(OUTPUT_DIR.glob("BATCH-*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        rows.append(data["sharepoint_item"])

    if not rows:
        print(f"No BATCH-*.json files found in {OUTPUT_DIR}/")
        return

    with CSV_FILE.open("w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig for Excel compatibility
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Exported {len(rows)} rows → {CSV_FILE}")


if __name__ == "__main__":
    main()

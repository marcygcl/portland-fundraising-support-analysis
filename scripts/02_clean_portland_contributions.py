"""Combine and standardize the Portland contribution source files.

Pipeline role
-------------
raw JSON/GeoJSON
    -> clean multi-year transaction table
    -> candidate-level source index

This is source cleaning only. Fundraising profiles and analysis belong later
in notebooks.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from helpers.linkage import normalize_name
from helpers.paths import CLEAN, RAW


RAW_DIR = RAW / "portland_contributions"
OUTPUT_DIR = CLEAN / "portland_contributions"

PARTICIPANT_PATH = RAW_DIR / "contributions.json"
EXTERNAL_PATH = RAW_DIR / "external-contributions.json"

TRANSACTIONS_OUTPUT = OUTPUT_DIR / "contributions.csv"
CANDIDATE_INDEX_OUTPUT = OUTPUT_DIR / "candidate_index.csv"


def load_features(path):
    """Return a list of features from JSON or GeoJSON."""
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if isinstance(data, dict) and data.get("type") == "FeatureCollection":
        return data.get("features", [])

    if isinstance(data, list):
        return data

    if isinstance(data, dict) and data.get("type") == "Feature":
        return [data]

    raise ValueError(f"Unsupported JSON/GeoJSON structure: {path}")


def features_to_frame(features, source_label):
    """Convert GeoJSON features into ordinary table rows."""
    rows = []

    for feature in features:
        row = dict(feature.get("properties", {}))

        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates")

        row["source_file_group"] = source_label
        row["longitude"] = np.nan
        row["latitude"] = np.nan

        is_point = geometry.get("type") == "Point"
        has_coordinates = (
            isinstance(coordinates, (list, tuple))
            and len(coordinates) >= 2
        )

        if is_point and has_coordinates:
            row["longitude"] = coordinates[0]
            row["latitude"] = coordinates[1]

        rows.append(row)

    return pd.DataFrame(rows)


def main(force=False):
    """Create one clean multi-year contribution source."""
    outputs_exist = (
        TRANSACTIONS_OUTPUT.exists()
        and CANDIDATE_INDEX_OUTPUT.exists()
    )

    if outputs_exist and not force:
        print("SKIP  clean Portland contribution outputs already exist")
        return

    # 1. Check raw inputs.
    for path in [PARTICIPANT_PATH, EXTERNAL_PATH]:
        if not path.exists():
            raise FileNotFoundError(f"Missing raw source: {path}")

    # 2. Read and combine both source groups.
    participant = features_to_frame(
        load_features(PARTICIPANT_PATH),
        "participant",
    )
    external = features_to_frame(
        load_features(EXTERNAL_PATH),
        "non_participant",
    )

    data = pd.concat(
        [participant, external],
        ignore_index=True,
        sort=False,
    )

    # 3. Make sure the source still has the fields we rely on.
    required = {"campaignName", "officeSought", "amount"}
    missing = required - set(data.columns)

    if missing:
        raise ValueError(
            f"Contribution source is missing required fields: {sorted(missing)}"
        )

    # 4. Standardize amount, date, district, and year.
    data["amount"] = pd.to_numeric(data["amount"], errors="coerce")

    if "date" in data.columns:
        data["date"] = pd.to_datetime(
            data["date"],
            errors="coerce",
            utc=True,
        )

    district_text = (
        data["officeSought"]
        .astype(str)
        .str.extract(
            r"Councilor\s+District\s+([1-4])",
            expand=False,
        )
    )
    data["district"] = pd.to_numeric(district_text, errors="coerce")

    year_text = (
        data["campaignName"]
        .astype(str)
        .str.extract(r"(\d{4})\s*$", expand=False)
    )
    data["year"] = pd.to_numeric(year_text, errors="coerce")

    # 5. Keep usable City Council records.
    valid_row = (
        data["district"].isin([1, 2, 3, 4])
        & data["year"].notna()
        & data["amount"].notna()
    )
    data = data.loc[valid_row].copy()

    data["district"] = data["district"].astype(int)
    data["year"] = data["year"].astype(int)

    # 6. Create a source-level candidate name.
    data["candidate"] = (
        data["campaignName"]
        .astype(str)
        .str.replace(r"\s*\d{4}\s*$", "", regex=True)
        .str.strip()
    )
    data["candidate_norm"] = data["candidate"].map(normalize_name)

    # 7. Keep public matching rows in clean data, but flag them explicitly.
    if "oaeType" in data.columns:
        oae_type = data["oaeType"].astype(str).str.strip().str.lower()
        data["is_public_matching_contribution"] = oae_type.eq(
            "public_matching_contribution"
        )
    else:
        data["is_public_matching_contribution"] = False

    # Only exact duplicate rows are removed.
    data = data.drop_duplicates().reset_index(drop=True)

    # 8. Build one source-index row per candidate/year/district.
    aggregation = {
        "contribution_records": ("amount", "size"),
        "total_amount": ("amount", "sum"),
    }

    if "date" in data.columns:
        aggregation["first_record_date"] = ("date", "min")
        aggregation["last_record_date"] = ("date", "max")

    candidate_index = (
        data.groupby(
            ["year", "district", "candidate", "candidate_norm"],
            as_index=False,
        )
        .agg(**aggregation)
        .sort_values(["year", "district", "candidate"])
    )

    # 9. Save clean source tables.
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    data.to_csv(TRANSACTIONS_OUTPUT, index=False)
    candidate_index.to_csv(CANDIDATE_INDEX_OUTPUT, index=False)

    print(f"SAVED {TRANSACTIONS_OUTPUT}")
    print(f"SAVED {CANDIDATE_INDEX_OUTPUT}")
    print(f"Candidate-year rows: {len(candidate_index):,}")
    print(f"Contribution records: {len(data):,}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    main(force=args.force)

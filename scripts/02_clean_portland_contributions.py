#!/usr/bin/env python3
"""Combine and standardize the global Portland contribution source files.

This stage does source cleaning only. Fundraising bins, profiles, distances,
PAM, and plots belong in later notebooks.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import argparse
import json

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
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if isinstance(data, dict) and data.get("type") == "FeatureCollection":
        return data.get("features", [])
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and data.get("type") == "Feature":
        return [data]

    raise ValueError(f"Unsupported JSON/GeoJSON structure: {path}")


def features_to_frame(features, source_label):
    rows = []

    for feature in features:
        row = dict(feature.get("properties", {}))
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates")

        row["source_file_group"] = source_label
        row["longitude"] = np.nan
        row["latitude"] = np.nan

        if (
            geometry.get("type") == "Point"
            and isinstance(coordinates, (list, tuple))
            and len(coordinates) >= 2
        ):
            row["longitude"] = coordinates[0]
            row["latitude"] = coordinates[1]

        rows.append(row)

    return pd.DataFrame(rows)


def main(force=False):
    if (
        TRANSACTIONS_OUTPUT.exists()
        and CANDIDATE_INDEX_OUTPUT.exists()
        and not force
    ):
        print("SKIP  clean Portland contribution outputs already exist")
        return

    for path in [PARTICIPANT_PATH, EXTERNAL_PATH]:
        if not path.exists():
            raise FileNotFoundError(f"Missing raw source: {path}")

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

    required = {"campaignName", "officeSought", "amount"}
    missing = sorted(required - set(data.columns))
    if missing:
        raise ValueError(
            f"Contribution source is missing required fields: {missing}"
        )

    data["amount"] = pd.to_numeric(data["amount"], errors="coerce")

    if "date" in data.columns:
        data["date"] = pd.to_datetime(
            data["date"],
            errors="coerce",
            utc=True,
        )

    data["district"] = pd.to_numeric(
        data["officeSought"]
        .astype(str)
        .str.extract(
            r"Councilor\s+District\s+([1-4])",
            expand=False,
        ),
        errors="coerce",
    )

    data["year"] = pd.to_numeric(
        data["campaignName"]
        .astype(str)
        .str.extract(r"(\d{4})\s*$", expand=False),
        errors="coerce",
    )

    data = data.loc[
        data["district"].isin([1, 2, 3, 4])
        & data["year"].notna()
        & data["amount"].notna()
    ].copy()

    data["district"] = data["district"].astype(int)
    data["year"] = data["year"].astype(int)

    data["candidate"] = (
        data["campaignName"]
        .astype(str)
        .str.replace(r"\s*\d{4}\s*$", "", regex=True)
        .str.strip()
    )
    data["candidate_norm"] = data["candidate"].map(normalize_name)

    if "oaeType" in data.columns:
        data["is_public_matching_contribution"] = (
            data["oaeType"]
            .astype(str)
            .str.strip()
            .str.lower()
            .eq("public_matching_contribution")
        )
    else:
        data["is_public_matching_contribution"] = False

    data = data.drop_duplicates().reset_index(drop=True)

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

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    data.to_csv(TRANSACTIONS_OUTPUT, index=False)
    candidate_index.to_csv(CANDIDATE_INDEX_OUTPUT, index=False)

    print(f"SAVED {TRANSACTIONS_OUTPUT}")
    print(f"SAVED {CANDIDATE_INDEX_OUTPUT}")
    print(f"Candidate-year rows: {len(candidate_index)}")
    print(f"Contribution records: {len(data)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    main(force=args.force)

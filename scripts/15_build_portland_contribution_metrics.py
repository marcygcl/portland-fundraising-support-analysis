"""Build candidate-level fundraising metrics from Portland contributions.

Input
-----
data/clean/portland_contributions/contributions.csv

Output
------
data/processed/candidate_metrics/<year>/portland_contribution_metrics.csv

Important
---------
The clean contributions table remains the source of truth.

This script only summarizes that long table to one row per candidate.

Main fundraising totals exclude public matching contributions.
Public matching is kept in separate columns.

Contribution counts are contribution-record counts, not unique donors.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from helpers.paths import CLEAN, PROCESSED


# ===============================================================
# 1. SETTINGS
# ===============================================================

YEARS = [2024, 2026]

INPUT_PATH = (
    CLEAN
    / "portland_contributions"
    / "contributions.csv"
)

BIN_EDGES = [
    -np.inf,
    25,
    100,
    250,
    1000,
    np.inf,
]

BIN_LABELS = [
    "Micro",
    "Small",
    "Medium",
    "Large",
    "Mega",
]


# ===============================================================
# 2. SMALL HELPERS
# ===============================================================

def make_boolean(series):
    """Convert common true/false text values to Python booleans."""

    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)

    return (
        series.astype("string")
        .str.strip()
        .str.lower()
        .isin(["true", "1", "yes"])
    )


def load_candidate_matches(year):
    """Load confirmed Portland-contribution -> official-candidate matches."""

    path = (
        PROCESSED
        / "candidates"
        / f"candidate_source_crosswalk_{year}.csv"
    )

    crosswalk = pd.read_csv(
        path,
        low_memory=False,
    )

    matches = crosswalk.loc[
        crosswalk["source"].eq("portland_contributions")
        & crosswalk["classification"].eq("match"),
        [
            "year",
            "district",
            "source_candidate_name",
            "suggested_candidate",
            "suggested_candidate_key",
        ],
    ].copy()

    matches = matches.rename(
        columns={
            "suggested_candidate": "candidate",
            "suggested_candidate_key": "candidate_key",
        }
    )

    return matches.drop_duplicates()


# ===============================================================
# 3. BUILD ONE YEAR
# ===============================================================

def build_year(data, year):

    print()
    print("=" * 70)
    print(f"PORTLAND CONTRIBUTION METRICS — {year}")
    print("=" * 70)

    # -----------------------------------------------------------
    # A. Keep one election year
    # -----------------------------------------------------------

    year_data = data.loc[
        data["year"].eq(year)
    ].copy()

    if year_data.empty:
        print("No rows found.")
        return

    # -----------------------------------------------------------
    # B. Attach the official candidate key
    # -----------------------------------------------------------

    matches = load_candidate_matches(year)

    year_data["source_candidate_name"] = (
        year_data["candidate"]
        .astype("string")
        .str.strip()
    )

    year_data = year_data.merge(
        matches,
        on=[
            "year",
            "district",
            "source_candidate_name",
        ],
        how="left",
        validate="many_to_one",
        suffixes=("_source", ""),
    )

    matched_rows = year_data["candidate_key"].notna().sum()

    print(
        f"Matched contribution rows: "
        f"{matched_rows:,} / {len(year_data):,}"
    )

    unmatched_names = (
        year_data.loc[
            year_data["candidate_key"].isna(),
            "source_candidate_name",
        ]
        .dropna()
        .drop_duplicates()
        .tolist()
    )

    if unmatched_names:
        print(
            "Unmatched candidate labels: "
            + " | ".join(unmatched_names)
        )

    year_data = year_data.loc[
        year_data["candidate_key"].notna()
    ].copy()

    # -----------------------------------------------------------
    # C. Prepare contribution amounts
    # -----------------------------------------------------------

    year_data["amount"] = pd.to_numeric(
        year_data["amount"],
        errors="coerce",
    )

    positive = (
        year_data["amount"].notna()
        & year_data["amount"].gt(0)
    )

    if "is_public_matching_contribution" in year_data.columns:
        is_public = make_boolean(
            year_data["is_public_matching_contribution"]
        )
    else:
        is_public = pd.Series(
            False,
            index=year_data.index,
        )

    private = year_data.loc[
        positive & ~is_public
    ].copy()

    public = year_data.loc[
        positive & is_public
    ].copy()

    keys = [
        "year",
        "district",
        "candidate_key",
    ]

    # -----------------------------------------------------------
    # D. Candidate identity table
    # -----------------------------------------------------------

    candidate_base = (
        year_data[
            keys
            + [
                "candidate",
                "source_candidate_name",
            ]
        ]
        .drop_duplicates(keys)
        .rename(
            columns={
                "source_candidate_name":
                    "portland_source_candidate_name",
            }
        )
    )

    # -----------------------------------------------------------
    # E. Overall private fundraising metrics
    # -----------------------------------------------------------

    totals = (
        private.groupby(
            keys,
            as_index=False,
        )
        .agg(
            portland_total_fundraising=(
                "amount",
                "sum",
            ),
            portland_total_contribution_count=(
                "amount",
                "size",
            ),
            portland_average_contribution=(
                "amount",
                "mean",
            ),
            portland_median_contribution=(
                "amount",
                "median",
            ),
        )
    )

    # -----------------------------------------------------------
    # F. Public matching metrics
    # -----------------------------------------------------------

    public_totals = (
        public.groupby(
            keys,
            as_index=False,
        )
        .agg(
            portland_public_matching_amount=(
                "amount",
                "sum",
            ),
            portland_public_matching_count=(
                "amount",
                "size",
            ),
        )
    )

    # -----------------------------------------------------------
    # G. Contribution-size bins
    # -----------------------------------------------------------

    private["contribution_bin"] = pd.cut(
        private["amount"],
        bins=BIN_EDGES,
        labels=BIN_LABELS,
        right=True,
        include_lowest=True,
    )

    bin_long = (
        private.groupby(
            keys + ["contribution_bin"],
            observed=True,
            as_index=False,
        )
        .agg(
            bin_amount=("amount", "sum"),
            bin_count=("amount", "size"),
        )
    )

    amount_wide = bin_long.pivot_table(
        index=keys,
        columns="contribution_bin",
        values="bin_amount",
        fill_value=0,
        observed=True,
    )

    count_wide = bin_long.pivot_table(
        index=keys,
        columns="contribution_bin",
        values="bin_count",
        fill_value=0,
        observed=True,
    )

    amount_wide.columns = [
        f"portland_{str(column).lower()}_amount"
        for column in amount_wide.columns
    ]

    count_wide.columns = [
        f"portland_{str(column).lower()}_contribution_count"
        for column in count_wide.columns
    ]

    bins = (
        amount_wide.join(
            count_wide,
            how="outer",
        )
        .reset_index()
    )

    # -----------------------------------------------------------
    # H. Merge all Portland metrics
    # -----------------------------------------------------------

    metrics = candidate_base.merge(
        totals,
        on=keys,
        how="left",
        validate="one_to_one",
    )

    metrics = metrics.merge(
        public_totals,
        on=keys,
        how="left",
        validate="one_to_one",
    )

    metrics = metrics.merge(
        bins,
        on=keys,
        how="left",
        validate="one_to_one",
    )

    # -----------------------------------------------------------
    # I. Fill observed zero counts/amounts
    # -----------------------------------------------------------

    zero_columns = [
        "portland_total_fundraising",
        "portland_total_contribution_count",
        "portland_public_matching_amount",
        "portland_public_matching_count",
    ]

    for label in BIN_LABELS:
        name = label.lower()

        zero_columns += [
            f"portland_{name}_amount",
            f"portland_{name}_contribution_count",
        ]

    for column in zero_columns:
        if column not in metrics.columns:
            metrics[column] = 0

        metrics[column] = (
            metrics[column]
            .fillna(0)
        )

    # -----------------------------------------------------------
    # J. Combined micro + small metrics
    # -----------------------------------------------------------

    metrics[
        "portland_micro_small_contribution_count"
    ] = (
        metrics["portland_micro_contribution_count"]
        + metrics["portland_small_contribution_count"]
    )

    metrics[
        "portland_micro_small_amount"
    ] = (
        metrics["portland_micro_amount"]
        + metrics["portland_small_amount"]
    )

    metrics["has_portland_contribution_data"] = True

    # -----------------------------------------------------------
    # K. Save
    # -----------------------------------------------------------

    metrics = metrics.sort_values(
        ["district", "candidate"]
    )

    output_path = (
        PROCESSED
        / "candidate_metrics"
        / str(year)
        / "portland_contribution_metrics.csv"
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    metrics.to_csv(
        output_path,
        index=False,
    )

    print(
        f"SAVED {output_path} "
        f"({len(metrics)} candidates)"
    )


# ===============================================================
# 4. MAIN
# ===============================================================

def main():

    if not INPUT_PATH.exists():
        raise FileNotFoundError(
            "Run 02_clean_portland_contributions.py first."
        )

    contributions = pd.read_csv(
        INPUT_PATH,
        low_memory=False,
    )

    contributions["year"] = pd.to_numeric(
        contributions["year"],
        errors="coerce",
    )

    contributions["district"] = pd.to_numeric(
        contributions["district"],
        errors="coerce",
    )

    for year in YEARS:
        build_year(
            contributions,
            year,
        )


if __name__ == "__main__":
    main()

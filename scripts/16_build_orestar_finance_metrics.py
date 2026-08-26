"""Build candidate-level fundraising and spending metrics from ORESTAR.

Input
-----
data/clean/orestar/<year>/city_council/transactions.csv

Output
------
data/processed/candidate_metrics/<year>/orestar_finance_metrics.csv

The clean ORESTAR transaction table remains the source of truth.
This script only creates candidate-level summaries.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from helpers.paths import (
    PROCESSED,
    orestar_transactions_path,
)


# ===============================================================
# 1. SETTINGS
# ===============================================================

YEARS = [2024, 2026]

CONTEST = "city_council"

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
    """Convert common true/false text values to booleans."""

    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)

    return (
        series.astype("string")
        .str.strip()
        .str.lower()
        .isin(["true", "1", "yes"])
    )


def load_candidate_matches(year):
    """Load confirmed ORESTAR -> official-candidate matches."""

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
        crosswalk["source"].eq("orestar")
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


def build_bin_table(data, value_name):
    """Build wide Micro-Small-Medium-Large-Mega amounts and counts."""

    keys = [
        "year",
        "district",
        "candidate_key",
    ]

    data = data.copy()

    data["size_bin"] = pd.cut(
        data["amount"],
        bins=BIN_EDGES,
        labels=BIN_LABELS,
        right=True,
        include_lowest=True,
    )

    grouped = (
        data.groupby(
            keys + ["size_bin"],
            observed=True,
            as_index=False,
        )
        .agg(
            bin_amount=("amount", "sum"),
            bin_count=("amount", "size"),
        )
    )

    amount_wide = grouped.pivot_table(
        index=keys,
        columns="size_bin",
        values="bin_amount",
        fill_value=0,
        observed=True,
    )

    count_wide = grouped.pivot_table(
        index=keys,
        columns="size_bin",
        values="bin_count",
        fill_value=0,
        observed=True,
    )

    if value_name == "contribution":

        amount_wide.columns = [
            f"orestar_{str(column).lower()}_contribution_amount"
            for column in amount_wide.columns
        ]

        count_wide.columns = [
            f"orestar_{str(column).lower()}_contribution_count"
            for column in count_wide.columns
        ]

    else:

        amount_wide.columns = [
            f"orestar_{str(column).lower()}_spending_amount"
            for column in amount_wide.columns
        ]

        count_wide.columns = [
            f"orestar_{str(column).lower()}_expenditure_count"
            for column in count_wide.columns
        ]

    return (
        amount_wide.join(
            count_wide,
            how="outer",
        )
        .reset_index()
    )


# ===============================================================
# 3. BUILD ONE YEAR
# ===============================================================

def build_year(year):

    print()
    print("=" * 70)
    print(f"ORESTAR CANDIDATE METRICS — {year}")
    print("=" * 70)

    input_path = orestar_transactions_path(
        year,
        CONTEST,
    )

    transactions = pd.read_csv(
        input_path,
        low_memory=False,
    )

    # -----------------------------------------------------------
    # A. Attach official candidate keys
    # -----------------------------------------------------------

    matches = load_candidate_matches(year)

    transactions["source_candidate_name"] = (
        transactions["source_file_stem"]
        .astype("string")
        .str.strip()
    )

    transactions = transactions.merge(
        matches,
        on=[
            "year",
            "district",
            "source_candidate_name",
        ],
        how="left",
        validate="many_to_one",
    )

    matched_rows = transactions["candidate_key"].notna().sum()

    print(
        f"Matched ORESTAR rows: "
        f"{matched_rows:,} / {len(transactions):,}"
    )

    transactions = transactions.loc[
        transactions["candidate_key"].notna()
    ].copy()

    keys = [
        "year",
        "district",
        "candidate_key",
    ]

    candidate_base = (
        transactions[
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
                    "orestar_source_candidate_name",
            }
        )
    )

    # -----------------------------------------------------------
    # B. Fundraising rows
    # -----------------------------------------------------------

    transactions["reported_contribution_amount"] = pd.to_numeric(
        transactions["reported_contribution_amount"],
        errors="coerce",
    )

    contribution_rows = (
        make_boolean(
            transactions["is_reported_contribution"]
        )
        & transactions["reported_contribution_amount"].notna()
        & transactions["reported_contribution_amount"].gt(0)
    )

    contributions = transactions.loc[
        contribution_rows
    ].copy()

    contributions["amount"] = (
        contributions["reported_contribution_amount"]
    )

    fundraising_totals = (
        contributions.groupby(
            keys,
            as_index=False,
        )
        .agg(
            orestar_total_fundraising=(
                "amount",
                "sum",
            ),
            orestar_total_contribution_count=(
                "amount",
                "size",
            ),
            orestar_average_contribution=(
                "amount",
                "mean",
            ),
            orestar_median_contribution=(
                "amount",
                "median",
            ),
        )
    )

    fundraising_bins = build_bin_table(
        contributions,
        "contribution",
    )

    # -----------------------------------------------------------
    # C. Spending rows
    # -----------------------------------------------------------

    transactions["reported_expenditure_amount"] = pd.to_numeric(
        transactions["reported_expenditure_amount"],
        errors="coerce",
    )

    expenditure_rows = (
        make_boolean(
            transactions["is_reported_expenditure"]
        )
        & transactions["reported_expenditure_amount"].notna()
        & transactions["reported_expenditure_amount"].gt(0)
    )

    spending = transactions.loc[
        expenditure_rows
    ].copy()

    spending["amount"] = (
        spending["reported_expenditure_amount"]
    )

    spending_totals = (
        spending.groupby(
            keys,
            as_index=False,
        )
        .agg(
            orestar_total_spending=(
                "amount",
                "sum",
            ),
            orestar_total_expenditure_count=(
                "amount",
                "size",
            ),
            orestar_average_expenditure=(
                "amount",
                "mean",
            ),
            orestar_median_expenditure=(
                "amount",
                "median",
            ),
        )
    )

    spending_bins = build_bin_table(
        spending,
        "spending",
    )

    # -----------------------------------------------------------
    # D. Merge fundraising + spending
    # -----------------------------------------------------------

    metrics = candidate_base.merge(
        fundraising_totals,
        on=keys,
        how="left",
        validate="one_to_one",
    )

    metrics = metrics.merge(
        fundraising_bins,
        on=keys,
        how="left",
        validate="one_to_one",
    )

    metrics = metrics.merge(
        spending_totals,
        on=keys,
        how="left",
        validate="one_to_one",
    )

    metrics = metrics.merge(
        spending_bins,
        on=keys,
        how="left",
        validate="one_to_one",
    )

    # -----------------------------------------------------------
    # E. Replace observed missing counts/amounts with zero
    # -----------------------------------------------------------

    metric_columns = [
        column
        for column in metrics.columns
        if (
            column.startswith("orestar_")
            and (
                column.endswith("_amount")
                or column.endswith("_count")
                or column
                in {
                    "orestar_total_fundraising",
                    "orestar_total_spending",
                }
            )
        )
    ]

    for column in metric_columns:
        metrics[column] = (
            metrics[column]
            .fillna(0)
        )

    # -----------------------------------------------------------
    # F. Combined micro + small variables
    # -----------------------------------------------------------

    metrics[
        "orestar_micro_small_contribution_count"
    ] = (
        metrics["orestar_micro_contribution_count"]
        + metrics["orestar_small_contribution_count"]
    )

    metrics[
        "orestar_micro_small_contribution_amount"
    ] = (
        metrics["orestar_micro_contribution_amount"]
        + metrics["orestar_small_contribution_amount"]
    )

    metrics[
        "orestar_micro_small_expenditure_count"
    ] = (
        metrics["orestar_micro_expenditure_count"]
        + metrics["orestar_small_expenditure_count"]
    )

    metrics[
        "orestar_micro_small_spending_amount"
    ] = (
        metrics["orestar_micro_spending_amount"]
        + metrics["orestar_small_spending_amount"]
    )

    metrics["has_orestar_data"] = True

    # -----------------------------------------------------------
    # G. Save
    # -----------------------------------------------------------

    metrics = metrics.sort_values(
        ["district", "candidate"]
    )

    output_path = (
        PROCESSED
        / "candidate_metrics"
        / str(year)
        / "orestar_finance_metrics.csv"
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

    for year in YEARS:
        build_year(year)


if __name__ == "__main__":
    main()

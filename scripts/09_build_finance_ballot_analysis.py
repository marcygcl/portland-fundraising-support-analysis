"""Merge fundraising and spending aggregates with 2024 ballot support.

Big idea
--------
Ballot support (`mentions`, `first_place_votes`) only exists for 2024 --
the 2026 election hasn't happened yet, so there is no outcome data to
merge against for 2026. This script is 2024 only until that changes.

Workflow
--------
For each of fundraising and spending:

1. load the candidate profile bins (long) + candidate summary;
2. pivot the bins wide into amount/count share columns;
3. inner-merge with ballot support on (year, district, candidate_key);
4. run Pearson/Spearman correlations (totals + bin shares);
5. run log1p univariate regressions (totals only);
6. save the analysis table + correlations + regressions.

Only candidates present in both ballot support and the finance source are
kept -- this is meant to be a regression-ready table, not a full roster.

Output locations
-----------------
The merged candidate-level table (one row per candidate, reusable as input
to other analyses) is saved under `data/processed/finance_vs_ballot_support/`.
The correlation and regression tables are analysis results, not reusable
input data, so they stay under `data/processed/ballot_support/`.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from scipy.stats import linregress

from helpers.finance_feature_helpers import (
    calculate_correlations,
    calculate_correlations_by_district,
)
from helpers.paths import PROCESSED

YEAR = 2024

JOIN_KEYS = ["year", "district", "candidate_key"]

OUTCOMES = ["mention_share", "first_place_share"]

BIN_LABELS = ["Micro", "Small", "Medium", "Large", "Mega"]

BALLOT_SUPPORT_PATH = (
    PROCESSED
    / "ballot_support"
    / str(YEAR)
    / f"candidate_ballot_support_{YEAR}.csv"
)

BALLOT_SUPPORT_DIR = PROCESSED / "ballot_support" / str(YEAR)

# Reusable merged tables (finance + ballot support, one row per candidate)
# live here. Correlation/regression result tables stay in BALLOT_SUPPORT_DIR
# -- they are analysis output, not input data another notebook would load.
FINANCE_VS_BALLOT_DIR = PROCESSED / "finance_vs_ballot_support" / str(YEAR)

DOMAINS = {
    "fundraising": {
        "profiles_path": (
            PROCESSED
            / "fundraising"
            / str(YEAR)
            / "candidate_fundraising_profiles_long.csv"
        ),
        "summary_path": (
            PROCESSED
            / "fundraising"
            / str(YEAR)
            / "candidate_fundraising_summary.csv"
        ),
        "bin_column": "contribution_bin",
        "amount_column": "amount",
        "count_column": "contribution_count",
        "amount_share_column": "amount_share",
        "count_share_column": "contribution_share",
        "count_label": "contribution",
        "total_amount_column": "total_amount",
        "total_count_column": "total_contribution_count",
        "average_column": "average_contribution",
        "median_column": "median_contribution",
        "analysis_output": (
            FINANCE_VS_BALLOT_DIR
            / f"candidate_finance_ballot_analysis_{YEAR}.csv"
        ),
        "correlations_output": (
            BALLOT_SUPPORT_DIR / f"finance_ballot_correlations_{YEAR}.csv"
        ),
        "regressions_output": (
            BALLOT_SUPPORT_DIR
            / f"finance_ballot_univariate_regressions_{YEAR}.csv"
        ),
    },
    "spending": {
        "profiles_path": (
            PROCESSED
            / "spending"
            / str(YEAR)
            / "candidate_spending_profiles_long.csv"
        ),
        "summary_path": (
            PROCESSED
            / "spending"
            / str(YEAR)
            / "candidate_spending_summary.csv"
        ),
        "bin_column": "expenditure_bin",
        "amount_column": "spending_amount",
        "count_column": "spending_count",
        "amount_share_column": "spending_amount_share",
        "count_share_column": "spending_count_share",
        "count_label": "expenditure",
        "total_amount_column": "total_spending",
        "total_count_column": "expenditure_count",
        "average_column": "average_expenditure",
        "median_column": "median_expenditure",
        "analysis_output": (
            FINANCE_VS_BALLOT_DIR
            / f"candidate_spending_ballot_analysis_{YEAR}.csv"
        ),
        "correlations_output": (
            BALLOT_SUPPORT_DIR / f"spending_ballot_correlations_{YEAR}.csv"
        ),
        "regressions_output": (
            BALLOT_SUPPORT_DIR
            / f"spending_ballot_univariate_regressions_{YEAR}.csv"
        ),
    },
}


def pivot_bins(
    profiles,
    bin_column,
    amount_column,
    count_column,
    amount_share_column,
    count_share_column,
    count_label,
):
    """Turn one row per (candidate, bin) into one row per candidate.

    Keeps both the raw amount/count per bin (for bar charts) and the
    share columns (for correlations/regressions).
    """

    source_columns = [
        amount_column,
        count_column,
        amount_share_column,
        count_share_column,
    ]

    bin_tables = []

    for bin_name in BIN_LABELS:
        suffix = bin_name.lower()

        one_bin = (
            profiles[profiles[bin_column].eq(bin_name)][
                JOIN_KEYS + source_columns
            ]
            .rename(
                columns={
                    amount_column: f"amount_{suffix}",
                    count_column: f"{count_label}_count_{suffix}",
                    amount_share_column: f"amount_share_{suffix}",
                    count_share_column: f"{count_label}_share_{suffix}",
                }
            )
        )

        bin_tables.append(one_bin)

    wide = bin_tables[0]

    for one_bin in bin_tables[1:]:
        wide = wide.merge(one_bin, on=JOIN_KEYS, how="outer")

    bin_columns = [
        column for column in wide.columns if column not in JOIN_KEYS
    ]

    wide[bin_columns] = wide[bin_columns].fillna(0.0)

    share_columns = [
        column
        for column in bin_columns
        if column.startswith("amount_share_")
        or column.startswith(f"{count_label}_share_")
    ]

    return wide, bin_columns, share_columns


def build_domain_table(support, config):
    """Merge one finance domain's aggregates with ballot support."""

    profiles = pd.read_csv(config["profiles_path"], low_memory=False)
    summary = pd.read_csv(config["summary_path"], low_memory=False)

    totals_columns = [
        config["total_amount_column"],
        config["total_count_column"],
        config["average_column"],
        config["median_column"],
    ]

    features = summary[JOIN_KEYS + totals_columns].copy()

    bin_wide, bin_columns, share_columns = pivot_bins(
        profiles,
        bin_column=config["bin_column"],
        amount_column=config["amount_column"],
        count_column=config["count_column"],
        amount_share_column=config["amount_share_column"],
        count_share_column=config["count_share_column"],
        count_label=config["count_label"],
    )

    features = features.merge(
        bin_wide,
        on=JOIN_KEYS,
        how="left",
        validate="one_to_one",
    )

    analysis = support.merge(
        features,
        on=JOIN_KEYS,
        how="inner",
        validate="one_to_one",
    )

    return analysis, totals_columns, share_columns


def run_correlations(analysis, predictors, family_lookup):
    """Pooled + per-district Pearson/Spearman correlations."""

    pooled = calculate_correlations(
        analysis,
        x_variables=predictors,
        outcomes=OUTCOMES,
        feature_family=family_lookup,
    )

    pooled.insert(0, "district", None)
    pooled.insert(0, "scope", "all_districts")

    by_district = calculate_correlations_by_district(
        analysis,
        x_variables=predictors,
        outcomes=OUTCOMES,
        feature_family=family_lookup,
        min_n=8,
    )

    if by_district.empty:
        return pooled.rename(columns={"feature": "predictor"})

    by_district.insert(0, "scope", "district")

    combined = pd.concat([pooled, by_district], ignore_index=True, sort=False)

    return combined.rename(columns={"feature": "predictor"})


def run_univariate_regressions(analysis, predictors):
    """log1p(predictor) vs. outcome, pooled and per district."""

    rows = []

    scopes = [("all_districts", None, analysis)]

    for district in sorted(analysis["district"].dropna().unique()):
        scopes.append(
            (
                "district",
                district,
                analysis[analysis["district"].eq(district)],
            )
        )

    for scope, district, data in scopes:
        for outcome in OUTCOMES:
            for predictor in predictors:
                pair = data[[predictor, outcome]].dropna()

                if len(pair) < 3:
                    continue

                x = np.log1p(pair[predictor].to_numpy(dtype=float))
                y = pair[outcome].to_numpy(dtype=float)

                if np.unique(x).size < 2 or np.unique(y).size < 2:
                    continue

                fit = linregress(x, y)

                rows.append(
                    {
                        "scope": scope,
                        "district": district,
                        "outcome": outcome,
                        "predictor": predictor,
                        "x_transform": "log1p",
                        "n": len(pair),
                        "intercept": fit.intercept,
                        "slope": fit.slope,
                        "r_squared": fit.rvalue ** 2,
                    }
                )

    return pd.DataFrame(rows)


def main(force=False):
    support = pd.read_csv(BALLOT_SUPPORT_PATH, low_memory=False)
    support = support[support["year"].eq(YEAR)].copy()

    for domain, config in DOMAINS.items():
        outputs = [
            config["analysis_output"],
            config["correlations_output"],
            config["regressions_output"],
        ]

        if all(path.exists() for path in outputs) and not force:
            print(f"SKIP  {domain} ballot analysis already exists for {YEAR}")
            continue

        analysis, totals_columns, share_columns = build_domain_table(
            support,
            config,
        )

        family_lookup = {column: "totals" for column in totals_columns}
        family_lookup.update(
            {column: "bin_shares" for column in share_columns}
        )

        correlation_predictors = totals_columns + share_columns

        correlations = run_correlations(
            analysis,
            correlation_predictors,
            family_lookup,
        )

        regressions = run_univariate_regressions(analysis, totals_columns)

        config["analysis_output"].parent.mkdir(parents=True, exist_ok=True)

        analysis.to_csv(config["analysis_output"], index=False)
        correlations.to_csv(config["correlations_output"], index=False)
        regressions.to_csv(config["regressions_output"], index=False)

        print(
            f"SAVED {config['analysis_output']} "
            f"({len(analysis)} candidates)"
        )
        print(
            f"SAVED {config['correlations_output']} "
            f"({len(correlations)} rows)"
        )
        print(
            f"SAVED {config['regressions_output']} "
            f"({len(regressions)} rows)"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    main(force=args.force)

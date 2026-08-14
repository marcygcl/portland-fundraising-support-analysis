"""Detail spending by ORESTAR purpose code, merged with 2024 ballot support.

Big idea
--------
The existing spending bins (Micro..Mega) describe transaction SIZE, not
WHY the money was spent. ORESTAR expenditures also carry a `purpose_codes`
field -- often several codes per transaction, separated by ";" -- that has
never been aggregated anywhere in this repo. This script builds that.

This is a detail table, not a rollup: one row per
(candidate, district, purpose_code), not one row per candidate.

Multi-code transactions
------------------------
A transaction with two purpose codes counts its full amount toward BOTH
codes, by design. Purpose-code shares can therefore sum to more than a
candidate's true total spending -- that's expected, so each purpose stays
an independently comparable share of what the candidate spent. Rows with
no purpose code at all are kept as "Unspecified" so the coded total can be
compared against real total spending.

2024 only
---------
Ballot support (mentions, first_place_votes) only exists for 2024 -- the
2026 election hasn't happened yet.

Output location
----------------
This is a reusable candidate x purpose-code table (finance merged with
ballot support), so it is saved under
`data/processed/finance_vs_ballot_support/`, not `data/processed/ballot_support/`.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from helpers.paths import PROCESSED, orestar_transactions_path

YEAR = 2024
CONTEST = "city_council"

UNSPECIFIED_LABEL = "Unspecified"

JOIN_KEYS = ["year", "district", "candidate_key"]

TRANSACTIONS_PATH = orestar_transactions_path(YEAR, CONTEST)

CROSSWALK_PATH = (
    PROCESSED / "candidates" / f"candidate_source_crosswalk_{YEAR}.csv"
)

SPENDING_SUMMARY_PATH = (
    PROCESSED
    / "spending"
    / str(YEAR)
    / CONTEST
    / "orestar_candidate_spending_summary.csv"
)

BALLOT_SUPPORT_PATH = (
    PROCESSED
    / "ballot_support"
    / str(YEAR)
    / f"candidate_ballot_support_{YEAR}.csv"
)

OUTPUT_PATH = (
    PROCESSED
    / "finance_vs_ballot_support"
    / str(YEAR)
    / f"spending_purpose_ballot_detail_{YEAR}.csv"
)


def to_bool(series):
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)

    return (
        series.astype("string")
        .str.strip()
        .str.lower()
        .isin(["true", "1", "yes"])
    )


def load_expenditures():
    """Keep positive reported expenditures, same filter as notebook 04."""

    transactions = pd.read_csv(TRANSACTIONS_PATH, low_memory=False)

    transactions["reported_expenditure_amount"] = pd.to_numeric(
        transactions["reported_expenditure_amount"],
        errors="coerce",
    )

    spending = transactions.loc[
        to_bool(transactions["is_reported_expenditure"])
        & transactions["reported_expenditure_amount"].notna()
        & transactions["reported_expenditure_amount"].gt(0)
    ].copy()

    spending["amount"] = spending["reported_expenditure_amount"]

    spending["source_candidate_name"] = (
        spending["source_file_stem"].astype("string").str.strip()
    )

    return spending


def attach_candidate_key(spending):
    """Same crosswalk join notebook 04 uses to get candidate_key."""

    crosswalk = pd.read_csv(CROSSWALK_PATH, low_memory=False)

    matched = (
        crosswalk.loc[
            crosswalk["source"].eq("orestar")
            & crosswalk["classification"].eq("match"),
            [
                "year",
                "district",
                "source_candidate_name",
                "suggested_candidate",
                "suggested_candidate_key",
            ],
        ]
        .rename(
            columns={
                "suggested_candidate": "canonical_candidate",
                "suggested_candidate_key": "candidate_key",
            }
        )
        .drop_duplicates()
    )

    out = spending.merge(
        matched,
        on=["year", "district", "source_candidate_name"],
        how="left",
        validate="many_to_one",
    )

    matched_count = out["candidate_key"].notna().sum()

    print(
        "Expenditures matched to an official candidate: "
        f"{matched_count:,} / {len(out):,}"
    )

    return out.loc[out["candidate_key"].notna()].copy()


def explode_purpose_codes(spending):
    """One row per (transaction, purpose_code); untagged rows -> Unspecified."""

    spending = spending.copy()

    codes = spending["purpose_codes"].astype("string").str.strip()
    codes = codes.replace("", pd.NA).fillna(UNSPECIFIED_LABEL)

    spending["purpose_code"] = codes.str.split(";").apply(
        lambda parts: [part.strip() for part in parts if part.strip()]
    )

    return spending.explode("purpose_code", ignore_index=True)


def build_detail(exploded):
    return (
        exploded.groupby(
            JOIN_KEYS + ["canonical_candidate", "purpose_code"],
            as_index=False,
        )
        .agg(
            purpose_amount=("amount", "sum"),
            purpose_transaction_count=("amount", "size"),
        )
    )


def main():
    spending = load_expenditures()
    spending = attach_candidate_key(spending)
    exploded = explode_purpose_codes(spending)
    detail = build_detail(exploded)

    spending_summary = pd.read_csv(SPENDING_SUMMARY_PATH, low_memory=False)[
        JOIN_KEYS + ["total_spending", "expenditure_count"]
    ]
    spending_summary = spending_summary[
        spending_summary["candidate_key"].notna()
    ]

    detail = detail.merge(
        spending_summary,
        on=JOIN_KEYS,
        how="left",
        validate="many_to_one",
    )

    detail["purpose_amount_share"] = np.where(
        detail["total_spending"].gt(0),
        detail["purpose_amount"] / detail["total_spending"],
        np.nan,
    )

    support = pd.read_csv(BALLOT_SUPPORT_PATH, low_memory=False)
    support = support[support["year"].eq(YEAR)][
        JOIN_KEYS
        + [
            "mentions",
            "mention_share",
            "first_place_votes",
            "first_place_share",
        ]
    ]

    detail = detail.merge(
        support,
        on=JOIN_KEYS,
        how="inner",
        validate="many_to_one",
    )

    detail = (
        detail.sort_values(["district", "canonical_candidate", "purpose_code"])
        .reset_index(drop=True)
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    detail.to_csv(OUTPUT_PATH, index=False)

    print(
        f"SAVED {OUTPUT_PATH} "
        f"({len(detail)} rows, "
        f"{detail['candidate_key'].nunique()} candidates, "
        f"{detail['purpose_code'].nunique()} purpose codes)"
    )


if __name__ == "__main__":
    main()

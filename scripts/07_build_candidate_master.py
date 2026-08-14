"""Build the Portland City Council candidate master.

Big idea
--------
The official candidate page defines the candidate universe.

Other sources are linked back to those official candidates.

Workflow
--------
1. load expected sources;
2. prepare official candidates;
3. build the source crosswalk;
4. add source coverage;
5. create the human-review queue;
6. save master + crosswalk + coverage summary.

Only confirmed `match` rows count as source coverage.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from helpers.linkage import load_linkage_decisions
from helpers.master_builder import (
    add_coverage_summary_columns,
    add_filing_fields,
    add_source_coverage,
    build_crosswalk,
    load_all_sources,
    prepare_official_candidates,
)
from helpers.master_sources import canonical_source
from helpers.paths import PROCESSED


def main(year, force=False):
    output_dir = PROCESSED / "candidates"

    master_output = output_dir / f"candidate_master_{year}.csv"
    crosswalk_output = (
        output_dir / f"candidate_source_crosswalk_{year}.csv"
    )
    review_output = output_dir / f"match_review_{year}.csv"
    coverage_output = output_dir / f"coverage_summary_{year}.csv"

    outputs = [
        master_output,
        crosswalk_output,
        review_output,
        coverage_output,
    ]

    if all(path.exists() for path in outputs) and not force:
        print(f"SKIP  candidate master already exists for {year}")
        return

    # 1. Load candidate-level sources.
    loaded = load_all_sources(year)

    official_source = canonical_source(year)
    official_data, _ = loaded.get(
        official_source,
        (None, None),
    )

    if official_data is None:
        raise FileNotFoundError(
            "Official candidate source is required before building "
            f"the master: {official_source}"
        )

    # 2. Prepare the official candidate universe.
    candidates = prepare_official_candidates(
        official_data,
        year,
    )

    # 3. Link every other source to official candidates.
    decisions = load_linkage_decisions()

    crosswalk = build_crosswalk(
        loaded_sources=loaded,
        candidates=candidates,
        decisions=decisions,
        year=year,
    )

    # 4. Build the candidate master.
    master = add_source_coverage(
        candidates,
        crosswalk,
        year,
    )
    master = add_filing_fields(
        master,
        official_data,
    )
    master = add_coverage_summary_columns(
        master,
        year,
    )

    master = (
        master
        .sort_values(["district", "candidate"])
        .reset_index(drop=True)
    )

    # 5. Create a review queue for uncertain linkages.
    review = crosswalk.loc[
        crosswalk["needs_review"]
    ].copy()

    review["review_decision"] = ""
    review["review_canonical_candidate_name"] = ""
    review["review_notes"] = ""

    # 6. Small district-level coverage summary.
    coverage_summary = (
        master.groupby("district", as_index=False)
        .agg(
            candidates=("candidate", "size"),
            candidates_with_all_expected_sources=(
                "all_expected_sources",
                "sum",
            ),
            average_source_count=("source_count", "mean"),
        )
    )

    # 7. Save.
    output_dir.mkdir(parents=True, exist_ok=True)

    master.to_csv(master_output, index=False)
    crosswalk.to_csv(crosswalk_output, index=False)
    review.to_csv(review_output, index=False)
    coverage_summary.to_csv(coverage_output, index=False)

    print(f"SAVED {master_output}")
    print(f"SAVED {crosswalk_output}")
    print(f"SAVED {review_output}")
    print(f"SAVED {coverage_output}")
    print(f"Official candidates: {len(master)}")
    print(f"Rows requiring linkage review: {len(review)}")

    if len(review):
        print("\nReview workflow:")
        print(f"1. Inspect {review_output}")
        print("2. Add decisions to config/linkage_decisions.csv")
        print("3. Rerun this script with --force")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    main(year=args.year, force=args.force)

"""Build the candidate master using explicit record linkage.

Candidate universe:
    official Portland candidate page (`candidate_filings`)

Other sources:
    report2025, Portland contributions, ORESTAR, and future registered sources

Workflow:
1. load official candidates;
2. block source/canonical pairs by year + district;
3. exact normalized match where possible;
4. otherwise calculate Jaro-Winkler name similarity;
5. classify match / maybe_match / non_match;
6. apply persistent human-reviewed overrides from
   config/linkage_decisions.csv;
7. create source crosswalk, review queue, and candidate master.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import argparse

import pandas as pd

from helpers.linkage import (
    MATCH,
    canonical_candidate_key,
    link_source_record,
    load_linkage_decisions,
    normalize_name,
)
from helpers.master_sources import (
    SOURCE_SPECS,
    canonical_source,
    expected_sources,
    resolve_source_path,
)
from helpers.paths import PROCESSED


def load_source(source_name, *, year):
    specification = SOURCE_SPECS[source_name]
    path = resolve_source_path(source_name, year)

    if path is None:
        return None, None

    frame = pd.read_csv(path, low_memory=False)

    if (
        specification.year_column
        and specification.year_column in frame.columns
    ):
        frame = frame.loc[
            pd.to_numeric(
                frame[specification.year_column],
                errors="coerce",
            ).eq(year)
        ].copy()

    if "district" not in frame.columns:
        raise ValueError(
            f"{source_name} candidate index needs a district column."
        )

    frame["district"] = pd.to_numeric(
        frame["district"],
        errors="coerce",
    )
    frame = frame.loc[frame["district"].notna()].copy()
    frame["district"] = frame["district"].astype(int)

    return frame, path


def prepare_canonical_candidates(frame, *, year):
    specification = SOURCE_SPECS[canonical_source(year)]
    candidate_column = specification.candidate_column

    required = {"district", candidate_column}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(
            f"Canonical candidate source is missing fields: {sorted(missing)}"
        )

    canonical = frame.copy()
    canonical["year"] = year
    canonical["candidate"] = (
        canonical[candidate_column].astype(str).str.strip()
    )
    canonical["candidate_norm"] = canonical["candidate"].map(
        normalize_name
    )

    if "candidate_key" not in canonical.columns:
        canonical["candidate_key"] = [
            canonical_candidate_key(year, district, candidate)
            for district, candidate in zip(
                canonical["district"],
                canonical["candidate"],
            )
        ]

    canonical = (
        canonical.sort_values(["district", "candidate"])
        .drop_duplicates("candidate_key", keep="last")
        .reset_index(drop=True)
    )

    canonical["is_non_candidate_row"] = canonical[
        "candidate"
    ].str.contains(
        r"write\s*in|uncertified",
        case=False,
        regex=True,
        na=False,
    )

    return canonical


def main(*, year, force=False):
    output_dir = PROCESSED / "master"

    master_output = output_dir / f"candidate_master_{year}.csv"
    crosswalk_output = (
        output_dir / f"candidate_source_crosswalk_{year}.csv"
    )
    review_output = output_dir / f"match_review_{year}.csv"
    coverage_output = output_dir / f"coverage_summary_{year}.csv"

    if (
        master_output.exists()
        and crosswalk_output.exists()
        and review_output.exists()
        and not force
    ):
        print(f"SKIP  candidate master already exists for {year}")
        return

    expected = expected_sources(year)
    canonical_source_name = canonical_source(year)
    decisions = load_linkage_decisions()

    loaded = {}
    for source_name in expected:
        frame, path = load_source(source_name, year=year)
        loaded[source_name] = (frame, path)

        if frame is None:
            print(
                f"WARN  expected source {source_name} "
                f"is not available for {year}"
            )
        else:
            print(f"READ  {source_name}: {len(frame)} rows from {path}")

    canonical_frame, canonical_path = loaded.get(
        canonical_source_name,
        (None, None),
    )

    if canonical_frame is None:
        raise FileNotFoundError(
            f"Canonical candidate source {canonical_source_name} "
            f"is required before building the {year} master."
        )

    master = prepare_canonical_candidates(
        canonical_frame,
        year=year,
    )

    crosswalk_rows = []

    # Canonical source: direct identity.
    for row in master.itertuples(index=False):
        crosswalk_rows.append(
            {
                "year": year,
                "district": row.district,
                "source": canonical_source_name,
                "source_candidate_name": row.candidate,
                "suggested_candidate": row.candidate,
                "candidate_key": row.candidate_key,
                "name_similarity": 1.0,
                "second_best_similarity": 0.0,
                "similarity_margin": 1.0,
                "classification": MATCH,
                "match_method": "canonical_source",
                "needs_review": False,
            }
        )

    # Link each additional source to the official candidate universe.
    for source_name in expected:
        if source_name == canonical_source_name:
            continue

        frame, path = loaded[source_name]
        if frame is None:
            continue

        specification = SOURCE_SPECS[source_name]
        candidate_column = specification.candidate_column

        if candidate_column not in frame.columns:
            raise ValueError(
                f"{source_name}: missing candidate column "
                f"{candidate_column}"
            )

        # One linkage attempt per unique source label/year/district.
        unique_columns = ["district", candidate_column]
        unique_columns += [
            column
            for column in specification.alternate_name_columns
            if column in frame.columns
        ]

        source_candidates = frame[
            unique_columns
        ].drop_duplicates()

        for row in source_candidates.itertuples(index=False):
            source_candidate_name = getattr(
                row,
                candidate_column,
            )

            if (
                pd.isna(source_candidate_name)
                or not str(source_candidate_name).strip()
            ):
                continue

            alternate_names = []
            for column in specification.alternate_name_columns:
                if hasattr(row, column):
                    alternate_names.append(getattr(row, column))

            result = link_source_record(
                year=year,
                district=int(row.district),
                source=source_name,
                source_candidate_name=str(source_candidate_name).strip(),
                alternate_source_names=alternate_names,
                canonical_candidates=master,
                decisions=decisions,
            )

            crosswalk_rows.append(
                {
                    "year": year,
                    "district": int(row.district),
                    "source": source_name,
                    "source_candidate_name": result.source_candidate_name,
                    "suggested_candidate": result.suggested_candidate,
                    "candidate_key": (
                        result.suggested_candidate_key
                        if result.classification == MATCH
                        else pd.NA
                    ),
                    "suggested_candidate_key": (
                        result.suggested_candidate_key
                    ),
                    "name_similarity": result.name_similarity,
                    "second_best_similarity": (
                        result.second_best_similarity
                    ),
                    "similarity_margin": result.similarity_margin,
                    "classification": result.classification,
                    "match_method": result.match_method,
                    "needs_review": result.needs_review,
                }
            )

    crosswalk = pd.DataFrame(crosswalk_rows)

    # Only confirmed MATCH rows contribute to source-presence columns.
    for source_name in expected:
        confirmed = crosswalk.loc[
            crosswalk["source"].eq(source_name)
            & crosswalk["classification"].eq(MATCH)
            & crosswalk["candidate_key"].notna()
        ].copy()

        if confirmed.empty:
            master[f"has_{source_name}"] = False
            master[f"name_{source_name}"] = pd.NA
            master[f"match_method_{source_name}"] = pd.NA
            continue

        collapsed = (
            confirmed.groupby("candidate_key", as_index=False)
            .agg(
                source_name=(
                    "source_candidate_name",
                    lambda values: " | ".join(
                        sorted(
                            {
                                str(value)
                                for value in values
                                if pd.notna(value)
                            }
                        )
                    ),
                ),
                match_method=(
                    "match_method",
                    lambda values: " | ".join(
                        sorted(
                            {
                                str(value)
                                for value in values
                                if pd.notna(value)
                            }
                        )
                    ),
                ),
            )
        )

        collapsed[f"has_{source_name}"] = True
        collapsed = collapsed.rename(
            columns={
                "source_name": f"name_{source_name}",
                "match_method": f"match_method_{source_name}",
            }
        )

        master = master.merge(
            collapsed,
            on="candidate_key",
            how="left",
        )
        master[f"has_{source_name}"] = (
            master[f"has_{source_name}"].fillna(False)
        )

    # The candidate-filings enriched index may already contain qualitative data.
    qualitative_columns = [
        column
        for column in [
            "candidate_key",
            "filing_status",
            "filing_date",
            "campaign_website",
            "occupation",
            "occupational_background",
            "prior_govt_experience",
            "public_funding_program",
            "needs_manual_review",
        ]
        if column in canonical_frame.columns
    ]

    if qualitative_columns:
        qualitative = canonical_frame[
            qualitative_columns
        ].drop_duplicates("candidate_key")

        duplicate_columns = [
            column
            for column in qualitative.columns
            if column != "candidate_key"
            and column in master.columns
        ]
        if duplicate_columns:
            master = master.drop(columns=duplicate_columns)

        master = master.merge(
            qualitative,
            on="candidate_key",
            how="left",
        )

    has_columns = [
        f"has_{source_name}"
        for source_name in expected
    ]
    for column in has_columns:
        if column not in master.columns:
            master[column] = False

    master["source_count"] = (
        master[has_columns].astype(int).sum(axis=1)
    )
    master["expected_source_count"] = len(expected)
    master["all_expected_sources"] = (
        master["source_count"]
        == master["expected_source_count"]
    )

    def coverage_status(row):
        present = [
            source_name
            for source_name in expected
            if bool(row[f"has_{source_name}"])
        ]
        return "+".join(present) if present else "no_source"

    master["coverage_status"] = master.apply(
        coverage_status,
        axis=1,
    )

    master = master.sort_values(
        ["district", "candidate"]
    ).reset_index(drop=True)

    review = crosswalk.loc[
        crosswalk["needs_review"]
    ].copy()

    # Blank columns invite persistent review decisions to be copied into
    # config/linkage_decisions.csv rather than editing generated data.
    review["review_decision"] = ""
    review["review_canonical_candidate_name"] = ""
    review["review_notes"] = ""

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
        print(
            "\nReview workflow:\n"
            f"1. Inspect {review_output}\n"
            "2. Add confirmed decisions to config/linkage_decisions.csv\n"
            "3. Rerun this script with --force"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    main(year=args.year, force=args.force)

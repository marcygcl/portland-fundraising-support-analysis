"""Small building blocks for the City Council candidate master.

This helper keeps scripts/07_build_candidate_master.py short and readable.

It does four things:
- load registered candidate-level sources;
- prepare the official candidate universe;
- build source-to-candidate linkage rows;
- add source coverage to the final master.
"""

import pandas as pd

from .linkage import (
    MATCH,
    canonical_candidate_key,
    link_source_record,
    normalize_name,
)
from .master_sources import (
    SOURCE_SPECS,
    canonical_source,
    expected_sources,
    resolve_source_path,
)


def load_source(source_name, year):
    """Load one registered source and standardize district/year."""
    spec = SOURCE_SPECS[source_name]
    path = resolve_source_path(source_name, year)

    if path is None:
        return None, None

    data = pd.read_csv(path, low_memory=False)

    if spec.year_column and spec.year_column in data.columns:
        source_year = pd.to_numeric(
            data[spec.year_column],
            errors="coerce",
        )
        data = data.loc[source_year.eq(year)].copy()

    if "district" not in data.columns:
        raise ValueError(
            f"{source_name} candidate index needs a district column."
        )

    data["district"] = pd.to_numeric(
        data["district"],
        errors="coerce",
    )
    data = data.loc[data["district"].notna()].copy()
    data["district"] = data["district"].astype(int)

    return data, path


def load_all_sources(year):
    """Load every source expected for one election year."""
    loaded = {}

    for source_name in expected_sources(year):
        data, path = load_source(source_name, year)
        loaded[source_name] = (data, path)

        if data is None:
            print(
                f"WARN  {source_name} is not available for {year}"
            )
        else:
            print(
                f"READ  {source_name}: {len(data):,} rows from {path}"
            )

    return loaded


def prepare_official_candidates(data, year):
    """Create the canonical one-row-per-candidate universe."""
    official_source = canonical_source(year)
    spec = SOURCE_SPECS[official_source]
    candidate_column = spec.candidate_column

    required = {"district", candidate_column}
    missing = required - set(data.columns)

    if missing:
        raise ValueError(
            "Official candidate source is missing fields: "
            f"{sorted(missing)}"
        )

    candidates = data.copy()
    candidates["year"] = year
    candidates["candidate"] = (
        candidates[candidate_column].astype(str).str.strip()
    )
    candidates["candidate_norm"] = (
        candidates["candidate"].map(normalize_name)
    )

    if "candidate_key" not in candidates.columns:
        candidates["candidate_key"] = [
            canonical_candidate_key(year, district, candidate)
            for district, candidate in zip(
                candidates["district"],
                candidates["candidate"],
            )
        ]

    candidates = (
        candidates
        .sort_values(["district", "candidate"])
        .drop_duplicates("candidate_key", keep="last")
        .reset_index(drop=True)
    )

    candidates["is_non_candidate_row"] = (
        candidates["candidate"]
        .str.contains(
            r"write\s*in|uncertified",
            case=False,
            regex=True,
            na=False,
        )
    )

    return candidates


def canonical_crosswalk_rows(candidates, year, source_name):
    """Direct identity rows for the official candidate source."""
    rows = []

    for candidate in candidates.itertuples(index=False):
        rows.append(
            {
                "year": year,
                "district": candidate.district,
                "source": source_name,
                "source_candidate_name": candidate.candidate,
                "suggested_candidate": candidate.candidate,
                "candidate_key": candidate.candidate_key,
                "suggested_candidate_key": candidate.candidate_key,
                "name_similarity": 1.0,
                "second_best_similarity": 0.0,
                "similarity_margin": 1.0,
                "classification": MATCH,
                "match_method": "canonical_source",
                "needs_review": False,
            }
        )

    return rows


def source_crosswalk_rows(
    source_name,
    source_data,
    candidates,
    decisions,
    year,
):
    """Link unique labels from one non-canonical source."""
    spec = SOURCE_SPECS[source_name]
    candidate_column = spec.candidate_column

    if candidate_column not in source_data.columns:
        raise ValueError(
            f"{source_name}: missing candidate column {candidate_column}"
        )

    columns = ["district", candidate_column]

    for alternate_column in spec.alternate_name_columns:
        if alternate_column in source_data.columns:
            columns.append(alternate_column)

    source_candidates = source_data[columns].drop_duplicates()
    rows = []

    for source_row in source_candidates.itertuples(index=False):
        source_name_value = getattr(source_row, candidate_column)

        if pd.isna(source_name_value):
            continue

        source_name_value = str(source_name_value).strip()

        if not source_name_value:
            continue

        alternate_names = [
            getattr(source_row, column)
            for column in spec.alternate_name_columns
            if hasattr(source_row, column)
        ]

        result = link_source_record(
            year=year,
            district=int(source_row.district),
            source=source_name,
            source_candidate_name=source_name_value,
            alternate_source_names=alternate_names,
            canonical_candidates=candidates,
            decisions=decisions,
        )

        confirmed_key = (
            result.suggested_candidate_key
            if result.classification == MATCH
            else pd.NA
        )

        rows.append(
            {
                "year": year,
                "district": int(source_row.district),
                "source": source_name,
                "source_candidate_name": result.source_candidate_name,
                "suggested_candidate": result.suggested_candidate,
                "candidate_key": confirmed_key,
                "suggested_candidate_key":
                    result.suggested_candidate_key,
                "name_similarity": result.name_similarity,
                "second_best_similarity":
                    result.second_best_similarity,
                "similarity_margin": result.similarity_margin,
                "classification": result.classification,
                "match_method": result.match_method,
                "needs_review": result.needs_review,
            }
        )

    return rows


def build_crosswalk(
    loaded_sources,
    candidates,
    decisions,
    year,
):
    """Build linkage rows for all expected sources."""
    official_source = canonical_source(year)

    rows = canonical_crosswalk_rows(
        candidates,
        year,
        official_source,
    )

    for source_name in expected_sources(year):
        if source_name == official_source:
            continue

        source_data, _ = loaded_sources[source_name]

        if source_data is None:
            continue

        rows.extend(
            source_crosswalk_rows(
                source_name=source_name,
                source_data=source_data,
                candidates=candidates,
                decisions=decisions,
                year=year,
            )
        )

    return pd.DataFrame(rows)


def add_source_coverage(candidates, crosswalk, year):
    """Add source-presence/name/match-method columns."""
    master = candidates.copy()

    for source_name in expected_sources(year):
        confirmed = crosswalk.loc[
            crosswalk["source"].eq(source_name)
            & crosswalk["classification"].eq(MATCH)
            & crosswalk["candidate_key"].notna()
        ].copy()

        has_column = f"has_{source_name}"
        name_column = f"name_{source_name}"
        method_column = f"match_method_{source_name}"

        if confirmed.empty:
            master[has_column] = False
            master[name_column] = pd.NA
            master[method_column] = pd.NA
            continue

        collapsed_rows = []

        for candidate_key, group in confirmed.groupby("candidate_key"):
            names = sorted(
                set(
                    group["source_candidate_name"]
                    .dropna()
                    .astype(str)
                )
            )
            methods = sorted(
                set(
                    group["match_method"]
                    .dropna()
                    .astype(str)
                )
            )

            collapsed_rows.append(
                {
                    "candidate_key": candidate_key,
                    name_column: " | ".join(names),
                    method_column: " | ".join(methods),
                    has_column: True,
                }
            )

        collapsed = pd.DataFrame(collapsed_rows)

        master = master.merge(
            collapsed,
            on="candidate_key",
            how="left",
        )
        master[has_column] = (
            master[has_column].fillna(False).astype(bool)
        )

    return master


def add_filing_fields(master, official_source_data):
    """Attach selected qualitative filing fields when available."""
    possible_columns = [
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

    available_columns = [
        column
        for column in possible_columns
        if column in official_source_data.columns
    ]

    if len(available_columns) <= 1:
        return master

    qualitative = (
        official_source_data[available_columns]
        .drop_duplicates("candidate_key")
    )

    duplicate_columns = [
        column
        for column in qualitative.columns
        if (
            column != "candidate_key"
            and column in master.columns
        )
    ]

    if duplicate_columns:
        master = master.drop(columns=duplicate_columns)

    return master.merge(
        qualitative,
        on="candidate_key",
        how="left",
    )


def add_coverage_summary_columns(master, year):
    """Add simple source-count and coverage-status columns."""
    sources = expected_sources(year)
    has_columns = []

    for source_name in sources:
        column = f"has_{source_name}"

        if column not in master.columns:
            master[column] = False

        has_columns.append(column)

    master["source_count"] = (
        master[has_columns].astype(int).sum(axis=1)
    )
    master["expected_source_count"] = len(sources)
    master["all_expected_sources"] = (
        master["source_count"]
        == master["expected_source_count"]
    )

    statuses = []

    for row in master.itertuples(index=False):
        present = [
            source_name
            for source_name in sources
            if bool(getattr(row, f"has_{source_name}"))
        ]

        statuses.append(
            "+".join(present)
            if present
            else "no_source"
        )

    master["coverage_status"] = statuses

    return master

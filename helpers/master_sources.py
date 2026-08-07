"""Registry of candidate-level sources used by the candidate master.

To add a new source later:
1. make the source pipeline create a candidate-level index;
2. register one SourceSpec here;
3. rerun scripts/07_build_candidate_master.py.

The official Portland candidate page is the canonical candidate universe.
Other sources are linked to that universe using helpers/linkage.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from .paths import ROOT


@dataclass(frozen=True)
class SourceSpec:
    name: str
    path_templates: tuple[str, ...]
    candidate_column: str
    expected_years: tuple[int, ...]
    alternate_name_columns: tuple[str, ...] = ()
    year_column: str | None = None
    canonical: bool = False


SOURCE_SPECS = {
    "candidate_filings": SourceSpec(
        name="candidate_filings",
        path_templates=(
            "data/clean/candidate_filings/{year}/candidate_index_enriched.csv",
            "data/clean/candidate_filings/{year}/candidate_index.csv",
        ),
        candidate_column="candidate",
        expected_years=(2024, 2026),
        canonical=True,
    ),
    "report2025": SourceSpec(
        name="report2025",
        path_templates=(
            "data/processed/boost/{year}/candidate_index.csv",
        ),
        candidate_column="candidate",
        expected_years=(2024,),
    ),
    "portland_contributions": SourceSpec(
        name="portland_contributions",
        path_templates=(
            "data/clean/portland_contributions/candidate_index.csv",
        ),
        candidate_column="candidate",
        expected_years=(2024, 2026),
        year_column="year",
    ),
    "orestar": SourceSpec(
        name="orestar",
        path_templates=(
            "data/clean/orestar/{year}/candidate_index.csv",
        ),
        candidate_column="source_candidate_name",
        alternate_name_columns=("filer",),
        expected_years=(2024, 2026),
    ),
}


def expected_sources(year: int) -> list[str]:
    return [
        source_name
        for source_name, specification in SOURCE_SPECS.items()
        if year in specification.expected_years
    ]


def canonical_source(year: int) -> str:
    candidates = [
        source_name
        for source_name, specification in SOURCE_SPECS.items()
        if specification.canonical
        and year in specification.expected_years
    ]

    if len(candidates) != 1:
        raise ValueError(
            f"Expected exactly one canonical source for {year}; found {candidates}"
        )

    return candidates[0]


def resolve_source_path(source_name: str, year: int):
    specification = SOURCE_SPECS[source_name]

    for template in specification.path_templates:
        path = ROOT / template.format(year=year)
        if path.exists():
            return path

    return None

"""Registry of candidate-level sources used by the City Council master.

To add a new source later:
1. make that source produce a candidate-level CSV;
2. register it below;
3. rerun scripts/07_build_candidate_master.py.
"""

from dataclasses import dataclass

from .paths import ROOT


@dataclass(frozen=True)
class SourceSpec:
    name: str
    path_templates: tuple
    candidate_column: str
    expected_years: tuple
    alternate_name_columns: tuple = ()
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
        path_templates=("data/processed/boost/{year}/candidate_index.csv",),
        candidate_column="candidate",
        expected_years=(2024,),
    ),
    "portland_contributions": SourceSpec(
        name="portland_contributions",
        path_templates=("data/clean/portland_contributions/candidate_index.csv",),
        candidate_column="candidate",
        expected_years=(2024, 2026),
        year_column="year",
    ),

    # The master is specifically a PORTLAND CITY COUNCIL master.
    # ORESTAR outputs are now separated by contest type.
    "orestar": SourceSpec(
        name="orestar",
        path_templates=(
            "data/clean/orestar/{year}/city_council/candidate_index.csv",
        ),
        candidate_column="source_candidate_name",
        alternate_name_columns=("filer",),
        expected_years=(2024, 2026),
    ),
}


def expected_sources(year):
    """Return source names expected for one election year."""
    return [
        name
        for name, spec in SOURCE_SPECS.items()
        if year in spec.expected_years
    ]


def canonical_source(year):
    """Return the one source that defines the official candidate universe."""
    matches = [
        name
        for name, spec in SOURCE_SPECS.items()
        if spec.canonical and year in spec.expected_years
    ]

    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one canonical source for {year}; found {matches}"
        )

    return matches[0]


def resolve_source_path(source_name, year):
    """Return the first configured path that exists."""
    spec = SOURCE_SPECS[source_name]

    for template in spec.path_templates:
        path = ROOT / template.format(year=year)

        if path.exists():
            return path

    return None

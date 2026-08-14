#!/usr/bin/env python3
"""Master switchboard for infrequent data-generation stages.

Edit RUN and YEARS only.

Every stage skips existing outputs unless FORCE = True.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent

RUN = {
    "download_portland_contributions": False,
    "clean_portland_contributions": False,
    "build_boost_matrices": False,
    "clean_orestar": False,
    "scrape_candidate_filings": True,
    "extract_candidate_filings": True,
    "build_candidate_master": True,
    "initialize_candidate_profiles": False,
    "build_finance_ballot_analysis": False,
    "build_spending_purpose_ballot_analysis": False,
}

YEARS = {
    "build_boost_matrices": [2024],
    "clean_orestar": [2024, 2026],
    "scrape_candidate_filings": [2024, 2026],
    "extract_candidate_filings": [2024, 2026],
    "build_candidate_master": [2024, 2026],
    "initialize_candidate_profiles": [2024, 2026],
}

# Set True only when intentionally rebuilding generated outputs.
FORCE = False


STAGES = [
    (
        "download_portland_contributions",
        "01_download_portland_contributions.py",
        False,
    ),
    (
        "clean_portland_contributions",
        "02_clean_portland_contributions.py",
        False,
    ),
    (
        "build_boost_matrices",
        "03_build_boost_matrices.py",
        True,
    ),
    (
        "clean_orestar",
        "04_clean_orestar.py",
        True,
    ),
    (
        "scrape_candidate_filings",
        "05_scrape_candidate_filings.py",
        True,
    ),
    (
        "extract_candidate_filings",
        "06_extract_candidate_filings.py",
        True,
    ),
    (
        "build_candidate_master",
        "07_build_candidate_master.py",
        True,
    ),
    (
        "initialize_candidate_profiles",
        "08_initialize_candidate_profiles.py",
        True,
    ),
    (
        "build_finance_ballot_analysis",
        "09_build_finance_ballot_analysis.py",
        False,
    ),
    (
        "build_spending_purpose_ballot_analysis",
        "10_build_spending_purpose_ballot_analysis.py",
        False,
    ),
]


def run_stage(name, script_name, year=None):
    command = [
        sys.executable,
        str(ROOT / "scripts" / script_name),
    ]

    if year is not None:
        command.extend(["--year", str(year)])

    # Candidate profile initialization never overwrites existing Markdown
    # files, so --force is not relevant there.
    if FORCE and name != "initialize_candidate_profiles":
        command.append("--force")

    label = f"{name} [{year}]" if year is not None else name

    print()
    print("=" * 72)
    print(f"RUN   {label}")
    print("=" * 72)

    subprocess.run(command, cwd=ROOT, check=True)


def main():
    for name, script_name, uses_year in STAGES:
        if not RUN.get(name, False):
            print(f"OFF   {name}")
            continue

        if uses_year:
            for year in YEARS.get(name, []):
                run_stage(name, script_name, year)
        else:
            run_stage(name, script_name)

    print()
    print("Pipeline finished.")


if __name__ == "__main__":
    main()

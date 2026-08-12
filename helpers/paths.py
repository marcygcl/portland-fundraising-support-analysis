"""Canonical repository paths.

Keeping common paths here prevents different scripts from saving the same
kind of data in slightly different places.
"""

from pathlib import Path


def find_repo_root(start=None):
    """Walk upward until we find the project root."""
    current = Path(start or Path.cwd()).resolve()

    for candidate in [current, *current.parents]:
        has_pipeline = (candidate / "run_pipeline.py").exists()
        has_data = (candidate / "data").is_dir()

        if has_pipeline and has_data:
            return candidate

    raise FileNotFoundError(
        f"Could not locate the repository root from {current}"
    )


ROOT = find_repo_root()

DATA = ROOT / "data"
RAW = DATA / "raw"
CLEAN = DATA / "clean"
PROCESSED = DATA / "processed"

CONFIG_DIR = ROOT / "config"
OUTPUTS = ROOT / "outputs"
CANDIDATE_PROFILES = ROOT / "candidate_profiles"


# ORESTAR -------------------------------------------------------------

def orestar_raw_dir():
    return RAW / "orestar"


def orestar_raw_year_dir(year):
    return orestar_raw_dir() / str(year)


def orestar_clean_dir(year, contest_type):
    return CLEAN / "orestar" / str(year) / contest_type


def orestar_transactions_path(year, contest_type):
    return orestar_clean_dir(year, contest_type) / "transactions.csv"


def orestar_candidate_index_path(year, contest_type):
    return orestar_clean_dir(year, contest_type) / "candidate_index.csv"


def orestar_file_audit_path(year, contest_type):
    return orestar_clean_dir(year, contest_type) / "file_audit.csv"


# Processed finance outputs -------------------------------------------

def fundraising_processed_dir(year, contest_type="city_council"):
    return PROCESSED / "fundraising" / str(year) / contest_type


def spending_processed_dir(year, contest_type="city_council"):
    return PROCESSED / "spending" / str(year) / contest_type

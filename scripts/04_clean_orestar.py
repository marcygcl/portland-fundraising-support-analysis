"""Clean manually downloaded ORESTAR campaign-finance workbooks.

This file is intentionally an orchestrator.

Technical Excel parsing lives in `helpers/orestar.py`, so the workflow here
stays simple:

1. choose years;
2. find workbooks;
3. identify supported contests;
4. hash + read files;
5. build source audit tables;
6. save each contest separately.

Outputs
-------
data/clean/orestar/<year>/<contest_type>/
    transactions.csv
    candidate_index.csv
    file_audit.csv

Fundraising/spending profiles are built later in notebooks.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from helpers.orestar import (
    build_candidate_index,
    build_file_audit,
    infer_contest_from_path,
    read_workbook,
    sha256_hash,
)
from helpers.paths import (
    orestar_candidate_index_path,
    orestar_clean_dir,
    orestar_file_audit_path,
    orestar_raw_dir,
    orestar_raw_year_dir,
    orestar_transactions_path,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Clean ORESTAR workbooks."
    )

    year_group = parser.add_mutually_exclusive_group(required=True)

    year_group.add_argument(
        "--year",
        type=int,
        nargs="+",
        help="One or more years, e.g. --year 2024 2026",
    )
    year_group.add_argument(
        "--all-years",
        action="store_true",
        help="Process every numeric folder under data/raw/orestar/.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing clean outputs.",
    )

    return parser.parse_args()


def discover_years():
    """Find numeric year folders under data/raw/orestar/."""
    root = orestar_raw_dir()

    if not root.exists():
        raise FileNotFoundError(
            f"ORESTAR raw directory not found: {root}"
        )

    years = sorted(
        int(path.name)
        for path in root.iterdir()
        if path.is_dir() and path.name.isdigit()
    )

    if not years:
        raise FileNotFoundError(
            f"No numeric year folders found under {root}"
        )

    return years


def find_workbooks(year_dir):
    """Find all .xls/.xlsx files under one year folder."""
    return sorted(
        path
        for path in year_dir.rglob("*")
        if (
            path.is_file()
            and path.suffix.lower() in {".xls", ".xlsx"}
        )
    )


def save_contest(
    data,
    year,
    contest_type,
    year_hash_counts,
    force=False,
):
    """Save clean transactions, candidate index, and source audit."""
    transactions_path = orestar_transactions_path(
        year,
        contest_type,
    )
    candidate_index_path = orestar_candidate_index_path(
        year,
        contest_type,
    )
    file_audit_path = orestar_file_audit_path(
        year,
        contest_type,
    )

    outputs = [
        transactions_path,
        candidate_index_path,
        file_audit_path,
    ]

    if all(path.exists() for path in outputs) and not force:
        print(
            f"SKIP  {year} {contest_type}: outputs already exist"
        )

        return {
            "year": year,
            "contest_type": contest_type,
            "status": "skipped",
            "workbooks": np.nan,
            "rows": np.nan,
        }

    contest_data = data.loc[
        data["contest_type"].eq(contest_type)
    ].copy()

    candidate_index = build_candidate_index(contest_data)
    file_audit = build_file_audit(
        contest_data,
        year_hash_counts,
    )

    output_dir = orestar_clean_dir(year, contest_type)
    output_dir.mkdir(parents=True, exist_ok=True)

    contest_data.to_csv(transactions_path, index=False)
    candidate_index.to_csv(candidate_index_path, index=False)
    file_audit.to_csv(file_audit_path, index=False)

    print(f"SAVED {year} {contest_type}")
    print(f"      Workbooks: {len(file_audit):,}")
    print(f"      Rows: {len(contest_data):,}")
    print(
        "      Contribution rows: "
        f"{int(contest_data['is_reported_contribution'].sum()):,}"
    )
    print(
        "      Expenditure rows: "
        f"{int(contest_data['is_reported_expenditure'].sum()):,}"
    )
    print(
        "      Exact duplicate exports: "
        f"{int(file_audit['is_exact_duplicate_export'].sum()):,}"
    )

    return {
        "year": year,
        "contest_type": contest_type,
        "status": "saved",
        "workbooks": len(file_audit),
        "rows": len(contest_data),
    }


def process_year(year, force=False):
    """Clean every supported ORESTAR contest found for one year."""
    year_dir = orestar_raw_year_dir(year)

    print()
    print(f"=== ORESTAR {year} ===")

    if not year_dir.exists():
        print(f"SKIP  raw year folder not found: {year_dir}")
        return []

    workbooks = find_workbooks(year_dir)

    if not workbooks:
        print("SKIP  no Excel workbooks found")
        return []

    # 1. Keep only source folders we know how to interpret.
    supported = []

    for path in workbooks:
        try:
            contest_type, office, district = infer_contest_from_path(
                path,
                year_dir,
            )
        except ValueError:
            print(
                "SKIP  unsupported folder: "
                f"{path.relative_to(year_dir)}"
            )
            continue

        supported.append(
            {
                "path": path,
                "contest_type": contest_type,
                "office": office,
                "district": district,
            }
        )

    if not supported:
        print("SKIP  no supported ORESTAR workbooks found")
        return []

    # 2. Hash files before reading so duplicate exports remain auditable.
    workbook_hashes = {
        item["path"]: sha256_hash(item["path"])
        for item in supported
    }

    year_hash_counts = (
        pd.Series(
            list(workbook_hashes.values()),
            dtype="string",
        )
        .value_counts()
        .to_dict()
    )

    # 3. Read and standardize every workbook.
    frames = []

    for item in supported:
        path = item["path"]

        print(
            f"READ  {item['contest_type']} "
            f"D{item['district']} {path.name}"
        )

        frame = read_workbook(
            path=path,
            year=year,
            year_dir=year_dir,
            source_hash=workbook_hashes[path],
        )

        if not frame.empty:
            frames.append(frame)

    if not frames:
        print("SKIP  no transaction rows were read")
        return []

    all_data = pd.concat(
        frames,
        ignore_index=True,
        sort=False,
    )

    # 4. Save every contest found in this year.
    contest_types = sorted(
        all_data["contest_type"].dropna().unique().tolist()
    )

    return [
        save_contest(
            data=all_data,
            year=year,
            contest_type=contest_type,
            year_hash_counts=year_hash_counts,
            force=force,
        )
        for contest_type in contest_types
    ]


def main():
    args = parse_args()

    years = (
        discover_years()
        if args.all_years
        else sorted(set(args.year))
    )

    print(
        "Years to clean:",
        ", ".join(str(year) for year in years),
    )

    results = []

    for year in years:
        results.extend(
            process_year(
                year,
                force=args.force,
            )
        )

    print()
    print("=== ORESTAR CLEANING COMPLETE ===")

    if not results:
        print("No supported ORESTAR data were cleaned.")
        return

    summary = pd.DataFrame(results)

    print(
        summary[
            ["year", "contest_type", "status", "workbooks", "rows"]
        ]
        .sort_values(["year", "contest_type"])
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()

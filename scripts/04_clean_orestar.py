#!/usr/bin/env python3
"""Consolidate ORESTAR exports for one election year.

ORESTAR is kept as a source-level dataset. Final spending definitions and
categories belong in later analytical notebooks.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import argparse
import hashlib
import re

import pandas as pd

from helpers.linkage import normalize_name
from helpers.paths import CLEAN, RAW


REPORTED_EXPENDITURE_SUBTYPES = {
    "Cash Expenditure",
    "Personal Expenditure for Reimbursement",
    "Miscellaneous Other Disbursement",
}

COLUMN_MAP = {
    "Tran Id": "tran_id",
    "Original Id": "original_id",
    "Tran Date": "tran_date",
    "Tran Status": "tran_status",
    "Filer": "filer",
    "Filer Id": "filer_id",
    "Contributor/Payee": "counterparty",
    "Sub Type": "sub_type",
    "Payer of Personal Expenditure": "personal_expenditure_payer",
    "Amount": "amount",
    "Aggregate Amount": "aggregate_amount",
    "Contributor/Payee Committee ID": "counterparty_committee_id",
    "Book Type": "book_type",
    "City": "city",
    "State": "state",
    "Zip": "zip",
    "County": "county",
    "Country": "country",
    "Purpose Codes": "purpose_codes",
    "Purp Desc": "purpose_description",
    "Exp Date": "expenditure_date",
}


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_columns(frame):
    frame = frame.rename(
        columns={
            old: new
            for old, new in COLUMN_MAP.items()
            if old in frame.columns
        }
    )

    frame.columns = [
        re.sub(
            r"_+",
            "_",
            re.sub(
                r"[^a-z0-9]+",
                "_",
                str(column).lower(),
            ),
        ).strip("_")
        for column in frame.columns
    ]

    return frame


def read_workbook(path, *, year):
    match = re.fullmatch(r"d([1-4])", path.parent.name.lower())
    if not match:
        raise ValueError(f"Cannot infer district from {path}")

    frame = pd.read_excel(path, sheet_name="ORESTAR Export")
    frame = normalize_columns(frame)

    frame["year"] = year
    frame["district"] = int(match.group(1))
    frame["source_file"] = path.name
    frame["source_file_stem"] = path.stem
    frame["source_file_hash"] = file_hash(path)

    return frame


def main(*, year, force=False):
    raw_dir = RAW / "orestar" / str(year)
    output_dir = CLEAN / "orestar" / str(year)

    transactions_output = output_dir / "transactions.csv"
    candidate_index_output = output_dir / "candidate_index.csv"
    file_audit_output = output_dir / "file_audit.csv"

    if (
        transactions_output.exists()
        and candidate_index_output.exists()
        and file_audit_output.exists()
        and not force
    ):
        print(f"SKIP  clean ORESTAR outputs already exist for {year}")
        return

    workbooks = sorted(
        list(raw_dir.glob("d*/*.xls"))
        + list(raw_dir.glob("d*/*.xlsx"))
    )

    if not workbooks:
        raise FileNotFoundError(
            f"No ORESTAR workbooks found under {raw_dir}"
        )

    data = pd.concat(
        [read_workbook(path, year=year) for path in workbooks],
        ignore_index=True,
        sort=False,
    )

    for required in ["amount", "tran_date", "sub_type"]:
        if required not in data.columns:
            raise ValueError(f"ORESTAR field missing: {required}")

    data["amount"] = pd.to_numeric(data["amount"], errors="coerce")
    data["tran_date"] = pd.to_datetime(
        data["tran_date"],
        errors="coerce",
    )
    data["transaction_year"] = data["tran_date"].dt.year
    data["sub_type"] = data["sub_type"].astype(str).str.strip()

    data["is_reported_expenditure"] = data["sub_type"].isin(
        REPORTED_EXPENDITURE_SUBTYPES
    )
    data["reported_expenditure_amount"] = data["amount"].where(
        data["is_reported_expenditure"],
        0,
    )

    file_audit = (
        data[
            [
                "year",
                "district",
                "source_file",
                "source_file_stem",
                "source_file_hash",
            ]
        ]
        .drop_duplicates()
        .sort_values(["district", "source_file"])
        .reset_index(drop=True)
    )

    file_audit["same_hash_file_count"] = file_audit.groupby(
        "source_file_hash"
    )["source_file_hash"].transform("size")
    file_audit["is_exact_duplicate_export"] = (
        file_audit["same_hash_file_count"] > 1
    )

    group_columns = [
        "year",
        "district",
        "source_file_stem",
        "source_file_hash",
    ]

    data["_headline_amount"] = data["reported_expenditure_amount"]

    candidate_index = (
        data.groupby(group_columns, as_index=False)
        .agg(
            source_rows=("amount", "size"),
            reported_expenditure_rows=(
                "is_reported_expenditure",
                "sum",
            ),
            reported_expenditure_amount=(
                "_headline_amount",
                "sum",
            ),
        )
    )

    optional_metadata = [
        column
        for column in ["filer", "filer_id"]
        if column in data.columns
    ]

    if optional_metadata:
        metadata = (
            data[group_columns + optional_metadata]
            .drop_duplicates(group_columns)
        )
        candidate_index = candidate_index.merge(
            metadata,
            on=group_columns,
            how="left",
        )

    candidate_index["source_candidate_name"] = (
        candidate_index["source_file_stem"]
        .astype(str)
        .str.replace("_", " ", regex=False)
        .str.strip()
    )
    candidate_index["source_candidate_name_norm"] = (
        candidate_index["source_candidate_name"].map(normalize_name)
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    data.drop(columns=["_headline_amount"]).to_csv(
        transactions_output,
        index=False,
    )
    candidate_index.to_csv(candidate_index_output, index=False)
    file_audit.to_csv(file_audit_output, index=False)

    print(f"SAVED {transactions_output}")
    print(f"SAVED {candidate_index_output}")
    print(f"SAVED {file_audit_output}")
    print(f"Workbooks: {len(workbooks)}")
    print(f"Rows: {len(data)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    main(year=args.year, force=args.force)

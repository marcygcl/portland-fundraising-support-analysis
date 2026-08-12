"""Source-specific helpers for ORESTAR Excel workbooks.

The main cleaning script should read like a simple workflow. Messy Excel details
live here:

- normalize column names;
- parse money;
- infer contest/district from folders;
- read one workbook;
- add deterministic contribution/spending flags.

No analytical profiles are created here.
"""

import hashlib
import re

import numpy as np
import pandas as pd


REPORTED_EXPENDITURE_SUBTYPES = {
    "Cash Expenditure",
    "Personal Expenditure for Reimbursement",
    "Miscellaneous Other Disbursement",
}

REPORTED_CONTRIBUTION_SUBTYPES = {
    "Cash Contribution",
    "In-Kind Contribution",
}


def sha256_hash(path):
    """Return a SHA-256 fingerprint for one source workbook."""
    digest = hashlib.sha256()

    with path.open("rb") as file:
        while True:
            chunk = file.read(1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def clean_column_name(value):
    """Convert an Excel column name to snake_case."""
    text = str(value).strip()

    # First split camelCase, then remove punctuation.
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    text = re.sub(r"[^A-Za-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text)

    return text.strip("_").lower()


def make_unique_columns(columns):
    """Normalize columns and suffix repeated names."""
    counts = {}
    cleaned = []

    for column in columns:
        base = clean_column_name(column) or "unnamed"
        counts[base] = counts.get(base, 0) + 1

        if counts[base] == 1:
            cleaned.append(base)
        else:
            cleaned.append(f"{base}_{counts[base]}")

    return cleaned


def parse_money(series):
    """Convert ORESTAR money strings to numbers."""
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")

    text = series.astype("string").str.strip()

    # Example: ($25.00) -> -25.00
    text = text.str.replace(r"^\((.*)\)$", r"-\1", regex=True)
    text = text.str.replace("$", "", regex=False)
    text = text.str.replace(",", "", regex=False)

    return pd.to_numeric(text, errors="coerce")


def first_nonempty(series):
    """Return the first non-null, non-blank value."""
    for value in series:
        if pd.isna(value):
            continue

        if str(value).strip():
            return value

    return pd.NA


def infer_contest_from_path(path, year_dir):
    """Infer contest type, office, and district from a parent folder.

    Accepted examples:
        city_concil_d3
        city_council_d3
        county_commisioner_d2
        county_commissioner_d2
    """
    folders = path.relative_to(year_dir).parts[:-1]

    city_patterns = [
        r"^city[\s_-]*concil[\s_-]*d[\s_-]*([1-4])$",
        r"^city[\s_-]*concil[\s_-]*district[\s_-]*([1-4])$",
        r"^city[\s_-]*council[\s_-]*d[\s_-]*([1-4])$",
        r"^city[\s_-]*council[\s_-]*district[\s_-]*([1-4])$",
        r"^d[\s_-]*([1-4])$",
        r"^district[\s_-]*([1-4])$",
    ]

    county_patterns = [
        r"^county[\s_-]*commisioner[\s_-]*d[\s_-]*(\d+)$",
        r"^county[\s_-]*commisioner[\s_-]*district[\s_-]*(\d+)$",
        r"^county[\s_-]*commissioner[\s_-]*d[\s_-]*(\d+)$",
        r"^county[\s_-]*commissioner[\s_-]*district[\s_-]*(\d+)$",
    ]

    for folder in reversed(folders):
        folder = str(folder).strip()

        for pattern in city_patterns:
            match = re.fullmatch(pattern, folder, flags=re.IGNORECASE)

            if match:
                return (
                    "city_council",
                    "Portland City Council",
                    int(match.group(1)),
                )

        for pattern in county_patterns:
            match = re.fullmatch(pattern, folder, flags=re.IGNORECASE)

            if match:
                return (
                    "county_commissioner",
                    "Multnomah County Commissioner",
                    int(match.group(1)),
                )

    raise ValueError(
        "Could not infer a supported ORESTAR contest from path:\n"
        f"{path}"
    )


def read_workbook(path, year, year_dir, source_hash):
    """Read one workbook and attach standard source metadata."""
    contest_type, office, district = infer_contest_from_path(
        path,
        year_dir,
    )

    data = pd.read_excel(path, dtype=object)

    if data.empty:
        return data

    data.columns = make_unique_columns(data.columns)
    data = data.dropna(how="all").copy()

    if "sub_type" not in data.columns:
        raise ValueError(f"Missing 'Sub Type' column in {path}")

    if "amount" not in data.columns:
        raise ValueError(f"Missing 'Amount' column in {path}")

    for column in ["amount", "aggregate_amount"]:
        if column in data.columns:
            data[column] = parse_money(data[column])

    date_columns = [
        "tran_date",
        "attest_date",
        "review_date",
        "due_date",
        "occptn_ltr_date",
        "filed_date",
        "expenditure_date",
    ]

    for column in date_columns:
        if column in data.columns:
            data[column] = pd.to_datetime(
                data[column],
                errors="coerce",
            )

    data["sub_type"] = data["sub_type"].astype("string").str.strip()

    # Source and contest metadata.
    data["year"] = int(year)
    data["contest_type"] = contest_type
    data["office"] = office
    data["district"] = int(district)
    data["source_file"] = path.name
    data["source_file_stem"] = path.stem
    data["source_file_hash"] = source_hash
    data["source_relative_path"] = str(path.relative_to(year_dir))

    if "tran_date" in data.columns:
        data["transaction_year"] = data["tran_date"].dt.year.astype("Int64")
    else:
        data["transaction_year"] = pd.Series(
            pd.NA,
            index=data.index,
            dtype="Int64",
        )

    # Deterministic spending flag.
    data["is_reported_expenditure"] = data["sub_type"].isin(
        REPORTED_EXPENDITURE_SUBTYPES
    )

    data["reported_expenditure_amount"] = np.where(
        data["is_reported_expenditure"],
        data["amount"],
        np.nan,
    )

    # Deterministic positive contribution flag. Refunds are excluded.
    data["is_reported_contribution"] = data["sub_type"].isin(
        REPORTED_CONTRIBUTION_SUBTYPES
    )

    data["reported_contribution_amount"] = np.where(
        data["is_reported_contribution"],
        data["amount"],
        np.nan,
    )

    return data

# ---------------------------------------------------------------------
# Candidate index and file audit
# ---------------------------------------------------------------------

def build_candidate_index(data):
    """Create one source-level row per ORESTAR workbook."""
    group_columns = [
        "year",
        "contest_type",
        "office",
        "district",
        "source_file",
        "source_file_stem",
        "source_file_hash",
        "source_relative_path",
    ]

    rows = []

    for key, group in data.groupby(
        group_columns,
        dropna=False,
        sort=False,
    ):
        (
            year,
            contest_type,
            office,
            district,
            source_file,
            source_file_stem,
            source_file_hash,
            source_relative_path,
        ) = key

        filer = (
            first_nonempty(group["filer"])
            if "filer" in group.columns
            else pd.NA
        )
        filer_id = (
            first_nonempty(group["filer_id"])
            if "filer_id" in group.columns
            else pd.NA
        )

        rows.append(
            {
                "year": year,
                "contest_type": contest_type,
                "office": office,
                "district": district,
                "source_file": source_file,
                "source_file_stem": source_file_stem,
                "source_file_hash": source_file_hash,
                "source_relative_path": source_relative_path,
                "source_rows": len(group),
                "reported_expenditure_rows": int(
                    group["is_reported_expenditure"].sum()
                ),
                "reported_expenditure_amount": (
                    group["reported_expenditure_amount"].sum(min_count=1)
                ),
                "reported_contribution_rows": int(
                    group["is_reported_contribution"].sum()
                ),
                "reported_contribution_amount": (
                    group["reported_contribution_amount"].sum(min_count=1)
                ),
                "filer": filer,
                "filer_id": filer_id,
                "source_candidate_name": source_file_stem,
            }
        )

    candidate_index = pd.DataFrame(rows)

    candidate_index["source_candidate_name_norm"] = (
        candidate_index["source_candidate_name"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    return (
        candidate_index
        .sort_values(["district", "source_candidate_name"])
        .reset_index(drop=True)
    )


def build_file_audit(data, year_hash_counts):
    """Create one row per workbook and flag repeated file hashes."""
    columns = [
        "year",
        "contest_type",
        "office",
        "district",
        "source_file",
        "source_file_stem",
        "source_file_hash",
        "source_relative_path",
    ]

    audit = data[columns].drop_duplicates().copy()

    audit["same_hash_file_count"] = (
        audit["source_file_hash"]
        .map(year_hash_counts)
        .fillna(1)
        .astype(int)
    )
    audit["is_exact_duplicate_export"] = (
        audit["same_hash_file_count"] > 1
    )

    return (
        audit
        .sort_values(["district", "source_file"])
        .reset_index(drop=True)
    )

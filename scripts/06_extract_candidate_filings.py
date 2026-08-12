"""Download and parse candidate filing PDFs.

Outputs
-------
candidate_filings.csv
    one row per candidate-document

candidate_filing_questions.csv
    every extracted Qualtrics Q block

candidate_profile_fields.csv
    one selected row per candidate with research fields

candidate_index_enriched.csv
    official candidate index + selected filing fields

The technical PDF parser lives in helpers/candidate_filings_parser.py.
"""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import requests

from config import USER_AGENT
from helpers.candidate_filings_parser import (
    get_text,
    parse_fields,
    question_records,
)
from helpers.linkage import slugify
from helpers.paths import CLEAN, RAW


PROFILE_COLUMNS = [
    "year",
    "district",
    "candidate",
    "candidate_key",
    "filing_status",
    "filing_date",
    "form_type_detected",
    "filed_as",
    "office_sought",
    "ballot_name",
    "campaign_website",
    "race_ethnicity_self_reported",
    "tribe_native_corporation_self_reported",
    "occupation",
    "occupational_background",
    "prior_govt_experience",
    "education_background",
    "public_funding_program",
    "candidate_committee",
    "filing_method",
    "parse_method",
    "needs_manual_review",
]


def download_pdf(url, destination, force=False):
    """Download one PDF, or reuse an existing raw copy."""
    already_exists = (
        destination.exists()
        and destination.stat().st_size > 0
    )

    if already_exists and not force:
        return True, "already_downloaded"

    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        return False, f"download_error: {error}"

    content_type = response.headers.get("Content-Type", "")
    looks_like_pdf = (
        "pdf" in content_type.lower()
        or response.content.startswith(b"%PDF")
    )

    if not looks_like_pdf:
        return False, f"not_a_pdf (content-type={content_type})"

    destination.write_bytes(response.content)

    return True, "downloaded"


def process_one_document(
    row,
    year,
    raw_pdf_dir,
    text_dir,
    force=False,
):
    """Download, extract, and parse one filing document."""
    candidate_slug = slugify(row.candidate)
    district_slug = f"d{int(row.district)}"

    has_label = (
        pd.notna(row.pdf_label)
        and str(row.pdf_label).strip()
    )
    label = row.pdf_label if has_label else "filing"
    label_slug = slugify(label) or "filing"

    pdf_path = (
        raw_pdf_dir
        / district_slug
        / candidate_slug
        / f"{label_slug}.pdf"
    )
    text_path = (
        text_dir
        / district_slug
        / candidate_slug
        / f"{label_slug}.txt"
    )

    success, download_status = download_pdf(
        row.pdf_url,
        pdf_path,
        force=force,
    )

    result = {
        "year": year,
        "district": int(row.district),
        "candidate": row.candidate,
        "candidate_key": row.candidate_key,
        "filing_status": row.filing_status,
        "filing_date": row.filing_date,
        "pdf_label": label,
        "pdf_url": row.pdf_url,
        "pdf_local_path": "",
        "download_status": download_status,
    }

    if not success:
        result["parse_method"] = "download_failed"
        result["needs_manual_review"] = True

        return result, []

    result["pdf_local_path"] = str(
        pdf_path.relative_to(RAW)
    )

    # OCR is used only as a fallback inside get_text().
    text, extraction_method = get_text(pdf_path)

    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text(text, encoding="utf-8")

    parsed_fields = parse_fields(text)

    result.update(parsed_fields)
    result["parse_method"] = extraction_method
    result["text_local_path"] = str(
        text_path.relative_to(CLEAN)
    )
    result["needs_manual_review"] = (
        extraction_method in {"failed", "ocr_fallback_short"}
        or parsed_fields.get("form_type_detected")
        == "unrecognized_or_scanned"
    )

    questions = []

    for question in question_records(text):
        questions.append(
            {
                "year": year,
                "district": int(row.district),
                "candidate": row.candidate,
                "candidate_key": row.candidate_key,
                "filing_status": row.filing_status,
                "filing_date": row.filing_date,
                "pdf_label": label,
                "pdf_url": row.pdf_url,
                "question_number": question["question_number"],
                "inline_answer": question["inline_answer"],
                "question_text": question["question_text"],
            }
        )

    return result, questions


def build_candidate_profile_fields(documents):
    """Choose the best parsed document row for each candidate."""
    documents = documents.copy()

    # Lower rank = better extraction.
    parse_rank = {
        "text_layer": 0,
        "ocr_fallback": 1,
        "ocr_fallback_short": 2,
        "failed": 3,
        "download_failed": 4,
    }

    documents["_parse_rank"] = (
        documents["parse_method"]
        .map(parse_rank)
        .fillna(99)
    )
    documents["_filing_date_parsed"] = pd.to_datetime(
        documents["filing_date"],
        errors="coerce",
    )

    available_columns = [
        column
        for column in PROFILE_COLUMNS
        if column in documents.columns
    ]

    # If a candidate has several documents:
    # 1. prefer the better extraction;
    # 2. then prefer the more recent filing.
    return (
        documents
        .sort_values(
            [
                "candidate_key",
                "_parse_rank",
                "_filing_date_parsed",
            ],
            ascending=[True, True, False],
        )
        .drop_duplicates(
            "candidate_key",
            keep="first",
        )[available_columns]
        .copy()
    )


def enrich_candidate_index(candidate_index, candidate_fields):
    """Attach selected filing fields to the official candidate index."""
    fields_to_merge = candidate_fields.drop(
        columns=[
            "year",
            "district",
            "candidate",
            "filing_status",
            "filing_date",
        ],
        errors="ignore",
    )

    return candidate_index.merge(
        fields_to_merge,
        on="candidate_key",
        how="left",
        validate="one_to_one",
    )


def main(
    year,
    force=False,
    limit=None,
    sleep_seconds=0.5,
):
    clean_dir = CLEAN / "candidate_filings" / str(year)
    raw_pdf_dir = RAW / "candidate_filings" / str(year) / "pdfs"
    text_dir = clean_dir / "extracted_text"

    candidate_list_path = clean_dir / "candidate_list.csv"
    candidate_index_path = clean_dir / "candidate_index.csv"

    document_output = clean_dir / "candidate_filings.csv"
    questions_output = clean_dir / "candidate_filing_questions.csv"
    candidate_fields_output = clean_dir / "candidate_profile_fields.csv"
    enriched_index_output = clean_dir / "candidate_index_enriched.csv"

    expected_outputs = [
        document_output,
        questions_output,
        candidate_fields_output,
        enriched_index_output,
    ]

    if all(path.exists() for path in expected_outputs) and not force:
        print(
            f"SKIP  candidate filing extraction already exists for {year}"
        )
        return

    for path in [candidate_list_path, candidate_index_path]:
        if not path.exists():
            raise FileNotFoundError(
                "Run 05_scrape_candidate_filings.py first: "
                f"{path}"
            )

    # 1. Load candidate-document rows that actually have PDF URLs.
    candidate_list = pd.read_csv(candidate_list_path)

    has_pdf_url = (
        candidate_list["pdf_url"].notna()
        & candidate_list["pdf_url"].astype(str).ne("")
    )
    candidate_list = candidate_list.loc[has_pdf_url].copy()

    if limit is not None:
        candidate_list = candidate_list.head(limit)

    print(
        f"Processing {len(candidate_list)} candidate-document rows..."
    )

    # 2. Process each document.
    document_rows = []
    question_rows = []
    total_documents = len(candidate_list)

    for row_number, row in enumerate(
        candidate_list.itertuples(index=False),
        start=1,
    ):
        print(
            f"[{row_number}/{total_documents}] "
            f"D{row.district} - {row.candidate}"
        )

        result, questions = process_one_document(
            row=row,
            year=year,
            raw_pdf_dir=raw_pdf_dir,
            text_dir=text_dir,
            force=force,
        )

        document_rows.append(result)
        question_rows.extend(questions)

        if result["download_status"] == "downloaded":
            time.sleep(sleep_seconds)

    documents = pd.DataFrame(document_rows)

    if documents.empty:
        raise RuntimeError(
            "No candidate filing documents were processed."
        )

    questions = pd.DataFrame(question_rows)

    # 3. Build one selected candidate-level profile row.
    candidate_fields = build_candidate_profile_fields(documents)

    base_candidate_index = pd.read_csv(candidate_index_path)
    enriched_index = enrich_candidate_index(
        base_candidate_index,
        candidate_fields,
    )

    # 4. Save reusable clean tables.
    documents.to_csv(document_output, index=False)
    questions.to_csv(questions_output, index=False)
    candidate_fields.to_csv(candidate_fields_output, index=False)
    enriched_index.to_csv(enriched_index_output, index=False)

    print(f"SAVED {document_output}")
    print(f"SAVED {questions_output}")
    print(f"SAVED {candidate_fields_output}")
    print(f"SAVED {enriched_index_output}")
    print(f"Question blocks saved: {len(questions):,}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional small test run, e.g. --limit 3",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.5,
        help="Seconds to pause after each newly downloaded PDF.",
    )
    args = parser.parse_args()

    main(
        year=args.year,
        force=args.force,
        limit=args.limit,
        sleep_seconds=args.sleep,
    )

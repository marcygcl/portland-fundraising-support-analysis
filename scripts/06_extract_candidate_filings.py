
"""Download and extract Portland candidate filing PDFs.

Outputs:
- raw PDFs;
- extracted text files;
- document-level parsed filing table;
- question-level long table containing every Qualtrics Q block;
- candidate-level profile fields;
- enriched official candidate index.

The long question table preserves all extracted questions so future analysis
does not need to reparse the PDFs. The candidate-level profile table only
promotes selected research fields.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


import pandas as pd
import requests

from config import USER_AGENT

from helpers.candidate_filings_parser import (
    get_text,
    parse_fields,
    question_records,
)

from helpers.linkage import (
    slugify,
)

from helpers.paths import (
    CLEAN,
    RAW,
)


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
    (
        "tribe_native_corporation_"
        "self_reported"
    ),

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


def download_pdf(
    *,
    url: str,
    destination: Path,
    force: bool,
):
    """Download a PDF unless a raw copy already exists."""

    if (
        destination.exists()
        and destination.stat().st_size > 0
        and not force
    ):
        return (
            True,
            "already_downloaded",
        )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        response = requests.get(
            url,
            headers={
                "User-Agent":
                    USER_AGENT,
            },
            timeout=30,
        )

        response.raise_for_status()

        content_type = (
            response.headers.get(
                "Content-Type",
                "",
            )
        )

        if (
            "pdf"
            not in content_type.lower()
            and not response.content.startswith(
                b"%PDF"
            )
        ):
            return (
                False,
                (
                    "not_a_pdf "
                    f"(content-type="
                    f"{content_type})"
                ),
            )

        destination.write_bytes(
            response.content
        )

        return (
            True,
            "downloaded",
        )

    except requests.RequestException as error:
        return (
            False,
            f"download_error: {error}",
        )


def main(
    *,
    year: int,
    force: bool = False,
    limit: int | None = None,
    sleep_seconds: float = 0.5,
):
    clean_dir = (
        CLEAN
        / "candidate_filings"
        / str(year)
    )

    raw_pdf_dir = (
        RAW
        / "candidate_filings"
        / str(year)
        / "pdfs"
    )

    text_dir = (
        clean_dir
        / "extracted_text"
    )

    candidate_list_path = (
        clean_dir
        / "candidate_list.csv"
    )

    candidate_index_path = (
        clean_dir
        / "candidate_index.csv"
    )

    document_output = (
        clean_dir
        / "candidate_filings.csv"
    )

    questions_output = (
        clean_dir
        / (
            "candidate_filing_"
            "questions.csv"
        )
    )

    candidate_fields_output = (
        clean_dir
        / "candidate_profile_fields.csv"
    )

    enriched_index_output = (
        clean_dir
        / "candidate_index_enriched.csv"
    )

    if (
        document_output.exists()
        and questions_output.exists()
        and candidate_fields_output.exists()
        and enriched_index_output.exists()
        and not force
    ):
        print(
            "SKIP  candidate filing "
            f"extraction already exists "
            f"for {year}"
        )
        return

    for path in [
        candidate_list_path,
        candidate_index_path,
    ]:
        if not path.exists():
            raise FileNotFoundError(
                "Run "
                "05_scrape_candidate_filings.py "
                f"first: {path}"
            )

    candidate_list = (
        pd.read_csv(
            candidate_list_path
        )
    )

    candidate_list = (
        candidate_list.loc[
            candidate_list[
                "pdf_url"
            ].notna()
            & candidate_list[
                "pdf_url"
            ]
            .astype(str)
            .ne("")
        ]
        .copy()
    )

    if limit is not None:
        candidate_list = (
            candidate_list.head(
                limit
            )
        )

    print(
        "Processing "
        f"{len(candidate_list)} "
        "candidate-document rows..."
    )

    document_results = []
    question_results = []

    for (
        row_number,
        row,
    ) in enumerate(
        candidate_list.itertuples(
            index=False
        ),
        start=1,
    ):
        candidate_slug = (
            slugify(
                row.candidate
            )
        )

        district_slug = (
            f"d{int(row.district)}"
        )

        label = (
            row.pdf_label
            if (
                pd.notna(
                    row.pdf_label
                )
                and str(
                    row.pdf_label
                ).strip()
            )
            else "filing"
        )

        label_slug = (
            slugify(
                label
            )
            or "filing"
        )

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

        print(
            f"[{row_number}/"
            f"{len(candidate_list)}] "
            f"D{row.district} - "
            f"{row.candidate}"
        )

        (
            success,
            download_status,
        ) = download_pdf(
            url=row.pdf_url,
            destination=pdf_path,
            force=force,
        )

        result = {
            "year":
                year,

            "district":
                int(
                    row.district
                ),

            "candidate":
                row.candidate,

            "candidate_key":
                row.candidate_key,

            "filing_status":
                row.filing_status,

            "filing_date":
                row.filing_date,

            "pdf_label":
                label,

            "pdf_url":
                row.pdf_url,

            "pdf_local_path":
                (
                    str(
                        pdf_path.relative_to(
                            RAW
                        )
                    )
                    if success
                    else ""
                ),

            "download_status":
                download_status,
        }

        if not success:
            result.update(
                {
                    "parse_method":
                        "download_failed",

                    "needs_manual_review":
                        True,
                }
            )

            document_results.append(
                result
            )

            continue

        (
            text,
            extraction_method,
        ) = get_text(
            pdf_path
        )

        text_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        text_path.write_text(
            text,
            encoding="utf-8",
        )

        parsed = (
            parse_fields(
                text
            )
        )

        result.update(
            parsed
        )

        result[
            "parse_method"
        ] = extraction_method

        result[
            "text_local_path"
        ] = str(
            text_path.relative_to(
                CLEAN
            )
        )

        result[
            "needs_manual_review"
        ] = (
            extraction_method
            in {
                "failed",
                "ocr_fallback_short",
            }
            or parsed.get(
                "form_type_detected"
            )
            == (
                "unrecognized_or_scanned"
            )
        )

        document_results.append(
            result
        )

        # -------------------------------------------------------------
        # Save every Q-number block
        # -------------------------------------------------------------

        for question in (
            question_records(
                text
            )
        ):
            question_results.append(
                {
                    "year":
                        year,

                    "district":
                        int(
                            row.district
                        ),

                    "candidate":
                        row.candidate,

                    "candidate_key":
                        row.candidate_key,

                    "filing_status":
                        row.filing_status,

                    "filing_date":
                        row.filing_date,

                    "pdf_label":
                        label,

                    "pdf_url":
                        row.pdf_url,

                    "question_number":
                        question[
                            "question_number"
                        ],

                    "inline_answer":
                        question[
                            "inline_answer"
                        ],

                    "question_text":
                        question[
                            "question_text"
                        ],
                }
            )

        if (
            download_status
            == "downloaded"
        ):
            time.sleep(
                sleep_seconds
            )

    documents = pd.DataFrame(
        document_results
    )

    if documents.empty:
        raise RuntimeError(
            "No candidate filing "
            "documents were processed."
        )

    questions = pd.DataFrame(
        question_results
    )

    # ---------------------------------------------------------------
    # Save document-level data
    # ---------------------------------------------------------------

    documents.to_csv(
        document_output,
        index=False,
    )

    # ---------------------------------------------------------------
    # Save every extracted question
    # ---------------------------------------------------------------

    questions.to_csv(
        questions_output,
        index=False,
    )

    # ---------------------------------------------------------------
    # Candidate-level profile fields
    # ---------------------------------------------------------------

    parse_rank = {
        "text_layer":
            0,

        "ocr_fallback":
            1,

        "ocr_fallback_short":
            2,

        "failed":
            3,

        "download_failed":
            4,
    }

    documents[
        "_parse_rank"
    ] = (
        documents[
            "parse_method"
        ]
        .map(
            parse_rank
        )
        .fillna(99)
    )

    documents[
        "_filing_date_parsed"
    ] = pd.to_datetime(
        documents[
            "filing_date"
        ],
        errors="coerce",
    )

    available_profile_columns = [
        column
        for column
        in PROFILE_COLUMNS
        if column
        in documents.columns
    ]

    candidate_fields = (
        documents
        .sort_values(
            [
                "candidate_key",
                "_parse_rank",
                "_filing_date_parsed",
            ],
            ascending=[
                True,
                True,
                False,
            ],
        )
        .drop_duplicates(
            "candidate_key",
            keep="first",
        )
        [
            available_profile_columns
        ]
        .copy()
    )

    candidate_fields.to_csv(
        candidate_fields_output,
        index=False,
    )

    # ---------------------------------------------------------------
    # Enrich official candidate index
    # ---------------------------------------------------------------

    base_index = pd.read_csv(
        candidate_index_path
    )

    fields_to_merge = (
        candidate_fields.drop(
            columns=[
                "year",
                "district",
                "candidate",
                "filing_status",
                "filing_date",
            ],
            errors="ignore",
        )
    )

    enriched_index = (
        base_index.merge(
            fields_to_merge,
            on="candidate_key",
            how="left",
            validate="one_to_one",
        )
    )

    enriched_index.to_csv(
        enriched_index_output,
        index=False,
    )

    print(
        f"SAVED {document_output}"
    )

    print(
        f"SAVED {questions_output}"
    )

    print(
        f"SAVED {candidate_fields_output}"
    )

    print(
        f"SAVED {enriched_index_output}"
    )

    print(
        "Question blocks saved: "
        f"{len(questions)}"
    )


if __name__ == "__main__":
    parser = (
        argparse.ArgumentParser()
    )

    parser.add_argument(
        "--year",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--force",
        action="store_true",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
    )

    parser.add_argument(
        "--sleep",
        type=float,
        default=0.5,
    )

    args = (
        parser.parse_args()
    )

    main(
        year=args.year,
        force=args.force,
        limit=args.limit,
        sleep_seconds=args.sleep,
    )
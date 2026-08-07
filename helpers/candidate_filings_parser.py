"""Extraction and parsing helpers for Portland candidate filings.

The Portland Auditor candidate application is exported from Qualtrics.
Question numbers can change across election years, so selected fields are
identified primarily by question text rather than fixed Q numbers.

The helper also exposes every Qualtrics question block so the pipeline can
save a long `candidate_filing_questions.csv` without reparsing PDFs later.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


MIN_TEXT_LAYER_CHARS = 200

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    import pytesseract
    from pdf2image import convert_from_path
except ImportError:
    pytesseract = None
    convert_from_path = None


# Examples:
#   Q26
#   Q28 None
#   Q24 Black or African American,
QUESTION_RE = re.compile(
    r"(?m)^Q(\d{1,3})\b([^\n]*)\n?"
)


# ---------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------

def extract_text_layer(pdf_path: Path) -> str:
    """Extract the embedded text layer when one exists."""
    if pdfplumber is None:
        return ""

    try:
        chunks = []

        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                chunks.append(page.extract_text() or "")

        return "\n".join(chunks).strip()

    except Exception:
        return ""


def extract_text_ocr(pdf_path: Path) -> str:
    """OCR fallback for scanned PDFs without a usable text layer."""
    if pytesseract is None or convert_from_path is None:
        return ""

    try:
        images = convert_from_path(
            str(pdf_path),
            dpi=300,
        )

        return "\n".join(
            pytesseract.image_to_string(image)
            for image in images
        ).strip()

    except Exception:
        return ""


def get_text(pdf_path: Path) -> tuple[str, str]:
    """Return extracted text and the extraction method used."""
    text = extract_text_layer(pdf_path)

    if len(text) >= MIN_TEXT_LAYER_CHARS:
        return text, "text_layer"

    ocr_text = extract_text_ocr(pdf_path)

    if len(ocr_text) >= MIN_TEXT_LAYER_CHARS:
        return ocr_text, "ocr_fallback"

    best = (
        ocr_text
        if len(ocr_text) > len(text)
        else text
    )

    return (
        best,
        "failed"
        if not best
        else "ocr_fallback_short",
    )


# ---------------------------------------------------------------------
# General text helpers
# ---------------------------------------------------------------------

def normalize_space(value: str) -> str:
    """Collapse repeated whitespace into one space."""
    return re.sub(
        r"\s+",
        " ",
        value or "",
    ).strip()


def clean_website(value: str) -> str:
    """Convert PDF markdown-style hyperlinks into a plain URL."""
    if not value:
        return ""

    markdown_link = re.search(
        r"\[[^\]]+\]\((https?://[^)]+)\)",
        value,
    )

    if markdown_link:
        return markdown_link.group(1).strip()

    return normalize_space(value)


def _valid_inline_answer(
    value: str,
) -> bool:
    value = normalize_space(value)

    if not value:
        return False

    return (
        "respondent skipped this question"
        not in value.lower()
    )


# ---------------------------------------------------------------------
# Qualtrics question blocks
# ---------------------------------------------------------------------

def split_question_blocks(
    text: str,
) -> list[dict]:
    """Split PDF text into Q-number blocks.

    This preserves answers printed on the same line as the
    question number, for example:

        Q28 None
        Prior Government Experience ...
    """

    matches = list(
        QUESTION_RE.finditer(text)
    )

    blocks = []

    for index, match in enumerate(matches):
        start = match.end()

        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(text)
        )

        blocks.append(
            {
                "question_number": int(
                    match.group(1)
                ),
                "inline_answer":
                    normalize_space(
                        match.group(2)
                    ),
                "text":
                    text[start:end].strip(),
            }
        )

    return blocks


def question_records(
    text: str,
) -> list[dict]:
    """Return all Q blocks for long-form storage."""

    records = []

    for block in split_question_blocks(
        text
    ):
        records.append(
            {
                "question_number":
                    block[
                        "question_number"
                    ],
                "inline_answer":
                    block[
                        "inline_answer"
                    ],
                "question_text":
                    block[
                        "text"
                    ],
            }
        )

    return records


def find_block(
    blocks: list[dict],
    *phrases: str,
) -> dict | None:
    """Find the first block containing one of the requested phrases."""

    phrases_lower = [
        phrase.lower()
        for phrase in phrases
    ]

    for block in blocks:
        haystack = (
            block["inline_answer"]
            + "\n"
            + block["text"]
        ).lower()

        if any(
            phrase in haystack
            for phrase in phrases_lower
        ):
            return block

    return None


def find_blocks(
    blocks: list[dict],
    *phrases: str,
) -> list[dict]:
    """Find all blocks containing one of the requested phrases."""

    phrases_lower = [
        phrase.lower()
        for phrase in phrases
    ]

    matches = []

    for block in blocks:
        haystack = (
            block["inline_answer"]
            + "\n"
            + block["text"]
        ).lower()

        if any(
            phrase in haystack
            for phrase in phrases_lower
        ):
            matches.append(
                block
            )

    return matches


def answer_after_label(
    block: dict | None,
    *label_phrases: str,
) -> str:
    """Extract a simple answer from a Qualtrics block.

    Preference order:
    1. answer printed on the same line as Q##;
    2. lines appearing after the line containing the field label.
    """

    if block is None:
        return ""

    inline = block.get(
        "inline_answer",
        "",
    )

    if _valid_inline_answer(
        inline
    ):
        return normalize_space(
            inline
        )

    if (
        "respondent skipped this question"
        in normalize_space(
            inline
        ).lower()
    ):
        return ""

    lines = [
        line.strip()
        for line
        in block.get(
            "text",
            "",
        ).splitlines()
        if line.strip()
    ]

    label_phrases_lower = [
        phrase.lower()
        for phrase in label_phrases
    ]

    for index, line in enumerate(
        lines
    ):
        line_lower = (
            line.lower()
        )

        if any(
            phrase in line_lower
            for phrase
            in label_phrases_lower
        ):
            answer_lines = (
                lines[index + 1:]
            )

            # Remove page artifacts.
            answer_lines = [
                value
                for value
                in answer_lines
                if not re.fullmatch(
                    r"\d+\s*/\s*\d+",
                    value,
                )
                and value.lower()
                != (
                    "candidate filing "
                    "application"
                )
            ]

            return normalize_space(
                " ".join(
                    answer_lines
                )
            )

    return ""


# ---------------------------------------------------------------------
# Race / ethnicity
# ---------------------------------------------------------------------

def extract_race_ethnicity(
    block: dict | None,
) -> str:
    """Extract self-reported race/ethnicity selections.

    Qualtrics may put one selection on the Q-number line and
    another after the question prompt.
    """

    if block is None:
        return ""

    values = []

    inline = normalize_space(
        block.get(
            "inline_answer",
            "",
        )
    )

    if _valid_inline_answer(
        inline
    ):
        values.append(
            inline
            .rstrip(",")
            .strip()
        )

    text = block.get(
        "text",
        "",
    )

    prompt_match = re.search(
        r"Race or Ethnicity"
        r"\s*\(Please check all that apply\)"
        r"\s*(.*)",
        text,
        flags=re.IGNORECASE,
    )

    if prompt_match:
        trailing = normalize_space(
            prompt_match.group(1)
        )

        if trailing:
            values.append(
                trailing
                .rstrip(",")
                .strip()
            )

    deduped = []

    for value in values:
        if (
            value
            and value
            not in deduped
        ):
            deduped.append(
                value
            )

    return " | ".join(
        deduped
    )


# ---------------------------------------------------------------------
# Education
# ---------------------------------------------------------------------

EDUCATION_LABELS = {
    "school":
        "complete name of school",
    "last_grade_completed":
        "last grade completed",
    "credential":
        "diploma/degree/certificate",
    "course_of_study":
        "course of study",
}


def _value_after_prefix(
    line: str,
    prefix: str,
) -> str:
    pattern = re.compile(
        rf"^{re.escape(prefix)}"
        r"(?:\s*\(optional\))?"
        r"\s*:?\s*(.*)$",
        flags=re.IGNORECASE,
    )

    match = pattern.match(
        line.strip()
    )

    return (
        normalize_space(
            match.group(1)
        )
        if match
        else ""
    )


def parse_education_blocks(
    blocks: list[dict],
) -> str:
    """Return structured education entries as JSON.

    The full raw question blocks are saved separately, so this
    field is only a convenient summary.
    """

    education_blocks = (
        find_blocks(
            blocks,
            "educational background",
        )
    )

    entries = []

    for block in education_blocks:

        combined = (
            block.get(
                "inline_answer",
                "",
            )
            + " "
            + block.get(
                "text",
                "",
            )
        )

        if (
            "respondent skipped this question"
            in combined.lower()
        ):
            continue

        entry = {
            "school": "",
            "last_grade_completed": "",
            "credential": "",
            "course_of_study": "",
        }

        lines = [
            line.strip()
            for line
            in block.get(
                "text",
                "",
            ).splitlines()
            if line.strip()
        ]

        for line in lines:
            for (
                key,
                prefix,
            ) in (
                EDUCATION_LABELS.items()
            ):
                value = (
                    _value_after_prefix(
                        line,
                        prefix,
                    )
                )

                if value:
                    entry[
                        key
                    ] = value

        if any(
            entry.values()
        ):
            entries.append(
                entry
            )

    if not entries:
        return ""

    return json.dumps(
        entries,
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------
# Public funding
# ---------------------------------------------------------------------

def extract_public_funding_program(
    blocks: list[dict],
) -> str:
    """Extract an explicit public-funding response when possible.

    Returns blank if a block only contains explanatory campaign-finance
    text but no identifiable candidate response.
    """

    candidate_blocks = (
        find_blocks(
            blocks,
            "small donor elections",
            "public funding",
            "public financing",
            (
                "open and accountable "
                "elections"
            ),
            "participate in",
        )
    )

    for block in candidate_blocks:

        inline = normalize_space(
            block.get(
                "inline_answer",
                "",
            )
        )

        if (
            _valid_inline_answer(
                inline
            )
            and len(inline) <= 200
        ):
            return inline

        combined = normalize_space(
            block.get(
                "text",
                "",
            )
        )

        explicit = re.search(
            r"\bI\s+"
            r"(?:do not plan|plan)"
            r"\s+to participate\b"
            r"[^.]*",
            combined,
            flags=re.IGNORECASE,
        )

        if explicit:
            return normalize_space(
                explicit.group(0)
            )

    return ""


# ---------------------------------------------------------------------
# Selected candidate-profile variables
# ---------------------------------------------------------------------

def parse_candidate_filing_fields(
    text: str,
) -> dict:
    """Extract research-relevant variables from a candidate filing."""

    blocks = (
        split_question_blocks(
            text
        )
    )

    filed_as = answer_after_label(
        find_block(
            blocks,
            "this form is filed as an",
        ),
        "this form is filed as an",
    )

    office_sought = (
        answer_after_label(
            find_block(
                blocks,
                (
                    "i am filing to be "
                    "a candidate"
                ),
                (
                    "i am filing for "
                    "the office of"
                ),
            ),
            (
                "i am filing to be "
                "a candidate"
            ),
            (
                "i am filing for "
                "the office of"
            ),
        )
    )

    ballot_name = (
        answer_after_label(
            find_block(
                blocks,
                (
                    "name should appear "
                    "on ballot"
                ),
            ),
            (
                "name should appear "
                "on ballot"
            ),
        )
    )

    campaign_website = (
        clean_website(
            answer_after_label(
                find_block(
                    blocks,
                    "campaign website",
                ),
                "campaign website",
            )
        )
    )

    race_ethnicity = (
        extract_race_ethnicity(
            find_block(
                blocks,
                "race or ethnicity",
            )
        )
    )

    tribe_native_corporation = (
        answer_after_label(
            find_block(
                blocks,
                (
                    "tribe or native "
                    "corporation"
                ),
            ),
            (
                "tribe or native "
                "corporation"
            ),
        )
    )

    occupation = (
        answer_after_label(
            find_block(
                blocks,
                (
                    "occupation "
                    "(present employment"
                ),
            ),
            (
                "occupation "
                "(present employment"
            ),
        )
    )

    occupational_background = (
        answer_after_label(
            find_block(
                blocks,
                (
                    "occupational "
                    "background"
                ),
            ),
            (
                "occupational "
                "background"
            ),
        )
    )

    prior_govt_experience = (
        answer_after_label(
            find_block(
                blocks,
                (
                    "prior government "
                    "experience"
                ),
                (
                    "prior governmental "
                    "experience"
                ),
            ),
            (
                "prior government "
                "experience"
            ),
            (
                "prior governmental "
                "experience"
            ),
        )
    )

    candidate_committee = (
        answer_after_label(
            find_block(
                blocks,
                (
                    "committee as registered "
                    "in orestar"
                ),
                "candidate committee",
            ),
            (
                "committee as registered "
                "in orestar"
            ),
            "candidate committee",
        )
    )

    filing_method = (
        answer_after_label(
            find_block(
                blocks,
                "i am filing by",
            ),
            "i am filing by",
        )
    )

    return {
        "form_type_detected":
            "candidate_filing_application",

        "filed_as":
            filed_as,

        "office_sought":
            office_sought,

        "ballot_name":
            ballot_name,

        "campaign_website":
            campaign_website,

        "race_ethnicity_self_reported":
            race_ethnicity,

        (
            "tribe_native_corporation_"
            "self_reported"
        ):
            tribe_native_corporation,

        "occupation":
            occupation,

        "occupational_background":
            occupational_background,

        "prior_govt_experience":
            prior_govt_experience,

        "education_background":
            parse_education_blocks(
                blocks
            ),

        "public_funding_program":
            extract_public_funding_program(
                blocks
            ),

        "candidate_committee":
            candidate_committee,

        "filing_method":
            filing_method,
    }


def parse_fields(
    text: str,
) -> dict:
    """Recognize a supported filing and parse selected fields."""

    looks_like_candidate_filing = (
        (
            "Candidate Filing Application"
            in text
            or "AUD 120 Form"
            in text
        )
        and bool(
            QUESTION_RE.search(
                text
            )
        )
    )

    if looks_like_candidate_filing:
        return (
            parse_candidate_filing_fields(
                text
            )
        )

    return {
        "form_type_detected":
            "unrecognized_or_scanned",

        "filed_as": "",
        "office_sought": "",
        "ballot_name": "",
        "campaign_website": "",

        (
            "race_ethnicity_"
            "self_reported"
        ): "",

        (
            "tribe_native_corporation_"
            "self_reported"
        ): "",

        "occupation": "",
        "occupational_background": "",
        "prior_govt_experience": "",
        "education_background": "",
        "public_funding_program": "",
        "candidate_committee": "",
        "filing_method": "",
    }
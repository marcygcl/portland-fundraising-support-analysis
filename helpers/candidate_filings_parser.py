"""Parse Portland candidate filing PDFs.

This helper contains the technical PDF logic so the pipeline script can stay
simple.

Workflow
--------
1. Try the PDF text layer.
2. Use OCR only as a fallback.
3. Split the Qualtrics export into Q-number blocks.
4. Extract selected research fields.
5. Preserve all question blocks separately for later review.

Question numbers can change across years, so fields are found mainly by
question text instead of fixed Q numbers.
"""

import json
import re


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


# Examples: "Q26", "Q28 None", "Q24 Black or African American,"
QUESTION_RE = re.compile(r"(?m)^Q(\d{1,3})\b([^\n]*)\n?")


# ---------------------------------------------------------------------
# 1. Extract text
# ---------------------------------------------------------------------

def extract_text_layer(pdf_path):
    """Read embedded PDF text when available."""
    if pdfplumber is None:
        return ""

    try:
        pages = []

        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                pages.append(page.extract_text() or "")

        return "\n".join(pages).strip()

    except Exception:
        # Not fatal: OCR may still work.
        return ""


def extract_text_ocr(pdf_path):
    """OCR fallback for scanned PDFs."""
    if pytesseract is None or convert_from_path is None:
        return ""

    try:
        images = convert_from_path(str(pdf_path), dpi=300)
        pages = []

        for image in images:
            pages.append(pytesseract.image_to_string(image))

        return "\n".join(pages).strip()

    except Exception:
        return ""


def get_text(pdf_path):
    """Return `(text, method)` from the best available extraction."""
    text_layer = extract_text_layer(pdf_path)

    if len(text_layer) >= MIN_TEXT_LAYER_CHARS:
        return text_layer, "text_layer"

    ocr_text = extract_text_ocr(pdf_path)

    if len(ocr_text) >= MIN_TEXT_LAYER_CHARS:
        return ocr_text, "ocr_fallback"

    best_text = (
        ocr_text
        if len(ocr_text) > len(text_layer)
        else text_layer
    )

    if not best_text:
        return "", "failed"

    return best_text, "ocr_fallback_short"


# ---------------------------------------------------------------------
# 2. General text helpers
# ---------------------------------------------------------------------

def normalize_space(value):
    return re.sub(r"\s+", " ", value or "").strip()


def clean_website(value):
    """Convert a PDF markdown-style hyperlink into a plain URL."""
    if not value:
        return ""

    match = re.search(
        r"\[[^\]]+\]\((https?://[^)]+)\)",
        value,
    )

    return match.group(1).strip() if match else normalize_space(value)


def valid_inline_answer(value):
    value = normalize_space(value)

    return bool(value) and (
        "respondent skipped this question"
        not in value.lower()
    )


# ---------------------------------------------------------------------
# 3. Qualtrics question blocks
# ---------------------------------------------------------------------

def split_question_blocks(text):
    """Split filing text into one dictionary per `Q##` block."""
    matches = list(QUESTION_RE.finditer(text))
    blocks = []

    for index, match in enumerate(matches):
        start = match.end()

        if index + 1 < len(matches):
            end = matches[index + 1].start()
        else:
            end = len(text)

        blocks.append(
            {
                "question_number": int(match.group(1)),
                "inline_answer": normalize_space(match.group(2)),
                "text": text[start:end].strip(),
            }
        )

    return blocks


def question_records(text):
    """Return every Q block in a simple long-table format."""
    records = []

    for block in split_question_blocks(text):
        records.append(
            {
                "question_number": block["question_number"],
                "inline_answer": block["inline_answer"],
                "question_text": block["text"],
            }
        )

    return records


def find_block(blocks, *phrases):
    """Return the first block containing any requested phrase."""
    phrases = [phrase.lower() for phrase in phrases]

    for block in blocks:
        text = (
            block["inline_answer"]
            + "\n"
            + block["text"]
        ).lower()

        if any(phrase in text for phrase in phrases):
            return block

    return None


def find_blocks(blocks, *phrases):
    """Return all blocks containing any requested phrase."""
    phrases = [phrase.lower() for phrase in phrases]
    results = []

    for block in blocks:
        text = (
            block["inline_answer"]
            + "\n"
            + block["text"]
        ).lower()

        if any(phrase in text for phrase in phrases):
            results.append(block)

    return results


def answer_after_label(block, *labels):
    """Extract a simple answer from one question block."""
    if block is None:
        return ""

    inline = block.get("inline_answer", "")

    if valid_inline_answer(inline):
        return normalize_space(inline)

    if "respondent skipped this question" in normalize_space(inline).lower():
        return ""

    lines = [
        line.strip()
        for line in block.get("text", "").splitlines()
        if line.strip()
    ]

    labels = [label.lower() for label in labels]

    for index, line in enumerate(lines):
        if not any(label in line.lower() for label in labels):
            continue

        answers = []

        for value in lines[index + 1:]:
            is_page_number = bool(
                re.fullmatch(r"\d+\s*/\s*\d+", value)
            )
            is_page_title = (
                value.lower() == "candidate filing application"
            )

            if not is_page_number and not is_page_title:
                answers.append(value)

        return normalize_space(" ".join(answers))

    return ""


# ---------------------------------------------------------------------
# 4. Fields that need special parsing
# ---------------------------------------------------------------------

def extract_race_ethnicity(block):
    """Extract self-reported race/ethnicity selections."""
    if block is None:
        return ""

    values = []
    inline = normalize_space(block.get("inline_answer", ""))

    if valid_inline_answer(inline):
        values.append(inline.rstrip(",").strip())

    match = re.search(
        r"Race or Ethnicity"
        r"\s*\(Please check all that apply\)"
        r"\s*(.*)",
        block.get("text", ""),
        flags=re.IGNORECASE,
    )

    if match:
        trailing = normalize_space(match.group(1))

        if trailing:
            values.append(trailing.rstrip(",").strip())

    # Remove duplicates while preserving order.
    unique = []

    for value in values:
        if value and value not in unique:
            unique.append(value)

    return " | ".join(unique)


EDUCATION_LABELS = {
    "school": "complete name of school",
    "last_grade_completed": "last grade completed",
    "credential": "diploma/degree/certificate",
    "course_of_study": "course of study",
}


def value_after_prefix(line, prefix):
    pattern = re.compile(
        rf"^{re.escape(prefix)}"
        r"(?:\s*\(optional\))?"
        r"\s*:?\s*(.*)$",
        flags=re.IGNORECASE,
    )

    match = pattern.match(line.strip())

    return normalize_space(match.group(1)) if match else ""


def parse_education_blocks(blocks):
    """Return structured education entries as JSON."""
    entries = []

    for block in find_blocks(blocks, "educational background"):
        combined = (
            block.get("inline_answer", "")
            + " "
            + block.get("text", "")
        )

        if "respondent skipped this question" in combined.lower():
            continue

        entry = {
            "school": "",
            "last_grade_completed": "",
            "credential": "",
            "course_of_study": "",
        }

        for line in block.get("text", "").splitlines():
            line = line.strip()

            if not line:
                continue

            for key, prefix in EDUCATION_LABELS.items():
                value = value_after_prefix(line, prefix)

                if value:
                    entry[key] = value

        if any(entry.values()):
            entries.append(entry)

    return (
        json.dumps(entries, ensure_ascii=False)
        if entries
        else ""
    )


def extract_public_funding_program(blocks):
    """Extract an explicit public-funding response when possible."""
    blocks = find_blocks(
        blocks,
        "small donor elections",
        "public funding",
        "public financing",
        "open and accountable elections",
        "participate in",
    )

    for block in blocks:
        inline = normalize_space(block.get("inline_answer", ""))

        if valid_inline_answer(inline) and len(inline) <= 200:
            return inline

        text = normalize_space(block.get("text", ""))

        match = re.search(
            r"\bI\s+(?:do not plan|plan)\s+to participate\b[^.]*",
            text,
            flags=re.IGNORECASE,
        )

        if match:
            return normalize_space(match.group(0))

    return ""


# ---------------------------------------------------------------------
# 5. Candidate-level research fields
# ---------------------------------------------------------------------

def parse_candidate_filing_fields(text):
    """Extract selected research fields from a recognized filing."""
    blocks = split_question_blocks(text)

    filed_as = answer_after_label(
        find_block(blocks, "this form is filed as an"),
        "this form is filed as an",
    )

    office_sought = answer_after_label(
        find_block(
            blocks,
            "i am filing to be a candidate",
            "i am filing for the office of",
        ),
        "i am filing to be a candidate",
        "i am filing for the office of",
    )

    ballot_name = answer_after_label(
        find_block(blocks, "name should appear on ballot"),
        "name should appear on ballot",
    )

    campaign_website = clean_website(
        answer_after_label(
            find_block(blocks, "campaign website"),
            "campaign website",
        )
    )

    race_ethnicity = extract_race_ethnicity(
        find_block(blocks, "race or ethnicity")
    )

    tribe_native_corporation = answer_after_label(
        find_block(blocks, "tribe or native corporation"),
        "tribe or native corporation",
    )

    occupation = answer_after_label(
        find_block(blocks, "occupation (present employment"),
        "occupation (present employment",
    )

    occupational_background = answer_after_label(
        find_block(blocks, "occupational background"),
        "occupational background",
    )

    prior_govt_experience = answer_after_label(
        find_block(
            blocks,
            "prior government experience",
            "prior governmental experience",
        ),
        "prior government experience",
        "prior governmental experience",
    )

    candidate_committee = answer_after_label(
        find_block(
            blocks,
            "committee as registered in orestar",
            "candidate committee",
        ),
        "committee as registered in orestar",
        "candidate committee",
    )

    filing_method = answer_after_label(
        find_block(blocks, "i am filing by"),
        "i am filing by",
    )

    return {
        "form_type_detected": "candidate_filing_application",
        "filed_as": filed_as,
        "office_sought": office_sought,
        "ballot_name": ballot_name,
        "campaign_website": campaign_website,
        "race_ethnicity_self_reported": race_ethnicity,
        "tribe_native_corporation_self_reported": tribe_native_corporation,
        "occupation": occupation,
        "occupational_background": occupational_background,
        "prior_govt_experience": prior_govt_experience,
        "education_background": parse_education_blocks(blocks),
        "public_funding_program": extract_public_funding_program(blocks),
        "candidate_committee": candidate_committee,
        "filing_method": filing_method,
    }


def parse_fields(text):
    """Recognize a supported filing and parse selected fields."""
    has_title = (
        "Candidate Filing Application" in text
        or "AUD 120 Form" in text
    )
    has_questions = bool(QUESTION_RE.search(text))

    if has_title and has_questions:
        return parse_candidate_filing_fields(text)

    # Stable schema for a document we could not recognize.
    return {
        "form_type_detected": "unrecognized_or_scanned",
        "filed_as": "",
        "office_sought": "",
        "ballot_name": "",
        "campaign_website": "",
        "race_ethnicity_self_reported": "",
        "tribe_native_corporation_self_reported": "",
        "occupation": "",
        "occupational_background": "",
        "prior_govt_experience": "",
        "education_background": "",
        "public_funding_program": "",
        "candidate_committee": "",
        "filing_method": "",
    }

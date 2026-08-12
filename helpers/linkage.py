"""Candidate-name linkage across Portland data sources.

Different sources do not always write the same candidate name.

Example:
    official page: Candace Avalos
    ORESTAR file:  Avalos.xls

Matching order
--------------
1. Restrict possible matches to the same year + district.
2. Apply a human-reviewed decision if one exists.
3. Accept exact normalized names.
4. Accept a unique short-token match ("Avalos" -> "Candace Avalos").
5. Use Jaro-Winkler similarity for unresolved records.
6. Send ambiguous cases to manual review.

We prefer leaving a record unresolved over linking it to the wrong candidate.
"""

import re
import unicodedata
from dataclasses import dataclass

import jellyfish
import pandas as pd

from config import (
    LINKAGE_AMBIGUITY_MARGIN,
    LINKAGE_MATCH_THRESHOLD,
    LINKAGE_MAYBE_THRESHOLD,
)
from .paths import CONFIG_DIR


DECISIONS_PATH = CONFIG_DIR / "linkage_decisions.csv"

MATCH = "match"
MAYBE_MATCH = "maybe_match"
NON_MATCH = "non_match"

KNOWN_NON_CANDIDATE_LABELS = {
    "uncertified write in",
    "write in",
}


@dataclass(frozen=True)
class LinkageResult:
    """Structured result returned by the matching function."""

    source_candidate_name: str
    suggested_candidate: str | None
    suggested_candidate_key: str | None
    name_similarity: float
    second_best_similarity: float
    similarity_margin: float
    classification: str
    match_method: str
    needs_review: bool


# ---------------------------------------------------------------------
# 1. Name cleaning
# ---------------------------------------------------------------------

def normalize_name(value):
    """Lowercase, remove accents/punctuation, and collapse spaces."""
    if pd.isna(value):
        return ""

    text = unicodedata.normalize("NFKD", str(value))

    letters = [
        character
        for character in text
        if not unicodedata.combining(character)
    ]

    text = "".join(letters).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def slugify(value):
    """Convert text into a filesystem-safe slug."""
    text = unicodedata.normalize("NFKD", str(value))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)

    return text.strip("-")


def district_number(value):
    """Read a district number from 1, '1', or 'District 1'."""
    if pd.isna(value):
        return None

    match = re.search(r"([1-4])", str(value))

    return int(match.group(1)) if match else None


def canonical_candidate_key(year, district, candidate):
    """Create a stable key from the official candidate-page name."""
    return f"{int(year)}|{int(district)}|{normalize_name(candidate)}"


# ---------------------------------------------------------------------
# 2. Similarity
# ---------------------------------------------------------------------

def jaro_winkler_name_similarity(left, right):
    """Jaro-Winkler similarity after project-standard normalization."""
    left_clean = normalize_name(left)
    right_clean = normalize_name(right)

    if not left_clean or not right_clean:
        return 0.0

    return float(
        jellyfish.jaro_winkler_similarity(left_clean, right_clean)
    )


def best_similarity_for_aliases(source_names, candidate_name):
    """Highest similarity between any source alias and one candidate."""
    best_score = 0.0

    for source_name in source_names:
        if pd.isna(source_name) or not str(source_name).strip():
            continue

        score = jaro_winkler_name_similarity(
            source_name,
            candidate_name,
        )

        best_score = max(best_score, score)

    return best_score


# ---------------------------------------------------------------------
# 3. Human-reviewed decisions
# ---------------------------------------------------------------------

def load_linkage_decisions(path=DECISIONS_PATH):
    """Load persistent human-reviewed decisions."""
    columns = [
        "year",
        "district",
        "source",
        "source_candidate_name",
        "decision",
        "canonical_candidate_name",
        "notes",
    ]

    if not path.exists():
        return pd.DataFrame(columns=columns)

    decisions = pd.read_csv(path)

    for column in columns:
        if column not in decisions.columns:
            decisions[column] = pd.NA

    decisions["year"] = pd.to_numeric(
        decisions["year"],
        errors="coerce",
    ).astype("Int64")

    decisions["district"] = pd.to_numeric(
        decisions["district"],
        errors="coerce",
    ).astype("Int64")

    decisions["source_name_norm"] = (
        decisions["source_candidate_name"].map(normalize_name)
    )

    decisions["decision"] = (
        decisions["decision"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
    )

    return decisions


def reviewed_decision(
    *,
    year,
    district,
    source,
    source_candidate_name,
    canonical_candidates,
    decisions,
):
    """Return a human-reviewed result when one has been recorded."""
    source_norm = normalize_name(source_candidate_name)

    rows = decisions.loc[
        decisions["year"].eq(year)
        & decisions["district"].eq(district)
        & decisions["source"].astype(str).eq(source)
        & decisions["source_name_norm"].eq(source_norm)
    ]

    if rows.empty:
        return None

    if len(rows) > 1:
        raise ValueError(
            "Multiple linkage decisions found for "
            f"{year}, D{district}, {source}, {source_candidate_name}"
        )

    decision_row = rows.iloc[0]
    decision = decision_row["decision"]

    if decision == NON_MATCH:
        return LinkageResult(
            source_candidate_name=source_candidate_name,
            suggested_candidate=None,
            suggested_candidate_key=None,
            name_similarity=0.0,
            second_best_similarity=0.0,
            similarity_margin=0.0,
            classification=NON_MATCH,
            match_method="human_review_non_match",
            needs_review=False,
        )

    # Blank or unknown decisions do not override automatic matching.
    if decision != MATCH:
        return None

    canonical_name = str(
        decision_row["canonical_candidate_name"]
    ).strip()

    if not canonical_name or canonical_name.lower() == "nan":
        raise ValueError(
            "A human-reviewed match needs canonical_candidate_name: "
            f"{source_candidate_name}"
        )

    canonical_norm = normalize_name(canonical_name)

    match = canonical_candidates.loc[
        canonical_candidates["candidate_norm"].eq(canonical_norm)
    ]

    if len(match) != 1:
        raise ValueError(
            "Reviewed canonical name does not uniquely identify a candidate: "
            f"{canonical_name}"
        )

    candidate = match.iloc[0]
    similarity = jaro_winkler_name_similarity(
        source_candidate_name,
        candidate["candidate"],
    )

    return LinkageResult(
        source_candidate_name=source_candidate_name,
        suggested_candidate=candidate["candidate"],
        suggested_candidate_key=candidate["candidate_key"],
        name_similarity=similarity,
        second_best_similarity=0.0,
        similarity_margin=similarity,
        classification=MATCH,
        match_method="human_review_match",
        needs_review=False,
    )


# ---------------------------------------------------------------------
# 4. Deterministic short-name matching
# ---------------------------------------------------------------------

def unique_token_match(source_candidate_name, canonical_candidates):
    """Match a short label only when it identifies exactly one candidate.

    Example:
        source:   Avalos
        official: Candace Avalos

    This is intentionally conservative:
    - at most 3 source tokens;
    - every source token must appear in the official name;
    - exactly one official candidate must satisfy the rule.
    """
    source_norm = normalize_name(source_candidate_name)

    if not source_norm:
        return None

    source_tokens = set(source_norm.split())

    if len(source_tokens) > 3:
        return None

    matches = []

    for _, candidate in canonical_candidates.iterrows():
        candidate_tokens = set(
            normalize_name(candidate["candidate"]).split()
        )

        if source_tokens.issubset(candidate_tokens):
            matches.append(candidate)

    return matches[0] if len(matches) == 1 else None


# ---------------------------------------------------------------------
# 5. Main matching function
# ---------------------------------------------------------------------

def link_source_record(
    *,
    year,
    district,
    source,
    source_candidate_name,
    alternate_source_names,
    canonical_candidates,
    decisions,
):
    """Link one source candidate label to an official candidate."""

    # Always block by year + district first.
    block = canonical_candidates.loc[
        canonical_candidates["year"].eq(year)
        & canonical_candidates["district"].eq(district)
    ].copy()

    if block.empty:
        return LinkageResult(
            source_candidate_name=source_candidate_name,
            suggested_candidate=None,
            suggested_candidate_key=None,
            name_similarity=0.0,
            second_best_similarity=0.0,
            similarity_margin=0.0,
            classification=NON_MATCH,
            match_method="no_candidates_in_block",
            needs_review=True,
        )

    # Human review wins.
    human = reviewed_decision(
        year=year,
        district=district,
        source=source,
        source_candidate_name=source_candidate_name,
        canonical_candidates=block,
        decisions=decisions,
    )

    if human is not None:
        return human

    # Primary name + optional aliases such as an ORESTAR filer name.
    source_names = [source_candidate_name] + list(
        alternate_source_names or []
    )

    source_norms = {
        normalize_name(value)
        for value in source_names
        if pd.notna(value) and str(value).strip()
    }

    primary_norm = normalize_name(source_candidate_name)

    if primary_norm in KNOWN_NON_CANDIDATE_LABELS:
        return LinkageResult(
            source_candidate_name=source_candidate_name,
            suggested_candidate=None,
            suggested_candidate_key=None,
            name_similarity=0.0,
            second_best_similarity=0.0,
            similarity_margin=0.0,
            classification=NON_MATCH,
            match_method="known_non_candidate",
            needs_review=False,
        )

    # Exact normalized name.
    exact = block.loc[
        block["candidate_norm"].isin(source_norms)
    ]

    if len(exact) == 1:
        candidate = exact.iloc[0]

        return LinkageResult(
            source_candidate_name=source_candidate_name,
            suggested_candidate=candidate["candidate"],
            suggested_candidate_key=candidate["candidate_key"],
            name_similarity=1.0,
            second_best_similarity=0.0,
            similarity_margin=1.0,
            classification=MATCH,
            match_method="exact_normalized_name",
            needs_review=False,
        )

    # Unique short label such as an ORESTAR surname-only workbook.
    token_candidate = unique_token_match(
        source_candidate_name,
        block,
    )

    if token_candidate is not None:
        return LinkageResult(
            source_candidate_name=source_candidate_name,
            suggested_candidate=token_candidate["candidate"],
            suggested_candidate_key=token_candidate["candidate_key"],
            name_similarity=1.0,
            second_best_similarity=0.0,
            similarity_margin=1.0,
            classification=MATCH,
            match_method="unique_token_containment",
            needs_review=False,
        )

    # Fuzzy matching for unresolved records.
    scores = []

    for candidate in block.itertuples(index=False):
        scores.append(
            {
                "candidate": candidate.candidate,
                "candidate_key": candidate.candidate_key,
                "similarity": best_similarity_for_aliases(
                    source_names,
                    candidate.candidate,
                ),
            }
        )

    scores = sorted(
        scores,
        key=lambda item: item["similarity"],
        reverse=True,
    )

    best = scores[0]
    second_best = (
        scores[1]["similarity"]
        if len(scores) > 1
        else 0.0
    )
    margin = best["similarity"] - second_best

    if (
        best["similarity"] >= LINKAGE_MATCH_THRESHOLD
        and margin >= LINKAGE_AMBIGUITY_MARGIN
    ):
        classification = MATCH
        method = "jaro_winkler_high"
        needs_review = False

    elif best["similarity"] >= LINKAGE_MAYBE_THRESHOLD:
        classification = MAYBE_MATCH
        needs_review = True

        ambiguous = (
            best["similarity"] >= LINKAGE_MATCH_THRESHOLD
            and margin < LINKAGE_AMBIGUITY_MARGIN
        )

        method = (
            "jaro_winkler_ambiguous"
            if ambiguous
            else "jaro_winkler_medium"
        )

    else:
        classification = NON_MATCH
        method = "jaro_winkler_low"
        needs_review = True

    return LinkageResult(
        source_candidate_name=source_candidate_name,
        suggested_candidate=best["candidate"],
        suggested_candidate_key=best["candidate_key"],
        name_similarity=float(best["similarity"]),
        second_best_similarity=float(second_best),
        similarity_margin=float(margin),
        classification=classification,
        match_method=method,
        needs_review=needs_review,
    )

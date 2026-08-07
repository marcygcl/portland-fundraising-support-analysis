"""Candidate record linkage across Portland data sources.

Method
------
1. Normalize names.
2. Block candidates by election year + district.
3. Apply explicit human-reviewed decisions when available.
4. Match exact normalized full names.
5. Recognize known non-candidate labels.
6. Match unique partial/token names within the year + district block.
7. Calculate Jaro-Winkler similarities for unresolved records.
8. Classify as match / maybe_match / non_match.

The partial-name rule is especially useful for ORESTAR, where workbook
filenames often contain only a surname (for example, "Avalos.xls").

We only accept a partial-name match when it identifies exactly ONE official
candidate inside the already restricted year + district block. Ambiguous cases
continue to fuzzy matching / manual review rather than being guessed.
"""

from __future__ import annotations

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


# ---------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------

DECISIONS_PATH = (
    CONFIG_DIR
    / "linkage_decisions.csv"
)

MATCH = "match"
MAYBE_MATCH = "maybe_match"
NON_MATCH = "non_match"


# Labels that can appear in election-result sources but are not actual
# candidate records that should be linked to the official candidate universe.
KNOWN_NON_CANDIDATE_LABELS = {
    "uncertified write in",
    "write in",
}


# ---------------------------------------------------------------------
# Linkage result
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class LinkageResult:
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
# Name normalization
# ---------------------------------------------------------------------

def normalize_name(
    value,
) -> str:
    """Normalize a candidate name while preserving meaningful tokens."""

    if pd.isna(value):
        return ""

    text = unicodedata.normalize(
        "NFKD",
        str(value),
    )

    text = "".join(
        character
        for character in text
        if not unicodedata.combining(
            character
        )
    )

    text = text.lower()

    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def slugify(
    value,
) -> str:
    """Convert arbitrary text into a filesystem-safe slug."""

    text = unicodedata.normalize(
        "NFKD",
        str(value),
    )

    text = (
        text
        .encode(
            "ascii",
            "ignore",
        )
        .decode("ascii")
        .lower()
    )

    text = re.sub(
        r"[^a-z0-9]+",
        "-",
        text,
    )

    return text.strip("-")


def district_number(
    value,
) -> int | None:
    """Parse district number from 1, '1', or 'District 1'."""

    if pd.isna(value):
        return None

    match = re.search(
        r"([1-4])",
        str(value),
    )

    return (
        int(
            match.group(1)
        )
        if match
        else None
    )


def canonical_candidate_key(
    year: int,
    district: int,
    candidate: str,
) -> str:
    """Stable key based on the official candidate-page name."""

    return (
        f"{int(year)}|"
        f"{int(district)}|"
        f"{normalize_name(candidate)}"
    )


# ---------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------

def jaro_winkler_name_similarity(
    left,
    right,
) -> float:
    """Jaro-Winkler similarity after project-standard normalization."""

    left_clean = normalize_name(
        left
    )

    right_clean = normalize_name(
        right
    )

    if (
        not left_clean
        or not right_clean
    ):
        return 0.0

    return float(
        jellyfish
        .jaro_winkler_similarity(
            left_clean,
            right_clean,
        )
    )


def _best_similarity_for_aliases(
    source_names: list[str],
    candidate_name: str,
) -> float:
    """Highest similarity between any source alias and a candidate."""

    clean_names = [
        str(value).strip()
        for value in source_names
        if (
            pd.notna(value)
            and str(value).strip()
        )
    ]

    if not clean_names:
        return 0.0

    return max(
        jaro_winkler_name_similarity(
            source_name,
            candidate_name,
        )
        for source_name
        in clean_names
    )


# ---------------------------------------------------------------------
# Human-reviewed linkage decisions
# ---------------------------------------------------------------------

def load_linkage_decisions(
    path=DECISIONS_PATH,
) -> pd.DataFrame:
    """Load persistent human-reviewed linkage decisions."""

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
        return pd.DataFrame(
            columns=columns
        )

    frame = pd.read_csv(
        path
    )

    for column in columns:
        if column not in frame.columns:
            frame[
                column
            ] = pd.NA

    frame[
        "year"
    ] = pd.to_numeric(
        frame["year"],
        errors="coerce",
    ).astype(
        "Int64"
    )

    frame[
        "district"
    ] = pd.to_numeric(
        frame["district"],
        errors="coerce",
    ).astype(
        "Int64"
    )

    frame[
        "source_name_norm"
    ] = frame[
        "source_candidate_name"
    ].map(
        normalize_name
    )

    frame[
        "decision"
    ] = (
        frame[
            "decision"
        ]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
    )

    return frame


def reviewed_decision(
    *,
    year: int,
    district: int,
    source: str,
    source_candidate_name: str,
    canonical_candidates: pd.DataFrame,
    decisions: pd.DataFrame,
) -> LinkageResult | None:
    """Return an explicit human decision when one exists."""

    source_norm = normalize_name(
        source_candidate_name
    )

    matches = decisions.loc[
        decisions[
            "year"
        ].eq(
            year
        )
        & decisions[
            "district"
        ].eq(
            district
        )
        & decisions[
            "source"
        ].astype(str).eq(
            source
        )
        & decisions[
            "source_name_norm"
        ].eq(
            source_norm
        )
    ]

    if matches.empty:
        return None

    # Duplicate manual decisions are themselves a data-quality issue.
    if len(matches) > 1:
        raise ValueError(
            "Multiple linkage decisions found for "
            f"{year}, D{district}, "
            f"{source}, "
            f"{source_candidate_name}"
        )

    decision_row = (
        matches.iloc[0]
    )

    decision = (
        decision_row[
            "decision"
        ]
    )

    # ---------------------------------------------------------------
    # Human-confirmed non-match
    # ---------------------------------------------------------------

    if decision == NON_MATCH:
        return LinkageResult(
            source_candidate_name=
                source_candidate_name,

            suggested_candidate=None,

            suggested_candidate_key=None,

            name_similarity=0.0,

            second_best_similarity=0.0,

            similarity_margin=0.0,

            classification=NON_MATCH,

            match_method=
                "human_review_non_match",

            needs_review=False,
        )

    # Unknown / blank decisions should not override automation.
    if decision != MATCH:
        return None

    # ---------------------------------------------------------------
    # Human-confirmed match
    # ---------------------------------------------------------------

    canonical_name = str(
        decision_row[
            "canonical_candidate_name"
        ]
    ).strip()

    if (
        not canonical_name
        or canonical_name.lower()
        == "nan"
    ):
        raise ValueError(
            "A human-reviewed match "
            "needs canonical_candidate_name: "
            f"{source_candidate_name}"
        )

    candidate_norm = (
        normalize_name(
            canonical_name
        )
    )

    canonical_match = (
        canonical_candidates.loc[
            canonical_candidates[
                "candidate_norm"
            ].eq(
                candidate_norm
            )
        ]
    )

    if len(
        canonical_match
    ) != 1:
        raise ValueError(
            "Reviewed canonical candidate "
            "name does not uniquely identify "
            "a candidate in this year/district: "
            f"{canonical_name}"
        )

    row = (
        canonical_match.iloc[0]
    )

    similarity = (
        jaro_winkler_name_similarity(
            source_candidate_name,
            row["candidate"],
        )
    )

    return LinkageResult(
        source_candidate_name=
            source_candidate_name,

        suggested_candidate=
            row["candidate"],

        suggested_candidate_key=
            row["candidate_key"],

        name_similarity=
            similarity,

        second_best_similarity=
            0.0,

        similarity_margin=
            similarity,

        classification=
            MATCH,

        match_method=
            "human_review_match",

        needs_review=
            False,
    )


# ---------------------------------------------------------------------
# Deterministic partial-name matching
# ---------------------------------------------------------------------

def _unique_token_containment_match(
    *,
    source_candidate_name: str,
    canonical_candidates: pd.DataFrame,
) -> pd.Series | None:
    """Match a short source name to exactly one canonical candidate.

    Example:

        source:     Avalos
        canonical:  Candace Avalos

        source tokens    = {"avalos"}
        candidate tokens = {"candace", "avalos"}

    The match is accepted only when exactly one official candidate in
    the already-blocked district contains every source token.

    This deliberately does not implement nickname inference. Cases such as
    Chris/Christopher or Mitch/Mitchell remain available for fuzzy/manual
    review unless another exact token is sufficient.
    """

    source_norm = normalize_name(
        source_candidate_name
    )

    if not source_norm:
        return None

    source_tokens = set(
        source_norm.split()
    )

    if not source_tokens:
        return None

    # This rule is intended primarily for short labels such as ORESTAR
    # workbook stems. Long organization/committee names are not appropriate
    # for deterministic token matching.
    if len(source_tokens) > 3:
        return None

    matching_indices = []

    for index, row in (
        canonical_candidates.iterrows()
    ):
        candidate_norm = (
            normalize_name(
                row["candidate"]
            )
        )

        candidate_tokens = set(
            candidate_norm.split()
        )

        if source_tokens.issubset(
            candidate_tokens
        ):
            matching_indices.append(
                index
            )

    if len(
        matching_indices
    ) != 1:
        return None

    return canonical_candidates.loc[
        matching_indices[0]
    ]


# ---------------------------------------------------------------------
# Main linkage function
# ---------------------------------------------------------------------

def link_source_record(
    *,
    year: int,
    district: int,
    source: str,
    source_candidate_name: str,
    alternate_source_names: list[str] | None,
    canonical_candidates: pd.DataFrame,
    decisions: pd.DataFrame,
) -> LinkageResult:
    """Link one source candidate label to an official candidate.

    Matching is always restricted to the same election year and district.

    Order:
        human decision
        -> known non-candidate
        -> exact normalized name
        -> unique token containment
        -> Jaro-Winkler
        -> manual review when unresolved
    """

    # -----------------------------------------------------------------
    # Block by year + district
    # -----------------------------------------------------------------

    block = (
        canonical_candidates.loc[
            canonical_candidates[
                "year"
            ].eq(
                year
            )
            & canonical_candidates[
                "district"
            ].eq(
                district
            )
        ]
        .copy()
    )

    if block.empty:
        return LinkageResult(
            source_candidate_name=
                source_candidate_name,

            suggested_candidate=None,

            suggested_candidate_key=None,

            name_similarity=0.0,

            second_best_similarity=0.0,

            similarity_margin=0.0,

            classification=NON_MATCH,

            match_method=
                "no_candidates_in_block",

            needs_review=True,
        )

    # -----------------------------------------------------------------
    # 1. Explicit human-reviewed decision
    # -----------------------------------------------------------------

    human = reviewed_decision(
        year=year,
        district=district,
        source=source,
        source_candidate_name=
            source_candidate_name,
        canonical_candidates=block,
        decisions=decisions,
    )

    if human is not None:
        return human

    # -----------------------------------------------------------------
    # Prepare aliases
    # -----------------------------------------------------------------

    source_names = [
        source_candidate_name
    ] + list(
        alternate_source_names
        or []
    )

    source_norms = {
        normalize_name(
            value
        )
        for value
        in source_names
        if (
            pd.notna(value)
            and str(value).strip()
        )
    }

    source_primary_norm = (
        normalize_name(
            source_candidate_name
        )
    )

    # -----------------------------------------------------------------
    # 2. Known labels that are not candidates
    # -----------------------------------------------------------------

    if (
        source_primary_norm
        in KNOWN_NON_CANDIDATE_LABELS
    ):
        return LinkageResult(
            source_candidate_name=
                source_candidate_name,

            suggested_candidate=None,

            suggested_candidate_key=None,

            name_similarity=0.0,

            second_best_similarity=0.0,

            similarity_margin=0.0,

            classification=NON_MATCH,

            match_method=
                "known_non_candidate",

            needs_review=False,
        )

    # -----------------------------------------------------------------
    # 3. Exact normalized name
    # -----------------------------------------------------------------

    exact = block.loc[
        block[
            "candidate_norm"
        ].isin(
            source_norms
        )
    ]

    if len(exact) == 1:
        row = exact.iloc[0]

        return LinkageResult(
            source_candidate_name=
                source_candidate_name,

            suggested_candidate=
                row["candidate"],

            suggested_candidate_key=
                row["candidate_key"],

            name_similarity=1.0,

            second_best_similarity=0.0,

            similarity_margin=1.0,

            classification=MATCH,

            match_method=
                "exact_normalized_name",

            needs_review=False,
        )

    # -----------------------------------------------------------------
    # 4. Unique partial/token match
    # -----------------------------------------------------------------
    #
    # IMPORTANT:
    # Use the PRIMARY source candidate label here.
    #
    # ORESTAR candidate indexes often use workbook stems such as:
    #
    #     Avalos
    #     Penson
    #     Koyama
    #
    # Those are appropriate for this deterministic rule.
    #
    # We deliberately do not use arbitrary committee/filer aliases here,
    # because organization names could create unintended token matches.
    # -----------------------------------------------------------------

    token_match = (
        _unique_token_containment_match(
            source_candidate_name=
                source_candidate_name,
            canonical_candidates=
                block,
        )
    )

    if token_match is not None:
        return LinkageResult(
            source_candidate_name=
                source_candidate_name,

            suggested_candidate=
                token_match[
                    "candidate"
                ],

            suggested_candidate_key=
                token_match[
                    "candidate_key"
                ],

            name_similarity=1.0,

            second_best_similarity=0.0,

            similarity_margin=1.0,

            classification=MATCH,

            match_method=
                "unique_token_containment",

            needs_review=False,
        )

    # -----------------------------------------------------------------
    # 5. Jaro-Winkler within district
    # -----------------------------------------------------------------

    scores = []

    for row in block.itertuples(
        index=False
    ):
        similarity = (
            _best_similarity_for_aliases(
                source_names,
                row.candidate,
            )
        )

        scores.append(
            {
                "candidate":
                    row.candidate,

                "candidate_key":
                    row.candidate_key,

                "similarity":
                    similarity,
            }
        )

    scores = sorted(
        scores,
        key=lambda item:
            item[
                "similarity"
            ],
        reverse=True,
    )

    best = (
        scores[0]
    )

    second_best = (
        scores[1][
            "similarity"
        ]
        if len(scores) > 1
        else 0.0
    )

    margin = (
        best[
            "similarity"
        ]
        - second_best
    )

    # -----------------------------------------------------------------
    # High-confidence fuzzy match
    # -----------------------------------------------------------------

    if (
        best[
            "similarity"
        ]
        >= LINKAGE_MATCH_THRESHOLD
        and margin
        >= LINKAGE_AMBIGUITY_MARGIN
    ):
        classification = (
            MATCH
        )

        method = (
            "jaro_winkler_high"
        )

        needs_review = (
            False
        )

    # -----------------------------------------------------------------
    # Potential / ambiguous match
    # -----------------------------------------------------------------

    elif (
        best[
            "similarity"
        ]
        >= LINKAGE_MAYBE_THRESHOLD
    ):
        classification = (
            MAYBE_MATCH
        )

        method = (
            "jaro_winkler_ambiguous"
            if (
                best[
                    "similarity"
                ]
                >= LINKAGE_MATCH_THRESHOLD
                and margin
                < LINKAGE_AMBIGUITY_MARGIN
            )
            else
            "jaro_winkler_medium"
        )

        needs_review = (
            True
        )

    # -----------------------------------------------------------------
    # Low-similarity record
    # -----------------------------------------------------------------

    else:
        classification = (
            NON_MATCH
        )

        method = (
            "jaro_winkler_low"
        )

        # Low similarity does not automatically mean that the source row
        # should be silently discarded. It may represent a candidate-name
        # variant, a candidate absent from the official universe, or a source
        # data issue. Keep it visible for review.
        needs_review = (
            True
        )

    return LinkageResult(
        source_candidate_name=
            source_candidate_name,

        suggested_candidate=
            best[
                "candidate"
            ],

        suggested_candidate_key=
            best[
                "candidate_key"
            ],

        name_similarity=float(
            best[
                "similarity"
            ]
        ),

        second_best_similarity=float(
            second_best
        ),

        similarity_margin=float(
            margin
        ),

        classification=
            classification,

        match_method=
            method,

        needs_review=
            needs_review,
    )
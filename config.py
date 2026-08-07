"""Project-level settings.

Only settings that a researcher may reasonably need to change belong here.
"""

# ---------------------------------------------------------------------
# Portland contribution JSON/GeoJSON endpoints
# ---------------------------------------------------------------------

PORTLAND_CONTRIBUTION_URLS = {
    "contributions.json": (
        "https://api.openelectionsportland.org/contributionsgeo"
    ),
    "external-contributions.json": (
        "https://api.openelectionsportland.org/external-contributionsgeo"
    ),
}

# ---------------------------------------------------------------------
# Official Portland candidate pages
# ---------------------------------------------------------------------
CANDIDATE_PAGES = {
    2024: (
        "https://www.portland.gov/auditor/elections/"
        "run4office/2024-city-candidates"
    ),
    2026: (
        "https://www.portland.gov/auditor/elections/"
        "run4office/2026-city-candidates"
    ),
}

USER_AGENT = (
    "Mozilla/5.0 "
    "(Portland campaign finance research project; public election data)"
)

# ---------------------------------------------------------------------
# report2025 / VoteKit inputs
# ---------------------------------------------------------------------
REPORT2025_DISTRICTS = {
    2024: [1, 2, 3, 4],
}

# ---------------------------------------------------------------------
# Record-linkage thresholds
# ---------------------------------------------------------------------
# Matching is always blocked by election year + district first.
#
# exact normalized names                  -> MATCH
# best Jaro-Winkler >= MATCH_THRESHOLD    -> MATCH if not ambiguous
# MAYBE_THRESHOLD <= score < MATCH        -> MAYBE_MATCH
# lower scores                            -> NON_MATCH
#
# A high score can still be MAYBE_MATCH if the best and second-best
# candidates are too similar to each other.
LINKAGE_MATCH_THRESHOLD = 0.95
LINKAGE_MAYBE_THRESHOLD = 0.85
LINKAGE_AMBIGUITY_MARGIN = 0.03

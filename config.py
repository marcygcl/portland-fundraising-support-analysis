"""Project settings that a researcher may reasonably want to change.

Keep this file small:
- URLs / configured years / districts / thresholds belong here.
- cleaning logic belongs in scripts or helpers.
- analysis choices belong in notebooks.
"""

# Portland contribution API
PORTLAND_CONTRIBUTION_URLS = {
    "contributions.json":
        "https://api.openelectionsportland.org/contributionsgeo",
    "external-contributions.json":
        "https://api.openelectionsportland.org/external-contributionsgeo",
}

# Official Portland candidate pages
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

# A descriptive user agent is polite when downloading public web data.
USER_AGENT = (
    "Mozilla/5.0 "
    "(Portland campaign finance research project; public election data)"
)

# VoteKit / report2025
REPORT2025_DISTRICTS = {
    2024: [1, 2, 3, 4],
}

# Candidate-name linkage
# Names are always compared within the same election year + district.
LINKAGE_MATCH_THRESHOLD = 0.95
LINKAGE_MAYBE_THRESHOLD = 0.85
LINKAGE_AMBIGUITY_MARGIN = 0.03

# Candidate profiles

## Question / purpose

Human-curated qualitative context on each candidate — background, prior
public roles, campaign themes — used to interpret the quantitative
finance and ballot-support analysis (especially to explain candidates
who over- or under-perform what their fundraising predicts).

## Main data sources

- Portland Auditor candidate pages, campaign filings, campaign websites,
  and other public sources (manually researched).

## Relevant processed datasets

- `data/processed/candidates/` — the structured candidate master,
  source crosswalk, and coverage tables. Structured/reusable candidate
  data lives there, not in this folder — this folder is qualitative and
  human-written.

## Contents

- `profile_template.md` — scaffold used to create new candidate files.
- `2024/`, `2026/` — one Markdown file per official candidate (mostly
  scaffolded, filled in as research happens).
- `2024_candidate_bios.md`, `2026_d3_d4_candidate_bios.md` — fuller
  narrative write-ups, originally companion documents to the
  `finance_vs_ballot_support` Question-3 analysis, kept here as reusable
  candidate context.

## Relevant builder scripts

- `scripts/08_initialize_candidate_profiles.py` — creates the
  per-candidate scaffold files. Never overwrites an existing file.

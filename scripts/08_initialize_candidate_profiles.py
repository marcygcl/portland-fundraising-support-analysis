#!/usr/bin/env python3
"""Create one qualitative Markdown scaffold per official candidate.

Existing candidate Markdown files are never overwritten.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import argparse

import pandas as pd

from config import CANDIDATE_PAGES
from helpers.linkage import slugify
from helpers.paths import CANDIDATE_PROFILES, PROCESSED


def value_or_missing(value):
    if pd.isna(value):
        return "Not available in extracted filing data"

    text = str(value).strip()
    return text if text else "Not available in extracted filing data"


def main(year):
    master_path = (
        PROCESSED
        / "master"
        / f"candidate_master_{year}.csv"
    )

    if not master_path.exists():
        raise FileNotFoundError(
            f"Run 07_build_candidate_master.py first: {master_path}"
        )

    master = pd.read_csv(master_path, low_memory=False)

    output_dir = CANDIDATE_PROFILES / str(year)
    output_dir.mkdir(parents=True, exist_ok=True)

    created = 0
    skipped = 0

    for row in master.itertuples(index=False):
        if getattr(row, "is_non_candidate_row", False):
            continue

        path = output_dir / f"{slugify(row.candidate)}.md"

        if path.exists():
            skipped += 1
            continue

        content = f"""# {row.candidate}

**Election:** {year} Portland City Council  
**District:** District {int(row.district)}  
**Filing status:** {value_or_missing(getattr(row, "filing_status", None))}  
**Campaign website:** {value_or_missing(getattr(row, "campaign_website", None))}

## Quick source-derived profile

- **Occupation:** {value_or_missing(getattr(row, "occupation", None))}
- **Prior government experience:** {value_or_missing(getattr(row, "prior_govt_experience", None))}
- **Public funding program:** {value_or_missing(getattr(row, "public_funding_program", None))}
- **Data coverage:** {value_or_missing(getattr(row, "coverage_status", None))}

## Short bio

_TODO: Write a concise, sourced 3-5 sentence bio._

## Political and community background

_TODO: Add relevant prior office, campaigns, organizations, endorsements, or community roles._

## Campaign themes and issues

_TODO: Summarize major campaign themes or issue positions from public sources._

## Campaign finance notes

_TODO: Add descriptive fundraising/spending observations after the finance notebooks are finalized._

## Interesting context / case-study notes

_TODO: Add qualitative details useful for interpreting the quantitative analysis._

## Sources

- Portland Auditor candidate page: {CANDIDATE_PAGES.get(year, "")}
- Candidate filing fields: `data/clean/candidate_filings/{year}/candidate_profile_fields.csv`
- Candidate master: `data/processed/master/candidate_master_{year}.csv`

> Keep factual claims sourced. Do not infer missing biographical information.
"""

        path.write_text(content, encoding="utf-8")
        created += 1

    index_lines = [
        f"# {year} Candidate Profiles",
        "",
        "Human-curated qualitative candidate profiles.",
        "",
    ]

    for path in sorted(output_dir.glob("*.md")):
        if path.name == "README.md":
            continue
        index_lines.append(
            f"- [{path.stem.replace('-', ' ').title()}]({path.name})"
        )

    (output_dir / "README.md").write_text(
        "\n".join(index_lines) + "\n",
        encoding="utf-8",
    )

    print(f"Created {created} candidate profile files.")
    print(f"Skipped {skipped} existing files.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    args = parser.parse_args()
    main(args.year)

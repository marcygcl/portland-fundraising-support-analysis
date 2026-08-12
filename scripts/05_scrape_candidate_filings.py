"""Scrape Portland's official City Council candidate page.

Observed layouts
----------------
2024: district headings + candidate headings + document links
2026: district headings + candidate tables

Keeping two small parsers is easier to debug than one "smart" parser.

Outputs
-------
candidate_list.csv
    one row per candidate-document combination

candidate_index.csv
    one row per official candidate
"""

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import requests
from bs4 import BeautifulSoup

from config import CANDIDATE_PAGES, USER_AGENT
from helpers.linkage import (
    canonical_candidate_key,
    district_number,
    normalize_name,
)
from helpers.paths import CLEAN, RAW


DISTRICT_HEADING_RE = re.compile(
    r"Councilor,?\s+(District\s+\d)",
    re.IGNORECASE,
)
WITHDRAWN_LABEL_RE = re.compile(
    r"Candidacy Withdrawn|Qualification Rescinded",
    re.IGNORECASE,
)


def clean_text(tag):
    """Return readable text from one BeautifulSoup element."""
    if tag is None:
        return ""

    text = tag.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def district_from_heading(text):
    match = DISTRICT_HEADING_RE.search(text)
    return match.group(1).title() if match else None


def is_councilor_heading(text):
    return "councilor" in text.lower()


def parse_heading_list_page(soup, year, base_url):
    """Parse the heading/list layout observed for 2024."""
    rows = []
    headings = soup.find_all(["h2", "h3"])

    for heading_index, heading in enumerate(headings):
        heading_text = clean_text(heading)

        if heading.name != "h2" or not is_councilor_heading(heading_text):
            continue

        district_label = district_from_heading(heading_text)

        if not district_label:
            continue

        # The next h2 marks the end of this district section.
        next_h2 = None

        for later in headings[heading_index + 1:]:
            if later.name == "h2":
                next_h2 = later
                break

        candidate_headings = []

        for later in headings[heading_index + 1:]:
            if later is next_h2:
                break

            if later.name == "h3":
                candidate_headings.append(later)

        for candidate_index, candidate_heading in enumerate(
            candidate_headings
        ):
            raw_name = clean_text(candidate_heading)
            status = "Qualified"

            if WITHDRAWN_LABEL_RE.search(raw_name):
                status = (
                    "Candidacy Withdrawn"
                    if "withdrawn" in raw_name.lower()
                    else "Qualification Rescinded"
                )

            name = (
                raw_name.split(":", 1)[-1]
                if ":" in raw_name
                else raw_name
            )
            name = name.strip("* ").strip()

            next_boundary = (
                candidate_headings[candidate_index + 1]
                if candidate_index + 1 < len(candidate_headings)
                else next_h2
            )

            found_pdf = False
            candidate_row_indexes = []

            for element in candidate_heading.find_all_next():
                if next_boundary is not None and element is next_boundary:
                    break

                if element.name == "a" and element.get("href"):
                    href = element["href"]
                    label = clean_text(element) or "Candidate Filing Application"

                    looks_like_document = (
                        "/documents/" in href
                        or href.lower().endswith(".pdf")
                    )

                    if looks_like_document:
                        rows.append(
                            {
                                "year": year,
                                "district_label": district_label,
                                "name": name,
                                "filing_status": status,
                                "filing_date": "",
                                "pdf_label": label,
                                "pdf_url": urljoin(base_url, href),
                            }
                        )
                        candidate_row_indexes.append(len(rows) - 1)
                        found_pdf = True

                if element.name == "li":
                    text = clean_text(element)

                    if text.lower().startswith("date filed"):
                        date_value = text.split(":", 1)[-1].strip()

                        for row_index in candidate_row_indexes:
                            rows[row_index]["filing_date"] = date_value

                    if "withdrawn" in text.lower() and "date" in text.lower():
                        for row_index in candidate_row_indexes:
                            rows[row_index]["filing_status"] = (
                                "Candidacy Withdrawn"
                            )

            # Keep official candidates even if no filing PDF is linked.
            if not found_pdf:
                rows.append(
                    {
                        "year": year,
                        "district_label": district_label,
                        "name": name,
                        "filing_status": status,
                        "filing_date": "",
                        "pdf_label": "",
                        "pdf_url": "",
                    }
                )

    return rows


def parse_table_page(soup, year, base_url):
    """Parse the candidate-table layout observed for 2026."""
    rows = []

    for heading in soup.find_all(["h2", "h3"]):
        heading_text = clean_text(heading)

        if not is_councilor_heading(heading_text):
            continue

        district_label = district_from_heading(heading_text)

        if not district_label:
            continue

        table = heading.find_next("table")

        if table is None:
            continue

        for table_row in table.find_all("tr"):
            cells = table_row.find_all("td")

            if len(cells) < 3:
                continue

            name = clean_text(cells[0])

            if not name or name.lower() == "name":
                continue

            status = clean_text(cells[1])
            filing_date = clean_text(cells[2])
            links = cells[3].find_all("a") if len(cells) > 3 else []

            if not links:
                rows.append(
                    {
                        "year": year,
                        "district_label": district_label,
                        "name": name,
                        "filing_status": status,
                        "filing_date": filing_date,
                        "pdf_label": "",
                        "pdf_url": "",
                    }
                )

            for link in links:
                href = link.get("href", "")

                if not href:
                    continue

                rows.append(
                    {
                        "year": year,
                        "district_label": district_label,
                        "name": name,
                        "filing_status": status,
                        "filing_date": filing_date,
                        "pdf_label": (
                            clean_text(link)
                            or "Candidate Filing Application"
                        ),
                        "pdf_url": urljoin(base_url, href),
                    }
                )

    return rows


def main(year, force=False):
    if year not in CANDIDATE_PAGES:
        raise ValueError(f"No candidate page configured for {year}")

    url = CANDIDATE_PAGES[year]

    raw_html_dir = RAW / "candidate_filings" / str(year) / "html"
    clean_dir = CLEAN / "candidate_filings" / str(year)

    html_path = raw_html_dir / "candidate_page.html"
    list_output = clean_dir / "candidate_list.csv"
    index_output = clean_dir / "candidate_index.csv"

    if list_output.exists() and index_output.exists() and not force:
        print(f"SKIP  candidate-page outputs already exist for {year}")
        return

    raw_html_dir.mkdir(parents=True, exist_ok=True)
    clean_dir.mkdir(parents=True, exist_ok=True)

    # 1. Download the official page, or reuse the raw snapshot.
    if html_path.exists() and not force:
        html = html_path.read_text(encoding="utf-8")
        print(f"READ  existing raw HTML {html_path}")
    else:
        print(f"GET   {url}")

        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
        response.raise_for_status()

        html = response.text
        html_path.write_text(html, encoding="utf-8")

        print(f"SAVED {html_path}")

    # 2. Detect the observed layout and parse candidate rows.
    soup = BeautifulSoup(html, "html.parser")

    if soup.find_all("table"):
        rows = parse_table_page(soup, year, url)
        layout = "table"
    else:
        rows = parse_heading_list_page(soup, year, url)
        layout = "heading_list"

    if not rows:
        raise RuntimeError(
            "No City Council candidate rows were parsed. "
            "The official page layout may have changed."
        )

    # 3. Standardize official candidate identity.
    data = pd.DataFrame(rows)
    data["district"] = data["district_label"].map(district_number)
    data = data.loc[data["district"].notna()].copy()
    data["district"] = data["district"].astype(int)

    data["candidate"] = data["name"].astype(str).str.strip()
    data["candidate_norm"] = data["candidate"].map(normalize_name)

    data["candidate_key"] = [
        canonical_candidate_key(year, district, candidate)
        for district, candidate in zip(
            data["district"],
            data["candidate"],
        )
    ]
    data["page_layout"] = layout

    # Candidate-document table.
    data.to_csv(list_output, index=False)

    # 4. Collapse to one row per official candidate.
    candidate_index = (
        data.groupby(
            [
                "year",
                "district",
                "candidate",
                "candidate_norm",
                "candidate_key",
            ],
            as_index=False,
        )
        .agg(
            filing_status=("filing_status", "last"),
            filing_date=("filing_date", "last"),
            document_count=(
                "pdf_url",
                lambda values: values.fillna("").ne("").sum(),
            ),
            has_pdf=(
                "pdf_url",
                lambda values: values.fillna("").ne("").any(),
            ),
        )
        .sort_values(["district", "candidate"])
    )

    candidate_index.to_csv(index_output, index=False)

    print(f"SAVED {list_output}")
    print(f"SAVED {index_output}")
    print(f"Official candidates: {len(candidate_index)}")
    print(f"Candidate-document rows: {len(data)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    main(year=args.year, force=args.force)

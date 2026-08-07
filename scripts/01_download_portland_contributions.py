#!/usr/bin/env python3
"""Download the Portland contribution JSON/GeoJSON snapshots once."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import argparse
import json

import requests

from config import PORTLAND_CONTRIBUTION_URLS, USER_AGENT
from helpers.paths import RAW


OUTPUT_DIR = RAW / "portland_contributions"


def validate_json(path):
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    valid = (
        isinstance(data, list)
        or (
            isinstance(data, dict)
            and data.get("type") in {"FeatureCollection", "Feature"}
        )
    )

    if not valid:
        raise ValueError(
            f"{path.name} does not look like the expected JSON/GeoJSON source."
        )


def download_file(*, url, output_path, force):
    if output_path.exists() and not force:
        print(f"SKIP  {output_path} already exists")
        return

    if not url:
        raise ValueError(
            f"No official URL configured for {output_path.name}. "
            "Add it to config.py or copy the existing raw file into place."
        )

    print(f"GET   {url}")
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=120,
    )
    response.raise_for_status()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(response.content)
    validate_json(output_path)

    print(f"SAVED {output_path}")


def main(force=False):
    for filename, url in PORTLAND_CONTRIBUTION_URLS.items():
        download_file(
            url=url,
            output_path=OUTPUT_DIR / filename,
            force=force,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    main(force=args.force)

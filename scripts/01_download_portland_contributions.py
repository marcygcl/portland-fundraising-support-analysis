"""Download Portland contribution JSON/GeoJSON snapshots.

This script only acquires raw data.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests

from config import PORTLAND_CONTRIBUTION_URLS, USER_AGENT
from helpers.paths import RAW


OUTPUT_DIR = RAW / "portland_contributions"


def validate_json(path):
    """Check that a downloaded file looks like the expected JSON/GeoJSON."""
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    is_list = isinstance(data, list)
    is_geojson = (
        isinstance(data, dict)
        and data.get("type") in {"FeatureCollection", "Feature"}
    )

    if not is_list and not is_geojson:
        raise ValueError(
            f"{path.name} does not look like the expected JSON/GeoJSON source."
        )


def download_file(url, output_path, force=False):
    """Download one raw file unless it already exists."""
    if output_path.exists() and not force:
        print(f"SKIP  {output_path} already exists")
        return

    if not url:
        raise ValueError(f"No URL configured for {output_path.name}")

    print(f"GET   {url}")

    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=120,
    )
    response.raise_for_status()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(response.content)

    # Catch HTML/error responses immediately.
    validate_json(output_path)

    print(f"SAVED {output_path}")


def main(force=False):
    for filename, url in PORTLAND_CONTRIBUTION_URLS.items():
        download_file(
            url,
            OUTPUT_DIR / filename,
            force=force,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force",
        action="store_true",
        help="Download again even if the raw files already exist.",
    )
    args = parser.parse_args()

    main(force=args.force)

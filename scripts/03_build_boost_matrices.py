#!/usr/bin/env python3
"""Rebuild 2024 Portland boost matrices from report2025 VoteKit profiles."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import argparse
from itertools import combinations

import numpy as np
import pandas as pd

from votekit.matrices import boost_matrix
from votekit.pref_profile import PreferenceProfile
from votekit.utils import mentions

from config import REPORT2025_DISTRICTS
from helpers.linkage import normalize_name
from helpers.paths import PROCESSED, RAW


def main(*, year, force=False):
    districts = REPORT2025_DISTRICTS.get(year)
    if not districts:
        raise ValueError(f"No report2025 configuration for year {year}")

    profile_dir = (
        RAW
        / "report2025"
        / str(year)
        / "cleaned_votekit_profiles"
    )
    output_dir = PROCESSED / "boost" / str(year)

    expected = [
        output_dir / f"boost_matrix_D{district}.csv"
        for district in districts
    ] + [
        output_dir / "candidate_index.csv",
        output_dir / "boost_directional_long.csv",
        output_dir / "boost_pairs.csv",
    ]

    if all(path.exists() for path in expected) and not force:
        print(f"SKIP  report2025 boost outputs already exist for {year}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    candidate_rows = []
    directional_rows = []
    pair_rows = []

    for district in districts:
        profile_path = (
            profile_dir
            / f"Portland_D{district}_cleaned_votekit_pref_profile.pkl"
        )

        if not profile_path.exists():
            raise FileNotFoundError(
                f"Missing report2025 profile: {profile_path}"
            )

        profile = PreferenceProfile.from_pickle(str(profile_path))
        mention_counts = mentions(profile)

        candidate_order = sorted(
            profile.candidates,
            reverse=True,
            key=lambda candidate: mention_counts[candidate],
        )

        matrix_frame = pd.DataFrame(
            boost_matrix(
                profile,
                candidates=candidate_order,
            ),
            index=candidate_order,
            columns=candidate_order,
        )

        matrix_frame.to_csv(
            output_dir / f"boost_matrix_D{district}.csv"
        )

        for rank, candidate in enumerate(candidate_order, start=1):
            candidate_rows.append(
                {
                    "year": year,
                    "district": district,
                    "candidate": candidate,
                    "candidate_norm": normalize_name(candidate),
                    "mention_count": float(mention_counts[candidate]),
                    "mention_rank": rank,
                    "is_uncertified_write_in": (
                        "write in" in candidate.lower()
                    ),
                }
            )

        for receiving_candidate in candidate_order:
            for conditioning_candidate in candidate_order:
                if receiving_candidate == conditioning_candidate:
                    continue

                directional_rows.append(
                    {
                        "year": year,
                        "district": district,
                        "receiving_candidate": receiving_candidate,
                        "conditioning_candidate": conditioning_candidate,
                        "boost": matrix_frame.loc[
                            receiving_candidate,
                            conditioning_candidate,
                        ],
                    }
                )

        for candidate_a, candidate_b in combinations(
            candidate_order, 2
        ):
            a_given_b = matrix_frame.loc[candidate_a, candidate_b]
            b_given_a = matrix_frame.loc[candidate_b, candidate_a]

            pair_rows.append(
                {
                    "year": year,
                    "district": district,
                    "candidate_a": candidate_a,
                    "candidate_b": candidate_b,
                    "boost_a_given_b": a_given_b,
                    "boost_b_given_a": b_given_a,
                    "boost_mean": float(
                        np.nanmean([a_given_b, b_given_a])
                    ),
                    "boost_asymmetry": a_given_b - b_given_a,
                }
            )

        print(f"D{district}: {len(candidate_order)} candidates")

    pd.DataFrame(candidate_rows).to_csv(
        output_dir / "candidate_index.csv",
        index=False,
    )
    pd.DataFrame(directional_rows).to_csv(
        output_dir / "boost_directional_long.csv",
        index=False,
    )
    pd.DataFrame(pair_rows).to_csv(
        output_dir / "boost_pairs.csv",
        index=False,
    )

    print(f"SAVED report2025 boost outputs to {output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    main(year=args.year, force=args.force)

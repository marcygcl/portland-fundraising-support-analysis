"""Beginner-friendly helpers for campaign-finance feature construction.

Source-specific decisions stay in the notebook.

This helper only handles repeated mechanical tasks:
- amount bins;
- candidate totals;
- group totals and shares;
- group-by-bin totals and shares;
- geography count profiles;
- correlation screens.
"""

import numpy as np
import pandas as pd

from scipy.stats import pearsonr, spearmanr
from statsmodels.stats.multitest import multipletests


# ---------------------------------------------------------------------
# Shared project bins
# ---------------------------------------------------------------------

BIN_LABELS = [
    "micro",
    "small",
    "medium",
    "large",
    "mega",
]

BIN_EDGES = [
    -np.inf,
    25,
    100,
    250,
    1000,
    np.inf,
]


def add_amount_bin(
    data,
    amount_column="amount",
    bin_column="amount_bin",
):
    """Assign each transaction to one of the five project amount bins."""

    out = data.copy()

    out[bin_column] = pd.cut(
        out[amount_column],
        bins=BIN_EDGES,
        labels=BIN_LABELS,
        right=True,
        ordered=True,
    )

    return out


def build_base_features(
    data,
    profile_keys,
    amount_column="amount",
):
    """Build total amount, record count, mean, and median by candidate."""

    features = (
        data
        .groupby(
            profile_keys,
            as_index=False,
        )
        .agg(
            total_amount=(
                amount_column,
                "sum",
            ),
            total_record_count=(
                amount_column,
                "size",
            ),
            mean_amount=(
                amount_column,
                "mean",
            ),
            median_amount=(
                amount_column,
                "median",
            ),
        )
    )

    feature_names = [
        "total_amount",
        "total_record_count",
        "mean_amount",
        "median_amount",
    ]

    return features, feature_names


def add_bin_features(
    data,
    features,
    profile_keys,
    amount_column="amount",
    bin_column="amount_bin",
    prefix="bin",
):
    """Add amount/count totals and shares for the five overall bins."""

    out = features.copy()

    grouped = (
        data
        .groupby(
            profile_keys + [bin_column],
            observed=False,
            as_index=False,
        )
        .agg(
            bin_amount=(
                amount_column,
                "sum",
            ),
            bin_count=(
                amount_column,
                "size",
            ),
        )
    )

    feature_names = []

    for bin_name in BIN_LABELS:

        one_bin = (
            grouped[
                grouped[bin_column]
                .astype("string")
                .eq(bin_name)
            ][
                profile_keys
                + [
                    "bin_amount",
                    "bin_count",
                ]
            ]
            .copy()
        )

        amount_name = f"{prefix}_amount_{bin_name}"
        amount_share_name = f"{prefix}_amount_share_{bin_name}"

        count_name = f"{prefix}_count_{bin_name}"
        count_share_name = f"{prefix}_count_share_{bin_name}"

        one_bin = one_bin.rename(
            columns={
                "bin_amount": amount_name,
                "bin_count": count_name,
            }
        )

        out = out.merge(
            one_bin,
            on=profile_keys,
            how="left",
            validate="one_to_one",
        )

        out[
            [
                amount_name,
                count_name,
            ]
        ] = (
            out[
                [
                    amount_name,
                    count_name,
                ]
            ]
            .fillna(0)
        )

        out[amount_share_name] = np.where(
            out["total_amount"].gt(0),
            out[amount_name]
            / out["total_amount"],
            np.nan,
        )

        out[count_share_name] = np.where(
            out["total_record_count"].gt(0),
            out[count_name]
            / out["total_record_count"],
            np.nan,
        )

        feature_names.extend(
            [
                amount_name,
                amount_share_name,
                count_name,
                count_share_name,
            ]
        )

    return out, feature_names


def add_group_features(
    data,
    features,
    profile_keys,
    group_column,
    groups,
    amount_column="amount",
):
    """Add amount/count totals and shares for named groups.

    Example:
        groups = ["cash", "in_kind"]

    Overall group shares use the candidate's full fundraising universe.
    """

    out = features.copy()
    feature_names = []

    for group_name in groups:

        subset = data[
            data[group_column].eq(
                group_name
            )
        ].copy()

        summary = (
            subset
            .groupby(
                profile_keys,
                as_index=False,
            )
            .agg(
                group_amount=(
                    amount_column,
                    "sum",
                ),
                group_count=(
                    amount_column,
                    "size",
                ),
            )
        )

        amount_name = f"{group_name}_amount"
        amount_share_name = f"{group_name}_amount_share"

        count_name = f"{group_name}_count"
        count_share_name = f"{group_name}_count_share"

        summary = summary.rename(
            columns={
                "group_amount": amount_name,
                "group_count": count_name,
            }
        )

        out = out.merge(
            summary,
            on=profile_keys,
            how="left",
            validate="one_to_one",
        )

        out[
            [
                amount_name,
                count_name,
            ]
        ] = (
            out[
                [
                    amount_name,
                    count_name,
                ]
            ]
            .fillna(0)
        )

        out[amount_share_name] = np.where(
            out["total_amount"].gt(0),
            out[amount_name]
            / out["total_amount"],
            np.nan,
        )

        out[count_share_name] = np.where(
            out["total_record_count"].gt(0),
            out[count_name]
            / out["total_record_count"],
            np.nan,
        )

        feature_names.extend(
            [
                amount_name,
                amount_share_name,
                count_name,
                count_share_name,
            ]
        )

    return out, feature_names


def add_group_bin_features(
    data,
    features,
    profile_keys,
    group_column,
    groups,
    bin_column="amount_bin",
    amount_column="amount",
):
    """Add four measures inside every group × amount-bin combination.

    Example for Cash + Small:

        cash_bin_amount_small
        cash_bin_amount_share_small
        cash_bin_count_small
        cash_bin_count_share_small

    Conditional share denominators:

        cash_bin_amount_share_small
            = Small Cash dollars / all Cash dollars

        cash_bin_count_share_small
            = Small Cash records / all Cash records
    """

    out = features.copy()
    feature_names = []

    for group_name in groups:

        subset = data[
            data[group_column].eq(
                group_name
            )
        ].copy()

        group_amount_name = f"{group_name}_amount"
        group_count_name = f"{group_name}_count"

        if group_amount_name not in out.columns:
            raise KeyError(
                f"Run add_group_features first. Missing: {group_amount_name}"
            )

        if group_count_name not in out.columns:
            raise KeyError(
                f"Run add_group_features first. Missing: {group_count_name}"
            )

        grouped = (
            subset
            .groupby(
                profile_keys + [bin_column],
                observed=False,
                as_index=False,
            )
            .agg(
                bin_amount=(
                    amount_column,
                    "sum",
                ),
                bin_count=(
                    amount_column,
                    "size",
                ),
            )
        )

        for bin_name in BIN_LABELS:

            one_bin = (
                grouped[
                    grouped[bin_column]
                    .astype("string")
                    .eq(bin_name)
                ][
                    profile_keys
                    + [
                        "bin_amount",
                        "bin_count",
                    ]
                ]
                .copy()
            )

            amount_name = (
                f"{group_name}_bin_amount_{bin_name}"
            )

            amount_share_name = (
                f"{group_name}_bin_amount_share_{bin_name}"
            )

            count_name = (
                f"{group_name}_bin_count_{bin_name}"
            )

            count_share_name = (
                f"{group_name}_bin_count_share_{bin_name}"
            )

            one_bin = one_bin.rename(
                columns={
                    "bin_amount": amount_name,
                    "bin_count": count_name,
                }
            )

            out = out.merge(
                one_bin,
                on=profile_keys,
                how="left",
                validate="one_to_one",
            )

            out[
                [
                    amount_name,
                    count_name,
                ]
            ] = (
                out[
                    [
                        amount_name,
                        count_name,
                    ]
                ]
                .fillna(0)
            )

            out[amount_share_name] = np.where(
                out[group_amount_name].gt(0),
                out[amount_name]
                / out[group_amount_name],
                np.nan,
            )

            out[count_share_name] = np.where(
                out[group_count_name].gt(0),
                out[count_name]
                / out[group_count_name],
                np.nan,
            )

            feature_names.extend(
                [
                    amount_name,
                    amount_share_name,
                    count_name,
                    count_share_name,
                ]
            )

    return out, feature_names


def add_flag_features(
    data,
    features,
    profile_keys,
    flag_column,
    eligible_column,
    prefix,
    amount_column="amount",
):
    """Add count and count share for a geographic/boolean flag.

    Example:
        portland_count
        portland_share

    The share denominator is the eligible geographic universe.
    """

    out = features.copy()

    eligible = data[
        data[eligible_column].fillna(False)
    ].copy()

    eligible_count = (
        eligible
        .groupby(
            profile_keys,
            as_index=False,
        )
        .agg(
            eligible_count=(
                amount_column,
                "size",
            )
        )
        .rename(
            columns={
                "eligible_count":
                    f"{prefix}_eligible_count",
            }
        )
    )

    inside = eligible[
        eligible[flag_column].fillna(False)
    ].copy()

    inside_count = (
        inside
        .groupby(
            profile_keys,
            as_index=False,
        )
        .agg(
            inside_count=(
                amount_column,
                "size",
            )
        )
        .rename(
            columns={
                "inside_count":
                    f"{prefix}_count",
            }
        )
    )

    out = out.merge(
        eligible_count,
        on=profile_keys,
        how="left",
        validate="one_to_one",
    )

    out = out.merge(
        inside_count,
        on=profile_keys,
        how="left",
        validate="one_to_one",
    )

    eligible_name = f"{prefix}_eligible_count"
    count_name = f"{prefix}_count"
    share_name = f"{prefix}_share"

    out[
        [
            eligible_name,
            count_name,
        ]
    ] = (
        out[
            [
                eligible_name,
                count_name,
            ]
        ]
        .fillna(0)
    )

    out[share_name] = np.where(
        out[eligible_name].gt(0),
        out[count_name]
        / out[eligible_name],
        np.nan,
    )

    feature_names = [
        count_name,
        share_name,
    ]

    return out, feature_names


def add_flag_bin_features(
    data,
    features,
    profile_keys,
    flag_column,
    prefix,
    bin_column="amount_bin",
    amount_column="amount",
):
    """Add geographic count and count-share features by amount bin.

    Geography is intentionally count-based in this notebook.

    Example:
        portland_bin_count_small
        portland_bin_count_share_small
    """

    out = features.copy()

    denominator_name = (
        f"{prefix}_count"
    )

    if denominator_name not in out.columns:
        raise KeyError(
            f"Run add_flag_features first. Missing: {denominator_name}"
        )

    subset = data[
        data[flag_column].fillna(False)
    ].copy()

    grouped = (
        subset
        .groupby(
            profile_keys + [bin_column],
            observed=False,
            as_index=False,
        )
        .agg(
            records=(
                amount_column,
                "size",
            )
        )
    )

    feature_names = []

    for bin_name in BIN_LABELS:

        one_bin = (
            grouped[
                grouped[bin_column]
                .astype("string")
                .eq(bin_name)
            ][
                profile_keys
                + [
                    "records",
                ]
            ]
            .copy()
        )

        count_name = (
            f"{prefix}_bin_count_{bin_name}"
        )

        share_name = (
            f"{prefix}_bin_count_share_{bin_name}"
        )

        one_bin = one_bin.rename(
            columns={
                "records": count_name,
            }
        )

        out = out.merge(
            one_bin,
            on=profile_keys,
            how="left",
            validate="one_to_one",
        )

        out[count_name] = (
            out[count_name]
            .fillna(0)
        )

        out[share_name] = np.where(
            out[denominator_name].gt(0),
            out[count_name]
            / out[denominator_name],
            np.nan,
        )

        feature_names.extend(
            [
                count_name,
                share_name,
            ]
        )

    return out, feature_names


def infer_measure(feature_name):
    """Translate a feature name into a simple measure label."""

    if "amount_share" in feature_name:
        return "dollar share"

    if "count_share" in feature_name:
        return "record share"

    if feature_name.endswith("_share"):
        return "record share"

    if "amount" in feature_name:
        return "dollar amount"

    if "count" in feature_name:
        return "record count"

    return "other"


def calculate_correlations(
    data,
    x_variables,
    outcomes,
    feature_family,
):
    """Calculate Pearson and Spearman correlations for all X/Y pairs."""

    rows = []

    for outcome in outcomes:

        for x_variable in x_variables:

            if x_variable not in data.columns:
                continue

            pair = (
                data[
                    [
                        x_variable,
                        outcome,
                    ]
                ]
                .dropna()
            )

            if len(pair) < 3:
                continue

            if pair[x_variable].nunique() < 2:
                continue

            if pair[outcome].nunique() < 2:
                continue

            x = np.asarray(
                pair[x_variable],
                dtype=np.float64,
            )

            y = np.asarray(
                pair[outcome],
                dtype=np.float64,
            )

            pearson_r, pearson_p = (
                pearsonr(
                    x,
                    y,
                )
            )

            spearman_r, spearman_p = (
                spearmanr(
                    x,
                    y,
                )
            )

            rows.append(
                {
                    "outcome": outcome,
                    "feature": x_variable,
                    "family": feature_family[
                        x_variable
                    ],
                    "measure": infer_measure(
                        x_variable
                    ),
                    "n": len(pair),
                    "pearson_r": pearson_r,
                    "pearson_p": pearson_p,
                    "spearman_r": spearman_r,
                    "spearman_p": spearman_p,
                }
            )

    results = pd.DataFrame(
        rows
    )

    if results.empty:
        return results

    results["abs_pearson_r"] = (
        results["pearson_r"].abs()
    )

    results["abs_spearman_r"] = (
        results["spearman_r"].abs()
    )

    # Keep p-values in the full output for reference,
    # but they do not need to be shown in the main exploratory tables.
    results["pearson_p_fdr"] = np.nan
    results["spearman_p_fdr"] = np.nan

    for outcome in outcomes:

        mask = (
            results["outcome"]
            .eq(outcome)
        )

        if mask.sum() == 0:
            continue

        results.loc[
            mask,
            "pearson_p_fdr",
        ] = multipletests(
            results.loc[
                mask,
                "pearson_p",
            ],
            method="fdr_bh",
        )[1]

        results.loc[
            mask,
            "spearman_p_fdr",
        ] = multipletests(
            results.loc[
                mask,
                "spearman_p",
            ],
            method="fdr_bh",
        )[1]

    return results

def calculate_correlations_by_district(
    data,
    x_variables,
    outcomes,
    feature_family,
    min_n=8,
):
    """Run the same correlation screen separately inside each district."""

    district_tables = []

    districts = sorted(
        data["district"]
        .dropna()
        .astype(int)
        .unique()
        .tolist()
    )

    for district in districts:

        district_data = (
            data[
                data["district"].eq(
                    district
                )
            ]
            .copy()
        )

        results = calculate_correlations(
            district_data,
            x_variables=x_variables,
            outcomes=outcomes,
            feature_family=feature_family,
        )

        if results.empty:
            continue

        results.insert(
            0,
            "district",
            district,
        )

        results = results[
            results["n"].ge(
                min_n
            )
        ].copy()

        district_tables.append(
            results
        )

    if len(district_tables) == 0:
        return pd.DataFrame()

    return pd.concat(
        district_tables,
        ignore_index=True,
    )


def make_correlation_race(
    correlations,
    outcome,
    top_n=20,
):
    """Return the strongest X variables for one outcome."""

    table = (
        correlations[
            correlations["outcome"].eq(
                outcome
            )
        ]
        .sort_values(
            "abs_pearson_r",
            ascending=False,
        )
        .head(
            top_n
        )
        .copy()
        .reset_index(
            drop=True
        )
    )

    table.insert(
        0,
        "rank",
        np.arange(
            1,
            len(table) + 1,
        ),
    )

    return table


def make_district_race(
    district_correlations,
    outcome,
    district,
    top_n=15,
):
    """Return the strongest X variables inside one district."""

    table = (
        district_correlations[
            district_correlations[
                "outcome"
            ].eq(
                outcome
            )
            & district_correlations[
                "district"
            ].eq(
                district
            )
        ]
        .sort_values(
            "abs_pearson_r",
            ascending=False,
        )
        .head(
            top_n
        )
        .copy()
        .reset_index(
            drop=True
        )
    )

    table.insert(
        0,
        "rank",
        np.arange(
            1,
            len(table) + 1,
        ),
    )

    return table


def compare_top_features_across_districts(
    pooled_correlations,
    district_correlations,
    outcome,
    top_n=15,
):
    """Show pooled Pearson r next to D1-D4 Pearson r for top features."""

    pooled = make_correlation_race(
        pooled_correlations,
        outcome=outcome,
        top_n=top_n,
    )[
        [
            "rank",
            "feature",
            "family",
            "measure",
            "pearson_r",
        ]
    ].rename(
        columns={
            "rank":
                "pooled_rank",
            "pearson_r":
                "pooled_r",
        }
    )

    comparison = pooled.copy()

    districts = sorted(
        district_correlations[
            "district"
        ]
        .dropna()
        .astype(int)
        .unique()
        .tolist()
    )

    for district in districts:

        district_values = (
            district_correlations[
                district_correlations[
                    "outcome"
                ].eq(
                    outcome
                )
                & district_correlations[
                    "district"
                ].eq(
                    district
                )
            ][
                [
                    "feature",
                    "pearson_r",
                ]
            ]
            .rename(
                columns={
                    "pearson_r":
                        f"D{district}_r",
                }
            )
        )

        comparison = comparison.merge(
            district_values,
            on="feature",
            how="left",
            validate="one_to_one",
        )

    return comparison


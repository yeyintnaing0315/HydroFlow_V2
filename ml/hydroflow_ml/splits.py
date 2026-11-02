from __future__ import annotations

import pandas as pd


def chronological_split(
    data: pd.DataFrame,
    train_fraction: float = 0.60,
    validation_fraction: float = 0.20,
) -> pd.Series:
    """Assign complete calendar dates to train, validation, and test blocks."""
    if train_fraction <= 0 or validation_fraction <= 0 or train_fraction + validation_fraction >= 1:
        raise ValueError("Split fractions must leave non-empty train, validation, and test blocks")
    dates = pd.Series(pd.to_datetime(data["date"]).drop_duplicates().sort_values().to_numpy())
    train_end = max(1, int(len(dates) * train_fraction))
    validation_end = max(train_end + 1, int(len(dates) * (train_fraction + validation_fraction)))
    if validation_end >= len(dates):
        raise ValueError("Not enough unique dates for requested split")

    train_cutoff = dates.iloc[train_end]
    validation_cutoff = dates.iloc[validation_end]
    row_dates = pd.to_datetime(data["date"])
    split = pd.Series("test", index=data.index, dtype="string")
    split.loc[row_dates < validation_cutoff] = "validation"
    split.loc[row_dates < train_cutoff] = "train"
    return split


def assert_temporal_order(data: pd.DataFrame, split: pd.Series) -> None:
    dates = pd.to_datetime(data["date"])
    if not (
        dates[split == "train"].max() < dates[split == "validation"].min()
        and dates[split == "validation"].max() < dates[split == "test"].min()
    ):
        raise ValueError("Chronological split overlaps or is out of order")

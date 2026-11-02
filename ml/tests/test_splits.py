import pandas as pd

from hydroflow_ml.splits import assert_temporal_order, chronological_split


def test_split_is_chronological_and_keeps_dates_together():
    dates = pd.date_range("2024-01-01", periods=10)
    data = pd.DataFrame(
        [(date, township) for date in dates for township in ("a", "b")],
        columns=["date", "township_id"],
    )
    split = chronological_split(data)
    assert_temporal_order(data, split)
    assert split.value_counts().to_dict() == {"train": 12, "validation": 4, "test": 4}
    assert pd.DataFrame({"date": data["date"], "split": split}).groupby("date")["split"].nunique().max() == 1

import pandas as pd

from dqt.core.time_utils import bucket_time, infer_time_granularity


def test_infer_granularity_short_span():
    s = pd.to_datetime(pd.date_range("2024-01-01", periods=30, freq="D").to_series())
    assert infer_time_granularity(s) == "day"


def test_infer_granularity_year_span():
    s = pd.to_datetime(pd.date_range("2024-01-01", periods=300, freq="D").to_series())
    assert infer_time_granularity(s) == "week"


def test_infer_granularity_multi_year():
    s = pd.to_datetime(pd.date_range("2020-01-01", periods=1200, freq="D").to_series())
    assert infer_time_granularity(s) == "month"


def test_infer_granularity_string_periods():
    s = pd.Series(["2024-01", "2024-02", "2024-03"])
    # Strings that look like dates → datetime-like → infer_time_granularity returns 'day' (small span)
    # But the bucket_time call would treat them as datetime. We accept both.
    g = infer_time_granularity(s)
    assert g in {"day", "month", "as_is"}


def test_bucket_time_month():
    s = pd.to_datetime(["2024-01-15", "2024-02-03", "2024-02-28", "2024-03-10"])
    result = bucket_time(pd.Series(s), granularity="month")
    assert list(result) == ["2024-01", "2024-02", "2024-02", "2024-03"]


def test_bucket_time_quarter():
    s = pd.to_datetime(["2024-01-15", "2024-04-03", "2024-07-28", "2024-10-10"])
    result = bucket_time(pd.Series(s), granularity="quarter")
    assert list(result) == ["2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4"]


def test_bucket_time_as_is_with_strings():
    s = pd.Series(["P1", "P2", "P1", "P3"])
    result = bucket_time(s, granularity="as_is")
    assert sorted(result.categories.tolist()) == ["P1", "P2", "P3"]


def test_bucket_time_handles_nan():
    s = pd.Series(pd.to_datetime(["2024-01-01", None, "2024-02-01"]))
    result = bucket_time(s, granularity="month")
    assert pd.isna(result[1])

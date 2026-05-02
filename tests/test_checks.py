import numpy as np
import pandas as pd

from dqt.core.checks import (
    cardinality_over_time,
    missingness_over_time,
    outlier_share_over_time,
    type_consistency,
)


def test_missingness_over_time(binary_df):
    df = binary_df.copy()
    df["m"] = df["date"].dt.to_period("M").astype(str)
    out = missingness_over_time(df, "x_num", "m")
    assert "missing_share" in out.columns
    assert (out["missing_share"] >= 0).all()
    assert (out["missing_share"] <= 1).all()


def test_cardinality_over_time(binary_df):
    df = binary_df.copy()
    df["m"] = df["date"].dt.to_period("M").astype(str)
    out = cardinality_over_time(df, "x_cat", "m")
    assert "n_unique" in out.columns
    assert (out["n_unique"] > 0).all()


def test_outlier_share_iqr():
    rng = np.random.default_rng(0)
    n = 500
    df = pd.DataFrame({
        "m": ["A"] * n + ["B"] * n,
        "x": np.concatenate([rng.normal(size=n), rng.normal(size=n)]),
    })
    # Inject obvious outliers in B
    df.loc[df["m"] == "B", "x"] = np.concatenate([rng.normal(size=n - 50), np.full(50, 100.0)])
    out = outlier_share_over_time(df, "x", "m", method="iqr")
    rate_a = out.loc[out["m"] == "A", "outlier_share"].iloc[0]
    rate_b = out.loc[out["m"] == "B", "outlier_share"].iloc[0]
    assert rate_b > rate_a


def test_outlier_share_zscore():
    df = pd.DataFrame({"m": ["A"] * 100, "x": [0.0] * 99 + [100.0]})
    out = outlier_share_over_time(df, "x", "m", method="z", z_threshold=3.0)
    assert out["outlier_share"].iloc[0] > 0.0


def test_type_consistency_clean_numeric():
    df = pd.DataFrame({"m": ["A"] * 100, "x": np.arange(100)})
    out = type_consistency(df, "x", "m")
    assert out["numeric_parse_share"].iloc[0] == 1.0


def test_type_consistency_mixed():
    df = pd.DataFrame({
        "m": ["A"] * 4 + ["B"] * 4,
        "x": ["1", "2", "3", "4", "1", "2", "N/A", "X"],
    })
    out = type_consistency(df, "x", "m")
    a = out.loc[out["m"] == "A", "numeric_parse_share"].iloc[0]
    b = out.loc[out["m"] == "B", "numeric_parse_share"].iloc[0]
    assert a == 1.0
    assert b == 0.5

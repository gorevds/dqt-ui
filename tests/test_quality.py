import numpy as np
import pandas as pd

from dqt.core.quality import (
    psi,
    psi_over_time,
    bins_target_rate_over_time,
    feature_distribution_over_time,
    stability_summary,
)
from dqt.core.target_utils import TargetKind


def test_psi_zero_for_identical():
    rng = np.random.default_rng(0)
    a = rng.normal(size=2000)
    assert psi(a, a, bins=10) == 0.0 or abs(psi(a, a, bins=10)) < 1e-9


def test_psi_positive_for_shifted():
    rng = np.random.default_rng(0)
    a = rng.normal(loc=0, size=5000)
    b = rng.normal(loc=2, size=5000)  # shifted
    val = psi(a, b, bins=10)
    assert val > 0.5  # should be a large drift


def test_psi_handles_empty():
    assert np.isnan(psi(np.array([]), np.array([1.0])))


def test_psi_over_time_first_reference(binary_df):
    # Bucket time first
    df = binary_df.copy()
    df["m"] = df["date"].dt.to_period("M").astype(str)
    out = psi_over_time(df, "x_num", "m", reference="first")
    assert len(out) == df["m"].nunique()
    assert out["psi"].iloc[0] == 0.0  # first vs first
    # Last bucket should have non-trivial PSI given the drift
    assert out["psi"].iloc[-1] > 0.05


def test_psi_over_time_previous(binary_df):
    df = binary_df.copy()
    df["m"] = df["date"].dt.to_period("M").astype(str)
    out = psi_over_time(df, "x_num", "m", reference="previous")
    assert out["psi"].iloc[0] == 0.0


def test_bins_target_rate_binary(binary_df):
    df = binary_df.copy()
    df["m"] = df["date"].dt.to_period("M").astype(str)
    df["bin"] = pd.cut(df["x_num"].fillna(0), bins=3).astype(str)
    out = bins_target_rate_over_time(df, "bin", "target", "m", TargetKind.BINARY)
    assert {"m", "bin", "rate", "count", "se"}.issubset(out.columns)
    assert (out["rate"] >= 0).all() and (out["rate"] <= 1).all()
    assert (out["se"] >= 0).all()


def test_feature_distribution_numeric(binary_df):
    df = binary_df.copy()
    df["m"] = df["date"].dt.to_period("M").astype(str)
    out = feature_distribution_over_time(df, "x_num", "m", is_numeric=True)
    assert {"q5", "q25", "q50", "q75", "q95", "count"}.issubset(out.columns)
    assert len(out) == df["m"].nunique()


def test_feature_distribution_categorical(binary_df):
    df = binary_df.copy()
    df["m"] = df["date"].dt.to_period("M").astype(str)
    out = feature_distribution_over_time(df, "x_cat", "m", is_numeric=False)
    assert "share" in out.columns
    grouped = out.groupby("m")["share"].sum()
    assert (grouped.round(3) == 1.0).all()


def test_stability_summary():
    rate_df = pd.DataFrame({
        "bin": ["a", "a", "b", "b"],
        "rate": [0.1, 0.12, 0.5, 0.55],
        "count": [100, 100, 100, 100],
        "se": [0.03] * 4,
    })
    psi_df = pd.DataFrame({"m": ["1", "2"], "psi": [0.0, 0.05]})
    summary = stability_summary(rate_df, psi_df)
    assert "rate_std" in summary
    assert "psi_mean" in summary
    assert summary["psi_max"] == 0.05

"""Shared fixtures: synthetic DQ datasets covering binary / regression / multiclass."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture(scope="session")
def rng():
    return np.random.default_rng(42)


@pytest.fixture
def binary_df(rng):
    """24 monthly buckets, binary target with feature drift."""
    n = 6000
    months = pd.date_range("2022-01-01", periods=24, freq="MS")
    rows = []
    for i, m in enumerate(months):
        # Drifting numeric: mean shifts with time
        x_num = rng.normal(loc=i * 0.1, scale=1.0, size=n // 24)
        x_cat = rng.choice(["A", "B", "C", "D"], size=n // 24, p=[0.4, 0.3, 0.2, 0.1])
        # Target depends on x_num (more risk → higher rate)
        p = 1 / (1 + np.exp(-x_num + 0.5))
        y = (rng.random(n // 24) < p).astype(int)
        for xn, xc, yi in zip(x_num, x_cat, y):
            rows.append({"date": m, "x_num": xn, "x_cat": xc, "target": yi})
    df = pd.DataFrame(rows)
    # Add some NaN
    df.loc[df.sample(frac=0.05, random_state=1).index, "x_num"] = np.nan
    df.loc[df.sample(frac=0.02, random_state=2).index, "x_cat"] = np.nan
    return df


@pytest.fixture
def regression_df(rng):
    """Regression target."""
    n = 1500
    dates = pd.date_range("2023-01-01", periods=12, freq="MS")
    df = pd.DataFrame({
        "month": np.repeat(dates, n // 12),
        "x": rng.normal(size=n),
    })
    df["target"] = 2 * df["x"] + rng.normal(scale=0.5, size=len(df))
    return df


@pytest.fixture
def multiclass_df(rng):
    n = 800
    dates = pd.date_range("2023-01-01", periods=8, freq="MS")
    df = pd.DataFrame({
        "month": np.repeat(dates, n // 8),
        "x": rng.normal(size=n),
    })
    df["target"] = pd.Categorical(rng.choice(["low", "mid", "high"], size=n))
    return df


@pytest.fixture
def small_csv(tmp_path, binary_df):
    path = tmp_path / "data.csv"
    binary_df.head(200).to_csv(path, index=False)
    return path

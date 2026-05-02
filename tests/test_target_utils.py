import numpy as np
import pandas as pd

from dqt.core.target_utils import TargetKind, detect_target_kind, to_binary_target


def test_detect_binary_int():
    s = pd.Series([0, 1, 1, 0, 1])
    info = detect_target_kind(s)
    assert info.kind == TargetKind.BINARY
    assert info.classes == [0, 1]


def test_detect_binary_strings():
    s = pd.Series(["good", "bad", "good", "bad", "good"])
    info = detect_target_kind(s)
    assert info.kind == TargetKind.BINARY
    assert set(info.classes) == {"good", "bad"}


def test_detect_multiclass():
    s = pd.Series(["A", "B", "C", "A", "B", "C"] * 5)
    info = detect_target_kind(s)
    assert info.kind == TargetKind.MULTICLASS
    assert info.n_unique == 3


def test_detect_regression_float():
    s = pd.Series(np.random.default_rng(0).normal(size=200))
    info = detect_target_kind(s)
    assert info.kind == TargetKind.REGRESSION


def test_detect_regression_int_high_card():
    s = pd.Series(np.arange(1000))
    info = detect_target_kind(s)
    assert info.kind == TargetKind.REGRESSION


def test_to_binary_target_with_strings():
    s = pd.Series(["bad", "good", "bad", None, "good"])
    info = detect_target_kind(s)
    out = to_binary_target(s, info)
    # classes sorted: ['bad', 'good'], pos = 'good'
    assert out.iloc[0] == 0
    assert out.iloc[1] == 1
    assert pd.isna(out.iloc[3])


def test_nan_share():
    s = pd.Series([1, 0, 1, np.nan, np.nan])
    info = detect_target_kind(s)
    assert info.nan_share == 0.4

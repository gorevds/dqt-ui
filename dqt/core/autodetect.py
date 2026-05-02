"""Heuristics for guessing time / target columns from a fresh DataFrame.

Used to pre-fill the column pickers on the /columns page so the user usually
just has to click Continue.
"""
from __future__ import annotations

from typing import Iterable, Optional

import pandas as pd


_TIME_HINTS = (
    "date", "time", "datetime", "timestamp", "period", "month", "year",
    "day", "week", "snapshot", "report", "applied", "created", "occurred",
    "event_dt", "_dt", "_ts", "ds",
)

_TARGET_HINTS = (
    "target", "label", "y", "outcome", "default", "_flag",
    "conversion", "converted", "click", "churn", "fraud", "is_",
    "response", "purchased",
)


def autodetect_time_column(df: pd.DataFrame) -> Optional[str]:
    """Pick the column most likely to be the time axis.

    Scoring:
      +100 datetime dtype
      +70  object/string column whose head parses as datetime (>80% rate)
      +30  name contains a time-related token (date/time/period/...)
    """
    candidates: list[tuple[int, str]] = []
    for col in df.columns:
        s = df[col]
        score = 0
        if pd.api.types.is_datetime64_any_dtype(s):
            score += 100
        elif pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s):
            sample = s.dropna().head(50)
            if len(sample) > 0:
                try:
                    parsed = pd.to_datetime(sample, errors="coerce")
                    if parsed.notna().mean() > 0.8:
                        score += 70
                except Exception:
                    pass
        name = str(col).lower()
        if any(h in name for h in _TIME_HINTS):
            score += 30
        if score > 0:
            candidates.append((score, col))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (-x[0], list(df.columns).index(x[1])))
    return candidates[0][1]


def autodetect_target_column(
    df: pd.DataFrame, exclude: Optional[Iterable[str]] = None,
) -> Optional[str]:
    """Pick the column most likely to be the target.

    Scoring:
      +80 strictly binary {0, 1}
      +50 has exactly 2 unique non-null values (any type)
      +40 name contains a target-related token (target/label/default/...)
    """
    excl = set(exclude or ())
    candidates: list[tuple[int, str]] = []
    for col in df.columns:
        if col in excl:
            continue
        s = df[col].dropna()
        score = 0
        unique = set(s.unique().tolist()) if not s.empty else set()
        if unique and unique.issubset({0, 1, 0.0, 1.0, True, False}):
            score += 80
        elif len(unique) == 2:
            score += 50
        name = str(col).lower()
        if any(h in name for h in _TARGET_HINTS):
            score += 40
        if score > 0:
            candidates.append((score, col))
    if not candidates:
        return None
    # Prefer higher score; tie-break by trailing position (target columns
    # are conventionally last).
    candidates.sort(key=lambda x: (-x[0], -list(df.columns).index(x[1])))
    return candidates[0][1]


def autodetect_features(
    df: pd.DataFrame, time_col: Optional[str], target_col: Optional[str],
) -> list[str]:
    """Everything except time and target."""
    excl = {c for c in (time_col, target_col) if c}
    return [c for c in df.columns if c not in excl]

"""Model output drift — score-centric monitoring.

Most credit-risk teams care about a single column more than any other:
the *score itself*. Was it stable this month? Is the calibration intact?

The report measures the score distribution in each time bucket, including
periods whose outcome labels are still missing. Calibration uses labelled
observations separately.

Use from the CLI::

    dqt analyze portfolio.parquet --score-col score --time month \\
                --target default_flag --fail-on red

or directly::

    from dqt.score_drift import analyze_score
    out = analyze_score(df, score_col="score", target_col="default_flag",
                        time_col="month")
"""
from __future__ import annotations

import math
from typing import Optional

import pandas as pd

from dqt.api import FeatureResult, Report
from dqt.app.pipeline import _verdict_for
from dqt.config import Config, severity_for
from dqt.core.autodetect import autodetect_time_column
from dqt.core.checks import missingness_over_time
from dqt.core.quality import psi_over_time
from dqt.core.target_utils import TargetKind, detect_target_kind, to_binary_target
from dqt.core.time_utils import bucket_time
from dqt.plots import plot_psi_over_time


def analyze_score(
    df: pd.DataFrame,
    score_col: str,
    *,
    target_col: Optional[str] = None,
    time_col: Optional[str] = None,
    granularity: str = "auto",
    max_bins: int = 5,
    reference_df: Optional[pd.DataFrame] = None,
    psi_reference: str = "first",
) -> dict:
    """Run a score-centric analysis. Returns ``{score_report, calibration}``
    where ``score_report`` is a regular :class:`dqt.api.Report` and
    ``calibration`` is a per-bucket calibration drift table (only when
    ``target_col`` is given and looks binary).
    """
    if score_col not in df.columns:
        raise KeyError(f"score column {score_col!r} not in dataframe")

    time_col = time_col or autodetect_time_column(df)
    if time_col is None or time_col == score_col:
        raise ValueError("Specify a time column distinct from the score")
    data = pd.DataFrame({"period": bucket_time(df[time_col], granularity),
                         "score": pd.to_numeric(df[score_col], errors="raise")}).dropna(subset=["period"])
    if data.empty:
        raise ValueError("No valid periods")
    baseline = None if reference_df is None else reference_df[score_col]
    series = psi_over_time(data, "score", "period", reference=psi_reference,
                           reference_values=baseline, is_numeric=True)
    missing = float(missingness_over_time(data, "score", "period")["missing_share"].max())
    summary = {"psi_max": float(series.psi.astype(float).max()), "psi_mean": float(series.psi.astype(float).mean()),
               "missing_share_max": missing}
    thresholds = Config.load().for_feature(score_col)
    feature = FeatureResult(
        name=score_col, kind="numeric", summary=summary,
        severity=severity_for(summary["psi_max"], None, missing, thresholds),
        verdict=_verdict_for(summary, missing, False, thresholds),
        figs={"psi": plot_psi_over_time(series, "period", thresholds=thresholds)},
    )
    score_report = Report(
        meta={"time_col": time_col, "target_col": score_col, "target_kind": "score",
              "granularity": granularity, "n_rows": len(data)},
        features=[feature], summary_table=pd.DataFrame([{"feature": score_col, "type": "numeric",
                                                      "severity": feature.severity, **summary}]),
    )

    calibration = None
    if target_col and target_col in df.columns:
        info = detect_target_kind(df[target_col])
        if info.kind == TargetKind.BINARY:
            calibration = _calibration_drift(
                df.assign(**{target_col: to_binary_target(df[target_col], info)}), score_col=score_col, target_col=target_col,
                time_col=time_col, n_buckets=max_bins, granularity=granularity,
            )

    return {"score_report": score_report, "calibration": calibration}


def _calibration_drift(
    df: pd.DataFrame, *, score_col: str, target_col: str,
    time_col: str, n_buckets: int, granularity: str = "auto",
) -> pd.DataFrame:
    """Per (period, score-quantile-bucket): observed default rate.

    The columns are::

        period, bucket, score_lo, score_hi, n, target_rate

    Bucket edges are computed once on the global score distribution so
    rows from every period land in the same buckets — this is the only
    way the comparison across periods is meaningful.
    """
    score = pd.to_numeric(df[score_col], errors="coerce")
    target = pd.to_numeric(df[target_col], errors="coerce")
    period = pd.Series(bucket_time(df[time_col], granularity), index=df.index)
    keep = score.notna() & target.notna() & period.notna()
    if not keep.any():
        return pd.DataFrame(columns=["period", "bucket", "score_lo",
                                      "score_hi", "n", "target_rate"])

    quantiles = pd.unique(score[keep].quantile(
        [i / n_buckets for i in range(n_buckets + 1)]).to_numpy())
    if len(quantiles) < 2:
        return pd.DataFrame(columns=["period", "bucket", "score_lo",
                                      "score_hi", "n", "target_rate"])
    edges = sorted(quantiles)
    labels = list(range(len(edges) - 1))

    sub = pd.DataFrame({
        "score": score[keep], "target": target[keep], "period": period[keep],
    })
    sub["bucket"] = pd.cut(sub["score"], bins=edges, labels=labels,
                            include_lowest=True)
    grouped = (
        sub.dropna(subset=["bucket"])
           .groupby(["period", "bucket"], observed=True)
           .agg(n=("target", "size"), target_rate=("target", "mean"))
           .reset_index()
    )
    edge_lo = {i: float(edges[i]) for i in labels}
    edge_hi = {i: float(edges[i + 1]) for i in labels}
    grouped["score_lo"] = grouped["bucket"].map(edge_lo)
    grouped["score_hi"] = grouped["bucket"].map(edge_hi)
    grouped["period"] = grouped["period"].astype(str)
    return grouped[["period", "bucket", "score_lo", "score_hi", "n",
                    "target_rate"]]


def calibration_delta(calibration: pd.DataFrame) -> pd.DataFrame:
    """Pivoted view: each row is a bucket, columns are periods, values
    are absolute target rate. Highlights buckets whose row range exceeds
    a typical scorecard tolerance (5 percentage points).
    """
    if calibration is None or calibration.empty:
        return pd.DataFrame(columns=["bucket", "max_drift_pp"])
    pivot = calibration.pivot_table(
        index=["bucket", "score_lo", "score_hi"],
        columns="period", values="target_rate", aggfunc="mean",
    )
    pivot["max_drift_pp"] = (pivot.max(axis=1) - pivot.min(axis=1)) * 100
    return pivot.reset_index()


def has_calibration_drift(calibration: pd.DataFrame, threshold_pp: float = 5.0) -> bool:
    """Returns True if any bucket's target rate moved more than
    ``threshold_pp`` percentage points across periods.
    """
    if calibration is None or calibration.empty:
        return False
    delta = calibration_delta(calibration)
    if delta.empty:
        return False
    worst = delta["max_drift_pp"].max()
    if worst is None or (isinstance(worst, float) and math.isnan(worst)):
        return False
    return float(worst) > float(threshold_pp)

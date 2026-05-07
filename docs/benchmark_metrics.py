"""Reproducible benchmark — DQT pairwise z-stability vs PSI / KS / Wasserstein / JSD.

Generates four synthetic scenarios, evaluates every metric on each one, and
writes the table to ``docs/benchmark_metrics.csv``. Run::

    python docs/benchmark_metrics.py

The output is read back into ``docs/benchmark_metrics.md`` (committed) so
reviewers don't have to re-run the script.

Scenarios:

1. **no-drift** — both reference and current draws come from the same
   distribution. Every metric should be ~ 0.
2. **covariate shift** — feature distribution drifts, but its relationship
   to the target stays linear. Distribution-level metrics light up; binwise
   target-rate stability holds.
3. **concept drift** — feature distribution unchanged, but the target's
   conditional dependency on the feature inverts halfway through. PSI/KS
   say "stable"; pairwise stability collapses.
4. **mixing shift** — distribution and concept drift simultaneously. Every
   metric should be elevated.

The point: pairwise z-stability is the only metric here that catches
**concept drift in isolation**, which is exactly the failure mode that
ruins scorecards in production.
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp, wasserstein_distance

from dqt.core.grouping import fit_binner
from dqt.core.quality import (
    bins_target_rate_over_time,
    pairwise_bin_stability,
    psi,
)
from dqt.core.target_utils import TargetKind


def jsd(p: np.ndarray, q: np.ndarray, eps: float = 1e-9) -> float:
    """Jensen-Shannon divergence (base-2). Bounded in [0, 1]."""
    p = np.asarray(p, dtype=float)
    q = np.asarray(q, dtype=float)
    p = p / max(p.sum(), eps)
    q = q / max(q.sum(), eps)
    m = 0.5 * (p + q)
    kl_pm = np.sum(np.where(p > 0, p * np.log2((p + eps) / (m + eps)), 0.0))
    kl_qm = np.sum(np.where(q > 0, q * np.log2((q + eps) / (m + eps)), 0.0))
    return float(0.5 * (kl_pm + kl_qm))


def _hist(x: np.ndarray, edges: np.ndarray) -> np.ndarray:
    h, _ = np.histogram(x, bins=edges)
    return h / max(h.sum(), 1)


def make_scenario(kind: str, n: int = 5000, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    # Reference (period 0) feature ~ N(0, 1).
    x_ref = rng.normal(0.0, 1.0, size=n)
    if kind == "no-drift":
        x_cur = rng.normal(0.0, 1.0, size=n)
    elif kind in ("covariate", "mixing"):
        x_cur = rng.normal(1.5, 1.0, size=n)  # mean shift
    elif kind == "concept":
        x_cur = rng.normal(0.0, 1.0, size=n)
    else:
        raise ValueError(kind)

    # Target depends on x linearly in reference period.
    logit_ref = -1.5 + 1.2 * x_ref
    y_ref = (rng.random(n) < 1.0 / (1 + np.exp(-logit_ref))).astype(int)

    # In concept / mixing scenarios the slope flips sign in the current period.
    slope_cur = -1.2 if kind in ("concept", "mixing") else 1.2
    logit_cur = -1.5 + slope_cur * x_cur
    y_cur = (rng.random(n) < 1.0 / (1 + np.exp(-logit_cur))).astype(int)

    df = pd.DataFrame({
        "x": np.concatenate([x_ref, x_cur]),
        "y": np.concatenate([y_ref, y_cur]),
        "period": ["ref"] * n + ["cur"] * n,
    })
    return df


def run_one(kind: str) -> dict:
    df = make_scenario(kind, n=5000, seed=12)
    ref = df[df["period"] == "ref"]
    cur = df[df["period"] == "cur"]

    # Distribution-level metrics on x.
    edges = np.unique(np.quantile(ref["x"], np.linspace(0, 1, 11)))
    psi_v = psi(cur["x"].to_numpy(), ref["x"].to_numpy(), bins=10)
    ks_v = float(ks_2samp(ref["x"], cur["x"]).statistic)
    wd_v = float(wasserstein_distance(ref["x"], cur["x"]))
    jsd_v = jsd(_hist(ref["x"].to_numpy(), edges), _hist(cur["x"].to_numpy(), edges))

    # Pairwise stability — needs binned data and per-bin rate per period.
    binner = fit_binner(
        df=df.assign(_y=df["y"]).rename(columns={"y": "_y_orig"})[["x", "_y"]],
        features=["x"],
        target_col="_y",
        target_kind=TargetKind.BINARY,
        feature_kinds={"x": "numeric"},
        max_bins=4,
        min_samples_leaf=0.05,
    )
    binned = binner.transform(df[["x"]])
    binned["period"] = df["period"].values
    binned["y"] = df["y"].values
    rate = bins_target_rate_over_time(
        binned, binned_feature="x", target_col="y",
        time_col="period", target_kind=TargetKind.BINARY,
    )
    pw = pairwise_bin_stability(rate, "period", target_kind=TargetKind.BINARY)
    # Per-period; the "current"-period score is the one drift detection cares about.
    stability_cur = float(pw.set_index("period").loc["cur", "stability"]) if not pw.empty else float("nan")

    return {
        "scenario": kind,
        "psi_x": round(psi_v, 4),
        "ks_x": round(ks_v, 4),
        "wasserstein_x": round(wd_v, 4),
        "jsd_x": round(jsd_v, 4),
        "stability_cur": round(stability_cur, 4),
    }


def main() -> None:
    rows = [run_one(s) for s in ("no-drift", "covariate", "concept", "mixing")]
    out = Path(__file__).with_name("benchmark_metrics.csv")
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"wrote {out}")
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()

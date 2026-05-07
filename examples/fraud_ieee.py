"""Fraud detection drift triage — synthetic IEEE-CIS-style transactions.

Fraud teams need drift answers that span very short time windows
(daily / weekly buckets) and a target with extreme class imbalance.
This example shows DQT's handling of both.

To convert to an .ipynb run::

    pip install jupytext
    jupytext --to notebook examples/fraud_ieee.py
"""
from __future__ import annotations

# %% Imports --------------------------------------------------------------

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from dqt import analyze


# %% Generate synthetic IEEE-CIS-style data ------------------------------

def make_fraud_like(n_rows: int = 6000, fraud_rate: float = 0.025, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = pd.date_range("2026-01-01", periods=90, freq="D")
    day_idx = rng.integers(0, len(days), size=n_rows)
    transaction_dt = days[day_idx]
    t = day_idx.astype(float) / max(1, len(days) - 1)

    # ---- Numeric features -----------------------------------------------
    transaction_amt = np.exp(rng.normal(loc=4.5 + 0.3 * t, scale=0.7, size=n_rows)).round(2)
    card_age_days = rng.integers(0, 1800, size=n_rows)
    card_use_count_30d = rng.poisson(lam=8 + 4 * t, size=n_rows)
    avg_amt_30d = transaction_amt * rng.uniform(0.7, 1.3, size=n_rows)
    distance_from_home_km = np.clip(rng.exponential(scale=120 + 80 * t, size=n_rows), 0, 8000)

    # ---- Categorical with shifting share --------------------------------
    devices = rng.choice(
        ["mobile_ios", "mobile_android", "desktop", "kiosk"],
        size=n_rows, p=[0.30, 0.40, 0.25, 0.05],
    )
    payment_method = rng.choice(
        ["credit", "debit", "wallet", "btc"],
        size=n_rows, p=[0.45, 0.30, 0.22, 0.03],
    )

    # ---- Target with realistic imbalance --------------------------------
    logit = (
        -4.0
        + 0.0008 * transaction_amt
        - 0.0003 * card_age_days
        + 0.05 * card_use_count_30d
        + 0.001 * distance_from_home_km
    )
    p_fraud = 1.0 / (1.0 + np.exp(-logit))
    # Re-scale so the marginal is close to ``fraud_rate``.
    p_fraud = p_fraud * (fraud_rate / max(p_fraud.mean(), 1e-6))
    is_fraud = (rng.random(n_rows) < p_fraud).astype(int)

    df = pd.DataFrame({
        "transaction_dt": transaction_dt,
        "transaction_amt": transaction_amt,
        "card_age_days": card_age_days,
        "card_use_count_30d": card_use_count_30d,
        "avg_amt_30d": avg_amt_30d.round(2),
        "distance_from_home_km": distance_from_home_km.round(0),
        "device": devices,
        "payment_method": payment_method,
        "is_fraud": is_fraud,
    })
    return df.sample(frac=1.0, random_state=seed).reset_index(drop=True)


df = make_fraud_like()
print(f"Loaded {len(df):,} rows; fraud rate = {df['is_fraud'].mean():.2%}")
print(df.describe(include="all").T.head(10))


# %% Run DQT with weekly granularity ------------------------------------

report = analyze(
    df,
    time_col="transaction_dt",
    target_col="is_fraud",
    granularity="week",
    max_bins=4,
)

counts = report.severity_counts()
print(f"\nSeverity: {counts}")


# %% Worst offenders ---------------------------------------------------

for f in sorted(report.features, key=lambda x: x.severity != "red"):
    icon = {"red": "🔴", "yellow": "🟡", "green": "🟢"}.get(f.severity, "⚪")
    print(f"  {icon} {f.severity:>6}  {f.name:<24}  {f.verdict}")


# %% CI-style fail-on threshold ----------------------------------------

if report.has_drift("yellow"):
    print("\n→ Drift detected at WATCH or worse — would fail a CI gate.")
else:
    print("\n→ Clean. CI gate would pass.")


# %% HTML report --------------------------------------------------------

out = Path(tempfile.gettempdir()) / "fraud_ieee_dqt.html"
report.save_html(out)
print(f"\nReport saved to {out}")

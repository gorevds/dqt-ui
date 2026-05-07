"""Credit-scoring drift triage — synthetic LendingClub-style portfolio.

This example mirrors the workflow a credit-risk analyst follows:

1. Pull a snapshot of recent applications + their default flag.
2. Run DQT over the time axis to see whether each input still behaves
   the way the scorecard expects.
3. Surface the worst offenders and decide which features to retrain.

The dataset here is synthetic so the example runs offline with no
external download. Replace ``df = make_lendingclub_like()`` with your
own DataFrame to use the example as-is on real data.

To convert to an .ipynb run::

    pip install jupytext
    jupytext --to notebook examples/credit_lendingclub.py
"""
from __future__ import annotations

# %% Imports --------------------------------------------------------------

import tempfile
from pathlib import Path

import pandas as pd

from dqt import analyze
from dqt.demo import make_demo_dataset


# %% Generate synthetic data ---------------------------------------------

def make_lendingclub_like(n_rows: int = 4000, seed: int = 42) -> pd.DataFrame:
    """A loan-application style dataset with deliberate drift signals.

    Borrowed from :func:`dqt.demo.make_demo_dataset` but with the column
    names tightened to the LendingClub vocabulary so this notebook reads
    closer to a real engagement.
    """
    df = make_demo_dataset(n_rows=n_rows, seed=seed)
    df = df.rename(columns={
        "application_date": "issue_date",
        "client_age": "borrower_age",
        "app_amount": "loan_amount",
        "app_term_months": "term_months",
        "app_type": "loan_type",
        "monthly_income": "annual_income",
        "previous_default_rate": "prior_default_rate",
        "default_flag": "is_default",
    })
    df["annual_income"] = (df["annual_income"] * 12).round(0)  # monthly → annual
    return df


df = make_lendingclub_like()
print(f"Loaded {len(df):,} rows, {len(df.columns)} columns")
print(df.head())


# %% Run DQT -------------------------------------------------------------

# Auto-detect everything except target / time, which we pin explicitly so
# the example is reproducible.
report = analyze(
    df,
    time_col="issue_date",
    target_col="is_default",
    granularity="month",
    max_bins=4,
)

print("\nSeverity counts:", report.severity_counts())


# %% Triage offenders ----------------------------------------------------

offenders = sorted(
    [f for f in report.features if f.severity in ("red", "yellow")],
    key=lambda f: (f.severity != "red", f.summary.get("psi_max") or 0.0),
    reverse=True,
)

print("\nTop offenders:")
for f in offenders[:10]:
    print(f"  [{f.severity:>6}]  {f.name:<25}  {f.verdict}")


# %% Drill into one feature ---------------------------------------------

top = offenders[0] if offenders else report.features[0]
print(f"\nDrilling into {top.name}: {top.verdict}")
print(f"  PSI max:        {top.summary.get('psi_max', float('nan')):.3f}")
print(f"  Stability min:  {top.summary.get('stability_min', float('nan')):.3f}")
print(f"  Missing max:    {top.summary.get('missing_share_max', 0):.1%}")


# %% Save HTML report ----------------------------------------------------

out = Path(tempfile.gettempdir()) / "credit_lendingclub_dqt.html"
report.save_html(out)
print(f"\nReport saved to {out}")
print("Open it in your browser, or share the file with the model risk team.")

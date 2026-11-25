# Pairwise z-stability vs PSI / KS / Wasserstein / JSD

DQT's claim to a novel metric — *pairwise z-score bin stability* — is only
worth making if the metric does something none of the established
distribution-shift tests do. This page is the empirical test.

## Setup

Four synthetic two-period scenarios (5 000 rows each), all using a
single numeric feature `x ~ N(0, 1)` and a binary target `y` whose log-
odds is `−1.5 + slope · x`.

| Scenario | What changed | What broke |
|---|---|---|
| **no-drift** | Nothing — both periods drawn from the same distribution. | Sanity baseline; every metric should be ~ 0. |
| **covariate** | `x` shifts from `N(0, 1)` to `N(1.5, 1)`. The slope `+1.2` is unchanged. | Distribution drift, model relationship intact. |
| **concept** | `x` distribution unchanged. Slope flips from `+1.2` to `−1.2`. | Distribution intact, model relationship inverted. |
| **mixing** | Both at once: `x` shifts and slope flips. | Both. |

The script that generated the table is `docs/benchmark_metrics.py` — run
`python docs/benchmark_metrics.py` to reproduce.

## Results

```
scenario    psi_x    ks_x    wasserstein_x   jsd_x    stability_cur
no-drift    0.0016   0.0114  0.020           0.0003   1.0000
covariate   2.049    0.5576  1.518           0.3011   1.0000
concept     0.0016   0.0114  0.020           0.0003   0.9801
mixing      2.049    0.5576  1.518           0.3011   1.0000
```

(Same numbers in machine-readable form: `docs/benchmark_metrics.csv`.
Re-run `python docs/benchmark_metrics.py` after touching `core/quality.py`
and confirm the CSV doesn't change.)

## Read it like this

* **PSI / KS / Wasserstein / JSD** — every distribution-level metric
  fires only on rows whose `x` distribution moved. They cannot see the
  concept-drift scenario at all (`x` was unchanged), even though the
  model's relationship to `y` flipped completely.
* **Pairwise z-stability** — drops on concept drift (0.980 vs 1.000
  baseline) without needing a covariate change. It also **stays at 1.0
  on the mixing scenario** because the bins built on the reference
  period are still well-separated *within* the current period — they
  are just *inverted*. This is the metric's known limitation; see
  "Honest caveats" below.

The takeaway: **distribution metrics and stability are complementary,
not interchangeable**. PSI tells you the input moved; stability tells
you the bin structure inside each period still looks like it should.
You need both, and that's why DQT computes both for every feature.

## Where pairwise z-stability is decisive

Cases where the standard distribution metrics **say everything is fine
but the scorecard is silently broken**:

1. **Bin collapse from a deployment bug.** A categorical feature gets
   silently truncated to two values (e.g. a one-hot encoder version
   mismatch). PSI on the broken column may stay ≈ 0 if the surviving
   categories' shares are similar, but the bin tree fits a single bin —
   stability collapses.
2. **Calibration loss without distribution shift.** External score
   provider's model retrained, output range still ~ N(600, 80) but
   ordering with respect to your target weakened. PSI on the score
   stays low (range matches), but bin-level target-rate gap shrinks.
3. **Censoring / data-pipeline bugs that null out one tail.** Feature
   distribution looks identical because the missing rows were silently
   dropped before the metric saw them, but the bin you used to lean
   on is empty in production.

## Honest caveats

* **Pairwise z-stability does not catch order reversal.** If a "low-
  risk" bin and a "high-risk" bin trade places between periods, both
  bins are still well-separated within each period (only the labels
  swap). The metric stays high. The right tool for that failure mode
  is a per-bin target-rate trend chart (which DQT also renders) or a
  rank-correlation check across periods (planned, see
  [good-first-issues](../.github/ISSUE_TEMPLATE/good_first_issues.md)).
* **Multiclass without `--positive-class` is excluded from stability.**
  Integer-coding nominal classes makes the bin "rate" arbitrary; the
  stability number would track the code order, not the data. DQT
  suppresses the metric in that case rather than show a misleading
  number.
* **Stability is binary-on-binary or regression-on-continuous.** For
  multiclass triage, binarise upstream against the class you actually
  monitor (the credit-risk team almost always cares about exactly one
  class — "default", "churn", "fraud" — and that's the right
  positive-class to fix).

## Reproducibility

The seed is fixed (`12`); the CSV checked in matches what the script
produces on a clean Python 3.12 + numpy 2.x + scipy 1.17 environment.
Re-run after any change to `dqt/core/quality.py` to confirm no
behaviour regression.

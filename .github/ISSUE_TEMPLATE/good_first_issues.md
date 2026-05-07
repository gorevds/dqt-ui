# Good first issues — seeds

This file is a curated list of starter contributions. Each item is sized
for one PR by a developer new to DQT. Open an issue using the template
referenced and link this file in the body.

## 1. README localisation: pick a language

**Files:** `README.<lang>.md`, top of `README.md` (language switcher row).

**Why:** ru is in flight. English landing page is generic; localised
versions remove a real adoption barrier in CIS / India / LATAM.

**Acceptance:** New `README.<lang>.md` mirroring section structure of
`README.md`; language switcher line `[English](README.md) | [<lang>](README.<lang>.md)`
prepended to both files.

## 2. Postgres native connector for `dqt analyze`

**Files:** `dqt/cli.py`, `tests/test_cli.py`, optional new
`dqt/io/postgres.py`.

**Why:** SQL via SQLAlchemy works but pulls every row. A native
psycopg2-based path with server-side cursor would scale better.

**Acceptance:** `--postgres-uri` flag + `--postgres-source TABLE_OR_QUERY`;
lazy-imported `psycopg2`; happy-path test against a sqlite fallback or
Postgres dialect URL.

## 3. Sample notebook: e-commerce churn

**Files:** `examples/churn_ecommerce.ipynb`.

**Why:** Most DQT users come from credit-risk; we want to demonstrate
non-banking applicability.

**Acceptance:** Notebook runs offline (synthetic data is fine), produces
an HTML report, walks through one drift verdict and one stable feature.

## 4. JSON Schema for `dqt analyze` output

**Files:** `docs/run_schema.json`, link from README.

**Why:** People want to consume DQT runs from external tooling. A
documented JSON schema for what `dqt analyze --save-run` writes lets
downstream automations validate before parsing.

**Acceptance:** Schema describing `runs.list_runs()` rows plus
`runs.get(id)` body; CI test that round-trips a real run through the
schema.

## 5. Localised severity verdicts

**Files:** `dqt/app/pipeline.py` (`_verdict_for`), new
`dqt/i18n/<lang>.py`.

**Why:** Verdict text is currently English-only. Pluggable locales let
non-English teams use the report verbatim in stakeholder reviews.

**Acceptance:** `DQT_VERDICT_LOCALE=ru` switches the verdict strings;
fallback to `en` if locale is unknown; one Russian translation included.

## 6. CSV with explicit time format flag

**Files:** `dqt/cli.py`, `dqt/api.py`, `dqt/core/time_utils.py`.

**Why:** Auto-parsing is convenient but brittle on European date
formats. A `--time-format "%d.%m.%Y"` flag lets users pin parsing.

**Acceptance:** New optional argument plumbed through to
`bucket_time` / `pd.to_datetime`; documented; one regression test on a
DD.MM.YYYY-style fixture.

---

How to claim one: comment "I'd like to take this" on the issue. The
maintainer will assign and link the PR back here when it merges.

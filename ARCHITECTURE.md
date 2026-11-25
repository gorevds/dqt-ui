# DQT — Architecture

This is a contributor-oriented overview of how DQT is organised, where the
boundaries are, and which extension points exist. The user-facing
documentation lives in [README.md](README.md). Read this before starting a
non-trivial PR.

## Layered design

```
┌─────────────────────────────────────────────────────────────┐
│  dqt.app   ─ Dash UI: callbacks, session store, file uploads │
│            ─ Lazy use of dqt.core; never imported by core.   │
├─────────────────────────────────────────────────────────────┤
│  dqt.api   ─ Public Python API: analyze() → Report          │
│  dqt.cli   ─ argparse front end: serve / analyze / runs     │
│  dqt.runs  ─ SQLite history of CLI runs                     │
│  dqt.notify─ Slack/JSON webhook posting                     │
│  dqt.config─ severity threshold overrides (YAML/JSON/env)    │
├─────────────────────────────────────────────────────────────┤
│  dqt.plots ─ Plotly figure builders, no Dash imports        │
│  dqt.report─ Self-contained Jinja2 HTML export              │
├─────────────────────────────────────────────────────────────┤
│  dqt.core  ─ Pure pandas/scikit-learn/scipy compute kernel  │
│            ─ No UI, no plotly, no Dash, no Flask.           │
└─────────────────────────────────────────────────────────────┘
```

The arrow direction is strict: `dqt.core` is at the bottom and depends on
nothing in the layers above; `dqt.app` is at the top and may depend on
anything below. This is not a stylistic preference — it is the contract
that makes `dqt.core` reusable as a headless library.

## Repository map

| Path | Purpose |
|---|---|
| `dqt/core/` | Compute kernel. PSI, tree binning, stability, time bucketing, autodetect heuristics, target-kind detection. |
| `dqt/plots/` | Plotly figures. Inputs are plain DataFrames. No callbacks. |
| `dqt/report/` | Jinja2 HTML report — Plotly figures embedded as CDN-loaded JSON. |
| `dqt/app/` | Dash 2.x application: layout, 4 callbacks for Upload→Columns→Settings→Report, session store, upload parser. |
| `dqt/api.py` | The Python entry point: `from dqt import analyze`. Wraps the pipeline and returns `Report`. |
| `dqt/cli.py` | argparse CLI: `dqt analyze`, `dqt serve`, `dqt runs {list,show,delete}`. |
| `dqt/runs.py` | SQLite (`~/.dqt/runs.db`) history of saved analyses. |
| `dqt/config.py` | YAML/JSON/env severity threshold overrides, per-feature. |
| `dqt/notify.py` | POST a result summary to a Slack/Teams/JSON webhook. |
| `dqt/integrations/` | Optional integrations (MLflow, Airflow, dbt). All imports of third-party tooling are lazy. |
| `dqt/demo.py` | Synthetic loan-application dataset (24 monthly buckets) with deliberate drift / missingness / outliers. |
| `tests/` | pytest. `conftest.py` exposes the `binary_df` fixture used everywhere. |
| `docs/` | Long-form notes (e.g. metric benchmarks). |
| `deploy/` | One-shot installer (`install.sh`), nginx + certbot + systemd. |
| `actions/dqt/` | The `gorevds/dqt-action` GitHub Action (composite). |
| `.github/workflows/` | CI: pytest + ruff. Trusted-publishing release workflow. |

## Data flow — from upload to a saved run

```
CSV / Parquet / SQL
        │
        ▼
  parse_upload()           dqt.app.io   (UI path)
  _read_file() / _read_sql() dqt.cli   (CLI path)
        │
        ▼
  autodetect.{time,target,features}
        │
        ▼
  detect_target_kind  →  TargetKind {BINARY, MULTICLASS, REGRESSION}
        │
        ▼
  bucket_time()             dqt.core.time_utils
        │
        ▼
  fit_binner()              dqt.core.grouping (sklearn DecisionTree*)
  binner.transform(df)
        │
        ▼
  for each feature:
    psi_over_time()
    bins_target_rate_over_time()
    pairwise_bin_stability(target_kind=<kind>)
    missingness_over_time()
    outlier_share_over_time()
        │
        ▼
  stability_summary()      → severity (green/yellow/red) via dqt.config
        │
        ▼
  Report (api.py dataclass) → HTML / Slack / runs DB / notebook _repr_html_
```

## Session model

`dqt.app.store.SessionStore` is a thread-safe in-memory dict with three
guard rails added in v1.1:

* **TTL eviction** via a background sweeper thread (every 5 min). Sessions
  older than `ttl_seconds` (default 4 h) are dropped.
* **LRU cap** at `max_sessions` (default 64). The oldest session is evicted
  when a new one would push above the cap.
* **Optional disk persistence.** When `DQT_SESSION_DIR` is set, every
  mutation (upload / column choice / settings / report cache) writes a
  `<sid>.parquet` (DataFrame) and `<sid>.json` (metadata) sidecar. On
  restart the store reloads sessions from that directory. Stale entries on
  disk are pruned during restore.

A single gunicorn worker is still assumed. For multi-worker horizontal
scaling, swap `STORE` with a Redis or Postgres-backed implementation that
honours the same shape (`create / get / get_or_create / save / reset /
sweep`).

### Session state schema

| Field | Set by | Carries |
|---|---|---|
| `sid` | `create()` | UUID-hex session id; appears in URLs as `?session=<sid>` |
| `created_at` | `create()` | epoch seconds |
| `last_seen` | `get()` | bumped on every retrieval — drives TTL |
| `df` | upload / demo callbacks | the working DataFrame |
| `filename` | upload / demo callbacks | display name only |
| `columns_meta` | columns page | `{time, target, features}` |
| `settings` | settings page | `{method, max_bins, granularity, …}` |
| `report_cache` | report page | full pipeline result dict, invalidated on any change above |

## Severity thresholds

`dqt.config.Thresholds` holds the cut-offs the verdict logic uses:

```
yellow    red
psi          0.10  0.25
stability    0.80  0.60
missing      0.20  0.50
```

The defaults are the standard banking thresholds (Lewis / Yurdakul). Users
override globally via env (`DQT_THRESHOLDS_PATH=/path/to/thresholds.yaml`)
or per-feature in the same YAML/JSON. `severity_for(...)` returns the
worst-of-metric verdict.

## Extension points

| Extension | Where | What it gets you |
|---|---|---|
| Custom severity thresholds | `dqt.config` | YAML/JSON overrides per-feature. |
| Webhook notifier | `dqt.notify.post()` | Slack / Teams / JSON payloads from the CLI. |
| Run history backend | `dqt.runs` | SQLite is the default; replace by writing your own `save / list / get / delete`. |
| Session store | `dqt.app.store.SessionStore` | Provide a Redis/Postgres-backed object exposing the same methods, then assign `STORE`. |
| Integrations | `dqt.integrations.*` | New `dqt/integrations/<name>.py` modules — lazy-imported third-party deps (Airflow, MLflow, dbt, etc.). |
| Plugin metrics | `entry_points = "dqt.metrics"` (planned, see `dqt.plugins`) | Install a third-party package; new metric appears in every report. |
| GitHub Action | `actions/dqt/action.yml` | Composite action that wraps `dqt analyze` for CI. |

## CLI vs UI: contract symmetry

Both call `dqt.api.analyze(...)`. Anything that affects analysis must go
through that function so the CLI and UI stay in lock-step. Resist the
temptation to reach into `dqt.app.pipeline.run_analysis` from new
front-ends — it is the plumbing, not the contract.

Things that intentionally diverge:

* Drill-down samples (`drill_samples`) are kept only in `report_cache`,
  never written to HTML — they can carry PII.
* The UI defaults `max_bins=5`; the CLI defaults `max_bins=3`. Not a bug:
  CI gates prefer fewer bins (faster + more conservative); the UI gives
  more visual detail.

## Testing strategy

* `dqt/core/*` is covered by direct unit tests with the synthetic
  `binary_df` fixture in `tests/conftest.py`.
* `dqt/app/main.py` has a smoke test only — Dash callbacks are
  notoriously hard to unit-test. PRs that touch callbacks should run
  `dqt serve` locally and walk the 4-step flow.
* The session store has its own test module (`tests/test_store.py`) that
  drives sweep/LRU/disk-persistence deterministically.
* Integrations use a stub-friendly architecture: third-party tooling is
  imported inside the function body, so unit tests can monkey-patch the
  module-level alias without paying the import cost.

## Running locally

```bash
. .venv/bin/activate
pip install -e ".[test]"
pytest -q                 # all green expected
ruff check dqt tests      # lint
dqt serve --debug         # Dash dev server
```

## Known limits

* Single-process worker — see "Session model" for swap-out path.
* `pairwise_bin_stability` for multiclass without `--positive-class`
  silently treats classes as ordinal codes via `pd.factorize`. The
  resulting score is a heuristic; binarise upstream when the precise
  semantics matter.
* `parse_upload` rejects payloads above `DQT_MAX_UPLOAD_MB` after
  decoding the base64 payload, so the in-memory peak is briefly
  ~1.4× the cap. Multi-GB uploads should arrive via SQL/parquet path.
* Drill-down samples are kept in memory only; sharing a `?session=<sid>`
  URL across processes (or after restart without `DQT_SESSION_DIR`)
  drops them.

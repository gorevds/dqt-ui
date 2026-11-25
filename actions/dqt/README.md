# `dqt-action` — DQT for GitHub Actions

Drop a `dqt analyze` step into any workflow. The action installs the
`dqtui` package, runs the analysis, uploads the HTML report as an
artefact, and surfaces severity counts so you can fan out into Slack /
Issues / labels.

## Quickstart

```yaml
name: Drift gate
on:
  schedule:
    - cron: "0 9 * * 1"      # Monday 09:00 UTC
  workflow_dispatch:

jobs:
  drift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: gorevds/dqt-ui/actions/dqt@main
        with:
          data: data/applications_history.parquet
          time: snapshot_date
          target: default_flag
          fail-on: red
          notify: ${{ secrets.SLACK_WEBHOOK_URL }}
```

## Common patterns

**Pin the package version** for reproducibility:

```yaml
      - uses: gorevds/dqt-ui/actions/dqt@main
        with:
          data: data.parquet
          dqtui-version: "1.1.0"
```

**Compare against a golden reference**:

```yaml
      - uses: gorevds/dqt-ui/actions/dqt@main
        with:
          data: data/current.parquet
          reference: data/2024Q4_baseline.parquet
          time: snapshot_date
          target: default_flag
```

**Multiclass: binarise against the class you actually care about**:

```yaml
      - uses: gorevds/dqt-ui/actions/dqt@main
        with:
          data: data.parquet
          target: severity
          positive-class: "high"
```

**Database source** (use a self-hosted runner with network access to your
warehouse — secrets shown as a sketch only):

```yaml
      - uses: gorevds/dqt-ui/actions/dqt@main
        with:
          sql-uri: ${{ secrets.SCORING_DB_URI }}
          sql-source: SELECT * FROM scoring.applications_last_90d
          time: created_at
          target: default_flag
```

## Inputs

| Name | Default | Description |
|---|---|---|
| `data` | — | Path to CSV/Parquet relative to the workspace. |
| `sql-uri` | — | SQLAlchemy URL. Mutually exclusive with `data`. |
| `sql-source` | — | Table name or SELECT query for `sql-uri`. |
| `reference` | — | Optional baseline file for PSI comparison. |
| `time` | autodetect | Time column. |
| `target` | autodetect | Target column. |
| `positive-class` | — | Multiclass binarisation target. |
| `features` | autodetect | Space-separated feature list. |
| `max-bins` | `3` | Max bins per feature. |
| `granularity` | `auto` | `auto / day / week / month / quarter / year`. |
| `fail-on` | `red` | `none / yellow / red` — exit code 2 on severity ≥ this. |
| `output` | `dqt-report.html` | Path for the HTML report. |
| `notify` | — | Webhook URL (Slack / Teams / generic). |
| `notify-format` | `slack` | `slack / json`. |
| `python-version` | `3.11` | Passed to `actions/setup-python`. |
| `dqtui-version` | latest | Pin a specific PyPI version. |
| `upload-artifact` | `true` | Whether to upload the HTML report. |
| `artifact-name` | `dqt-report` | Name for the uploaded artefact. |

## Outputs

| Name | Example | Use it for |
|---|---|---|
| `report-path` | `/runner/work/.../dqt-report.html` | Pass to a custom upload step. |
| `severity` | `red` | Fan out into Slack only on red. |
| `red-count` | `2` | Render in a job summary. |
| `yellow-count` | `5` | Same. |

## Conditional fan-out on severity

```yaml
      - uses: gorevds/dqt-ui/actions/dqt@main
        id: dqt
        with:
          data: data.parquet
          fail-on: none      # don't fail the job; let the next step decide
      - if: steps.dqt.outputs.severity == 'red'
        run: |
          gh issue create -t "Drift detected: ${{ steps.dqt.outputs.red-count }} features" \
                          -b "See attached HTML report from this run."
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

## Caveats

- **Linux / macOS runners only.** The composite uses bash heredocs and
  `>> $GITHUB_OUTPUT` redirects that don't work reliably on
  Windows-hosted runners. Pin `runs-on: ubuntu-latest` (or
  `macos-latest`) for jobs that use this action; Windows users should
  run `dqt analyze` directly from their workflow.
- The action installs `dqtui` from PyPI on every run. For self-hosted
  runners with a slow network, pre-bake the image with `pip install
  dqtui` to skip the install step.
- `--save-run` is always passed so the run shows up in the runs DB and
  the action can extract severity. The runs DB lives at `~/.dqt/` on
  the runner, which is ephemeral by default — wire a cache step if you
  need cross-run history.
- Self-contained HTML report can be tens of MB on wide datasets;
  upload-artifact retention defaults apply.

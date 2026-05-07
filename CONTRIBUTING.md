# Contributing to DQT

Thanks for considering a contribution. DQT is a small, opinionated tool
maintained by a single developer; the bar for merging is **code that the
maintainer is comfortable owning**, not feature parity with bigger tools.

## Before you start

1. Read [ARCHITECTURE.md](ARCHITECTURE.md) — the layered design is strict
   and most "obvious" PRs that violate it will get a redesign request.
2. Open an issue first for anything bigger than a doc fix or an obvious
   bug. We don't want you to write a 500-line PR only to learn the answer
   is "no".
3. Search existing issues — many ideas have been triaged already.

## Setup

```bash
git clone https://github.com/gorevds/dqt-ui
cd dqt-ui
python -m venv .venv && . .venv/bin/activate
pip install -e ".[test]"
pytest -q                 # ~130 tests, all green
ruff check dqt tests
```

To run the UI for manual testing:

```bash
dqt serve --debug
# open http://localhost:8050 ; click "Load demo dataset" if you don't have your own.
```

To run the CLI against the demo:

```bash
python -c "from dqt.demo import make_demo_dataset; make_demo_dataset(2000).to_csv('/tmp/d.csv', index=False)"
dqt analyze /tmp/d.csv -o /tmp/d.html --fail-on=red
```

## Pull-request expectations

* **One idea per PR.** Bundling unrelated changes makes review slower and
  riskier.
* **Tests for any new metric, callback, or integration.** Even a one-line
  test is enough; we don't ask for coverage targets, only that future
  refactors won't silently break your contribution.
* **Type hints everywhere.** `from __future__ import annotations` is
  already at every module top; honour the existing style.
* **Stick to the layering.** `dqt.core` does not import `dqt.app`,
  `plotly`, or `dash`. If your change requires it, propose a module split
  in the issue first.
* **Document non-obvious "why".** Comments explaining *what* the code
  does are usually noise (well-named identifiers do that). A one-line
  comment explaining a hidden constraint or a workaround is gold.

## Code style

* Ruff with `line-length=110`, rule sets `E,F,W,I,B`. CI fails on any
  violation. Run `ruff format` (or your editor's auto-format) before
  pushing.
* No trailing-whitespace, no tabs, UTF-8.
* Imports grouped: standard library / third-party / first-party.
* No emojis in code or comments unless they exist in the codebase already.

## Commit and PR conventions

We use Conventional Commits-style prefixes — `feat`, `fix`, `docs`,
`refactor`, `test`, `build`, `ci`, `chore`. Squash-merge is the default,
so the PR title becomes the merge commit. Example PR titles that read
well in `git log --oneline`:

```
feat(api): expose drill_samples on Report.feature(name)
fix(autodetect): narrow datetime parse exception, drop UserWarning noise
docs(readme): clarify --fail-on yellow vs red semantics
```

Do not add `Co-Authored-By: Claude` (or any other AI-attribution
trailer) to commit messages. The maintainer strips these on merge if
they sneak in.

## Areas that welcome contribution

These are explicit invitations — open a PR without an issue first.

1. **New connector for `dqt analyze`** — Postgres native, BigQuery,
   Athena. Lazy-import the SDK; mirror the existing `--sql-uri` flag
   shape.
2. **Localised README** — translate `README.md` to your language. Add a
   `README.<lang>.md` and a language switcher line at the top of every
   variant. We already have `ru` planned.
3. **Sample notebooks** — `examples/<dataset>.ipynb` showing a real
   triage flow. The synthetic `make_demo_dataset()` is fine if a public
   dataset isn't available offline.
4. **Severity verdicts in another language** — `_verdict_for()` builds
   English strings. A pluggable verdict locale is in scope.
5. **Custom metrics plugin** — write one against the entry-points API
   (`dqt.metrics`). Even a thin example helps validate the contract.

## Areas that will likely be declined

We're not chasing parity with the broader MLops ecosystem. Please don't
spend a weekend on these without asking first.

* **LLM / text / image / embedding drift** — out of scope; that's
  Evidently's home turf.
* **Performance estimation without ground truth (CBPE/DLE)** — that's
  NannyML's specialty and would dilute DQT's positioning.
* **Schema enforcement / data contracts** — covered well by
  `great_expectations` / `pandera` / `soda-core`.
* **General-purpose EDA snapshots** — `ydata-profiling` exists.

## Reporting issues

Open an issue with the bug-report template and a minimal reproducer. If
the bug only shows up in the UI, attach a screenshot.

## Releasing (maintainer only)

1. Bump version in `pyproject.toml`.
2. Update `CHANGELOG.md` (Keep-a-Changelog format).
3. Tag `vX.Y.Z` and push tag.
4. Trusted-publishing GitHub Action releases to PyPI; GHCR workflow
   builds and pushes the Docker image.
5. Update the live demo at `https://dqt.gorev.space`.

## License

By contributing you agree your code is released under the MIT License,
the same license DQT itself uses.

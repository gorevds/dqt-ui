"""Log a DQT report to MLflow.

Usage::

    import mlflow
    from dqt import analyze
    from dqt.integrations.mlflow import log_report

    with mlflow.start_run() as run:
        report = analyze(df)
        log_report(report)               # logs HTML, severity JSON, key metrics
        # ... your training code ...

What it logs into the active run:

* ``dqt-report.html`` — the self-contained Plotly report, as an artefact.
* ``dqt-summary.json`` — severity counts + per-feature verdict, as an
  artefact (cheap to download for downstream comparisons).
* Metrics ``dqt.green / dqt.yellow / dqt.red`` — severity counts as
  numeric metrics so you can plot drift over runs in the MLflow UI.
* Tags ``dqt.target_col / dqt.time_col / dqt.target_kind`` — for filter
  / search.

The function is a no-op if MLflow is not installed; the import is lazy
so ``import dqt.integrations.mlflow`` does not pull MLflow itself.
"""
from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:  # pragma: no cover
    from dqt.api import Report

_log = logging.getLogger(__name__)


def _import_mlflow() -> Any:
    try:
        import mlflow  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "dqt.integrations.mlflow requires the mlflow package. "
            "Install it with `pip install mlflow`."
        ) from exc
    return mlflow


def log_report(
    report: "Report",
    *,
    artifact_path: str = "dqt",
    run_id: Optional[str] = None,
    extra_tags: Optional[dict] = None,
) -> dict:
    """Log a :class:`dqt.api.Report` to the active (or specified) MLflow run.

    Parameters
    ----------
    report
        The result of :func:`dqt.analyze`.
    artifact_path
        Sub-folder inside the run where the HTML and JSON land.
    run_id
        If given, log to this run instead of the active one. Useful when
        DQT runs in a separate process from training.
    extra_tags
        Extra tags merged into the run.

    Returns
    -------
    dict
        The summary dict that was logged as JSON, so callers can inspect
        without re-reading the artefact.
    """
    mlflow = _import_mlflow()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        html_path = tmp_path / "dqt-report.html"
        json_path = tmp_path / "dqt-summary.json"
        report.save_html(html_path)

        counts = report.severity_counts()
        summary = {
            "severity_counts": counts,
            "n_features": len(report.features),
            "meta": report.meta,
            "features": [
                {"name": f.name, "severity": f.severity, "verdict": f.verdict,
                 "summary": _json_safe(f.summary)}
                for f in report.features
            ],
        }
        json_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

        client = mlflow.tracking.MlflowClient()
        if run_id is None:
            active = mlflow.active_run()
            if active is None:
                raise RuntimeError(
                    "log_report() needs an active MLflow run; "
                    "call mlflow.start_run() first or pass run_id=..."
                )
            run_id = active.info.run_id

        client.log_artifact(run_id, str(html_path), artifact_path)
        client.log_artifact(run_id, str(json_path), artifact_path)
        client.log_metric(run_id, "dqt.green", float(counts.get("green", 0)))
        client.log_metric(run_id, "dqt.yellow", float(counts.get("yellow", 0)))
        client.log_metric(run_id, "dqt.red", float(counts.get("red", 0)))
        client.set_tag(run_id, "dqt.target_col", str(report.meta.get("target_col") or ""))
        client.set_tag(run_id, "dqt.time_col", str(report.meta.get("time_col") or ""))
        client.set_tag(run_id, "dqt.target_kind", str(report.meta.get("target_kind") or ""))
        for k, v in (extra_tags or {}).items():
            client.set_tag(run_id, str(k), str(v))

        _log.info("dqt: logged report to run %s under artefact path %r", run_id, artifact_path)
        return summary


def _json_safe(obj: Any) -> Any:
    """Coerce numpy / pandas scalars / NaN / arrays to plain Python."""
    import math

    import numpy as np
    import pandas as pd

    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [_json_safe(v) for v in obj.tolist()]
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if math.isnan(v) else v
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if obj is pd.NaT or obj is getattr(pd, "NA", None):
        return None
    if isinstance(obj, float):
        return None if math.isnan(obj) else obj
    return obj

"""Tests for the MLflow integration. We don't depend on mlflow itself —
the import is stubbed so the test runs without ``pip install mlflow``.
"""
from __future__ import annotations

import sys
import types
from typing import Any


def _install_mlflow_stub() -> dict:
    """Insert a fake ``mlflow`` module into sys.modules and return the
    structure used to capture calls.
    """
    captured: dict[str, Any] = {
        "artifacts": [], "metrics": {}, "tags": {},
        "run_id": "stub-run-id",
    }

    class _ClientStub:
        def log_artifact(self, run_id, path, artifact_path):
            captured["artifacts"].append((run_id, path, artifact_path))

        def log_metric(self, run_id, key, value):
            captured["metrics"][key] = value

        def set_tag(self, run_id, key, value):
            captured["tags"][key] = value

    class _RunInfo:
        run_id = captured["run_id"]

    class _ActiveRun:
        info = _RunInfo()

    fake = types.ModuleType("mlflow")
    fake.tracking = types.ModuleType("mlflow.tracking")
    fake.tracking.MlflowClient = lambda: _ClientStub()
    fake.active_run = lambda: _ActiveRun()

    sys.modules["mlflow"] = fake
    sys.modules["mlflow.tracking"] = fake.tracking
    return captured


def test_log_report_round_trip(monkeypatch, binary_df):
    """A real DQT report logs html + json + 3 metrics + 3 tags."""
    captured = _install_mlflow_stub()
    monkeypatch.setattr(sys, "modules", sys.modules)

    from dqt import analyze
    from dqt.integrations.mlflow import log_report

    report = analyze(binary_df.head(800), time_col="date", target_col="target")
    summary = log_report(report)

    # Two artefacts logged: HTML + summary JSON.
    assert len(captured["artifacts"]) == 2
    paths = sorted(p[1] for p in captured["artifacts"])
    assert any(p.endswith("dqt-report.html") for p in paths)
    assert any(p.endswith("dqt-summary.json") for p in paths)

    assert set(captured["metrics"]) == {"dqt.green", "dqt.yellow", "dqt.red"}
    assert captured["tags"]["dqt.target_col"] == "target"
    assert captured["tags"]["dqt.time_col"] == "date"

    assert "severity_counts" in summary
    assert summary["meta"]["target_col"] == "target"

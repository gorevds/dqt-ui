"""Tests for the Airflow operator. Airflow itself is stubbed."""
from __future__ import annotations

import sys
import types

import pytest


def _install_airflow_stub() -> None:
    """Pin a tiny ``airflow.models`` and ``airflow.exceptions`` module."""
    if "airflow" in sys.modules:
        return
    af = types.ModuleType("airflow")
    af.models = types.ModuleType("airflow.models")
    af.exceptions = types.ModuleType("airflow.exceptions")

    class _BaseOperator:
        template_fields = ()

        def __init__(self, *, task_id="t", **kwargs):
            self.task_id = task_id

    class _AirflowException(Exception):
        pass

    af.models.BaseOperator = _BaseOperator
    af.exceptions.AirflowException = _AirflowException
    sys.modules["airflow"] = af
    sys.modules["airflow.models"] = af.models
    sys.modules["airflow.exceptions"] = af.exceptions


def test_operator_runs_on_csv(tmp_path, binary_df):
    _install_airflow_stub()
    from dqt.integrations.airflow import DQTAnalyzeOperator

    csv = tmp_path / "data.csv"
    binary_df.head(800).to_csv(csv, index=False)

    op = DQTAnalyzeOperator(
        task_id="t",
        input_path=str(csv),
        time_col="date",
        target_col="target",
        fail_on="none",
        save_run=False,
    )
    summary = op.execute(context={})
    assert "severity_counts" in summary
    assert summary["target_col"] == "target"
    assert summary["n_features"] >= 1


def test_operator_raises_when_drift_threshold_hit(tmp_path, binary_df):
    _install_airflow_stub()
    from dqt.integrations.airflow import DQTAnalyzeOperator

    # Force every feature into red severity by setting absurd thresholds via
    # the test by spiking last-month rate. Easier: request fail_on=yellow with
    # drifty demo data — binary_df has injected drift.
    csv = tmp_path / "data.csv"
    binary_df.to_csv(csv, index=False)

    op = DQTAnalyzeOperator(
        task_id="t", input_path=str(csv),
        time_col="date", target_col="target",
        fail_on="yellow", save_run=False,
    )
    with pytest.raises(Exception, match="drift"):
        op.execute(context={})


def test_operator_rejects_missing_input():
    _install_airflow_stub()
    from dqt.integrations.airflow import DQTAnalyzeOperator

    with pytest.raises(ValueError, match="input_path or sql_uri"):
        DQTAnalyzeOperator(task_id="t")


def test_operator_rejects_invalid_fail_on(tmp_path):
    _install_airflow_stub()
    from dqt.integrations.airflow import DQTAnalyzeOperator

    with pytest.raises(ValueError, match="fail_on"):
        DQTAnalyzeOperator(task_id="t", input_path="x.csv", fail_on="catastrophic")


def test_operator_class_identity_is_stable(tmp_path):
    """Two operator instances must share the same class object — Airflow's
    scheduler pickles operators in several execution modes, and a
    dynamically-minted subclass per __new__ would break that.
    """
    _install_airflow_stub()
    # Re-import to pick up the module-level class once the stub is in place.
    import importlib

    import dqt.integrations.airflow as airflow_mod

    importlib.reload(airflow_mod)

    op1 = airflow_mod.DQTAnalyzeOperator(task_id="t1", input_path="a.csv", fail_on="none")
    op2 = airflow_mod.DQTAnalyzeOperator(task_id="t2", input_path="b.csv", fail_on="none")
    assert type(op1) is type(op2)
    # Class should be the one exported by the module, not a fresh dynamic subclass.
    assert type(op1) is airflow_mod.DQTAnalyzeOperator

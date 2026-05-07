"""Airflow operator for DQT analyses.

Usage::

    from dqt.integrations.airflow import DQTAnalyzeOperator

    drift_check = DQTAnalyzeOperator(
        task_id="drift_check",
        input_path="/data/applications_last_90d.parquet",
        time_col="snapshot_date",
        target_col="default_flag",
        fail_on="red",
        output_path="/tmp/dqt_{{ ds }}.html",
    )

The operator pushes a JSON-serialisable summary to XCom under the default
return key (``return_value``); downstream tasks branch / notify off it
without re-reading the report.

Airflow itself is not declared as a hard dependency. The class hierarchy
is decided once at module import time:

* If ``airflow.models.BaseOperator`` is importable, ``DQTAnalyzeOperator``
  inherits from it directly. Pickling, dynamic task mapping, and
  cross-process scheduler serialization all work because the class
  identity is stable across processes.

* If Airflow is not installed, ``DQTAnalyzeOperator`` is a plain class
  whose ``__init__`` raises ``ImportError`` with a clear message — so
  ``import dqt.integrations.airflow`` never crashes a non-Airflow venv.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional, Sequence, Union

import pandas as pd

_log = logging.getLogger(__name__)


def _try_import_baseoperator() -> Optional[type]:
    try:
        from airflow.models import BaseOperator  # type: ignore[import-not-found]
    except ImportError:
        return None
    return BaseOperator


def _try_import_airflow_exception() -> type:
    try:
        from airflow.exceptions import AirflowException  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover
        # Fall back to a plain RuntimeError so non-Airflow callers (tests
        # that exercise execute() with a stub) still see the same shape.
        class AirflowException(RuntimeError):
            pass
    return AirflowException


_BASE = _try_import_baseoperator()


class _DQTAnalyzeMixin:
    """The actual operator behaviour. Mixed with Airflow's BaseOperator at
    module load when Airflow is available; instantiable on its own only
    in tests with an Airflow stub injected via :data:`sys.modules`.
    """

    template_fields: Sequence[str] = ("input_path", "output_path")

    def __init__(
        self,
        input_path: Optional[Union[str, Path]] = None,
        *,
        sql_uri: Optional[str] = None,
        sql_source: Optional[str] = None,
        time_col: Optional[str] = None,
        target_col: Optional[str] = None,
        positive_class: Optional[str] = None,
        features: Optional[Sequence[str]] = None,
        granularity: str = "auto",
        max_bins: int = 3,
        fail_on: str = "none",
        output_path: Optional[Union[str, Path]] = None,
        reference_path: Optional[Union[str, Path]] = None,
        notify_url: Optional[str] = None,
        notify_format: str = "slack",
        save_run: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if not (input_path or sql_uri):
            raise ValueError("DQTAnalyzeOperator: pass input_path or sql_uri")
        if fail_on not in ("none", "yellow", "red"):
            raise ValueError(f"fail_on must be none/yellow/red, got {fail_on!r}")
        self.input_path = str(input_path) if input_path else None
        self.sql_uri = sql_uri
        self.sql_source = sql_source
        self.time_col = time_col
        self.target_col = target_col
        self.positive_class = positive_class
        self.features = list(features) if features else None
        self.granularity = granularity
        self.max_bins = max_bins
        self.fail_on = fail_on
        self.output_path = str(output_path) if output_path else None
        self.reference_path = str(reference_path) if reference_path else None
        self.notify_url = notify_url
        self.notify_format = notify_format
        self.save_run = save_run

    def _load_dataframe(self) -> pd.DataFrame:
        from dqt.io import read_file, read_sql

        if self.input_path:
            return read_file(Path(self.input_path))
        return read_sql(self.sql_uri, self.sql_source or "")

    def execute(self, context: dict) -> dict:
        from dqt.api import analyze
        from dqt.notify import post as notify_post

        df = self._load_dataframe()
        ref_df = (_read_or_none(self.reference_path)
                  if self.reference_path else None)

        if self.positive_class is not None and self.target_col:
            df = df.copy()
            df[self.target_col] = (
                df[self.target_col].astype(str) == str(self.positive_class)
            ).astype(int)
            if ref_df is not None and self.target_col in ref_df.columns:
                ref_df = ref_df.copy()
                ref_df[self.target_col] = (
                    ref_df[self.target_col].astype(str) == str(self.positive_class)
                ).astype(int)

        report = analyze(
            df,
            time_col=self.time_col,
            target_col=self.target_col,
            features=self.features,
            granularity=self.granularity,
            max_bins=self.max_bins,
            reference_df=ref_df,
        )

        if self.output_path:
            report.save_html(self.output_path)
            _log.info("DQT report written to %s", self.output_path)

        if self.save_run:
            from dqt.runs import save as runs_save

            source = (self.input_path or f"sql:{self.sql_source}")
            runs_save(report, source=source)

        if self.notify_url:
            notify_post(self.notify_url, report, fmt=self.notify_format,
                        title=f"DQT — {report.meta['target_col']}")

        summary = {
            "severity_counts": report.severity_counts(),
            "n_features": len(report.features),
            "n_rows": int(report.meta["n_rows"]),
            "time_col": report.meta["time_col"],
            "target_col": report.meta["target_col"],
            "worst_features": [
                {"name": f.name, "severity": f.severity, "verdict": f.verdict}
                for f in report.features if f.severity in ("red", "yellow")
            ][:20],
            "report_path": self.output_path,
        }

        if self.fail_on != "none" and report.has_drift(self.fail_on):
            raise _try_import_airflow_exception()(
                f"DQT detected drift at severity ≥ {self.fail_on}: "
                f"{summary['severity_counts']}"
            )
        return summary


# Decide the public class once, at module load time, so the class identity
# is pickle-stable. Airflow's scheduler relies on that for any execution
# mode that serialises tasks across processes (LocalExecutor in some
# configurations, dynamic task mapping, the dag-bag deepcopy path, ...).

if _BASE is not None:
    class DQTAnalyzeOperator(_DQTAnalyzeMixin, _BASE):  # type: ignore[misc, valid-type]
        """Airflow operator for DQT analyses. See module docstring."""
else:
    class DQTAnalyzeOperator(_DQTAnalyzeMixin):  # type: ignore[no-redef]
        """Stub used when Airflow is not installed. ``__init__`` raises so
        users get a clear error instead of a silently bad inheritance.
        """

        def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401
            raise ImportError(
                "DQTAnalyzeOperator requires Apache Airflow. Install it "
                "with `pip install apache-airflow` or pin a constraints file."
            )


def _read_or_none(path: Optional[Union[str, Path]]) -> Optional[pd.DataFrame]:
    from dqt.io import read_file

    return None if path is None else read_file(Path(path))

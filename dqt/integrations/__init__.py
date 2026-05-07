"""Optional third-party integrations.

Each module imports its third-party dependency lazily inside the function
body so that simply importing :mod:`dqt.integrations` doesn't pull in
Airflow / MLflow / dbt-core / etc. The integrations test suite stubs the
relevant module via ``sys.modules`` to avoid heavy installs in CI.
"""
from __future__ import annotations

"""Public file/SQL read helpers — same shape used by the CLI and the
Airflow / dbt integrations. Stable surface as of v1.1.

Why these live here, not under ``dqt.app.io``:

* ``dqt.app.io`` parses base64-encoded HTTP uploads (Dash payloads).
* ``dqt.io`` parses on-disk paths and SQLAlchemy URLs — what every
  non-UI consumer needs.

External code should import from ``dqt.io`` and treat the surface as
public. The CLI keeps thin private wrappers for backwards compat.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def read_file(path: Path, engine: str = "auto") -> pd.DataFrame:
    """Read a CSV / TSV / TXT / Parquet from disk into a DataFrame.

    ``engine="duckdb"`` enables the duckdb backend for parquet — useful
    when the path is a directory glob or the file is too big for the
    default pyarrow path. duckdb is a lazy, optional dependency.
    """
    name = path.name.lower()
    if name.endswith((".csv", ".tsv", ".txt")):
        sep = "\t" if name.endswith(".tsv") else None
        if sep is None:
            return pd.read_csv(path, sep=None, engine="python")
        return pd.read_csv(path, sep=sep)
    if name.endswith((".parquet", ".pq")):
        if engine == "duckdb":
            try:
                import duckdb  # type: ignore
            except ImportError as exc:
                raise ImportError(
                    "engine='duckdb' requires the duckdb package "
                    "(`pip install duckdb`)."
                ) from exc
            return duckdb.query(f"SELECT * FROM '{path}'").to_df()
        return pd.read_parquet(path)
    raise ValueError(f"unsupported file extension: {path}")


def read_sql(uri: str, table_or_query: str) -> pd.DataFrame:
    """Read a table or SELECT query through SQLAlchemy.

    SQLAlchemy itself is an optional dep — imported lazily so plain
    file-only callers do not pay for it.
    """
    try:
        import sqlalchemy  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "SQL input requires SQLAlchemy (`pip install sqlalchemy` plus "
            "the driver for your database, e.g. psycopg2-binary / pymysql / "
            "snowflake-sqlalchemy)."
        ) from exc
    engine = sqlalchemy.create_engine(uri)
    if table_or_query.strip().lower().startswith("select"):
        return pd.read_sql(table_or_query, engine)
    return pd.read_sql_table(table_or_query, engine)


# Backwards-compat for any caller that imported the leading-underscore
# helpers from dqt.cli before they were promoted. New code should not
# rely on these.
_read_file: Any = read_file
_read_sql: Any = read_sql

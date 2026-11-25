"""Named reference baselines.

A baseline is a frozen DataFrame snapshot stored once and referenced by
many subsequent analyses (``--reference-baseline NAME``). Lets risk
teams say "compare every Monday's analysis to the 2024Q4 approved
baseline" without juggling file paths and golden-snapshot conventions.

Storage:
* metadata in the runs DB (a separate ``baselines`` table)
* DataFrame as a Parquet file in ``~/.dqt/baselines/`` (override via
  ``DQT_BASELINES_DIR``).

The metadata table stays small (one row per baseline + a sha256 of the
parquet) so listing is cheap; the parquet is loaded on demand.
"""
from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from dqt.runs import db_path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS baselines (
    name        TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    n_rows      INTEGER NOT NULL,
    n_cols      INTEGER NOT NULL,
    columns     TEXT NOT NULL,
    sha256      TEXT NOT NULL,
    description TEXT,
    parquet     TEXT NOT NULL
);
"""


def baselines_dir() -> Path:
    return Path(os.environ.get("DQT_BASELINES_DIR")
                or Path.home() / ".dqt" / "baselines")


@contextmanager
def _conn():
    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p)
    try:
        c.executescript(_SCHEMA)
        yield c
        c.commit()
    finally:
        c.close()


def freeze(name: str, df: pd.DataFrame, description: Optional[str] = None,
           overwrite: bool = False) -> dict:
    """Persist ``df`` as a named baseline and return the metadata row.

    Raises ``KeyError`` if ``name`` already exists and ``overwrite`` is
    False (default). Use ``overwrite=True`` to replace; the previous
    parquet file is deleted only if it sat at a different path than the
    one we're about to write.
    """
    name = name.strip()
    if not name:
        raise ValueError("baseline name must be non-empty")
    out_dir = baselines_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = out_dir / f"{uuid.uuid4().hex}.parquet"
    old_path = None
    try:
        df.to_parquet(parquet_path, index=False)
        digest = _sha256(parquet_path)
        with _conn() as c:
            c.execute("BEGIN IMMEDIATE")
            existing = c.execute("SELECT parquet FROM baselines WHERE name=?", (name,)).fetchone()
            if existing and not overwrite:
                raise KeyError(f"baseline {name!r} already exists; pass overwrite=True to replace")
            if existing:
                old_path = existing[0]
            created_at = datetime.utcnow().isoformat(timespec="seconds")
            columns = list(map(str, df.columns))
            c.execute(
                "INSERT OR REPLACE INTO baselines (name, created_at, n_rows, n_cols, columns, "
                "sha256, description, parquet) VALUES (?,?,?,?,?,?,?,?)",
                (name, created_at, len(df), len(columns), ",".join(columns), digest, description, str(parquet_path)),
            )
            if old_path and c.execute("SELECT 1 FROM baselines WHERE parquet=?", (old_path,)).fetchone():
                old_path = None
    except Exception:
        parquet_path.unlink(missing_ok=True)
        raise
    if old_path:
        _remove_unreferenced(old_path)
    try:
        from dqt import events
        events.dispatch("baseline.frozen",
                         {"name": name, "n_rows": int(len(df)),
                          "n_cols": int(len(df.columns)), "sha256": digest})
    except Exception:  # noqa: BLE001
        pass
    return {"name": name, "created_at": created_at, "n_rows": len(df), "n_cols": len(columns),
            "columns": columns, "sha256": digest, "description": description, "parquet": str(parquet_path)}


def list_baselines() -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT name, created_at, n_rows, n_cols, sha256, description, parquet "
            "FROM baselines ORDER BY name",
        ).fetchall()
    cols = ("name", "created_at", "n_rows", "n_cols", "sha256",
            "description", "parquet")
    return [dict(zip(cols, r)) for r in rows]


def get(name: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute(
            "SELECT name, created_at, n_rows, n_cols, columns, sha256, "
            "description, parquet FROM baselines WHERE name=?",
            (name,),
        ).fetchone()
    if row is None:
        return None
    cols = ("name", "created_at", "n_rows", "n_cols", "columns", "sha256",
            "description", "parquet")
    out = dict(zip(cols, row))
    out["columns"] = (out["columns"] or "").split(",") if out["columns"] else []
    return out


def load(name: str) -> pd.DataFrame:
    """Load the DataFrame for baseline ``name``. Raises if missing."""
    # Open the file inside the read transaction so a concurrent replacement
    # cannot unlink the selected snapshot before the reader has a descriptor.
    with _conn() as c:
        c.execute("BEGIN")
        row = c.execute("SELECT parquet, sha256 FROM baselines WHERE name=?", (name,)).fetchone()
        if row is None:
            raise KeyError(f"baseline {name!r} not found")
        handle = Path(row[0]).open("rb")
    with handle:
        if _digest(handle) != row[1]:
            raise ValueError(f"baseline {name!r} checksum mismatch")
        handle.seek(0)
        return pd.read_parquet(handle)


def delete(name: str) -> bool:
    with _conn() as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT parquet FROM baselines WHERE name=?", (name,)).fetchone()
        if row is None:
            return False
        c.execute("DELETE FROM baselines WHERE name=?", (name,))
        shared = c.execute("SELECT 1 FROM baselines WHERE parquet=?", (row[0],)).fetchone()
    if not shared:
        _remove_unreferenced(row[0])
    return True


def _remove_unreferenced(path):
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        logging.getLogger(__name__).exception("Could not remove retired baseline %s", path)


def _sha256(path: Path) -> str:
    with path.open("rb") as fh:
        return _digest(fh)


def _digest(fh) -> str:
    h = hashlib.sha256()
    for chunk in iter(lambda: fh.read(1 << 20), b""):
        h.update(chunk)
    return h.hexdigest()

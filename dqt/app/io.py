"""Upload parsing: base64 → DataFrame for CSV / Parquet."""
from __future__ import annotations

import base64
import io
import os

import pandas as pd

_DEFAULT_MAX_MB = 250


def max_bytes() -> int:
    """Upload size cap, honouring ``DQT_MAX_UPLOAD_MB``. Bounds: 1 MB .. 4 GB."""
    raw = os.environ.get("DQT_MAX_UPLOAD_MB")
    mb = _DEFAULT_MAX_MB
    if raw:
        try:
            mb = int(raw)
        except ValueError:
            mb = _DEFAULT_MAX_MB
    mb = max(1, min(mb, 4096))
    return mb * 1024 * 1024


# Back-compat: callers and tests sometimes import MAX_BYTES directly. The
# module-level value reflects the env at import time; callers that need a
# live value should call ``max_bytes()``.
MAX_BYTES = max_bytes()


class UploadTooLargeError(ValueError):
    """Raised when an upload exceeds the configured size cap."""


def parse_upload(contents: str, filename: str) -> pd.DataFrame:
    """Decode a dcc.Upload payload into a DataFrame. Raises ValueError on bad input."""
    if not contents:
        raise ValueError("Empty upload")
    header, b64 = contents.split(",", 1)
    raw = base64.b64decode(b64)
    cap = max_bytes()
    if len(raw) > cap:
        raise UploadTooLargeError(
            f"File too large ({len(raw)/1024/1024:.1f} MB > {cap/1024/1024:.0f} MB). "
            "Set DQT_MAX_UPLOAD_MB to raise the cap, or pre-aggregate the file."
        )

    name = (filename or "").lower()
    buf = io.BytesIO(raw)
    if name.endswith(".csv") or name.endswith(".tsv") or name.endswith(".txt"):
        sep = "\t" if name.endswith(".tsv") else None
        try:
            # engine='python' is required for sep=None auto-detection; it
            # rejects low_memory, hence the branching.
            if sep is None:
                return pd.read_csv(buf, sep=None, engine="python")
            return pd.read_csv(buf, sep=sep, low_memory=False)
        except Exception as e:
            raise ValueError(f"Failed to parse CSV: {e}") from e
    if name.endswith(".parquet") or name.endswith(".pq"):
        try:
            return pd.read_parquet(buf)
        except Exception as e:
            raise ValueError(f"Failed to parse Parquet: {e}") from e
    if name.endswith(".xlsx") or name.endswith(".xls"):
        raise ValueError("Excel not supported in v1; convert to CSV/Parquet")
    raise ValueError(f"Unsupported file extension: {filename}")


def column_summary(df: pd.DataFrame) -> list[dict]:
    """Per-column overview rows: name, dtype, nan share, n_unique, sample."""
    rows = []
    for c in df.columns:
        s = df[c]
        sample_vals = s.dropna().head(3).tolist()
        sample_str = ", ".join(str(v)[:30] for v in sample_vals)
        rows.append({
            "column": c,
            "dtype": str(s.dtype),
            "nan_share": f"{float(s.isna().mean()):.1%}",
            "n_unique": int(s.nunique(dropna=True)),
            "sample": sample_str[:80],
        })
    return rows

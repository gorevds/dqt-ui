"""dbt manifest reader: resolve a dbt model name to a fully qualified
warehouse relation so DQT can monitor it without hard-coding paths.

Usage from the CLI::

    dqt analyze --from-dbt /path/to/target/manifest.json \\
                --dbt-model my_model \\
                --sql-uri snowflake://... \\
                --time created_at --target default_flag --fail-on red

The manifest is read locally; only the resolved ``database.schema.alias``
is passed to the SQL connector — there is no network call to dbt itself.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional, Tuple

_log = logging.getLogger(__name__)


def resolve_model(manifest_path: Path, model_name: str) -> Tuple[str, str]:
    """Return ``(fully_qualified_relation, materialization)`` for ``model_name``.

    ``fully_qualified_relation`` is what you would put after ``FROM`` in
    a SELECT — quoted database/schema/alias joined by dots, in the order
    dbt itself uses (``"DB"."SCHEMA"."ALIAS"`` for Snowflake-like).

    ``materialization`` is the dbt materialization (``view`` / ``table`` /
    ``incremental`` / ``ephemeral`` / etc.). Callers may want to refuse
    monitoring of ``ephemeral`` relations because they have no warehouse
    address.
    """
    manifest = _load_manifest(manifest_path)
    candidates = []
    for _uid, node in (manifest.get("nodes") or {}).items():
        if node.get("resource_type") != "model":
            continue
        if node.get("name") != model_name and node.get("alias") != model_name:
            continue
        candidates.append((_uid, node))
    if not candidates:
        available = sorted({n.get("name") for n in (manifest.get("nodes") or {}).values()
                            if n.get("resource_type") == "model"})
        raise KeyError(
            f"dbt model {model_name!r} not found in manifest. "
            f"Known models: {', '.join(filter(None, available))[:200]}"
        )
    if len(candidates) > 1:
        names = [c[0] for c in candidates]
        raise ValueError(
            f"dbt model {model_name!r} is ambiguous; candidates: {names}"
        )
    _, node = candidates[0]
    materialization = (node.get("config") or {}).get("materialized") or "view"
    if materialization == "ephemeral":
        raise ValueError(
            f"dbt model {model_name!r} is materialized=ephemeral and has no "
            "warehouse relation; pick a different model or change materialization."
        )

    quote = '"'
    parts = [node.get("database"), node.get("schema"), node.get("alias") or node.get("name")]
    if not all(parts):
        raise ValueError(
            f"dbt model {model_name!r} is missing database/schema/alias in the "
            f"manifest. Got: db={parts[0]!r} schema={parts[1]!r} alias={parts[2]!r}"
        )
    relation = ".".join(f"{quote}{p}{quote}" for p in parts)
    return relation, materialization


def list_monitorable_models(manifest_path: Path, tag: str = "monitor") -> list:
    """Return all dbt model names tagged with ``tag``. Convention: tag a
    model in dbt with ``+meta: {monitor: true}`` or ``+tags: ["monitor"]``
    to opt it into automatic drift checks.
    """
    manifest = _load_manifest(manifest_path)
    out = []
    for node in (manifest.get("nodes") or {}).values():
        if node.get("resource_type") != "model":
            continue
        tags = set(node.get("tags") or [])
        meta = node.get("meta") or {}
        if tag in tags or bool(meta.get(tag)):
            out.append(node.get("name"))
    return sorted(filter(None, out))


def _load_manifest(manifest_path: Path) -> dict:
    if not manifest_path.exists():
        raise FileNotFoundError(f"dbt manifest not found at {manifest_path}")
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"dbt manifest at {manifest_path} is not valid JSON: {exc}") from exc


def cli_resolve(
    manifest_path: Optional[str], model_name: Optional[str],
) -> Optional[str]:
    """Convenience for ``dqt analyze`` — return a SELECT * statement against
    the resolved relation, or ``None`` if no manifest/model was passed.
    """
    if not manifest_path or not model_name:
        return None
    relation, _ = resolve_model(Path(manifest_path), model_name)
    return f"SELECT * FROM {relation}"

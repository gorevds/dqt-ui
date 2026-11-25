"""Tests for the dbt manifest reader."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dqt.integrations.dbt import (
    cli_resolve,
    list_monitorable_models,
    resolve_model,
)


def _write_manifest(path: Path, nodes: dict) -> None:
    path.write_text(json.dumps({"nodes": nodes}), encoding="utf-8")


def test_resolve_model_returns_qualified_relation(tmp_path):
    manifest = tmp_path / "manifest.json"
    _write_manifest(manifest, {
        "model.proj.my_model": {
            "resource_type": "model",
            "name": "my_model",
            "alias": "my_model",
            "database": "ANALYTICS",
            "schema": "PROD",
            "config": {"materialized": "table"},
            "tags": ["monitor"],
        },
    })
    relation, mat = resolve_model(manifest, "my_model")
    assert relation == '"ANALYTICS"."PROD"."my_model"'
    assert mat == "table"


def test_resolve_model_unknown_raises(tmp_path):
    manifest = tmp_path / "manifest.json"
    _write_manifest(manifest, {
        "model.proj.foo": {
            "resource_type": "model", "name": "foo", "alias": "foo",
            "database": "DB", "schema": "S", "config": {"materialized": "view"},
        },
    })
    with pytest.raises(KeyError, match="bar"):
        resolve_model(manifest, "bar")


def test_resolve_model_rejects_ephemeral(tmp_path):
    manifest = tmp_path / "manifest.json"
    _write_manifest(manifest, {
        "model.proj.eph": {
            "resource_type": "model", "name": "eph", "alias": "eph",
            "database": "DB", "schema": "S",
            "config": {"materialized": "ephemeral"},
        },
    })
    with pytest.raises(ValueError, match="ephemeral"):
        resolve_model(manifest, "eph")


def test_list_monitorable_models_picks_tag_or_meta(tmp_path):
    manifest = tmp_path / "manifest.json"
    _write_manifest(manifest, {
        "m.proj.tagged":   {"resource_type": "model", "name": "tagged",   "tags": ["monitor"]},
        "m.proj.meta_one": {"resource_type": "model", "name": "meta_one", "meta": {"monitor": True}},
        "m.proj.normal":   {"resource_type": "model", "name": "normal"},
        "src.proj.raw":    {"resource_type": "source", "name": "raw"},
    })
    monitorable = list_monitorable_models(manifest)
    assert monitorable == ["meta_one", "tagged"]


def test_cli_resolve_returns_select(tmp_path):
    manifest = tmp_path / "manifest.json"
    _write_manifest(manifest, {
        "model.proj.x": {
            "resource_type": "model", "name": "x", "alias": "x",
            "database": "D", "schema": "S",
            "config": {"materialized": "table"},
        },
    })
    sql = cli_resolve(str(manifest), "x")
    assert sql == 'SELECT * FROM "D"."S"."x"'


def test_cli_resolve_returns_none_when_unset(tmp_path):
    assert cli_resolve(None, None) is None
    assert cli_resolve(str(tmp_path), None) is None
    assert cli_resolve(None, "x") is None


def test_resolve_model_missing_manifest(tmp_path):
    with pytest.raises(FileNotFoundError):
        resolve_model(tmp_path / "nope.json", "x")


def test_resolve_model_invalid_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not valid json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        resolve_model(bad, "x")

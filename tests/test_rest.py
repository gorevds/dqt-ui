"""Tests for the REST API blueprint."""
from __future__ import annotations

import io

import pytest
from flask import Flask

from dqt.app.rest import register_api


@pytest.fixture
def client(monkeypatch, tmp_path):
    # Sandbox runs DB so the test isn't polluted by ~/.dqt/.
    monkeypatch.setenv("DQT_RUNS_DB", str(tmp_path / "runs.db"))
    app = Flask(__name__)
    register_api(app)
    return app.test_client()


def test_healthz(client):
    r = client.get("/api/v1/healthz")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "ok"
    assert "version" in body


def test_create_run_csv(client, binary_df):
    csv_bytes = binary_df.head(800).to_csv(index=False).encode()
    r = client.post(
        "/api/v1/runs",
        data={
            "file": (io.BytesIO(csv_bytes), "data.csv"),
            "time": "date",
            "target": "target",
        },
        content_type="multipart/form-data",
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert "run_id" in body
    assert "severity_counts" in body
    assert body["meta"]["target_col"] == "target"


def test_create_run_rejects_bad_extension(client):
    r = client.post(
        "/api/v1/runs",
        data={"file": (io.BytesIO(b"not data"), "data.xyz")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 400
    assert "unsupported" in r.get_json()["error"].lower()


def test_create_run_rejects_missing_file(client):
    r = client.post(
        "/api/v1/runs",
        data={"time": "date"},
        content_type="multipart/form-data",
    )
    assert r.status_code == 400


def test_list_and_get_run(client, binary_df):
    csv = binary_df.head(800).to_csv(index=False).encode()
    create = client.post(
        "/api/v1/runs",
        data={"file": (io.BytesIO(csv), "data.csv"), "time": "date", "target": "target"},
        content_type="multipart/form-data",
    )
    run_id = create.get_json()["run_id"]

    list_r = client.get("/api/v1/runs")
    assert list_r.status_code == 200
    runs = list_r.get_json()["runs"]
    assert any(r["id"] == run_id for r in runs)

    detail_r = client.get(f"/api/v1/runs/{run_id}")
    assert detail_r.status_code == 200
    detail = detail_r.get_json()
    assert detail["id"] == run_id


def test_get_run_404(client):
    r = client.get("/api/v1/runs/9999999")
    assert r.status_code == 404


def test_upload_size_cap(client, monkeypatch):
    monkeypatch.setenv("DQT_MAX_UPLOAD_MB", "1")
    big = b"x" * (2 * 1024 * 1024)
    r = client.post(
        "/api/v1/runs",
        data={"file": (io.BytesIO(big), "x.csv")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 413


def test_max_content_length_set_on_app(monkeypatch, tmp_path):
    """Werkzeug must enforce the cap at the request-parse layer so a
    malicious upload can't OOM the worker before our handler runs.
    """
    monkeypatch.setenv("DQT_RUNS_DB", str(tmp_path / "runs.db"))
    monkeypatch.setenv("DQT_MAX_UPLOAD_MB", "5")
    app = Flask(__name__)
    register_api(app)
    assert app.config["MAX_CONTENT_LENGTH"] == 5 * 1024 * 1024


def test_filename_path_traversal_sanitised(client, binary_df):
    """Even if the client sends ``../../etc/passwd.csv``, the source
    label stored in the runs DB must be the cleaned filename only.
    """
    from dqt.runs import get as runs_get

    csv = binary_df.head(800).to_csv(index=False).encode()
    r = client.post(
        "/api/v1/runs",
        data={"file": (io.BytesIO(csv), "../../etc/passwd.csv"),
              "time": "date", "target": "target"},
        content_type="multipart/form-data",
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    run_id = r.get_json()["run_id"]
    record = runs_get(run_id)
    assert record is not None
    assert ".." not in (record.get("source") or "")
    assert "/" not in (record.get("source") or "")

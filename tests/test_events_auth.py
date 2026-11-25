"""Tests for events module + auth opt-in plumbing."""
from __future__ import annotations

import pytest


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    monkeypatch.setenv("DQT_RUNS_DB", str(tmp_path / "runs.db"))
    monkeypatch.setenv("DQT_AUDIT_LOG", str(tmp_path / "audit.log"))
    yield tmp_path


def test_event_subscribe_dispatch(sandbox, monkeypatch):
    from dqt import events

    posted = []

    class _Resp:
        status = 200

        def __enter__(self): return self

        def __exit__(self, *a): return False

    def _fake_open(req, timeout=8.0):
        posted.append({"url": req.full_url,
                        "body": req.data,
                        "header": req.headers.get("X-dqt-event")})
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", _fake_open)

    events.subscribe("https://example.test/hook", workspace="risk")
    sent = events.dispatch("run.created", {"run_id": 7},
                            workspace="risk", threaded=False)
    assert sent == 1
    assert posted[0]["url"] == "https://example.test/hook"
    assert b'"run_id": 7' in posted[0]["body"]


def test_event_pattern_matching(sandbox, monkeypatch):
    from dqt import events

    sent_urls = []

    class _Resp:
        status = 200

        def __enter__(self): return self

        def __exit__(self, *a): return False

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=8.0: sent_urls.append(req.full_url) or _Resp(),
    )

    events.subscribe("https://run.test/hook",
                      workspace="ws", pattern="run.*")
    events.subscribe("https://all.test/hook",
                      workspace="ws", pattern="*")
    events.subscribe("https://other.test/hook",
                      workspace="ws", pattern="severity.changed")

    events.dispatch("run.created", {"id": 1}, workspace="ws", threaded=False)
    assert "https://run.test/hook" in sent_urls
    assert "https://all.test/hook" in sent_urls
    assert "https://other.test/hook" not in sent_urls


def test_event_unsubscribe(sandbox, monkeypatch):
    from dqt import events

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("should not fire")),
    )
    sub = events.subscribe("https://gone.test", workspace="x")
    assert events.unsubscribe(sub["id"]) is True
    sent = events.dispatch("run.created", {}, workspace="x", threaded=False)
    assert sent == 0


def test_event_swallows_failures(sandbox, monkeypatch):
    from dqt import events

    def _bad(req, timeout=8.0):
        import urllib.error
        raise urllib.error.URLError("dns")

    monkeypatch.setattr("urllib.request.urlopen", _bad)
    events.subscribe("https://broken.test", workspace="x")
    # Must not raise — best-effort delivery.
    sent = events.dispatch("run.created", {}, workspace="x", threaded=False)
    assert sent == 1


def test_auth_inactive_by_default(monkeypatch):
    from dqt import auth

    monkeypatch.delenv("DQT_AUTH", raising=False)
    assert auth.is_active() is False


def test_auth_active_with_env(monkeypatch):
    from dqt import auth

    monkeypatch.setenv("DQT_AUTH", "oidc")
    assert auth.is_active() is True


def test_oidc_factory_fails_closed(monkeypatch):
    from dqt.app.main import create_app

    monkeypatch.setenv("DQT_AUTH", "oidc")
    monkeypatch.delenv("DQT_AUTH_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="DQT_AUTH_SECRET_KEY"):
        create_app()


def test_oidc_factory_protects_application(monkeypatch):
    from dqt.app.main import create_app

    for key in ("DQT_OIDC_CLIENT_ID", "DQT_OIDC_CLIENT_SECRET", "DQT_AUTH_SECRET_KEY"):
        monkeypatch.setenv(key, "test")
    monkeypatch.setenv("DQT_AUTH", "oidc")
    monkeypatch.setenv("DQT_OIDC_ISSUER", "https://example.test")
    client = create_app().server.test_client()
    assert client.get("/").location.endswith("/auth/login")
    assert client.get("/api/v1/runs").status_code == 401
    assert client.post("/_dash-update-component").status_code == 401
    assert client.get("/api/v1/healthz").status_code == 200


def test_runs_save_emits_run_created(sandbox, monkeypatch, binary_df):
    """C5 fix: every saved run must dispatch run.created to subscribers."""
    from dqt import analyze, events

    fired = []

    class _Resp:
        status = 200

        def __enter__(self): return self

        def __exit__(self, *a): return False

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=8.0: fired.append(req.full_url) or _Resp(),
    )
    events.subscribe("https://hooks.test/run", workspace="risk", pattern="run.*")

    from dqt.runs import save as runs_save
    report = analyze(binary_df.head(800), time_col="date", target_col="target")
    runs_save(report, source="x.csv", workspace="risk")

    # Threaded dispatch — give it a moment to run.
    import time
    time.sleep(0.3)
    assert "https://hooks.test/run" in fired


def test_baseline_freeze_emits_event(sandbox, monkeypatch):
    import pandas as pd

    from dqt import baselines, events

    fired = []
    class _Resp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=8.0: fired.append(req.full_url) or _Resp(),
    )
    events.subscribe("https://hooks.test/baseline", workspace="default",
                      pattern="baseline.*")

    baselines.freeze("v1", pd.DataFrame({"x": [1, 2, 3]}))

    import time
    time.sleep(0.3)
    assert "https://hooks.test/baseline" in fired


def test_rbac_enforced_in_rest(sandbox, monkeypatch):
    """C4 fix: REST POST /runs must 403 when RBAC denies the action."""
    import io

    from flask import Flask

    from dqt.app.rest import register_api

    monkeypatch.setenv("DQT_AUTH", "oidc")  # turn RBAC on
    app = Flask(__name__)
    app.secret_key = "test"
    register_api(app)
    client = app.test_client()

    # No session user → analyze permission denied.
    csv = b"date,target\n2026-01-01,0\n"
    r = client.post(
        "/api/v1/runs",
        data={"file": (io.BytesIO(csv), "x.csv")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 403
    assert r.get_json()["permission"] == "analyze"


def test_rbac_open_mode_allows_unauthenticated(sandbox, monkeypatch, binary_df):
    """When DQT_AUTH is unset, REST stays open — back-compat for v1.0/v1.1
    deployments that haven't enabled auth yet.
    """
    import io

    from flask import Flask

    from dqt.app.rest import register_api

    monkeypatch.delenv("DQT_AUTH", raising=False)
    app = Flask(__name__)
    register_api(app)
    client = app.test_client()

    csv = binary_df.head(400).to_csv(index=False).encode()
    r = client.post(
        "/api/v1/runs",
        data={"file": (io.BytesIO(csv), "x.csv"),
              "time": "date", "target": "target"},
        content_type="multipart/form-data",
    )
    assert r.status_code == 200


def test_workspace_isolation_from_create_to_share(sandbox, monkeypatch, binary_df):
    import io

    from flask import Flask

    from dqt import rbac, runs, workspaces
    from dqt.app.rest import register_api
    from dqt.app.runs_page import run_detail

    monkeypatch.setenv("DQT_AUTH", "oidc")
    server = Flask(__name__)
    server.secret_key = "test"
    register_api(server)
    client = server.test_client()
    ids = {}
    for ws in ("risk", "sales"):
        workspaces.create(ws)
        email = f"{ws}@example.test"
        rbac.grant(email, workspace=ws, role="owner")
        with client.session_transaction() as session:
            session["user"] = {"email": email, "sub": ws}
        csv = binary_df.head(200).to_csv(index=False).encode()
        res = client.post("/api/v1/runs", data={"workspace": ws, "time": "date", "target": "target",
                                                "file": (io.BytesIO(csv), "data.csv")})
        assert res.status_code == 200
        ids[ws] = res.json["run_id"]
        assert runs.get(ids[ws])["workspace"] == ws
    own, other = ids["sales"], ids["risk"]
    assert [r["id"] for r in client.get("/api/v1/runs?workspace=sales").json["runs"]] == [own]
    assert client.get("/api/v1/runs?workspace=risk").status_code == 403
    assert client.get(f"/api/v1/runs/{other}").status_code == 404
    assert client.get(f"/api/v1/runs/{other}/feature/x_num").status_code == 404
    assert client.get(f"/api/v1/runs/{own}/diff/{other}").status_code == 404
    assert client.post(f"/api/v1/runs/{other}/share?workspace=sales").status_code == 404
    token = client.post(f"/api/v1/runs/{own}/share").json["token"]
    assert server.test_client().get(f"/api/v1/share/{token}").json["id"] == own
    assert client.get(f"/api/v1/runs/{own}/feature/x_num").status_code == 200
    with server.test_request_context():
        from flask import session
        session["user"] = {"email": "sales@example.test", "sub": "sales"}
        assert run_detail(str(other)).children == "Run not found"


def test_oidc_callback_verifies_signed_identity(monkeypatch, sandbox):
    import time
    from urllib.parse import parse_qs, urlparse

    from joserfc import jwt
    from joserfc.jwk import RSAKey

    from dqt.app.main import create_app

    issuer = "https://issuer.example.test"
    for key, value in {"DQT_AUTH": "oidc", "DQT_OIDC_ISSUER": issuer,
                       "DQT_OIDC_CLIENT_ID": "dqt", "DQT_OIDC_CLIENT_SECRET": "secret",
                       "DQT_AUTH_SECRET_KEY": "local-test", "DQT_AUTH_ALLOWED_DOMAINS": "example.test"}.items():
        monkeypatch.setenv(key, value)
    app = create_app().server
    provider = app.extensions["authlib.integrations.flask_client"].create_client("dqt_oidc")
    key = RSAKey.generate_key(2048)
    metadata = {"issuer": issuer, "authorization_endpoint": issuer + "/authorize",
                "token_endpoint": issuer + "/token", "id_token_signing_alg_values_supported": ["RS256"],
                "jwks": {"keys": [key.as_dict(private=False)]}}
    monkeypatch.setattr(provider, "load_server_metadata", lambda: metadata)
    client = app.test_client()
    response = client.get("/auth/login", base_url="https://localhost")
    params = parse_qs(urlparse(response.location).query)
    now = int(time.time())
    claims = {"iss": issuer, "aud": "dqt", "sub": "123", "nonce": params["nonce"][0],
              "iat": now, "exp": now + 120, "email": "risk@example.test", "email_verified": True}
    token = jwt.encode({"alg": "RS256"}, claims, key)
    monkeypatch.setattr(provider, "fetch_access_token", lambda **kw: {"id_token": token, "access_token": "test"})
    response = client.get("/auth/callback", base_url="https://localhost",
                          query_string={"code": "test", "state": params["state"][0]})
    assert response.status_code == 302 and response.location == "/"
    with client.session_transaction() as session:
        assert session["user"]["email"] == "risk@example.test"


def test_private_analysis_permissions_and_session_ownership(monkeypatch, sandbox):
    from flask import Flask, session
    from werkzeug.exceptions import Forbidden

    from dqt import auth, rbac
    from dqt.app.store import SessionStore

    monkeypatch.setenv("DQT_AUTH", "oidc")
    store = SessionStore(start_sweeper=False)
    server = Flask(__name__)
    server.secret_key = "test"
    rbac.grant("analyst@example.test", workspace="risk", role="analyst")
    rbac.grant("viewer@example.test", workspace="risk", role="viewer")

    with server.test_request_context():
        session["user"] = {"sub": "analyst", "email": "analyst@example.test"}
        assert auth.analysis_workspace() == "risk"
        first = store.create()
        session["user"] = {"sub": "viewer", "email": "viewer@example.test"}
        with pytest.raises(Forbidden):
            auth.require_analysis(lambda: None)()
        assert store.get(first.sid) is None
        assert store.reset(first.sid).sid != first.sid
        session["user"] = {"sub": "analyst", "email": "analyst@example.test"}
        assert store.get(first.sid) is first

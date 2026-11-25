"""Optional OpenID Connect sign-in for the Dash application and REST API."""
from __future__ import annotations

import os
from typing import Any, Optional

from flask import abort, redirect, request, session, url_for


def is_active() -> bool:
    return os.environ.get("DQT_AUTH", "").strip().lower() == "oidc"


def permitted(permission: str, workspace: str) -> bool:
    from dqt.rbac import check

    return check((session.get("user") or {}).get("email"), permission, workspace=workspace)


def analysis_workspace() -> Optional[str]:
    from dqt.rbac import workspaces_for
    if not is_active():
        return "default"
    allowed = workspaces_for(session["user"]["email"], "analyze")
    return allowed[0] if allowed else None


def require_analysis(fn):
    from functools import wraps

    @wraps(fn)
    def checked(*args, **kwargs):
        if analysis_workspace() is None:
            abort(403)
        return fn(*args, **kwargs)
    return checked


def register(flask_app: Any) -> None:
    if not os.environ.get("DQT_AUTH", "").strip():
        return
    if not is_active():
        raise RuntimeError("Unsupported DQT_AUTH mode")

    from authlib.integrations.base_client import OAuthError
    from authlib.integrations.flask_client import OAuth
    from joserfc.errors import JoseError

    required = ("DQT_AUTH_SECRET_KEY", "DQT_OIDC_ISSUER", "DQT_OIDC_CLIENT_ID",
                "DQT_OIDC_CLIENT_SECRET")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError("Missing OIDC configuration: " + ", ".join(missing))
    issuer = os.environ["DQT_OIDC_ISSUER"]
    if not issuer.startswith("https://"):
        raise RuntimeError("DQT_OIDC_ISSUER must use HTTPS")
    flask_app.secret_key = os.environ["DQT_AUTH_SECRET_KEY"]
    flask_app.config.update(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_HTTPONLY=True,
                            SESSION_COOKIE_SAMESITE="Lax")
    provider = OAuth(flask_app).register(
        name="dqt_oidc", client_id=os.environ["DQT_OIDC_CLIENT_ID"],
        client_secret=os.environ["DQT_OIDC_CLIENT_SECRET"],
        server_metadata_url=issuer.rstrip("/") + "/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    domains = {s.strip().lower() for s in os.getenv("DQT_AUTH_ALLOWED_DOMAINS", "").split(",") if s.strip()}

    @flask_app.get("/auth/login")
    def oidc_login():
        return provider.authorize_redirect(url_for("oidc_callback", _external=True, _scheme="https"))

    @flask_app.get("/auth/callback")
    def oidc_callback():
        try:
            token = provider.authorize_access_token(claims_options={"iss": {"essential": True, "value": issuer}})
        except (OAuthError, JoseError, ValueError):
            abort(403)
        claims = token.get("userinfo") or {}
        email = str(claims.get("email") or "").strip().lower()
        if (not token.get("id_token") or claims.get("iss") != issuer or not claims.get("sub")
                or claims.get("email_verified") is not True or "@" not in email
                or (domains and email.rsplit("@", 1)[1] not in domains)):
            abort(403)
        session.clear()
        session["user"] = {"email": email, "sub": claims["sub"]}
        from dqt import audit
        audit.record("auth.login", {"email": email})
        return redirect("/")

    @flask_app.get("/auth/logout")
    def oidc_logout():
        from dqt import audit
        audit.record("auth.logout", {"email": (session.get("user") or {}).get("email")})
        session.clear()
        return redirect("/")

    @flask_app.before_request
    def require_login():
        if request.endpoint in {"oidc_login", "oidc_callback", "oidc_logout",
                                 "dqt_api_v1._healthz", "dqt_api_v1._share_view"}:
            return None
        if not session.get("user"):
            if request.path.startswith(("/api/", "/_dash-")):
                abort(401)
            return redirect(url_for("oidc_login"))
        return None


def current_user(session_obj: Optional[dict]) -> Optional[dict]:
    return (session_obj or {}).get("user")

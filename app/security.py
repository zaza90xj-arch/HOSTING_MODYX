"""CSRF, rate limiting, auth decorators, audit log, security headers."""
import hmac
import secrets
import time
from functools import wraps

from flask import abort, current_app, g, redirect, request, session, url_for

from .db import execute, now, query


# ---- CSRF ---------------------------------------------------------------
def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def check_csrf():
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
    expected = session.get("_csrf", "")
    if not expected or not hmac.compare_digest(sent, expected):
        abort(403)


# ---- Rate limiting (stored in the database so it works across workers) ----
def rate_ok(key, limit, window_seconds):
    ts = int(time.time())
    execute("DELETE FROM rate_limits WHERE ts < ?", (ts - 86400,))
    n = query("SELECT COUNT(*) AS c FROM rate_limits WHERE key=? AND ts>?", (key, ts - window_seconds), one=True)["c"]
    if n >= limit:
        return False
    execute("INSERT INTO rate_limits (key, ts) VALUES (?, ?)", (key, ts))
    return True


def rate_reset(key):
    execute("DELETE FROM rate_limits WHERE key=?", (key,))


# ---- Auth ------------------------------------------------------------------
def login_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
        return view(*a, **kw)
    return wrapped


def role_required(*roles):
    def deco(view):
        @wraps(view)
        def wrapped(*a, **kw):
            if g.user is None:
                return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
            if g.user["role"] not in roles:
                abort(403)
            return view(*a, **kw)
        return wrapped
    return deco


def audit(action, target=None, user_id=None):
    uid = user_id if user_id is not None else (g.user["id"] if getattr(g, "user", None) else None)
    execute(
        "INSERT INTO audit_log (user_id, action, target, ip, created_at) VALUES (?,?,?,?,?)",
        (uid, action, target, request.remote_addr, now()),
    )


def safe_next(url):
    if url and url.startswith("/") and not url.startswith("//") and "\\" not in url:
        return url
    return None


# ---- Headers ---------------------------------------------------------------
def add_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; img-src 'self' data:; script-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    if current_app.config["SESSION_COOKIE_SECURE"]:
        resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.endpoint and request.endpoint != "static":
        resp.headers["Cache-Control"] = "no-store"
    return resp

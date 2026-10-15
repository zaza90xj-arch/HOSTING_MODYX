import hashlib
import re
import secrets

from flask import (Blueprint, current_app, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from . import i18n
from .db import execute, iso_in, now, query
from .mailer import send_mail
from .security import audit, login_required, rate_ok, rate_reset, safe_next

bp = Blueprint("auth", __name__)
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
_DUMMY_HASH = generate_password_hash("not-a-real-password")


def T(key, **kw):
    return i18n.t(key, i18n.current_lang(), **kw)


def _h(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def issue_token(user_id, kind, hours):
    raw = secrets.token_urlsafe(32)
    execute("UPDATE tokens SET used_at=? WHERE user_id=? AND kind=? AND used_at IS NULL", (now(), user_id, kind))
    execute("INSERT INTO tokens (user_id, kind, token_hash, expires_at, created_at) VALUES (?,?,?,?,?)",
            (user_id, kind, _h(raw), iso_in(hours=hours), now()))
    return raw


def peek_token(raw, kind):
    row = query("SELECT * FROM tokens WHERE token_hash=? AND kind=? AND used_at IS NULL", (_h(raw), kind), one=True)
    return row if row and row["expires_at"] >= now() else None


def consume_token(raw, kind):
    row = peek_token(raw, kind)
    if row:
        execute("UPDATE tokens SET used_at=? WHERE id=?", (now(), row["id"]))
    return row


def base_url():
    return current_app.config["BASE_URL"] or request.url_root.rstrip("/")


def send_verification(user):
    raw = issue_token(user["id"], "verify", 48)
    link = f"{base_url()}{url_for('auth.verify', token=raw)}"
    return send_mail(current_app._get_current_object(), user["email"], T("mail_verify_subject"),
                     T("mail_verify_body", name=user["name"], link=link))


def start_session(user):
    session.clear()
    session["uid"] = user["id"]
    session.permanent = True
    execute("UPDATE users SET last_login_at=? WHERE id=?", (now(), user["id"]))


@bp.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("main.dashboard"))
    first = query("SELECT COUNT(*) c FROM users", one=True)["c"] == 0
    if not first and not current_app.config["ALLOW_REGISTRATION"]:
        flash(T("err_registration_closed"), "err")
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        pw = request.form.get("password", "")
        pw2 = request.form.get("password2", "")
        error = None
        if not rate_ok(f"reg:{request.remote_addr}", 10, 3600):
            error = "err_rate"
        elif not (2 <= len(name) <= 60):
            error = "err_name"
        elif not EMAIL_RE.match(email) or len(email) > 254:
            error = "err_email"
        elif len(pw) < 8 or len(pw) > 128:
            error = "err_password_len"
        elif pw != pw2:
            error = "err_password_match"
        elif query("SELECT 1 FROM users WHERE email=?", (email,), one=True):
            error = "err_email_taken"
        if error:
            flash(T(error), "err")
            return render_template("auth/register.html", form=request.form), 400
        role = "admin" if (first or email in current_app.config["ADMIN_EMAILS"]) else "user"
        plan = "owner" if role == "admin" else "free"
        uid = execute(
            "INSERT INTO users (email, name, password_hash, role, plan_id, lang, created_at) VALUES (?,?,?,?,?,?,?)",
            (email, name, generate_password_hash(pw), role, plan, i18n.current_lang(), now()))
        user = query("SELECT * FROM users WHERE id=?", (uid,), one=True)
        start_session(user)
        g.user = user
        audit("auth.register", email)
        sent = send_verification(user)
        if current_app.config["MAIL_MODE"] == "console":
            flash(T("msg_mail_not_configured"), "warn")
        elif not sent:
            flash(T("err_mail_failed"), "err")
        else:
            flash(T("msg_verify_sent"), "ok")
        return redirect(url_for("main.dashboard"))
    return render_template("auth/register.html", form={})


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("main.dashboard"))
    nxt = safe_next(request.values.get("next"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        pw = request.form.get("password", "")
        key = f"login:{email}:{request.remote_addr}"
        if not rate_ok(key, 8, 900):
            flash(T("err_rate"), "err")
            return render_template("auth/login.html", next=nxt), 429
        user = query("SELECT * FROM users WHERE email=? AND is_active=1", (email,), one=True)
        ok = check_password_hash(user["password_hash"] if user else _DUMMY_HASH, pw)
        if not (user and ok):
            flash(T("err_login"), "err")
            return render_template("auth/login.html", next=nxt), 401
        rate_reset(key)
        start_session(user)
        g.user = user
        audit("auth.login")
        return redirect(nxt or url_for("main.dashboard"))
    return render_template("auth/login.html", next=nxt)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    audit("auth.logout")
    session.clear()
    return redirect(url_for("main.index"))


@bp.route("/verify/<token>")
def verify(token):
    row = consume_token(token, "verify")
    if not row:
        flash(T("err_token"), "err")
        return redirect(url_for("main.index"))
    execute("UPDATE users SET email_verified=1 WHERE id=?", (row["user_id"],))
    audit("auth.verify_email", user_id=row["user_id"])
    flash(T("msg_verified"), "ok")
    return redirect(url_for("main.dashboard") if g.user else url_for("auth.login"))


@bp.route("/resend-verification", methods=["POST"])
@login_required
def resend_verification():
    if g.user["email_verified"]:
        return redirect(url_for("main.dashboard"))
    if not rate_ok(f"resend:{g.user['id']}", 3, 3600):
        flash(T("err_rate"), "err")
    elif send_verification(g.user):
        flash(T("msg_verify_sent") if current_app.config["MAIL_MODE"] != "console" else T("msg_mail_not_configured"), "ok")
    else:
        flash(T("err_mail_failed"), "err")
    return redirect(request.referrer and safe_next(request.referrer.replace(request.host_url.rstrip("/"), "")) or url_for("main.dashboard"))


@bp.route("/forgot", methods=["GET", "POST"])
def forgot():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if rate_ok(f"forgot:{request.remote_addr}", 5, 3600):
            user = query("SELECT * FROM users WHERE email=? AND is_active=1", (email,), one=True)
            if user:
                raw = issue_token(user["id"], "reset", 1)
                link = f"{base_url()}{url_for('auth.reset', token=raw)}"
                send_mail(current_app._get_current_object(), user["email"], T("mail_reset_subject"),
                          T("mail_reset_body", name=user["name"], link=link))
                audit("auth.reset_requested", user_id=user["id"])
        # Same answer whether or not the account exists (no account enumeration).
        flash(T("msg_reset_sent"), "ok")
        return redirect(url_for("auth.login"))
    return render_template("auth/forgot.html")


@bp.route("/reset/<token>", methods=["GET", "POST"])
def reset(token):
    if not peek_token(token, "reset"):
        flash(T("err_token"), "err")
        return redirect(url_for("auth.forgot"))
    if request.method == "POST":
        pw, pw2 = request.form.get("password", ""), request.form.get("password2", "")
        if len(pw) < 8 or len(pw) > 128:
            flash(T("err_password_len"), "err")
        elif pw != pw2:
            flash(T("err_password_match"), "err")
        else:
            row = consume_token(token, "reset")
            if row:
                execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(pw), row["user_id"]))
                audit("auth.password_reset", user_id=row["user_id"])
                session.clear()
                flash(T("msg_password_changed"), "ok")
                return redirect(url_for("auth.login"))
        return render_template("auth/reset.html", token=token), 400
    return render_template("auth/reset.html", token=token)

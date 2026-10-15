import os
import re
import shutil
import sqlite3
import time

from flask import (Blueprint, abort, current_app, flash, g, jsonify, make_response,
                   redirect, render_template, request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from . import i18n, server, storage
from .db import execute, now, query
from .security import audit, login_required, role_required

bp = Blueprint("main", __name__)
RUNTIMES = ("static", "node", "python", "php", "docker")
# Suggested defaults only. They are stored, and executed in an isolated container from Phase 5.
DEFAULT_CMDS = {
    "static": ("", ""),
    "node": ("npm install", "node index.js"),
    "python": ("pip install -r requirements.txt", "python app.py"),
    "php": ("composer install", "php -S 0.0.0.0:8000"),
    "docker": ("docker build -t app .", "docker run app"),
}


def T(key, **kw):
    return i18n.t(key, i18n.current_lang(), **kw)


def get_plan():
    return query("SELECT * FROM plans WHERE id=?", (g.user["plan_id"],), one=True)


def own_project(pid):
    row = query("SELECT * FROM projects WHERE id=? AND owner_id=?", (pid, g.user["id"]), one=True)
    if row is None:
        abort(404)  # 404 (not 403) so other people's project ids are not revealed
    return row


def get_setting(key, default=""):
    row = query("SELECT value FROM server_settings WHERE key=?", (key,), one=True)
    return row["value"] if row else default


def set_setting(key, value):
    execute("INSERT INTO server_settings (key, value, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at", (key, value, now()))


# ---- public ------------------------------------------------------------------
@bp.route("/")
def index():
    return render_template("landing.html")


@bp.route("/lang/<code>")
def set_lang(code):
    if code not in i18n.LANGS:
        abort(404)
    if g.user:
        execute("UPDATE users SET lang=? WHERE id=?", (code, g.user["id"]))
    session["lang"] = code
    target = request.args.get("next", "")
    if not (target.startswith("/") and not target.startswith("//") and "\\" not in target):
        target = url_for("main.index")
    resp = make_response(redirect(target))
    resp.set_cookie("lang", code, max_age=31536000, samesite="Lax")
    return resp


@bp.route("/healthz")
def healthz():
    try:
        query("SELECT 1")
        return jsonify(status="ok")
    except sqlite3.Error:
        return jsonify(status="error"), 503


@bp.route("/status")
def status():
    checks = []
    try:
        t0 = time.perf_counter()
        query("SELECT 1")
        checks.append(("status_db", True, f"{(time.perf_counter() - t0) * 1000:.1f} ms"))
    except sqlite3.Error:
        checks.append(("status_db", False, ""))
    try:
        probe = storage.root() / ".probe"
        probe.write_text("ok")
        probe.unlink()
        checks.append(("status_storage", True, ""))
    except OSError:
        checks.append(("status_storage", False, ""))
    checks.append(("status_mail", current_app.config["MAIL_MODE"] == "smtp",
                   "SMTP" if current_app.config["MAIL_MODE"] == "smtp" else T("status_mail_off")))
    return render_template("status.html", checks=checks)


# ---- dashboard -----------------------------------------------------------------
@bp.route("/dashboard")
@login_required
def dashboard():
    plan = get_plan()
    n_projects = query("SELECT COUNT(*) c FROM projects WHERE owner_id=?", (g.user["id"],), one=True)["c"]
    used = storage.dir_size(storage.user_dir(g.user["id"]))
    activity = query("SELECT action, target, created_at FROM audit_log WHERE user_id=? ORDER BY id DESC LIMIT 8", (g.user["id"],))
    recent = query("SELECT id, name, runtime, status FROM projects WHERE owner_id=? ORDER BY id DESC LIMIT 5", (g.user["id"],))
    admin = g.user["role"] == "admin"
    events = query("SELECT level, message, created_at FROM events ORDER BY id DESC LIMIT 5") if admin else []
    return render_template("dashboard.html", plan=plan, n_projects=n_projects, used=used, activity=activity,
                           recent=recent, live=admin, events=events, env_type=get_setting("env_type", "") if admin else "")


# ---- projects ------------------------------------------------------------------
@bp.route("/projects")
@login_required
def projects():
    rows = query("SELECT * FROM projects WHERE owner_id=? ORDER BY id DESC", (g.user["id"],))
    return render_template("projects.html", rows=rows, plan=get_plan())


def make_slug(name):
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:30] or "project"
    slug, i = base, 1
    while query("SELECT 1 FROM projects WHERE slug=?", (slug,), one=True):
        i += 1
        slug = f"{base}-{i}"
    return slug


def read_project_form():
    f = request.form
    data = {"name": f.get("name", "").strip(), "description": f.get("description", "").strip(),
            "runtime": f.get("runtime", ""), "build_command": f.get("build_command", "").strip(),
            "start_command": f.get("start_command", "").strip()}
    if not 2 <= len(data["name"]) <= 60:
        return data, "err_project_name"
    if len(data["description"]) > 300:
        return data, "err_project_desc"
    if data["runtime"] not in RUNTIMES:
        return data, "err_runtime"
    for k in ("build_command", "start_command"):
        if len(data[k]) > 200 or "\n" in data[k] or "\r" in data[k]:
            return data, "err_command"
    return data, None


@bp.route("/projects/new", methods=["GET", "POST"])
@login_required
def project_new():
    plan = get_plan()
    count = query("SELECT COUNT(*) c FROM projects WHERE owner_id=?", (g.user["id"],), one=True)["c"]
    blocked = None
    if current_app.config["REQUIRE_VERIFIED"] and not g.user["email_verified"]:
        blocked = "err_verify_first"
    elif count >= plan["max_projects"]:
        blocked = "err_project_limit"
    if request.method == "POST":
        if blocked:
            flash(T(blocked, limit=plan["max_projects"]), "err")
            return render_template("project_new.html", form=request.form, blocked=blocked, plan=plan, defaults=DEFAULT_CMDS), 403
        data, error = read_project_form()
        if error:
            flash(T(error), "err")
            return render_template("project_new.html", form=request.form, blocked=None, plan=plan, defaults=DEFAULT_CMDS), 400
        try:
            pid = execute(
                "INSERT INTO projects (owner_id, slug, name, description, runtime, build_command, start_command, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (g.user["id"], make_slug(data["name"]), data["name"], data["description"], data["runtime"],
                 data["build_command"], data["start_command"], now(), now()))
        except sqlite3.IntegrityError:
            flash(T("err_try_again"), "err")
            return redirect(url_for("main.project_new"))
        storage.ensure_project_dir(g.user["id"], pid)
        audit("project.create", data["name"])
        flash(T("msg_project_created"), "ok")
        return redirect(url_for("main.project", pid=pid))
    return render_template("project_new.html", form={}, blocked=blocked, plan=plan, defaults=DEFAULT_CMDS)


@bp.route("/projects/<int:pid>")
@login_required
def project(pid):
    p = own_project(pid)
    size = storage.dir_size(storage.project_dir(g.user["id"], pid))
    return render_template("project.html", p=p, size=size, plan=get_plan(), defaults=DEFAULT_CMDS)


@bp.route("/projects/<int:pid>/edit", methods=["POST"])
@login_required
def project_edit(pid):
    own_project(pid)
    data, error = read_project_form()
    if error:
        flash(T(error), "err")
        return redirect(url_for("main.project", pid=pid))
    execute("UPDATE projects SET name=?, description=?, runtime=?, build_command=?, start_command=?, updated_at=? WHERE id=? AND owner_id=?",
            (data["name"], data["description"], data["runtime"], data["build_command"], data["start_command"], now(), pid, g.user["id"]))
    audit("project.update", data["name"])
    flash(T("msg_saved"), "ok")
    return redirect(url_for("main.project", pid=pid))


@bp.route("/projects/<int:pid>/delete", methods=["POST"])
@login_required
def project_delete(pid):
    p = own_project(pid)
    if request.form.get("confirm", "").strip() != p["slug"]:
        flash(T("err_confirm_slug"), "err")
        return redirect(url_for("main.project", pid=pid))
    storage.remove_project_dir(g.user["id"], pid)
    execute("DELETE FROM projects WHERE id=? AND owner_id=?", (pid, g.user["id"]))
    audit("project.delete", p["name"])
    flash(T("msg_project_deleted"), "ok")
    return redirect(url_for("main.projects"))


# ---- settings / plans / not-yet-built -----------------------------------------------
@bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        form = request.form.get("form")
        if form == "profile":
            name, lang = request.form.get("name", "").strip(), request.form.get("lang", "")
            if not 2 <= len(name) <= 60 or lang not in i18n.LANGS:
                flash(T("err_name"), "err")
            else:
                execute("UPDATE users SET name=?, lang=? WHERE id=?", (name, lang, g.user["id"]))
                audit("settings.profile")
                flash(T("msg_saved"), "ok")
        elif form == "password":
            cur, new, new2 = (request.form.get(k, "") for k in ("current", "password", "password2"))
            if not check_password_hash(g.user["password_hash"], cur):
                flash(T("err_current_password"), "err")
            elif not 8 <= len(new) <= 128:
                flash(T("err_password_len"), "err")
            elif new != new2:
                flash(T("err_password_match"), "err")
            else:
                execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new), g.user["id"]))
                audit("settings.password")
                flash(T("msg_password_changed"), "ok")
        return redirect(url_for("main.settings"))
    return render_template("settings.html")


@bp.route("/plans")
@login_required
def plans():
    return render_template("plans.html", plans=query("SELECT * FROM plans ORDER BY sort"))


@bp.route("/soon/<feature>")
@login_required
def soon(feature):
    phase = i18n.SOON_PHASE.get(feature)
    if not phase:
        abort(404)
    return render_template("soon.html", feature=feature, phase=phase)


# ---- server connection (owner only) -----------------------------------------------
@bp.route("/server")
@role_required("admin")
def server_page():
    info = server.detect(storage.root())
    return render_template("server.html", info=info, label=get_setting("label"), env_type=get_setting("env_type"),
                           provider=get_setting("provider"), confirmed_at=get_setting("confirmed_at"))


@bp.route("/server/settings", methods=["POST"])
@role_required("admin")
def server_settings():
    label = request.form.get("label", "").strip()
    env_type = request.form.get("env_type", "")
    provider = request.form.get("provider", "").strip()
    if len(label) > 40 or len(provider) > 60 or env_type not in ("vps", "dev"):
        flash(T("err_server_form"), "err")
    else:
        set_setting("label", label)
        set_setting("env_type", env_type)
        set_setting("provider", provider)
        set_setting("confirmed_at", now())
        audit("server.confirm", env_type)
        flash(T("msg_saved"), "ok")
    return redirect(url_for("main.server_page"))


@bp.route("/server/guide")
@role_required("admin")
def server_guide():
    return render_template("guide.html")


@bp.route("/api/metrics")
@role_required("admin")
def api_metrics():
    try:
        return jsonify(server.metrics(storage.root()))
    except Exception:  # noqa: BLE001
        return jsonify(error="unavailable"), 503

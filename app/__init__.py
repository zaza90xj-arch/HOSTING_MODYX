import secrets

from flask import Flask, g, redirect, render_template, request, session

from . import db, i18n, security
from .config import load_config


def _registration_open(app):
    if app.config["ALLOW_REGISTRATION"]:
        return True
    try:
        return db.query("SELECT COUNT(*) c FROM users", one=True)["c"] == 0
    except Exception:  # noqa: BLE001
        return False


def create_app(overrides=None):
    app = Flask(__name__)
    app.config.update(load_config(overrides))

    if not app.config["SECRET_KEY"]:
        if app.config["ENV"] == "production":
            raise RuntimeError("SECRET_KEY must be set in production (see .env.example)")
        app.config["SECRET_KEY"] = "dev-" + secrets.token_hex(16)  # random per process; dev only
    if app.config["ENV"] == "production" and not app.config["BASE_URL"]:
        raise RuntimeError("BASE_URL must be set in production (used for e-mail links)")

    db.migrate(app.config["DATABASE_PATH"])
    app.teardown_appcontext(db.close_db)

    @app.before_request
    def load_user():
        g.user = None
        uid = session.get("uid")
        if uid:
            row = db.query("SELECT * FROM users WHERE id=? AND is_active=1", (uid,), one=True)
            if row is None:
                session.clear()
            g.user = row
        security.check_csrf()

    app.after_request(security.add_headers)

    @app.context_processor
    def inject():
        lang = i18n.current_lang()
        return {
            "t": lambda key, **kw: i18n.t(key, lang, **kw),
            "lang": lang,
            "dir": "rtl" if lang == "ar" else "ltr",
            "csrf_token": security.csrf_token,
            "user": g.get("user"),
            "nav": i18n.NAV,
            "registration_open": _registration_open(app),
        }

    from .auth import bp as auth_bp
    from .main import bp as main_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    def error_page(code):
        def handler(e):
            if code == 500:
                try:
                    cause = getattr(e, "original_exception", None) or e
                    db.execute("INSERT INTO events (level, message, created_at) VALUES (?,?,?)",
                               ("error", f"500 {request.method} {request.path}: {type(cause).__name__}", db.now()))
                except Exception:  # noqa: BLE001 - never fail while reporting a failure
                    pass
            return render_template("error.html", code=code), code
        return handler

    for code in (403, 404, 405, 413, 429, 500):
        app.register_error_handler(code, error_page(code))

    return app

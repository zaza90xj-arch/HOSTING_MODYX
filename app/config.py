"""Configuration loaded from environment variables. No secrets live in code."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _bool(v, default=False):
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def load_config(overrides=None):
    env = os.environ.get
    cfg = {
        "ENV": env("MODYX_ENV", "development"),
        "SECRET_KEY": env("SECRET_KEY", ""),
        "BASE_URL": env("BASE_URL", "").rstrip("/"),
        "DATABASE_PATH": env("DATABASE_PATH", str(BASE_DIR / "instance" / "modyx.db")),
        "STORAGE_ROOT": env("STORAGE_ROOT", str(BASE_DIR / "data" / "storage")),
        "ADMIN_EMAILS": [e.strip().lower() for e in env("ADMIN_EMAILS", "").split(",") if e.strip()],
        "SMTP_HOST": env("SMTP_HOST", ""),
        "SMTP_PORT": int(env("SMTP_PORT", "587")),
        "SMTP_USER": env("SMTP_USER", ""),
        "SMTP_PASSWORD": env("SMTP_PASSWORD", ""),
        "SMTP_TLS": _bool(env("SMTP_TLS"), True),
        "MAIL_FROM": env("MAIL_FROM", "MODYX VPS HOSTING <no-reply@localhost>"),
        "MAX_CONTENT_LENGTH": int(env("MAX_UPLOAD_MB", "64")) * 1024 * 1024,
        "DEFAULT_LANG": env("DEFAULT_LANG", "ar"),
        "ALLOW_REGISTRATION": _bool(env("ALLOW_REGISTRATION"), False),
        "TESTING": False,
    }
    # Mail: real SMTP when configured, otherwise the link is written to the server log (dev only).
    cfg["MAIL_MODE"] = "smtp" if cfg["SMTP_HOST"] else "console"
    # Only force verified e-mail when mail can really be delivered.
    cfg["REQUIRE_VERIFIED"] = _bool(env("REQUIRE_VERIFIED"), cfg["MAIL_MODE"] == "smtp")
    # Secure cookies need HTTPS. Set COOKIE_SECURE=false only for a first test over plain HTTP.
    cfg["SESSION_COOKIE_SECURE"] = _bool(env("COOKIE_SECURE"), cfg["ENV"] == "production")
    cfg["SESSION_COOKIE_HTTPONLY"] = True
    cfg["SESSION_COOKIE_SAMESITE"] = "Lax"
    if overrides:
        cfg.update(overrides)
    return cfg

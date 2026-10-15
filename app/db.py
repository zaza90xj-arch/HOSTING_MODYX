"""SQLite data layer + plain-SQL migrations (PostgreSQL arrives with the production stack, see docs/ROADMAP.md)."""
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import current_app, g

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def iso_in(hours=0, minutes=0):
    return (datetime.now(timezone.utc) + timedelta(hours=hours, minutes=minutes)).isoformat(timespec="seconds")


def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    return con


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE_PATH"])
    return g.db


def close_db(exc=None):
    con = g.pop("db", None)
    if con is not None:
        con.close()


def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    if one:
        return rows[0] if rows else None
    return rows


def execute(sql, args=()):
    con = get_db()
    cur = con.execute(sql, args)
    con.commit()
    return cur.lastrowid


def migrate(path):
    con = connect(path)
    con.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
    done = {r["name"] for r in con.execute("SELECT name FROM schema_migrations")}
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if f.name in done:
            continue
        con.executescript(f.read_text(encoding="utf-8"))
        con.execute("INSERT INTO schema_migrations VALUES (?, ?)", (f.name, now()))
        con.commit()
    con.close()

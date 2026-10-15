CREATE TABLE plans (
  id            TEXT PRIMARY KEY,
  sort          INTEGER NOT NULL,
  max_projects  INTEGER NOT NULL,
  storage_mb    INTEGER NOT NULL,
  ram_mb        INTEGER NOT NULL,
  cpu_percent   INTEGER NOT NULL,
  build_minutes INTEGER NOT NULL
);
-- Starting values only. Edit to match the real capacity of your servers.
INSERT INTO plans VALUES ('free',      1,   2,    256,  128,  10,   30);
INSERT INTO plans VALUES ('developer', 2,  10,   2048,  512,  25,  300);
INSERT INTO plans VALUES ('pro',       3,  30,  10240, 1024,  50, 1000);
INSERT INTO plans VALUES ('business',  4, 100,  51200, 2048, 100, 3000);

CREATE TABLE users (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  email          TEXT NOT NULL UNIQUE,
  name           TEXT NOT NULL,
  password_hash  TEXT NOT NULL,
  role           TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user','developer','admin')),
  lang           TEXT NOT NULL DEFAULT 'ar' CHECK (lang IN ('ar','en')),
  plan_id        TEXT NOT NULL DEFAULT 'free' REFERENCES plans(id),
  email_verified INTEGER NOT NULL DEFAULT 0,
  is_active      INTEGER NOT NULL DEFAULT 1,
  created_at     TEXT NOT NULL,
  last_login_at  TEXT
);

CREATE TABLE tokens (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind       TEXT NOT NULL CHECK (kind IN ('verify','reset')),
  token_hash TEXT NOT NULL UNIQUE,
  expires_at TEXT NOT NULL,
  used_at    TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE projects (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  slug          TEXT NOT NULL UNIQUE,
  name          TEXT NOT NULL,
  description   TEXT NOT NULL DEFAULT '',
  runtime       TEXT NOT NULL CHECK (runtime IN ('static','node','python','php','docker')),
  build_command TEXT NOT NULL DEFAULT '',
  start_command TEXT NOT NULL DEFAULT '',
  status        TEXT NOT NULL DEFAULT 'created',
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);
CREATE INDEX idx_projects_owner ON projects(owner_id);

CREATE TABLE audit_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
  action     TEXT NOT NULL,
  target     TEXT,
  ip         TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX idx_audit_user ON audit_log(user_id, id DESC);

CREATE TABLE rate_limits (
  key TEXT NOT NULL,
  ts  INTEGER NOT NULL
);
CREATE INDEX idx_rate_key ON rate_limits(key, ts);

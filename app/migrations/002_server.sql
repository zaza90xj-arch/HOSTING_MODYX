-- Owner plan: a personal panel is not metered by commercial plans.
INSERT INTO plans VALUES ('owner', 0, 50, 1048576, 0, 0, 0);

CREATE TABLE server_settings (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

-- Real runtime errors and system events recorded by the panel itself.
CREATE TABLE events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  level      TEXT NOT NULL CHECK (level IN ('info','warning','error')),
  message    TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX idx_events_id ON events(id DESC);

# MODYX VPS HOSTING: honest status

| Phase | Scope | Status |
|---|---|---|
| 1 | Panel, dashboard, projects with real storage folders, bilingual RTL/LTR, tests | **Built and tested** |
| 2 | Secure login (first account = owner, registration then closed), real server detection, live CPU/RAM/disk/network metrics, error events, environment confirmation, installer files | **Built and tested locally.** `deploy/install.sh`, systemd and nginx files are **not tested on a real server yet** |
| 3 | File manager (upload, edit, search, safe unzip); path-safety helper already exists in `app/storage.py` | Not built |
| 4 | Restricted real terminal | Not built |
| 5 | GitHub App/OAuth, clone, isolated build, deploy, rollback, signed webhooks | Not built |
| 6 | Runtimes, logs, health checks, backups, domains/HTTPS | Not built |
| 7 | Security, resource-limit, recovery and mobile testing | Not built |
| 8 | Deployment and migration guides | Partly (README, ANDROID_SETUP) |

## Architecture decisions
- **Flask + SQLite, no React/FastAPI yet.** It runs in 50-100 MB of RAM, fits a 1 GB free server, and is already tested. SQL migrations in `app/migrations` make a later PostgreSQL move a contained change.
- **The panel is installed on the server it manages.** No SSH keys or server passwords are ever stored. Remote-over-SSH control is intentionally not built.
- **Nothing claims to be a VPS by itself.** The owner confirms "real VPS" or "development environment"; development mode shows a permanent banner.
- **Migration:** copy `DATABASE_PATH` and `STORAGE_ROOT`, install the panel on the new server, restore both.

## Compatibility limits
Linux (Ubuntu 22.04/24.04 targeted), x86_64 or arm64. On arm64 some Docker images do not exist. With 1 GB RAM run small apps only and add swap. Docker support (phase 6) needs Docker installed and a non-root, rootless or socket-proxy setup; the panel will never mount the host Docker socket into user apps.

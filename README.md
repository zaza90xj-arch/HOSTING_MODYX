# MODYX VPS HOSTING

A control panel you install **on your own Linux server** (a real VPS, or a development environment). It reads the server's real hardware and live metrics and manages projects. It does not create servers, does not spend money, and shows "unavailable" instead of fake numbers.

**Status:** phases 1-2 built and tested (34 automated tests). File manager, terminal, GitHub, deployments, runtimes and backups are **not built yet**; their pages say so. See `docs/ROADMAP.md`. Android-only setup: `docs/ANDROID_SETUP.md`.

## Quick start (development)
```bash
pip install -r requirements.txt
python wsgi.py        # http://localhost:8000
python -m unittest discover -s tests -v
```
First account registered becomes the owner; registration then closes (`ALLOW_REGISTRATION=false`).

## Real server
`sudo bash deploy/install.sh https://your-domain` on Ubuntu (untested on a real server so far). Or `docker compose up -d --build`.

---
Details from the original phase 1 README follow.

Developer hosting platform, built in phases. **Phase 1 is real and tested; later phases are listed as "not built yet" in the UI and are never simulated.** See `docs/ROADMAP.md`.

## What works now
- Sign up, log in/out, e-mail verification, password reset (rate limited, CSRF protected, hashed passwords)
- Roles (user / developer / admin). Admin = e-mail listed in `ADMIN_EMAILS`
- Projects: create / edit / delete (type the project ID to confirm). Each project gets a **real folder** under `STORAGE_ROOT/<user>/<project>`
- Plan limits enforced for number of projects; storage usage is measured from disk
- Dashboard with real numbers; admin sees live server CPU/RAM/disk (psutil)
- Arabic + English, RTL/LTR, mobile first dark UI
- Service status page, `/healthz`, 404/403/500 pages, audit log, security headers (CSP, frame deny)

## What does NOT run yet
Executing projects, terminal, GitHub, deployments, databases, domains, backups, AI, billing. Pages for them show an honest "not built yet" notice.

## Run locally (any machine with Python 3.10+)
```bash
pip install -r requirements.txt
cp .env.example .env        # optional for development
python wsgi.py              # http://localhost:8000
```
In development, verification/reset e-mails are printed in the server console (SMTP not configured).

## Tests
```bash
python -m unittest discover -s tests -v
```
Covers sign-up, login, rate limit, CSRF, verification, reset, roles, plan limits, project isolation between users, delete confirmation, path-traversal protection, i18n completeness.

## Deploy (VPS with Docker)
```bash
cp .env.example .env   # set SECRET_KEY, BASE_URL, ADMIN_EMAILS, SMTP_*
docker compose up -d --build
```
Put a reverse proxy with HTTPS (Caddy or Nginx) in front of port 8000. Without HTTPS, do not use production mode (cookies are Secure-only).

## Deploy from a phone
Upload this folder to a GitHub repository, then use a host that builds from GitHub (Render, Railway, Fly.io). Set the env vars from `.env.example` in their dashboard and attach a persistent disk for `/srv/instance` and `/srv/data`; without a disk, data is lost on every deploy.

## Security notes
Passwords: scrypt hashes. Sessions: signed HttpOnly SameSite cookies. CSRF token on every POST. Login/register/reset are rate limited in the database. Uploaded code is never executed by this app; execution will live in separate isolated containers (phase 5).

import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from app import create_app, storage
from app.translations import AR, EN


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = create_app({
            "DATABASE_PATH": os.path.join(self.tmp, "t.db"), "STORAGE_ROOT": os.path.join(self.tmp, "storage"),
            "TESTING": True, "MAIL_MODE": "memory", "REQUIRE_VERIFIED": False,
            "ADMIN_EMAILS": ["boss@example.com"], "DEFAULT_LANG": "en", "ALLOW_REGISTRATION": True})
        self.c = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def csrf(self, client=None, path="/login"):
        client = client or self.c
        html = client.get(path, follow_redirects=True).get_data(as_text=True)
        return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)

    def post(self, path, data, client=None, follow=False):
        client = client or self.c
        data = dict(data, csrf_token=self.csrf(client))
        return client.post(path, data=data, follow_redirects=follow)

    def register(self, email="a@example.com", pw="password123", client=None):
        return self.post("/register", {"name": "Test User", "email": email, "password": pw, "password2": pw}, client)

    def new_client(self):
        return self.app.test_client()


class AuthTests(Base):
    def test_register_login_logout(self):
        r = self.register()
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.c.get("/dashboard").status_code, 200)
        self.post("/logout", {})
        self.assertEqual(self.c.get("/dashboard").status_code, 302)
        r = self.post("/login", {"email": "a@example.com", "password": "password123"})
        self.assertEqual(r.status_code, 302)

    def test_validation_and_duplicates(self):
        self.assertEqual(self.post("/register", {"name": "x", "email": "bad", "password": "1", "password2": "1"}).status_code, 400)
        self.assertEqual(self.post("/register", {"name": "Ok Name", "email": "b@example.com", "password": "password123", "password2": "different1"}).status_code, 400)
        self.register()
        self.assertEqual(self.register(client=self.new_client()).status_code, 400)

    def test_password_is_hashed(self):
        self.register()
        import sqlite3
        row = sqlite3.connect(self.app.config["DATABASE_PATH"]).execute("select password_hash from users").fetchone()
        self.assertNotIn("password123", row[0])

    def test_wrong_password_and_rate_limit(self):
        self.register()
        self.post("/logout", {})
        for _ in range(8):
            self.assertEqual(self.post("/login", {"email": "a@example.com", "password": "nope"}).status_code, 401)
        self.assertEqual(self.post("/login", {"email": "a@example.com", "password": "password123"}).status_code, 429)

    def test_csrf_required(self):
        self.assertEqual(self.c.post("/login", data={"email": "a", "password": "b"}).status_code, 403)
        self.assertEqual(self.c.post("/register", data={"csrf_token": "wrong"}).status_code, 403)

    def test_open_redirect_blocked(self):
        self.register()
        self.post("/logout", {})
        r = self.post("/login", {"email": "a@example.com", "password": "password123", "next": "//evil.com"})
        self.assertNotIn("evil.com", r.headers["Location"])

    def test_email_verification_flow(self):
        self.register()
        mail = self.app.extensions["outbox"][-1]
        token = re.search(r"/verify/(\S+)", mail["body"]).group(1)
        self.assertIn(b"Verify your email", self.c.get("/dashboard").data)
        self.assertEqual(self.c.get(f"/verify/{token}").status_code, 302)
        self.assertNotIn(b"Verify your email", self.c.get("/dashboard").data)
        self.c.get(f"/verify/{token}")  # second use must fail
        self.assertIn(b"invalid or has expired", self.c.get("/dashboard").data + self.c.get("/").data + self.c.get("/login").data)

    def test_verification_gate(self):
        self.app.config["REQUIRE_VERIFIED"] = True
        self.register()
        r = self.post("/projects/new", {"name": "Site", "runtime": "static"})
        self.assertEqual(r.status_code, 403)

    def test_password_reset_flow(self):
        self.register()
        self.post("/logout", {})
        self.post("/forgot", {"email": "ghost@example.com"})
        self.assertEqual(len(self.app.extensions["outbox"]), 1)  # only the verification mail: no mail for unknown account
        self.post("/forgot", {"email": "a@example.com"})
        token = re.search(r"/reset/(\S+)", self.app.extensions["outbox"][-1]["body"]).group(1)
        self.assertEqual(self.post(f"/reset/{token}", {"password": "newpassword9", "password2": "newpassword9"}).status_code, 302)
        self.assertEqual(self.post(f"/reset/{token}", {"password": "another1234", "password2": "another1234"}).status_code, 302)  # token dead -> redirected to /forgot
        self.assertEqual(self.post("/login", {"email": "a@example.com", "password": "newpassword9"}).status_code, 302)
        self.post("/logout", {})
        self.assertEqual(self.post("/login", {"email": "a@example.com", "password": "password123"}).status_code, 401)

    def test_admin_role_from_env_only(self):
        self.register("boss@example.com")
        self.register("x@example.com", client=self.new_client())
        import sqlite3
        roles = dict(sqlite3.connect(self.app.config["DATABASE_PATH"]).execute("select email, role from users").fetchall())
        self.assertEqual(roles, {"boss@example.com": "admin", "x@example.com": "user"})


class ProjectTests(Base):
    def setUp(self):
        super().setUp()
        self.register()

    def create(self, name="My Site", client=None, runtime="static"):
        return self.post("/projects/new", {"name": name, "runtime": runtime, "description": "d", "build_command": "", "start_command": ""}, client)

    def test_create_makes_real_directory(self):
        r = self.create()
        self.assertEqual(r.status_code, 302)
        pid = int(r.headers["Location"].rsplit("/", 1)[1])
        with self.app.app_context():
            self.assertTrue(storage.project_dir(1, pid).is_dir())

    def test_plan_limit_enforced(self):
        import sqlite3
        con = sqlite3.connect(self.app.config["DATABASE_PATH"]); con.execute("update users set plan_id='free'"); con.commit(); con.close()
        self.assertEqual(self.create("One").status_code, 302)
        self.assertEqual(self.create("Two").status_code, 302)
        self.assertEqual(self.create("Three").status_code, 403)  # free plan = 2 projects

    def test_validation(self):
        self.assertEqual(self.post("/projects/new", {"name": "x", "runtime": "static"}).status_code, 400)
        self.assertEqual(self.post("/projects/new", {"name": "Good", "runtime": "cobol"}).status_code, 400)
        self.assertEqual(self.post("/projects/new", {"name": "Good", "runtime": "node", "start_command": "a\nb"}).status_code, 400)

    def test_other_users_cannot_touch_project(self):
        pid = int(self.create().headers["Location"].rsplit("/", 1)[1])
        other = self.new_client()
        self.register("b@example.com", client=other)
        self.assertEqual(other.get(f"/projects/{pid}").status_code, 404)
        self.assertEqual(self.post(f"/projects/{pid}/edit", {"name": "Hacked", "runtime": "node"}, other).status_code, 404)
        self.assertEqual(self.post(f"/projects/{pid}/delete", {"confirm": "x"}, other).status_code, 404)
        self.assertEqual(self.c.get(f"/projects/{pid}").status_code, 200)

    def test_delete_requires_confirmation_and_removes_files(self):
        pid = int(self.create("Delete Me").headers["Location"].rsplit("/", 1)[1])
        with self.app.app_context():
            d = storage.project_dir(1, pid)
        (d / "index.html").write_text("hi")
        self.post(f"/projects/{pid}/delete", {"confirm": "wrong"})
        self.assertTrue(d.exists())
        self.post(f"/projects/{pid}/delete", {"confirm": "delete-me"})
        self.assertFalse(d.exists())
        self.assertEqual(self.c.get(f"/projects/{pid}").status_code, 404)

    def test_dashboard_numbers_come_from_disk(self):
        pid = int(self.create().headers["Location"].rsplit("/", 1)[1])
        with self.app.app_context():
            d = storage.project_dir(1, pid)
        (d / "big.bin").write_bytes(b"x" * 5000)
        self.assertIn(b"5.0 kB", self.c.get("/dashboard").data)

    def test_host_stats_admin_only(self):
        self.assertIn(b"Server (this machine)", self.c.get("/dashboard").data)  # first user = owner/admin
        other = self.new_client()
        self.register("x@example.com", client=other)
        self.assertNotIn(b"Server (this machine)", other.get("/dashboard").data)


class StorageSafetyTests(Base):
    def test_safe_join_blocks_escapes(self):
        with self.app.app_context():
            base = storage.root()
            self.assertEqual(storage.safe_join(base, "a", "b.txt"), base / "a" / "b.txt")
            for bad in ("../x", "a/../../x", "..\\..\\x"):
                try:
                    p = storage.safe_join(base, bad)
                    self.assertTrue(base in p.parents or p == base)  # leading slashes are stripped, never escape
                except storage.UnsafePath:
                    pass
            with self.assertRaises(storage.UnsafePath):
                storage.safe_join(base, "../outside")
            (base / "link").symlink_to("/etc")
            with self.assertRaises(storage.UnsafePath):
                storage.safe_join(base, "link", "passwd")


class SiteTests(Base):
    def test_pages_and_headers(self):
        for p in ("/", "/login", "/register", "/forgot", "/status"):
            r = self.c.get(p)
            self.assertEqual(r.status_code, 200, p)
            self.assertEqual(r.headers["X-Frame-Options"], "DENY")
            self.assertIn("default-src 'self'", r.headers["Content-Security-Policy"])
        self.assertEqual(self.c.get("/nope").status_code, 404)
        self.assertEqual(self.c.get("/healthz").get_json(), {"status": "ok"})

    def test_protected_pages_redirect(self):
        for p in ("/dashboard", "/projects", "/projects/new", "/settings", "/plans", "/soon/files", "/server", "/server/guide", "/api/metrics"):
            self.assertEqual(self.c.get(p).status_code, 302, p)

    def test_language_switch_and_rtl(self):
        html = self.c.get("/lang/ar?next=/login", follow_redirects=True).get_data(as_text=True)
        self.assertIn('dir="rtl"', html)
        self.assertIn("تسجيل الدخول", html)
        self.assertIn('dir="ltr"', self.c.get("/lang/en?next=/login", follow_redirects=True).get_data(as_text=True))

    def test_logged_in_pages_render_in_both_languages(self):
        self.register()
        for code in ("ar", "en"):
            self.c.get(f"/lang/{code}")
            for p in ("/dashboard", "/projects", "/projects/new", "/settings", "/plans", "/soon/files", "/soon/terminal", "/server", "/server/guide"):
                self.assertEqual(self.c.get(p).status_code, 200, (code, p))

    def test_settings_changes(self):
        self.register()
        self.post("/settings", {"form": "profile", "name": "New Name", "lang": "ar"})
        self.assertIn("New Name", self.c.get("/dashboard").get_data(as_text=True))
        self.post("/settings", {"form": "password", "current": "bad", "password": "newpassword9", "password2": "newpassword9"})
        self.post("/logout", {})
        self.assertEqual(self.post("/login", {"email": "a@example.com", "password": "password123"}).status_code, 302)


class TranslationTests(unittest.TestCase):
    def test_languages_in_sync(self):
        self.assertEqual(set(EN), set(AR))

    def test_every_used_key_exists(self):
        root = Path(__file__).resolve().parent.parent / "app"
        text = "".join(p.read_text(encoding="utf-8") for p in list(root.rglob("*.html")) + [root / "auth.py", root / "main.py", root / "i18n.py"])
        used = set(re.findall(r"\bt\('([a-z0-9_]+)'", text)) | set(re.findall(r"\bT\(\"([a-z0-9_]+)\"", text))
        used |= set(re.findall(r"\"(err_[a-z_]+|msg_[a-z_]+)\"", text)) | set(re.findall(r"\"(nav_[a-z]+)\"", text))
        used |= {f"phase_{n}" for n in range(1, 10)} | {f"error_{c}{s}" for c in (403, 404, 405, 413, 429, 500) for s in ("", "_help")}
        used |= {f"rt_{r}" for r in ("static", "node", "python", "php", "docker")} | {f"plan_{p}" for p in ("free", "developer", "pro", "business")}
        used |= {f"soon_{f}" for f in ("files", "github", "deployments", "terminal", "logs", "domains", "backups")}
        used |= {f"role_{r}" for r in ("user", "developer", "admin")} | {"status_created", "status_db", "status_storage", "status_mail"}
        self.assertEqual(sorted(k for k in used if not k.endswith("_") and k not in EN), [])


class ServerTests(Base):
    def setUp(self):
        super().setUp()
        self.app.add_url_rule("/boom", "boom", lambda: 1 / 0)  # must be added before the first request
        self.register()  # first account = owner (admin)

    def test_first_user_is_owner_and_others_are_not(self):
        import sqlite3
        self.register("two@example.com", client=self.new_client())
        rows = sqlite3.connect(self.app.config["DATABASE_PATH"]).execute("select email, role, plan_id from users order by id").fetchall()
        self.assertEqual(rows, [("a@example.com", "admin", "owner"), ("two@example.com", "user", "free")])

    def test_registration_closed_after_owner(self):
        self.app.config["ALLOW_REGISTRATION"] = False
        other = self.new_client()
        self.assertEqual(other.get("/register").status_code, 302)
        r = self.post("/register", {"name": "Intruder", "email": "i@example.com", "password": "password123", "password2": "password123"}, other)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])
        self.assertNotIn(b"Create owner account", other.get("/").data)

    def test_non_owner_cannot_use_server_pages(self):
        other = self.new_client()
        self.register("x@example.com", client=other)
        for p in ("/server", "/server/guide", "/api/metrics"):
            self.assertEqual(other.get(p).status_code, 403, p)
        self.assertEqual(self.post("/server/settings", {"env_type": "vps"}, other).status_code, 403)

    def test_metrics_are_real_measurements(self):
        import psutil
        m = self.c.get("/api/metrics").get_json()
        self.assertEqual(m["ram"]["total"], psutil.virtual_memory().total)
        self.assertEqual(m["disk"]["total"], __import__("shutil").disk_usage(self.app.config["STORAGE_ROOT"]).total)
        self.assertTrue(0 <= m["cpu"] <= 100)
        self.assertGreater(m["uptime_s"], 0)
        self.assertGreater(m["net"]["recv"] + m["net"]["sent"], -1)

    def test_metrics_unavailable_is_503_not_fake_zeros(self):
        from app import server
        orig = server.metrics
        server.metrics = lambda root: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            r = self.c.get("/api/metrics")
        finally:
            server.metrics = orig
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.get_json(), {"error": "unavailable"})

    def test_detect_matches_machine(self):
        import platform
        from app import server
        with self.app.app_context():
            info = server.detect(storage.root())
        self.assertTrue(info["ok"])
        self.assertEqual(info["arch"], platform.machine().lower())
        self.assertEqual(info["cpu_logical"], os.cpu_count())
        self.assertIn("python3", info["tools"])
        self.assertEqual(info["root"], os.geteuid() == 0)
        self.assertEqual(("warn_root" in info["warnings"]), info["root"])

    def test_server_page_and_confirmation(self):
        self.assertIn(b"Open the Server page", self.c.get("/dashboard").data)  # unconfirmed environment is flagged
        self.post("/server/settings", {"label": "my-box", "env_type": "dev", "provider": "none"})
        html = self.c.get("/dashboard").data
        self.assertIn(b"Development mode", html)
        self.assertNotIn(b"Open the Server page", html)
        self.assertIn(b"my-box", self.c.get("/server").data)
        self.post("/server/settings", {"label": "x", "env_type": "hacked", "provider": ""})
        self.assertIn(b"my-box", self.c.get("/server").data)  # invalid input did not overwrite

    def test_server_error_recorded_as_event(self):
        self.app.config["PROPAGATE_EXCEPTIONS"] = False
        self.assertEqual(self.c.get("/boom").status_code, 500)
        self.assertIn(b"ZeroDivisionError", self.c.get("/dashboard").data)


class ConfigTests(unittest.TestCase):
    def test_production_requires_secret(self):
        with self.assertRaises(RuntimeError):
            create_app({"ENV": "production", "SECRET_KEY": "", "BASE_URL": "https://x.y", "DATABASE_PATH": tempfile.mkdtemp() + "/a.db"})


if __name__ == "__main__":
    unittest.main()

from flask import g, request, session

LANGS = ("ar", "en")

# (endpoint or 'soon:<feature>', i18n key, icon-less)  -- phase = when the feature becomes real
NAV = [
    ("main.dashboard", "nav_dashboard", None),
    ("main.server_page", "nav_server", None),
    ("main.projects", "nav_projects", None),
    ("main.soon:files", "nav_files", 3),
    ("main.soon:terminal", "nav_terminal", 4),
    ("main.soon:github", "nav_github", 5),
    ("main.soon:deployments", "nav_deployments", 5),
    ("main.soon:logs", "nav_logs", 6),
    ("main.soon:backups", "nav_backups", 6),
    ("main.soon:domains", "nav_domains", 6),
    ("main.settings", "nav_settings", None),
]
SOON_PHASE = {"files": 3, "terminal": 4, "github": 5, "deployments": 5, "logs": 6, "backups": 6, "domains": 6}


def current_lang():
    if g.get("user") is not None:
        return g.user["lang"]
    from flask import current_app
    return session.get("lang") or request.cookies.get("lang") or current_app.config["DEFAULT_LANG"]


def t(key, lang, **kw):
    from .translations import TR
    text = TR.get(lang, {}).get(key) or TR["en"].get(key) or key
    return text.format(**kw) if kw else text

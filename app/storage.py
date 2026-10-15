"""Real per-project storage on disk. Every path is resolved and checked to stay inside STORAGE_ROOT."""
import os
import shutil
from pathlib import Path

from flask import current_app


class UnsafePath(ValueError):
    pass


def root():
    p = Path(current_app.config["STORAGE_ROOT"]).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_join(base, *parts):
    """Join parts under base; refuse '..', absolute paths and symlink escapes."""
    base = Path(base).resolve()
    target = base.joinpath(*[str(x).lstrip("/\\") for x in parts]).resolve()
    if target != base and base not in target.parents:
        raise UnsafePath("path escapes its base directory")
    return target


def user_dir(user_id):
    return safe_join(root(), str(int(user_id)))


def project_dir(user_id, project_id):
    return safe_join(root(), str(int(user_id)), str(int(project_id)))


def ensure_project_dir(user_id, project_id):
    p = project_dir(user_id, project_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def dir_size(path):
    total = 0
    path = Path(path)
    if not path.exists():
        return 0
    for dirpath, _dirs, files in os.walk(path, followlinks=False):
        for f in files:
            try:
                total += os.lstat(os.path.join(dirpath, f)).st_size
            except OSError:
                pass
    return total


def remove_project_dir(user_id, project_id):
    p = project_dir(user_id, project_id)
    if p.exists():
        shutil.rmtree(p)

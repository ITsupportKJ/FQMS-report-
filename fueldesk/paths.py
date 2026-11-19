"""Where the app keeps its files. Everything lives in the user's app-data
folder, never next to the program, so installs under Program Files work."""

import os
import sys
from pathlib import Path

from . import APP_NAME


def app_home() -> Path:
    override = os.environ.get("FUELDESK_HOME")          # used by tests
    if override:
        root = Path(override)
    elif sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        root = Path(base) / APP_NAME
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def _sub(name: str) -> Path:
    p = app_home() / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    return app_home() / "fueldesk.db"


def reports_dir() -> Path:
    return _sub("reports")


def backups_dir() -> Path:
    return _sub("backups")


def logs_dir() -> Path:
    return _sub("logs")

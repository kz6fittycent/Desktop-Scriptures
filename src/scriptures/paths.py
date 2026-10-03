"""Where the app's bundled files and the user's own data live.

Three ways the app runs:

- From a source checkout (development): bundled files are in the repo's
  data/, and the bundled database is used directly.
- As a snap: bundled files are inside the read-only snap, and the user's
  database is a copy in $SNAP_USER_COMMON.
- As a packaged Windows or macOS app (PyInstaller - see packaging/):
  bundled files are unpacked beside the program (sys._MEIPASS), and the
  user's database is a copy in the platform's usual per-user data folder,
  since the install location is read-only:
    Windows  %APPDATA%\\Desktop Scriptures
    macOS    ~/Library/Application Support/Desktop Scriptures
    Linux    $XDG_DATA_HOME/desktop-scriptures (~/.local/share/...)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Desktop Scriptures"


def is_frozen() -> bool:
    """A PyInstaller build, rather than Python running the source."""
    return bool(getattr(sys, "frozen", False))


def _app_root() -> Path:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent.parent.parent


APP_ROOT = _app_root()
DATA_DIR = APP_ROOT / "data"
BUNDLED_DB_PATH = DATA_DIR / "scriptures.db"


def user_data_dir() -> Path | None:
    """The folder for the user's own copy of the database (and the study
    index beside it), or None when the bundled database is used directly
    (running from source)."""
    snap_user_common = os.environ.get("SNAP_USER_COMMON")
    if snap_user_common:
        return Path(snap_user_common)
    if not is_frozen():
        return None
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return base / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "desktop-scriptures"


def voices_dir() -> Path:
    """Where downloaded Listen voices go (see tts.py) - per user, since
    the app runs as the user and can't write anywhere system-wide (in a
    snap, $SNAP_COMMON under /var/snap is root-only):
      snap     $SNAP_USER_COMMON/voices (~/snap/desktop-scriptures/common)
      Windows  %LOCALAPPDATA%\\Desktop Scriptures\\voices - local, not
               roaming: ~60 MB files shouldn't follow a roaming profile
      macOS    ~/Library/Application Support/Desktop Scriptures/voices
      source   data/tts_voices (where scripts/download_tts_voices.py puts them)
    """
    if is_frozen() and sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / APP_NAME / "voices"
    user_dir = user_data_dir()
    if user_dir is None:
        return DATA_DIR / "tts_voices"
    return user_dir / "voices"

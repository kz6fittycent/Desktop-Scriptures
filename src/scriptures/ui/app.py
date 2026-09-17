#!/usr/bin/env python3
"""Scriptures - entry point.

Usage:
    python3 app.py [path-to-scriptures.db]

Defaults to data/scriptures.db relative to the project root if no path
is given - unless running inside a snap (SNAP_USER_COMMON set), see
`_default_db_path()`.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from scriptures.db import connect, sync_bundled_content  # noqa: E402
from scriptures.ui.main_window import MainWindow  # noqa: E402

# The bundled, pre-imported database - read-only once packaged (it ships
# inside the snap's squashfs at this same relative path).
BUNDLED_DB_PATH = PROJECT_ROOT / "data" / "scriptures.db"


def _default_db_path() -> Path:
    """Outside a snap, just use the bundled database directly, same as
    always. Inside one (SNAP_USER_COMMON set), notes/tags/highlights/streak
    all live in this same single-file database alongside the scripture
    text, so it must live under SNAP_USER_COMMON to persist across snap
    revision upgrades - SNAP itself is read-only and replaced on every
    update. The first launch seeds that writable copy from the bundled
    database; every launch after that just opens it in place.
    """
    snap_user_common = os.environ.get("SNAP_USER_COMMON")
    if not snap_user_common:
        return BUNDLED_DB_PATH

    writable_db_path = Path(snap_user_common) / "scriptures.db"
    if not writable_db_path.exists() and BUNDLED_DB_PATH.exists():
        writable_db_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BUNDLED_DB_PATH, writable_db_path)
    return writable_db_path


def main() -> None:
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else _default_db_path()

    if not db_path.exists():
        print(f"Database not found at {db_path}")
        print("Run scripts/import_scriptures.py first, or pass a path:")
        print("  python3 app.py /path/to/scriptures.db")
        sys.exit(1)

    conn = connect(db_path)

    # Only relevant for the writable $SNAP_USER_COMMON copy - see
    # sync_bundled_content's docstring for why this can't just be part
    # of the one-time seed copy above.
    if os.environ.get("SNAP_USER_COMMON") and db_path != BUNDLED_DB_PATH:
        sync_bundled_content(conn, BUNDLED_DB_PATH)

    app = QApplication(sys.argv)
    window = MainWindow(conn)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

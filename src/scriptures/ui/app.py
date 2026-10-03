#!/usr/bin/env python3
"""Scriptures - entry point.

Usage:
    python3 app.py [path-to-scriptures.db]
    python3 app.py --smoke-test

Defaults to data/scriptures.db relative to the project root if no path
is given - unless running as a snap or a packaged app, which use a
writable copy in the user's data folder (see scriptures/paths.py and
`_default_db_path()`).

--smoke-test opens the database, builds the main window, synthesizes a
sentence with a bundled voice if any are installed, prints "smoke test
passed", and exits - used by the Windows/macOS build workflow to check a
packaged build actually starts.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scriptures import paths  # noqa: E402
from scriptures.db import connect, sync_bundled_content  # noqa: E402
from scriptures.ui.main_window import MainWindow  # noqa: E402

BUNDLED_DB_PATH = paths.BUNDLED_DB_PATH


def _default_db_path() -> Path:
    """Running from source, just use the bundled database directly, same
    as always. As a snap or a packaged app, notes/tags/highlights/streak
    all live in this same single-file database alongside the scripture
    text, and the bundled copy is read-only (and replaced on every
    update) - so the user's database is a writable copy in their data
    folder. The first launch seeds that copy from the bundled database;
    every launch after that opens it in place, and sync_bundled_content
    brings in each update's new scripture content.
    """
    user_dir = paths.user_data_dir()
    if user_dir is None:
        return BUNDLED_DB_PATH

    writable_db_path = user_dir / "scriptures.db"
    if not writable_db_path.exists() and BUNDLED_DB_PATH.exists():
        writable_db_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BUNDLED_DB_PATH, writable_db_path)
    return writable_db_path


def _smoke_test(window: MainWindow) -> None:
    """Exits 0 on success, 1 on any failure - an exception inside a Qt
    slot would otherwise just be printed while the app kept running."""
    try:
        from scriptures import tts

        installed = [v.key for v in tts.VOICES if tts.is_voice_installed(v.key)]
        if installed:
            audio = tts.synthesize(installed[0], "In the beginning God created the heaven and the earth.")
            if len(audio) < 1000:
                raise RuntimeError("text-to-speech produced no audio")
        print(f"smoke test passed (window built; voices installed: {len(installed)})", flush=True)
        code = 0
    except Exception:  # noqa: BLE001 - reported, then a failing exit code
        import traceback

        traceback.print_exc()
        print("smoke test FAILED", flush=True)
        code = 1
    window.close()
    QApplication.instance().exit(code)


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--smoke-test"]
    smoke_test = len(args) != len(sys.argv) - 1
    db_path = Path(args[0]) if args else _default_db_path()

    if not db_path.exists():
        print(f"Database not found at {db_path}")
        print("Run scripts/import_scriptures.py first, or pass a path:")
        print("  python3 app.py /path/to/scriptures.db")
        sys.exit(1)

    conn = connect(db_path)

    # Only relevant for a writable copy - see sync_bundled_content's
    # docstring for why this can't just be part of the one-time seed
    # copy above.
    if paths.user_data_dir() is not None and db_path != BUNDLED_DB_PATH:
        sync_bundled_content(conn, BUNDLED_DB_PATH)

    app = QApplication(sys.argv)
    app.setApplicationName(paths.APP_NAME)
    window = MainWindow(conn)
    window.show()
    if smoke_test:
        QTimer.singleShot(0, lambda: _smoke_test(window))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

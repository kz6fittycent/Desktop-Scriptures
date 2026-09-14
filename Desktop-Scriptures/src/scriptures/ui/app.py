#!/usr/bin/env python3
"""Scriptures - entry point.

Usage:
    python3 app.py [path-to-scriptures.db]

Defaults to data/scriptures.db relative to the project root if no path
is given.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from scriptures.db import connect  # noqa: E402
from scriptures.ui.main_window import MainWindow  # noqa: E402

DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "scriptures.db"


def main() -> None:
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB_PATH

    if not db_path.exists():
        print(f"Database not found at {db_path}")
        print("Run scripts/import_scriptures.py first, or pass a path:")
        print("  python3 app.py /path/to/scriptures.db")
        sys.exit(1)

    conn = connect(db_path)

    app = QApplication(sys.argv)
    window = MainWindow(conn)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

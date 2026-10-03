"""Entry point for the packaged Windows/macOS app (see desktop-scriptures.spec).

PyInstaller needs a top-level script; this one just runs the same main()
as `python3 src/scriptures/ui/app.py`.
"""

from scriptures.ui.app import main

if __name__ == "__main__":
    main()

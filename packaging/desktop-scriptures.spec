# PyInstaller build for the Windows and macOS apps - see
# .github/workflows/desktop-builds.yml and packaging/README.md.
#
#   pip install -r requirements.txt pyinstaller pillow
#   python scripts/download_tts_voices.py
#   pyinstaller packaging/desktop-scriptures.spec --noconfirm
#
# Produces dist/Desktop Scriptures/ (Windows: Desktop Scriptures.exe inside;
# macOS: also dist/Desktop Scriptures.app). The bundled files land in the
# same data/ layout as the snap - see src/scriptures/paths.py.
# -*- mode: python ; coding: utf-8 -*-

import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).parent
NAME = "Desktop Scriptures"
VERSION = re.search(
    r'__version__ = "([^"]+)"', (ROOT / "src" / "scriptures" / "__init__.py").read_text()
).group(1)

# Mirrors snapcraft.yaml's file list.
DATA_FILES = [
    "scriptures.db",
    "volumes.json",
    "scripture_of_the_day_pool.json",
    "verse_citations.json",
]
voices = ROOT / "data" / "tts_voices"
if not any(voices.glob("*.onnx")):
    sys.exit("No voices in data/tts_voices - run scripts/download_tts_voices.py first.")

datas = [(str(ROOT / "data" / name), "data") for name in DATA_FILES]
datas += [(str(path), "data/tts_voices") for path in sorted(voices.glob("*.onnx*"))]
datas += [(str(ROOT / "LICENSE"), "."), (str(ROOT / "THIRD_PARTY_LICENSES.md"), ".")]
datas += collect_data_files("piper")  # espeak-ng's pronunciation data
# Non-Python files inside the scriptures package itself (schema.sql).
datas += [
    (str(path), str(path.parent.relative_to(ROOT / "src")))
    for path in (ROOT / "src" / "scriptures").rglob("*")
    if path.is_file() and path.suffix not in (".py", ".pyc") and "__pycache__" not in path.parts
]

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    datas=datas,
    hiddenimports=["piper", "piper.voice"],
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=NAME,
    console=False,
    icon=str(ROOT / "snap" / "gui" / "desktop-scriptures.png"),  # converted by Pillow
)
coll = COLLECT(exe, a.binaries, a.datas, name=NAME)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{NAME}.app",
        icon=str(ROOT / "snap" / "gui" / "desktop-scriptures.png"),
        bundle_identifier="io.github.kz6fittycent.desktop-scriptures",
        version=VERSION,
        info_plist={
            "CFBundleShortVersionString": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "13.0",
        },
    )

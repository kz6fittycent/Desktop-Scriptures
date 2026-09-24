#!/usr/bin/env python3
"""Download the 4 bundled Piper TTS voice models into data/tts_voices/
for local development (see src/scriptures/tts.py's module docstring).

Not run automatically, and its output is never committed to this repo -
each model is ~60MB, too large to check in. snapcraft.yaml's
"tts-voices" part fetches the same files at build time via the same
MODEL_SOURCES below, so this script and that part are the two places
that ever need updating if a voice choice changes.

Usage:
    python3 scripts/download_tts_voices.py
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEST_DIR = PROJECT_ROOT / "data" / "tts_voices"

BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en"

# key -> (locale, speaker, quality) - must match src/scriptures/tts.py's
# VOICES list keys exactly.
MODEL_SOURCES: dict[str, tuple[str, str, str]] = {
    "en_US-lessac-medium": ("en_US", "lessac", "medium"),
    "en_US-hfc_female-medium": ("en_US", "hfc_female", "medium"),
    "en_GB-alan-medium": ("en_GB", "alan", "medium"),
    "en_GB-cori-medium": ("en_GB", "cori", "medium"),
}


def _download(url: str, dest: Path) -> None:
    print(f"  {url}")
    with urllib.request.urlopen(url) as response, open(dest, "wb") as f:
        total = int(response.headers.get("Content-Length", 0))
        written = 0
        while chunk := response.read(1024 * 256):
            f.write(chunk)
            written += len(chunk)
            if total:
                print(f"\r  {written / 1_048_576:.1f} / {total / 1_048_576:.1f} MB", end="")
        print()


def main() -> None:
    DEST_DIR.mkdir(parents=True, exist_ok=True)
    for key, (locale, speaker, quality) in MODEL_SOURCES.items():
        onnx_dest = DEST_DIR / f"{key}.onnx"
        json_dest = DEST_DIR / f"{key}.onnx.json"
        if onnx_dest.exists() and json_dest.exists():
            print(f"{key}: already downloaded, skipping")
            continue
        print(f"{key}:")
        base = f"{BASE_URL}/{locale}/{speaker}/{quality}/{key}"
        _download(f"{base}.onnx", onnx_dest)
        _download(f"{base}.onnx.json", json_dest)
    print("Done.")


if __name__ == "__main__":
    sys.exit(main())

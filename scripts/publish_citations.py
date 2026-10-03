#!/usr/bin/env python3
"""Check a freshly harvested citation file, and package it for the
"citations-data" GitHub release the app downloads from (see
src/scriptures/content_updates.py and .github/workflows/refresh-*-citations.yml).

Usage:
    python3 scripts/publish_citations.py NAME --baseline PATH --out DIR

NAME is verse_citations.json or liahona_citations.json (read from data/).
--baseline is that file as it was before the harvest. The harvest must not
have lost entries (scriptures.citation_files.check_replacement - the same
check the app makes before using a download); if it did, this exits with
an error and nothing is published.

Writes DIR/NAME.gz and DIR/NAME.gz.sha256. The gzip has no timestamp, so
unchanged data gives an identical file and checksum - and the app skips
the download.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scriptures.citation_files import FILES, check_replacement, entry_count  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("name", choices=FILES)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    source = PROJECT_ROOT / "data" / args.name
    raw = source.read_bytes()
    data = json.loads(raw)
    problem = check_replacement(args.name, data, args.baseline)
    if problem:
        sys.exit(f"Not publishing {args.name}: {problem}")
    print(f"{args.name}: {entry_count(args.name, data)} entries - ok to publish")

    args.out.mkdir(parents=True, exist_ok=True)
    packed = gzip.compress(raw, compresslevel=9, mtime=0)
    gz = args.out / f"{args.name}.gz"
    gz.write_bytes(packed)
    sha = hashlib.sha256(packed).hexdigest()
    (args.out / f"{args.name}.gz.sha256").write_text(f"{sha}  {gz.name}\n")
    print(f"Wrote {gz} ({len(packed) / 1_000_000:.1f} MB, sha256 {sha})")


if __name__ == "__main__":
    main()

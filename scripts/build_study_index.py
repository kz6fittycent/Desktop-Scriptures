"""Build (or bring up to date) a study index without the GUI - the same
IndexBuilder the "Build Study Index..." dialog uses (see
src/scriptures/embeddings.py), for benchmarking with
scripts/eval_study_index.py or building against a scratch copy.

    python3 scripts/build_study_index.py SCRIPTURES_DB EMBEDDINGS_URL MODEL [--api-key KEY] [--dimensions N]

The index is written next to SCRIPTURES_DB as study_index.db. Progress is
printed every ~30 seconds; Ctrl+C stops it, and re-running resumes.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from PySide6.QtCore import QCoreApplication  # noqa: E402

from scriptures import study_index  # noqa: E402
from scriptures.ai_client import AiConfig  # noqa: E402
from scriptures.db import connect  # noqa: E402
from scriptures.embeddings import IndexBuilder  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("scriptures_db")
    parser.add_argument("embeddings_url")
    parser.add_argument("model")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--dimensions", type=int, default=None)
    args = parser.parse_args()

    app = QCoreApplication(sys.argv)
    conn = connect(Path(args.scriptures_db))
    index_conn = study_index.connect_index(study_index.index_path_for(conn))
    builder = IndexBuilder(
        conn, index_conn, AiConfig(args.embeddings_url, args.api_key, args.model), args.model,
        args.dimensions,
    )
    started = time.time()
    last_print = [0.0]

    def on_progress(done: int, total: int) -> None:
        now = time.time()
        if now - last_print[0] >= 30 or done == total:
            last_print[0] = now
            print(f"{time.strftime('%H:%M:%S')} {done:,}/{total:,} ({done / max(total, 1):.1%})", flush=True)

    def on_finished(ok: bool, message: str) -> None:
        print(f"{'OK' if ok else 'FAILED'} after {(time.time() - started) / 60:.1f} min: {message}", flush=True)
        app.exit(0 if ok else 1)

    builder.progress.connect(on_progress)
    builder.finished.connect(on_finished)
    builder.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

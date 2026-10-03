"""Standalone test script for citation updates (content_updates.py,
citation_files.py, scripts/publish_citations.py). No test framework (see
tests/test_ask.py's docstring); a local HTTP server stands in for the
GitHub "citations-data" release, and SNAP_USER_COMMON points the user
data folder at a temp dir.

Run directly:

    python3 tests/test_content_updates.py
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer  # noqa: E402

from scriptures import citations, content_updates as cu  # noqa: E402
from scriptures.paths import DATA_DIR  # noqa: E402

GC = "verse_citations.json"
LIAHONA = "liahona_citations.json"


def _bundled(name: str) -> dict:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def _newer_gc(extra_talk: str, keep: int | None = None) -> dict:
    data = _bundled(GC)
    data["_harvested"] = "2999-01-01"
    items = list(data["citations"].items())[:keep] if keep else list(data["citations"].items())
    data["citations"] = dict(items)
    data["citations"]["Moses 1:39"] = [
        {"talk_title": extra_talk, "speaker": "Test", "date": "October 2999", "url": "https://example.com/t"}
    ]
    return data


class _Env:
    def __init__(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="scriptures-citations-test-"))
        self.saved_env = os.environ.get("SNAP_USER_COMMON")
        os.environ["SNAP_USER_COMMON"] = str(self.tmp)
        self.files: dict[str, bytes] = {}
        env = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                env.requests.append(self.path)
                body = env.files.get(self.path.rsplit("/", 1)[-1])
                if body is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.requests: list[str] = []
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.saved_url = cu.RELEASE_URL
        cu.RELEASE_URL = f"http://127.0.0.1:{self.httpd.server_port}/citations-data"
        # The Liahona file: serve the bundled one unchanged, so it's "already current".
        self.publish(LIAHONA, _bundled(LIAHONA))

    def publish(self, name: str, data: dict, corrupt: bool = False) -> None:
        packed = gzip.compress(json.dumps(data).encode(), mtime=0)
        sha = hashlib.sha256(packed).hexdigest()
        self.files[f"{name}.gz"] = packed + (b"x" if corrupt else b"")
        self.files[f"{name}.gz.sha256"] = f"{sha}  {name}.gz\n".encode()

    def check(self) -> tuple[list, list]:
        updater = cu.CitationUpdater()
        result: dict = {}
        loop = QEventLoop()
        updater.finished.connect(lambda updated, problems: (result.update(u=updated, p=problems), loop.quit()))
        QTimer.singleShot(20_000, loop.quit)
        updater.check()
        loop.exec()
        return result["u"], result["p"]

    def close(self) -> None:
        cu.RELEASE_URL = self.saved_url
        if self.saved_env is None:
            os.environ.pop("SNAP_USER_COMMON", None)
        else:
            os.environ["SNAP_USER_COMMON"] = self.saved_env
        self.httpd.shutdown()
        citations.reload()
        shutil.rmtree(self.tmp, ignore_errors=True)


def test_newer_data_is_downloaded_and_used() -> None:
    env = _Env()
    try:
        assert cu.citation_path(GC) == DATA_DIR / GC
        env.publish(GC, _newer_gc("A Brand New Talk"))
        updated, problems = env.check()
        assert GC in updated and not problems, (updated, problems)
        assert cu.citation_path(GC) == env.tmp / "citation_updates" / GC
        citations.reload()
        titles = [c.talk_title for c in citations.get_citations("Moses 1:39")]
        assert "A Brand New Talk" in titles
        # The same file again: only the tiny checksums are fetched.
        env.requests.clear()
        updated, problems = env.check()
        assert updated == [] and all(r.endswith(".sha256") for r in env.requests), env.requests
        print("test_newer_data_is_downloaded_and_used: PASSED")
    finally:
        env.close()


def test_bad_or_shrunken_data_is_refused() -> None:
    env = _Env()
    try:
        env.publish(GC, _newer_gc("Corrupt"), corrupt=True)
        updated, problems = env.check()
        assert GC not in updated and "checksum mismatch" in problems[0], problems
        env.publish(GC, _newer_gc("Wiped", keep=142))  # the near-miss: 142 of 1,257 verses
        updated, problems = env.check()
        assert GC not in updated and "only" in problems[0], problems
        assert cu.citation_path(GC) == DATA_DIR / GC  # still the bundled data
        del env.files[f"{GC}.gz.sha256"]  # not published yet / offline
        updated, problems = env.check()
        assert GC not in updated and problems, problems
        print("test_bad_or_shrunken_data_is_refused: PASSED")
    finally:
        env.close()


def test_older_download_loses_to_newer_bundled_data() -> None:
    env = _Env()
    try:
        folder = env.tmp / "citation_updates"
        folder.mkdir(parents=True)
        old = _bundled(GC)
        old["_harvested"] = "2000-01-01"
        (folder / GC).write_text(json.dumps(old))
        # An app update bundled newer data than this old download.
        assert cu.citation_path(GC) == DATA_DIR / GC
        print("test_older_download_loses_to_newer_bundled_data: PASSED")
    finally:
        env.close()


def test_publish_script_refuses_a_shrunken_harvest() -> None:
    import subprocess

    tmp = Path(tempfile.mkdtemp(prefix="scriptures-publish-test-"))
    try:
        big = tmp / "big.json"
        big.write_text((DATA_DIR / GC).read_text(encoding="utf-8"))
        ok = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "publish_citations.py"), GC,
             "--baseline", str(big), "--out", str(tmp / "out")],
            capture_output=True, text=True,
        )
        assert ok.returncode == 0, ok.stderr
        sha = (tmp / "out" / f"{GC}.gz.sha256").read_text().split()[0]
        assert hashlib.sha256((tmp / "out" / f"{GC}.gz").read_bytes()).hexdigest() == sha
        small = _bundled(GC)
        small["citations"] = dict(list(small["citations"].items()) + [(f"Fake 1:{i}", []) for i in range(2000)])
        bigger = tmp / "bigger.json"
        bigger.write_text(json.dumps(small))  # a baseline with far more verses than data/
        refused = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "publish_citations.py"), GC,
             "--baseline", str(bigger), "--out", str(tmp / "out2")],
            capture_output=True, text=True,
        )
        assert refused.returncode != 0 and "Not publishing" in refused.stderr, refused
        assert not (tmp / "out2").exists()
        print("test_publish_script_refuses_a_shrunken_harvest: PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    test_newer_data_is_downloaded_and_used()
    test_bad_or_shrunken_data_is_refused()
    test_older_download_loses_to_newer_bundled_data()
    test_publish_script_refuses_a_shrunken_harvest()
    print("All citation update tests passed.")

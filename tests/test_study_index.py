"""Standalone test script for src/scriptures/study_index.py and
src/scriptures/embeddings.py. No test framework (see tests/test_ask.py's
own docstring for why).

The embeddings endpoint is a real local HTTP server (http.server on a
background thread) speaking the OpenAI-compatible /embeddings shape, so
embeddings.py's actual Qt networking - batching, retries, Retry-After,
batch-halving, auth failures - is exercised end to end. Its "embedding"
is a deterministic bag-of-words hash, so texts sharing words really do
land near each other and search ranking can be checked meaningfully.

Run directly:

    python3 tests/test_study_index.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
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

from scriptures import study_index as si  # noqa: E402
from scriptures.ai_client import AiConfig  # noqa: E402
from scriptures.citations import CitingWork  # noqa: E402
from scriptures.db import connect  # noqa: E402
from scriptures.embeddings import IndexBuilder  # noqa: E402

DIMS = 64


def fake_embedding(text: str) -> list[float]:
    vector = [0.0] * DIMS
    for word in re.findall(r"[a-z]+", text.lower()):
        bucket = int(hashlib.md5(word.encode()).hexdigest(), 16) % DIMS
        vector[bucket] += 1.0
    return vector


class FakeServer:
    """`script` is a list of per-request behaviors consumed in order -
    ("ok",), ("status", code, retry_after), or ("too_large_over", n):
    reject any batch bigger than n with a 400. Once the script runs out,
    every request succeeds."""

    def __init__(self):
        self.script: list[tuple] = []
        self.requests: list[dict] = []
        self.too_large_over: int | None = None
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silence
                pass

            def do_POST(self):  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                server.requests.append(
                    {"body": body, "auth": self.headers.get("Authorization")}
                )
                texts = body["input"]
                behavior = server.script.pop(0) if server.script else ("ok",)
                if behavior[0] == "status":
                    self.send_response(behavior[1])
                    if behavior[2] is not None:
                        self.send_header("Retry-After", str(behavior[2]))
                    payload = json.dumps({"error": {"message": f"fake {behavior[1]}"}}).encode()
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                if server.too_large_over is not None and len(texts) > server.too_large_over:
                    self.send_response(400)
                    payload = b'{"error": {"message": "batch too large"}}'
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                # Deliberately reversed - the client must reorder by index.
                data = [
                    {"index": i, "embedding": fake_embedding(t)} for i, t in enumerate(texts)
                ][::-1]
                payload = json.dumps({"data": data}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_address[1]}/v1"

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


_FAKE_WORKS = [
    CitingWork("The Power of Faith", "A. Speaker", "April 2020", "https://example.org/faith",
               "General Conference", ["Alma 32:21"]),
    CitingWork("Gathering Israel", "B. Writer", "May 1999", "https://example.org/gather",
               "Ensign", ["Genesis 1:1"]),
]


def _seed(conn) -> None:
    conn.execute("INSERT INTO volumes (id, name, slug, sort_order) VALUES (1, 'Holy Bible', 'holy-bible', 1)")
    conn.execute("INSERT INTO volumes (id, name, slug, sort_order) VALUES (2, 'The Book of Mormon', 'book-of-mormon', 2)")
    conn.execute(
        "INSERT INTO volumes (id, name, slug, sort_order) "
        "VALUES (5, 'Journal of Discourses', 'journal-of-discourses', 5)"
    )
    conn.execute("INSERT INTO books (id, volume_id, name, sort_order) VALUES (1, 1, 'Genesis', 1)")
    conn.execute("INSERT INTO books (id, volume_id, name, sort_order) VALUES (2, 2, 'Alma', 1)")
    conn.execute("INSERT INTO books (id, volume_id, name, sort_order) VALUES (3, 5, 'Volume 1', 1)")
    conn.execute("INSERT INTO chapters (id, book_id, chapter_number) VALUES (1, 1, 1)")
    conn.execute("INSERT INTO chapters (id, book_id, chapter_number) VALUES (2, 2, 32)")
    conn.execute(
        "INSERT INTO chapters (id, book_id, chapter_number, title, speaker, discourse_date) "
        "VALUES (3, 3, 1, 'On Prayer', 'Brigham Young', '1853-01-01')"
    )
    genesis = [
        "In the beginning God created the heaven and the earth.",
        "And the earth was without form, and void.",
        "And God said, Let there be light: and there was light.",
        "And God saw the light, that it was good.",
        "And God called the light Day, and the darkness he called Night.",
    ]
    for n, text in enumerate(genesis, start=1):
        conn.execute(
            "INSERT INTO verses (chapter_id, verse_number, text, reference) VALUES (1, ?, ?, ?)",
            (n, text, f"Genesis 1:{n}"),
        )
    alma = {
        21: "Faith is not to have a perfect knowledge of things; therefore if ye have faith "
            "ye hope for things which are not seen, which are true.",
        27: "If ye will awake and arouse your faculties, even to an experiment upon my words, "
            "and exercise a particle of faith.",
        28: "Compare the word unto a seed, if ye give place that a seed may be planted in your heart.",
    }
    for n, text in alma.items():
        conn.execute(
            "INSERT INTO verses (chapter_id, verse_number, text, reference) VALUES (2, ?, ?, ?)",
            (n, text, f"Alma 32:{n}"),
        )
    discourse = "\n\n".join(
        f"Paragraph {i} about prayer and the spirit of revelation, morning and evening." for i in range(40)
    )
    conn.execute(
        "INSERT INTO verses (chapter_id, verse_number, text, reference) VALUES (3, 1, ?, 'Journal of Discourses 1:1')",
        (discourse,),
    )
    conn.execute(
        "INSERT INTO topics (id, name, slug, description, sort_order) "
        "VALUES (1, 'Faith', 'faith', 'Trust and confidence in Jesus Christ.', 1)"
    )
    conn.execute(
        "INSERT INTO topic_verses (topic_id, volume_slug, reference, sort_order) "
        "VALUES (1, 'book-of-mormon', 'Alma 32:21', 1)"
    )
    conn.execute(
        "INSERT INTO notes (verse_id, text) VALUES "
        "((SELECT id FROM verses WHERE reference = 'Alma 32:28'), 'The seed grows when nourished')"
    )
    conn.execute(
        "INSERT INTO journal_entries (entry_date, text) VALUES ('2026-01-01', 'PRIVATE JOURNAL TEXT')"
    )
    conn.commit()


class _Env:
    def __init__(self, batch_size: int = 4):
        self.tmp = Path(tempfile.mkdtemp(prefix="scriptures-study-index-test-"))
        self.conn = connect(self.tmp / "scriptures.db")
        _seed(self.conn)
        self.index_conn = si.connect_index(si.index_path_for(self.conn))
        self.server = FakeServer()
        self.config = AiConfig(base_url=self.server.base_url, api_key="sk-test", model="chat-model")
        self.batch_size = batch_size

    def build(self, model: str = "embed-a", dimensions: int | None = None, cancel_after: int | None = None):
        builder = IndexBuilder(
            self.conn, self.index_conn, self.config, model, dimensions, batch_size=self.batch_size
        )
        result: dict = {}
        loop = QEventLoop()

        def on_progress(done: int, total: int) -> None:
            result.setdefault("progress", []).append((done, total))
            if cancel_after is not None and len(result["progress"]) > cancel_after:
                builder.cancel()

        builder.progress.connect(on_progress)
        builder.finished.connect(lambda ok, msg: (result.update(ok=ok, message=msg), loop.quit()))
        QTimer.singleShot(30_000, loop.quit)  # safety net
        builder.start()
        loop.exec()
        result["builder"] = builder
        return result

    def close(self) -> None:
        self.server.close()
        self.index_conn.close()
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)


def _with_fake_works(fn):
    def wrapper():
        original = si.iter_citing_works
        si.iter_citing_works = lambda: list(_FAKE_WORKS)
        try:
            fn()
        finally:
            si.iter_citing_works = original
    wrapper.__name__ = fn.__name__
    return wrapper


@_with_fake_works
def test_collect_pieces_covers_every_source_but_the_journal() -> None:
    env = _Env()
    try:
        pieces = si.collect_pieces(env.conn)
        kinds = {p.kind for p in pieces}
        assert {"scripture", "discourse", "topic", "talk", "article", "note"} <= kinds, kinds
        assert not any("PRIVATE JOURNAL" in p.text for p in pieces)
        genesis = [p.meta["reference"] for p in pieces if p.key.startswith("scripture:holy-bible")]
        # 5 verses, windows of 3 overlapping by one.
        assert genesis == ["Genesis 1:1-3", "Genesis 1:3-5"], genesis
        discourse_parts = [p for p in pieces if p.kind == "discourse"]
        assert len(discourse_parts) > 1
        assert all(len(p.text) <= si.DISCOURSE_MAX_CHARS + 200 for p in discourse_parts)
        assert si.index_path_for(env.conn) == env.tmp / "study_index.db"
        print("test_collect_pieces_covers_every_source_but_the_journal: PASSED")
    finally:
        env.close()


@_with_fake_works
def test_build_embeds_everything_and_search_ranks_by_meaning() -> None:
    env = _Env()
    try:
        result = env.build()
        assert result["ok"], result
        status = si.index_status(env.index_conn)
        assert status.complete and status.embedded == status.unique_texts, status
        assert status.model == "embed-a"
        assert env.server.requests[0]["auth"] == "Bearer sk-test"
        assert all(len(r["body"]["input"]) <= 4 for r in env.server.requests)
        assert "dimensions" not in env.server.requests[0]["body"]

        index = si.StudyIndex(env.index_conn)
        question = "hope for things which are not seen"
        hits = index.search(question, fake_embedding(question), limit=5)
        assert hits[0].meta.get("reference", "").startswith("Alma 32:21"), hits[0]
        assert hits[0].semantic_rank is not None and hits[0].keyword_rank is not None

        only_talks = index.search("faith", fake_embedding("faith"), kinds={"talk"})
        assert [h.meta["title"] for h in only_talks] == ["The Power of Faith"]
        only_bible = index.search("light", fake_embedding("light"), volume_slugs={"holy-bible"})
        assert only_bible and all(h.volume_slug == "holy-bible" for h in only_bible)

        keyword_only = index.search("nourished seed", None)
        assert keyword_only[0].kind == "note" and keyword_only[0].semantic_rank is None
        print("test_build_embeds_everything_and_search_ranks_by_meaning: PASSED")
    finally:
        env.close()


@_with_fake_works
def test_retry_after_and_backoff_recover() -> None:
    env = _Env()
    try:
        env.server.script = [("status", 429, 0), ("status", 503, 0)]
        result = env.build()
        assert result["ok"], result
        assert si.index_status(env.index_conn).complete
        print("test_retry_after_and_backoff_recover: PASSED")
    finally:
        env.close()


@_with_fake_works
def test_too_large_batches_are_halved() -> None:
    env = _Env(batch_size=8)
    try:
        env.server.too_large_over = 2
        result = env.build()
        assert result["ok"], result
        assert si.index_status(env.index_conn).complete
        assert max(len(r["body"]["input"]) for r in env.server.requests[-3:]) <= 2
        print("test_too_large_batches_are_halved: PASSED")
    finally:
        env.close()


@_with_fake_works
def test_auth_failure_stops_and_flags_api_key() -> None:
    env = _Env()
    try:
        env.server.script = [("status", 401, None)]
        result = env.build()
        assert result["ok"] is False and result["builder"].needs_api_key
        assert "fake 401" in result["message"]
        print("test_auth_failure_stops_and_flags_api_key: PASSED")
    finally:
        env.close()


@_with_fake_works
def test_cancel_then_resume_and_incremental_rebuild() -> None:
    env = _Env(batch_size=2)
    try:
        first = env.build(cancel_after=2)
        assert first["ok"] is False and first["message"] == ""
        partial = si.index_status(env.index_conn)
        assert 0 < partial.embedded < partial.unique_texts, partial

        env.server.requests.clear()
        second = env.build()
        assert second["ok"]
        sent = sum(len(r["body"]["input"]) for r in env.server.requests)
        assert sent == partial.unique_texts - partial.embedded, (sent, partial)

        # A new note is the only thing re-embedded next time; a deleted
        # one's piece disappears.
        env.conn.execute(
            "INSERT INTO notes (chapter_id, text) VALUES (1, 'Creation and light')"
        )
        env.conn.execute("UPDATE notes SET deleted_at = datetime('now') WHERE text LIKE 'The seed%'")
        env.conn.commit()
        env.server.requests.clear()
        third = env.build()
        assert third["ok"]
        assert [r["body"]["input"] for r in env.server.requests] == [
            ["My note on Genesis 1:\nCreation and light"]
        ]
        notes = env.index_conn.execute("SELECT text FROM pieces WHERE kind = 'note'").fetchall()
        assert [n["text"] for n in notes] == ["My note on Genesis 1:\nCreation and light"]
        print("test_cancel_then_resume_and_incremental_rebuild: PASSED")
    finally:
        env.close()


@_with_fake_works
def test_changing_model_or_dimensions_rebuilds_from_scratch() -> None:
    env = _Env()
    try:
        assert env.build(model="embed-a")["ok"]
        total = si.index_status(env.index_conn).unique_texts

        env.server.requests.clear()
        result = env.build(model="embed-b", dimensions=32)
        assert result["ok"] and result["builder"].model_changed
        assert sum(len(r["body"]["input"]) for r in env.server.requests) == total
        assert env.server.requests[0]["body"]["dimensions"] == 32
        assert si.recorded_model(env.index_conn) == ("embed-b", 32)
        print("test_changing_model_or_dimensions_rebuilds_from_scratch: PASSED")
    finally:
        env.close()


def test_split_discourse_limits() -> None:
    giant_paragraph = " ".join(f"Sentence number {i} is here." for i in range(400))
    parts = si.split_discourse("Short opening.\n\n" + giant_paragraph + "\n\nShort close.")
    assert all(len(p) <= si.DISCOURSE_MAX_CHARS for p in parts)
    assert "Short opening." in parts[0] and "Short close." in parts[-1]
    no_spaces = "x" * 5000
    assert all(len(p) <= si.DISCOURSE_MAX_CHARS for p in si.split_discourse(no_spaces))
    print("test_split_discourse_limits: PASSED")


@_with_fake_works
def test_not_implemented_fails_fast_without_retrying() -> None:
    env = _Env()
    try:
        env.server.script = [("status", 501, None)]
        result = env.build()
        assert result["ok"] is False
        assert "may not offer embeddings" in result["message"], result["message"]
        assert len(env.server.requests) == 1
        print("test_not_implemented_fails_fast_without_retrying: PASSED")
    finally:
        env.close()


if __name__ == "__main__":
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    test_split_discourse_limits()
    test_collect_pieces_covers_every_source_but_the_journal()
    test_build_embeds_everything_and_search_ranks_by_meaning()
    test_retry_after_and_backoff_recover()
    test_too_large_batches_are_halved()
    test_auth_failure_stops_and_flags_api_key()
    test_not_implemented_fails_fast_without_retrying()
    test_cancel_then_resume_and_incremental_rebuild()
    test_changing_model_or_dimensions_rebuilds_from_scratch()
    print("All study index tests passed.")

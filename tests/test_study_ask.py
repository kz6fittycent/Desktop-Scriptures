"""Standalone test script for src/scriptures/study_ask.py - AI search
grounded in the study index. No test framework (see tests/test_ask.py's
own docstring for why).

Builds a small study index with tests/test_study_index.py's fixtures,
then runs StudyQuestionAsker against a local HTTP server that answers both
/embeddings (the same bag-of-words fake) and /chat/completions (a
scripted reply per test).

Run directly:

    python3 tests/test_study_ask.py
"""

from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer  # noqa: E402

from scriptures import study_ask, study_index as si  # noqa: E402
from scriptures.ai_client import AiConfig  # noqa: E402
from test_study_index import _Env, _with_fake_works, fake_embedding  # noqa: E402


class ChatAndEmbeddingsServer:
    """`chat_reply` is the assistant message content to send back (or an
    (http_status, body) tuple to fail with)."""

    def __init__(self):
        self.chat_reply: object = "[]"
        self.chat_requests: list[dict] = []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, status: int, payload: dict) -> None:
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path.endswith("/embeddings"):
                    data = [{"index": i, "embedding": fake_embedding(t)} for i, t in enumerate(body["input"])]
                    self._send(200, {"data": data})
                    return
                server.chat_requests.append(body)
                if isinstance(server.chat_reply, tuple):
                    status, payload = server.chat_reply
                    self._send(status, payload)
                    return
                self._send(200, {"choices": [{"message": {"content": server.chat_reply}}]})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_address[1]}/v1"

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def _ask(env: _Env, server: ChatAndEmbeddingsServer, questions: list[str]) -> dict:
    index = si.StudyIndex(env.index_conn)
    config = AiConfig(server.base_url, "", "chat-model")
    asker = study_ask.StudyQuestionAsker(
        env.conn, index, si.index_path_for(env.conn), config,
        AiConfig(server.base_url, "", "embed-a"), None, questions,
    )
    result: dict = {}
    loop = QEventLoop()
    asker.succeeded.connect(lambda results, note: (result.update(results=results, note=note), loop.quit()))
    asker.failed.connect(lambda message, key: (result.update(error=message, key=key), loop.quit()))
    QTimer.singleShot(15_000, loop.quit)
    loop.exec()
    return result


def test_parse_selection() -> None:
    assert study_ask.parse_selection("[3, 1, 3, 9]", 5) == [2, 0]
    assert study_ask.parse_selection('Sure! Here you go: ["2", 4]', 5) == [1, 3]
    assert study_ask.parse_selection("[]", 5) == []
    assert study_ask.parse_selection("I can't help with that.", 5) is None
    assert study_ask.parse_selection("[42, 99]", 5) is None  # nothing from the list
    assert study_ask.parse_selection(str(list(range(1, 30))), 30) == list(range(10))
    print("test_parse_selection: PASSED")


def test_follow_up_filters() -> None:
    d = study_ask.detect_filters
    assert d(["how do I cope with grief", "just the Book of Mormon"]) == ({"scripture"}, {"book-of-mormon"})
    assert d(["grief", "only D&C please"]) == ({"scripture"}, {"doctrine-and-covenants"})
    assert d(["grief", "what about the JST"]) == ({"scripture"}, {"inspired-version"})
    assert d(["grief", "New Testament only"]) == ({"scripture"}, {"holy-bible", "inspired-version"})
    assert d(["grief", "any conference talks?"]) == ({"talk"}, None)
    assert d(["grief", "Ensign articles"]) == ({"article"}, None)
    # The first question is never a filter - it may be *about* the book.
    assert d(["how was the Book of Mormon translated"]) == (None, None)
    # The latest follow-up that names something wins.
    assert d(["grief", "just the Bible", "actually the Book of Mormon"]) == ({"scripture"}, {"book-of-mormon"})
    assert d(["grief", "the ones about hope"]) == (None, None)
    print("test_follow_up_filters: PASSED")


def test_retrieval_query_and_prompt() -> None:
    # A pure filter follow-up isn't searched for; a real refinement is.
    assert study_ask.retrieval_query(["grief", "just the Book of Mormon"]) == "grief"
    assert study_ask.retrieval_query(["grief", "the ones about hope"]) == "grief the ones about hope"
    hit = si.SearchHit(1, "k", "scripture", "Alma 32:21-23\nFaith is not...", "book-of-mormon", 2,
                       {"reference": "Alma 32:21-23"}, 1.0, 1, 1)
    messages = study_ask.selection_messages(["what is faith", "only Alma"], [hit])
    assert messages[0]["role"] == "system"
    assert "Original question: what is faith\nRefinement: only Alma" in messages[1]["content"]
    assert "[1] (Scripture) Alma 32:21-23 - Faith is not..." in messages[1]["content"]
    print("test_retrieval_query_and_prompt: PASSED")


@_with_fake_works
def test_model_choice_orders_results_and_text_comes_from_the_database() -> None:
    env = _Env()
    server = ChatAndEmbeddingsServer()
    try:
        assert env.build()["ok"]
        server.chat_reply = "[2, 1]"
        result = _ask(env, server, ["faith hope things not seen"])
        assert result.get("note") == "", result
        results = result["results"]
        assert len(results) == 2
        prompt = server.chat_requests[0]["messages"][1]["content"]
        # The model's #2 then #1, in that order.
        listed = [line for line in prompt.splitlines() if line.startswith("[")]
        assert results[0].title in listed[1] or results[0].title.split(":")[0] in listed[1]
        for r in results:
            if r.kind == "scripture":
                verse_text = env.conn.execute(
                    "SELECT text FROM verses WHERE chapter_id = ? ORDER BY verse_number", (r.chapter_id,)
                ).fetchall()
                assert any(v[0][:30] in r.detail for v in verse_text), r.detail
        print("test_model_choice_orders_results_and_text_comes_from_the_database: PASSED")
    finally:
        server.close()
        env.close()


@_with_fake_works
def test_falls_back_to_index_order_when_the_model_reply_is_unusable() -> None:
    env = _Env()
    server = ChatAndEmbeddingsServer()
    try:
        assert env.build()["ok"]
        for reply in ("Here are some great verses about faith!", (500, {"error": "boom"})):
            server.chat_reply = reply
            result = _ask(env, server, ["faith"])
            assert result["results"], result
            assert result["note"].startswith("Showing the study index's best matches"), result["note"]
        print("test_falls_back_to_index_order_when_the_model_reply_is_unusable: PASSED")
    finally:
        server.close()
        env.close()


@_with_fake_works
def test_auth_failure_is_reported() -> None:
    env = _Env()
    server = ChatAndEmbeddingsServer()
    try:
        assert env.build()["ok"]
        server.chat_reply = (401, {"error": {"message": "bad key"}})
        result = _ask(env, server, ["faith"])
        assert result.get("key") is True, result
        print("test_auth_failure_is_reported: PASSED")
    finally:
        server.close()
        env.close()


@_with_fake_works
def test_every_kind_resolves_to_something_clickable() -> None:
    env = _Env()
    try:
        assert env.build()["ok"]
        index = si.StudyIndex(env.index_conn)
        seen = {}
        for query in ("faith", "prayer revelation", "seed nourished", "gathering israel"):
            for hit in index.search(query, fake_embedding(query), limit=20):
                result = study_ask.to_result(env.conn, hit)
                if result is not None:
                    seen.setdefault(hit.kind, result)
        assert {"scripture", "discourse", "topic", "talk", "note"} <= set(seen), set(seen)
        assert seen["talk"].url and seen["topic"].topic_id and seen["discourse"].chapter_id
        assert seen["note"].chapter_id and seen["scripture"].chapter_id
        print("test_every_kind_resolves_to_something_clickable: PASSED")
    finally:
        env.close()


if __name__ == "__main__":
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    test_parse_selection()
    test_follow_up_filters()
    test_retrieval_query_and_prompt()
    test_model_choice_orders_results_and_text_comes_from_the_database()
    test_falls_back_to_index_order_when_the_model_reply_is_unusable()
    test_auth_failure_is_reported()
    test_every_kind_resolves_to_something_clickable()
    print("All study ask tests passed.")

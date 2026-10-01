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
    """`chat_reply` answers the candidate-selection request (or an
    (http_status, body) tuple fails it); `topic_reply` answers the topic
    request that comes first (see study_ask.TOPIC_PROMPT) - "[]", no
    topic, by default. `chat_requests` records selection requests only."""

    def __init__(self):
        self.chat_reply: object = "[]"
        self.topic_reply: object = "[]"
        self.chat_requests: list[dict] = []
        self.topic_requests: list[dict] = []
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
                is_topic = body["messages"][0]["content"] == study_ask.TOPIC_PROMPT
                (server.topic_requests if is_topic else server.chat_requests).append(body)
                reply = server.topic_reply if is_topic else server.chat_reply
                if isinstance(reply, tuple):
                    status, payload = reply
                    self._send(status, payload)
                    return
                self._send(200, {"choices": [{"message": {"content": reply}}]})

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
        result = _ask(env, server, ["the power of faith"])
        assert result.get("note") == "", result
        results = result["results"]
        # The model's two picks (both scripture - the Standard Works group
        # is listed first), plus the always-shown talk "The Power of Faith"
        # (its title shares "power" and "faith" with the question). The
        # article, "Gathering Israel", shares nothing, so isn't forced in.
        assert [r.kind for r in results] == ["scripture", "scripture", "talk"], results
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


@_with_fake_works
def test_candidates_cover_every_group_and_results_follow_tier_order() -> None:
    env = _Env()
    server = ChatAndEmbeddingsServer()
    try:
        assert env.build()["ok"]
        index = si.StudyIndex(env.index_conn)
        query = "the power of faith"
        hits = study_ask.gather_candidates(index, [query], query, fake_embedding(query))
        kinds = [h.kind for h in hits]
        # Both talk cards are present even though scripture text matches
        # "faith" far more strongly.
        assert kinds.count("talk") == 1 and kinds.count("article") == 1, kinds
        assert "scripture" in kinds, kinds
        assert {"discourse", "topic"} & set(kinds), kinds

        # The model picks everything in reverse; display follows the tiers.
        server.chat_reply = json.dumps(list(range(len(hits), 0, -1)))
        result = _ask(env, server, [query])
        shown = [r.kind for r in result["results"]]
        tiers = {"scripture": 0, "talk": 1, "article": 2}
        ranks = [tiers.get(k, 3) for k in shown]
        assert ranks == sorted(ranks), shown

        # The model picks only scripture: the talk and article are still
        # shown (the fixtures have one of each).
        scripture_only = [i + 1 for i, h in enumerate(hits) if h.kind == "scripture"]
        picked = scripture_only[:3]
        server.chat_reply = json.dumps(picked)
        result = _ask(env, server, [query])
        shown = [r.kind for r in result["results"]]
        assert shown[: len(picked)] == ["scripture"] * len(picked), shown
        assert "talk" in shown and "article" not in shown, shown
        # A question sharing two words with the article's title gets it too.
        result = _ask(env, server, ["the power of faith in gathering israel"])
        shown = [r.kind for r in result["results"]]
        assert "talk" in shown and "article" in shown, shown
        assert shown.index("talk") < shown.index("article"), shown
        # ...but not after a follow-up that asked for scripture only.
        result = _ask(env, server, [query, "just the Bible"])
        assert "talk" not in [r.kind for r in result["results"]]

        fallback = study_ask.fallback_hits(hits)
        assert [study_ask.tier(h) for h in fallback] == sorted(study_ask.tier(h) for h in fallback)
        assert {study_ask.tier(h) for h in fallback} >= {0, 1, 2}
        print("test_candidates_cover_every_group_and_results_follow_tier_order: PASSED")
    finally:
        server.close()
        env.close()


def test_snippets_show_the_question_words_the_opening_hides() -> None:
    text = (
        "And it came to pass that the Lord did warn me, that I, Nephi, should depart from them "
        "and flee into the wilderness, and all those who would go with me. Wherefore, it came "
        "to pass that I, Nephi, did take my family, and also Zoram and his family, and Sam, "
        "mine elder brother and his family, and Jacob and Joseph, my younger brethren, and also "
        "my sisters, and all those who would go with me."
    )
    keywords = study_ask.snippet_keywords("Where are Nephi's sisters mentioned?")
    assert keywords[:2] == ["nephi", "sisters"], keywords
    plain = study_ask._snippet(text, 220)
    assert "sisters" not in plain and plain.startswith("And it came")
    centered = study_ask._snippet(text, 220, keywords)
    assert "my sisters" in centered and centered.startswith("..."), centered
    # Nothing hidden (or nothing matching): the opening, as before.
    assert study_ask._snippet(text, 220, ["nephi"]) == plain
    assert study_ask._snippet(text, 220, ["zarahemla"]) == plain
    # The prompt uses the centered form.
    hit = si.SearchHit(1, "k", "scripture", f"2 Nephi 5:5-7\n{text}", "book-of-mormon", 3,
                       {"reference": "2 Nephi 5:5-7"}, 1.0, 1, 1)
    prompt = study_ask.selection_messages(["Where are Nephi's sisters mentioned?"], [hit])[1]["content"]
    assert "my sisters" in prompt
    print("test_snippets_show_the_question_words_the_opening_hides: PASSED")


def test_forced_talks_need_two_shared_words() -> None:
    def talk(title):
        return si.SearchHit(1, "k", "talk", f'General Conference: "{title}" - A. Speaker', None, None, {}, 1.0, 1, 1)
    # Possessives normalize ("Mark's" -> "mark").
    assert study_ask.snippet_keywords("What was Mark's relationship to Christ?") == ["mark", "relationship", "christ"]
    assert study_ask._shares_a_word(talk("Eternal Marriage"), "eternal marriage")
    assert not study_ask._shares_a_word(talk("A Plea to My Sisters"), "Where are Nephi's sisters mentioned?")
    assert study_ask._shares_a_word(talk("The Book of Mormon—a Book from God"), "how can I know the Book of Mormon is true")
    assert study_ask._shares_a_word(talk("Faith"), "faith")  # a one-word question needs one
    assert not study_ask._shares_a_word(talk("Where Your Treasure Is"), "Who is Teancum")
    print("test_forced_talks_need_two_shared_words: PASSED")


def test_parse_topic_choice() -> None:
    topics = [(10, "Faith"), (20, "Hope"), (30, "Charity"), (40, "Prayer")]
    assert study_ask.parse_topic_choice("[3]", topics) == [30]
    # It sometimes lists more than asked; at most KEY_TOPICS are kept.
    assert study_ask.parse_topic_choice("[1, 2, 3, 4]", topics) == [10, 20, 30][: study_ask.KEY_TOPICS]
    assert study_ask.parse_topic_choice("[]", topics) == []
    assert study_ask.parse_topic_choice("Faith, I think", topics) is None
    print("test_parse_topic_choice: PASSED")


@_with_fake_works
def test_key_passages_from_the_chosen_topic_join_the_candidates() -> None:
    env = _Env()
    server = ChatAndEmbeddingsServer()
    try:
        # A key passage the question's words would never find: Faith's
        # (fixture) key passage is Alma 32:28, about planting a seed.
        topic_id = env.conn.execute("SELECT id FROM topics WHERE slug = 'faith'").fetchone()[0]
        env.conn.execute(
            "INSERT INTO topic_key_verses (topic_id, volume_slug, reference, sort_order) "
            "VALUES (?, 'book-of-mormon', 'Alma 32:28', 1)",
            (topic_id,),
        )
        env.conn.commit()
        assert env.build()["ok"]
        index = si.StudyIndex(env.index_conn)
        question = "light and darkness"

        hits = study_ask.gather_candidates(index, [question], question, None, env.conn, [topic_id])
        keys = [h for h in hits if h.meta.get("key_topic")]
        assert [h.meta["reference"] for h in keys] == ["Alma 32:28"], [h.meta for h in hits]
        assert keys[0].chapter_id == 2 and keys[0].volume_slug == "book-of-mormon"
        prompt = study_ask.selection_messages([question], hits)[1]["content"]
        assert "(Scripture - a key passage on Faith) Alma 32:28" in prompt, prompt
        # No topics, no key passages.
        assert not [h for h in study_ask.gather_candidates(index, [question], question, None, env.conn, [])
                    if h.meta.get("key_topic")]

        # End to end: the topic request is made first, listing the topics.
        # (By meaning, this tiny fixture's search already returns every
        # scripture window - including Alma 32:28's - so the key passage is
        # correctly skipped there as a duplicate.)
        server.topic_reply = "[1]"
        server.chat_reply = "[1]"
        result = _ask(env, server, [question])
        assert result.get("results"), result
        assert "1. Faith" in server.topic_requests[0]["messages"][1]["content"]
        listed = server.chat_requests[0]["messages"][1]["content"]
        assert "Alma 32:2" in listed  # the passage is offered either way
        print("test_key_passages_from_the_chosen_topic_join_the_candidates: PASSED")
    finally:
        server.close()
        env.close()


if __name__ == "__main__":
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    test_parse_selection()
    test_follow_up_filters()
    test_parse_topic_choice()
    test_forced_talks_need_two_shared_words()
    test_snippets_show_the_question_words_the_opening_hides()
    test_retrieval_query_and_prompt()
    test_model_choice_orders_results_and_text_comes_from_the_database()
    test_falls_back_to_index_order_when_the_model_reply_is_unusable()
    test_auth_failure_is_reported()
    test_every_kind_resolves_to_something_clickable()
    test_candidates_cover_every_group_and_results_follow_tier_order()
    test_key_passages_from_the_chosen_topic_join_the_candidates()
    print("All study ask tests passed.")

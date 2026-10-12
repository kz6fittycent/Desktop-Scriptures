"""Standalone test script for src/scriptures/ai_client.py's ChatRequest -
the one way the app asks a chat model anything - for both providers. No
test framework (see tests/test_ask.py's docstring); a QCoreApplication
event loop runs each request.

- OpenAI-compatible: against a tiny local HTTP server, including one that
  rejects structured output (the request must be retried without it).
- Anthropic: the SDK client is replaced with a stand-in (no network, no
  key needed); the SDK's own exception classes are used. Skipped when the
  `anthropic` package isn't installed.

Run directly:

    python3 tests/test_ai_client.py
"""

from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QTimer  # noqa: E402

from scriptures import ai_client  # noqa: E402

APP = QCoreApplication.instance() or QCoreApplication([])
MESSAGES = [{"role": "system", "content": "Pick fruit."}, {"role": "user", "content": "1. apple 2. car"}]


def _run(request: ai_client.ChatRequest) -> tuple:
    result = []
    request.finished.connect(lambda content, message, needs_key: (result.append((content, message, needs_key)), APP.quit()))
    QTimer.singleShot(10_000, APP.quit)
    APP.exec()
    assert result, "ChatRequest never finished"
    return result[0]


class _Server(BaseHTTPRequestHandler):
    rejects_schema = False
    bodies: list = []

    def do_POST(self) -> None:  # noqa: N802 (http.server naming)
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Server.bodies.append(body)
        if _Server.rejects_schema and "response_format" in body:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"error": "response_format not supported"}')
            return
        reply = {"choices": [{"message": {"content": '{"numbers": [1]}'}}]}
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(reply).encode())

    def log_message(self, *_args) -> None:
        pass


def _serve() -> str:
    server = HTTPServer(("127.0.0.1", 0), _Server)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}/v1"


def test_openai_structured_output_and_fallback() -> None:
    url = _serve()
    config = ai_client.AiConfig(url, "", "local-model")
    _Server.bodies = []
    content, message, _ = _run(ai_client.ChatRequest(config, MESSAGES, schema=ai_client.numbers_schema(2)))
    assert content == '{"numbers": [1]}', (content, message)
    schema = _Server.bodies[0]["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["numbers"]["items"]["enum"] == [1, 2]

    # A server that rejects structured output: asked again without it, and
    # not offered it again this session.
    url = _serve()
    config = ai_client.AiConfig(url, "", "local-model")
    _Server.rejects_schema, _Server.bodies = True, []
    content, _, _ = _run(ai_client.ChatRequest(config, MESSAGES, schema=ai_client.numbers_schema(2)))
    assert content == '{"numbers": [1]}'
    assert ["response_format" in b for b in _Server.bodies] == [True, False]
    _Server.bodies = []
    _run(ai_client.ChatRequest(config, MESSAGES, schema=ai_client.numbers_schema(2)))
    assert ["response_format" in b for b in _Server.bodies] == [False]
    _Server.rejects_schema = False
    print("test_openai_structured_output_and_fallback: PASSED")


def test_provider_detection_and_embeddings() -> None:
    claude = ai_client.AiConfig("https://api.anthropic.com", "k", "")
    assert ai_client.is_anthropic(claude)
    assert ai_client.is_anthropic(ai_client.AiConfig("https://api.anthropic.com/v1/", "k", ""))
    assert not ai_client.is_anthropic(ai_client.AiConfig("https://notanthropic.com.example.org/v1", "", ""))
    # Anthropic has no embeddings: "same as chat" means none, never sends
    # the Anthropic key elsewhere.
    assert ai_client.embeddings_config(claude, "", "", "embeddinggemma").base_url == ""
    local = ai_client.embeddings_config(claude, "http://localhost:11434/v1", "", "embeddinggemma")
    assert local.base_url == "http://localhost:11434/v1" and local.api_key == ""
    print("test_provider_detection_and_embeddings: PASSED")


def test_anthropic_params() -> None:
    config = ai_client.AiConfig(ai_client.ANTHROPIC_BASE_URL, "k", "")
    params = ai_client.anthropic_chat_params(config, MESSAGES, ai_client.numbers_schema(2))
    assert params["model"] == ai_client.RECOMMENDED_ANTHROPIC_MODEL
    assert params["system"] == "Pick fruit." and [m["role"] for m in params["messages"]] == ["user"]
    assert params["output_config"]["effort"] == "low"
    assert params["output_config"]["format"]["type"] == "json_schema"
    assert params["fallbacks"] == "default" and params["betas"] == ["server-side-fallback-2026-07-01"]
    assert "temperature" not in params
    # An older model: no effort (it would be rejected), no fallbacks.
    older = ai_client.anthropic_chat_params(ai_client.AiConfig(config.base_url, "k", "claude-haiku-4-5"), MESSAGES, None)
    assert "output_config" not in older and "fallbacks" not in older and "betas" not in older
    print("test_anthropic_params: PASSED")


def _response(text: str, stop_reason: str = "end_turn"):
    blocks = [SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)] if text else []
    return SimpleNamespace(stop_reason=stop_reason, content=blocks)


class _StubMessages:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def create(self, **params):
        self.calls.append(params)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _stub_client(plain, beta):
    return SimpleNamespace(messages=plain, beta=SimpleNamespace(messages=beta))


def test_anthropic_requests() -> None:
    try:
        import anthropic
        import httpx2
    except ImportError:
        print("test_anthropic_requests: SKIPPED (anthropic not installed)")
        return
    original = ai_client._anthropic_client
    try:
        claude = ai_client.AiConfig(ai_client.ANTHROPIC_BASE_URL, "k", "claude-opus-5-5")
        plain, beta = _StubMessages([]), _StubMessages([_response('{"numbers": [1]}')])
        ai_client._anthropic_client = lambda _config: _stub_client(plain, beta)
        content, _, _ = _run(ai_client.ChatRequest(claude, MESSAGES, schema=ai_client.numbers_schema(2)))
        assert content == '{"numbers": [1]}' and len(beta.calls) == 1 and not plain.calls  # fallbacks -> beta

        beta = _StubMessages([_response("", "refusal")])
        ai_client._anthropic_client = lambda _config: _stub_client(plain, beta)
        content, message, _ = _run(ai_client.ChatRequest(claude, MESSAGES))
        assert content is None and "declined" in message

        request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")

        def error(cls, status):
            return cls("bad", response=httpx2.Response(status, request=request), body=None)

        # Structured output rejected (an older model): asked again without it.
        old = ai_client.AiConfig(ai_client.ANTHROPIC_BASE_URL, "k", "claude-haiku-4-5")
        plain = _StubMessages([error(anthropic.BadRequestError, 400), _response("[1]")])
        ai_client._anthropic_client = lambda _config: _stub_client(plain, beta)
        content, _, _ = _run(ai_client.ChatRequest(old, MESSAGES, schema=ai_client.numbers_schema(2)))
        assert content == "[1]" and "output_config" in plain.calls[0] and "output_config" not in plain.calls[1]

        beta = _StubMessages([error(anthropic.AuthenticationError, 401)])
        ai_client._anthropic_client = lambda _config: _stub_client(plain, beta)
        content, message, needs_key = _run(ai_client.ChatRequest(claude, MESSAGES))
        assert content is None and needs_key and "key" in message
    finally:
        ai_client._anthropic_client = original
    print("test_anthropic_requests: PASSED")


if __name__ == "__main__":
    test_openai_structured_output_and_fallback()
    test_provider_detection_and_embeddings()
    test_anthropic_params()
    test_anthropic_requests()
    print("All AI client tests passed.")

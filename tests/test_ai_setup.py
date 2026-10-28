"""Standalone test script for src/scriptures/ai_setup.py and the AI Setup
Wizard's resulting settings (ui/ai_setup_wizard.py). No test framework
(see tests/test_ask.py's own docstring for why).

Local server detection runs against real local HTTP servers on random
ports standing in for Ollama and an inference snap, plus a port nothing
listens on.

Run directly:

    python3 tests/test_ai_setup.py
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scriptures import ai_setup  # noqa: E402
from scriptures.ai_setup import FoundServer, KnownServer, LocalServerScan  # noqa: E402


def _models_server(model_ids: list[str]) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):  # noqa: N802
            payload = json.dumps(
                {"object": "list", "data": [{"id": m, "object": "model"} for m in model_ids]}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait(signal_owner_signal, timeout_ms: int = 10_000):
    result = {}
    loop = QEventLoop()
    signal_owner_signal.connect(lambda *args: (result.setdefault("args", args), loop.quit()))
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    return result.get("args")


def test_model_classification_and_ordering() -> None:
    for name in ("embeddinggemma:latest", "nomic-embed-text", "text-embedding-3-small",
                 "mxbai-embed-large", "bge-m3", "all-minilm"):
        assert ai_setup.is_embedding_model(name), name
    for name in ("gemma3-4b", "gpt-4o-mini", "qwen3-coder:latest", "llama3.2"):
        assert not ai_setup.is_embedding_model(name), name
    chat, embedding = ai_setup.split_models(
        ["qwen3-coder:latest", "embeddinggemma:latest", "llama3.2", "gemma3:4b"]
    )
    assert chat == ["llama3.2", "gemma3:4b", "qwen3-coder:latest"], chat
    assert embedding == ["embeddinggemma:latest"]
    print("test_model_classification_and_ordering: PASSED")


def test_parse_models_tolerates_odd_responses() -> None:
    body = b'{"models": [{"name": "x"}], "object": "list", "data": [{"id": "gemma3-4b"}]}'
    assert ai_setup.parse_models(body) == ["gemma3-4b"]
    assert ai_setup.parse_models(b"not json") == []
    assert ai_setup.parse_models(b'{"data": "nope"}') == []
    print("test_parse_models_tolerates_odd_responses: PASSED")


def test_suggested_chat_server_prefers_general_models() -> None:
    coder_only = FoundServer("Ollama", "http://a/v1", ["qwen3-coder:latest", "embeddinggemma"], True)
    general = FoundServer("Snap", "http://b/v1", ["gemma3-4b"])
    embed_only = FoundServer("Other", "http://c/v1", ["nomic-embed-text"])
    assert ai_setup.suggested_chat_server([coder_only, general]) is general
    assert ai_setup.suggested_chat_server([coder_only, embed_only]) is coder_only
    assert ai_setup.suggested_chat_server([embed_only]) is None
    print("test_suggested_chat_server_prefers_general_models: PASSED")


def test_local_scan_finds_running_servers_only() -> None:
    ollama = _models_server(["qwen3-coder:latest", "embeddinggemma:latest"])
    snap = _models_server(["gemma3-4b"])
    try:
        servers = (
            KnownServer("Ollama", f"http://127.0.0.1:{ollama.server_address[1]}/v1", is_ollama=True),
            KnownServer("Nothing here", f"http://127.0.0.1:{_closed_port()}/v1"),
            KnownServer("Snap", f"http://127.0.0.1:{snap.server_address[1]}/v1"),
        )
        scan = LocalServerScan(servers)
        args = _wait(scan.finished)
        assert args is not None, "scan never finished"
        found = args[0]
        assert [f.name for f in found] == ["Ollama", "Snap"], found
        assert found[0].is_ollama and found[0].embedding_models == ["embeddinggemma:latest"]
        assert found[1].chat_models == ["gemma3-4b"]
        print("test_local_scan_finds_running_servers_only: PASSED")
    finally:
        ollama.shutdown()
        snap.shutdown()


def test_wizard_results_for_snap_chat_and_ollama_embeddings() -> None:
    """Drives the real wizard against stand-ins for this exact setup: an
    inference snap for chat, Ollama for embeddings."""
    from scriptures.ui.ai_setup_wizard import AiSetupWizard

    ollama = _models_server(["qwen3-coder:latest", "embeddinggemma:latest"])
    snap = _models_server(["gemma3-4b"])
    original = ai_setup.KNOWN_LOCAL_SERVERS
    ollama_url = f"http://127.0.0.1:{ollama.server_address[1]}/v1"
    snap_url = f"http://127.0.0.1:{snap.server_address[1]}/v1"
    ai_setup.KNOWN_LOCAL_SERVERS = (
        KnownServer("Ollama", ollama_url, is_ollama=True),
        KnownServer("Snap", snap_url),
    )
    try:
        wizard = AiSetupWizard({})
        wizard.show()
        loop = QEventLoop()
        QTimer.singleShot(1500, loop.quit)
        loop.exec()
        for _ in range(3):
            wizard.next()
            QApplication.processEvents()
        assert (wizard.base_url, wizard.model) == (snap_url, "gemma3-4b"), (wizard.base_url, wizard.model)
        assert wizard.embeddings_base_url == ollama_url
        assert wizard.embedding_model == "embeddinggemma:latest"
        assert wizard.api_key == "" and wizard.embeddings_api_key == ""
        assert wizard.build_now
        print("test_wizard_results_for_snap_chat_and_ollama_embeddings: PASSED")
    finally:
        ai_setup.KNOWN_LOCAL_SERVERS = original
        ollama.shutdown()
        snap.shutdown()


def _openrouter_server(chat_ids: list[str], embedding_ids: list[str]) -> ThreadingHTTPServer:
    """OpenRouter's shape: /models lists chat models only, and embedding
    models are listed separately at /embeddings/models."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):  # noqa: N802
            ids = embedding_ids if self.path.endswith("/embeddings/models") else chat_ids
            payload = json.dumps({"data": [{"id": m} for m in ids]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_openrouter_study_index_models() -> None:
    """OpenRouter is offered for the study index, suggests OpenAI's small
    embedding model, and its Refresh lists the separate embedding-model
    list - including models with no "embed" in the name."""
    import dataclasses

    from scriptures.ui.ai_setup_wizard import AiSetupWizard

    openrouter = ai_setup.hosted_provider("openrouter")
    assert openrouter.offers_embeddings
    assert openrouter.embedding_model == "openai/text-embedding-3-small"
    assert openrouter.embedding_dimensions == "512"
    for key in ("anthropic", "groq"):
        assert not ai_setup.hosted_provider(key).offers_embeddings, key

    embedding_ids = ["openai/text-embedding-3-small", "baai/bge-m3", "voyageai/voyage-4"]
    server = _openrouter_server(["openai/gpt-5", "meta-llama/llama-4"], embedding_ids)
    stand_in_url = f"http://127.0.0.1:{server.server_address[1]}/api/v1"
    original_providers, original_servers = ai_setup.HOSTED_PROVIDERS, ai_setup.KNOWN_LOCAL_SERVERS
    ai_setup.HOSTED_PROVIDERS = tuple(
        dataclasses.replace(p, base_url=stand_in_url) if p.key == "openrouter" else p
        for p in original_providers
    )
    ai_setup.KNOWN_LOCAL_SERVERS = ()
    try:
        wizard = AiSetupWizard({})
        page = wizard.embeddings_page
        page.initializePage()
        page._cards.select("openrouter")
        QApplication.processEvents()
        assert page.url() == stand_in_url
        assert page.model() == "openai/text-embedding-3-small"
        assert page.dimensions() == "512"

        page._key.setText("test-key")
        page._list_models()
        assert _wait(page._lister.finished) is not None, "model list never arrived"
        listed = [page._model.itemText(i) for i in range(page._model.count())]
        assert listed == embedding_ids, listed
        print("test_openrouter_study_index_models: PASSED")
    finally:
        ai_setup.HOSTED_PROVIDERS, ai_setup.KNOWN_LOCAL_SERVERS = original_providers, original_servers
        server.shutdown()


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    test_model_classification_and_ordering()
    test_parse_models_tolerates_odd_responses()
    test_suggested_chat_server_prefers_general_models()
    test_local_scan_finds_running_servers_only()
    test_wizard_results_for_snap_chat_and_ollama_embeddings()
    test_openrouter_study_index_models()
    print("All AI setup tests passed.")

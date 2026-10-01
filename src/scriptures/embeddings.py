"""Embeddings over the user's own AI endpoint (OpenAI-compatible
POST .../embeddings - see ai_client.py for the overall bring-your-own-
endpoint design), and the background builder that fills the study index
with them (see study_index.py).

All network work is asynchronous on Qt's own event loop
(QNetworkAccessManager), the same way ask.py's QuestionAsker works, so
the UI stays responsive without any threads. The builder persists every
batch as soon as it arrives, so cancelling - or closing the app - loses
at most one in-flight batch, and the next build resumes from there.

Transient failures (HTTP 429 rate limiting, 5xx, timeouts, a dropped
connection) are retried with backoff, honoring a Retry-After header when
the server sends one. A 400 on a multi-text batch is treated as "this
batch is too big for this server" and retried as two halves, down to a
single text, before giving up - local servers in particular vary widely
in how much they accept per request.
"""

from __future__ import annotations

import json
import sqlite3

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from scriptures import study_index
from scriptures.ai_client import AUTH_ERRORS, AiConfig, build_request

DEFAULT_BATCH_SIZE = 64
MAX_RETRIES = 6
MAX_BACKOFF_SECONDS = 60.0
REQUEST_TIMEOUT_MS = 120_000

_RETRYABLE_NETWORK_ERRORS = (
    QNetworkReply.NetworkError.TimeoutError,
    QNetworkReply.NetworkError.OperationCanceledError,  # transfer timeout surfaces as this
    QNetworkReply.NetworkError.RemoteHostClosedError,
    QNetworkReply.NetworkError.TemporaryNetworkFailureError,
    QNetworkReply.NetworkError.NetworkSessionFailedError,
    QNetworkReply.NetworkError.ConnectionRefusedError,
    QNetworkReply.NetworkError.ProxyTimeoutError,
)


def build_payload(model: str, texts: list[str], dimensions: int | None) -> bytes:
    payload: dict = {"model": model, "input": texts}
    # Only sent when the user asked for it - it's an OpenAI extension
    # (text-embedding-3-*), and not every compatible server accepts it.
    if dimensions:
        payload["dimensions"] = dimensions
    return json.dumps(payload).encode("utf-8")


def parse_response(body: bytes, expected: int) -> list[list[float]]:
    """The standard {"data": [{"index": i, "embedding": [...]}, ...]}
    shape, put back in input order (servers aren't required to keep it).
    Raises ValueError for anything else."""
    try:
        data = json.loads(body)["data"]
        ordered = sorted(data, key=lambda item: item.get("index", 0))
        vectors = [item["embedding"] for item in ordered]
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("The endpoint's response wasn't a list of embeddings.") from exc
    if len(vectors) != expected or not all(isinstance(v, list) and v for v in vectors):
        raise ValueError(
            f"Asked for {expected} embedding(s) but the endpoint returned {len(vectors)}."
        )
    return vectors


def _retry_after_seconds(reply: QNetworkReply) -> float | None:
    raw = bytes(reply.rawHeader("Retry-After")).decode("ascii", "ignore").strip()
    try:
        return max(0.0, float(raw)) if raw else None
    except ValueError:
        return None  # an HTTP-date form - fall back to our own backoff


class EmbeddingRequest(QObject):
    """One POST .../embeddings for a list of texts.

    `succeeded(vectors)` or `failed(message, kind, retry_after)` fires
    exactly once. `kind` is "retry" (transient - worth trying again),
    "too_large" (HTTP 400/413/422 - possibly too much input in one
    request), "auth" (missing/wrong API key), or "fatal". `retry_after`
    is the server's Retry-After in seconds, or -1 if it gave none."""

    succeeded = Signal(list)
    failed = Signal(str, str, float)

    def __init__(
        self,
        config: AiConfig,
        model: str,
        texts: list[str],
        dimensions: int | None = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._expected = len(texts)
        self._manager = QNetworkAccessManager(self)
        request = build_request(config, "/embeddings")
        request.setTransferTimeout(REQUEST_TIMEOUT_MS)
        self._reply = self._manager.post(request, build_payload(model, texts, dimensions))
        self._reply.finished.connect(self._on_finished)

    def abort(self) -> None:
        self._reply.finished.disconnect(self._on_finished)
        self._reply.abort()
        self._reply.deleteLater()

    def _on_finished(self) -> None:
        reply = self._reply
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        error = reply.error()
        body = bytes(reply.readAll())
        retry_after = _retry_after_seconds(reply)
        reply.deleteLater()

        if error == QNetworkReply.NetworkError.NoError:
            try:
                self.succeeded.emit(parse_response(body, self._expected))
            except ValueError as exc:
                self.failed.emit(str(exc), "fatal", -1.0)
            return

        detail = _server_message(body) or reply.errorString()
        if error in AUTH_ERRORS or status in (401, 403):
            self.failed.emit(detail, "auth", -1.0)
        elif status == 429 or (isinstance(status, int) and status >= 500):
            self.failed.emit(detail, "retry", retry_after if retry_after is not None else -1.0)
        elif status in (400, 413, 422):
            self.failed.emit(detail, "too_large", -1.0)
        elif status == 404:
            self.failed.emit(
                f"{detail} - this endpoint may not offer embeddings, or the embedding "
                "model name isn't one it knows.",
                "fatal",
                -1.0,
            )
        elif status is None and error in _RETRYABLE_NETWORK_ERRORS:
            self.failed.emit(detail, "retry", -1.0)
        else:
            self.failed.emit(detail, "fatal", -1.0)


def _server_message(body: bytes) -> str:
    """OpenAI-style {"error": {"message": ...}} (or {"error": "..."}),
    if the server sent one - far more useful than Qt's generic text."""
    try:
        error = json.loads(body).get("error")
    except (ValueError, AttributeError):
        return ""
    if isinstance(error, dict):
        return str(error.get("message", ""))
    return str(error) if error else ""


class QueryEmbedder(QObject):
    """Embeds a single question for StudyIndex.search - `ready(vector)`
    or `failed(message)`, exactly once. No retries: a question is
    interactive, so on failure the caller just searches by keyword."""

    ready = Signal(list)
    failed = Signal(str)

    def __init__(
        self,
        config: AiConfig,
        model: str,
        text: str,
        dimensions: int | None = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._request = EmbeddingRequest(config, model, [text], dimensions, self)
        self._request.succeeded.connect(lambda vectors: self.ready.emit(vectors[0]))
        self._request.failed.connect(lambda message, _kind, _after: self.failed.emit(message))


class IndexBuilder(QObject):
    """Brings a study index fully up to date: re-collects every piece from
    the main database (cheap, about a second), syncs the index to match,
    then embeds whatever text doesn't have a vector yet, a batch at a
    time.

    Signals: `progress(embedded, total)` after preparation and after each
    batch; `finished(ok, message)` exactly once - ok=False with
    message="" means it was cancelled. `needs_api_key` is set when the
    failure was an authentication error."""

    progress = Signal(int, int)
    finished = Signal(bool, str)

    def __init__(
        self,
        scripture_conn: sqlite3.Connection,
        index_conn: sqlite3.Connection,
        config: AiConfig,
        model: str,
        dimensions: int | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._scripture_conn = scripture_conn
        self._index_conn = index_conn
        self._config = config
        self._model = model
        self._dimensions = dimensions
        self._batch_size = batch_size
        self._request: EmbeddingRequest | None = None
        self._pending: list[str] = []
        self._total = 0
        self._embedded = 0
        self._batch: list[tuple[str, str]] = []
        self._attempt = 0
        self._cancelled = False
        self._done = False
        self.needs_api_key = False
        self.model_changed = False

    def start(self) -> None:
        # Deferred a tick so a dialog can show "Preparing..." before the
        # (brief, synchronous) collect/sync step runs.
        QTimer.singleShot(0, self._prepare)

    def cancel(self) -> None:
        if self._done:
            return
        self._cancelled = True
        if self._request is not None:
            self._request.abort()
            self._request = None
        self._finish(False, "")

    def _prepare(self) -> None:
        if self._cancelled:
            return
        self.model_changed = study_index.configure_model(
            self._index_conn, self._model, self._dimensions
        )
        study_index.sync_pieces(
            self._index_conn, study_index.collect_pieces(self._scripture_conn)
        )
        status = study_index.index_status(self._index_conn)
        self._total, self._embedded = status.unique_texts, status.embedded
        self._pending = study_index.pending_hashes(self._index_conn)
        self.progress.emit(self._embedded, self._total)
        self._next_batch()

    def _next_batch(self) -> None:
        if self._cancelled:
            return
        self._batch = study_index.texts_for(self._index_conn, self._pending[: self._batch_size])
        if not self._batch:
            self._finish(True, "The study index is up to date.")
            return
        self._attempt = 0
        self._send()

    def _send(self) -> None:
        self._request = EmbeddingRequest(
            self._config, self._model, [text for _hash, text in self._batch], self._dimensions,
            self,
        )
        self._request.succeeded.connect(self._on_succeeded)
        self._request.failed.connect(self._on_failed)

    def _on_succeeded(self, vectors: list) -> None:
        self._request = None
        if self._cancelled:
            return
        try:
            study_index.store_vectors(
                self._index_conn,
                [(content_hash, vector) for (content_hash, _text), vector in zip(self._batch, vectors)],
            )
        except ValueError as exc:
            self._finish(False, str(exc))
            return
        del self._pending[: len(self._batch)]
        self._embedded += len(self._batch)
        self.progress.emit(self._embedded, self._total)
        self._next_batch()

    def _on_failed(self, message: str, kind: str, retry_after: float) -> None:
        self._request = None
        if self._cancelled:
            return
        if kind == "auth":
            self.needs_api_key = True
            self._finish(False, f"The endpoint rejected the request (authentication): {message}")
        elif kind == "too_large" and len(self._batch) > 1:
            # Retry as a smaller batch from now on; the rest of this batch
            # is still at the front of _pending, so the next one picks it up.
            self._batch_size = max(1, len(self._batch) // 2)
            self._batch = self._batch[: self._batch_size]
            self._send()
        elif kind == "retry" and self._attempt < MAX_RETRIES:
            self._attempt += 1
            delay = retry_after if retry_after >= 0 else min(MAX_BACKOFF_SECONDS, 2.0 ** self._attempt)
            QTimer.singleShot(int(delay * 1000), self._resend_if_running)
        else:
            self._finish(False, message)

    def _resend_if_running(self) -> None:
        if not self._cancelled and not self._done:
            self._send()

    def _finish(self, ok: bool, message: str) -> None:
        if self._done:
            return
        self._done = True
        self.finished.emit(ok, message)

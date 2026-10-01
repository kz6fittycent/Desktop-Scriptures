"""AI Integration → "Build Study Index..." - builds (or brings up to date)
the study index (see study_index.py) through the user's own embeddings
endpoint (see embeddings.py), with an up-front estimate of how much text
will be sent and how much disk it'll take, a progress bar, and Stop.

Stopping - or just closing the dialog - keeps everything embedded so far;
the next build picks up where this one left off. Re-running it later
only embeds what's new or changed (new notes, new citation data from an
app update, and so on).
"""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from scriptures import study_index
from scriptures.ai_client import AiConfig
from scriptures.embeddings import IndexBuilder

# Measured on the full corpus: the stored text plus its keyword index
# take about 1.5 bytes per character of indexed text.
_TEXT_BYTES_PER_CHAR = 1.5
# Each vector number is stored as float16.
_BYTES_PER_DIMENSION = 2
_TYPICAL_DIMENSIONS = 1536


def _megabytes(n: float) -> str:
    return f"{n / 1_000_000:,.0f} MB"


class StudyIndexDialog(QDialog):
    def __init__(
        self,
        scripture_conn: sqlite3.Connection,
        config: AiConfig,
        embedding_model: str,
        embedding_dimensions: int | None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Study Index")
        self.setMinimumWidth(480)
        self._scripture_conn = scripture_conn
        self._config = config
        self._model = embedding_model
        self._dimensions = embedding_dimensions
        self._index_path = study_index.index_path_for(scripture_conn)
        self._index_conn: sqlite3.Connection | None = study_index.connect_index(self._index_path)
        self._builder: IndexBuilder | None = None

        layout = QVBoxLayout(self)

        intro = QLabel(
            "The study index lets AI features find passages by meaning, not just "
            "matching words - across the scriptures, the Journal of Discourses, "
            "Lectures on Faith, the Topical Guide, cross-references, General "
            "Conference talks and Ensign/Liahona articles (titles and the verses "
            "they cite), and your own notes. It's built once on this computer and "
            "kept up to date when you run this again."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        privacy = QLabel(
            f"Building it sends that text - <b>including your notes</b>, but never "
            f"your Journal - to <b>{config.base_url}</b> using the embedding model "
            f"<b>{embedding_model}</b>."
        )
        privacy.setWordWrap(True)
        privacy.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(privacy)

        self._estimate_label = QLabel()
        self._estimate_label.setWordWrap(True)
        layout.addWidget(self._estimate_label)

        self._progress = QProgressBar()
        self._progress.setTextVisible(True)
        layout.addWidget(self._progress)

        self._status_label = QLabel()
        self._status_label.setObjectName("resultSecondary")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        buttons = QHBoxLayout()
        self._delete_button = QPushButton("Delete Index")
        self._delete_button.setToolTip("Remove the study index from this computer to free up space")
        self._delete_button.clicked.connect(self._delete_index)
        buttons.addWidget(self._delete_button)
        buttons.addStretch(1)
        self._build_button = QPushButton("Build")
        self._build_button.setDefault(True)
        self._build_button.clicked.connect(self._toggle_build)
        buttons.addWidget(self._build_button)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self._refresh_estimate()

    def _refresh_estimate(self) -> None:
        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            estimate = study_index.estimate_build(
                self._scripture_conn, self._index_conn, self._model, self._dimensions
            )
        finally:
            QGuiApplication.restoreOverrideCursor()

        self._progress.setRange(0, max(1, estimate.unique_texts))
        self._progress.setValue(estimate.embedded)
        self._progress.setFormat(f"%v of {estimate.unique_texts:,} pieces")

        text_bytes = estimate.total_chars * _TEXT_BYTES_PER_CHAR
        if self._dimensions:
            vector_bytes = estimate.unique_texts * self._dimensions * _BYTES_PER_DIMENSION
            disk = f"about {_megabytes(text_bytes + vector_bytes)} of disk space in total"
        else:
            vector_bytes = estimate.unique_texts * _TYPICAL_DIMENSIONS * _BYTES_PER_DIMENSION
            disk = (
                f"about {_megabytes(text_bytes)} of disk space plus the vectors - "
                f"around {_megabytes(vector_bytes)} more for a typical "
                f"{_TYPICAL_DIMENSIONS:,}-dimension model (setting Embedding "
                "dimensions in AI Settings, where supported, makes this smaller)"
            )
        pending = estimate.unique_texts - estimate.embedded
        if pending == 0:
            self._estimate_label.setText(
                f"The study index is up to date ({estimate.unique_texts:,} pieces). "
                "Run Build again any time to pick up new notes or content."
            )
            self._build_button.setText("Check for Updates")
        else:
            self._estimate_label.setText(
                f"<b>{pending:,}</b> pieces still to send - roughly "
                f"<b>{estimate.pending_tokens / 1_000_000:,.1f} million tokens</b>. "
                f"A hosted endpoint usually takes minutes; a local server without a "
                f"GPU can take hours (you can stop and resume any time). Uses {disk}."
            )
            self._estimate_label.setTextFormat(Qt.TextFormat.RichText)
            self._build_button.setText("Resume" if estimate.embedded else "Build")

    def _toggle_build(self) -> None:
        if self._builder is not None:
            self._builder.cancel()
            return
        self._status_label.setText("Preparing...")
        self._build_button.setText("Stop")
        self._delete_button.setEnabled(False)
        self._builder = IndexBuilder(
            self._scripture_conn, self._index_conn, self._config, self._model, self._dimensions,
            parent=self,
        )
        self._builder.progress.connect(self._on_progress)
        self._builder.finished.connect(self._on_finished)
        self._builder.start()

    def _on_progress(self, embedded: int, total: int) -> None:
        self._progress.setRange(0, max(1, total))
        self._progress.setValue(embedded)
        self._progress.setFormat(f"%v of {total:,} pieces")
        self._status_label.setText("Building... you can stop and resume later.")

    def _on_finished(self, ok: bool, message: str) -> None:
        builder, self._builder = self._builder, None
        self._delete_button.setEnabled(True)
        if ok:
            self._status_label.setText(f"✅ {message}")
        elif message:
            self._status_label.setText(f"⚠️ {message}")
            if builder is not None and builder.needs_api_key:
                QMessageBox.warning(
                    self,
                    "Study Index",
                    "The endpoint rejected the request as unauthorized. Check the API "
                    "key under AI Integration → AI Settings.",
                )
        else:
            self._status_label.setText("Stopped - everything so far is saved. Resume any time.")
        self._refresh_estimate()

    def _delete_index(self) -> None:
        answer = QMessageBox.question(
            self,
            "Delete Study Index",
            "Delete the study index from this computer? You can build it again later "
            "(which re-sends everything to your endpoint).",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._index_conn.close()
        self._index_path.unlink(missing_ok=True)
        self._index_conn = study_index.connect_index(self._index_path)
        self._status_label.setText("Deleted.")
        self._refresh_estimate()

    def done(self, result: int) -> None:  # noqa: D401 - Qt override
        """Closing while a build runs stops it (progress so far is kept)."""
        if self._builder is not None:
            self._builder.finished.disconnect(self._on_finished)
            self._builder.cancel()
            self._builder = None
        if self._index_conn is not None:
            self._index_conn.close()
            self._index_conn = None
        super().done(result)

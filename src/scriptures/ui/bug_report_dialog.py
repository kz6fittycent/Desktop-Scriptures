"""Help → Report a Bug. The user sees one optional box to say what
happened, and a Submit button; the app's log is gathered and attached
behind the scenes (bug_report.py) - they never see it. After Submit the
dialog says the report went in (or, if it couldn't be sent right now,
that it will go automatically next time the app opens).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from scriptures import bug_report

_DIALOG_WIDTH = 460

_RESULT_MESSAGES = {
    "sent": "Thank you! Your bug has been reported.",
    "duplicate": "Thank you! Your bug has been reported. Someone else ran into this too, "
    "so your report was added to theirs.",
    "rejected": "Sorry - the report couldn't be accepted. Please try again later.",
    "failed": "Your report couldn't be sent right now, so it's been saved. "
    "It will be sent automatically the next time you open Desktop Scriptures.",
}


class BugReportDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Report a Bug")
        self.setFixedWidth(_DIALOG_WIDTH)
        self._reporter: bug_report.BugReporter | None = None
        self._report: dict | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        self._intro = QLabel(
            "Something not working right? You can tell us what happened below - "
            "but you don't have to. If you'd rather not, just click <b>Submit</b>; "
            "the app sends the details needed to look into it on its own."
        )
        self._intro.setObjectName("bugReportMessage")
        self._intro.setWordWrap(True)
        layout.addWidget(self._intro)

        self._description = QTextEdit()
        self._description.setAcceptRichText(False)
        self._description.setPlaceholderText("What were you doing, and what went wrong? (optional)")
        self._description.setFixedHeight(130)
        layout.addWidget(self._description)

        self._note = QLabel(
            "Reports are posted on the project's public GitHub page so they can be fixed. "
            "They never include your notes, journal, or anything else you've written."
        )
        self._note.setObjectName("bugReportNote")
        self._note.setWordWrap(True)
        layout.addWidget(self._note)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self._cancel_button)
        self._submit_button = QPushButton("Submit")
        self._submit_button.setDefault(True)
        self._submit_button.clicked.connect(self._submit)
        buttons.addWidget(self._submit_button)
        layout.addLayout(buttons)

    def _submit(self) -> None:
        self._submit_button.setEnabled(False)
        self._submit_button.setText("Sending…")
        self._cancel_button.setEnabled(False)
        self._description.setReadOnly(True)

        self._report = bug_report.build_report(self._description.toPlainText())
        self._reporter = bug_report.BugReporter(self)
        self._reporter.finished.connect(self._on_finished)
        self._reporter.send(self._report)

    def _on_finished(self, result: str) -> None:
        if result == "failed" and bug_report.save_pending(self._report) is None:
            result = "rejected"  # couldn't even save it - don't promise a retry
        self._description.hide()
        self._note.hide()
        self._cancel_button.hide()
        self._intro.setText(_RESULT_MESSAGES[result])
        self._submit_button.setText("Close")
        self._submit_button.setEnabled(True)
        self._submit_button.clicked.disconnect()
        self._submit_button.clicked.connect(self.accept)
        self.adjustSize()

    def reject(self) -> None:
        # No closing (Esc, the window's X) while a report is on its way.
        if self._reporter is not None and not self._submit_button.isEnabled():
            return
        super().reject()

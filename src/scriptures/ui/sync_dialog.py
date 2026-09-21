"""Guided "Sync Options" dialog (see main_window.py's Sync menu and
sync.py's module docstring for the overall cloud-folder sync design).

Rather than dropping the user straight into a bare folder picker, this
asks which cloud client (if any) keeps a folder synced on this machine,
guesses where that client conventionally keeps it, and lets the user
confirm or correct both the location and the folder name before anything
is created on disk. Picking "Other" skips the guess and just asks for a
location directly, for anyone who already knows exactly which folder they
want to use.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

# Where each cloud client's own desktop app conventionally keeps its
# synced folder on Linux - just a starting guess the user can override
# below, not a guarantee that client is actually installed. Nextcloud and
# Dropbox both ship an official Linux client that defaults to these paths;
# OneDrive and Google Drive have no official one, so these match what the
# common third-party clients for each (e.g. abraunegg/onedrive, Insync)
# default to instead.
PROVIDER_DEFAULT_LOCATIONS: dict[str, str] = {
    "Nextcloud": "~/Nextcloud",
    "Dropbox": "~/Dropbox",
    "OneDrive": "~/OneDrive",
    "Google Drive": "~/Google Drive",
}
OTHER_PROVIDER = "Other (I already have a folder)"
DEFAULT_SUBFOLDER_NAME = "Desktop Scriptures"


class SyncFolderDialog(QDialog):
    """On accept, `chosen_path` holds the final folder, already created on
    disk if it didn't exist yet. None (with the dialog rejected) if the
    user cancelled."""

    def __init__(self, current_path: str | None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Sync Options")
        self.setMinimumWidth(420)
        self.chosen_path: Path | None = None

        layout = QVBoxLayout(self)

        intro = QLabel(
            "Which cloud service keeps a folder synced on this computer? "
            "Desktop Scriptures will create its own folder inside it - it "
            "never talks to the cloud service directly, it just reads and "
            "writes small files there."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._provider_group = QButtonGroup(self)
        provider_buttons: dict[str, QRadioButton] = {}
        for name in PROVIDER_DEFAULT_LOCATIONS:
            button = QRadioButton(name)
            self._provider_group.addButton(button)
            layout.addWidget(button)
            provider_buttons[name] = button
        other_button = QRadioButton(OTHER_PROVIDER)
        self._provider_group.addButton(other_button)
        layout.addWidget(other_button)
        self._provider_group.buttonClicked.connect(self._on_provider_changed)

        form = QFormLayout()

        location_row = QHBoxLayout()
        self._location_edit = QLineEdit()
        self._location_edit.textChanged.connect(self._update_preview)
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._browse_location)
        location_row.addWidget(self._location_edit)
        location_row.addWidget(browse_button)
        form.addRow("Create inside:", location_row)

        self._name_edit = QLineEdit()
        self._name_edit.textChanged.connect(self._update_preview)
        form.addRow("Folder name:", self._name_edit)

        layout.addLayout(form)

        # Reuses SearchView's own muted/small-text styling (object name
        # "resultSecondary" - see theme.py) rather than introducing a new
        # selector just for this dialog.
        self._preview_label = QLabel()
        self._preview_label.setObjectName("resultSecondary")
        self._preview_label.setWordWrap(True)
        layout.addWidget(self._preview_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Reopening this dialog to change an already-configured folder
        # shows exactly what's configured now (split back into location +
        # name) rather than resetting to a fresh guess every time.
        if current_path:
            other_button.setChecked(True)
            current = Path(current_path)
            self._location_edit.setText(str(current.parent))
            self._name_edit.setText(current.name)
        else:
            first_button = next(iter(provider_buttons.values()))
            first_button.setChecked(True)
            self._on_provider_changed(first_button)
        self._update_preview()

    def _on_provider_changed(self, button) -> None:
        name = button.text()
        if name == OTHER_PROVIDER:
            self._location_edit.setText(str(Path.home()))
            self._name_edit.setText("")
        else:
            guess = Path(PROVIDER_DEFAULT_LOCATIONS[name]).expanduser()
            self._location_edit.setText(str(guess))
            self._name_edit.setText(DEFAULT_SUBFOLDER_NAME)

    def _browse_location(self) -> None:
        start = self._location_edit.text().strip()
        if not start or not Path(start).is_dir():
            start = str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Choose Location", start)
        if chosen:
            self._location_edit.setText(chosen)

    def _final_path(self) -> Path:
        # An empty folder name (only ever the case for "Other") means the
        # chosen location itself IS the sync folder, rather than a new
        # subfolder created inside it.
        base = Path(self._location_edit.text().strip() or ".").expanduser()
        name = self._name_edit.text().strip()
        return (base / name) if name else base

    def _update_preview(self) -> None:
        path = self._final_path()
        if path.is_dir():
            state = "This folder already exists - its contents won't be touched, beyond this app's own sync files."
        elif path.parent.is_dir():
            state = "This folder doesn't exist yet - it will be created."
        else:
            state = (
                f"⚠ {path.parent} doesn't exist either - make sure the cloud "
                "client you picked above is installed and set up, or Browse "
                "to the correct location."
            )
        self._preview_label.setText(f"Will use: {path}\n{state}")

    def _on_accept(self) -> None:
        path = self._final_path()
        if not str(path).strip() or str(path) in (".", "/"):
            QMessageBox.warning(self, "Sync", "Choose a location and folder name first.")
            return
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            QMessageBox.warning(self, "Sync", f"Couldn't create that folder:\n{e}")
            return
        self.chosen_path = path
        self.accept()

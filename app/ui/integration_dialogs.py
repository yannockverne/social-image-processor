"""Small, conventional configuration surfaces for optional integrations."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from app.ui.trello_panel import TrelloPanel


class TrelloConfigurationDialog(QDialog):
    """Host the existing Trello browser away from the batch workspace."""

    def __init__(self, panel: TrelloPanel, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Trello Configuration")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        layout.addWidget(panel)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class R2SettingsDialog(QDialog):
    """Edit the persisted R2 endpoint without crowding the batch controls."""

    def __init__(self, worker_url: QLineEdit, prefix: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("R2 Upload Settings")
        self.setMinimumWidth(520)
        layout = QFormLayout(self)
        layout.addRow("Worker URL", worker_url)
        prefix_label = QLabel(prefix or "Default (no fixed prefix)")
        prefix_label.setTextInteractionFlags(prefix_label.textInteractionFlags())
        layout.addRow("Path / prefix", prefix_label)
        note = QLabel("The Trello card ID is used as the prefix when Trello updates are enabled.")
        note.setWordWrap(True)
        layout.addRow(note)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

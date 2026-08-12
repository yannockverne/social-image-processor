"""Optional Trello browser widget; no image-processing responsibilities."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from app.models.trello import TrelloCredentials
from app.services.trello_service import (
    CredentialStore,
    TrelloService,
    WindowsCredentialStore,
)
from app.ui.workers import FunctionWorker


class TrelloPanel(QFrame):
    """Own connection and dependent Board → List → Card selector state."""

    start_worker = Signal(object)

    def __init__(
        self,
        credential_store: CredentialStore | None = None,
        service_factory: Callable[[TrelloCredentials], TrelloService] = TrelloService,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.store = credential_store or WindowsCredentialStore()
        self.service_factory = service_factory
        self.service = None
        self.processed_files: tuple[Path, ...] = ()
        layout = QVBoxLayout(self)
        # Keep this optional section compact.  Stacking the title, status, and
        # connect button made all three rows part of MainWindow's mandatory
        # height, which pushed its minimum size beyond a 1080-pixel Windows
        # desktop.  A single header row preserves the same controls while
        # leaving the image table and log free to shrink as intended.
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(7)
        header = QHBoxLayout()
        header.setSpacing(10)
        title = QLabel("TRELLO")
        title.setObjectName("sectionTitle")
        self.status = QLabel("Not connected")
        # Connection and upload messages are useful context, but they must not
        # make this optional panel dictate the window's minimum width.  QLabel
        # will simply clip a particularly long service error in a narrow window.
        self.status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.connect_button = QPushButton("Connect Trello")
        self.connect_button.clicked.connect(self.connect_trello)
        self.credentials_button = QPushButton("Change credentials")
        self.credentials_button.clicked.connect(self.change_credentials)
        self.credentials_button.setVisible(False)
        header.addWidget(title)
        header.addWidget(self.status)
        header.addStretch()
        header.addWidget(self.connect_button)
        header.addWidget(self.credentials_button)
        layout.addLayout(header)
        # Board, list, and card form one dependent choice, so present them as a
        # single compact row instead of three full-width form rows.  Besides
        # making that relationship clearer, this removes two control heights
        # from MainWindow's minimumSizeHint on the roomier Windows style.
        selectors = QGridLayout()
        selectors.setHorizontalSpacing(10)
        selectors.setVerticalSpacing(3)
        self.board, self.trello_list, self.card = QComboBox(), QComboBox(), QComboBox()
        for column, (label_text, selector) in enumerate(
            (("Board", self.board), ("List", self.trello_list), ("Card", self.card))
        ):
            selector.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            selectors.addWidget(QLabel(label_text), 0, column)
            selectors.addWidget(selector, 1, column)
            selectors.setColumnStretch(column, 1)
        layout.addLayout(selectors)
        upload = QHBoxLayout()
        self.files_status = QLabel("No processed files ready")
        self.files_status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.attach_button = QPushButton("ATTACH TO CARD")
        self.attach_button.clicked.connect(self.attach_to_card)
        upload.addWidget(self.files_status)
        upload.addStretch()
        upload.addWidget(self.attach_button)
        layout.addLayout(upload)
        self.board.currentIndexChanged.connect(self._board_changed)
        self.trello_list.currentIndexChanged.connect(self._list_changed)
        self.card.currentIndexChanged.connect(self._update_attach_state)
        self._set_selectors_enabled(False)
        self._update_attach_state()

    def _set_selectors_enabled(self, enabled: bool) -> None:
        for selector in (self.board, self.trello_list, self.card):
            selector.setEnabled(enabled)

    def connect_trello(self) -> None:
        try:
            credentials = self.store.load()
        except Exception as error:
            self._show_error(str(error))
            return
        if credentials is None:
            credentials = self._prompt_credentials()
            if credentials is None:
                return
            try:
                self.store.save(credentials)
            except Exception as error:
                self._show_error(str(error))
                return
        self.service = self.service_factory(credentials)
        # Make recovery available even when the very first request rejects
        # credentials loaded from the Windows vault.
        self.credentials_button.setVisible(True)
        self.connect_button.setText("Reconnect")
        self.status.setText("Connecting…")
        self.connect_button.setEnabled(False)
        self._run(self.service.list_boards, self._boards_loaded)

    def change_credentials(self) -> None:
        """Prompt unconditionally, replacing a bad or obsolete stored secret."""
        credentials = self._prompt_credentials()
        if credentials is None:
            return
        try:
            self.store.save(credentials)
        except Exception as error:
            self._show_error(str(error))
            return
        self.service = self.service_factory(credentials)
        self.status.setText("Reconnecting…")
        self.connect_button.setEnabled(False)
        self._set_selectors_enabled(False)
        self._run(self.service.list_boards, self._boards_loaded)

    def _prompt_credentials(self) -> TrelloCredentials | None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Connect Trello")
        form = QFormLayout(dialog)
        key, token = QLineEdit(), QLineEdit()
        token.setEchoMode(QLineEdit.Password)
        form.addRow("API key", key)
        form.addRow("Token", token)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if (
            dialog.exec() != QDialog.Accepted
            or not key.text().strip()
            or not token.text().strip()
        ):
            return None
        return TrelloCredentials(key.text().strip(), token.text().strip())

    def _run(self, function, callback) -> None:
        worker = FunctionWorker(function)
        worker.signals.result.connect(callback)
        worker.signals.error.connect(self._show_error)
        worker.signals.finished.connect(
            lambda _worker: self.connect_button.setEnabled(True)
        )
        self.start_worker.emit(worker)

    @staticmethod
    def _fill(selector: QComboBox, items, placeholder: str) -> None:
        selector.blockSignals(True)
        selector.clear()
        selector.addItem(placeholder, None)
        for item in items:
            selector.addItem(item.name, item.id)
        selector.setCurrentIndex(0)
        selector.blockSignals(False)

    def _boards_loaded(self, boards) -> None:
        self._fill(
            self.board, boards, "Select a board…" if boards else "No boards found"
        )
        self._fill(self.trello_list, (), "Select a board first…")
        self._fill(self.card, (), "Select a list first…")
        self._set_selectors_enabled(True)
        self.trello_list.setEnabled(False)
        self.card.setEnabled(False)
        self.status.setText(
            "Connected" if boards else "Connected — no open boards found"
        )
        self.connect_button.setText("Reconnect")
        self.credentials_button.setVisible(True)
        self._update_attach_state()

    def _board_changed(self, _index: int) -> None:
        board_id = self.board.currentData()
        self._fill(
            self.trello_list, (), "Loading…" if board_id else "Select a board first…"
        )
        self._fill(self.card, (), "Select a list first…")
        self.trello_list.setEnabled(False)
        self.card.setEnabled(False)
        if board_id and self.service:
            self._run(lambda: self.service.list_lists(board_id), self._lists_loaded)

    def _lists_loaded(self, lists) -> None:
        self._fill(
            self.trello_list, lists, "Select a list…" if lists else "No lists found"
        )
        self.trello_list.setEnabled(True)

    def _list_changed(self, _index: int) -> None:
        list_id = self.trello_list.currentData()
        self._fill(self.card, (), "Loading…" if list_id else "Select a list first…")
        self.card.setEnabled(False)
        if list_id and self.service:
            self._run(lambda: self.service.list_cards(list_id), self._cards_loaded)

    def _cards_loaded(self, cards) -> None:
        self._fill(self.card, cards, "Select a card…" if cards else "No cards found")
        self.card.setEnabled(True)
        self._update_attach_state()

    def set_processed_files(self, paths) -> None:
        """Replace upload eligibility with successful outputs from one batch."""
        self.processed_files = tuple(Path(path) for path in paths)
        count = len(self.processed_files)
        self.files_status.setText(
            f"{count} processed file{'s' if count != 1 else ''} ready"
            if count
            else "No processed files ready"
        )
        self._update_attach_state()

    def _update_attach_state(self, *_args) -> None:
        self.attach_button.setEnabled(
            bool(self.service and self.card.currentData() and self.processed_files)
        )

    def attach_to_card(self) -> None:
        card_id = self.card.currentData()
        if not card_id:
            self._show_error("Select a Trello card first.")
            return
        if not self.processed_files:
            self._show_error("No processed files ready")
            return
        self.attach_button.setEnabled(False)
        self.status.setText(f"Uploading {len(self.processed_files)} file(s)…")
        self._run(
            lambda: self.service.upload_attachments(card_id, self.processed_files),
            self._attachments_uploaded,
        )

    def _attachments_uploaded(self, results) -> None:
        succeeded = [result for result in results if result.succeeded]
        failed = [result for result in results if not result.succeeded]
        # Successful paths leave the pending set. A retry therefore targets
        # failures only instead of creating duplicate successful attachments.
        self.processed_files = tuple(result.path for result in failed)
        remaining = len(self.processed_files)
        self.files_status.setText(
            f"{remaining} processed file{'s' if remaining != 1 else ''} ready"
            if remaining
            else "No processed files ready"
        )
        if failed:
            details = "; ".join(f"{r.path.name}: {r.message}" for r in failed)
            self.status.setText(
                f"Uploaded {len(succeeded)}; failed {len(failed)} — {details}"
            )
        else:
            self.status.setText(f"Uploaded {len(succeeded)} file(s) successfully")
        self._update_attach_state()

    def _show_error(self, message: str) -> None:
        self.status.setText(message)
        self.connect_button.setEnabled(True)

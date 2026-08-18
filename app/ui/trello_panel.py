"""Optional Trello browser widget; no image-processing responsibilities."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
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
    activity = Signal(str)
    state_changed = Signal()

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
        layout = QVBoxLayout(self)
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
        header.addStretch()
        header.addWidget(self.connect_button)
        header.addWidget(self.credentials_button)
        layout.addLayout(header)
        layout.addWidget(self.status)
        selectors = QFormLayout()
        selectors.setHorizontalSpacing(10)
        selectors.setVerticalSpacing(5)
        self.board, self.trello_list, self.card = QComboBox(), QComboBox(), QComboBox()
        for label_text, selector in (
            ("Board", self.board),
            ("List", self.trello_list),
            ("Card", self.card),
        ):
            selector.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            selectors.addRow(label_text, selector)
        layout.addLayout(selectors)
        self.board.currentIndexChanged.connect(self._board_changed)
        self.trello_list.currentIndexChanged.connect(self._list_changed)
        self.card.currentIndexChanged.connect(self.state_changed)
        self._set_selectors_enabled(False)

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
        self.state_changed.emit()
        self.connect_button.setText("Reconnect")
        self.credentials_button.setVisible(True)

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

    def _show_error(self, message: str) -> None:
        self.status.setText(message)
        self.connect_button.setEnabled(True)
        self.state_changed.emit()

    def disconnect_trello(self) -> None:
        """End the in-memory Trello session without changing saved credentials."""
        self.service = None
        self.status.setText("Not connected")
        self.connect_button.setText("Connect Trello")
        self._fill(self.board, (), "Connect to browse boards…")
        self._fill(self.trello_list, (), "Select a board first…")
        self._fill(self.card, (), "Select a list first…")
        self._set_selectors_enabled(False)
        self.state_changed.emit()

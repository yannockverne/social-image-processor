"""Optional Trello browser widget; no image-processing responsibilities."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
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
    QTextEdit,
    QVBoxLayout,
)

from app.models.trello import TrelloCredentials
from app.services.trello_service import (
    CredentialStore,
    TrelloService,
    WindowsCredentialStore,
    PREPARATION_LIST_NAME,
)
from app.ui.workers import FunctionWorker


class NewTrelloCardDialog(QDialog):
    """Collect only the user-authored fields needed for a new post card."""

    request_create = Signal()
    board_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Trello card")
        self.setMinimumWidth(420)
        form = QFormLayout(self)
        self.board = QComboBox()
        self.trello_list = QComboBox()
        self.title_edit = QLineEdit()
        self.x_edit = QTextEdit()
        self.instagram_edit = QTextEdit()
        self.x_edit.setFixedHeight(90)
        self.instagram_edit.setFixedHeight(90)
        form.addRow("Board", self.board)
        form.addRow("List", self.trello_list)
        form.addRow("Card title", self.title_edit)
        form.addRow("X text", self.x_edit)
        form.addRow("Instagram text", self.instagram_edit)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self.buttons.button(QDialogButtonBox.Ok).setText("Create card")
        self.buttons.accepted.connect(self._accept_if_valid)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)
        self.board.currentIndexChanged.connect(self._board_selected)

    def set_boards(self, boards, preferred_id: str | None = None) -> None:
        TrelloPanel._fill(self.board, boards, "Select a board…")
        index = self.board.findData(preferred_id)
        if index > 0:
            self.board.setCurrentIndex(index)

    def _board_selected(self, _index: int) -> None:
        board_id = self.board.currentData()
        TrelloPanel._fill(
            self.trello_list, (), "Loading…" if board_id else "Select a board first…"
        )
        self.trello_list.setEnabled(False)
        self.board_changed.emit(board_id or "")

    def set_lists(self, lists, preferred_id: str | None = None) -> None:
        TrelloPanel._fill(
            self.trello_list, lists, "Select a list…" if lists else "No lists found"
        )
        index = self.trello_list.findData(preferred_id)
        if index < 1:
            index = next(
                (i for i in range(1, self.trello_list.count())
                 if self.trello_list.itemText(i) == PREPARATION_LIST_NAME),
                0,
            )
        self.trello_list.setCurrentIndex(index)
        self.trello_list.setEnabled(True)

    def _accept_if_valid(self) -> None:
        if (
            self.title_edit.text().strip()
            and self.board.currentData()
            and self.trello_list.currentData()
        ):
            self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)
            self.request_create.emit()

    def reset_submission(self) -> None:
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(True)

    def values(self) -> tuple[str, str, str, str, str]:
        return (
            self.board.currentData(),
            self.trello_list.currentData(),
            self.title_edit.text().strip(),
            self.x_edit.toPlainText(),
            self.instagram_edit.toPlainText(),
        )


class TrelloPanel(QFrame):
    """Own connection and dependent Board → List → Card selector state."""

    start_worker = Signal(object)
    activity = Signal(str)
    state_changed = Signal()
    destination_used = Signal(str, str)

    def __init__(
        self,
        credential_store: CredentialStore | None = None,
        service_factory: Callable[[TrelloCredentials], TrelloService] = TrelloService,
        preferred_board_id: str | None = None,
        preferred_list_id: str | None = None,
        url_opener: Callable[[QUrl], bool] = QDesktopServices.openUrl,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.store = credential_store or WindowsCredentialStore()
        self.service_factory = service_factory
        self.service = None
        self.preferred_board_id = preferred_board_id
        self.preferred_list_id = preferred_list_id
        self._boards = []
        self._cards_by_id = {}
        self.url_opener = url_opener
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
        self._boards = list(boards)
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
        index = self.board.findData(self.preferred_board_id)
        if index > 0:
            self.board.setCurrentIndex(index)
        elif self.preferred_board_id:
            # Avoid retrying an inaccessible identifier for the lifetime of this
            # connection, while leaving the last known-good persisted value alone.
            self.preferred_board_id = None

    def _board_changed(self, _index: int) -> None:
        self._cards_by_id.clear()
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
        index = self.trello_list.findData(self.preferred_list_id)
        if index > 0:
            self.trello_list.setCurrentIndex(index)
        elif self.preferred_list_id and self.board.currentData():
            self.preferred_list_id = None

    def _list_changed(self, _index: int) -> None:
        self._cards_by_id.clear()
        list_id = self.trello_list.currentData()
        self._fill(self.card, (), "Loading…" if list_id else "Select a list first…")
        self.card.setEnabled(False)
        if list_id and self.service:
            self._run(lambda: self.service.list_cards(list_id), self._cards_loaded)

    def _cards_loaded(self, cards) -> None:
        self._cards_by_id = {card.id: card for card in cards}
        self._fill(self.card, cards, "Select a card…" if cards else "No cards found")
        self.card.setEnabled(True)

    def selected_card_url(self) -> str | None:
        card = self._cards_by_id.get(self.card.currentData())
        return card.url if card else None

    def open_selected_card(self) -> bool:
        """Open the selected card using URL data already returned by Trello."""
        url = self.selected_card_url()
        if not url:
            self._show_error("Select a Trello card with a valid URL first.")
            return False
        try:
            if not self.url_opener(QUrl(url)):
                raise RuntimeError("the browser rejected the URL")
        except Exception as error:
            message = f"Could not open Trello card: {error}"
            self._show_error(message)
            self.activity.emit(message)
            return False
        return True

    def _show_error(self, message: str) -> None:
        self.status.setText(message)
        self.connect_button.setEnabled(True)
        self.state_changed.emit()

    def create_new_card(self) -> None:
        """Prompt for and asynchronously create a card on the selected board."""
        if self.service is None:
            self._show_error("Trello is not connected. Connect Trello first.")
            return
        dialog = NewTrelloCardDialog(self.window())
        preferred_board = self.board.currentData() or self.preferred_board_id
        dialog.set_boards(self._boards, preferred_board)
        dialog.board_changed.connect(
            lambda board_id: self._load_dialog_lists(dialog, board_id)
        )
        dialog.request_create.connect(lambda: self._submit_new_card(dialog))
        if dialog.board.currentData():
            self._load_dialog_lists(dialog, dialog.board.currentData())
        dialog.open()

    def _load_dialog_lists(self, dialog: NewTrelloCardDialog, board_id: str) -> None:
        if not board_id or not self.service:
            return
        self._run(
            lambda: self.service.list_lists(board_id),
            lambda lists: (
                dialog.set_lists(lists, self.preferred_list_id)
                if dialog.board.currentData() == board_id
                else None
            ),
        )

    def _submit_new_card(self, dialog: NewTrelloCardDialog) -> None:
        board_id, list_id, title, x_text, instagram_text = dialog.values()
        self.status.setText("Creating Trello card…")
        worker = FunctionWorker(
            lambda: self.service.create_post_card(
                board_id, list_id, title, x_text, instagram_text
            )
        )
        worker.signals.result.connect(
            lambda card: self._new_card_created(card, dialog, board_id, list_id)
        )
        worker.signals.error.connect(
            lambda message: self._new_card_failed(message, dialog)
        )
        worker.signals.finished.connect(
            lambda _worker: self.connect_button.setEnabled(True)
        )
        self.start_worker.emit(worker)

    def _new_card_created(self, card, dialog=None, board_id=None, list_id=None) -> None:
        """Add and select the result without disturbing existing browsing logic."""
        index = self.card.findData(card.id)
        if index < 0:
            self.card.addItem(card.name, card.id)
            index = self.card.count() - 1
        self._cards_by_id[card.id] = card
        self.card.setEnabled(True)
        self.card.setCurrentIndex(index)
        message = f'Trello card "{card.name}" created with publication checklist.'
        self.status.setText(message)
        self.activity.emit(message)
        self.state_changed.emit()
        if board_id and list_id:
            self.preferred_board_id, self.preferred_list_id = board_id, list_id
            self.destination_used.emit(board_id, list_id)
        if dialog is not None:
            dialog.accept()

    def _new_card_failed(self, message: str, dialog: NewTrelloCardDialog) -> None:
        dialog.reset_submission()
        self._show_error(message)

    def disconnect_trello(self) -> None:
        """End the in-memory Trello session without changing saved credentials."""
        self.service = None
        self._cards_by_id.clear()
        self.status.setText("Not connected")
        self.connect_button.setText("Connect Trello")
        self._fill(self.board, (), "Connect to browse boards…")
        self._fill(self.trello_list, (), "Select a board first…")
        self._fill(self.card, (), "Select a list first…")
        self._set_selectors_enabled(False)
        self.state_changed.emit()

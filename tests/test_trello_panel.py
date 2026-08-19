from __future__ import annotations

import pytest

pytest.importorskip("PySide6.QtGui", exc_type=ImportError)
from PySide6.QtWidgets import QApplication

from app.models.trello import (
    TrelloBoard,
    TrelloCard,
    TrelloCredentials,
    TrelloList,
)
from app.ui.trello_panel import NewTrelloCardDialog, TrelloPanel


class MemoryStore:
    def __init__(self):
        self.saved = []

    def load(self):
        return TrelloCredentials("key", "token")

    def save(self, credentials):
        self.saved.append(credentials)


class FakeService:
    def __init__(self, _credentials):
        self.calls = []

    def list_boards(self):
        self.calls.append(("boards", None))
        return [TrelloBoard("b1", "Board one")]

    def list_lists(self, board_id):
        self.calls.append(("lists", board_id))
        return [TrelloList("l1", "Ready")]

    def list_cards(self, list_id):
        self.calls.append(("cards", list_id))
        return [TrelloCard("c1", "Post")]

    def create_post_card(self, board_id, list_id, title, x_text, instagram_text):
        self.calls.append(("create", board_id, list_id, title, x_text, instagram_text))
        return TrelloCard("c-new", title)


@pytest.fixture(scope="module")
def application():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(application):
    widget = TrelloPanel(MemoryStore(), FakeService)

    def run_now(worker):
        worker.run()
        application.processEvents()

    widget.start_worker.connect(run_now)
    yield widget
    widget.close()


def test_disconnected_state(panel) -> None:
    assert panel.status.text() == "Not connected"
    assert panel.connect_button.text() == "Connect Trello"
    assert not panel.board.isEnabled()


def test_dependent_board_list_and_card_loading_requires_explicit_choices(panel) -> None:
    panel.connect_button.click()
    assert panel.status.text() == "Connected"
    assert panel.board.count() == 2
    assert panel.board.currentData() is None
    assert not panel.trello_list.isEnabled()

    panel.board.setCurrentIndex(1)
    assert panel.service.calls[-1] == ("lists", "b1")
    assert panel.trello_list.currentData() is None

    panel.trello_list.setCurrentIndex(1)
    assert panel.service.calls[-1] == ("cards", "l1")
    assert panel.card.count() == 2
    assert panel.card.currentData() is None


def test_saved_board_and_list_are_restored_on_connect(application) -> None:
    widget = TrelloPanel(
        MemoryStore(), FakeService, preferred_board_id="b1", preferred_list_id="l1"
    )
    widget.start_worker.connect(lambda worker: worker.run())
    widget.connect_trello()
    application.processEvents()

    assert widget.board.currentData() == "b1"
    assert widget.trello_list.currentData() == "l1"
    widget.close()


def test_stale_saved_list_keeps_restored_board(application) -> None:
    widget = TrelloPanel(
        MemoryStore(), FakeService, preferred_board_id="b1", preferred_list_id="gone"
    )
    widget.start_worker.connect(lambda worker: worker.run())
    widget.connect_trello()
    application.processEvents()

    assert widget.board.currentData() == "b1"
    assert widget.trello_list.currentData() is None
    widget.close()


def test_stale_saved_board_falls_back_safely(application) -> None:
    widget = TrelloPanel(
        MemoryStore(), FakeService, preferred_board_id="gone", preferred_list_id="l1"
    )
    widget.start_worker.connect(lambda worker: worker.run())
    widget.connect_trello()
    application.processEvents()

    assert widget.board.currentData() is None
    assert widget.preferred_board_id is None
    widget.close()


def test_failure_stays_inside_trello_panel(panel) -> None:
    panel.connect_button.click()
    panel._show_error("Trello authentication failed")
    assert panel.status.text() == "Trello authentication failed"
    assert panel.connect_button.isEnabled()
    assert not panel.credentials_button.isHidden()


def test_change_credentials_replaces_stored_values(panel, monkeypatch) -> None:
    replacement = TrelloCredentials("new-key", "new-token")
    monkeypatch.setattr(panel, "_prompt_credentials", lambda: replacement)
    panel.change_credentials()
    assert panel.store.saved == [replacement]
    assert panel.status.text() == "Connected"


def test_new_card_dialog_returns_exact_field_values(application) -> None:
    dialog = NewTrelloCardDialog()
    dialog.set_boards([TrelloBoard("b1", "Board")], "b1")
    dialog.set_lists([TrelloList("l1", "Ready")], "l1")
    dialog.title_edit.setText("  Card title  ")
    dialog.x_edit.setPlainText("X\ncopy")
    dialog.instagram_edit.setPlainText("")
    assert dialog.values() == ("b1", "l1", "Card title", "X\ncopy", "")
    dialog.close()


def test_new_card_is_created_and_automatically_selected(panel) -> None:
    panel.connect_button.click()
    panel.board.setCurrentIndex(1)

    class AcceptedDialog:
        accepted = False

        def values(self):
            return ("b1", "l1", "New post", "X text", "Instagram text")

        def accept(self):
            self.accepted = True

    activity = []
    panel.activity.connect(activity.append)
    dialog = AcceptedDialog()
    panel._submit_new_card(dialog)

    assert panel.service.calls[-1] == (
        "create",
        "b1",
        "l1",
        "New post",
        "X text",
        "Instagram text",
    )
    assert panel.card.currentData() == "c-new"
    assert "publication checklist" in panel.status.text()
    assert activity == [panel.status.text()]
    assert dialog.accepted


def test_new_card_requires_connection(panel) -> None:
    panel.create_new_card()
    assert "not connected" in panel.status.text()
    panel.connect_button.click()

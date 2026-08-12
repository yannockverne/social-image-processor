from __future__ import annotations

import pytest

pytest.importorskip("PySide6.QtGui", exc_type=ImportError)
from PySide6.QtWidgets import QApplication

from app.models.trello import TrelloBoard, TrelloCard, TrelloCredentials, TrelloList
from app.ui.trello_panel import TrelloPanel


class MemoryStore:
    def load(self):
        return TrelloCredentials("key", "token")

    def save(self, credentials):
        raise AssertionError("existing credentials should not be saved again")


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


def test_failure_stays_inside_trello_panel(panel) -> None:
    panel._show_error("Trello authentication failed")
    assert panel.status.text() == "Trello authentication failed"
    assert panel.connect_button.isEnabled()

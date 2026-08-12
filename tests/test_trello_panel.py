from __future__ import annotations

import pytest

pytest.importorskip("PySide6.QtGui", exc_type=ImportError)
from PySide6.QtWidgets import QApplication

from pathlib import Path

from app.models.trello import (
    TrelloAttachmentResult,
    TrelloBoard,
    TrelloCard,
    TrelloCredentials,
    TrelloList,
)
from app.ui.trello_panel import TrelloPanel


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

    def upload_attachments(self, card_id, paths):
        self.calls.append(("upload", card_id, tuple(paths)))
        return [TrelloAttachmentResult(path, True) for path in paths]


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
    panel.connect_button.click()
    panel._show_error("Trello authentication failed")
    assert panel.status.text() == "Trello authentication failed"
    assert panel.connect_button.isEnabled()
    assert not panel.credentials_button.isHidden()


def test_upload_disabled_without_outputs_and_enabled_with_card(panel) -> None:
    panel.connect_button.click()
    panel.board.setCurrentIndex(1)
    panel.trello_list.setCurrentIndex(1)
    panel.card.setCurrentIndex(1)
    assert not panel.attach_button.isEnabled()
    assert panel.files_status.text() == "No processed files ready"

    panel.set_processed_files([Path("X_ready.jpg"), Path("Insta_ready.jpg")])
    assert panel.attach_button.isEnabled()
    assert panel.files_status.text() == "2 processed files ready"


def test_explicit_attach_uploads_current_processed_outputs(panel) -> None:
    files = [Path("X_ready.jpg"), Path("Insta_ready.jpg")]
    panel.connect_button.click()
    panel.board.setCurrentIndex(1)
    panel.trello_list.setCurrentIndex(1)
    panel.card.setCurrentIndex(1)
    panel.set_processed_files(files)
    activity = []
    panel.activity.connect(activity.append)
    panel.attach_button.click()
    assert panel.service.calls[-1] == ("upload", "c1", tuple(files))
    assert panel.status.text() == "Uploaded 2 file(s) successfully"
    assert not panel.attach_button.isEnabled()
    assert activity == [
        'Trello: uploading 2 attachments to "Post"…',
        "Trello: X_ready.jpg uploaded.",
        "Trello: Insta_ready.jpg uploaded.",
        "Trello: 2/2 attachments uploaded successfully.",
    ]


def test_partial_upload_failure_is_clear(panel) -> None:
    activity = []
    panel.activity.connect(activity.append)
    panel._attachments_uploaded(
        [
            TrelloAttachmentResult(Path("X_ok.jpg"), True),
            TrelloAttachmentResult(Path("X_bad.jpg"), False, "network unavailable"),
        ]
    )
    assert "Uploaded 1; failed 1" in panel.status.text()
    assert "X_bad.jpg: network unavailable" in panel.status.text()
    assert panel.processed_files == (Path("X_bad.jpg"),)
    assert activity == [
        "Trello: X_ok.jpg uploaded.",
        "Trello: X_bad.jpg failed — network unavailable.",
        "Trello: 1/2 attachments uploaded. 1 pending retry.",
    ]


def test_retry_retains_failed_files_in_original_relative_order(panel) -> None:
    panel._attachments_uploaded(
        [
            TrelloAttachmentResult(Path("first.jpg"), False, "failed"),
            TrelloAttachmentResult(Path("second.jpg"), True),
            TrelloAttachmentResult(Path("third.jpg"), False, "failed"),
        ]
    )

    assert panel.processed_files == (Path("first.jpg"), Path("third.jpg"))


def test_change_credentials_replaces_stored_values(panel, monkeypatch) -> None:
    replacement = TrelloCredentials("new-key", "new-token")
    monkeypatch.setattr(panel, "_prompt_credentials", lambda: replacement)
    panel.change_credentials()
    assert panel.store.saved == [replacement]
    assert panel.status.text() == "Connected"

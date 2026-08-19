from __future__ import annotations

from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

import pytest


from app.models.trello import TrelloCredentials
from app.services.trello_service import (
    PUBLICATION_CHECKLIST_ITEMS,
    TrelloError,
    TrelloService,
    build_post_description,
)


class Response(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def test_board_list_and_card_reads_are_mapped(monkeypatch) -> None:
    responses = iter(
        (
            b'[{"id":"b1","name":"Publishing"}]',
            b'[{"id":"l1","name":"Ready"}]',
            b'[{"id":"c1","name":"Launch"}]',
        )
    )
    urls = []

    def open_request(request, timeout):
        urls.append((request.full_url, timeout))
        return Response(next(responses))

    monkeypatch.setattr("app.services.trello_service.urlopen", open_request)
    service = TrelloService(TrelloCredentials("key", "secret"), timeout=3)

    assert service.list_boards()[0].name == "Publishing"
    assert service.list_lists("b1")[0].name == "Ready"
    assert service.list_cards("l1")[0].name == "Launch"
    assert "/boards/b1/lists" in urls[1][0]
    assert "/lists/l1/cards" in urls[2][0]
    assert all(timeout == 3 for _, timeout in urls)


@pytest.mark.parametrize(
    ("failure", "message"),
    (
        (HTTPError("url", 401, "Unauthorized", {}, None), "authentication failed"),
        (URLError("offline"), "unavailable"),
    ),
)
def test_api_and_authentication_failures_are_readable(
    monkeypatch, failure: Exception, message: str
) -> None:
    def fail(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr("app.services.trello_service.urlopen", fail)
    with pytest.raises(TrelloError, match=message):
        TrelloService(TrelloCredentials("key", "token")).list_boards()


def test_card_description_read_and_single_update(monkeypatch) -> None:
    requests = []
    responses = iter((b'{"desc":"Existing"}', b'{"id":"card-1"}'))

    def open_request(request, timeout):
        requests.append(request)
        return Response(next(responses))

    monkeypatch.setattr("app.services.trello_service.urlopen", open_request)
    service = TrelloService(TrelloCredentials("key", "token"))
    assert service.get_card_description("card-1") == "Existing"
    service.update_card_description("card-1", "## URL MAKE\nhttps://pub/x.jpg\n")
    assert len(requests) == 2
    assert requests[1].method == "PUT"
    assert "/cards/card-1?" in requests[1].full_url
    assert "desc=%23%23+URL+MAKE" in requests[1].full_url


@pytest.mark.parametrize(
    ("x_text", "instagram_text", "expected"),
    (
        ("X copy", "Insta copy", "## X\n\nX copy\n\n## Insta\n\nInsta copy\n"),
        ("", "Insta only", "## X\n\n\n\n## Insta\n\nInsta only\n"),
        ("X only", "", "## X\n\nX only\n\n## Insta\n\n\n"),
    ),
)
def test_post_description_keeps_empty_platform_sections(
    x_text, instagram_text, expected
) -> None:
    assert build_post_description(x_text, instagram_text) == expected


def test_create_post_card_adds_unchecked_publication_checklist(monkeypatch) -> None:
    requests = []
    responses = iter(
        [
            '[{"id":"prepare","name":"🛠️ À préparer"}]'.encode(),
            b'{"id":"card-2","name":"A spontaneous post"}',
            b'{"id":"check-1"}',
            *[b'{"id":"item"}' for _ in PUBLICATION_CHECKLIST_ITEMS],
        ]
    )

    def open_request(request, timeout):
        requests.append(request)
        return Response(next(responses))

    monkeypatch.setattr("app.services.trello_service.urlopen", open_request)
    card = TrelloService(TrelloCredentials("key", "token")).create_post_card(
        "board-1", "A spontaneous post", "X copy", "Insta copy"
    )

    assert (card.id, card.name) == ("card-2", "A spontaneous post")
    assert requests[1].method == "POST"
    assert "idList=prepare" in requests[1].full_url
    assert "desc=%23%23+X" in requests[1].full_url
    item_requests = requests[3:]
    assert len(item_requests) == len(PUBLICATION_CHECKLIST_ITEMS)
    assert all("checked=false" in request.full_url for request in item_requests)
    assert all(
        urlencode({"name": item}) in request.full_url
        for item, request in zip(PUBLICATION_CHECKLIST_ITEMS, item_requests)
    )


def test_create_post_card_reports_missing_destination_list(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.trello_service.urlopen",
        lambda *_args, **_kwargs: Response(b'[{"id":"other","name":"Ready"}]'),
    )
    with pytest.raises(TrelloError, match="Destination list.*not found"):
        TrelloService(TrelloCredentials("key", "token")).create_post_card(
            "board", "Title", "", ""
        )


def test_checklist_failure_does_not_claim_full_creation(monkeypatch) -> None:
    responses = iter(
        (
            Response('[{"id":"prepare","name":"🛠️ À préparer"}]'.encode()),
            Response(b'{"id":"card-2","name":"Title"}'),
        )
    )

    def open_request(*_args, **_kwargs):
        try:
            return next(responses)
        except StopIteration:
            raise HTTPError("url", 500, "failure", {}, None)

    monkeypatch.setattr("app.services.trello_service.urlopen", open_request)
    with pytest.raises(TrelloError, match="was created, but.*checklist"):
        TrelloService(TrelloCredentials("key", "token")).create_post_card(
            "board", "Title", "", ""
        )

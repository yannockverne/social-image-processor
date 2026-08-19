from __future__ import annotations

from io import BytesIO
import json
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
    assert PUBLICATION_CHECKLIST_ITEMS == (
        "Photos",
        "Image selection",
        "Retouching",
        "Instagram + X copy",
        "X post published",
        "Instagram post published",
    )
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


def _checklist(items):
    return json.dumps(
        [{"id": "check", "name": "Publication", "checkItems": items}]
    ).encode()


def test_processing_checklist_completes_only_incomplete_targets(monkeypatch) -> None:
    requests = []
    items = [
        {"id": "photos", "name": "Photos", "state": "incomplete"},
        {"id": "selection", "name": "Image selection", "state": "complete"},
        {"id": "retouch", "name": "Retouching", "state": "incomplete"},
        {"id": "copy", "name": "Instagram + X copy", "state": "incomplete"},
        {"id": "other", "name": "Unrelated", "state": "incomplete"},
    ]
    responses = iter(
        (_checklist(items), b'{"state":"complete"}', b'{"state":"complete"}')
    )

    def open_request(request, timeout):
        requests.append(request)
        return Response(next(responses))

    monkeypatch.setattr("app.services.trello_service.urlopen", open_request)
    result = TrelloService(
        TrelloCredentials("key", "token")
    ).complete_processing_checklist("card")

    assert result.completed == ("Photos", "Retouching")
    assert result.already_complete == ("Image selection",)
    assert result.missing == ()
    assert [request.get_method() for request in requests] == ["GET", "PUT", "PUT"]
    assert "checkItem/photos" in requests[1].full_url
    assert "checkItem/retouch" in requests[2].full_url
    assert all("state=complete" in request.full_url for request in requests[1:])
    assert not any(
        "copy" in request.full_url or "other" in request.full_url
        for request in requests[1:]
    )


def test_processing_checklist_completes_all_three_targets(monkeypatch) -> None:
    items = [
        {"id": str(index), "name": name, "state": "incomplete"}
        for index, name in enumerate(PUBLICATION_CHECKLIST_ITEMS)
    ]
    responses = iter([_checklist(items), *[b'{"state":"complete"}'] * 3])
    monkeypatch.setattr(
        "app.services.trello_service.urlopen",
        lambda *_args, **_kwargs: Response(next(responses)),
    )
    result = TrelloService(
        TrelloCredentials("key", "token")
    ).complete_processing_checklist("card")
    assert result.completed == ("Photos", "Image selection", "Retouching")


def test_processing_checklist_reports_missing_items_without_creating(
    monkeypatch,
) -> None:
    requests = []

    def open_request(request, timeout):
        requests.append(request)
        return Response(
            _checklist([{"id": "photos", "name": "Photos", "state": "complete"}])
        )

    monkeypatch.setattr("app.services.trello_service.urlopen", open_request)
    result = TrelloService(
        TrelloCredentials("key", "token")
    ).complete_processing_checklist("card")
    assert result.missing == ("Image selection", "Retouching")
    assert len(requests) == 1


def test_processing_card_without_publication_checklist_is_unchanged(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.services.trello_service.urlopen",
        lambda *_args, **_kwargs: Response(b"[]"),
    )
    result = TrelloService(
        TrelloCredentials("key", "token")
    ).complete_processing_checklist("card")
    assert result.missing == ("Photos", "Image selection", "Retouching")


def test_processing_checklist_read_failure_is_reported(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.trello_service.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("offline")),
    )
    with pytest.raises(TrelloError, match="unavailable"):
        TrelloService(TrelloCredentials("key", "token")).complete_processing_checklist(
            "card"
        )


def test_processing_checklist_continues_after_partial_update_failure(
    monkeypatch,
) -> None:
    items = [
        {"id": name.lower(), "name": name, "state": "incomplete"}
        for name in ("Photos", "Image selection", "Retouching")
    ]
    calls = 0

    def open_request(request, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            return Response(_checklist(items))
        if calls == 2:
            raise HTTPError("url", 500, "failure", {}, None)
        return Response(b'{"state":"complete"}')

    monkeypatch.setattr("app.services.trello_service.urlopen", open_request)
    result = TrelloService(
        TrelloCredentials("key", "token")
    ).complete_processing_checklist("card")
    assert result.failed == ("Photos",)
    assert result.completed == ("Image selection", "Retouching")
    assert calls == 4

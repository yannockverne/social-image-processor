from __future__ import annotations

from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest


from app.models.trello import TrelloCredentials
from app.services.trello_service import TrelloError, TrelloService


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

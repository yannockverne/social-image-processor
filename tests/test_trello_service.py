from __future__ import annotations

from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from pathlib import Path

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


def test_successful_multiple_attachment_uploads(monkeypatch, tmp_path: Path) -> None:
    files = [tmp_path / "X_01.jpg", tmp_path / "Insta_01.jpg"]
    for index, path in enumerate(files):
        path.write_bytes(f"image-{index}".encode())
    requests = []

    def open_request(request, timeout):
        requests.append(request)
        return Response(b'{"id":"attachment"}')

    monkeypatch.setattr("app.services.trello_service.urlopen", open_request)
    results = TrelloService(TrelloCredentials("key", "token")).upload_attachments(
        "card-1", files
    )

    assert all(result.succeeded for result in results)
    assert len(requests) == 2
    assert all(request.method == "POST" for request in requests)
    assert all("/cards/card-1/attachments" in request.full_url for request in requests)
    for file, request in zip(files, requests, strict=True):
        assert f'filename="{file.name}"'.encode() in request.data
        assert file.read_bytes() in request.data


def test_partial_attachment_failure_is_retained(monkeypatch, tmp_path: Path) -> None:
    files = [tmp_path / "X_good.jpg", tmp_path / "X_bad.jpg"]
    for path in files:
        path.write_bytes(b"image")
    calls = 0

    def open_request(_request, timeout):
        nonlocal calls
        del timeout
        calls += 1
        if calls == 2:
            raise HTTPError("url", 500, "failure", {}, None)
        return Response(b'{"id":"attachment"}')

    monkeypatch.setattr("app.services.trello_service.urlopen", open_request)
    results = TrelloService(TrelloCredentials("key", "token")).upload_attachments(
        "card-1", files
    )

    assert [result.succeeded for result in results] == [True, False]
    assert "API error (500)" in results[1].message


@pytest.mark.parametrize(
    ("failure", "message"),
    (
        (HTTPError("url", 403, "Forbidden", {}, None), "authentication failed"),
        (URLError("offline"), "unavailable"),
        (HTTPError("url", 429, "Rate limited", {}, None), "API error (429)"),
    ),
)
def test_attachment_auth_network_and_api_failures(
    monkeypatch, tmp_path: Path, failure: Exception, message: str
) -> None:
    path = tmp_path / "X_image.jpg"
    path.write_bytes(b"image")
    monkeypatch.setattr(
        "app.services.trello_service.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(failure),
    )
    result = TrelloService(TrelloCredentials("key", "token")).upload_attachments(
        "card", [path]
    )[0]
    assert not result.succeeded
    assert message in result.message

from __future__ import annotations

import json
from pathlib import Path
from urllib.error import URLError

import pytest

from app.core.watermarking import WatermarkCatalog
from app.models.image_item import ImageItem
from app.models.results import ExportStatus
from app.services.batch_processor import BatchProcessor
from app.services.r2_upload_service import R2UploadService

Image = pytest.importorskip("PIL.Image")


class Response:
    def __init__(self, body: bytes = b"", status: int = 200) -> None:
        self.status = status
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return self._body


def test_successful_upload_uses_put_and_deterministic_encoded_key(
    tmp_path: Path,
) -> None:
    local = tmp_path / "X 01.jpg"
    local.write_bytes(b"jpeg")
    requests = []
    public_url = "https://pub-example.r2.dev/campaign/X%2001.jpg"

    def open_request(request, *, timeout):
        requests.append((request, timeout))
        return Response(json.dumps({"ok": True, "publicUrl": public_url}).encode())

    service = R2UploadService(
        "https://worker.example/upload/", remote_prefix="campaign", opener=open_request
    )
    result = service.upload(local)

    assert result.success
    assert result.object_key == "campaign/X 01.jpg"
    assert result.public_url == public_url
    assert len(requests) == 1
    assert requests[0][0].method == "PUT"
    assert requests[0][0].data == b"jpeg"
    assert requests[0][0].get_header("Content-type") == "image/jpeg"
    assert requests[0][0].get_header("User-agent") == "SocialImageProcessor/1.0"


def test_successful_upload_without_public_url_is_returned_as_failure(
    tmp_path: Path,
) -> None:
    local = tmp_path / "X_01.jpg"
    local.write_bytes(b"jpeg")

    def open_request(*_args, **_kwargs):
        return Response(b'{"ok": true, "fileName": "X_01.jpg"}')

    result = R2UploadService(
        "https://worker.example/upload", opener=open_request
    ).upload(local)

    assert not result.success
    assert "usable publicUrl" in result.error_message


def test_successful_upload_with_invalid_json_is_returned_as_failure(
    tmp_path: Path,
) -> None:
    local = tmp_path / "X_01.jpg"
    local.write_bytes(b"jpeg")

    def open_request(*_args, **_kwargs):
        return Response(b"not JSON")

    result = R2UploadService(
        "https://worker.example/upload", opener=open_request
    ).upload(local)

    assert not result.success
    assert "invalid JSON" in result.error_message


@pytest.mark.parametrize("url", ["", "worker.example", "ftp://worker.example"])
def test_invalid_or_missing_worker_url_does_not_make_request(
    tmp_path: Path, url: str
) -> None:
    local = tmp_path / "X_01.jpg"
    local.write_bytes(b"jpeg")
    called = False

    def forbidden(*_args, **_kwargs):
        nonlocal called
        called = True

    result = R2UploadService(url, opener=forbidden).upload(local)

    assert not result.success
    assert "valid HTTP or HTTPS" in result.error_message
    assert not called


def test_network_failure_is_returned_not_raised(tmp_path: Path) -> None:
    local = tmp_path / "X_01.jpg"
    local.write_bytes(b"jpeg")

    def fail(*_args, **_kwargs):
        raise URLError("offline")

    result = R2UploadService("https://worker.example", opener=fail).upload(local)

    assert not result.success
    assert "offline" in result.error_message
    assert local.read_bytes() == b"jpeg"


def test_http_failure_is_returned_not_raised(tmp_path: Path) -> None:
    local = tmp_path / "X_01.jpg"
    local.write_bytes(b"jpeg")

    def reject(request, *, timeout):
        return Response(status=503)

    result = R2UploadService("https://worker.example", opener=reject).upload(local)

    assert not result.success
    assert "HTTP 503" in result.error_message


def test_disabled_upload_makes_no_request_and_export_succeeds(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (8, 4)).save(source)
    item = ImageItem(source, 8, 4, source.stat().st_size, export_to_x=True)
    result = BatchProcessor(
        [item],
        tmp_path / "out",
        watermark_enabled=False,
        watermark_catalog=WatermarkCatalog(),
    ).process()

    assert result.exports[0].status is ExportStatus.SUCCEEDED
    assert result.uploads == ()


def test_upload_failures_are_independent_and_keep_local_exports(tmp_path: Path) -> None:
    sources = []
    for name in ("one.png", "two.png"):
        path = tmp_path / name
        Image.new("RGB", (8, 4)).save(path)
        sources.append(ImageItem(path, 8, 4, path.stat().st_size, export_to_x=True))
    attempts = 0

    def alternating(request, *, timeout):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise URLError("first failed")
        return Response(b'{"publicUrl": "https://pub-example.r2.dev/two.jpg"}')

    result = BatchProcessor(
        sources,
        tmp_path / "out",
        watermark_enabled=False,
        watermark_catalog=WatermarkCatalog(),
        r2_upload_service=R2UploadService(
            "https://worker.example/upload", opener=alternating
        ),
    ).process()

    assert [upload.success for upload in result.uploads] == [False, True]
    assert all(export.status is ExportStatus.SUCCEEDED for export in result.exports)
    assert all(export.output_path.is_file() for export in result.exports)
    assert result.statistics.successful_output_count == 2

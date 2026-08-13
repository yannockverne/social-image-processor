"""HTTP client for uploading finalized exports through a Cloudflare Worker."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Protocol
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from app.models.results import R2UploadResult


class HTTPResponse(Protocol):
    status: int

    def __enter__(self): ...
    def __exit__(self, *args): ...
    def read(self) -> bytes: ...
    def geturl(self) -> str: ...


class R2UploadService:
    """Upload local files with PUT; contains all transport-specific behavior."""

    def __init__(
        self,
        worker_url: str,
        *,
        remote_prefix: str = "",
        opener=urlopen,
        timeout: float = 30.0,
    ) -> None:
        self.worker_url = worker_url.strip()
        self.remote_prefix = remote_prefix.strip().strip("/")
        self._opener = opener
        self._timeout = timeout

    @property
    def validation_error(self) -> str:
        parsed = urlsplit(self.worker_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return "Worker URL must be a valid HTTP or HTTPS URL."
        if parsed.query or parsed.fragment:
            return "Worker URL must not contain a query string or fragment."
        return ""

    def object_key(self, local_path: Path) -> str:
        """Return a deterministic, traversal-safe key based on the export name."""
        name = Path(local_path).name
        return (
            str(PurePosixPath(self.remote_prefix, name)) if self.remote_prefix else name
        )

    def upload(self, local_path: Path) -> R2UploadResult:
        path = Path(local_path)
        key = self.object_key(path)
        if error := self.validation_error:
            return R2UploadResult(path, key, False, error_message=error)
        parsed = urlsplit(self.worker_url)
        base_path = parsed.path.rstrip("/")
        encoded_key = "/".join(quote(part, safe="") for part in key.split("/"))
        target = urlunsplit(
            (parsed.scheme, parsed.netloc, f"{base_path}/{encoded_key}", "", "")
        )
        try:
            request = Request(
                target,
                data=path.read_bytes(),
                method="PUT",
                headers={"Content-Type": "image/jpeg"},
            )
            with self._opener(request, timeout=self._timeout) as response:
                response.read()
                status = response.status
                if not 200 <= status < 300:
                    raise RuntimeError(f"HTTP {status}")
                public_url = response.geturl() or target
            return R2UploadResult(path, key, True, public_url)
        except Exception as error:
            return R2UploadResult(
                path, key, False, error_message=f"{type(error).__name__}: {error}"
            )

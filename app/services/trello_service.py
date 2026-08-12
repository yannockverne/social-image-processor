"""Synchronous, testable Trello operations and Windows credential storage.

The UI runs service calls through its existing Qt worker pool. The standard
library HTTP client handles browsing and explicit attachment uploads without a
new runtime dependency. On Windows credentials are stored by Credential Manager,
not in the application's JSON settings.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import sys
from pathlib import Path
import mimetypes
import uuid
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.models.trello import (
    TrelloAttachmentResult,
    TrelloBoard,
    TrelloCard,
    TrelloCredentials,
    TrelloList,
)


class TrelloError(RuntimeError):
    """Human-readable Trello connection or API failure."""


class CredentialStore(Protocol):
    def load(self) -> TrelloCredentials | None: ...

    def save(self, credentials: TrelloCredentials) -> None: ...


class WindowsCredentialStore:
    """Store a compact credential payload in the current user's Windows vault."""

    target = "SocialImageProcessor/Trello"

    def _ensure_windows(self) -> None:
        if sys.platform != "win32":
            raise TrelloError("Trello credential storage is available on Windows only.")

    def save(self, credentials: TrelloCredentials) -> None:
        self._ensure_windows()
        payload = json.dumps(
            {"api_key": credentials.api_key, "token": credentials.token}
        ).encode("utf-16-le")

        class CREDENTIAL(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD),
                ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR),
                ("LastWritten", wintypes.FILETIME),
                ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR),
            ]

        blob = (ctypes.c_ubyte * len(payload)).from_buffer_copy(payload)
        credential = CREDENTIAL(
            0,
            1,
            self.target,
            None,
            wintypes.FILETIME(),
            len(payload),
            blob,
            2,
            0,
            None,
            None,
            "Trello",
        )
        if not ctypes.windll.advapi32.CredWriteW(ctypes.byref(credential), 0):
            raise TrelloError(
                "Windows Credential Manager could not save Trello credentials."
            )

    def load(self) -> TrelloCredentials | None:
        self._ensure_windows()

        class CREDENTIAL(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD),
                ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR),
                ("LastWritten", wintypes.FILETIME),
                ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR),
            ]

        pointer = ctypes.POINTER(CREDENTIAL)()
        if not ctypes.windll.advapi32.CredReadW(
            self.target, 1, 0, ctypes.byref(pointer)
        ):
            return None
        try:
            raw = ctypes.string_at(
                pointer.contents.CredentialBlob, pointer.contents.CredentialBlobSize
            )
            value = json.loads(raw.decode("utf-16-le"))
            return TrelloCredentials(value["api_key"], value["token"])
        except (KeyError, UnicodeError, json.JSONDecodeError) as error:
            raise TrelloError("Stored Trello credentials are invalid.") from error
        finally:
            ctypes.windll.advapi32.CredFree(pointer)


class TrelloService:
    base_url = "https://api.trello.com/1"

    def __init__(self, credentials: TrelloCredentials, timeout: float = 15) -> None:
        self.credentials = credentials
        self.timeout = timeout

    def _get(self, path: str, **parameters) -> list[dict]:
        query = urlencode(
            {
                **parameters,
                "key": self.credentials.api_key,
                "token": self.credentials.token,
            }
        )
        request = Request(
            f"{self.base_url}{path}?{query}", headers={"Accept": "application/json"}
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                value = json.load(response)
        except HTTPError as error:
            if error.code in (401, 403):
                raise TrelloError(
                    "Trello authentication failed. Check the API key and token."
                ) from error
            raise TrelloError(f"Trello API error ({error.code}).") from error
        except (URLError, TimeoutError, OSError) as error:
            raise TrelloError(
                "Trello is unavailable. Check the network connection."
            ) from error
        except (json.JSONDecodeError, UnicodeError) as error:
            raise TrelloError("Trello returned an invalid response.") from error
        if not isinstance(value, list):
            raise TrelloError("Trello returned an unexpected response.")
        return value

    @staticmethod
    def _raise_transport_error(error: Exception) -> None:
        if isinstance(error, HTTPError):
            if error.code in (401, 403):
                raise TrelloError(
                    "Trello authentication failed. Check the API key and token."
                ) from error
            raise TrelloError(f"Trello API error ({error.code}).") from error
        raise TrelloError(
            "Trello is unavailable. Check the network connection."
        ) from error

    def list_boards(self) -> list[TrelloBoard]:
        return [
            TrelloBoard(item["id"], item["name"])
            for item in self._get("/members/me/boards", fields="name", filter="open")
        ]

    def list_lists(self, board_id: str) -> list[TrelloList]:
        return [
            TrelloList(item["id"], item["name"])
            for item in self._get(
                f"/boards/{board_id}/lists", fields="name", filter="open"
            )
        ]

    def list_cards(self, list_id: str) -> list[TrelloCard]:
        return [
            TrelloCard(item["id"], item["name"])
            for item in self._get(
                f"/lists/{list_id}/cards", fields="name", filter="open"
            )
        ]

    def upload_attachment(self, card_id: str, path: Path) -> None:
        """Attach one existing processed file to *card_id* using multipart POST."""
        path = Path(path)
        if not path.is_file():
            raise TrelloError(f"Processed file is unavailable: {path.name}")
        boundary = f"sip-{uuid.uuid4().hex}"
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        body = (
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode()
            + path.read_bytes()
            + f"\r\n--{boundary}--\r\n".encode()
        )
        query = urlencode(
            {"key": self.credentials.api_key, "token": self.credentials.token}
        )
        request = Request(
            f"{self.base_url}/cards/{card_id}/attachments?{query}",
            data=body,
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                json.load(response)
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            self._raise_transport_error(error)
        except (json.JSONDecodeError, UnicodeError) as error:
            raise TrelloError("Trello returned an invalid response.") from error

    def upload_attachments(
        self, card_id: str, paths: list[Path] | tuple[Path, ...]
    ) -> list[TrelloAttachmentResult]:
        """Upload each unique path independently and retain every outcome."""
        results = []
        seen: set[str] = set()
        for path in map(Path, paths):
            identity = str(path.resolve()).casefold()
            if identity in seen:
                continue
            seen.add(identity)
            try:
                self.upload_attachment(card_id, path)
                results.append(TrelloAttachmentResult(path, True))
            except Exception as error:
                results.append(TrelloAttachmentResult(path, False, str(error)))
        return results

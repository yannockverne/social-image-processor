"""Synchronous, testable Trello operations and Windows credential storage.

The UI runs service calls through its existing Qt worker pool. The standard
library HTTP client handles browsing and card description updates without a new
runtime dependency. On Windows credentials are stored by Credential Manager,
not in the application's JSON settings.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import sys
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.models.trello import (
    TrelloBoard,
    TrelloCard,
    TrelloCredentials,
    TrelloChecklistSyncResult,
    TrelloList,
)

PREPARATION_LIST_NAME = "🛠️ À préparer"
PUBLICATION_CHECKLIST_NAME = "Publication"
PUBLICATION_CHECKLIST_ITEMS = (
    "Photos",
    "Image selection",
    "Retouching",
    "Instagram + X copy",
    "X post published",
    "Instagram post published",
)
PROCESSING_CHECKLIST_ITEMS = PUBLICATION_CHECKLIST_ITEMS[:3]


def build_post_description(x_text: str, instagram_text: str) -> str:
    """Build the stable Trello description without manufacturing missing copy."""
    return f"## X\n\n{x_text}\n\n## Insta\n\n{instagram_text}\n"


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

    def _post(self, path: str, **parameters) -> dict:
        query = urlencode(
            {
                **parameters,
                "key": self.credentials.api_key,
                "token": self.credentials.token,
            }
        )
        request = Request(f"{self.base_url}{path}?{query}", method="POST")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                value = json.load(response)
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            self._raise_transport_error(error)
        except (json.JSONDecodeError, UnicodeError) as error:
            raise TrelloError("Trello returned an invalid response.") from error
        if not isinstance(value, dict):
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

    def create_post_card(
        self, board_id: str, title: str, x_text: str, instagram_text: str
    ) -> TrelloCard:
        """Create a post card and its complete, initially-unchecked checklist."""
        destination = next(
            (
                item
                for item in self.list_lists(board_id)
                if item.name == PREPARATION_LIST_NAME
            ),
            None,
        )
        if destination is None:
            raise TrelloError(
                f'Destination list "{PREPARATION_LIST_NAME}" was not found.'
            )

        value = self._post(
            "/cards",
            idList=destination.id,
            name=title,
            desc=build_post_description(x_text, instagram_text),
        )
        card_id, card_name = value.get("id"), value.get("name")
        if not isinstance(card_id, str) or not isinstance(card_name, str):
            raise TrelloError("Trello returned an invalid card creation response.")

        try:
            checklist = self._post(
                f"/cards/{card_id}/checklists", name=PUBLICATION_CHECKLIST_NAME
            )
            checklist_id = checklist.get("id")
            if not isinstance(checklist_id, str):
                raise TrelloError("Trello returned an invalid checklist response.")
            for item in PUBLICATION_CHECKLIST_ITEMS:
                self._post(
                    f"/checklists/{checklist_id}/checkItems",
                    name=item,
                    checked="false",
                )
        except Exception as error:
            raise TrelloError(
                f'Card "{card_name}" was created, but its publication checklist '
                f"could not be completed: {error}"
            ) from error
        return TrelloCard(card_id, card_name)

    def get_card_description(self, card_id: str) -> str:
        query = urlencode(
            {
                "fields": "desc",
                "key": self.credentials.api_key,
                "token": self.credentials.token,
            }
        )
        request = Request(
            f"{self.base_url}/cards/{card_id}?{query}",
            headers={"Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                value = json.load(response)
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            self._raise_transport_error(error)
        except (json.JSONDecodeError, UnicodeError) as error:
            raise TrelloError("Trello returned an invalid response.") from error
        if not isinstance(value, dict) or not isinstance(value.get("desc", ""), str):
            raise TrelloError("Trello returned an unexpected response.")
        return value.get("desc", "")

    def update_card_description(self, card_id: str, description: str) -> None:
        query = urlencode(
            {
                "key": self.credentials.api_key,
                "token": self.credentials.token,
                "desc": description,
            }
        )
        request = Request(f"{self.base_url}/cards/{card_id}?{query}", method="PUT")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                json.load(response)
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            self._raise_transport_error(error)
        except (json.JSONDecodeError, UnicodeError) as error:
            raise TrelloError("Trello returned an invalid response.") from error

    def complete_processing_checklist(self, card_id: str) -> TrelloChecklistSyncResult:
        """Complete canonical processing items without changing card structure.

        Update failures are collected per item so one failed request does not stop
        the remaining canonical items from being attempted. Checklist read
        failures remain service errors for the caller to report.
        """
        checklists = self._get(f"/cards/{card_id}/checklists")
        checklist = next(
            (
                value
                for value in checklists
                if value.get("name") == PUBLICATION_CHECKLIST_NAME
                and isinstance(value.get("checkItems"), list)
            ),
            None,
        )
        if checklist is None:
            return TrelloChecklistSyncResult(missing=PROCESSING_CHECKLIST_ITEMS)

        items_by_name = {
            item.get("name"): item
            for item in checklist["checkItems"]
            if isinstance(item, dict)
        }
        completed: list[str] = []
        already_complete: list[str] = []
        missing: list[str] = []
        failed: list[str] = []
        for name in PROCESSING_CHECKLIST_ITEMS:
            item = items_by_name.get(name)
            if item is None or not isinstance(item.get("id"), str):
                missing.append(name)
            elif item.get("state") == "complete":
                already_complete.append(name)
            else:
                try:
                    self._put(
                        f"/cards/{card_id}/checkItem/{item['id']}", state="complete"
                    )
                    completed.append(name)
                except TrelloError:
                    failed.append(name)
        return TrelloChecklistSyncResult(
            tuple(completed),
            tuple(already_complete),
            tuple(missing),
            tuple(failed),
        )

    def _put(self, path: str, **parameters) -> dict:
        query = urlencode(
            {
                **parameters,
                "key": self.credentials.api_key,
                "token": self.credentials.token,
            }
        )
        request = Request(f"{self.base_url}{path}?{query}", method="PUT")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                value = json.load(response)
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            self._raise_transport_error(error)
        except (json.JSONDecodeError, UnicodeError) as error:
            raise TrelloError("Trello returned an invalid response.") from error
        if not isinstance(value, dict):
            raise TrelloError("Trello returned an unexpected response.")
        return value

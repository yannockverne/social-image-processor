"""Small immutable models used at the Trello integration boundary."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class TrelloCredentials:
    api_key: str
    token: str


@dataclass(frozen=True, slots=True)
class TrelloBoard:
    id: str
    name: str


@dataclass(frozen=True, slots=True)
class TrelloList:
    id: str
    name: str


@dataclass(frozen=True, slots=True)
class TrelloCard:
    id: str
    name: str
    url: str | None = None


@dataclass(frozen=True, slots=True)
class TrelloChecklistSyncResult:
    """Outcome of completing the processing items on an existing checklist."""

    completed: tuple[str, ...] = ()
    already_complete: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TrelloAttachmentResult:
    """Per-file outcome so a multi-file upload can report partial failure."""

    path: Path
    succeeded: bool
    message: str = ""

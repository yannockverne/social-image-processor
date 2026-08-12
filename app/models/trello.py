"""Small immutable models used at the Trello integration boundary."""

from __future__ import annotations

from dataclasses import dataclass


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

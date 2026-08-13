"""Manage the application-owned URL block in a Trello description."""

from __future__ import annotations

import re
from collections.abc import Iterable

HEADING = "## URL MAKE"
_SECTION = re.compile(
    r"(?m)^## URL MAKE[ \t]*(?:\r?\n|$).*?"
    r"(?=^(?:[ \t]*\r?\n)*##(?:[ \t]|$)|\Z)",
    re.DOTALL,
)


def replace_url_make_section(description: str, urls: Iterable[str]) -> str:
    """Return *description* with exactly one managed section containing *urls*.

    Text outside the managed section is byte-for-byte preserved. Callers should
    avoid invoking this function with no usable URLs when an old block must stay.
    """
    block = HEADING + "\n" + "\n".join(urls) + "\n"
    match = _SECTION.search(description)
    if match:
        return description[: match.start()] + block + description[match.end() :]
    if not description:
        return block
    separator = (
        ""
        if description.endswith("\n\n")
        else ("\n" if description.endswith("\n") else "\n\n")
    )
    return description + separator + block

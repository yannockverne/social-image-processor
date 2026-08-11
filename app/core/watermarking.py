"""Exact-resolution watermark catalog behavior."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

from app.models.watermark import WatermarkMatch, WatermarkStatus

Dimensions = tuple[int, int]


class WatermarkCatalog:
    """Immutable lookup of watermark paths by raw stored dimensions."""

    def __init__(
        self, entries: Mapping[Dimensions, Iterable[Path]] | None = None
    ) -> None:
        entries = entries or {}
        self._entries = {
            dimensions: tuple(sorted(paths, key=_path_sort_key))
            for dimensions, paths in entries.items()
        }

    @property
    def entries(self) -> Mapping[Dimensions, tuple[Path, ...]]:
        """Return a read-only snapshot of the catalog entries."""
        return dict(self._entries)

    def match(self, dimensions: Dimensions) -> WatermarkMatch:
        """Classify *dimensions* as exact, missing, or ambiguous."""
        paths = self._entries.get(dimensions, ())
        if not paths:
            status = WatermarkStatus.MISSING
        elif len(paths) == 1:
            status = WatermarkStatus.EXACT
        else:
            status = WatermarkStatus.AMBIGUOUS
        return WatermarkMatch(status=status, dimensions=dimensions, paths=paths)


def _path_sort_key(path: Path) -> tuple[str, str]:
    """Provide stable, case-insensitive ordering with a deterministic tie-break."""
    name = path.name
    return name.casefold(), name

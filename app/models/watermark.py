"""Models describing exact-resolution watermark matching."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class WatermarkStatus(StrEnum):
    """Result of matching one source size against the watermark catalog."""

    EXACT = "exact"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class WatermarkMatch:
    """All watermark candidates for one pair of raw pixel dimensions."""

    status: WatermarkStatus
    dimensions: tuple[int, int]
    paths: tuple[Path, ...] = ()

    @property
    def exact_path(self) -> Path | None:
        """Return the sole exact match, if one exists."""
        if self.status is WatermarkStatus.EXACT and len(self.paths) == 1:
            return self.paths[0]
        return None

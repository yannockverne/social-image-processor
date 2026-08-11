"""Model for a discovered source image."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.models.watermark import WatermarkMatch


@dataclass(frozen=True, slots=True)
class ImageItem:
    """Metadata and user selections for one source image.

    Pixel data is deliberately not retained in this model so a populated image
    list cannot keep every full-resolution source in memory.
    """

    path: Path
    width: int
    height: int
    size_bytes: int
    export_to_x: bool = False
    export_to_instagram: bool = False
    watermark_match: WatermarkMatch | None = None

    @property
    def dimensions(self) -> tuple[int, int]:
        """Return raw stored pixel dimensions as ``(width, height)``."""
        return self.width, self.height

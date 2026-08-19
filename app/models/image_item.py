"""Model for a discovered source image."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.models.watermark import WatermarkMatch


# Instagram accepts feed images from portrait 4:5 through landscape 1.91:1.
INSTAGRAM_MIN_ASPECT_RATIO = 4 / 5
INSTAGRAM_MAX_ASPECT_RATIO = 1.91

# Resolutions marketed as 21:9 do not all share the mathematical 7:3 ratio.
# This narrow band covers both 64:27 (for example, 2560x1080) and common
# 43:18 captures (3440x1440), while keeping ordinary widescreen images out.
ULTRAWIDE_MIN_ASPECT_RATIO = 7 / 3
ULTRAWIDE_MAX_ASPECT_RATIO = 12 / 5


def is_instagram_ratio_supported(width: int, height: int) -> bool:
    """Return whether valid dimensions are in Instagram's feed image range."""
    if width <= 0 or height <= 0:
        return False
    ratio = width / height
    return INSTAGRAM_MIN_ASPECT_RATIO <= ratio <= INSTAGRAM_MAX_ASPECT_RATIO


def is_21_9_ratio(width: int, height: int) -> bool:
    """Return whether valid dimensions are in the practical 21:9 range."""
    if width <= 0 or height <= 0:
        return False
    ratio = width / height
    return ULTRAWIDE_MIN_ASPECT_RATIO <= ratio <= ULTRAWIDE_MAX_ASPECT_RATIO


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

"""Persisted application settings model."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEFAULT_JPEG_QUALITY = 92
MIN_JPEG_QUALITY = 70
MAX_JPEG_QUALITY = 100
DEFAULT_BACKGROUND_COLOR = "#000000"


@dataclass(frozen=True, slots=True)
class ApplicationSettings:
    """Locally persisted, non-secret application preferences."""

    input_directory: Path | None = None
    output_directory: Path | None = None
    watermark_directory: Path | None = None
    jpeg_quality: int = DEFAULT_JPEG_QUALITY
    watermark_enabled: bool = True
    background_color: str = DEFAULT_BACKGROUND_COLOR
    selected_watermark: str | None = None

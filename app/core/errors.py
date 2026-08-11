"""Typed errors raised by core image operations."""

from __future__ import annotations

from pathlib import Path


class ImageProcessingError(Exception):
    """Base class for expected image-processing failures."""


class DimensionMismatchError(ImageProcessingError):
    """Raised when a full-frame watermark does not exactly fit its source."""

    def __init__(
        self,
        source_size: tuple[int, int],
        watermark_size: tuple[int, int],
    ) -> None:
        self.source_size = source_size
        self.watermark_size = watermark_size
        super().__init__(
            "Watermark dimensions "
            f"{watermark_size[0]}x{watermark_size[1]} do not match source "
            f"dimensions {source_size[0]}x{source_size[1]}"
        )


class OutputWriteError(ImageProcessingError):
    """Raised when a completed JPEG cannot be safely written."""

    def __init__(self, output_path: Path, reason: BaseException) -> None:
        self.output_path = output_path
        self.reason = reason
        super().__init__(f"Could not write JPEG to {output_path}: {reason}")

"""Structured processing result models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from app.models.profiles import ExportPlatform


class ExportStatus(StrEnum):
    """Outcome of an attempted source or platform export."""

    SUCCEEDED = "succeeded"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ExportResult:
    """Outcome for one requested platform output."""

    source_path: Path
    platform: ExportPlatform
    status: ExportStatus
    output_path: Path | None = None
    output_size_bytes: int = 0
    message: str = ""


@dataclass(frozen=True, slots=True)
class BatchResult:
    """Final aggregate returned by a future batch processor."""

    exports: tuple[ExportResult, ...] = field(default_factory=tuple)
    processed_source_size_bytes: int = 0
    output_size_bytes: int = 0

    @property
    def bytes_saved(self) -> int:
        """Return the signed difference between source and output sizes."""
        return self.processed_source_size_bytes - self.output_size_bytes

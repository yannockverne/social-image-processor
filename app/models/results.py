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
class R2UploadResult:
    """Independent upload outcome, suitable for later Trello integration."""

    local_path: Path
    object_key: str
    success: bool
    public_url: str | None = None
    error_message: str = ""


@dataclass(frozen=True, slots=True)
class SuccessfulOutput:
    """Event emitted after one platform file is finalized."""

    result: ExportResult


@dataclass(frozen=True, slots=True)
class R2UploadStarted:
    local_path: Path
    object_key: str


@dataclass(frozen=True, slots=True)
class R2UploadFinished:
    result: R2UploadResult


@dataclass(frozen=True, slots=True)
class SkippedSource:
    """Event emitted when safety rules skip all exports for a source."""

    source_path: Path
    message: str


@dataclass(frozen=True, slots=True)
class FailedSource:
    """Event emitted when a source cannot be prepared."""

    source_path: Path
    message: str


@dataclass(frozen=True, slots=True)
class FailedExport:
    """Event emitted when only one requested platform export fails."""

    result: ExportResult


@dataclass(frozen=True, slots=True)
class ProgressUpdate:
    """Monotonic selected-source progress."""

    completed: int
    total: int
    source_path: Path


@dataclass(frozen=True, slots=True)
class BatchStatistics:
    """Approved source-once/output-every-file accounting totals."""

    processed_source_count: int = 0
    successful_output_count: int = 0
    processed_source_size_bytes: int = 0
    output_size_bytes: int = 0

    @property
    def bytes_saved(self) -> int:
        return self.processed_source_size_bytes - self.output_size_bytes

    @property
    def reduction_percentage(self) -> float:
        if self.processed_source_size_bytes == 0:
            return 0.0
        return self.bytes_saved / self.processed_source_size_bytes * 100


BatchEvent = (
    SuccessfulOutput
    | SkippedSource
    | FailedSource
    | FailedExport
    | ProgressUpdate
    | BatchStatistics
    | R2UploadStarted
    | R2UploadFinished
)


@dataclass(frozen=True, slots=True)
class BatchResult:
    """Final aggregate returned by the batch processor."""

    exports: tuple[ExportResult, ...] = field(default_factory=tuple)
    events: tuple[BatchEvent, ...] = field(default_factory=tuple)
    statistics: BatchStatistics = field(default_factory=BatchStatistics)
    uploads: tuple[R2UploadResult, ...] = field(default_factory=tuple)

    @property
    def processed_source_size_bytes(self) -> int:
        return self.statistics.processed_source_size_bytes

    @property
    def output_size_bytes(self) -> int:
        return self.statistics.output_size_bytes

    @property
    def bytes_saved(self) -> int:
        """Return the signed difference between source and output sizes."""
        return self.statistics.bytes_saved

    @property
    def reduction_percentage(self) -> float:
        return self.statistics.reduction_percentage

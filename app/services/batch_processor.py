"""Synchronous, Qt-independent batch processing orchestration."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from app.core.image_processing import export_prepared_jpeg, prepare_jpeg
from app.core.output_naming import OutputNameAllocator
from app.core.watermarking import WatermarkCatalog
from app.models.image_item import ImageItem
from app.models.profiles import ExportPlatform
from app.models.results import (
    BatchEvent,
    BatchResult,
    BatchStatistics,
    ExportResult,
    ExportStatus,
    FailedExport,
    FailedSource,
    ProgressUpdate,
    SkippedSource,
    SuccessfulOutput,
)
from app.models.watermark import WatermarkStatus

EventCallback = Callable[[BatchEvent], None]


class BatchProcessor:
    """Process immutable source selections while isolating individual failures."""

    def __init__(
        self,
        sources: Iterable[ImageItem],
        output_directory: Path,
        *,
        watermark_enabled: bool,
        watermark_catalog: WatermarkCatalog,
        jpeg_quality: int = 92,
        background: str | tuple[int, int, int] = "#000000",
    ) -> None:
        self._sources = tuple(sources)
        self._output_directory = Path(output_directory)
        self._watermark_enabled = watermark_enabled
        self._watermark_catalog = WatermarkCatalog(watermark_catalog.entries)
        self._jpeg_quality = jpeg_quality
        self._background = background

    def process(self, on_event: EventCallback | None = None) -> BatchResult:
        """Run the captured batch and return all outcomes and accounting data."""
        selected = tuple(item for item in self._sources if _platforms(item))
        allocator = OutputNameAllocator(self._output_directory)
        exports: list[ExportResult] = []
        events: list[BatchEvent] = []
        successful_sources = 0
        source_bytes = 0
        output_bytes = 0

        def emit(event: BatchEvent) -> None:
            events.append(event)
            if on_event is not None:
                on_event(event)

        for completed, item in enumerate(selected, start=1):
            platforms = _platforms(item)
            watermark_path: Path | None = None
            try:
                if self._watermark_enabled:
                    match = self._watermark_catalog.match(item.dimensions)
                    if match.status is not WatermarkStatus.EXACT:
                        reason = (
                            f"watermark enabled but exact {item.width}x{item.height} "
                            f"match is {match.status.value}"
                        )
                        emit(SkippedSource(item.path, reason))
                        emit(ProgressUpdate(completed, len(selected), item.path))
                        continue
                    watermark_path = match.exact_path

                prepared = prepare_jpeg(
                    item.path,
                    watermark_path=watermark_path,
                    background=self._background,
                )
            except Exception as error:
                emit(FailedSource(item.path, str(error)))
                emit(ProgressUpdate(completed, len(selected), item.path))
                continue

            source_succeeded = False
            for platform in platforms:
                try:
                    output_path = allocator.allocate(item.path, platform)
                    generated = export_prepared_jpeg(
                        prepared, output_path, quality=self._jpeg_quality
                    )
                    result = ExportResult(
                        item.path,
                        platform,
                        ExportStatus.SUCCEEDED,
                        generated.path,
                        generated.size_bytes,
                    )
                    exports.append(result)
                    output_bytes += generated.size_bytes
                    source_succeeded = True
                    emit(SuccessfulOutput(result))
                except Exception as error:
                    result = ExportResult(
                        item.path,
                        platform,
                        ExportStatus.FAILED,
                        message=str(error),
                    )
                    exports.append(result)
                    emit(FailedExport(result))

            if source_succeeded:
                successful_sources += 1
                source_bytes += item.size_bytes
            emit(ProgressUpdate(completed, len(selected), item.path))

        statistics = BatchStatistics(
            successful_sources,
            sum(result.status is ExportStatus.SUCCEEDED for result in exports),
            source_bytes,
            output_bytes,
        )
        emit(statistics)
        return BatchResult(tuple(exports), tuple(events), statistics)


def _platforms(item: ImageItem) -> tuple[ExportPlatform, ...]:
    platforms: list[ExportPlatform] = []
    if item.export_to_x:
        platforms.append(ExportPlatform.X)
    if item.export_to_instagram:
        platforms.append(ExportPlatform.INSTAGRAM)
    return tuple(platforms)

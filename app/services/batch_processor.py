"""Synchronous, Qt-independent batch processing orchestration."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from urllib.parse import urlsplit

from app.core.image_processing import export_prepared_jpeg, prepare_jpeg
from app.core.output_naming import OutputNameAllocator
from app.core.watermarking import DEFAULT_WATERMARK_SIZE_RATIO, WatermarkCatalog
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
    R2UploadFinished,
    R2UploadResult,
    R2UploadStarted,
    SkippedSource,
    SuccessfulOutput,
)
from app.models.watermark import WatermarkStatus
from app.services.r2_upload_service import R2UploadService
from app.services.url_make import replace_url_make_section

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
        selected_watermark: str | Path | None = None,
        watermark_size_ratio: float = DEFAULT_WATERMARK_SIZE_RATIO,
        jpeg_quality: int = 92,
        background: str | tuple[int, int, int] = "#000000",
        r2_upload_service: R2UploadService | None = None,
        trello_service=None,
        trello_card_id: str | None = None,
    ) -> None:
        self._sources = tuple(sources)
        self._output_directory = Path(output_directory)
        self._watermark_enabled = watermark_enabled
        self._watermark_catalog = WatermarkCatalog(watermark_catalog.paths)
        self._selected_watermark = selected_watermark
        self._watermark_size_ratio = watermark_size_ratio
        self._jpeg_quality = jpeg_quality
        self._background = background
        self._r2_upload_service = r2_upload_service
        self._trello_service = trello_service
        self._trello_card_id = trello_card_id

    def process(self, on_event: EventCallback | None = None) -> BatchResult:
        """Run the captured batch and return all outcomes and accounting data."""
        selected = tuple(item for item in self._sources if _platforms(item))
        allocator = OutputNameAllocator(self._output_directory)
        exports: list[ExportResult] = []
        uploads = []
        events: list[BatchEvent] = []
        successful_sources = 0
        source_bytes = 0
        output_bytes = 0
        platform_numbers = {ExportPlatform.X: 0, ExportPlatform.INSTAGRAM: 0}

        def emit(event: BatchEvent) -> None:
            events.append(event)
            if on_event is not None:
                on_event(event)

        for completed, item in enumerate(selected, start=1):
            platforms = _platforms(item)
            sequence_numbers = {}
            for platform in platforms:
                platform_numbers[platform] += 1
                sequence_numbers[platform] = platform_numbers[platform]
            watermark_path: Path | None = None
            try:
                if self._watermark_enabled:
                    match = self._watermark_catalog.match(
                        item.dimensions, self._selected_watermark
                    )
                    if match.status is not WatermarkStatus.EXACT:
                        reason = "watermark enabled but no valid watermark design is selected"
                        emit(SkippedSource(item.path, reason))
                        emit(ProgressUpdate(completed, len(selected), item.path))
                        continue
                    watermark_path = match.exact_path

                prepared = prepare_jpeg(
                    item.path,
                    watermark_path=watermark_path,
                    background=self._background,
                    watermark_size_ratio=self._watermark_size_ratio,
                )
            except Exception as error:
                emit(FailedSource(item.path, str(error)))
                emit(ProgressUpdate(completed, len(selected), item.path))
                continue

            source_succeeded = False
            for platform in platforms:
                try:
                    output_path = allocator.allocate(
                        platform, sequence_numbers[platform]
                    )
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
                    if self._r2_upload_service is not None:
                        try:
                            key = self._r2_upload_service.object_key(generated.path)
                            emit(R2UploadStarted(generated.path, key))
                            upload = self._r2_upload_service.upload(generated.path)
                        except Exception as error:
                            upload = R2UploadResult(
                                generated.path,
                                generated.path.name,
                                False,
                                error_message=f"{type(error).__name__}: {error}",
                            )
                        uploads.append(upload)
                        emit(R2UploadFinished(upload))
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
        trello_urls_updated = 0
        trello_error = ""
        urls = [_usable_public_url(upload) for upload in uploads]
        urls = [url for url in urls if url is not None]
        if self._trello_service is not None and self._trello_card_id and urls:
            try:
                description = self._trello_service.get_card_description(
                    self._trello_card_id
                )
                self._trello_service.update_card_description(
                    self._trello_card_id,
                    replace_url_make_section(description, urls),
                )
                trello_urls_updated = len(urls)
            except Exception as error:
                trello_error = f"{type(error).__name__}: {error}"
        return BatchResult(
            tuple(exports),
            tuple(events),
            statistics,
            tuple(uploads),
            trello_urls_updated,
            trello_error,
        )


def _platforms(item: ImageItem) -> tuple[ExportPlatform, ...]:
    platforms: list[ExportPlatform] = []
    if item.export_to_x:
        platforms.append(ExportPlatform.X)
    if item.export_to_instagram:
        platforms.append(ExportPlatform.INSTAGRAM)
    return tuple(platforms)


def _usable_public_url(upload: R2UploadResult) -> str | None:
    if not upload.success or not isinstance(upload.public_url, str):
        return None
    value = upload.public_url.strip()
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return value

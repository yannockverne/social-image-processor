"""Non-recursive source and watermark folder discovery."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.core.watermarking import Dimensions, WatermarkCatalog
from app.models.image_item import ImageItem

SUPPORTED_SOURCE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg"})
SUPPORTED_WATERMARK_SUFFIXES = frozenset({".png"})


@dataclass(frozen=True, slots=True)
class ScanIssue:
    """A file or folder that could not be inspected during discovery."""

    path: Path
    message: str


@dataclass(frozen=True, slots=True)
class WatermarkScanResult:
    """A usable catalog plus isolated watermark scan issues."""

    catalog: WatermarkCatalog
    issues: tuple[ScanIssue, ...] = ()


@dataclass(frozen=True, slots=True)
class SourceScanResult:
    """Valid source metadata plus isolated source scan issues."""

    images: tuple[ImageItem, ...] = ()
    issues: tuple[ScanIssue, ...] = ()


def scan_watermark_folder(folder: Path) -> WatermarkScanResult:
    """Build a dimension-keyed catalog from immediate PNG children of *folder*."""
    candidates, folder_issue = _candidate_files(folder, SUPPORTED_WATERMARK_SUFFIXES)
    if folder_issue is not None:
        return WatermarkScanResult(WatermarkCatalog(), (folder_issue,))

    entries: defaultdict[Dimensions, list[Path]] = defaultdict(list)
    issues: list[ScanIssue] = []
    for path in candidates:
        try:
            dimensions = _read_dimensions(path)
        except _IMAGE_ERRORS as error:
            issues.append(ScanIssue(path, _describe_error(error)))
            continue
        entries[dimensions].append(path)

    return WatermarkScanResult(WatermarkCatalog(entries), tuple(issues))


def scan_input_folder(
    folder: Path, watermark_catalog: WatermarkCatalog
) -> SourceScanResult:
    """Read metadata for immediate supported image children of *folder*."""
    candidates, folder_issue = _candidate_files(folder, SUPPORTED_SOURCE_SUFFIXES)
    if folder_issue is not None:
        return SourceScanResult(issues=(folder_issue,))

    images: list[ImageItem] = []
    issues: list[ScanIssue] = []
    for path in candidates:
        try:
            dimensions = _read_dimensions(path)
            size_bytes = path.stat().st_size
        except _IMAGE_ERRORS as error:
            issues.append(ScanIssue(path, _describe_error(error)))
            continue

        images.append(
            ImageItem(
                path=path,
                width=dimensions[0],
                height=dimensions[1],
                size_bytes=size_bytes,
                watermark_match=watermark_catalog.match(dimensions),
            )
        )

    return SourceScanResult(tuple(images), tuple(issues))


def _candidate_files(
    folder: Path, supported_suffixes: frozenset[str]
) -> tuple[list[Path], ScanIssue | None]:
    """Return sorted immediate files, converting root failures into one issue."""
    try:
        candidates = [
            path
            for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() in supported_suffixes
        ]
    except OSError as error:
        return [], ScanIssue(folder, _describe_error(error))
    candidates.sort(key=lambda path: (path.name.casefold(), path.name))
    return candidates, None


def _read_dimensions(path: Path) -> Dimensions:
    """Read raw stored dimensions and verify file integrity without retaining pixels."""
    with Image.open(path) as image:
        dimensions = image.size
        image.verify()
    return dimensions


def _describe_error(error: BaseException) -> str:
    detail = str(error).strip()
    return f"{type(error).__name__}: {detail}" if detail else type(error).__name__


_IMAGE_ERRORS = (OSError, ValueError, UnidentifiedImageError)

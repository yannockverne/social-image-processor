from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

Image = pytest.importorskip("PIL.Image")

import app.services.batch_processor as batch_module  # noqa: E402
from app.core.errors import OutputWriteError  # noqa: E402
from app.core.watermarking import WatermarkCatalog  # noqa: E402
from app.models.image_item import ImageItem  # noqa: E402
from app.models.profiles import ExportPlatform  # noqa: E402
from app.models.results import (  # noqa: E402
    BatchStatistics,
    ExportStatus,
    FailedExport,
    FailedSource,
    ProgressUpdate,
    SkippedSource,
)
from app.services.batch_processor import BatchProcessor  # noqa: E402


def _source(
    path: Path, *, x: bool = False, instagram: bool = False, size: int | None = None
) -> ImageItem:
    return ImageItem(path, 8, 4, path.stat().st_size if size is None else size, x, instagram)


def _run(
    sources: list[ImageItem], output: Path, catalog: WatermarkCatalog | None = None, **kwargs: object
):
    return BatchProcessor(
        sources,
        output,
        watermark_enabled=bool(kwargs.pop("watermark_enabled", False)),
        watermark_catalog=catalog or WatermarkCatalog(),
        **kwargs,
    ).process()


@pytest.mark.parametrize(
    ("x", "instagram", "expected"),
    [(True, False, ["X_source.jpg"]), (False, True, ["Insta_source.jpg"])],
)
def test_single_platform_selection_creates_one_output(
    tmp_path: Path, x: bool, instagram: bool, expected: list[str]
) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (8, 4), "red").save(source)

    result = _run([_source(source, x=x, instagram=instagram)], tmp_path / "out")

    assert [export.output_path.name for export in result.exports] == expected
    assert all(export.status is ExportStatus.SUCCEEDED for export in result.exports)


def test_dual_selection_prepares_once_and_creates_both_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (8, 4), "red").save(source)
    calls = 0
    original = batch_module.prepare_jpeg

    def counted(*args: object, **kwargs: object):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(batch_module, "prepare_jpeg", counted)
    result = _run([_source(source, x=True, instagram=True)], tmp_path / "out")

    assert calls == 1
    assert {export.output_path.name for export in result.exports} == {
        "X_source.jpg",
        "Insta_source.jpg",
    }
    assert result.statistics.processed_source_count == 1
    assert result.processed_source_size_bytes == source.stat().st_size


def test_unselected_source_is_ignored_and_not_progress_total(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (8, 4)).save(source)
    result = _run([_source(source)], tmp_path / "out")

    assert result.exports == ()
    assert not (tmp_path / "out").exists()
    assert not any(isinstance(event, ProgressUpdate) for event in result.events)


def test_disabled_watermark_exports_without_catalog_match(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (8, 4), "red").save(source)
    result = _run([_source(source, x=True)], tmp_path / "out")
    assert result.statistics.successful_output_count == 1


def test_exact_watermark_is_composited_and_inputs_are_unchanged(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    watermark = tmp_path / "watermark.png"
    Image.new("RGB", (8, 4), "red").save(source)
    Image.new("RGBA", (8, 4), (0, 0, 255, 255)).save(watermark)
    before = [hashlib.sha256(path.read_bytes()).digest() for path in (source, watermark)]

    result = _run(
        [_source(source, x=True)],
        tmp_path / "out",
        WatermarkCatalog({(8, 4): [watermark]}),
        watermark_enabled=True,
    )

    with Image.open(result.exports[0].output_path) as output:
        red, _green, blue = output.getpixel((0, 0))
        assert blue > red
    assert before == [hashlib.sha256(path.read_bytes()).digest() for path in (source, watermark)]


@pytest.mark.parametrize("watermarks", [[], ["one.png", "two.png"]])
def test_missing_or_ambiguous_watermark_skips_complete_source(
    tmp_path: Path, watermarks: list[str]
) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (8, 4)).save(source)
    paths = []
    for name in watermarks:
        path = tmp_path / name
        Image.new("RGBA", (8, 4)).save(path)
        paths.append(path)

    result = _run(
        [_source(source, x=True, instagram=True)],
        tmp_path / "out",
        WatermarkCatalog({(8, 4): paths}),
        watermark_enabled=True,
    )

    assert result.exports == ()
    assert sum(isinstance(event, SkippedSource) for event in result.events) == 1
    assert result.statistics.processed_source_count == 0


def test_corrupt_source_does_not_stop_later_source_and_progress_is_monotonic(
    tmp_path: Path,
) -> None:
    corrupt = tmp_path / "bad.png"
    good = tmp_path / "good.png"
    corrupt.write_bytes(b"not an image")
    Image.new("RGB", (8, 4)).save(good)
    items = [
        ImageItem(corrupt, 8, 4, corrupt.stat().st_size, True),
        _source(good, instagram=True),
    ]

    result = _run(items, tmp_path / "out")
    progress = [event for event in result.events if isinstance(event, ProgressUpdate)]

    assert any(isinstance(event, FailedSource) for event in result.events)
    assert result.statistics.successful_output_count == 1
    assert [(event.completed, event.total) for event in progress] == [(1, 2), (2, 2)]


def test_one_platform_failure_isolated_and_statistics_count_only_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (8, 4)).save(source)
    original = batch_module.export_prepared_jpeg

    def fail_x(prepared: object, output: Path, **kwargs: object):
        if output.name.startswith("X_"):
            raise OutputWriteError(output, OSError("denied"))
        return original(prepared, output, **kwargs)

    monkeypatch.setattr(batch_module, "export_prepared_jpeg", fail_x)
    item = _source(source, x=True, instagram=True, size=1000)
    result = _run([item], tmp_path / "out")

    assert any(isinstance(event, FailedExport) for event in result.events)
    assert result.statistics.processed_source_count == 1
    assert result.statistics.successful_output_count == 1
    assert result.processed_source_size_bytes == 1000
    assert result.output_size_bytes == (tmp_path / "out" / "Insta_source.jpg").stat().st_size


def test_duplicate_names_are_reserved_across_multi_output_batch(tmp_path: Path) -> None:
    first_dir = tmp_path / "a"
    second_dir = tmp_path / "b"
    first_dir.mkdir()
    second_dir.mkdir()
    first = first_dir / "same.png"
    second = second_dir / "same.png"
    Image.new("RGB", (8, 4), "red").save(first)
    Image.new("RGB", (8, 4), "blue").save(second)

    result = _run(
        [_source(first, x=True), _source(second, x=True)], tmp_path / "out"
    )
    assert [export.output_path.name for export in result.exports] == [
        "X_same.jpg",
        "X_same_2.jpg",
    ]


def test_signed_negative_savings_and_final_statistics_event(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (8, 4)).save(source)
    result = _run([_source(source, x=True, size=1)], tmp_path / "out", jpeg_quality=100)

    assert result.bytes_saved < 0
    assert result.reduction_percentage < 0
    assert result.events[-1] == result.statistics
    assert isinstance(result.events[-1], BatchStatistics)

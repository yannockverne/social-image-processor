from pathlib import Path

import pytest

Image = pytest.importorskip("PIL.Image")

from app.core.watermarking import WatermarkCatalog  # noqa: E402
from app.models.watermark import WatermarkStatus  # noqa: E402
from app.services.folder_scanner import (  # noqa: E402
    scan_input_folder,
    scan_watermark_folder,
)


def _image(path: Path, size: tuple[int, int], mode: str = "RGB") -> None:
    Image.new(mode, size, 0).save(path)


def test_source_scan_is_non_recursive_case_insensitive_and_sorted(
    tmp_path: Path,
) -> None:
    _image(tmp_path / "z.JPG", (30, 20))
    _image(tmp_path / "A.png", (10, 5))
    _image(tmp_path / "b.JpEg", (20, 10))
    (tmp_path / "ignored.gif").write_bytes(b"not selected")
    nested = tmp_path / "nested"
    nested.mkdir()
    _image(nested / "hidden.png", (1, 1))

    result = scan_input_folder(tmp_path, WatermarkCatalog())

    assert [item.path.name for item in result.images] == ["A.png", "b.JpEg", "z.JPG"]
    assert [(item.width, item.height) for item in result.images] == [
        (10, 5),
        (20, 10),
        (30, 20),
    ]
    assert all(item.size_bytes == item.path.stat().st_size for item in result.images)
    assert all(not item.export_to_x for item in result.images)
    assert all(not item.export_to_instagram for item in result.images)
    assert result.issues == ()


def test_watermark_scan_uses_pixels_and_detects_duplicate_dimensions(
    tmp_path: Path,
) -> None:
    first = tmp_path / "claims_1x1.png"
    second = tmp_path / "another.PNG"
    _image(first, (40, 20), "RGBA")
    _image(second, (40, 20), "RGBA")
    _image(tmp_path / "unique.png", (20, 40), "RGBA")
    (tmp_path / "ignored.jpg").write_bytes(b"not a watermark")

    result = scan_watermark_folder(tmp_path)

    assert result.catalog.match((40, 20)).status is WatermarkStatus.AMBIGUOUS
    assert result.catalog.match((20, 40)).status is WatermarkStatus.EXACT
    assert result.catalog.match((1, 1)).status is WatermarkStatus.MISSING
    assert result.issues == ()


def test_sources_are_classified_against_catalog(tmp_path: Path) -> None:
    exact_source = tmp_path / "exact.png"
    missing_source = tmp_path / "missing.jpg"
    ambiguous_source = tmp_path / "ambiguous.jpeg"
    _image(exact_source, (10, 10))
    _image(missing_source, (20, 10))
    _image(ambiguous_source, (30, 10))
    catalog = WatermarkCatalog(
        {
            (10, 10): [Path("exact-watermark.png")],
            (30, 10): [Path("one.png"), Path("two.png")],
        }
    )

    result = scan_input_folder(tmp_path, catalog)
    statuses = {item.path.name: item.watermark_match.status for item in result.images}

    assert statuses == {
        "ambiguous.jpeg": WatermarkStatus.AMBIGUOUS,
        "exact.png": WatermarkStatus.EXACT,
        "missing.jpg": WatermarkStatus.MISSING,
    }


def test_corrupt_files_are_isolated_for_both_scans(tmp_path: Path) -> None:
    _image(tmp_path / "good.png", (10, 10))
    (tmp_path / "bad.png").write_bytes(b"not an image")

    watermark_result = scan_watermark_folder(tmp_path)
    source_result = scan_input_folder(tmp_path, watermark_result.catalog)

    assert len(watermark_result.catalog.entries) == 1
    assert [issue.path.name for issue in watermark_result.issues] == ["bad.png"]
    assert [item.path.name for item in source_result.images] == ["good.png"]
    assert [issue.path.name for issue in source_result.issues] == ["bad.png"]


def test_missing_folder_is_reported_without_raising(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"

    watermark_result = scan_watermark_folder(missing)
    source_result = scan_input_folder(missing, WatermarkCatalog())

    assert watermark_result.catalog.entries == {}
    assert watermark_result.issues[0].path == missing
    assert source_result.images == ()
    assert source_result.issues[0].path == missing

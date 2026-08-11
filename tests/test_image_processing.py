from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

Image = pytest.importorskip("PIL.Image")

from app.core.errors import DimensionMismatchError, OutputWriteError  # noqa: E402
from app.core.image_processing import (  # noqa: E402
    composite_full_frame,
    export_jpeg,
    flatten_to_rgb,
    render_for_jpeg,
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_exact_full_frame_alpha_compositing_at_origin() -> None:
    source = Image.new("RGB", (2, 1), (100, 100, 100))
    watermark = Image.new("RGBA", (2, 1), (0, 0, 0, 0))
    watermark.putpixel((0, 0), (200, 0, 0, 128))

    result = composite_full_frame(source, watermark)

    assert result.size == source.size
    assert result.getpixel((0, 0)) == (150, 50, 50, 255)
    assert result.getpixel((1, 0)) == (100, 100, 100, 255)


def test_dimension_mismatch_is_typed_and_never_resized() -> None:
    source = Image.new("RGB", (10, 5))
    watermark = Image.new("RGBA", (5, 10))

    with pytest.raises(DimensionMismatchError) as caught:
        composite_full_frame(source, watermark)

    assert caught.value.source_size == (10, 5)
    assert caught.value.watermark_size == (5, 10)


def test_transparency_flattens_against_default_black_and_custom_background() -> None:
    transparent = Image.new("RGBA", (1, 1), (255, 0, 0, 0))

    assert flatten_to_rgb(transparent).getpixel((0, 0)) == (0, 0, 0)
    assert flatten_to_rgb(transparent, "#123456").getpixel((0, 0)) == (
        0x12,
        0x34,
        0x56,
    )


@pytest.mark.parametrize("mode", ["RGB", "RGBA", "L", "P"])
def test_supported_modes_normalize_to_same_size_rgb(mode: str) -> None:
    source = Image.new(mode, (7, 3))

    result = render_for_jpeg(source)

    assert result.mode == "RGB"
    assert result.size == (7, 3)


def test_png_to_jpeg_preserves_dimensions_and_input_files(tmp_path: Path) -> None:
    source_path = tmp_path / "SOURCE.PNG"
    watermark_path = tmp_path / "watermark.png"
    output_path = tmp_path / "output" / "X_SOURCE.jpg"
    Image.new("RGBA", (8, 4), (255, 0, 0, 100)).save(source_path)
    Image.new("RGBA", (8, 4), (0, 0, 255, 80)).save(watermark_path)
    source_digest = _digest(source_path)
    watermark_digest = _digest(watermark_path)

    exported = export_jpeg(
        source_path,
        output_path,
        watermark_path=watermark_path,
        quality=92,
    )

    assert exported.path == output_path
    assert exported.dimensions == (8, 4)
    assert exported.size_bytes == output_path.stat().st_size
    assert _digest(source_path) == source_digest
    assert _digest(watermark_path) == watermark_digest
    with Image.open(output_path) as generated:
        generated.verify()
    with Image.open(output_path) as generated:
        assert generated.format == "JPEG"
        assert generated.mode == "RGB"
        assert generated.size == (8, 4)


def test_export_rejects_mismatched_watermark_without_output(tmp_path: Path) -> None:
    source_path = tmp_path / "source.png"
    watermark_path = tmp_path / "watermark.png"
    output_path = tmp_path / "output.jpg"
    Image.new("RGB", (8, 4)).save(source_path)
    Image.new("RGBA", (4, 8)).save(watermark_path)

    with pytest.raises(DimensionMismatchError):
        export_jpeg(source_path, output_path, watermark_path=watermark_path)

    assert not output_path.exists()


def test_failed_save_leaves_no_completed_or_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_path = tmp_path / "source.png"
    output_path = tmp_path / "exports" / "X_source.jpg"
    Image.new("RGB", (3, 3)).save(source_path)

    def fail_save(*args: object, **kwargs: object) -> None:
        raise OSError("simulated write failure")

    monkeypatch.setattr(Image.Image, "save", fail_save)

    with pytest.raises(OutputWriteError, match="simulated write failure"):
        export_jpeg(source_path, output_path)

    assert not output_path.exists()
    assert list(output_path.parent.iterdir()) == []


def test_export_never_overwrites_an_existing_output(tmp_path: Path) -> None:
    source_path = tmp_path / "source.png"
    output_path = tmp_path / "X_source.jpg"
    Image.new("RGB", (3, 3)).save(source_path)
    output_path.write_bytes(b"existing output")

    with pytest.raises(OutputWriteError):
        export_jpeg(source_path, output_path)

    assert output_path.read_bytes() == b"existing output"
    assert not list(tmp_path.glob(f".{output_path.name}.*.tmp"))


def test_failed_finalization_cleans_temporary_and_reserved_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_path = tmp_path / "source.png"
    output_path = tmp_path / "X_source.jpg"
    Image.new("RGB", (3, 3)).save(source_path)

    def fail_replace(_self: Path, _target: Path) -> None:
        raise OSError("simulated finalization failure")

    monkeypatch.setattr(type(tmp_path), "replace", fail_replace)

    with pytest.raises(OutputWriteError, match="simulated finalization failure"):
        export_jpeg(source_path, output_path)

    assert not output_path.exists()
    assert not list(tmp_path.glob(f".{output_path.name}.*.tmp"))


def test_safe_export_fsyncs_a_writable_file_for_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows reports EBADF when fsync receives a read-only descriptor."""
    source_path = tmp_path / "source.png"
    output_path = tmp_path / "X_source.jpg"
    Image.new("RGB", (3, 3)).save(source_path)
    path_type = type(tmp_path)
    original_open = path_type.open
    opened_modes: list[str] = []

    def record_open(self: Path, mode: str = "r", *args: object, **kwargs: object):
        opened_modes.append(mode)
        return original_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(path_type, "open", record_open)

    export_jpeg(source_path, output_path)

    assert "rb+" in opened_modes
    assert "rb" not in opened_modes
    assert "xb" in opened_modes
    with Image.open(output_path) as generated:
        generated.verify()

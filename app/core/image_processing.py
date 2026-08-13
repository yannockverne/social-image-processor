"""Qt-independent full-resolution image processing and JPEG output."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile

from PIL import Image, ImageColor

from app.core.errors import OutputWriteError
from app.core.watermarking import watermark_geometry

DEFAULT_BACKGROUND = "#000000"


@dataclass(frozen=True, slots=True)
class JPEGExport:
    """Metadata describing one successfully finalized JPEG."""

    path: Path
    dimensions: tuple[int, int]
    size_bytes: int


@dataclass(frozen=True, slots=True)
class PreparedJPEG:
    """A rendered RGB image and safe metadata shared by platform exports."""

    image: Image.Image
    icc_profile: bytes | None = None


def composite_watermark(source: Image.Image, watermark: Image.Image) -> Image.Image:
    """Scale and alpha-composite an artwork asset at proportional bottom-right."""
    source_rgba = source.convert("RGBA")
    watermark_rgba = watermark.convert("RGBA")
    size, position = watermark_geometry(source.size, watermark.size)
    resized = watermark_rgba.resize(size, Image.Resampling.LANCZOS)
    source_rgba.alpha_composite(resized, position)
    return source_rgba


# Transitional import compatibility; behavior is intentionally dynamic now.
composite_full_frame = composite_watermark


def flatten_to_rgb(
    image: Image.Image, background: str | tuple[int, int, int] = DEFAULT_BACKGROUND
) -> Image.Image:
    """Flatten all supported Pillow modes onto an RGB background."""
    color = ImageColor.getrgb(background) if isinstance(background, str) else background
    if len(color) != 3 or any(not 0 <= channel <= 255 for channel in color):
        raise ValueError("Background must be an RGB color")

    rgba = image.convert("RGBA")
    flattened = Image.new("RGB", rgba.size, color)
    flattened.paste(rgba, (0, 0), rgba.getchannel("A"))
    return flattened


def render_for_jpeg(
    source: Image.Image,
    watermark: Image.Image | None = None,
    background: str | tuple[int, int, int] = DEFAULT_BACKGROUND,
) -> Image.Image:
    """Create a same-size RGB raster, optionally with a dynamic watermark."""
    composed = composite_watermark(source, watermark) if watermark else source
    return flatten_to_rgb(composed, background)


def export_jpeg(
    source_path: Path,
    output_path: Path,
    *,
    watermark_path: Path | None = None,
    quality: int = 92,
    background: str | tuple[int, int, int] = DEFAULT_BACKGROUND,
) -> JPEGExport:
    """Render *source_path* and safely finalize a JPEG in the output directory.

    Raw stored pixel orientation is used. EXIF data is not copied. An ICC profile
    is retained only when Pillow exposes it as bytes suitable for a JPEG save.
    """
    if not 1 <= quality <= 100:
        raise ValueError("JPEG quality must be between 1 and 100")

    prepared = prepare_jpeg(
        source_path, watermark_path=watermark_path, background=background
    )
    return export_prepared_jpeg(prepared, output_path, quality=quality)


def prepare_jpeg(
    source_path: Path,
    *,
    watermark_path: Path | None = None,
    background: str | tuple[int, int, int] = DEFAULT_BACKGROUND,
) -> PreparedJPEG:
    """Decode and render a source once for one or more identical exports."""
    with Image.open(source_path) as source:
        source.load()
        icc_profile = source.info.get("icc_profile")
        safe_icc_profile = icc_profile if isinstance(icc_profile, bytes) else None
        if watermark_path is None:
            rendered = render_for_jpeg(source, background=background)
        else:
            with Image.open(watermark_path) as watermark:
                watermark.load()
                rendered = render_for_jpeg(source, watermark, background)
    return PreparedJPEG(rendered, safe_icc_profile)


def export_prepared_jpeg(
    prepared: PreparedJPEG, output_path: Path, *, quality: int = 92
) -> JPEGExport:
    """Safely write an already-rendered image without decoding it again."""
    if not 1 <= quality <= 100:
        raise ValueError("JPEG quality must be between 1 and 100")
    _atomic_save_jpeg(prepared.image, output_path, quality, prepared.icc_profile)
    return JPEGExport(output_path, prepared.image.size, output_path.stat().st_size)


def _atomic_save_jpeg(
    image: Image.Image,
    output_path: Path,
    quality: int,
    icc_profile: bytes | None,
) -> None:
    """Save beside the destination and atomically finalize without overwriting."""
    temporary_path: Path | None = None
    destination_reserved = False
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)

        save_options: dict[str, object] = {"format": "JPEG", "quality": quality}
        if icc_profile is not None:
            save_options["icc_profile"] = icc_profile
        image.save(temporary_path, **save_options)
        # Windows rejects fsync() on a read-only descriptor with EBADF.  Open the
        # completed temporary JPEG for update even though no further writes are
        # made, so the durability flush is portable.
        with temporary_path.open("rb+") as saved_file:
            os.fsync(saved_file.fileno())

        # The exclusive placeholder prevents replacing an output that appeared
        # since batch name allocation.  Close it before os.replace(): Windows
        # cannot replace an open file.
        with output_path.open("xb"):
            destination_reserved = True
        temporary_path.replace(output_path)
        destination_reserved = False
    except (OSError, ValueError) as error:
        raise OutputWriteError(output_path, error) from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        if destination_reserved:
            output_path.unlink(missing_ok=True)

import math
from pathlib import Path

from app.core.watermarking import (
    DEFAULT_WATERMARK_SIZE_RATIO,
    WATERMARK_MARGIN_RATIO,
    WatermarkCatalog,
    watermark_geometry,
)
from app.models.watermark import WatermarkStatus


def test_catalog_orders_and_selects_multiple_designs() -> None:
    catalog = WatermarkCatalog([Path("Zulu.png"), Path("alpha.png")])
    assert [path.name for path in catalog.paths] == ["alpha.png", "Zulu.png"]
    assert catalog.match((4000, 5000), "Zulu.png").status is WatermarkStatus.EXACT
    assert catalog.match((4000, 5000), "alpha.png").exact_path == Path("alpha.png")


def test_missing_selection_is_unavailable() -> None:
    catalog = WatermarkCatalog([Path("Origin.png")])
    assert catalog.match((100, 100), "Gone.png").status is WatermarkStatus.MISSING


def test_landscape_geometry_uses_geometric_mean_and_bottom_right() -> None:
    size, position = watermark_geometry((4000, 2000), (1000, 400))
    expected_width = round(math.sqrt(4000 * 2000) * DEFAULT_WATERMARK_SIZE_RATIO)
    assert size == (expected_width, round(expected_width * 0.4))
    assert position == (
        4000 - size[0] - round(4000 * WATERMARK_MARGIN_RATIO),
        2000 - size[1] - round(2000 * WATERMARK_MARGIN_RATIO),
    )


def test_portrait_geometry_preserves_aspect_ratio_and_margins() -> None:
    size, position = watermark_geometry((3000, 4000), (500, 200))
    expected_width = round(math.sqrt(3000 * 4000) * DEFAULT_WATERMARK_SIZE_RATIO)
    assert size == (expected_width, round(expected_width * 200 / 500))
    assert position == (
        3000 - size[0] - round(3000 * WATERMARK_MARGIN_RATIO),
        4000 - size[1] - round(4000 * WATERMARK_MARGIN_RATIO),
    )


def test_custom_size_ratio_changes_rendered_dimensions() -> None:
    default_size, _ = watermark_geometry((3000, 4000), (1000, 400))
    explicit_size, _ = watermark_geometry((3000, 4000), (1000, 400), 0.10)
    assert default_size[0] == round(math.sqrt(3000 * 4000) * 0.08)
    assert explicit_size[0] == round(math.sqrt(3000 * 4000) * 0.10)

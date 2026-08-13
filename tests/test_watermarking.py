from pathlib import Path

from app.core.watermarking import (
    WATERMARK_MARGIN_RATIO,
    WATERMARK_WIDTH_RATIO,
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


def test_landscape_geometry_is_proportional_and_bottom_right() -> None:
    size, position = watermark_geometry((4000, 2000), (1000, 400))
    assert size == (round(4000 * WATERMARK_WIDTH_RATIO), 144)
    assert position == (
        4000 - size[0] - round(4000 * WATERMARK_MARGIN_RATIO),
        2000 - size[1] - round(2000 * WATERMARK_MARGIN_RATIO),
    )


def test_portrait_geometry_preserves_aspect_ratio_and_margins() -> None:
    size, position = watermark_geometry((3000, 4000), (500, 200))
    assert size[0] / size[1] == 2.5
    assert position[0] + size[0] < 3000
    assert position[1] + size[1] < 4000

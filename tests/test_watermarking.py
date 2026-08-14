import math
from pathlib import Path

from app.core.watermarking import (
    DEFAULT_WATERMARK_SIZE_RATIO,
    WATERMARK_MARGIN_RATIO,
    WatermarkCatalog,
    get_watermark_size_ratio,
    set_watermark_size_ratio,
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
    assert size[0] / size[1] == 2.5
    assert position[0] + size[0] < 3000
    assert position[1] + size[1] < 4000


def test_explicit_size_ratio_overrides_session_value() -> None:
    set_watermark_size_ratio(0.08)
    session_size, _ = watermark_geometry((3000, 4000), (1000, 400))
    explicit_size, _ = watermark_geometry((3000, 4000), (1000, 400), 0.10)
    assert explicit_size[0] > session_size[0]


def test_session_size_ratio_can_change_without_settings() -> None:
    original = get_watermark_size_ratio()
    try:
        set_watermark_size_ratio(0.095)
        assert get_watermark_size_ratio() == 0.095
        size, _ = watermark_geometry((3000, 4000), (1000, 400))
        assert size[0] == round(math.sqrt(3000 * 4000) * 0.095)
    finally:
        set_watermark_size_ratio(original)

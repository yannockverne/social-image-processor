from pathlib import Path

import pytest

from app.models.image_item import ImageItem, is_instagram_ratio_supported
from app.models.profiles import ExportPlatform, get_profile


def test_image_selections_default_to_unchecked() -> None:
    item = ImageItem(Path("source.png"), 3440, 1440, 123)

    assert item.dimensions == (3440, 1440)
    assert item.export_to_x is False
    assert item.export_to_instagram is False


@pytest.mark.parametrize(
    ("dimensions", "supported"),
    [
        ((800, 1000), True),
        ((1910, 1000), True),
        ((1000, 1000), True),
        ((799, 1000), False),
        ((1911, 1000), False),
        ((0, 1000), False),
        ((1000, 0), False),
        ((-1, 1000), False),
    ],
)
def test_instagram_ratio_supported(dimensions, supported: bool) -> None:
    assert is_instagram_ratio_supported(*dimensions) is supported


@pytest.mark.parametrize(
    ("platform", "prefix"),
    [(ExportPlatform.X, "X_"), (ExportPlatform.INSTAGRAM, "Insta_")],
)
def test_profiles_preserve_dimensions_without_cropping(
    platform: ExportPlatform, prefix: str
) -> None:
    profile = get_profile(platform)

    assert profile.filename_prefix == prefix
    assert profile.output_format == "JPEG"
    assert profile.preserve_dimensions is True
    assert profile.crop is False


def test_unknown_profile_is_rejected() -> None:
    with pytest.raises(ValueError):
        get_profile("unsupported")

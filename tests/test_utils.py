import pytest

from app.utils.formatting import format_bytes, reduction_percentage


@pytest.mark.parametrize(
    ("value", "formatted"),
    [(0, "0 B"), (1023, "1023 B"), (1024, "1.0 KB"), (1536, "1.5 KB")],
)
def test_format_bytes(value: int, formatted: str) -> None:
    assert format_bytes(value) == formatted


def test_reduction_percentage_supports_growth_and_empty_sources() -> None:
    assert reduction_percentage(100, 25) == 75.0
    assert reduction_percentage(100, 125) == -25.0
    assert reduction_percentage(0, 10) == 0.0

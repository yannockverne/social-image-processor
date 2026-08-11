from pathlib import Path

from app.core.watermarking import WatermarkCatalog
from app.models.watermark import WatermarkStatus


def test_catalog_classifies_exact_missing_and_ambiguous_matches() -> None:
    exact = Path("watermark_exact.png")
    duplicate_a = Path("a.png")
    duplicate_b = Path("B.png")
    catalog = WatermarkCatalog(
        {(3440, 1440): [exact], (4000, 5000): [duplicate_b, duplicate_a]}
    )

    exact_match = catalog.match((3440, 1440))
    assert exact_match.status is WatermarkStatus.EXACT
    assert exact_match.exact_path == exact

    missing_match = catalog.match((1440, 3440))
    assert missing_match.status is WatermarkStatus.MISSING
    assert missing_match.paths == ()

    ambiguous_match = catalog.match((4000, 5000))
    assert ambiguous_match.status is WatermarkStatus.AMBIGUOUS
    assert ambiguous_match.paths == (duplicate_a, duplicate_b)
    assert ambiguous_match.exact_path is None


def test_entries_returns_a_copy() -> None:
    catalog = WatermarkCatalog({(1, 2): [Path("watermark.png")]})
    snapshot = catalog.entries

    snapshot[(3, 4)] = (Path("other.png"),)

    assert catalog.match((3, 4)).status is WatermarkStatus.MISSING

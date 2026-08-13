"""Discovery model and deterministic dynamic-watermark geometry."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from app.models.watermark import WatermarkMatch, WatermarkStatus

Dimensions = tuple[int, int]
WATERMARK_WIDTH_RATIO = 0.09
WATERMARK_MARGIN_RATIO = 0.0175
MAX_UPSCALE_FACTOR = 4.0


class WatermarkCatalog:
    """Immutable, predictably ordered collection of reusable PNG assets."""

    def __init__(self, paths: Iterable[Path] | dict | None = None) -> None:
        # Accept legacy dimension mappings in memory while old callers migrate.
        if isinstance(paths, dict):
            paths = (path for group in paths.values() for path in group)
        self._paths = tuple(sorted(paths or (), key=_path_sort_key))

    @property
    def paths(self) -> tuple[Path, ...]:
        return self._paths

    @property
    def entries(self) -> dict[Dimensions, tuple[Path, ...]]:
        """Compatibility snapshot; dynamic assets are not dimension keyed."""
        return {(0, 0): self._paths} if self._paths else {}

    def find(self, selected: str | Path | None) -> Path | None:
        """Resolve a persisted filename (or path) only within this catalog."""
        if selected is None:
            return None
        name = Path(selected).name
        return next((path for path in self._paths if path.name == name), None)

    def match(
        self, _dimensions: Dimensions, selected: str | Path | None = None
    ) -> WatermarkMatch:
        """Return availability for the selected design (dimensions are irrelevant)."""
        path = self.find(selected)
        if path is None and selected is None and len(self._paths) == 1:
            path = self._paths[0]
        status = WatermarkStatus.EXACT if path else WatermarkStatus.MISSING
        return WatermarkMatch(status, _dimensions, (path,) if path else ())


def watermark_geometry(
    source_size: Dimensions, asset_size: Dimensions
) -> tuple[Dimensions, tuple[int, int]]:
    """Return proportional rendered size and bottom-right position.

    Width is 9% of source width, capped at four times the asset's natural width.
    Each axis uses a 1.75% margin. Rounding is deterministic and the asset always
    remains wholly inside the source.
    """
    sw, sh = source_size
    aw, ah = asset_size
    if min(sw, sh, aw, ah) <= 0:
        raise ValueError("Image dimensions must be positive")
    width = max(1, round(sw * WATERMARK_WIDTH_RATIO))
    width = min(width, round(aw * MAX_UPSCALE_FACTOR), sw)
    height = max(1, round(width * ah / aw))
    if height > sh:
        height = sh
        width = max(1, round(height * aw / ah))
    mx, my = round(sw * WATERMARK_MARGIN_RATIO), round(sh * WATERMARK_MARGIN_RATIO)
    return (width, height), (max(0, sw - width - mx), max(0, sh - height - my))


def _path_sort_key(path: Path) -> tuple[str, str]:
    return path.name.casefold(), path.name

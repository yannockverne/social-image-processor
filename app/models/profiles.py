"""Built-in platform export profiles."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ExportPlatform(StrEnum):
    """Supported V1 export destinations."""

    X = "x"
    INSTAGRAM = "instagram"


@dataclass(frozen=True, slots=True)
class ExportProfile:
    """Immutable platform-specific export behavior."""

    platform: ExportPlatform
    filename_prefix: str
    output_format: str = "JPEG"
    preserve_dimensions: bool = True
    crop: bool = False


_PROFILES = {
    ExportPlatform.X: ExportProfile(ExportPlatform.X, "X_"),
    ExportPlatform.INSTAGRAM: ExportProfile(ExportPlatform.INSTAGRAM, "Insta_"),
}


def get_profile(platform: ExportPlatform | str) -> ExportProfile:
    """Return a built-in profile for *platform*.

    ``ValueError`` is raised for unsupported strings rather than falling back
    to a potentially incorrect export profile.
    """
    return _PROFILES[ExportPlatform(platform)]

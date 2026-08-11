"""JSON-backed local settings persistence."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping

from app.models.settings import (
    ApplicationSettings,
    DEFAULT_BACKGROUND_COLOR,
    DEFAULT_JPEG_QUALITY,
    MAX_JPEG_QUALITY,
    MIN_JPEG_QUALITY,
)

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def default_settings_path() -> Path:
    """Return the platform-appropriate settings JSON path."""
    if appdata := os.environ.get("APPDATA"):
        root = Path(appdata)
    elif xdg_config := os.environ.get("XDG_CONFIG_HOME"):
        root = Path(xdg_config)
    else:
        root = Path.home() / ".config"
    return root / "SocialImageProcessor" / "settings.json"


class SettingsService:
    """Load and atomically save application settings."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path if path is not None else default_settings_path()

    def load(self) -> ApplicationSettings:
        """Load valid values and safely fall back for absent/corrupt data."""
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return ApplicationSettings()

        if not isinstance(payload, dict):
            return ApplicationSettings()
        try:
            return self._from_mapping(payload)
        except (OSError, TypeError, ValueError):
            # Settings are convenience state, never a reason to prevent launch.
            return ApplicationSettings()

    def save(self, settings: ApplicationSettings) -> None:
        """Atomically persist *settings*, creating its parent directory."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "input_directory": self._serialize_path(settings.input_directory),
            "output_directory": self._serialize_path(settings.output_directory),
            "watermark_directory": self._serialize_path(settings.watermark_directory),
            "jpeg_quality": self._quality(settings.jpeg_quality),
            "watermark_enabled": bool(settings.watermark_enabled),
            "background_color": self._color(settings.background_color),
        }

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                json.dump(payload, handle, indent=2)
                handle.write("\n")
                temporary_path = Path(handle.name)
            temporary_path.replace(self.path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    @classmethod
    def _from_mapping(cls, payload: Mapping[str, Any]) -> ApplicationSettings:
        return ApplicationSettings(
            input_directory=cls._path(payload.get("input_directory")),
            output_directory=cls._path(payload.get("output_directory")),
            watermark_directory=cls._path(payload.get("watermark_directory")),
            jpeg_quality=cls._quality(payload.get("jpeg_quality")),
            watermark_enabled=cls._boolean(payload.get("watermark_enabled"), True),
            background_color=cls._color(payload.get("background_color")),
        )

    @staticmethod
    def _path(value: Any) -> Path | None:
        if not isinstance(value, str) or not value or "\x00" in value:
            return None
        try:
            return Path(value)
        except (OSError, TypeError, ValueError):
            return None

    @staticmethod
    def _serialize_path(value: Path | None) -> str | None:
        return str(value) if value is not None else None

    @staticmethod
    def _quality(value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            return DEFAULT_JPEG_QUALITY
        return max(MIN_JPEG_QUALITY, min(MAX_JPEG_QUALITY, value))

    @staticmethod
    def _boolean(value: Any, default: bool) -> bool:
        return value if isinstance(value, bool) else default

    @staticmethod
    def _color(value: Any) -> str:
        if isinstance(value, str) and _HEX_COLOR.fullmatch(value):
            return value.upper()
        return DEFAULT_BACKGROUND_COLOR

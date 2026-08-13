import json
from pathlib import Path

from app.models.settings import ApplicationSettings
from app.services.settings_service import SettingsService, default_settings_path


def test_missing_settings_return_safe_defaults(tmp_path: Path) -> None:
    settings = SettingsService(tmp_path / "missing.json").load()

    assert settings == ApplicationSettings()
    assert settings.jpeg_quality == 92
    assert settings.watermark_enabled is True
    assert settings.background_color == "#000000"


def test_settings_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "settings.json"
    service = SettingsService(path)
    expected = ApplicationSettings(
        input_directory=Path("C:/photos"),
        output_directory=Path("C:/exports"),
        watermark_directory=Path("C:/watermarks"),
        jpeg_quality=88,
        watermark_enabled=False,
        background_color="#12abEF",
        selected_watermark="Origin.png",
    )

    service.save(expected)

    assert service.load() == ApplicationSettings(
        input_directory=expected.input_directory,
        output_directory=expected.output_directory,
        watermark_directory=expected.watermark_directory,
        jpeg_quality=88,
        watermark_enabled=False,
        background_color="#12ABEF",
        selected_watermark="Origin.png",
    )
    assert json.loads(path.read_text(encoding="utf-8"))["jpeg_quality"] == 88


def test_corrupt_or_non_object_json_returns_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("not json", encoding="utf-8")
    assert SettingsService(path).load() == ApplicationSettings()

    path.write_text("[]", encoding="utf-8")
    assert SettingsService(path).load() == ApplicationSettings()


def test_invalid_values_are_safely_normalized(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "input_directory": 42,
                "jpeg_quality": 120,
                "watermark_enabled": "yes",
                "background_color": "black",
            }
        ),
        encoding="utf-8",
    )

    settings = SettingsService(path).load()

    assert settings.input_directory is None
    assert settings.jpeg_quality == 100
    assert settings.watermark_enabled is True
    assert settings.background_color == "#000000"


def test_invalid_path_does_not_discard_other_valid_settings(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"input_directory": "bad\u0000path", "jpeg_quality": 84}),
        encoding="utf-8",
    )

    settings = SettingsService(path).load()

    assert settings.input_directory is None
    assert settings.jpeg_quality == 84


def test_quality_is_clamped_at_both_bounds(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{"jpeg_quality": 1}', encoding="utf-8")
    assert SettingsService(path).load().jpeg_quality == 70

    path.write_text('{"jpeg_quality": 1000}', encoding="utf-8")
    assert SettingsService(path).load().jpeg_quality == 100


def test_appdata_is_preferred_for_default_path(monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", "C:/Users/test/AppData/Roaming")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/ignored")

    assert default_settings_path() == Path(
        "C:/Users/test/AppData/Roaming/SocialImageProcessor/settings.json"
    )

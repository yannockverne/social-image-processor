from pathlib import Path
import sys

from app.utils.resources import resource_path


def test_resource_path_uses_source_root() -> None:
    expected = Path(__file__).parents[1] / "app/assets/icons/social_image_processor.png"

    assert resource_path("app/assets/icons/social_image_processor.png") == expected


def test_resource_path_uses_pyinstaller_bundle(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert resource_path("app/example.dat") == tmp_path / "app/example.dat"

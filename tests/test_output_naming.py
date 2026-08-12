from pathlib import Path

from app.core.output_naming import OutputNameAllocator
from app.models.profiles import ExportPlatform


def test_platform_prefixes_and_sequence_are_the_complete_base_name(
    tmp_path: Path,
) -> None:
    allocator = OutputNameAllocator(tmp_path)

    assert allocator.allocate(ExportPlatform.X, 1).name == "X_01.jpg"
    assert allocator.allocate(ExportPlatform.INSTAGRAM, 2).name == "Insta_02.jpg"


def test_existing_and_batch_reserved_names_are_numbered(tmp_path: Path) -> None:
    (tmp_path / "X_01.JPG").write_bytes(b"existing")
    allocator = OutputNameAllocator(tmp_path)

    first = allocator.allocate(ExportPlatform.X, 1)
    second = allocator.allocate(ExportPlatform.X, 1)

    assert first.name == "X_01_2.jpg"
    assert second.name == "X_01_3.jpg"


def test_missing_output_directory_does_not_prevent_allocation(tmp_path: Path) -> None:
    output_directory = tmp_path / "new"

    result = OutputNameAllocator(output_directory).allocate(ExportPlatform.X, 1)

    assert result == output_directory / "X_01.jpg"
    assert not output_directory.exists()


def test_manual_order_sequence_is_zero_padded(tmp_path: Path) -> None:
    allocator = OutputNameAllocator(tmp_path)

    assert allocator.allocate(ExportPlatform.INSTAGRAM, 2).name == "Insta_02.jpg"

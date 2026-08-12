from pathlib import Path

from app.core.output_naming import OutputNameAllocator
from app.models.profiles import ExportPlatform


def test_platform_prefixes_and_multiple_dot_stem(tmp_path: Path) -> None:
    allocator = OutputNameAllocator(tmp_path)
    source = Path("holiday.final.PNG")

    assert allocator.allocate(source, ExportPlatform.X).name == "X_holiday.final.jpg"
    assert (
        allocator.allocate(source, ExportPlatform.INSTAGRAM).name
        == "Insta_holiday.final.jpg"
    )


def test_existing_and_batch_reserved_names_are_numbered(tmp_path: Path) -> None:
    (tmp_path / "X_name.JPG").write_bytes(b"existing")
    allocator = OutputNameAllocator(tmp_path)

    first = allocator.allocate(Path("name.jpeg"), ExportPlatform.X)
    second = allocator.allocate(Path("name.jpeg"), ExportPlatform.X)

    assert first.name == "X_name_2.jpg"
    assert second.name == "X_name_3.jpg"


def test_missing_output_directory_does_not_prevent_allocation(tmp_path: Path) -> None:
    output_directory = tmp_path / "new"

    result = OutputNameAllocator(output_directory).allocate(
        Path("SOURCE.JPG"), ExportPlatform.X
    )

    assert result == output_directory / "X_SOURCE.jpg"
    assert not output_directory.exists()


def test_manual_order_sequence_is_zero_padded_before_source_name(
    tmp_path: Path,
) -> None:
    allocator = OutputNameAllocator(tmp_path)

    assert (
        allocator.allocate(Path("third.png"), ExportPlatform.INSTAGRAM, 2).name
        == "Insta_02_third.jpg"
    )

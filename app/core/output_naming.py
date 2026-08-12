"""Collision-safe V1 output filename allocation."""

from __future__ import annotations

from pathlib import Path

from app.models.profiles import ExportPlatform, ExportProfile, get_profile


class OutputNameAllocator:
    """Allocate output paths unique on disk and within the current batch.

    Names are compared case-insensitively to match Windows filesystem behavior,
    even when development and tests run on a case-sensitive platform.
    """

    def __init__(self, output_directory: Path) -> None:
        self.output_directory = output_directory
        self._reserved: set[str] = set()

    def allocate(
        self,
        source_path: Path,
        profile: ExportProfile | ExportPlatform | str,
        sequence_number: int | None = None,
    ) -> Path:
        """Reserve and return the first available profile-prefixed JPG path."""
        if not isinstance(profile, ExportProfile):
            profile = get_profile(profile)

        sequence = f"{sequence_number:02d}_" if sequence_number is not None else ""
        base_name = f"{profile.filename_prefix}{sequence}{source_path.stem}"
        suffix_number: int | None = None
        while True:
            suffix = "" if suffix_number is None else f"_{suffix_number}"
            candidate = self.output_directory / f"{base_name}{suffix}.jpg"
            key = candidate.name.casefold()
            if key not in self._reserved and not self._exists_case_insensitively(key):
                self._reserved.add(key)
                return candidate
            suffix_number = 2 if suffix_number is None else suffix_number + 1

    def _exists_case_insensitively(self, candidate_key: str) -> bool:
        try:
            return any(
                child.name.casefold() == candidate_key
                for child in self.output_directory.iterdir()
            )
        except FileNotFoundError:
            return False

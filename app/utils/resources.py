"""Resolve read-only application resources in source and bundled builds."""

from __future__ import annotations

from pathlib import Path
import sys


def resource_path(relative_path: str | Path) -> Path:
    """Return a resource path rooted at the source tree or PyInstaller bundle."""
    bundle_root = getattr(sys, "_MEIPASS", None)
    root = Path(bundle_root) if bundle_root is not None else Path(__file__).parents[2]
    return root / relative_path

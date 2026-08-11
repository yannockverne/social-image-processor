"""Display formatting helpers."""

from __future__ import annotations


def format_bytes(size_bytes: int) -> str:
    """Format a byte count using binary units with stable precision."""
    sign = "-" if size_bytes < 0 else ""
    value = float(abs(size_bytes))
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{sign}{int(value)} {unit}"
            return f"{sign}{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def reduction_percentage(source_bytes: int, output_bytes: int) -> float:
    """Return signed percentage reduction, or zero for an empty source."""
    if source_bytes == 0:
        return 0.0
    return ((source_bytes - output_bytes) / source_bytes) * 100

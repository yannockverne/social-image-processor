"""Centralized visual theme for the desktop interface."""

from __future__ import annotations

import os
import re

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QWidget


ACCENT = "#4f9cf9"


STYLESHEET = f"""
QWidget {{
    color: #e7eaf0;
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}}
QMainWindow, QWidget#mainContent {{ background-color: #111419; }}
QLabel {{ background: transparent; }}
QLabel#appTitle {{
    color: #f4f6fa;
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 1px;
}}
QLabel#appSubtitle {{ color: #858d9b; font-size: 12px; }}
QLabel#sectionTitle {{
    color: #aeb5c1;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
}}
QLabel#fieldLabel {{ color: #aeb5c1; font-weight: 600; }}
QFrame#card, QWidget#previewPanel, QFrame#footer {{
    background-color: #1a1e24;
    border: 1px solid #2a3039;
    border-radius: 8px;
}}
QLineEdit, QSpinBox {{
    min-height: 30px;
    padding: 0 9px;
    background-color: #12151a;
    border: 1px solid #343b46;
    border-radius: 5px;
    selection-background-color: {ACCENT};
}}
QLineEdit:hover, QSpinBox:hover {{ border-color: #485261; }}
QLineEdit:focus, QSpinBox:focus {{ border: 1px solid {ACCENT}; }}
QPushButton {{
    min-height: 30px;
    padding: 0 13px;
    background-color: #292f38;
    border: 1px solid #3a424e;
    border-radius: 5px;
    color: #e1e5eb;
    font-weight: 600;
}}
QPushButton:hover {{ background-color: #333b47; border-color: #505b6b; }}
QPushButton:pressed {{ background-color: #222831; }}
QPushButton:disabled {{ color: #686f7a; background-color: #20242a; border-color: #292e36; }}
QPushButton[role="secondary"] {{
    min-height: 26px;
    padding: 0 10px;
    background-color: transparent;
    color: #aeb8c7;
}}
QPushButton[role="secondary"]:hover {{ background-color: #272d35; color: #edf1f7; }}
QPushButton#processButton {{
    min-width: 172px;
    min-height: 40px;
    padding: 0 22px;
    background-color: {ACCENT};
    border: 1px solid #67aafb;
    color: #08111d;
    font-size: 13px;
    font-weight: 800;
}}
QPushButton#processButton:hover {{ background-color: #69adff; }}
QPushButton#processButton:pressed {{ background-color: #3c88e5; }}
QCheckBox {{ spacing: 8px; font-weight: 600; }}
QTableView {{
    background-color: #171b20;
    alternate-background-color: #1b2026;
    border: 1px solid #2a3039;
    border-radius: 7px;
    gridline-color: transparent;
    selection-background-color: #244d78;
    selection-color: #ffffff;
    outline: none;
}}
/* Keep item-view check indicators on the native style geometry. In particular,
   padding this subcontrol makes the Windows style paint and hit-test a
   checkable model item with different rectangles. */
QTableView::item {{ border-bottom: 1px solid #232932; }}
QTableView::item:selected {{ background-color: #244d78; border-bottom-color: #35689a; }}
QHeaderView::section {{
    background-color: #20252c;
    color: #aeb6c2;
    border: none;
    border-right: 1px solid #303640;
    border-bottom: 1px solid #343b46;
    padding: 9px 8px;
    font-size: 11px;
    font-weight: 700;
}}
QTableCornerButton::section {{ background-color: #20252c; border: none; }}
QTextEdit {{
    background-color: #12161b;
    border: 1px solid #2a3039;
    border-radius: 7px;
    padding: 8px;
    color: #cbd1da;
    font-family: "Cascadia Mono", "Consolas", monospace;
    /* Keep the inherited pixel sizing mode explicit when changing families.
       On the Windows style engine, resolving a family-only QTextEdit rule
       against QWidget's pixel-sized font feeds pointSize() (-1) back into
       QFont::setPointSize. */
    font-size: 13px;
    selection-background-color: #315f8d;
}}
QLabel#previewTitle {{ color: #f0f2f6; font-size: 14px; font-weight: 700; }}
QLabel#previewImage {{
    background-color: #0c0e12;
    border: 1px solid #2c333d;
    border-radius: 5px;
    color: #737c89;
}}
QLabel#previewStatus {{ color: #8e97a5; font-size: 12px; }}
QFrame#metric {{ background-color: #15191e; border: 1px solid #292f38; border-radius: 6px; }}
QLabel#metricLabel {{ color: #818a97; font-size: 10px; font-weight: 700; }}
QLabel#metricValue {{ color: #f1f3f7; font-size: 17px; font-weight: 700; }}
QLabel#statusText {{ color: #c6ccd5; font-weight: 600; }}
QProgressBar {{
    min-height: 8px; max-height: 8px;
    background-color: #0f1216;
    border: 1px solid #2b313a;
    border-radius: 4px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{ background-color: {ACCENT}; border-radius: 3px; }}
QSplitter::handle {{ background-color: #111419; }}
QSplitter::handle:horizontal {{ width: 8px; }}
QSplitter::handle:vertical {{ height: 8px; }}
QScrollBar:vertical {{ background: #15191e; width: 11px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #3a424d; border-radius: 5px; min-height: 28px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QStatusBar {{ background-color: #111419; color: #9ca5b2; }}
QToolTip {{ background-color: #282e37; color: #f0f2f5; border: 1px solid #424b58; padding: 5px; }}
"""


# TEMPORARY: native-Windows stylesheet bisect support.  STYLESHEET remains the
# production source of truth; rules are only filtered when the diagnostic
# environment variable is explicitly present.
STYLE_DIAGNOSTIC_GROUPS = (
    "global",
    "labels",
    "cards",
    "inputs",
    "buttons",
    "checkboxes",
    "tables",
    "headers",
    "text_edits",
    "preview",
    "progress",
    "scrollbars_and_chrome",
)

# TEMPORARY: property-level follow-up for the confirmed ``global`` group.  The
# names deliberately describe both the selector and declaration so native
# Windows results can identify the exact QSS input without ambiguity.
GLOBAL_STYLE_DIAGNOSTIC_SUBSETS = (
    "qwidget-color",
    "qwidget-font-family",
    "qwidget-font-size",
    "main-window-background-color",
)

_QSS_RULE = re.compile(r"(?:/\*.*?\*/\s*)?([^{}]+)\{[^{}]*\}", re.DOTALL)
_QSS_DECLARATION = re.compile(r"([\w-]+)\s*:\s*([^;]+);", re.DOTALL)


def _style_group(selector: str) -> str:
    """Classify one existing QSS rule without changing the production QSS."""
    if "QPushButton" in selector:
        return "buttons"
    if "QTableView" in selector:
        return "tables"
    if "QHeaderView" in selector or "QTableCornerButton" in selector:
        return "headers"
    if "QTextEdit" in selector:
        return "text_edits"
    if "QLineEdit" in selector or "QSpinBox" in selector:
        return "inputs"
    if "QCheckBox" in selector:
        return "checkboxes"
    if "QProgressBar" in selector:
        return "progress"
    if any(name in selector for name in ("preview", "metric")):
        return "preview"
    if "QFrame#card" in selector or "QFrame#footer" in selector:
        return "cards"
    if "QLabel" in selector:
        return "labels"
    if any(
        name in selector
        for name in ("QScrollBar", "QSplitter", "QStatusBar", "QToolTip")
    ):
        return "scrollbars_and_chrome"
    return "global"


def diagnostic_style_selection(value: str) -> set[str]:
    """Resolve a diagnostic mode to enabled group names."""
    all_groups = set(STYLE_DIAGNOSTIC_GROUPS)
    normalized = value.strip().lower()
    midpoint = len(STYLE_DIAGNOSTIC_GROUPS) // 2
    if normalized in ("all", ""):
        return all_groups
    if normalized == "none":
        return set()
    if normalized == "first-half":
        return set(STYLE_DIAGNOSTIC_GROUPS[:midpoint])
    if normalized == "second-half":
        return set(STYLE_DIAGNOSTIC_GROUPS[midpoint:])
    operation, separator, names = normalized.partition(":")
    if not separator or operation not in ("include", "exclude"):
        raise ValueError(
            "expected all, none, first-half, second-half, include:<groups>, "
            "or exclude:<groups>"
        )
    requested = {name.strip() for name in names.split(",") if name.strip()}
    unknown = requested - all_groups
    if unknown:
        raise ValueError(f"unknown stylesheet group(s): {', '.join(sorted(unknown))}")
    return requested if operation == "include" else all_groups - requested


def diagnostic_global_selection(value: str) -> set[str]:
    """Resolve the temporary property-level selection within ``global``."""
    all_subsets = set(GLOBAL_STYLE_DIAGNOSTIC_SUBSETS)
    normalized = value.strip().lower()
    if normalized in ("all", ""):
        return all_subsets
    if normalized == "none":
        return set()
    operation, separator, names = normalized.partition(":")
    if not separator or operation not in ("include", "exclude"):
        raise ValueError("expected all, none, include:<subsets>, or exclude:<subsets>")
    requested = {name.strip() for name in names.split(",") if name.strip()}
    unknown = requested - all_subsets
    if unknown:
        raise ValueError(
            f"unknown global stylesheet subset(s): {', '.join(sorted(unknown))}"
        )
    return requested if operation == "include" else all_subsets - requested


def _global_subset(selector: str, property_name: str) -> str | None:
    """Return the diagnostic name for one declaration in a global rule."""
    normalized_selector = " ".join(selector.split())
    if normalized_selector == "QWidget" and property_name in (
        "color",
        "font-family",
        "font-size",
    ):
        return f"qwidget-{property_name}"
    if (
        normalized_selector == "QMainWindow, QWidget#mainContent"
        and property_name == "background-color"
    ):
        return "main-window-background-color"
    return None


def diagnostic_stylesheet(
    enabled: set[str], global_subsets: set[str] | None = None
) -> str:
    """Filter complete rules while retaining their original cascade order."""
    selected_rules: list[str] = []
    for match in _QSS_RULE.finditer(STYLESHEET):
        selector = match.group(1).strip()
        group = _style_group(selector)
        if group not in enabled:
            continue
        if group != "global" or global_subsets is None:
            selected_rules.append(match.group(0))
            continue
        declarations = [
            f"    {property_name}: {value.strip()};"
            for property_name, value in _QSS_DECLARATION.findall(match.group(0))
            if _global_subset(selector, property_name) in global_subsets
        ]
        if declarations:
            selected_rules.append(f"{selector} {{\n" + "\n".join(declarations) + "\n}")
    return "\n".join(selected_rules)


def configure_application_font(application: QApplication) -> None:
    """Set the base font before any widgets can inherit or polish it.

    On Windows, changing the application font after constructing the widget
    tree makes Qt propagate it through already pixel-sized stylesheet fonts.
    QHeaderView's private section widgets then pass the pixel font's invalid
    point-size sentinel to QFont::setPointSize.  Configuring the same visual
    font before widget construction avoids that mixed-unit propagation path.
    """
    font = QFont(application.font())
    font.setFamily("Segoe UI")
    if font.pointSize() > 0:
        font.setPointSize(10)
    elif font.pixelSize() > 0:
        font.setPixelSize(font.pixelSize())
    application.setFont(font)


def apply_theme(widget: QWidget) -> None:
    """Apply the application theme without changing inherited widget fonts."""
    diagnostic_mode = os.environ.get("SIP_STYLE_DIAGNOSTIC")
    if diagnostic_mode is None:
        widget.setStyleSheet(STYLESHEET)
        return
    enabled = diagnostic_style_selection(diagnostic_mode)
    global_mode = os.environ.get("SIP_GLOBAL_STYLE_DIAGNOSTIC")
    global_subsets = (
        diagnostic_global_selection(global_mode) if global_mode is not None else None
    )
    widget.setStyleSheet(diagnostic_stylesheet(enabled, global_subsets))

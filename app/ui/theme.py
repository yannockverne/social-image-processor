"""Centralized visual theme for the desktop interface."""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QWidget


ACCENT = "#4f9cf9"


STYLESHEET = f"""
QWidget {{
    color: #e7eaf0;
    font-family: "Segoe UI", "Inter", sans-serif;
}}
QMainWindow, QWidget#mainContent {{ background-color: #111419; }}
QMenuBar {{ background-color: #171b20; color: #d8dde5; }}
QMenuBar::item:selected, QMenu::item:selected {{ background-color: #2b5278; }}
QMenu {{ background-color: #1d2229; border: 1px solid #343b46; padding: 4px; }}
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
QFrame#card, QFrame[role="workflowCard"], QWidget#previewPanel, QFrame#footer {{
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
QLabel#metricValue {{ color: #f1f3f7; font-size: 15px; font-weight: 700; }}
QLabel#statusText {{ color: #c6ccd5; font-weight: 600; }}
QLabel#integrationStatus {{ color: #aeb5c1; font-weight: 600; }}
QLabel#readySummary {{ color: #cbd1da; font-weight: 600; }}
QPushButton#trelloCardSelector {{ text-align: left; }}
QWidget#loadingOverlay {{ background-color: rgba(17, 20, 25, 205); }}
QLabel#loadingMessage {{ color: #f0f3f8; font-size: 14px; font-weight: 700; }}
QProgressBar#loadingSpinner {{ min-height: 4px; max-height: 4px; }}
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


def configure_application_font(application: QApplication) -> None:
    """Set the base font before any widgets can inherit or polish it.

    The application font supplies the default text size, so the global QWidget
    rule does not need a pixel-size override.  Keeping the default in point
    units avoids passing a pixel font's invalid point-size sentinel through the
    native Windows style while retaining the established 10-point visual scale.
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
    widget.setStyleSheet(STYLESHEET)

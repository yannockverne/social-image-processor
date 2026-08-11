"""Application entry point."""

from __future__ import annotations

import sys


def main() -> int:
    """Start the Qt application without side effects when imported."""
    from PySide6.QtWidgets import QApplication
    from app.ui.main_window import MainWindow

    application = QApplication(sys.argv)
    application.setApplicationName("Social Image Processor")
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())

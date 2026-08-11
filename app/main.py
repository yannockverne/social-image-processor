"""Application entry point."""

from __future__ import annotations

import sys


def main() -> int:
    """Start the Qt application.

    The complete main window is introduced in the UI phase. Keeping Qt imports
    inside this function makes importing the package safe in non-GUI contexts.
    """
    from PySide6.QtWidgets import QApplication, QLabel

    application = QApplication(sys.argv)
    placeholder = QLabel("Social Image Processor")
    placeholder.setMinimumSize(480, 240)
    placeholder.setWindowTitle("Social Image Processor")
    placeholder.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())

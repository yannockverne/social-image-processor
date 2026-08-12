"""Application entry point."""

from __future__ import annotations

import sys


def main() -> int:
    """Start the Qt application without side effects when imported."""
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from app.ui.main_window import MainWindow
    from app.ui.theme import configure_application_font
    from app.utils.resources import resource_path

    application = QApplication(sys.argv)
    application.setApplicationName("Social Image Processor")
    # Establish the default family and 10-point scale before widgets inherit it.
    configure_application_font(application)
    application.setWindowIcon(
        QIcon(str(resource_path("app/assets/icons/social_image_processor.png")))
    )
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())

"""Application entry point."""

from __future__ import annotations

import sys


def main() -> int:
    """Start the Qt application without side effects when imported."""
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from app.ui.startup_diagnostics import install_message_handler, marker, widget_state
    from app.ui.main_window import MainWindow
    from app.ui.theme import configure_application_font
    from app.utils.resources import resource_path

    install_message_handler()
    marker("QApplication creation started")
    application = QApplication(sys.argv)
    marker("QApplication created")
    application.setApplicationName("Social Image Processor")
    # QApplication::setFont must run before MainWindow constructs table/header
    # internals; late propagation mixes point- and pixel-sized QSS fonts on
    # the native Windows style and produces QFont::setPointSize(-1).
    configure_application_font(application)
    marker("application font configured")
    application.setWindowIcon(
        QIcon(str(resource_path("app/assets/icons/social_image_processor.png")))
    )
    marker("MainWindow construction started")
    window = MainWindow()
    marker("MainWindow construction completed")
    widget_state("MainWindow", window)
    marker("show() started")
    window.show()
    marker("show() completed")
    marker("processEvents() started")
    application.processEvents()
    marker("processEvents() completed; entering application event loop")
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())

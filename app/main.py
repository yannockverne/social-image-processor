"""Application entry point."""

from __future__ import annotations

import os
import sys


def main() -> int:
    """Start the Qt application without side effects when imported."""
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from app.ui.startup_diagnostics import (
        install_message_handler,
        marker,
        report_style_diagnostic,
        widget_state,
    )
    from app.ui.main_window import MainWindow
    from app.ui.theme import (
        STYLE_DIAGNOSTIC_GROUPS,
        configure_application_font,
        diagnostic_style_selection,
    )
    from app.utils.resources import resource_path

    diagnostic_mode = os.environ.get("SIP_STYLE_DIAGNOSTIC")
    if diagnostic_mode is not None:
        try:
            enabled_groups = diagnostic_style_selection(diagnostic_mode)
        except ValueError as error:
            print(f"SIP_STYLE_DIAGNOSTIC: {error}", file=sys.stderr)
            return 2

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
    if diagnostic_mode is not None:
        report_style_diagnostic(
            diagnostic_mode, enabled_groups, STYLE_DIAGNOSTIC_GROUPS
        )
        window.close()
        return 0
    marker("processEvents() completed; entering application event loop")
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())

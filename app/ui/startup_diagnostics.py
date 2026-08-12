"""Temporary startup tracing for the native Windows Qt warning investigation."""

from __future__ import annotations

import sys

from PySide6.QtCore import QtMsgType, qInstallMessageHandler


_phase = "message handler installation"
_enabled = False


def _write(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _qt_message_handler(message_type, context, message: str) -> None:
    """Forward every Qt message and annotate it with the current startup phase."""
    level = {
        QtMsgType.QtDebugMsg: "debug",
        QtMsgType.QtInfoMsg: "info",
        QtMsgType.QtWarningMsg: "warning",
        QtMsgType.QtCriticalMsg: "critical",
        QtMsgType.QtFatalMsg: "fatal",
    }.get(message_type, str(message_type))
    location = ""
    if context is not None and context.file:
        location = f" {context.file}:{context.line}"
    _write(f"[startup-diagnostic][Qt {level}][phase={_phase}]{location} {message}")


def install_message_handler() -> None:
    """Install before QApplication construction so no startup warning is missed."""
    global _enabled
    _enabled = True
    qInstallMessageHandler(_qt_message_handler)
    marker("Qt message handler installed")


def marker(phase: str) -> None:
    """Set and print the phase attached to subsequent Qt messages."""
    global _phase
    if not _enabled:
        return
    _phase = phase
    _write(f"[startup-diagnostic][phase] {phase}")


def widget_state(label: str, widget) -> None:
    """Print the font and direct-style state of a newly created widget."""
    if not _enabled:
        return
    font = widget.font()
    meta_object = widget.metaObject()
    marker(f"inspect widget: {label}")
    _write(
        "[startup-diagnostic][widget] "
        f"label={label!r} class={meta_object.className()!r} "
        f"objectName={widget.objectName()!r} family={font.family()!r} "
        f"pointSize={font.pointSize()} pixelSize={font.pixelSize()} "
        f"directStylesheet={bool(widget.styleSheet())}"
    )

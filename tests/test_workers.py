"""Regression tests for QRunnable and signal-bridge lifetime."""

from __future__ import annotations

from threading import Event

import pytest

pytest.importorskip(
    "PySide6.QtGui",
    reason="PySide6 GUI runtime libraries are unavailable",
    exc_type=ImportError,
)
from PySide6.QtCore import QObject, QThreadPool, Slot
from PySide6.QtWidgets import QApplication, QWidget
from shiboken6 import delete

from app.ui.workers import FunctionWorker


@pytest.fixture(scope="module")
def application():
    return QApplication.instance() or QApplication([])


def test_worker_completes_after_ui_teardown_without_deleted_signal_source(
    application, capsys
) -> None:
    entered, release = Event(), Event()
    pool = QThreadPool()
    owner = QWidget()

    class Receiver(QObject):
        @Slot(object)
        def receive(self, _value) -> None:
            pass

    receiver = Receiver(owner)

    def delayed_result() -> str:
        entered.set()
        assert release.wait(5)
        return "done"

    worker = FunctionWorker(delayed_result)
    worker.signals.result.connect(receiver.receive)
    pool.start(worker)
    assert entered.wait(5)
    delete(owner)
    release.set()
    assert pool.waitForDone(5000)
    application.processEvents()

    captured = capsys.readouterr()
    assert "Signal source has been deleted" not in captured.err
    assert "Traceback" not in captured.err


def test_worker_emits_result_error_and_finished_normally(application) -> None:
    pool = QThreadPool()
    results, errors, finished = [], [], []
    successful = FunctionWorker(lambda: 42)
    successful.signals.result.connect(results.append)
    successful.signals.error.connect(errors.append)
    successful.signals.finished.connect(finished.append)
    pool.start(successful)
    assert pool.waitForDone(5000)
    application.processEvents()
    assert results == [42]
    assert errors == []
    assert finished == [successful]

    failed = FunctionWorker(lambda: (_ for _ in ()).throw(ValueError("broken")))
    failed.signals.result.connect(results.append)
    failed.signals.error.connect(errors.append)
    failed.signals.finished.connect(finished.append)
    pool.start(failed)
    assert pool.waitForDone(5000)
    application.processEvents()
    assert results == [42]
    assert errors == ["ValueError: broken"]
    assert finished == [successful, failed]

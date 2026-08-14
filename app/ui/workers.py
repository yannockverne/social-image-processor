"""Qt adapters which execute synchronous services and Pillow work off-thread."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from threading import Lock

from PIL import Image
from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from app.core.image_processing import composite_full_frame


class WorkerSignals(QObject):
    result = Signal(object)
    event = Signal(object)
    error = Signal(str)
    finished = Signal(object)


_running_workers: set[FunctionWorker | BatchWorker] = set()
_running_workers_lock = Lock()


def _retain_running(worker: FunctionWorker | BatchWorker) -> None:
    """Keep the Python runnable and its QObject signal source alive in run()."""
    with _running_workers_lock:
        _running_workers.add(worker)


def _release_running(worker: FunctionWorker | BatchWorker) -> None:
    with _running_workers_lock:
        _running_workers.discard(worker)


class FunctionWorker(QRunnable):
    def __init__(self, function, *args, **kwargs) -> None:
        super().__init__()
        # The Python wrapper owns WorkerSignals.  Native QThreadPool auto-delete
        # can invalidate that ownership at the end of run on some PySide6 platform.
        self.setAutoDelete(False)
        self.function, self.args, self.kwargs = function, args, kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        _retain_running(self)
        try:
            self.signals.result.emit(self.function(*self.args, **self.kwargs))
        except Exception as error:
            self.signals.error.emit(f"{type(error).__name__}: {error}")
        finally:
            try:
                self.signals.finished.emit(self)
            finally:
                _release_running(self)


def render_preview_bytes(
    source: Path,
    size: tuple[int, int],
    watermark: Path | None = None,
    watermark_size_ratio: float | None = None,
) -> bytes:
    """Return a bounded PNG preview; only exact-match paths are supplied by UI."""
    with Image.open(source) as image:
        image.load()
        if watermark is not None:
            with Image.open(watermark) as overlay:
                overlay.load()
                image = composite_full_frame(image, overlay, watermark_size_ratio)
        image.thumbnail(size, Image.Resampling.LANCZOS)
        output = BytesIO()
        image.convert("RGBA").save(output, "PNG")
        return output.getvalue()


class BatchWorker(QRunnable):
    """Thin signal adapter around an already-configured BatchProcessor."""

    def __init__(self, processor) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.processor = processor
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        _retain_running(self)
        try:
            result = self.processor.process(self.signals.event.emit)
            self.signals.result.emit(result)
        except Exception as error:
            self.signals.error.emit(f"{type(error).__name__}: {error}")
        finally:
            try:
                self.signals.finished.emit(self)
            finally:
                _release_running(self)

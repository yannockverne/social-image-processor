from __future__ import annotations

from pathlib import Path
from threading import Event

import pytest

pytest.importorskip(
    "PySide6.QtGui",
    reason="PySide6 GUI runtime libraries are unavailable",
    exc_type=ImportError,
)
from PIL import Image
from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtGui import QCloseEvent, QPixmap
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from app.models.image_item import ImageItem
from app.models.profiles import ExportPlatform
from app.models.results import (
    BatchStatistics,
    ExportResult,
    ExportStatus,
    ProgressUpdate,
    SuccessfulOutput,
)
from app.models.settings import ApplicationSettings
from app.services.settings_service import SettingsService
from app.services.folder_scanner import WatermarkScanResult
from app.core.watermarking import WatermarkCatalog
from app.ui.image_table import ImageTableModel
from app.ui.main_window import MainWindow
from app.ui.workers import FunctionWorker


@pytest.fixture(scope="module")
def application():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(application, tmp_path: Path):
    settings = SettingsService(tmp_path / "settings.json")
    widget = MainWindow(settings)
    yield widget
    widget.pool.waitForDone(5000)
    widget.close()


def test_window_constructs_and_restores_settings(application, tmp_path: Path) -> None:
    service = SettingsService(tmp_path / "settings.json")
    service.save(
        ApplicationSettings(Path("input"), Path("output"), Path("marks"), 87, False)
    )
    window = MainWindow(service)
    assert window.input_path.text() == "input"
    assert window.output_path.text() == "output"
    assert window.watermark_path.text() == "marks"
    assert window.quality.value() == 87
    assert not window.watermark_enabled.isChecked()
    assert window.minimumSizeHint().width() <= 1920
    assert window.minimumSizeHint().height() <= 1080
    window.pool.waitForDone(5000)
    window.close()


def test_launch_with_saved_paths_defers_and_safely_restores_scans(
    application, tmp_path: Path, monkeypatch
) -> None:
    input_directory = tmp_path / "input"
    output_directory = tmp_path / "output"
    watermark_directory = tmp_path / "watermarks"
    input_directory.mkdir()
    output_directory.mkdir()
    watermark_directory.mkdir()
    Image.new("RGB", (2, 2)).save(input_directory / "source.jpg")
    Image.new("RGBA", (2, 2)).save(watermark_directory / "mark.png")
    service = SettingsService(tmp_path / "settings.json")
    service.save(
        ApplicationSettings(
            input_directory, output_directory, watermark_directory, 87, True
        )
    )
    starts = []
    original_start = MainWindow._scan_restored_paths
    monkeypatch.setattr(
        MainWindow,
        "_scan_restored_paths",
        lambda self: (starts.append(True), original_start(self))[-1],
    )

    window = MainWindow(service)
    assert starts == []
    assert window.input_path.text() == str(input_directory)
    application.processEvents()
    assert starts == [True]
    assert window.pool.waitForDone(5000)
    application.processEvents()
    assert window.pool.waitForDone(5000)
    application.processEvents()
    assert [item.path.name for item in window.model.items] == ["source.jpg"]
    window.close()


def test_launch_with_stale_saved_paths_does_not_start_workers(
    application, tmp_path: Path, monkeypatch
) -> None:
    service = SettingsService(tmp_path / "settings.json")
    missing = tmp_path / "no-longer-there"
    service.save(ApplicationSettings(missing, tmp_path, missing, 92, True))

    window = MainWindow(service)
    starts = []
    monkeypatch.setattr(window.pool, "start", lambda worker: starts.append(worker))
    application.processEvents()

    assert starts == []
    assert "unavailable" in window.log.toPlainText()
    window.close()


@pytest.mark.parametrize(
    ("directory_name", "button_name", "path_name"),
    (
        ("input", "input_browse", "input_path"),
        ("watermarks", "watermark_browse", "watermark_path"),
    ),
)
def test_browse_commits_path_then_defers_exactly_one_scan(
    window,
    application,
    tmp_path: Path,
    monkeypatch,
    directory_name: str,
    button_name: str,
    path_name: str,
) -> None:
    selected = tmp_path / directory_name
    selected.mkdir()
    starts = []

    def select_directory(*_args):
        getattr(window, path_name).editingFinished.emit()
        return str(selected)

    monkeypatch.setattr(QFileDialog, "getExistingDirectory", select_directory)
    monkeypatch.setattr(window, "_start_worker", lambda worker: starts.append(worker))

    getattr(window, button_name).click()

    assert getattr(window, path_name).text() == str(selected)
    assert starts == []
    # Windows can deliver this focus-loss signal after the native dialog
    # callback has committed the selected path.
    getattr(window, path_name).editingFinished.emit()
    application.processEvents()
    assert len(starts) == 1
    application.processEvents()
    assert len(starts) == 1


@pytest.mark.parametrize("button_name", ("input_browse", "watermark_browse"))
def test_cancelled_browse_does_not_start_scan(
    window, application, monkeypatch, button_name: str
) -> None:
    starts = []
    path_name = "input_path" if button_name == "input_browse" else "watermark_path"

    def cancel_dialog(*_args):
        getattr(window, path_name).editingFinished.emit()
        return ""

    monkeypatch.setattr(QFileDialog, "getExistingDirectory", cancel_dialog)
    monkeypatch.setattr(window, "_start_worker", lambda worker: starts.append(worker))

    getattr(window, button_name).click()
    getattr(window, path_name).editingFinished.emit()
    application.processEvents()

    assert starts == []


@pytest.mark.parametrize(
    "path_name",
    ("input_path", "watermark_path"),
)
def test_manual_path_edit_still_starts_one_scan(
    window, tmp_path: Path, monkeypatch, path_name: str
) -> None:
    starts = []
    monkeypatch.setattr(window, "_start_worker", lambda worker: starts.append(worker))
    edit = getattr(window, path_name)

    edit.setText(str(tmp_path))
    edit.textEdited.emit(str(tmp_path))
    edit.editingFinished.emit()

    assert len(starts) == 1


def test_stale_watermark_scan_result_is_ignored(window) -> None:
    current = WatermarkCatalog({(2, 2): [Path("current.png")]})
    stale = WatermarkCatalog({(3, 3): [Path("stale.png")]})
    window.watermark_generation = 2

    window._watermarks_ready(2, WatermarkScanResult(current))
    window._watermarks_ready(1, WatermarkScanResult(stale))

    assert window.catalog.match((2, 2)).exact_path == Path("current.png")
    assert window.catalog.match((3, 3)).exact_path is None


def test_worker_and_signal_bridge_are_retained_until_finished(
    window, application
) -> None:
    entered, release = Event(), Event()

    def wait_for_release() -> str:
        entered.set()
        assert release.wait(5)
        return "done"

    worker = FunctionWorker(wait_for_release)
    results = []
    worker.signals.result.connect(results.append)
    window._start_worker(worker)

    assert entered.wait(5)
    assert worker in window._active_workers
    release.set()
    assert window.pool.waitForDone(5000)
    assert worker in window._active_workers
    application.processEvents()
    assert results == ["done"]
    assert worker not in window._active_workers


def test_platform_bulk_actions_are_isolated_and_stale_thumbnail_ignored(window) -> None:
    window.model.replace_items([ImageItem(Path("one.png"), 10, 5, 100)], 4)
    window.model.set_platform_all(ImageTableModel.X, True)
    assert window.model.items[0].export_to_x
    assert not window.model.items[0].export_to_instagram
    window.model.set_platform_all(ImageTableModel.INSTAGRAM, True)
    window.model.set_platform_all(ImageTableModel.X, False)
    assert not window.model.items[0].export_to_x
    assert window.model.items[0].export_to_instagram
    assert not window.model.set_thumbnail(0, 3, QPixmap(2, 2))
    assert window.model.data(window.model.index(0, 0), Qt.DecorationRole) is None


def test_selection_and_watermark_toggle_refresh_preview(window, monkeypatch) -> None:
    window.model.replace_items([ImageItem(Path("one.png"), 10, 5, 100)], 1)
    calls = []
    monkeypatch.setattr(window, "_refresh_selected_preview", lambda: calls.append(True))
    window.table.selectionModel().select(
        window.model.index(0, 0),
        QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows,
    )
    window.watermark_enabled.setChecked(not window.watermark_enabled.isChecked())
    assert len(calls) >= 2


def test_progress_results_statistics_and_completion_restore_controls(
    window, tmp_path: Path
) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (2, 2)).save(source)
    output = tmp_path / "X_source.jpg"
    output.write_bytes(b"123")
    window.model.replace_items([ImageItem(source, 2, 2, 100, True)], 1)
    window._set_batch_running(True)
    assert not window.input_path.isEnabled()
    window.progress.setRange(0, 1)
    window._batch_event(ProgressUpdate(1, 1, source))
    result = ExportResult(source, ExportPlatform.X, ExportStatus.SUCCEEDED, output, 3)
    window._batch_event(SuccessfulOutput(result))
    window._batch_event(BatchStatistics(1, 1, 100, 125))
    assert window.progress.value() == 1
    assert "X_source.jpg" in window.log.toPlainText()
    assert window.stat_saved.text() == "-25 B"
    assert window.stat_reduction.text() == "-25.0 %"
    window._set_batch_running(False)
    assert window.input_path.isEnabled()


def test_close_is_rejected_during_processing(window, monkeypatch) -> None:
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: None)
    window.batch_running = True
    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted()
    window.batch_running = False


def test_empty_folder_fields_are_rejected_for_processing(window, monkeypatch) -> None:
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: messages.append(True))
    window.input_path.clear()
    window.output_path.clear()

    window.start_processing()

    assert messages == [True]
    assert not window.batch_running


def test_import_has_no_application_start_side_effect() -> None:
    import app.main

    assert callable(app.main.main)

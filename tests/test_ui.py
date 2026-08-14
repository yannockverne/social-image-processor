from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from threading import Event

import pytest

pytest.importorskip(
    "PySide6.QtGui",
    reason="PySide6 GUI runtime libraries are unavailable",
    exc_type=ImportError,
)
from PIL import Image
from PySide6.QtCore import (
    QEvent,
    QItemSelectionModel,
    QModelIndex,
    Qt,
    QtMsgType,
    qInstallMessageHandler,
)
from PySide6.QtGui import QCloseEvent, QFont, QHelpEvent, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMessageBox,
    QStyle,
    QStyleOptionViewItem,
    QTextEdit,
    QWidget,
)

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
from app.ui.image_table import ImageTableModel, PlatformCheckDelegate
from app.ui.main_window import MainWindow
from app.ui.theme import apply_theme, configure_application_font
from app.ui.workers import FunctionWorker


@pytest.fixture(scope="module")
def application():
    return QApplication.instance() or QApplication([])


def process_deferred_scan(application) -> None:
    """Run both the scan-source timer and the coalesced dispatch timer."""
    application.processEvents()
    application.processEvents()


def test_theme_uses_valid_application_font_for_default_text_size(application) -> None:
    original_font = QFont(application.font())
    point_font = QFont(original_font)
    point_font.setPointSize(9)
    application.setFont(point_font)
    messages: list[str] = []

    def capture_font_warnings(message_type, _context, message) -> None:
        if message_type == QtMsgType.QtWarningMsg:
            messages.append(message)

    previous_handler = qInstallMessageHandler(capture_font_warnings)
    widget = None

    try:
        configure_application_font(application)
        widget = QWidget()
        apply_theme(widget)
        widget.ensurePolished()
        application.processEvents()

        assert application.font().family() == "Segoe UI"
        assert application.font().pointSize() == 10
        assert widget.font().family() == "Segoe UI"
        assert widget.font().pointSize() == 10
        assert not any("QFont::setPointSize" in message for message in messages)
        global_rule = widget.styleSheet().split("QMainWindow", 1)[0]
        assert "font-size" not in global_rule
    finally:
        qInstallMessageHandler(previous_handler)
        application.setFont(original_font)
        if widget is not None:
            widget.close()


def test_theme_preserves_pixel_sized_application_font(application) -> None:
    original_font = QFont(application.font())
    pixel_font = QFont(original_font)
    pixel_font.setPixelSize(17)
    application.setFont(pixel_font)
    widget = QWidget()

    try:
        configure_application_font(application)
        apply_theme(widget)

        themed_font = application.font()
        assert themed_font.pointSize() == -1
        assert themed_font.pixelSize() == 17
        assert themed_font.family() == "Segoe UI"
    finally:
        application.setFont(original_font)
        widget.close()


def test_theme_text_edit_family_preserves_inherited_pixel_size(application) -> None:
    """A family override must not reinterpret QWidget's pixel size as points."""
    original_font = QFont(application.font())
    messages: list[str] = []

    def capture_font_warnings(message_type, _context, message) -> None:
        if message_type == QtMsgType.QtWarningMsg:
            messages.append(message)

    previous_handler = qInstallMessageHandler(capture_font_warnings)
    widget = QWidget()
    editor = QTextEdit(widget)

    try:
        configure_application_font(application)
        apply_theme(widget)
        widget.ensurePolished()
        editor.ensurePolished()
        application.processEvents()

        assert editor.font().pixelSize() == 13
        assert not any("QFont::setPointSize" in message for message in messages)
    finally:
        qInstallMessageHandler(previous_handler)
        application.setFont(original_font)
        widget.close()


def test_normal_window_startup_has_no_invalid_point_size_warning(
    application, tmp_path: Path
) -> None:
    """Exercise dynamic children, QTextEdit, table, and both header paths."""
    original_font = QFont(application.font())
    messages: list[str] = []

    def capture_font_warnings(message_type, _context, message) -> None:
        if message_type == QtMsgType.QtWarningMsg:
            messages.append(message)

    configure_application_font(application)
    previous_handler = qInstallMessageHandler(capture_font_warnings)
    window = MainWindow(SettingsService(tmp_path / "settings.json"))
    try:
        window.ensurePolished()
        for child in window.findChildren(QWidget):
            child.ensurePolished()
        window.table.horizontalHeader().ensurePolished()
        window.table.verticalHeader().ensurePolished()
        application.processEvents()
        assert not any("QFont::setPointSize" in message for message in messages)
    finally:
        window.close()
        qInstallMessageHandler(previous_handler)
        application.setFont(original_font)


def drain_window_work(application, window) -> None:
    """Drain deferred scans, workers, and the result callbacks they can enqueue."""
    for _ in range(6):
        application.processEvents()
        assert window.pool.waitForDone(5000)
    application.processEvents()


@pytest.fixture
def window(application, tmp_path: Path):
    settings = SettingsService(tmp_path / "settings.json")
    widget = MainWindow(settings)
    yield widget
    # Drain both queued scan dispatches and their worker completion signals.
    # This also runs after a failed assertion, preventing close protection from
    # turning the original failure into a modal-dialog hang on Windows.
    for _ in range(6):
        application.processEvents()
        widget.pool.waitForDone(5000)
    application.processEvents()
    widget.close()


class EmptySettingsService:
    """Keep focused UI tests independent of persisted application state."""

    def load(self) -> ApplicationSettings:
        return ApplicationSettings()

    def save(self, settings: ApplicationSettings) -> None:
        pass


@pytest.fixture
def window_without_restored_paths(application):
    """Create a window whose deferred restoration callback cannot start a scan."""
    widget = MainWindow(EmptySettingsService())
    yield widget
    application.processEvents()
    assert widget.pool.waitForDone(5000)
    application.processEvents()
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
    assert window.trello_update_enabled.text() == "Update Trello card"
    window.pool.waitForDone(5000)
    window.close()


def test_trello_activity_reaches_shared_log(window) -> None:
    window.trello_panel.activity.emit("Trello: X_ready.jpg uploaded.")
    assert "Trello: X_ready.jpg uploaded." in window.log.toPlainText()


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
    drain_window_work(application, window)
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
    process_deferred_scan(application)
    assert len(starts) == 1
    assert isinstance(starts[0], FunctionWorker)
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
    window, application, tmp_path: Path, monkeypatch, path_name: str
) -> None:
    starts = []
    monkeypatch.setattr(window, "_start_worker", lambda worker: starts.append(worker))
    edit = getattr(window, path_name)

    edit.setText(str(tmp_path))
    edit.textEdited.emit(str(tmp_path))
    edit.editingFinished.emit()

    assert starts == []
    application.processEvents()
    assert len(starts) == 1
    assert isinstance(starts[0], FunctionWorker)


@pytest.mark.parametrize(
    ("button_name", "path_name"),
    (
        ("input_browse", "input_path"),
        ("watermark_browse", "watermark_path"),
    ),
)
def test_repeated_same_path_requests_in_one_event_turn_create_one_worker(
    window,
    application,
    tmp_path: Path,
    monkeypatch,
    button_name: str,
    path_name: str,
) -> None:
    starts = []
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", lambda *_args: str(tmp_path)
    )
    monkeypatch.setattr(window, "_start_worker", lambda worker: starts.append(worker))

    getattr(window, button_name).click()
    # Model the second callback observed on Windows: the still-queued startup
    # restoration callback reads the path just committed by Browse.
    window._scan_restored_paths()
    getattr(window, path_name).editingFinished.emit()

    assert starts == []
    application.processEvents()
    assert len(starts) == 1
    assert isinstance(starts[0], FunctionWorker)


def test_stale_watermark_scan_result_is_ignored(window) -> None:
    current = WatermarkCatalog([Path("current.png")])
    stale = WatermarkCatalog([Path("stale.png")])
    window.settings = ApplicationSettings(selected_watermark="current.png")
    window.watermark_generation = 2

    window._watermarks_ready(2, WatermarkScanResult(current))
    window._watermarks_ready(1, WatermarkScanResult(stale))

    assert window.catalog.paths == (Path("current.png"),)
    assert window.catalog.find("current.png") == Path("current.png")
    assert window.catalog.find("stale.png") is None
    assert window.watermark_selector.currentData() == "current.png"


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


@pytest.mark.parametrize(
    ("column", "attribute"),
    (
        (ImageTableModel.X, "export_to_x"),
        (ImageTableModel.INSTAGRAM, "export_to_instagram"),
    ),
)
def test_platform_check_state_integer_transitions(
    window, column: int, attribute: str
) -> None:
    """Accept the integer check states emitted by the native item delegate."""
    window.model.replace_items([ImageItem(Path("one.png"), 10, 5, 100)], 1)
    index = window.model.index(0, column)

    assert window.model.setData(index, Qt.CheckState.Checked.value, Qt.CheckStateRole)
    assert getattr(window.model.items[0], attribute) is True
    assert window.model.data(index, Qt.CheckStateRole) == Qt.Checked

    assert window.model.setData(index, Qt.CheckState.Unchecked.value, Qt.CheckStateRole)
    assert getattr(window.model.items[0], attribute) is False
    assert window.model.data(index, Qt.CheckStateRole) == Qt.Unchecked


def test_move_buttons_reorder_complete_items_and_update_order(window) -> None:
    first = ImageItem(Path("first.png"), 10, 5, 100, True, False)
    second = ImageItem(Path("second.png"), 20, 7, 200, False, True)
    window.model.replace_items([first, second], 1)
    window.table.selectRow(1)

    window.move_up_button.click()

    assert window.model.items == [second, first]
    assert window.model.items[0].dimensions == (20, 7)
    assert window.model.items[0].export_to_instagram
    assert not window.model.items[0].export_to_x
    assert window.model.data(window.model.index(0, ImageTableModel.ORDER)) == 1
    window.move_down_button.click()
    assert window.model.items == [first, second]


def _platform_control_rects(window, row: int, column: int):
    index = window.model.index(row, column)
    option = QStyleOptionViewItem()
    delegate = window.table.itemDelegateForIndex(index)
    delegate.initStyleOption(option, index)
    option.rect = window.table.visualRect(index)
    option.widget = window.table
    return delegate.control_rects(option, index)


def test_platform_controls_are_centered_and_warning_follows_item(
    window, application
) -> None:
    supported = ImageItem(Path("square.png"), 1000, 1000, 100)
    unsupported = ImageItem(Path("wide.png"), 2390, 1000, 100)
    window.model.replace_items([supported, unsupported], 1)
    window.show()
    application.processEvents()

    x_check, x_warning = _platform_control_rects(window, 0, ImageTableModel.X)
    x_cell = window.table.visualRect(window.model.index(0, ImageTableModel.X))
    assert abs(x_check.center().x() - x_cell.center().x()) <= 1
    assert abs(x_check.center().y() - x_cell.center().y()) <= 1
    assert x_warning.isEmpty()

    check, warning = _platform_control_rects(window, 1, ImageTableModel.INSTAGRAM)
    instagram_cell = window.table.visualRect(
        window.model.index(1, ImageTableModel.INSTAGRAM)
    )
    group_center_x = (check.left() + warning.right()) // 2
    assert abs(group_center_x - instagram_cell.center().x()) <= 1
    assert abs(check.center().y() - instagram_cell.center().y()) <= 1
    assert abs(warning.center().y() - instagram_cell.center().y()) <= 1
    assert not warning.isEmpty()
    assert (
        window.model.data(
            window.model.index(0, ImageTableModel.INSTAGRAM),
            ImageTableModel.InstagramRatioWarningRole,
        )
        is False
    )

    window.model.move_row(1, -1)
    assert window.model.items[0] is unsupported
    assert (
        window.model.data(
            window.model.index(0, ImageTableModel.INSTAGRAM),
            ImageTableModel.InstagramRatioWarningRole,
        )
        is True
    )


def test_platform_checkbox_native_style_option_tracks_model_state(
    window, application
) -> None:
    window.model.replace_items([ImageItem(Path("one.png"), 10, 5, 100)], 1)
    index = window.model.index(0, ImageTableModel.X)
    option = QStyleOptionViewItem()
    option.widget = window.table
    option.rect = window.table.visualRect(index)
    option.state = QStyle.State_Enabled | QStyle.State_Active
    delegate = window.platform_check_delegate
    indicator_rect, _ = delegate.control_rects(option, index)

    unchecked = delegate._checkbox_style_option(option, index, indicator_rect)
    assert unchecked.checkState == Qt.Unchecked
    assert unchecked.state & QStyle.State_Off
    assert not unchecked.state & QStyle.State_On
    assert unchecked.state & QStyle.State_Enabled
    assert unchecked.state & QStyle.State_Active
    assert unchecked.rect == indicator_rect

    assert window.model.setData(index, Qt.Checked, Qt.CheckStateRole)
    checked = delegate._checkbox_style_option(option, index, indicator_rect)
    assert checked.checkState == Qt.Checked
    assert checked.state & QStyle.State_On
    assert not checked.state & QStyle.State_Off
    assert checked.state & QStyle.State_Enabled
    assert checked.state & QStyle.State_Active
    assert checked.rect == indicator_rect


def test_instagram_warning_is_informational_and_checkbox_remains_clickable(
    window_without_restored_paths, application
) -> None:
    window = window_without_restored_paths
    window.show()
    application.processEvents()
    window.table.setFocus()
    process_deferred_scan(application)

    window.model.replace_items([ImageItem(Path("wide.png"), 2390, 1000, 100)], 1)
    application.processEvents()
    index = window.model.index(0, ImageTableModel.INSTAGRAM)
    check, warning = _platform_control_rects(window, 0, ImageTableModel.INSTAGRAM)
    assert PlatformCheckDelegate.WARNING_TOOLTIP == (
        "Aspect ratio may require cropping for Instagram."
    )

    QTest.mouseClick(window.table.viewport(), Qt.LeftButton, pos=warning.center())
    assert not window.model.items[0].export_to_instagram
    QTest.mouseClick(window.table.viewport(), Qt.LeftButton, pos=check.center())
    application.processEvents()
    assert window.model.items[0].export_to_instagram
    assert window.model.data(index, ImageTableModel.InstagramRatioWarningRole)


def test_instagram_warning_help_event_uses_qhelp_event_positions(
    window_without_restored_paths, application, monkeypatch
) -> None:
    window = window_without_restored_paths
    window.show()
    application.processEvents()
    window.model.replace_items([ImageItem(Path("wide.png"), 2390, 1000, 100)], 1)
    application.processEvents()

    index = window.model.index(0, ImageTableModel.INSTAGRAM)
    option = QStyleOptionViewItem()
    option.widget = window.table
    option.rect = window.table.visualRect(index)
    delegate = window.platform_check_delegate
    _, warning = delegate.control_rects(option, index)
    global_position = window.table.viewport().mapToGlobal(warning.center())
    event = QHelpEvent(QEvent.ToolTip, warning.center(), global_position)
    tooltip_calls = []
    monkeypatch.setattr(
        "app.ui.image_table.QToolTip.showText",
        lambda *args: tooltip_calls.append(args),
    )

    assert not hasattr(event, "position")
    assert delegate.helpEvent(event, window.table, option, index)
    assert tooltip_calls == [
        (global_position, PlatformCheckDelegate.WARNING_TOOLTIP, window.table)
    ]


def test_instagram_checkbox_remains_clickable_without_warning(
    window_without_restored_paths, application
) -> None:
    window = window_without_restored_paths
    window.show()
    application.processEvents()
    window.table.setFocus()
    process_deferred_scan(application)

    window.model.replace_items([ImageItem(Path("square.png"), 1000, 1000, 100)], 1)
    check, warning = _platform_control_rects(window, 0, ImageTableModel.INSTAGRAM)
    assert warning.isEmpty()

    QTest.mouseClick(window.table.viewport(), Qt.LeftButton, pos=check.center())
    application.processEvents()
    assert window.model.items[0].export_to_instagram


def test_table_toolbar_ends_at_table_edge_before_preview(window, application) -> None:
    window.show()
    application.processEvents()

    assert window.move_up_button.parentWidget() is window.table_area
    assert window.move_down_button.parentWidget() is window.table_area
    assert window.table.parentWidget() is window.table_area
    assert window.move_down_button.geometry().right() == window.table.geometry().right()
    assert window.table_area.geometry().right() < window.preview.geometry().left()


def test_drag_drop_reorders_model_items(window) -> None:
    items = [
        ImageItem(Path("a.png"), 1, 1, 1),
        ImageItem(Path("b.png"), 2, 2, 2),
        ImageItem(Path("c.png"), 3, 3, 3),
    ]
    window.model.replace_items(items, 1)
    mime_data = window.model.mimeData([window.model.index(0, 0)])

    assert window.model.dropMimeData(mime_data, Qt.MoveAction, 3, 0, QModelIndex())
    assert window.model.items == [items[1], items[2], items[0]]


@pytest.mark.parametrize(
    ("column", "attribute"),
    (
        (ImageTableModel.X, "export_to_x"),
        (ImageTableModel.INSTAGRAM, "export_to_instagram"),
    ),
)
def test_platform_checkbox_toggles_from_table_view(
    window_without_restored_paths, application, column: int, attribute: str
) -> None:
    window = window_without_restored_paths
    window.show()
    application.processEvents()

    # Move focus away from the path field before installing the controlled row.
    # On Windows that focus transition emits input_path.editingFinished, whose
    # deferred empty-path scan clears the model.  Drain it now so the real
    # checkbox click cannot trigger that unrelated scan for the first time.
    window.table.setFocus()
    process_deferred_scan(application)

    # The fake settings service guarantees that the construction-time
    # _scan_restored_paths callback has no path from which to start a worker.
    window.model.replace_items([ImageItem(Path("one.png"), 10, 5, 100)], 1)
    assert window.model.rowCount() == 1

    index = window.model.index(0, column)
    assert index.isValid()
    assert not getattr(window.model.items[0], attribute)

    cell_rect = window.table.visualRect(index)
    assert cell_rect.isValid()

    # Use the delegate's shared paint/hit-test geometry.  This exercises the
    # native Windows checkbox regression without relying on the style's default
    # (uncentered) item-indicator placement.
    indicator_rect, _ = _platform_control_rects(window, 0, column)
    assert indicator_rect.isValid()
    assert not indicator_rect.isEmpty()

    QTest.mouseClick(
        window.table.viewport(),
        Qt.LeftButton,
        Qt.NoModifier,
        indicator_rect.center(),
    )
    application.processEvents()

    assert window.model.rowCount() == 1
    assert getattr(window.model.items[0], attribute)

    QTest.mouseClick(
        window.table.viewport(),
        Qt.LeftButton,
        Qt.NoModifier,
        indicator_rect.center(),
    )
    application.processEvents()

    assert not getattr(window.model.items[0], attribute)


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


def test_watermark_size_is_session_only_and_refreshes_preview(
    application, tmp_path: Path, monkeypatch
) -> None:
    service = SettingsService(tmp_path / "settings.json")
    first = MainWindow(service)
    calls: list[bool] = []
    monkeypatch.setattr(first, "_refresh_selected_preview", lambda: calls.append(True))

    assert first.watermark_size.value() == 8.0
    assert first.watermark_size.minimum() == 3.0
    assert first.watermark_size.maximum() == 15.0
    assert first.watermark_size.singleStep() == 0.5
    assert first.watermark_size.decimals() == 1

    first.watermark_size.setValue(11.5)
    first.save_settings()
    assert calls == [True]
    assert "watermark_size" not in (tmp_path / "settings.json").read_text()
    first.close()

    reopened = MainWindow(service)
    assert reopened.watermark_size.value() == 8.0
    reopened._set_batch_running(True)
    assert not reopened.watermark_size.isEnabled()
    reopened._set_batch_running(False)
    assert reopened.watermark_size.isEnabled()
    reopened.close()
    application.processEvents()


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


def _capture_configured_batch(window, tmp_path, monkeypatch):
    input_directory = tmp_path / "input"
    output_directory = tmp_path / "output"
    input_directory.mkdir()
    output_directory.mkdir()
    source = input_directory / "source.jpg"
    Image.new("RGB", (8, 4)).save(source)
    window.input_path.setText(str(input_directory))
    window.output_path.setText(str(output_directory))
    window.model.replace_items(
        [ImageItem(source, 8, 4, source.stat().st_size, export_to_x=True)], 1
    )
    window.watermark_enabled.setChecked(False)
    window.r2_upload_enabled.setChecked(True)
    window.r2_worker_url.setText("https://worker.example/upload")
    workers = []
    monkeypatch.setattr(window, "_start_worker", workers.append)
    window.start_processing()
    return workers[0].processor


def test_trello_batch_uses_one_selected_card_id_for_r2_and_update(
    window, tmp_path: Path, monkeypatch
) -> None:
    window.settings = replace(window.settings, r2_remote_prefix="configured-prefix")
    trello_service = object()
    window.trello_panel.service = trello_service
    window.trello_panel.card.addItem("Human-readable title", "trello-card-123")
    window.trello_update_enabled.setChecked(True)

    processor = _capture_configured_batch(window, tmp_path, monkeypatch)

    assert processor._r2_upload_service.remote_prefix == "trello-card-123"
    assert processor._trello_service is trello_service
    assert processor._trello_card_id == "trello-card-123"
    assert window.settings.r2_remote_prefix == "configured-prefix"


def test_r2_only_batch_keeps_configured_prefix_without_requiring_trello(
    window, tmp_path: Path, monkeypatch
) -> None:
    window.settings = replace(window.settings, r2_remote_prefix="configured-prefix")
    window.trello_update_enabled.setChecked(False)
    window.trello_panel.service = None

    processor = _capture_configured_batch(window, tmp_path, monkeypatch)

    assert processor._r2_upload_service.remote_prefix == "configured-prefix"
    assert processor._trello_service is None
    assert processor._trello_card_id is None
    assert window.settings.r2_remote_prefix == "configured-prefix"


def test_import_has_no_application_start_side_effect() -> None:
    import app.main

    assert callable(app.main.main)

"""Main desktop window and GUI-thread orchestration."""

from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path

from PySide6.QtCore import QItemSelection, QSignalBlocker, QThreadPool, QTimer, Qt
from PySide6.QtGui import QCloseEvent, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.watermarking import WatermarkCatalog
from app.models.results import (
    BatchStatistics,
    FailedExport,
    FailedSource,
    ProgressUpdate,
    SkippedSource,
    SuccessfulOutput,
)
from app.models.settings import ApplicationSettings
from app.models.watermark import WatermarkStatus
from app.services.batch_processor import BatchProcessor
from app.services.folder_scanner import scan_input_folder, scan_watermark_folder
from app.services.settings_service import SettingsService
from app.ui.image_table import ImageTableModel
from app.ui.preview_panel import PreviewPanel
from app.ui.theme import apply_theme
from app.ui.trello_panel import TrelloPanel
from app.ui.workers import BatchWorker, FunctionWorker, render_preview_bytes
from app.utils.formatting import format_bytes


class MainWindow(QMainWindow):
    """Functional V1 interface around the existing synchronous services."""

    def __init__(self, settings_service: SettingsService | None = None) -> None:
        super().__init__()
        self.settings_service = settings_service or SettingsService()
        self.settings = self.settings_service.load()
        self.catalog = WatermarkCatalog()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(3)
        # QThreadPool owns the native QRunnable while it runs, but it does not
        # reliably keep the Python wrapper (and its QObject signal bridge)
        # alive on every PySide6 platform.  Retain each worker explicitly.
        self._active_workers: set[FunctionWorker | BatchWorker] = set()
        # Every source of a path scan (restoration, Browse, and manual edits)
        # feeds this queue.  A zero-duration turn coalesces callbacks which Qt
        # may deliver in a platform-dependent order before creating a worker.
        self._pending_scans: dict[str, Path | None] = {}
        self._scan_dispatch_scheduled = False
        self.scan_generation = 0
        self.watermark_generation = 0
        self.preview_generation = 0
        self.batch_running = False
        self._build_ui()
        apply_theme(self)
        self._restore_settings()
        self.setWindowTitle("Social Image Processor")
        self.resize(1280, 800)
        # Restored paths must not start workers while the window is still being
        # constructed.  In particular, this avoids a native Qt shutdown seen on
        # Windows when the second launch restores a non-empty folder path.
        QTimer.singleShot(0, self._scan_restored_paths)

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("mainContent")
        outer = QVBoxLayout(central)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(10)

        identity = QVBoxLayout()
        identity.setSpacing(1)
        title = QLabel("SOCIAL IMAGE PROCESSOR")
        title.setObjectName("appTitle")
        subtitle = QLabel("Prepare once. Publish anywhere.")
        subtitle.setObjectName("appSubtitle")
        identity.addWidget(title)
        identity.addWidget(subtitle)
        outer.addLayout(identity)

        setup_card = QFrame()
        setup_card.setObjectName("card")
        setup_layout = QVBoxLayout(setup_card)
        setup_layout.setContentsMargins(14, 11, 14, 13)
        setup_layout.setSpacing(8)
        setup_title = QLabel("FOLDERS & OPTIONS")
        setup_title.setObjectName("sectionTitle")
        setup_layout.addWidget(setup_title)
        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(7)
        self.input_path, self.input_browse = self._path_row(
            "Select input folder", self.scan_input
        )
        self.output_path, self.output_browse = self._path_row("Select output folder")
        self.watermark_path, self.watermark_browse = self._path_row(
            "Select watermark folder", self.refresh_watermarks
        )
        form.addRow(
            self._field_label("Input folder"),
            self._row_widget(self.input_path, self.input_browse),
        )
        form.addRow(
            self._field_label("Output folder"),
            self._row_widget(self.output_path, self.output_browse),
        )
        form.addRow(
            self._field_label("Watermark folder"),
            self._row_widget(self.watermark_path, self.watermark_browse),
        )
        setup_layout.addLayout(form)

        options = QHBoxLayout()
        self.watermark_enabled = QCheckBox("Apply watermark")
        self.watermark_enabled.toggled.connect(self._watermark_toggled)
        self.quality = QSpinBox()
        self.quality.setRange(70, 100)
        self.quality.setSuffix(" %")
        self.quality.setFixedWidth(90)
        options.addWidget(self.watermark_enabled)
        options.addWidget(QLabel("JPEG quality"))
        options.addWidget(self.quality)
        options.addStretch()
        setup_layout.addLayout(options)
        outer.addWidget(setup_card)

        self.trello_panel = TrelloPanel(parent=self)
        self.trello_panel.start_worker.connect(self._start_worker)
        outer.addWidget(self.trello_panel)

        selections = QHBoxLayout()
        for text, column, value in (
            ("Select all X", ImageTableModel.X, True),
            ("Clear all X", ImageTableModel.X, False),
            ("Select all Instagram", ImageTableModel.INSTAGRAM, True),
            ("Clear all Instagram", ImageTableModel.INSTAGRAM, False),
        ):
            button = QPushButton(text)
            button.setProperty("role", "secondary")
            button.clicked.connect(
                lambda _=False, c=column, v=value: self.model.set_platform_all(c, v)
            )
            selections.addWidget(button)
        selections.addStretch()
        outer.addLayout(selections)

        self.model = ImageTableModel(self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(76)
        self.table.setColumnWidth(0, 110)
        self.table.setColumnWidth(1, 230)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.selectionModel().selectionChanged.connect(self._selection_changed)
        self.preview = PreviewPanel()
        split = QSplitter(Qt.Horizontal)
        split.addWidget(self.table)
        split.addWidget(self.preview)
        split.setSizes([850, 430])
        outer.addWidget(split, 3)

        bottom = QSplitter(Qt.Horizontal)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Processing messages will appear here.")
        stats_frame = QFrame()
        stats_frame.setObjectName("card")
        stats = QVBoxLayout(stats_frame)
        stats.setContentsMargins(12, 10, 12, 12)
        stats.setSpacing(7)
        stats_title = QLabel("BATCH METRICS")
        stats_title.setObjectName("sectionTitle")
        stats.addWidget(stats_title)
        self.stat_source, self.stat_output, self.stat_saved, self.stat_reduction = (
            QLabel("—") for _ in range(4)
        )
        metric_grid = QGridLayout()
        metric_grid.setSpacing(7)
        for index, (label, value) in enumerate(
            (
                ("SOURCE", self.stat_source),
                ("OUTPUT", self.stat_output),
                ("SAVED", self.stat_saved),
                ("REDUCTION", self.stat_reduction),
            )
        ):
            metric_grid.addWidget(self._metric(label, value), index // 2, index % 2)
        stats.addLayout(metric_grid)
        bottom.addWidget(self.log)
        bottom.addWidget(stats_frame)
        bottom.setSizes([900, 300])
        outer.addWidget(bottom, 1)

        footer = QFrame()
        footer.setObjectName("footer")
        processing = QHBoxLayout(footer)
        processing.setContentsMargins(12, 9, 10, 9)
        processing.setSpacing(12)
        self.progress_text = QLabel("Ready")
        self.progress_text.setObjectName("statusText")
        self.progress_text.setMinimumWidth(150)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.process_button = QPushButton("PROCESS IMAGES")
        self.process_button.setObjectName("processButton")
        self.process_button.setMinimumHeight(38)
        self.process_button.clicked.connect(self.start_processing)
        processing.addWidget(self.progress_text)
        processing.addWidget(self.progress, 1)
        processing.addWidget(self.process_button)
        outer.addWidget(footer)
        self.setCentralWidget(central)
        self.conflicting_controls = [
            self.input_path,
            self.input_browse,
            self.output_path,
            self.output_browse,
            self.watermark_path,
            self.watermark_browse,
            self.watermark_enabled,
            self.quality,
            self.table,
            self.process_button,
        ]

    @staticmethod
    def _row_widget(edit, button):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(edit, 1)
        layout.addWidget(button)
        return widget

    @staticmethod
    def _field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    @staticmethod
    def _metric(label_text: str, value: QLabel) -> QFrame:
        frame = QFrame()
        frame.setObjectName("metric")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 7, 10, 8)
        layout.setSpacing(1)
        label = QLabel(label_text)
        label.setObjectName("metricLabel")
        value.setObjectName("metricValue")
        layout.addWidget(label)
        layout.addWidget(value)
        return frame

    def _path_row(self, caption: str, changed=None):
        edit, button = QLineEdit(), QPushButton("Browse…")
        suppress_browse_editing_finished = False

        def field_changed():
            if not suppress_browse_editing_finished:
                changed()

        def user_edited():
            nonlocal suppress_browse_editing_finished
            suppress_browse_editing_finished = False

        def begin_browse():
            nonlocal suppress_browse_editing_finished
            # Arm this on pressed, before clicking the button can finish the
            # line edit.  Windows may otherwise deliver editingFinished either
            # before the native dialog opens or while its callback unwinds.
            suppress_browse_editing_finished = changed is not None

        def browse():
            begin_browse()
            path = QFileDialog.getExistingDirectory(self, caption, edit.text())
            if path:
                # Treat the dialog result as one atomic UI commit.  In
                # particular, do not let setText participate in a field signal
                # chain which can start a worker while the native dialog's
                # callback is still unwinding.
                blocker = QSignalBlocker(edit)
                edit.setText(path)
                del blocker
                self.save_settings()
                if changed:
                    QTimer.singleShot(0, changed)

        button.pressed.connect(begin_browse)
        button.clicked.connect(browse)
        if changed:
            edit.textEdited.connect(user_edited)
            edit.editingFinished.connect(field_changed)
        edit.editingFinished.connect(self.save_settings)
        return edit, button

    def _start_worker(self, worker: FunctionWorker | BatchWorker) -> None:
        """Start *worker* while retaining its runnable and signal bridge."""
        self._active_workers.add(worker)
        worker.signals.finished.connect(self._worker_finished)
        self.pool.start(worker)

    def _worker_finished(self, worker: FunctionWorker | BatchWorker) -> None:
        self._active_workers.discard(worker)

    def _restore_settings(self) -> None:
        controls = (
            self.input_path,
            self.output_path,
            self.watermark_path,
            self.quality,
            self.watermark_enabled,
        )
        blockers = [QSignalBlocker(control) for control in controls]
        try:
            for edit, path in (
                (self.input_path, self.settings.input_directory),
                (self.output_path, self.settings.output_directory),
                (self.watermark_path, self.settings.watermark_directory),
            ):
                edit.setText(str(path) if path else "")
            self.quality.setValue(self.settings.jpeg_quality)
            self.watermark_enabled.setChecked(self.settings.watermark_enabled)
        finally:
            del blockers
        self.quality.valueChanged.connect(self.save_settings)

    @staticmethod
    def _existing_directory(text: str) -> Path | None:
        """Return a restored/entered directory only when it is safe to scan."""
        if not text.strip():
            return None
        try:
            path = Path(text)
            return path if path.is_dir() else None
        except (OSError, ValueError):
            return None

    def _scan_restored_paths(self) -> None:
        """Start any initial scans after construction and ignore stale paths."""
        watermark = self._existing_directory(self.watermark_path.text())
        input_directory = self._existing_directory(self.input_path.text())
        if self.watermark_path.text() and watermark is None:
            self.log.append(
                "Saved watermark folder is unavailable; select a valid folder to scan."
            )
        if self.input_path.text() and input_directory is None:
            self.log.append(
                "Saved input folder is unavailable; select a valid folder to scan."
            )
        if watermark is not None:
            self.refresh_watermarks()
        elif input_directory is not None:
            self.scan_input()

    def _request_scan(self, kind: str) -> None:
        """Coalesce path scan requests made during the current Qt event turn."""
        edit = self.input_path if kind == "input" else self.watermark_path
        self._pending_scans[kind] = self._existing_directory(edit.text())
        if self._scan_dispatch_scheduled:
            return
        self._scan_dispatch_scheduled = True
        QTimer.singleShot(0, self._dispatch_pending_scans)

    def _dispatch_pending_scans(self) -> None:
        pending, self._pending_scans = self._pending_scans, {}
        self._scan_dispatch_scheduled = False
        # Watermarks affect input scan results, so preserve the restoration
        # ordering and let watermark completion request any necessary input scan.
        for kind in ("watermark", "input"):
            if kind not in pending:
                continue
            if kind == "watermark":
                self._start_watermark_scan(pending[kind])
            else:
                self._start_input_scan(pending[kind])

    def save_settings(self) -> None:
        def path(text):
            if not text.strip():
                return None
            try:
                return Path(text)
            except (OSError, ValueError):
                return None

        self.settings = ApplicationSettings(
            path(self.input_path.text()),
            path(self.output_path.text()),
            path(self.watermark_path.text()),
            self.quality.value(),
            self.watermark_enabled.isChecked(),
            self.settings.background_color,
        )
        try:
            self.settings_service.save(self.settings)
        except (OSError, ValueError) as error:
            self.statusBar().showMessage(f"Could not save settings: {error}", 5000)

    def refresh_watermarks(self) -> None:
        self.save_settings()
        self._request_scan("watermark")

    def _start_watermark_scan(self, path: Path | None) -> None:
        self.watermark_generation += 1
        generation = self.watermark_generation
        if path is None:
            self.catalog = WatermarkCatalog()
            return
        worker = FunctionWorker(scan_watermark_folder, path)
        worker.signals.result.connect(
            lambda result, g=generation: self._watermarks_ready(g, result)
        )
        worker.signals.error.connect(self._show_worker_error)
        self._start_worker(worker)

    def _watermarks_ready(self, generation: int, result) -> None:
        if generation != self.watermark_generation:
            return
        self.catalog = result.catalog
        if result.issues:
            self.log.append(
                "\n".join(
                    f"WATERMARK SCAN ERROR {i.path.name}: {i.message}"
                    for i in result.issues
                )
            )
        self.model.items = [
            replace(item, watermark_match=self.catalog.match(item.dimensions))
            for item in self.model.items
        ]
        if self.model.items:
            self.model.dataChanged.emit(
                self.model.index(0, ImageTableModel.WATERMARK),
                self.model.index(len(self.model.items) - 1, ImageTableModel.WATERMARK),
            )
        self._refresh_selected_preview()
        if self.input_path.text() and not self.model.items:
            self.scan_input()

    def scan_input(self) -> None:
        self.save_settings()
        self._request_scan("input")

    def _start_input_scan(self, path: Path | None) -> None:
        if path is None:
            self.scan_generation += 1
            self.model.replace_items((), self.scan_generation)
            self.preview.clear()
            return
        self.scan_generation += 1
        generation = self.scan_generation
        self.preview.clear()
        worker = FunctionWorker(scan_input_folder, path, self.catalog)
        worker.signals.result.connect(
            lambda result, g=generation: self._scan_ready(g, result)
        )
        worker.signals.error.connect(self._show_worker_error)
        self._start_worker(worker)

    def _scan_ready(self, generation: int, result) -> None:
        if generation != self.scan_generation:
            return
        self.model.replace_items(result.images, generation)
        for issue in result.issues:
            self.log.append(f"SOURCE SCAN ERROR {issue.path.name}: {issue.message}")
        for row, item in enumerate(result.images):
            worker = FunctionWorker(render_preview_bytes, item.path, (120, 70))
            worker.signals.result.connect(
                lambda data, r=row, g=generation: self._thumbnail_ready(g, r, data)
            )
            self._start_worker(worker)

    def _thumbnail_ready(self, generation: int, row: int, data: bytes) -> None:
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        self.model.set_thumbnail(row, generation, pixmap)

    def _selection_changed(
        self, selected: QItemSelection, _deselected: QItemSelection
    ) -> None:
        self._refresh_selected_preview()

    def _refresh_selected_preview(self) -> None:
        rows = (
            self.table.selectionModel().selectedRows()
            if self.table.selectionModel()
            else []
        )
        if not rows:
            self.preview.clear()
            return
        row = rows[0].row()
        if row >= len(self.model.items):
            return
        item = self.model.items[row]
        self.preview_generation += 1
        generation = self.preview_generation
        watermark = None
        status = "Watermark disabled"
        if self.watermark_enabled.isChecked():
            match = item.watermark_match
            if match and match.status is WatermarkStatus.EXACT:
                watermark, status = match.exact_path, "✓ Exact watermark preview"
            elif match and match.status is WatermarkStatus.AMBIGUOUS:
                status = "⚠ Ambiguous watermark — preview not composited"
            else:
                status = "⚠ Missing watermark — preview not composited"
        self.preview.show_loading(item.path.name, status)
        worker = FunctionWorker(render_preview_bytes, item.path, (900, 700), watermark)
        worker.signals.result.connect(
            lambda data, g=generation: self._preview_ready(g, data)
        )
        worker.signals.error.connect(
            lambda message, g=generation: self._preview_error(g, message)
        )
        self._start_worker(worker)

    def _preview_ready(self, generation: int, data: bytes) -> None:
        if generation != self.preview_generation:
            return
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        self.preview.show_pixmap(pixmap)

    def _preview_error(self, generation: int, message: str) -> None:
        if generation == self.preview_generation:
            self.preview.image.setText("Unable to render preview")
            self.preview.status.setText(message)

    def _watermark_toggled(self) -> None:
        self.save_settings()
        self._refresh_selected_preview()

    def start_processing(self) -> None:
        input_dir = self._existing_directory(self.input_path.text())
        output_dir = self._existing_directory(self.output_path.text())
        if input_dir is None or output_dir is None:
            self._validation_error("Choose valid input and output folders.")
            return
        if os.path.normcase(os.path.realpath(input_dir)) == os.path.normcase(
            os.path.realpath(output_dir)
        ):
            self._validation_error("Input and output folders must be different.")
            return
        selected = [
            item
            for item in self.model.items
            if item.export_to_x or item.export_to_instagram
        ]
        if not selected:
            self._validation_error("Select X and/or Instagram for at least one image.")
            return
        self.save_settings()
        self.log.clear()
        self._set_batch_running(True)
        self.progress.setRange(0, len(selected))
        self.progress.setValue(0)
        self.progress_text.setText(f"Processing image 0 / {len(selected)}")
        processor = BatchProcessor(
            selected,
            output_dir,
            watermark_enabled=self.watermark_enabled.isChecked(),
            watermark_catalog=self.catalog,
            jpeg_quality=self.quality.value(),
            background=self.settings.background_color,
        )
        worker = BatchWorker(processor)
        worker.signals.event.connect(self._batch_event)
        worker.signals.error.connect(self._show_worker_error)
        worker.signals.finished.connect(lambda _worker: self._set_batch_running(False))
        self._start_worker(worker)

    def _batch_event(self, event) -> None:
        if isinstance(event, ProgressUpdate):
            self.progress.setValue(event.completed)
            self.progress_text.setText(
                f"Processing image {event.completed} / {event.total}"
            )
        elif isinstance(event, SuccessfulOutput):
            source_size = next(
                (
                    i.size_bytes
                    for i in self.model.items
                    if i.path == event.result.source_path
                ),
                0,
            )
            self.log.append(
                f"{event.result.source_path.name}\n→ {event.result.output_path.name}\n{format_bytes(source_size)} → {format_bytes(event.result.output_size_bytes)}\n"
            )
        elif isinstance(event, SkippedSource):
            self.log.append(f"SKIPPED {event.source_path.name}\n{event.message}\n")
        elif isinstance(event, FailedSource):
            self.log.append(f"ERROR {event.source_path.name}\n{event.message}\n")
        elif isinstance(event, FailedExport):
            self.log.append(
                f"ERROR {event.result.source_path.name} ({event.result.platform.value})\n{event.result.message}\n"
            )
        elif isinstance(event, BatchStatistics):
            self.stat_source.setText(format_bytes(event.processed_source_size_bytes))
            self.stat_output.setText(format_bytes(event.output_size_bytes))
            self.stat_saved.setText(format_bytes(event.bytes_saved))
            self.stat_reduction.setText(f"{event.reduction_percentage:.1f} %")

    def _set_batch_running(self, running: bool) -> None:
        self.batch_running = running
        for control in self.conflicting_controls:
            control.setEnabled(not running)
        if not running:
            self.progress_text.setText("Complete")

    def _validation_error(self, message: str) -> None:
        QMessageBox.warning(self, "Cannot process images", message)

    def _show_worker_error(self, message: str) -> None:
        self.log.append(f"ERROR\n{message}\n")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.batch_running or self._active_workers:
            event.ignore()
            QMessageBox.warning(
                self,
                "Background work in progress",
                "Wait for scanning, previews, or processing to finish before closing.",
            )
            return
        self.save_settings()
        event.accept()

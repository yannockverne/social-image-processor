"""Main desktop window and GUI-thread orchestration."""

from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path

from PySide6.QtCore import QItemSelection, QSignalBlocker, QThreadPool, QTimer, Qt
from PySide6.QtGui import QCloseEvent, QDesktopServices, QPixmap
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QDoubleSpinBox,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.watermarking import DEFAULT_WATERMARK_SIZE_RATIO, WatermarkCatalog
from app.models.results import (
    BatchStatistics,
    ExportStatus,
    FailedExport,
    FailedSource,
    ProgressUpdate,
    R2UploadFinished,
    R2UploadStarted,
    SkippedSource,
    SuccessfulOutput,
)
from app.models.settings import ApplicationSettings
from app.models.watermark import WatermarkStatus
from app.services.batch_processor import BatchProcessor
from app.services.folder_scanner import scan_input_folder, scan_watermark_folder
from app.services.settings_service import SettingsService
from app.services.r2_upload_service import R2UploadService
from app.ui.image_table import ImageTableModel, PlatformCheckDelegate
from app.ui.integration_dialogs import R2SettingsDialog, TrelloConfigurationDialog
from app.ui.loading_overlay import LoadingOverlay
from app.ui.preview_panel import PreviewPanel
from app.ui.theme import apply_theme
from app.ui.trello_panel import TrelloPanel
from app.ui.workers import BatchWorker, FunctionWorker, render_preview_bytes
from app.utils.formatting import format_bytes


class MainWindow(QMainWindow):
    """Functional V1 interface around the existing synchronous services."""

    TABLE_MINIMUM_WIDTH = 560
    RESULTS_MAXIMUM_HEIGHT = 110

    def __init__(self, settings_service: SettingsService | None = None) -> None:
        super().__init__()
        self.settings_service = settings_service or SettingsService()
        self.settings = self.settings_service.load()
        self.catalog = WatermarkCatalog()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(3)
        application = QApplication.instance()
        if application is not None:
            # aboutToQuit can bypass closeEvent (for example, an external quit
            # request).  Keep Qt alive until runnable signal bridges finish.
            application.aboutToQuit.connect(self.pool.waitForDone)
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
        self._thumbnail_total = 0
        self._thumbnail_completed = 0
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
        self._build_menu()
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

        # Construct the existing controls once, then organize them by workflow.
        self.input_path, self.input_browse = self._path_row(
            "Select input folder", self.scan_input
        )
        self.output_path, self.output_browse = self._path_row("Select output folder")
        self.watermark_path, self.watermark_browse = self._path_row(
            "Select watermark folder", self.refresh_watermarks
        )
        self.watermark_enabled = QCheckBox("Apply watermark")
        self.watermark_enabled.toggled.connect(self._watermark_toggled)
        self.watermark_selector = QComboBox()
        self.watermark_selector.setMinimumWidth(150)
        self.watermark_selector.currentIndexChanged.connect(self._watermark_selected)
        self.watermark_size = QDoubleSpinBox()
        self.watermark_size.setObjectName("watermarkSize")
        self.watermark_size.setRange(3.0, 15.0)
        self.watermark_size.setSingleStep(0.5)
        self.watermark_size.setDecimals(1)
        self.watermark_size.setSuffix(" %")
        self.watermark_size.setFixedWidth(90)
        self.watermark_size.setValue(DEFAULT_WATERMARK_SIZE_RATIO * 100)
        self.watermark_size.setToolTip(
            "Watermark width as a percentage of the image's geometric mean. "
            "This value resets to 8% on every launch."
        )
        self.watermark_size.valueChanged.connect(self._refresh_selected_preview)
        self.quality = QSpinBox()
        self.quality.setRange(70, 100)
        self.quality.setSuffix(" %")
        self.quality.setFixedWidth(90)

        self.r2_upload_enabled = QCheckBox("Upload exports to R2")
        self.trello_update_enabled = QCheckBox("Update Trello card")
        self.r2_worker_url = QLineEdit()
        self.r2_worker_url.setPlaceholderText("https://worker.example.com/upload")
        self.r2_worker_url.setClearButtonEnabled(True)
        self.trello_panel = TrelloPanel(parent=self)
        self.trello_panel.start_worker.connect(self._start_worker)
        self.trello_dialog = TrelloConfigurationDialog(self.trello_panel, self)
        self.r2_dialog = R2SettingsDialog(
            self.r2_worker_url, self.settings.r2_remote_prefix, self
        )
        self.trello_status = QLabel("Trello: Disconnected")
        self.r2_status = QLabel("R2: Not configured")
        for label in (self.trello_status, self.r2_status):
            label.setObjectName("integrationStatus")
        self.trello_card_button = QPushButton("No card selected — Select card")
        self.trello_card_button.setObjectName("trelloCardSelector")
        self.trello_card_button.clicked.connect(self.trello_dialog.open)
        self.trello_new_card_button = QPushButton("New card…")
        self.trello_new_card_button.setProperty("role", "secondary")
        self.trello_new_card_button.clicked.connect(self.trello_panel.create_new_card)

        self.ready_loaded = QLabel("0 images loaded")
        self.ready_x = QLabel("0 selected for X")
        self.ready_instagram = QLabel("0 selected for Instagram")
        for label in (self.ready_loaded, self.ready_x, self.ready_instagram):
            label.setObjectName("readySummary")
        self.process_button = QPushButton("PROCESS IMAGES")
        self.process_button.setObjectName("processButton")
        self.process_button.setMinimumHeight(38)
        self.process_button.clicked.connect(self.start_processing)

        dashboard = QGridLayout()
        dashboard.setContentsMargins(0, 0, 0, 0)
        dashboard.setHorizontalSpacing(10)
        dashboard.setVerticalSpacing(10)
        dashboard.addWidget(self._build_source_section(), 0, 0)
        dashboard.addWidget(self._build_image_processing_section(), 0, 1)
        dashboard.addWidget(self._build_publishing_section(), 1, 0)
        dashboard.addWidget(self._build_ready_section(), 1, 1)
        dashboard.setColumnStretch(0, 1)
        dashboard.setColumnStretch(1, 1)
        dashboard.setRowStretch(0, 1)
        dashboard.setRowStretch(1, 1)
        outer.addLayout(dashboard)

        self.table_area = QWidget()
        table_layout = QVBoxLayout(self.table_area)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(8)
        selections = QHBoxLayout()
        for platform, column in (
            ("X", ImageTableModel.X),
            ("Instagram", ImageTableModel.INSTAGRAM),
        ):
            selections.addWidget(self._field_label(platform))
            for text, value in (("Select all", True), ("Clear", False)):
                button = QPushButton(text)
                button.setObjectName(
                    f"{'selectAll' if value else 'clearAll'}{platform}Button"
                )
                button.setProperty("role", "secondary")
                button.clicked.connect(
                    lambda _=False, c=column, v=value: self.model.set_platform_all(c, v)
                )
                selections.addWidget(button)
            selections.addSpacing(8)
        selections.addStretch()
        self.move_up_button = QPushButton("Move Up")
        self.move_down_button = QPushButton("Move Down")
        for button in (self.move_up_button, self.move_down_button):
            button.setProperty("role", "secondary")
            selections.addWidget(button)
        table_layout.addLayout(selections)

        self.model = ImageTableModel(self)
        self.model.dataChanged.connect(self._update_ready_summary)
        self.model.modelReset.connect(self._update_ready_summary)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.platform_check_delegate = PlatformCheckDelegate(self.table)
        self.table.setItemDelegateForColumn(
            ImageTableModel.X, self.platform_check_delegate
        )
        self.table.setItemDelegateForColumn(
            ImageTableModel.INSTAGRAM, self.platform_check_delegate
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setDragDropMode(QAbstractItemView.InternalMove)
        self.table.setDefaultDropAction(Qt.MoveAction)
        self.table.setDragDropOverwriteMode(False)
        self.table.setDropIndicatorShown(True)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(76)
        header = self.table.horizontalHeader()
        for column in range(self.model.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.Interactive)
        # Metadata columns start compact while the filename takes whatever
        # space remains. Keep the pane minimum low enough that it cannot crowd
        # the preview out of an even split at normal desktop widths.
        header.setSectionResizeMode(ImageTableModel.FILENAME, QHeaderView.Stretch)
        self.table.setColumnWidth(ImageTableModel.ORDER, 48)
        self.table.setColumnWidth(ImageTableModel.THUMBNAIL, 82)
        self.table.setColumnWidth(ImageTableModel.DIMENSIONS, 90)
        self.table.setColumnWidth(ImageTableModel.SIZE, 64)
        self.table.setColumnWidth(ImageTableModel.X, 38)
        self.table.setColumnWidth(ImageTableModel.INSTAGRAM, 78)
        self.table.setColumnWidth(ImageTableModel.WATERMARK, 92)
        header.setStretchLastSection(False)
        self.table.selectionModel().selectionChanged.connect(self._selection_changed)
        self.move_up_button.clicked.connect(lambda: self._move_selected_row(-1))
        self.move_down_button.clicked.connect(lambda: self._move_selected_row(1))
        table_layout.addWidget(self.table)
        self.table_area.setMinimumWidth(self.TABLE_MINIMUM_WIDTH)
        self.loading_overlay = LoadingOverlay(self.table_area)
        self.preview = PreviewPanel()
        self.image_splitter = QSplitter(Qt.Horizontal)
        self.image_splitter.addWidget(self.table_area)
        self.image_splitter.addWidget(self.preview)
        self.image_splitter.setChildrenCollapsible(False)
        self.image_splitter.setStretchFactor(0, 1)
        self.image_splitter.setStretchFactor(1, 1)
        # Give the panes an explicit initial ratio. The handle remains movable,
        # so users can still temporarily favor either pane at narrower widths.
        self.image_splitter.setSizes([640, 640])
        self.image_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        outer.addWidget(self.image_splitter, 1)

        # Keep vertical sizing separate from the splitter: on some native Qt
        # platforms QSplitter drops its maximum height when it is shown.  The
        # structural parent owns the row height while the splitter only divides
        # the available width between Activity and Batch Metrics.
        self.results_container = QFrame()
        self.results_container.setMaximumHeight(self.RESULTS_MAXIMUM_HEIGHT)
        self.results_container.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Preferred
        )
        results_layout = QVBoxLayout(self.results_container)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(0)

        self.results_splitter = QSplitter(Qt.Horizontal)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.log.setPlaceholderText("Processing and Trello activity will appear here.")
        self.trello_panel.activity.connect(self.log.append)
        stats_frame = QFrame()
        stats_frame.setObjectName("card")
        stats = QVBoxLayout(stats_frame)
        stats.setContentsMargins(8, 2, 8, 2)
        stats.setSpacing(1)
        stats_title = QLabel("BATCH METRICS")
        stats_title.setObjectName("sectionTitle")
        stats.addWidget(stats_title)
        self.stat_source, self.stat_output, self.stat_saved, self.stat_reduction = (
            QLabel("—") for _ in range(4)
        )
        metric_grid = QGridLayout()
        metric_grid.setContentsMargins(0, 0, 0, 0)
        metric_grid.setHorizontalSpacing(3)
        metric_grid.setVerticalSpacing(1)
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
        self.results_splitter.addWidget(self.log)
        self.results_splitter.addWidget(stats_frame)
        self.results_splitter.setStretchFactor(0, 3)
        self.results_splitter.setStretchFactor(1, 1)
        # This row is a compact summary, not another vertical work surface.
        # Its children advertise useful horizontal expansion while the parent
        # layout gives all surplus height to the table and preview above.
        self.results_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        results_layout.addWidget(self.results_splitter)
        outer.addWidget(self.results_container, 0)

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
        processing.addWidget(self.progress_text)
        processing.addWidget(self.progress, 1)
        outer.addWidget(footer)
        self.setCentralWidget(central)

        self.trello_panel.state_changed.connect(self._update_integration_status)
        self.r2_worker_url.textChanged.connect(self._update_integration_status)
        self.conflicting_controls = [
            self.input_path, self.input_browse, self.output_path, self.output_browse,
            self.watermark_path, self.watermark_browse, self.watermark_enabled,
            self.watermark_selector, self.watermark_size, self.quality,
            self.r2_upload_enabled, self.r2_worker_url, self.trello_update_enabled,
            self.trello_card_button, self.trello_new_card_button,
            self.table, self.move_up_button,
            self.move_down_button, self.process_button,
        ]
        self._connect_menu_actions()

    @staticmethod
    def _section(title: str, object_name: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName(object_name)
        frame.setProperty("role", "workflowCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(6)
        heading = QLabel(title)
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)
        return frame, layout

    def _build_source_section(self) -> QFrame:
        frame, layout = self._section("SOURCE", "sourceSection")
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(6)
        form.addRow(
            self._field_label("Input folder"),
            self._row_widget(self.input_path, self.input_browse),
        )
        form.addRow(
            self._field_label("Output folder"),
            self._row_widget(self.output_path, self.output_browse),
        )
        layout.addLayout(form)
        return frame

    def _build_image_processing_section(self) -> QFrame:
        frame, layout = self._section("IMAGE PROCESSING", "imageProcessingSection")
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(6)
        form.addRow(
            self._field_label("Watermark folder"),
            self._row_widget(self.watermark_path, self.watermark_browse),
        )
        layout.addLayout(form)
        layout.addWidget(self.watermark_enabled)
        controls = QGridLayout()
        controls.setHorizontalSpacing(8)
        for column, text in enumerate(("Design", "Size", "JPEG quality")):
            controls.addWidget(self._field_label(text), 0, column)
        controls.addWidget(self.watermark_selector, 1, 0)
        controls.addWidget(self.watermark_size, 1, 1)
        controls.addWidget(self.quality, 1, 2)
        controls.setColumnStretch(0, 1)
        layout.addLayout(controls)
        return frame

    def _build_publishing_section(self) -> QFrame:
        frame, layout = self._section("PUBLISHING", "publishingSection")
        status = QGridLayout()
        status.addWidget(self.r2_upload_enabled, 0, 0)
        status.addWidget(self.r2_status, 0, 1)
        status.addWidget(self.trello_update_enabled, 1, 0)
        status.addWidget(self.trello_status, 1, 1)
        status.setColumnStretch(0, 1)
        status.setColumnStretch(1, 1)
        layout.addLayout(status)
        layout.addWidget(self._field_label("Trello card"))
        card_row = QHBoxLayout()
        card_row.addWidget(self.trello_card_button, 1)
        card_row.addWidget(self.trello_new_card_button)
        layout.addLayout(card_row)
        return frame

    def _build_ready_section(self) -> QFrame:
        frame, layout = self._section("READY TO PROCESS", "readySection")
        summary = QGridLayout()
        summary.addWidget(self.ready_loaded, 0, 0)
        summary.addWidget(self.ready_x, 0, 1)
        summary.addWidget(self.ready_instagram, 1, 0, 1, 2)
        layout.addLayout(summary)
        layout.addStretch()
        layout.addWidget(self.process_button)
        return frame

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        self.open_output_action = file_menu.addAction("Open Output Folder")
        self.open_output_action.triggered.connect(self.open_output_folder)
        file_menu.addSeparator()
        self.quit_action = file_menu.addAction("Quit")
        self.quit_action.triggered.connect(self.close)

        trello_menu = self.menuBar().addMenu("&Trello")
        self.trello_settings_action = trello_menu.addAction("Configuration…")
        self.trello_connect_action = trello_menu.addAction("Connect / Reconnect")
        self.trello_disconnect_action = trello_menu.addAction("Disconnect")

        r2_menu = self.menuBar().addMenu("&R2 Upload")
        self.r2_settings_action = r2_menu.addAction("Settings…")

        help_menu = self.menuBar().addMenu("&Help")
        self.about_action = help_menu.addAction("About")

    def _connect_menu_actions(self) -> None:
        self.trello_settings_action.triggered.connect(self.trello_dialog.open)
        self.trello_connect_action.triggered.connect(self.trello_panel.connect_trello)
        self.trello_disconnect_action.triggered.connect(
            self.trello_panel.disconnect_trello
        )
        self.r2_settings_action.triggered.connect(self.r2_dialog.open)
        self.about_action.triggered.connect(self.show_about)

    def open_output_folder(self) -> None:
        path = self._existing_directory(self.output_path.text())
        if path is None:
            self._validation_error("Choose a valid output folder first.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            "About Social Image Processor",
            "<b>Social Image Processor</b><br>Prepare social-ready image batches for publishing.",
        )

    def _update_integration_status(self) -> None:
        connected = self.trello_panel.service is not None
        self.trello_status.setText(
            f"Trello: {'Connected' if connected else 'Disconnected'}"
        )
        card = self.trello_panel.card.currentText().strip()
        self.trello_card_button.setText(
            card
            if self.trello_panel.card.currentData()
            else "No card selected — Select card"
        )
        self._update_trello_card_button()
        configured = not bool(R2UploadService(self.r2_worker_url.text()).validation_error)
        self.r2_status.setText(f"R2: {'Ready' if configured else 'Not configured'}")

    def _update_trello_card_button(self) -> None:
        """Synchronize selector interaction without duplicating Trello state."""
        self.trello_card_button.setEnabled(
            self.trello_update_enabled.isChecked()
            and self.r2_upload_enabled.isChecked()
            and not self.batch_running
        )

    def _update_ready_summary(self, *_args) -> None:
        """Derive workflow counts directly from the authoritative image model."""
        items = self.model.items
        self.ready_loaded.setText(f"{len(items)} images loaded")
        self.ready_x.setText(
            f"{sum(item.export_to_x for item in items)} selected for X"
        )
        self.ready_instagram.setText(
            f"{sum(item.export_to_instagram for item in items)} selected for Instagram"
        )

    def _move_selected_row(self, offset: int) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        new_row = self.model.move_row(rows[0].row(), offset)
        self.table.selectRow(new_row)
        self._refresh_selected_preview()

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
        frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(6, 0, 6, 1)
        layout.setSpacing(0)
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
            self.r2_upload_enabled,
            self.r2_worker_url,
            self.trello_update_enabled,
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
            self.r2_upload_enabled.setChecked(self.settings.r2_upload_enabled)
            self.r2_worker_url.setText(self.settings.r2_worker_url)
            self.trello_update_enabled.setChecked(
                self.settings.trello_update_enabled and self.settings.r2_upload_enabled
            )
            self.watermark_selector.addItem("No watermark selected", None)
        finally:
            del blockers
        self.quality.valueChanged.connect(self.save_settings)
        self.r2_upload_enabled.toggled.connect(self._r2_toggled)
        self.trello_update_enabled.toggled.connect(self._trello_toggled)
        self.r2_worker_url.editingFinished.connect(self.save_settings)
        self._r2_toggled(self.r2_upload_enabled.isChecked())
        self._update_integration_status()

    def _r2_toggled(self, enabled: bool) -> None:
        if not enabled:
            self.trello_update_enabled.setChecked(False)
        self.trello_update_enabled.setEnabled(enabled and not self.batch_running)
        self.r2_worker_url.setEnabled(enabled and not self.batch_running)
        self._update_trello_card_button()
        self.save_settings()

    def _trello_toggled(self, _enabled: bool) -> None:
        self._update_trello_card_button()
        self.save_settings()

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
            self.watermark_selector.currentData(),
            self.r2_upload_enabled.isChecked(),
            self.r2_worker_url.text().strip(),
            self.settings.r2_remote_prefix,
            self.trello_update_enabled.isChecked()
            and self.r2_upload_enabled.isChecked(),
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
        selected = self.settings.selected_watermark
        blocker = QSignalBlocker(self.watermark_selector)
        self.watermark_selector.clear()
        self.watermark_selector.addItem("Select watermark…", None)
        for asset in self.catalog.paths:
            self.watermark_selector.addItem(asset.stem, asset.name)
        selected_index = self.watermark_selector.findData(selected)
        if selected and selected_index < 0:
            self.watermark_selector.insertItem(
                1, f"Unavailable: {Path(selected).stem}", selected
            )
            selected_index = 1
        self.watermark_selector.setCurrentIndex(max(0, selected_index))
        del blocker
        if result.issues:
            self.log.append(
                "\n".join(
                    f"WATERMARK SCAN ERROR {i.path.name}: {i.message}"
                    for i in result.issues
                )
            )
        self.model.items = [
            replace(
                item,
                watermark_match=self.catalog.match(
                    item.dimensions, self.watermark_selector.currentData()
                ),
            )
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
            self.loading_overlay.finish()
            return
        self.scan_generation += 1
        generation = self.scan_generation
        self.preview.clear()
        self._thumbnail_total = 0
        self._thumbnail_completed = 0
        self.loading_overlay.show_work("Scanning images…")
        worker = FunctionWorker(
            scan_input_folder, path, self.catalog, self.watermark_selector.currentData()
        )
        worker.signals.result.connect(
            lambda result, g=generation: self._scan_ready(g, result)
        )
        worker.signals.error.connect(
            lambda message, g=generation: self._scan_error(g, message)
        )
        self._start_worker(worker)

    def _scan_ready(self, generation: int, result) -> None:
        if generation != self.scan_generation:
            return
        self.model.replace_items(result.images, generation)
        for issue in result.issues:
            self.log.append(f"SOURCE SCAN ERROR {issue.path.name}: {issue.message}")
        self._thumbnail_total = len(result.images)
        self._thumbnail_completed = 0
        if not result.images:
            self.loading_overlay.finish()
            self.progress_text.setText("Ready — no images found")
            return
        self.loading_overlay.show_work(
            f"Generating thumbnails… 0 / {self._thumbnail_total}"
        )
        for row, item in enumerate(result.images):
            worker = FunctionWorker(render_preview_bytes, item.path, (120, 70))
            worker.signals.result.connect(
                lambda data, r=row, g=generation, p=item.path: self._thumbnail_ready(
                    g, r, p, data
                )
            )
            worker.signals.error.connect(self._show_worker_error)
            worker.signals.finished.connect(
                lambda _worker, g=generation: self._thumbnail_finished(g)
            )
            self._start_worker(worker)

    def _scan_error(self, generation: int, message: str) -> None:
        self._show_worker_error(message)
        if generation == self.scan_generation:
            self.loading_overlay.finish()
            self.progress_text.setText("Image scan failed")

    def _thumbnail_finished(self, generation: int) -> None:
        if generation != self.scan_generation:
            return
        self._thumbnail_completed += 1
        if self._thumbnail_completed >= self._thumbnail_total:
            self.loading_overlay.finish()
            self.progress_text.setText(f"Ready — {self._thumbnail_total} images")
        else:
            self.loading_overlay.show_work(
                "Generating thumbnails… "
                f"{self._thumbnail_completed} / {self._thumbnail_total}"
            )

    def _thumbnail_ready(
        self, generation: int, row: int, source_path: Path, data: bytes
    ) -> None:
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        self.model.set_thumbnail(row, generation, pixmap, source_path)

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
            match = self.catalog.match(
                item.dimensions, self.watermark_selector.currentData()
            )
            if match and match.status is WatermarkStatus.EXACT:
                watermark, status = match.exact_path, "✓ Dynamic watermark preview"
            else:
                status = "⚠ Missing watermark — preview not composited"
        self.preview.show_loading(item.path.name, status)
        worker = FunctionWorker(
            render_preview_bytes,
            item.path,
            (900, 700),
            watermark,
            self.watermark_size.value() / 100,
        )
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

    def _watermark_selected(self) -> None:
        """Persist the global design and refresh row/preview availability."""
        selected = self.watermark_selector.currentData()
        self.model.items = [
            replace(item, watermark_match=self.catalog.match(item.dimensions, selected))
            for item in self.model.items
        ]
        if self.model.items:
            self.model.dataChanged.emit(
                self.model.index(0, ImageTableModel.WATERMARK),
                self.model.index(len(self.model.items) - 1, ImageTableModel.WATERMARK),
            )
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
        if (
            self.watermark_enabled.isChecked()
            and self.catalog.find(self.watermark_selector.currentData()) is None
        ):
            self._validation_error(
                "Watermarking is enabled. Select an available PNG watermark design."
            )
            return
        trello_update_enabled = self.trello_update_enabled.isChecked()
        trello_service = None
        trello_card_id = None
        if trello_update_enabled:
            if not self.r2_upload_enabled.isChecked():
                self._validation_error("Enable R2 upload before updating Trello.")
                return
            if self.trello_panel.service is None:
                self._validation_error("Connect to Trello before processing.")
                return
            trello_card_id = self.trello_panel.card.currentData()
            if not trello_card_id:
                self._validation_error("Select a Trello card before processing.")
                return
            trello_service = self.trello_panel.service
        r2_service = None
        if self.r2_upload_enabled.isChecked():
            r2_service = R2UploadService(
                self.r2_worker_url.text(),
                remote_prefix=(
                    trello_card_id
                    if trello_update_enabled
                    else self.settings.r2_remote_prefix
                ),
            )
            if r2_service.validation_error:
                self._validation_error(r2_service.validation_error)
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
            selected_watermark=self.watermark_selector.currentData(),
            watermark_size_ratio=self.watermark_size.value() / 100,
            jpeg_quality=self.quality.value(),
            background=self.settings.background_color,
            r2_upload_service=r2_service,
            trello_service=trello_service,
            trello_card_id=trello_card_id,
        )
        worker = BatchWorker(processor)
        worker.signals.event.connect(self._batch_event)
        worker.signals.result.connect(self._batch_complete)
        worker.signals.error.connect(self._show_worker_error)
        worker.signals.finished.connect(lambda _worker: self._set_batch_running(False))
        self._start_worker(worker)

    def _batch_complete(self, result) -> None:
        """Report the final local, R2, and Trello outcomes once per batch."""
        successful = sum(e.status is ExportStatus.SUCCEEDED for e in result.exports)
        self.log.append(f"[DONE] Local exports: {successful}/{len(result.exports)}")
        if self.r2_upload_enabled.isChecked():
            uploaded = sum(upload.success for upload in result.uploads)
            self.log.append(f"[R2] Uploads: {uploaded}/{len(result.uploads)}")
        else:
            self.log.append("[R2] Disabled")
        if not self.trello_update_enabled.isChecked():
            self.log.append("[TRELLO] Disabled")
        elif result.trello_error:
            self.log.append(f"[TRELLO] URL MAKE update failed: {result.trello_error}")
        elif result.trello_urls_updated:
            self.log.append(
                f"[TRELLO] URL MAKE updated with {result.trello_urls_updated} URLs"
            )
        else:
            self.log.append("[TRELLO] No usable R2 URLs; URL MAKE unchanged")

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
                f"[EXPORT] {event.result.output_path.name}\n{event.result.source_path.name}\n{format_bytes(source_size)} → {format_bytes(event.result.output_size_bytes)}\n"
            )
        elif isinstance(event, R2UploadStarted):
            self.log.append(f"[R2] Uploading {event.local_path.name}...")
        elif isinstance(event, R2UploadFinished):
            if event.result.success:
                self.log.append(f"[R2] Uploaded {event.result.local_path.name}\n")
            else:
                self.log.append(
                    f"[R2] Upload failed for {event.result.local_path.name}: "
                    f"{event.result.error_message}\n"
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
            self._r2_toggled(self.r2_upload_enabled.isChecked())

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

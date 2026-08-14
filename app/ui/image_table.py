"""Table model for source metadata and platform selections."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import (
    QAbstractTableModel,
    QByteArray,
    QEvent,
    QMimeData,
    QModelIndex,
    QPoint,
    QRect,
    QSize,
    Qt,
)
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolTip,
)

from app.models.image_item import ImageItem, is_instagram_ratio_supported
from app.models.watermark import WatermarkStatus
from app.utils.formatting import format_bytes


class ImageTableModel(QAbstractTableModel):
    """A lightweight metadata model which never retains source rasters."""

    ORDER, THUMBNAIL, FILENAME, DIMENSIONS, SIZE, X, INSTAGRAM, WATERMARK = range(8)
    HEADERS = (
        "Order",
        "Preview",
        "Filename",
        "Dimensions",
        "Size",
        "X",
        "Instagram",
        "Watermark",
    )
    ROW_MIME_TYPE = "application/x-social-image-processor-row"
    InstagramRatioWarningRole = Qt.UserRole + 1

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.items: list[ImageItem] = []
        self._thumbnails: dict[int, QPixmap] = {}
        self.generation = 0

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.items)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        item, column = self.items[index.row()], index.column()
        if role == Qt.DecorationRole and column == self.THUMBNAIL:
            return self._thumbnails.get(index.row())
        if role == Qt.DisplayRole:
            if column == self.ORDER:
                return index.row() + 1
            if column == self.FILENAME:
                return item.path.name
            if column == self.DIMENSIONS:
                return f"{item.width}x{item.height}"
            if column == self.SIZE:
                return format_bytes(item.size_bytes)
            if column == self.WATERMARK:
                status = item.watermark_match.status if item.watermark_match else None
                return {
                    WatermarkStatus.EXACT: "✓ Exact",
                    WatermarkStatus.MISSING: "⚠ Missing",
                    WatermarkStatus.AMBIGUOUS: "⚠ Ambiguous",
                }.get(status, "—")
        if role == Qt.CheckStateRole:
            if column == self.X:
                return Qt.Checked if item.export_to_x else Qt.Unchecked
            if column == self.INSTAGRAM:
                return Qt.Checked if item.export_to_instagram else Qt.Unchecked
        if role == self.InstagramRatioWarningRole and column == self.INSTAGRAM:
            return not is_instagram_ratio_supported(item.width, item.height)
        if role == Qt.ForegroundRole and column == self.WATERMARK:
            status = item.watermark_match.status if item.watermark_match else None
            return QColor("#67d391" if status is WatermarkStatus.EXACT else "#ffb454")
        if role == Qt.TextAlignmentRole and column in (
            self.DIMENSIONS,
            self.SIZE,
            self.ORDER,
            self.X,
            self.INSTAGRAM,
            self.WATERMARK,
        ):
            return Qt.AlignCenter
        return None

    def flags(self, index):
        flags = super().flags(index)
        if index.isValid():
            flags |= Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled
        else:
            flags |= Qt.ItemIsDropEnabled
        if index.isValid() and index.column() in (self.X, self.INSTAGRAM):
            flags |= Qt.ItemIsUserCheckable | Qt.ItemIsEditable
        return flags

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.CheckStateRole or index.column() not in (self.X, self.INSTAGRAM):
            return False
        item = self.items[index.row()]
        # QStyledItemDelegate supplies the check state as a Python int on some
        # PySide6/platform combinations, while direct callers commonly supply
        # a Qt.CheckState enum.  Python's Enum comparison does not consider the
        # integer 2 equal to CheckState.Checked, so normalize either form first.
        check_state = getattr(value, "value", value)
        checked = check_state == Qt.CheckState.Checked.value
        self.items[index.row()] = replace(
            item,
            **(
                {"export_to_x": checked}
                if index.column() == self.X
                else {"export_to_instagram": checked}
            ),
        )
        self.dataChanged.emit(index, index, [Qt.CheckStateRole])
        return True

    def replace_items(self, items, generation: int) -> None:
        self.beginResetModel()
        self.items = list(items)
        self._thumbnails.clear()
        self.generation = generation
        self.endResetModel()

    def supportedDropActions(self):
        return Qt.MoveAction

    def mimeTypes(self):
        return [self.ROW_MIME_TYPE]

    def mimeData(self, indexes):
        mime_data = QMimeData()
        rows = {index.row() for index in indexes if index.isValid()}
        if len(rows) == 1:
            mime_data.setData(self.ROW_MIME_TYPE, QByteArray(str(rows.pop()).encode()))
        return mime_data

    def dropMimeData(self, data, action, row, column, parent):
        if action == Qt.IgnoreAction:
            return True
        if action != Qt.MoveAction or not data.hasFormat(self.ROW_MIME_TYPE):
            return False
        try:
            source_row = int(bytes(data.data(self.ROW_MIME_TYPE)))
        except ValueError:
            return False
        destination_row = row if row >= 0 else parent.row()
        if destination_row < 0:
            destination_row = len(self.items)
        return self.moveRows(
            QModelIndex(), source_row, 1, QModelIndex(), destination_row
        )

    def moveRows(
        self, source_parent, source_row, count, destination_parent, destination_child
    ):
        """Move complete image records; the list order is the batch source of truth."""
        if (
            source_parent.isValid()
            or destination_parent.isValid()
            or count != 1
            or not 0 <= source_row < len(self.items)
            or not 0 <= destination_child <= len(self.items)
            or destination_child in (source_row, source_row + 1)
        ):
            return False
        self.beginMoveRows(
            source_parent, source_row, source_row, destination_parent, destination_child
        )
        old_items = self.items.copy()
        item = self.items.pop(source_row)
        if destination_child > source_row:
            destination_child -= 1
        self.items.insert(destination_child, item)
        # Thumbnails are keyed by their immutable image item, so rebuild the row
        # mapping to keep the raster attached during both button and drag moves.
        old_thumbnails = self._thumbnails
        self._thumbnails = {}
        for old_row, pixmap in old_thumbnails.items():
            mapped_item = old_items[old_row]
            self._thumbnails[self.items.index(mapped_item)] = pixmap
        self.endMoveRows()
        self.dataChanged.emit(
            self.index(0, self.ORDER),
            self.index(len(self.items) - 1, self.ORDER),
            [Qt.DisplayRole],
        )
        return True

    def move_row(self, row: int, offset: int) -> int:
        """Move one row by one step and return its resulting row."""
        target = row + offset
        if not 0 <= target < len(self.items):
            return row
        destination = target if offset < 0 else target + 1
        return (
            target
            if self.moveRows(QModelIndex(), row, 1, QModelIndex(), destination)
            else row
        )

    def set_platform_all(self, column: int, selected: bool) -> None:
        key = "export_to_x" if column == self.X else "export_to_instagram"
        self.items = [replace(item, **{key: selected}) for item in self.items]
        if self.items:
            self.dataChanged.emit(
                self.index(0, column),
                self.index(len(self.items) - 1, column),
                [Qt.CheckStateRole],
            )

    def set_thumbnail(
        self,
        row: int,
        generation: int,
        pixmap: QPixmap,
        expected_path=None,
    ) -> bool:
        if generation != self.generation:
            return False
        if expected_path is not None:
            row = next(
                (
                    index
                    for index, item in enumerate(self.items)
                    if item.path == expected_path
                ),
                -1,
            )
        if not 0 <= row < len(self.items):
            return False
        self._thumbnails[row] = pixmap
        index = self.index(row, self.THUMBNAIL)
        self.dataChanged.emit(index, index, [Qt.DecorationRole])
        return True


class PlatformCheckDelegate(QStyledItemDelegate):
    """Paint centered native platform checks and an informational ratio warning."""

    WARNING_TOOLTIP = "Aspect ratio may require cropping for Instagram."
    WARNING_SIZE = 16
    GROUP_SPACING = 4

    def _style(self, option):
        return option.widget.style() if option.widget else QApplication.style()

    def _native_indicator_size(self, option) -> QSize:
        style = self._style(option)
        return QSize(
            style.pixelMetric(QStyle.PM_IndicatorWidth, option, option.widget),
            style.pixelMetric(QStyle.PM_IndicatorHeight, option, option.widget),
        )

    def control_rects(self, option, index) -> tuple[QRect, QRect]:
        """Return centered checkbox and optional warning rectangles."""
        indicator_size = self._native_indicator_size(option)
        warning = bool(index.data(ImageTableModel.InstagramRatioWarningRole))
        warning_width = self.WARNING_SIZE if warning else 0
        group_width = indicator_size.width() + (
            self.GROUP_SPACING + warning_width if warning else 0
        )
        # Center from widths rather than QRect.center(): QRect uses inclusive right
        # and bottom edges, so mixing its center with half-width arithmetic can
        # introduce an avoidable extra pixel of bias for odd-sized cells.
        left = option.rect.left() + (option.rect.width() - group_width) // 2
        top = option.rect.top() + (option.rect.height() - indicator_size.height()) // 2
        indicator = QRect(
            QPoint(left, top),
            indicator_size,
        )
        warning_rect = QRect()
        if warning:
            warning_rect = QRect(
                left + indicator_size.width() + self.GROUP_SPACING,
                option.rect.top() + (option.rect.height() - self.WARNING_SIZE) // 2,
                self.WARNING_SIZE,
                self.WARNING_SIZE,
            )
        return indicator, warning_rect

    def _checkbox_style_option(self, option, index, indicator_rect):
        """Build the model-initialized option used by the native checkbox style."""
        check = type(option)(option)
        self.initStyleOption(check, index)
        check.rect = indicator_rect

        # The option supplied to paint() describes the view item but has not yet
        # been initialized from the model.  Windows' native style consults the
        # QStyleOptionViewItem checkState in addition to the State_On/Off bits.
        # Keep both representations synchronized with the model.
        check_state = (
            Qt.Checked if index.data(Qt.CheckStateRole) == Qt.Checked else Qt.Unchecked
        )
        check.checkState = check_state
        check.state &= ~(QStyle.State_On | QStyle.State_Off | QStyle.State_NoChange)
        check.state |= (
            QStyle.State_On if check_state == Qt.Checked else QStyle.State_Off
        )

        # initStyleOption() supplies the model roles; enabled/active belong to
        # the view's paint context and must remain exactly as the view provided.
        context_states = QStyle.State_Enabled | QStyle.State_Active
        check.state = (check.state & ~context_states) | (option.state & context_states)
        return check

    def paint(self, painter: QPainter, option, index) -> None:
        style = self._style(option)
        background = type(option)(option)
        background.features &= ~QStyleOptionViewItem.HasCheckIndicator
        background.text = ""
        style.drawControl(QStyle.CE_ItemViewItem, background, painter, option.widget)

        indicator_rect, warning_rect = self.control_rects(option, index)
        check = self._checkbox_style_option(option, index, indicator_rect)
        style.drawPrimitive(
            QStyle.PE_IndicatorItemViewItemCheck, check, painter, option.widget
        )

        if not warning_rect.isEmpty():
            icon = style.standardIcon(
                QStyle.SP_MessageBoxWarning, option, option.widget
            )
            icon.paint(painter, warning_rect)

    def editorEvent(self, event, model, option, index) -> bool:
        # This is deliberately the exact rectangle used by paint().  In
        # particular, do not ask the style for a second indicator rectangle:
        # native styles may place that rectangle as though the unmodified item
        # option were being painted, which diverges from our centered control.
        indicator_rect, _ = self.control_rects(option, index)
        event_position = event.position()
        event_position = (
            event_position.toPoint()
            if hasattr(event_position, "toPoint")
            else event_position
        )
        if event.type() in (QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick):
            if event.button() == Qt.LeftButton and indicator_rect.contains(
                event_position
            ):
                if event.type() == QEvent.MouseButtonDblClick:
                    return True
                new_state = (
                    Qt.Unchecked
                    if index.data(Qt.CheckStateRole) == Qt.Checked
                    else Qt.Checked
                )
                return model.setData(index, new_state, Qt.CheckStateRole)
            return False
        if event.type() == QEvent.MouseButtonPress:
            return indicator_rect.contains(event_position)
        return super().editorEvent(event, model, option, index)

    def helpEvent(self, event, view, option, index) -> bool:
        _, warning_rect = self.control_rects(option, index)
        if not warning_rect.isEmpty() and warning_rect.contains(event.pos()):
            QToolTip.showText(event.globalPos(), self.WARNING_TOOLTIP, view)
            return True
        return super().helpEvent(event, view, option, index)

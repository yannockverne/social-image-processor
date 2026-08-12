"""Table model for source metadata and platform selections."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QPixmap

from app.models.image_item import ImageItem
from app.models.watermark import WatermarkStatus
from app.utils.formatting import format_bytes


class ImageTableModel(QAbstractTableModel):
    """A lightweight metadata model which never retains source rasters."""

    THUMBNAIL, FILENAME, DIMENSIONS, SIZE, X, INSTAGRAM, WATERMARK = range(7)
    HEADERS = (
        "Preview",
        "Filename",
        "Dimensions",
        "Size",
        "X",
        "Instagram",
        "Watermark",
    )

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
        if role == Qt.ForegroundRole and column == self.WATERMARK:
            status = item.watermark_match.status if item.watermark_match else None
            return QColor("#67d391" if status is WatermarkStatus.EXACT else "#ffb454")
        if role == Qt.TextAlignmentRole and column in (
            self.DIMENSIONS,
            self.SIZE,
            self.X,
            self.INSTAGRAM,
            self.WATERMARK,
        ):
            return Qt.AlignCenter
        return None

    def flags(self, index):
        flags = super().flags(index)
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

    def set_platform_all(self, column: int, selected: bool) -> None:
        key = "export_to_x" if column == self.X else "export_to_instagram"
        self.items = [replace(item, **{key: selected}) for item in self.items]
        if self.items:
            self.dataChanged.emit(
                self.index(0, column),
                self.index(len(self.items) - 1, column),
                [Qt.CheckStateRole],
            )

    def set_thumbnail(self, row: int, generation: int, pixmap: QPixmap) -> bool:
        if generation != self.generation or not 0 <= row < len(self.items):
            return False
        self._thumbnails[row] = pixmap
        index = self.index(row, self.THUMBNAIL)
        self.dataChanged.emit(index, index, [Qt.DecorationRole])
        return True

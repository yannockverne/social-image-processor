"""Selected-image preview presentation widget (no image processing)."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget


class PreviewPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.title = QLabel("Preview")
        self.image = QLabel("Select an image")
        self.image.setAlignment(Qt.AlignCenter)
        self.image.setMinimumSize(300, 240)
        self.image.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.image.setStyleSheet(
            "QLabel { background: palette(base); border: 1px solid palette(mid); }"
        )
        self.status = QLabel("")
        self.status.setAlignment(Qt.AlignCenter)
        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.image, 1)
        layout.addWidget(self.status)

    def show_loading(self, filename: str, status: str = "") -> None:
        self.title.setText(filename)
        self.image.setPixmap(QPixmap())
        self.image.setText("Loading preview…")
        self.status.setText(status)

    def show_pixmap(self, pixmap: QPixmap) -> None:
        self.image.setText("")
        self.image.setPixmap(
            pixmap.scaled(
                self.image.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        )

    def clear(self) -> None:
        self.title.setText("Preview")
        self.image.setPixmap(QPixmap())
        self.image.setText("Select an image")
        self.status.clear()

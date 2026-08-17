"""Non-blocking busy veil used while the image workspace is populated."""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget


class LoadingOverlay(QWidget):
    """A light, event-loop-friendly overlay over one content widget."""

    def __init__(self, target: QWidget) -> None:
        super().__init__(target)
        self.setObjectName("loadingOverlay")
        self.setAttribute(self.WidgetAttribute.WA_TransparentForMouseEvents)
        layout = QVBoxLayout(self)
        layout.addStretch()
        self.message = QLabel("Scanning images…")
        self.message.setObjectName("loadingMessage")
        self.message.setAlignment(Qt.AlignCenter)
        self.spinner = QProgressBar()
        self.spinner.setObjectName("loadingSpinner")
        self.spinner.setRange(0, 0)
        self.spinner.setFixedWidth(190)
        layout.addWidget(self.message, alignment=Qt.AlignCenter)
        layout.addWidget(self.spinner, alignment=Qt.AlignCenter)
        layout.addStretch()
        target.installEventFilter(self)
        self.hide()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.parentWidget() and event.type() in (QEvent.Resize, QEvent.Show):
            self.setGeometry(watched.rect())
        return super().eventFilter(watched, event)

    def show_work(self, message: str) -> None:
        self.message.setText(message)
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()

    def finish(self) -> None:
        self.hide()

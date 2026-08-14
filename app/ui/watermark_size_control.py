"""Non-persisted watermark size control for the desktop UI."""

from __future__ import annotations

from PySide6.QtWidgets import QDoubleSpinBox, QLabel, QLayout, QWidget

from app.core.watermarking import (
    DEFAULT_WATERMARK_SIZE_RATIO,
    set_watermark_size_ratio,
)


def install_watermark_size_control(window) -> QDoubleSpinBox:
    """Add a session-only watermark-size percentage beside the design selector."""
    set_watermark_size_ratio(DEFAULT_WATERMARK_SIZE_RATIO)

    control = QDoubleSpinBox(window)
    control.setObjectName("watermarkSize")
    control.setRange(3.0, 15.0)
    control.setSingleStep(0.5)
    control.setDecimals(1)
    control.setSuffix(" %")
    control.setFixedWidth(90)
    control.setValue(DEFAULT_WATERMARK_SIZE_RATIO * 100.0)
    control.setToolTip(
        "Watermark width as a percentage of the image's geometric mean. "
        "This value resets to 8% on every launch."
    )

    options = _find_layout_containing(
        window.centralWidget().layout(), window.watermark_selector
    )
    if options is None:
        raise RuntimeError("Could not locate watermark options layout")

    selector_index = _widget_index(options, window.watermark_selector)
    label = QLabel("Watermark size")
    options.insertWidget(selector_index + 1, label)
    options.insertWidget(selector_index + 2, control)

    window.watermark_size = control
    window.conflicting_controls.append(control)

    def size_changed(value: float) -> None:
        set_watermark_size_ratio(value / 100.0)
        window._refresh_selected_preview()

    control.valueChanged.connect(size_changed)
    return control


def _widget_index(layout: QLayout, target: QWidget) -> int:
    for index in range(layout.count()):
        if layout.itemAt(index).widget() is target:
            return index
    raise RuntimeError("Widget is not present in the requested layout")


def _find_layout_containing(layout: QLayout | None, target: QWidget) -> QLayout | None:
    if layout is None:
        return None
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item.widget() is target:
            return layout
        child = item.layout()
        if child is not None:
            found = _find_layout_containing(child, target)
            if found is not None:
                return found
    return None

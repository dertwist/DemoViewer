
from PySide6.QtWidgets import (
    QGraphicsView,
    QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QSlider, QDoubleSpinBox, QSpinBox,
    QFormLayout, QGroupBox, QLineEdit
)
from PySide6.QtGui import QPainter
from PySide6.QtCore import Qt, Signal, Slot, QPointF


class ZoomableGraphicsView(QGraphicsView):
    mouse_moved = Signal(float, float)

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)

    def wheelEvent(self, e):
        factor = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
        old = self.mapToScene(e.position().toPoint())
        self.scale(factor, factor)
        delta = self.mapToScene(e.position().toPoint()) - old
        self.translate(delta.x(), delta.y())

    def mouseMoveEvent(self, e):
        pt = self.mapToScene(e.position().toPoint())
        self.mouse_moved.emit(pt.x(), pt.y())
        super().mouseMoveEvent(e)


class LabeledSliderSpinBox(QWidget):
    """
    A combined widget for a label, slider, and spinbox.
    It supports both integer and float behaviors.
    """
    valueChanged = Signal(float)

    def __init__(self, label_text, default_value=0.0, minimum=0.0, maximum=100.0,
                 single_step=1.0, is_float=True, parent=None):
        super().__init__(parent)
        self.is_float = is_float
        self._layout = QHBoxLayout(self)
        self._label = QLabel(label_text, self)
        self._layout.addWidget(self._label)

        self._slider = QSlider(Qt.Horizontal, self)
        # We'll scale float values by 100 internally if is_float
        if self.is_float:
            self._slider.setRange(int(minimum * 100), int(maximum * 100))
            self._slider.setSingleStep(int(single_step * 100))
            self._slider.setValue(int(default_value * 100))
        else:
            self._slider.setRange(int(minimum), int(maximum))
            self._slider.setSingleStep(int(single_step))
            self._slider.setValue(int(default_value))
        self._layout.addWidget(self._slider)

        if self.is_float:
            self._spin = QDoubleSpinBox(self)
            self._spin.setDecimals(2 if single_step < 1 else 0)
            self._spin.setRange(minimum, maximum)
            self._spin.setSingleStep(single_step)
            self._spin.setValue(default_value)
        else:
            self._spin = QSpinBox(self)
            self._spin.setRange(int(minimum), int(maximum))
            self._spin.setSingleStep(int(single_step))
            self._spin.setValue(int(default_value))

        self._layout.addWidget(self._spin)

        # Connect signals
        self._slider.valueChanged.connect(self._on_slider_changed)
        self._spin.valueChanged.connect(self._on_spin_changed)

    def _on_slider_changed(self, val):
        real_val = float(val) / 100 if self.is_float else float(val)
        self._spin.blockSignals(True)
        self._spin.setValue(real_val)
        self._spin.blockSignals(False)
        self.valueChanged.emit(real_val)

    def _on_spin_changed(self, val):
        # val is float or int
        if self.is_float:
            scaled = int(val * 100)
        else:
            scaled = int(val)
        self._slider.blockSignals(True)
        self._slider.setValue(scaled)
        self._slider.blockSignals(False)
        self.valueChanged.emit(float(val))

    def get_value(self) -> float:
        return float(self._spin.value())

    def set_value(self, val: float):
        self._spin.setValue(val)
        self._on_spin_changed(val)


class RadarInfoWidget(QWidget):
    """Widget for displaying radar information including win percentages"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)

        # Create info fields using QLineEdit instead of QLabel for better readability
        self.addon_edit = QLineEdit("Addon: N/A")
        self.addon_edit.setReadOnly(True)

        self.map_edit = QLineEdit("Map: N/A")
        self.map_edit.setReadOnly(True)

        self.points_edit = QLineEdit("Points: 0")
        self.points_edit.setReadOnly(True)

        # Win percentage labels with team colors
        self.ct_win_label = QLabel("CT Win %: N/A")
        self.ct_win_label.setStyleSheet("color: #5D79AE; font-weight: bold;")  # CT Blue

        self.t_win_label = QLabel("T Win %: N/A")
        self.t_win_label.setStyleSheet("color: #C19511; font-weight: bold;")  # T Yellow/Gold

        # Add fields to layout
        self.layout.addWidget(self.addon_edit)
        self.layout.addWidget(self.map_edit)
        self.layout.addWidget(self.points_edit)

        # Add win percentage labels to a horizontal layout
        win_layout = QHBoxLayout()
        win_layout.addWidget(self.ct_win_label)
        win_layout.addWidget(self.t_win_label)
        self.layout.addLayout(win_layout)

        self.setLayout(self.layout)

    def update_info(self, addon, map_name, points, ct_win_pct=None, t_win_pct=None):
        """Update the displayed information"""
        self.addon_edit.setText(f"Addon: {addon}")
        self.map_edit.setText(f"Map: {map_name}")
        self.points_edit.setText(f"Points: {points}")

        # Format win percentages with 1 decimal place
        if ct_win_pct is not None:
            self.ct_win_label.setText(f"CT Win %: {ct_win_pct:.1f}%")
        else:
            self.ct_win_label.setText("CT Win %: N/A")

        if t_win_pct is not None:
            self.t_win_label.setText(f"T Win %: {t_win_pct:.1f}%")
        else:
            self.t_win_label.setText("T Win %: N/A")

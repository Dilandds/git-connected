"""
Shared orientation gizmo widget for 3D view rotation in annotation mode.
Used by both PyVista and pygfx viewers.
"""
import sys
from pathlib import Path
from PyQt5.QtWidgets import QWidget, QSizePolicy
from PyQt5.QtCore import Qt, pyqtSignal, QPointF, QRectF
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QPixmap


def _get_xyz_gizmo_path():
    """Return path to xyz_gizmo.png (handles PyInstaller frozen bundle)."""
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent.parent
    return base / 'assets' / 'xyz_gizmo.png'


class OrientationGizmoWidget(QWidget):
    """Interactive XYZ axes gizmo for rotating the 3D view in annotation mode.
    Click and drag to rotate the camera. Uses XYZ axes image or draws fallback.
    """
    rotation_delta = pyqtSignal(float, float)  # dx, dy in pixels

    SIZE = 72

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip("Drag to rotate view")
        self._drag_start = None
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        path = _get_xyz_gizmo_path()
        self._gizmo_pixmap = QPixmap(str(path)) if path.exists() else None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start is not None and event.buttons() & Qt.LeftButton:
            delta = event.pos() - self._drag_start
            self.rotation_delta.emit(float(delta.x()), float(delta.y()))
            self._drag_start = event.pos()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = None
            self.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        if self._gizmo_pixmap and not self._gizmo_pixmap.isNull():
            scaled = self._gizmo_pixmap.scaled(
                w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            x = (w - scaled.width()) // 2
            y = (h - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            self._paint_xyz_fallback(painter, w, h)
        painter.end()

    def _paint_xyz_fallback(self, painter, w, h):
        """Draw XYZ axes when image is not available."""
        cx, cy = w / 2, h / 2
        s = min(w, h) * 0.32
        def pt(x, y):
            return QPointF(x, y)
        # X axis - red, left
        painter.setPen(QPen(QColor("#E53935"), 2.5))
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(pt(cx, cy), pt(cx - s, cy + s * 0.3))
        # Y axis - green, down-right
        painter.setPen(QPen(QColor("#43A047"), 2.5))
        painter.drawLine(pt(cx, cy), pt(cx + s * 0.5, cy + s * 0.7))
        # Z axis - blue, up
        painter.setPen(QPen(QColor("#1E88E5"), 2.5))
        painter.drawLine(pt(cx, cy), pt(cx, cy - s))
        # Center circle (orange)
        painter.setBrush(QBrush(QColor("#FF9800")))
        painter.setPen(QPen(QColor("#FFFFFF"), 1.5))
        painter.drawEllipse(QRectF(cx - 4, cy - 4, 8, 8))

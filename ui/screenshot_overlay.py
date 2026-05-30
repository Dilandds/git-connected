"""
Transparent overlay widget for rubber-band rectangle selection (screenshot capture).
"""
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, pyqtSignal, QRect, QPoint
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QCursor


class ScreenshotOverlay(QWidget):
    """Transparent overlay that lets the user draw a rectangle on the 3D view."""

    region_selected = pyqtSignal(QRect)  # emitted with the selected rectangle

    def __init__(self, parent=None, zoom_callback=None, rotate_callback=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setStyleSheet("background: transparent;")
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)
        # Need keyboard focus so arrow keys can rotate the 3D camera
        self.setFocusPolicy(Qt.StrongFocus)

        self._origin = QPoint()
        self._current = QPoint()
        self._drawing = False
        self._zoom_callback = zoom_callback
        self._rotate_callback = rotate_callback
        # Arrow-key rotation step (pixels of equivalent drag)
        self._key_rotate_step = 18.0

    # ---- painting ----

    def paintEvent(self, event):
        if not self._drawing:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRect(self._origin, self._current).normalized()

        # Semi-transparent fill
        painter.setBrush(QBrush(QColor(82, 148, 226, 40)))
        # Blue border
        pen = QPen(QColor(82, 148, 226, 200), 2, Qt.DashLine)
        painter.setPen(pen)
        painter.drawRect(rect)
        painter.end()

    # ---- mouse events ----

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._origin = event.pos()
            self._current = event.pos()
            self._drawing = True
            self.update()

    def _constrain_square(self, origin, pos):
        """Constrain pos so the selection from origin is always a square."""
        dx = pos.x() - origin.x()
        dy = pos.y() - origin.y()
        side = max(abs(dx), abs(dy))
        sx = side if dx >= 0 else -side
        sy = side if dy >= 0 else -side
        return QPoint(origin.x() + sx, origin.y() + sy)

    def mouseMoveEvent(self, event):
        if self._drawing:
            self._current = self._constrain_square(self._origin, event.pos())
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._drawing:
            self._drawing = False
            final_pos = self._constrain_square(self._origin, event.pos())
            rect = QRect(self._origin, final_pos).normalized()
            self.update()
            # Only emit if the square has a minimum size
            if rect.width() > 10 and rect.height() > 10:
                self.region_selected.emit(rect)

    def wheelEvent(self, event):
        """Forward wheel events for zoom."""
        if self._zoom_callback:
            delta = event.angleDelta().y()
            if delta > 0:
                self._zoom_callback(1.15)
            elif delta < 0:
                self._zoom_callback(0.85)
            event.accept()
        else:
            super().wheelEvent(event)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Escape:
            self._drawing = False
            self.update()
            return
        # Arrow keys rotate the 3D camera (replaces the on-screen 3D Control gizmo)
        if self._rotate_callback is not None:
            step = self._key_rotate_step
            if event.modifiers() & Qt.ShiftModifier:
                step *= 2.5
            dx = dy = 0.0
            if key == Qt.Key_Left:
                dx = -step
            elif key == Qt.Key_Right:
                dx = step
            elif key == Qt.Key_Up:
                dy = -step
            elif key == Qt.Key_Down:
                dy = step
            else:
                super().keyPressEvent(event)
                return
            self._rotate_callback(dx, dy)
            event.accept()
            return
        super().keyPressEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        # Grab focus so arrow keys reach this overlay immediately
        self.setFocus(Qt.OtherFocusReason)

    def hideEvent(self, event):
        """Reset cursor when overlay is hidden - CrossCursor can persist on some platforms."""
        super().hideEvent(event)
        self.setCursor(Qt.ArrowCursor)  # Clear CrossCursor before hide completes
        parent = self.parent()
        if parent and isinstance(parent, QWidget):
            parent.setCursor(Qt.ArrowCursor)
        # Force Qt to refresh cursor (workaround for stuck cursor)
        pos = QCursor.pos()
        QCursor.setPos(pos.x() + 1, pos.y())
        QCursor.setPos(pos.x(), pos.y())

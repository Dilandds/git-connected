"""
Transparent overlay widget for rubber-band rectangle selection (screenshot capture).
"""
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, pyqtSignal, QRect, QPoint
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush


class ScreenshotOverlay(QWidget):
    """Transparent overlay that lets the user draw a rectangle on the 3D view."""

    region_selected = pyqtSignal(QRect)  # emitted with the selected rectangle

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setStyleSheet("background: transparent;")
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)

        self._origin = QPoint()
        self._current = QPoint()
        self._drawing = False

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

    def mouseMoveEvent(self, event):
        if self._drawing:
            self._current = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._drawing:
            self._drawing = False
            rect = QRect(self._origin, event.pos()).normalized()
            self.update()
            # Only emit if the rectangle has a minimum size
            if rect.width() > 10 and rect.height() > 10:
                self.region_selected.emit(rect)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._drawing = False
            self.update()

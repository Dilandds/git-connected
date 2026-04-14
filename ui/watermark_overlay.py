"""
Semi-transparent diagonal watermark overlay for the Education edition.
Paints repeated "ECTOFORM" text across the widget at a 30° angle.
"""
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QFont, QColor


class WatermarkOverlay(QWidget):
    """Transparent overlay that draws tiled diagonal 'ECTOFORM' watermarks."""

    def __init__(self, parent=None, text: str = "ECTOFORM", opacity: float = 0.07):
        super().__init__(parent)
        self._text = text
        self._opacity = opacity
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setOpacity(self._opacity)

        font = QFont("Arial", 48, QFont.Bold)
        painter.setFont(font)
        painter.setPen(QColor(180, 180, 180))

        fm = painter.fontMetrics()
        text_w = fm.horizontalAdvance(self._text)
        text_h = fm.height()

        # Tile the text diagonally across the entire widget
        step_x = text_w + 120
        step_y = text_h + 100

        painter.save()
        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(-30)

        # Cover enough area to fill the rotated rectangle
        span = max(self.width(), self.height()) * 2
        y = -span
        while y < span:
            x = -span
            while x < span:
                painter.drawText(int(x), int(y), self._text)
                x += step_x
            y += step_y

        painter.restore()
        painter.end()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()

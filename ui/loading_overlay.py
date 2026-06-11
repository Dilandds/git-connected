"""
Loading overlay displayed while a 3D file is being processed.
Appears over the viewer with logo + animated spinner.
"""
import sys
import math
from pathlib import Path

from typing import Optional
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt5.QtGui import QPainter, QColor, QPen, QFont, QPixmap, QFontMetricsF


def _asset_path(filename: str) -> Path:
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent.parent
    return base / 'assets' / filename


class LoadingOverlay(QWidget):
    """Full-widget overlay shown while a 3D file loads.

    Parent widget is responsible for sizing (call setGeometry(parent.rect())).
    """

    _SPINNER_RADIUS = 28
    _SPINNER_ARC_SPAN = 110   # degrees
    _SPINNER_SPEED = 9        # degrees per tick
    _TICK_MS = 25             # ~40 fps

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setWindowFlags(Qt.Widget)
        # On Windows the WebGPU canvas is a native HWND and always paints over
        # non-native Qt child widgets regardless of raise_().  Making the overlay
        # native too gives it its own HWND so Windows z-ordering works correctly.
        import sys as _sys
        if _sys.platform == 'win32':
            self.setAttribute(Qt.WA_NativeWindow)
        self._angle = 0
        self._logo: Optional[QPixmap] = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._load_logo()
        self.hide()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_loading(self):
        """Show the overlay and start animating."""
        if self.parent():
            self.setGeometry(self.parent().rect())
        self.raise_()
        self.show()
        self._angle = 0
        if not self._timer.isActive():
            self._timer.start(self._TICK_MS)

    def hide_loading(self):
        """Stop animation and hide."""
        self._timer.stop()
        self.hide()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_logo(self):
        for name in ('Logo_Ectoform_2_copy-removebg-preview.png', 'logo.png'):
            path = _asset_path(name)
            if path.exists():
                pm = QPixmap(str(path))
                if not pm.isNull():
                    self._logo = pm.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    return

    def _tick(self):
        self._angle = (self._angle + self._SPINNER_SPEED) % 360
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        # --- background ---
        painter.fillRect(self.rect(), QColor(28, 32, 38, 230))

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2

        # --- logo or text ---
        logo_bottom = cy - 20
        if self._logo and not self._logo.isNull():
            lw, lh = self._logo.width(), self._logo.height()
            logo_top = logo_bottom - lh
            painter.drawPixmap(int(cx - lw / 2), int(logo_top), self._logo)
        else:
            font = QFont('Arial', 20, QFont.Bold)
            painter.setFont(font)
            painter.setPen(QColor('#E0ECF4'))
            fm = QFontMetricsF(font)
            text = 'ECTOFORM'
            tw = fm.horizontalAdvance(text)
            th = fm.height()
            logo_bottom = cy - 10
            painter.drawText(
                QRectF(cx - tw / 2, logo_bottom - th, tw, th),
                Qt.AlignCenter, text,
            )

        # --- spinner ring (background track) ---
        r = self._SPINNER_RADIUS
        spinner_cx, spinner_cy = cx, logo_bottom + 22 + r
        rect = QRectF(spinner_cx - r, spinner_cy - r, r * 2, r * 2)

        pen = QPen(QColor(50, 58, 68), 4)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawEllipse(rect)

        # --- spinner arc ---
        pen = QPen(QColor('#5294E2'), 4)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        start_angle = int(-self._angle * 16)
        span_angle = int(self._SPINNER_ARC_SPAN * 16)
        painter.drawArc(rect, start_angle, span_angle)

        # --- "Loading…" label ---
        font = QFont('Arial', 11)
        painter.setFont(font)
        painter.setPen(QColor('#7a8a9a'))
        label_rect = QRectF(cx - 80, spinner_cy + r + 14, 160, 22)
        painter.drawText(label_rect, Qt.AlignCenter, 'Loading…')

        painter.end()

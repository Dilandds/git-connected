"""
Full-screen snipping overlay — freezes the screen then lets the user drag a
rectangle to capture any area (works for every app unconditionally).

SnipCountdown: counts down N seconds before the freeze so the user has time
to switch apps, restore windows, or arrange anything they want to capture.
"""
from PyQt5.QtCore import Qt, pyqtSignal, QRect, QPoint, QTimer
from PyQt5.QtGui import QPixmap, QColor, QPainter, QPen, QFont
from PyQt5.QtWidgets import QWidget, QApplication, QLabel, QVBoxLayout, QHBoxLayout


# ── macOS helper: float above every Mission Control space ─────────────────────

def _mac_join_all_spaces(widget):
    """Make widget visible in all macOS spaces including fullscreen-app spaces."""
    try:
        import ctypes
        _lib = ctypes.CDLL('/usr/lib/libobjc.dylib')
        _lib.sel_registerName.restype  = ctypes.c_void_p
        _lib.sel_registerName.argtypes = [ctypes.c_char_p]
        _lib.objc_msgSend.restype  = ctypes.c_void_p
        _lib.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        _sel = _lib.sel_registerName
        _msg = _lib.objc_msgSend
        _view = ctypes.c_void_p(int(widget.winId()))
        _win  = ctypes.c_void_p(_msg(_view, _sel(b'window')))
        if not _win:
            return
        # CanJoinAllSpaces(1) | FullScreenAuxiliary(256)
        _f_ul = ctypes.cast(_msg, ctypes.CFUNCTYPE(
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong))
        _f_ul(_win, _sel(b'setCollectionBehavior:'), ctypes.c_ulong(1 | 256))
        # NSScreenSaverWindowLevel = 1000
        _f_l = ctypes.cast(_msg, ctypes.CFUNCTYPE(
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long))
        _f_l(_win, _sel(b'setLevel:'), ctypes.c_long(1000))
        _msg(_win, _sel(b'orderFrontRegardless'))
    except Exception:
        pass


# ── Pre-snip countdown toast ──────────────────────────────────────────────────

class SnipCountdown(QWidget):
    """Centred full-screen countdown overlay that fires the snip at zero.

    The user has SECONDS seconds to open, restore, or arrange any window they
    want to capture.  The screenshot fires automatically — even if the widget
    is covered.  Click anywhere to skip; right-click or Esc to cancel.
    """
    ready     = pyqtSignal()
    cancelled = pyqtSignal()

    SECONDS = 5

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(440, 220)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Card background
        card = QWidget()
        card.setStyleSheet("""
            QWidget {
                background: rgba(15, 15, 15, 230);
                border-radius: 20px;
            }
        """)
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(32, 24, 32, 24)
        card_lay.setSpacing(10)

        # Top instruction line
        top = QLabel('Open the app you want to capture')
        top.setAlignment(Qt.AlignCenter)
        top.setStyleSheet('color: #d1d5db; font-size: 15px; font-weight: 500; background: transparent;')
        card_lay.addWidget(top)

        # Large countdown number
        self._num = QLabel(str(self.SECONDS))
        self._num.setAlignment(Qt.AlignCenter)
        self._num.setStyleSheet('color: #ffffff; font-size: 72px; font-weight: 800; background: transparent;')
        card_lay.addWidget(self._num)

        # Bottom hint
        bot = QLabel('Click anywhere to snip now  •  Right-click or Esc to cancel')
        bot.setAlignment(Qt.AlignCenter)
        bot.setStyleSheet('color: #6b7280; font-size: 12px; background: transparent;')
        card_lay.addWidget(bot)

        lay.addWidget(card)

        self._remaining = self.SECONDS

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

        # Centre of primary screen
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            screen.center().x() - self.width() // 2,
            screen.center().y() - self.height() // 2,
        )

    def start(self):
        self._timer.start()
        self.show()
        self.raise_()
        _mac_join_all_spaces(self)   # float above Chrome/Brave fullscreen spaces

    def _tick(self):
        self._remaining -= 1
        if self._remaining <= 0:
            self._fire()
        else:
            self._num.setText(str(self._remaining))

    def _fire(self):
        self._timer.stop()
        self.hide()
        self.ready.emit()

    def _cancel(self):
        self._timer.stop()
        self.hide()
        self.cancelled.emit()

    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton:
            self._cancel()
        else:
            self._fire()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self._cancel()


# ── Full-screen snip overlay ──────────────────────────────────────────────────

class SnipOverlay(QWidget):
    """Full-screen frozen-screenshot overlay with drag-to-select snipping."""

    captured  = pyqtSignal(QPixmap)
    cancelled = pyqtSignal()

    def __init__(self, base_pixmap: QPixmap, dpr: float, parent=None):
        super().__init__(
            parent,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool,
        )
        self._base = base_pixmap
        self._dpr  = dpr

        self._start:    QPoint | None = None
        self._end:      QPoint | None = None
        self._selecting = False

        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)

    # ── paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)

        p.drawPixmap(self.rect(), self._base)
        p.fillRect(self.rect(), QColor(0, 0, 0, 90))

        if not self._selecting:
            p.setPen(QColor(255, 255, 255, 180))
            f = QFont()
            f.setPointSize(14)
            f.setBold(True)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignCenter,
                       'Drag to select an area   •   Esc / Right-click to cancel')

        if self._selecting and self._start and self._end:
            sel = QRect(self._start, self._end).normalized()
            if sel.width() > 2 and sel.height() > 2:
                p.save()
                p.setClipRect(sel)
                p.drawPixmap(self.rect(), self._base)
                p.restore()
                pen = QPen(QColor(255, 255, 255), 2)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawRect(sel)

    # ── mouse ─────────────────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._start     = e.pos()
            self._end       = e.pos()
            self._selecting = True
        elif e.button() == Qt.RightButton:
            self._cancel()

    def mouseMoveEvent(self, e):
        if self._selecting:
            self._end = e.pos()
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self._selecting:
            self._end       = e.pos()
            self._selecting = False
            sel = QRect(self._start, self._end).normalized()
            if sel.width() > 5 and sel.height() > 5:
                phys = QRect(
                    int(sel.x()      * self._dpr),
                    int(sel.y()      * self._dpr),
                    int(sel.width()  * self._dpr),
                    int(sel.height() * self._dpr),
                )
                cropped = self._base.copy(phys)
                if not cropped.isNull():
                    self.releaseKeyboard()
                    self.close()
                    self.captured.emit(cropped)
                    return
            self._cancel()

    # ── keyboard ──────────────────────────────────────────────────────────────

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self._cancel()

    def force_front(self):
        """Float above every macOS Mission Control space (call after show())."""
        _mac_join_all_spaces(self)

    def _cancel(self):
        self.releaseKeyboard()
        self.close()
        self.cancelled.emit()

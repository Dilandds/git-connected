"""
Floating "Snip" trigger button — stays on top of every app/space while
screenshot mode is active.  Click it from any app to fire screencapture -i.
"""
from PyQt5.QtCore import Qt, pyqtSignal, QPoint
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QFont, QFontMetrics
from PyQt5.QtWidgets import QWidget, QApplication


def _mac_join_all_spaces(widget):
    """Float widget above every macOS Mission Control space."""
    try:
        import ctypes
        lib = ctypes.CDLL('/usr/lib/libobjc.dylib')
        lib.sel_registerName.restype  = ctypes.c_void_p
        lib.sel_registerName.argtypes = [ctypes.c_char_p]
        lib.objc_msgSend.restype  = ctypes.c_void_p
        lib.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        sel = lib.sel_registerName
        msg = lib.objc_msgSend
        view = ctypes.c_void_p(int(widget.winId()))
        win  = ctypes.c_void_p(msg(view, sel(b'window')))
        if not win:
            return
        f_ul = ctypes.cast(msg, ctypes.CFUNCTYPE(
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong))
        f_ul(win, sel(b'setCollectionBehavior:'), ctypes.c_ulong(1 | 256))
        f_l = ctypes.cast(msg, ctypes.CFUNCTYPE(
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long))
        f_l(win, sel(b'setLevel:'), ctypes.c_long(1000))
        msg(win, sel(b'orderFrontRegardless'))
    except Exception:
        pass


class SnipTriggerButton(QWidget):
    """
    Small draggable pill that floats above every app/space.
    Emits `triggered` when clicked — caller starts screencapture.
    """
    triggered = pyqtSignal()

    _W, _H = 110, 40
    _R     = 20          # corner radius
    _BG    = QColor(30, 30, 30, 220)
    _BG_H  = QColor(50, 120, 255, 240)   # hover blue
    _TEXT  = QColor(255, 255, 255)

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(self._W, self._H)
        self.setCursor(Qt.PointingHandCursor)

        self._hovered  = False
        self._drag_pos = None

        # Place near top-right of primary screen
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self._W - 20, screen.top() + 60)

    # ── show/hide ─────────────────────────────────────────────────────────────

    def show_floating(self):
        self.show()
        self.raise_()
        _mac_join_all_spaces(self)

    # ── paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(0, 0, self._W, self._H, self._R, self._R)

        p.fillPath(path, self._BG_H if self._hovered else self._BG)

        p.setPen(self._TEXT)
        f = QFont()
        f.setPointSize(13)
        f.setBold(True)
        p.setFont(f)
        p.drawText(self.rect(), Qt.AlignCenter, '📷  Snip')

    # ── interaction ───────────────────────────────────────────────────────────

    def enterEvent(self, e):
        self._hovered = True
        self.update()

    def leaveEvent(self, e):
        self._hovered = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(e.globalPos() - self._drag_pos)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            # Only fire if the mouse didn't move much (it's a click, not a drag)
            moved = (e.globalPos() - (self.frameGeometry().topLeft() + self._drag_pos)
                     if self._drag_pos else QPoint(999, 999))
            self._drag_pos = None
            if abs(moved.x()) < 6 and abs(moved.y()) < 6:
                self.triggered.emit()

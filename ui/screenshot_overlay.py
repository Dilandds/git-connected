"""
Transparent overlay widget for rubber-band rectangle selection (screenshot capture).

Input model in screenshot mode:
  - Left-mouse drag / wheel pass through to the pygfx canvas (native rotate + zoom).
  - Hold Space and drag to draw the capture square; release Space (or mouse) to commit.
  - Esc cancels the current draw.

Forwarding is achieved by toggling WA_TransparentForMouseEvents — the Qt-guaranteed
way to let the QRenderWidget underneath receive mouse events natively.
"""
from PyQt5.QtWidgets import QWidget, QLineEdit, QTextEdit, QPlainTextEdit, QApplication
from PyQt5.QtCore import Qt, pyqtSignal, QRect, QPoint
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QCursor


class ScreenshotOverlay(QWidget):
    """Transparent overlay that lets the user draw a rectangle on the 3D view
    while Space is held. Otherwise it is mouse-transparent so the 3D canvas
    underneath handles rotate/zoom natively."""

    region_selected = pyqtSignal(QRect)  # emitted with the selected rectangle

    def __init__(self, parent=None, zoom_callback=None, rotate_callback=None):
        super().__init__(parent)
        # NOTE: zoom_callback / rotate_callback are accepted for backwards
        # compatibility but no longer used — wheel + left-drag pass straight
        # to the pygfx canvas via WA_TransparentForMouseEvents.
        self._zoom_callback = zoom_callback
        self._rotate_callback = rotate_callback

        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setStyleSheet("background: transparent;")
        # Default: transparent to mouse so 3D canvas below handles rotate/zoom.
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setMouseTracking(True)
        # Need keyboard focus so Space / Esc reach the overlay.
        self.setFocusPolicy(Qt.StrongFocus)

        self._origin = QPoint()
        self._current = QPoint()
        self._drawing = False
        self._space_held = False

    # ---- helpers ----

    def _set_capture_mode(self, capture: bool):
        """Toggle whether the overlay grabs the mouse (capture) or forwards it (navigate)."""
        # When capturing: become opaque to mouse so we receive press/move/release.
        # When not capturing: become transparent so events reach pygfx canvas below.
        self.setAttribute(Qt.WA_TransparentForMouseEvents, not capture)
        self.setCursor(Qt.CrossCursor if capture else Qt.ArrowCursor)

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

    # ---- mouse events (only reach us while Space is held) ----

    def mousePressEvent(self, event):
        if not self._space_held:
            event.ignore()
            return
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
            self._finalize_draw(event.pos())

    def _finalize_draw(self, end_pos):
        """Commit the rubber-band rectangle and emit region_selected if big enough."""
        self._drawing = False
        final_pos = self._constrain_square(self._origin, end_pos)
        rect = QRect(self._origin, final_pos).normalized()
        self.update()
        if rect.width() > 10 and rect.height() > 10:
            self.region_selected.emit(rect)

    def wheelEvent(self, event):
        # Should rarely fire (we're mouse-transparent unless capturing), but if it
        # does, just ignore so the canvas below handles native zoom.
        event.ignore()

    # ---- keyboard ----

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Escape:
            self._drawing = False
            self._space_held = False
            self._set_capture_mode(False)
            self.update()
            return
        if key == Qt.Key_Space and not event.isAutoRepeat():
            self._space_held = True
            self._set_capture_mode(True)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            # If user was mid-draw, commit on space release.
            if self._drawing:
                self._finalize_draw(self._current)
            self._space_held = False
            self._set_capture_mode(False)
            event.accept()
            return
        super().keyReleaseEvent(event)

    # ---- show / hide ----

    def _on_focus_changed(self, old_widget, new_widget):
        """Release keyboard grab while a text input has focus; re-grab when it leaves."""
        if isinstance(new_widget, (QLineEdit, QTextEdit, QPlainTextEdit)):
            try:
                self.releaseKeyboard()
            except Exception:
                pass
        else:
            if self.isVisible():
                try:
                    self.grabKeyboard()
                except Exception:
                    pass

    def showEvent(self, event):
        super().showEvent(event)
        # Reset to navigate mode every time we appear.
        self._drawing = False
        self._space_held = False
        self._set_capture_mode(False)
        # Grab keyboard so Space/Esc reach us regardless of focused widget,
        # and so Space doesn't trigger focused buttons elsewhere.
        # Release temporarily when a text input gains focus so typing works.
        self.setFocus(Qt.OtherFocusReason)
        app = QApplication.instance()
        if app is not None:
            app.focusChanged.connect(self._on_focus_changed)
        try:
            self.grabKeyboard()
        except Exception:
            pass

    def hideEvent(self, event):
        """Release keyboard grab and reset cursor when overlay is hidden."""
        app = QApplication.instance()
        if app is not None:
            try:
                app.focusChanged.disconnect(self._on_focus_changed)
            except Exception:
                pass
        try:
            self.releaseKeyboard()
        except Exception:
            pass
        super().hideEvent(event)
        self.setCursor(Qt.ArrowCursor)
        parent = self.parent()
        if parent and isinstance(parent, QWidget):
            parent.setCursor(Qt.ArrowCursor)
        # Force Qt to refresh cursor (workaround for stuck cursor)
        pos = QCursor.pos()
        QCursor.setPos(pos.x() + 1, pos.y())
        QCursor.setPos(pos.x(), pos.y())

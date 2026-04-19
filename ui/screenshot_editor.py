"""
Screenshot Editor — allows drawing lines and placing text on a captured screenshot
before saving. Opens as a modal dialog from the screenshot panel.
"""
import logging
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QApplication, QInputDialog, QWidget, QFileDialog, QSlider, QSpinBox
)
from PyQt5.QtCore import Qt, QPoint, QPointF, pyqtSignal
from PyQt5.QtGui import (
    QPainter, QPixmap, QColor, QPen, QFont, QImage,
    QCursor, QFontMetrics
)
from ui.styles import default_theme, make_font
from i18n import t, on_language_changed
from ui.draw_color_picker import DrawColorPicker

logger = logging.getLogger(__name__)

# Tool modes
TOOL_NONE = 'none'
TOOL_LINE = 'line'
TOOL_TEXT = 'text'
TOOL_ARROW = 'arrow'


class _EditorCanvas(QWidget):
    """Canvas widget that renders the screenshot with drawn annotations on top."""

    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self._original = pixmap
        self._scale = 1.0
        self._offset = QPoint(0, 0)
        self._tool = TOOL_NONE
        self._color = '#FF0000'
        self._line_width = 3
        self._font_size = 16

        # Annotation layers (stored in image coords)
        self._lines = []       # list of (QPointF start, QPointF end, color, width)
        self._arrows = []      # list of (QPointF start, QPointF end, color, width)
        self._texts = []       # list of (QPointF pos, str text, color, font_size)
        self._undo_stack = []  # list of ('line'|'arrow'|'text', index)

        # Drawing state
        self._drawing = False
        self._draw_start = QPointF()
        self._draw_current = QPointF()

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self._fit_to_widget()

    def set_tool(self, tool: str):
        self._tool = tool
        if tool == TOOL_LINE or tool == TOOL_ARROW:
            self.setCursor(Qt.CrossCursor)
        elif tool == TOOL_TEXT:
            self.setCursor(Qt.IBeamCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def set_color(self, color: str):
        self._color = color

    def set_line_width(self, w: int):
        self._line_width = w

    def set_font_size(self, s: int):
        self._font_size = s

    def undo(self):
        if not self._undo_stack:
            return
        kind, idx = self._undo_stack.pop()
        if kind == 'line' and idx < len(self._lines):
            self._lines.pop(idx)
        elif kind == 'arrow' and idx < len(self._arrows):
            self._arrows.pop(idx)
        elif kind == 'text' and idx < len(self._texts):
            self._texts.pop(idx)
        self.update()

    def clear_annotations(self):
        self._lines.clear()
        self._arrows.clear()
        self._texts.clear()
        self._undo_stack.clear()
        self.update()

    def get_result_pixmap(self) -> QPixmap:
        """Return the original pixmap with all annotations burned in."""
        result = self._original.copy()
        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)
        self._paint_annotations(painter, scale=1.0, offset=QPointF(0, 0))
        painter.end()
        return result

    # ---- coordinate transforms ----

    def _widget_to_image(self, pos: QPoint) -> QPointF:
        return QPointF(
            (pos.x() - self._offset.x()) / self._scale,
            (pos.y() - self._offset.y()) / self._scale,
        )

    def _image_to_widget(self, pos: QPointF) -> QPointF:
        return QPointF(
            pos.x() * self._scale + self._offset.x(),
            pos.y() * self._scale + self._offset.y(),
        )

    def _fit_to_widget(self):
        if self._original.isNull():
            return
        w_ratio = self.width() / max(self._original.width(), 1)
        h_ratio = self.height() / max(self._original.height(), 1)
        self._scale = min(w_ratio, h_ratio, 1.0)  # don't upscale
        img_w = self._original.width() * self._scale
        img_h = self._original.height() * self._scale
        self._offset = QPoint(
            int((self.width() - img_w) / 2),
            int((self.height() - img_h) / 2),
        )

    # ---- painting ----

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(default_theme.background))

        # Draw image
        if not self._original.isNull():
            target_w = int(self._original.width() * self._scale)
            target_h = int(self._original.height() * self._scale)
            scaled = self._original.scaled(target_w, target_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            painter.drawPixmap(self._offset, scaled)

        # Draw annotations
        offset_f = QPointF(self._offset)
        self._paint_annotations(painter, self._scale, offset_f)

        # Draw in-progress line/arrow
        if self._drawing and self._tool in (TOOL_LINE, TOOL_ARROW):
            start_w = self._image_to_widget(self._draw_start)
            end_w = self._image_to_widget(self._draw_current)
            pen = QPen(QColor(self._color), self._line_width * self._scale)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawLine(start_w, end_w)
            if self._tool == TOOL_ARROW:
                self._draw_arrowhead(painter, start_w, end_w, self._color, self._line_width * self._scale)

        painter.end()

    def _paint_annotations(self, painter: QPainter, scale: float, offset: QPointF):
        """Paint all annotations. Used for both display and burn-in."""
        # Lines
        for start, end, color, width in self._lines:
            pen = QPen(QColor(color), width * scale)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            s = QPointF(start.x() * scale + offset.x(), start.y() * scale + offset.y())
            e = QPointF(end.x() * scale + offset.x(), end.y() * scale + offset.y())
            painter.drawLine(s, e)

        # Arrows
        for start, end, color, width in self._arrows:
            pen = QPen(QColor(color), width * scale)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            s = QPointF(start.x() * scale + offset.x(), start.y() * scale + offset.y())
            e = QPointF(end.x() * scale + offset.x(), end.y() * scale + offset.y())
            painter.drawLine(s, e)
            self._draw_arrowhead(painter, s, e, color, width * scale)

        # Texts
        for pos, text, color, font_size in self._texts:
            font = QFont("Arial", max(1, int(font_size * scale)))
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(color))
            p = QPointF(pos.x() * scale + offset.x(), pos.y() * scale + offset.y())
            painter.drawText(p, text)

    def _draw_arrowhead(self, painter, start: QPointF, end: QPointF, color: str, width: float):
        """Draw an arrowhead at the end point."""
        import math
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1:
            return
        # Normalize
        ux, uy = dx / length, dy / length
        # Arrow size proportional to line width
        arrow_len = max(12, width * 4)
        arrow_w = arrow_len * 0.5
        # Two points for arrowhead
        bx = end.x() - ux * arrow_len
        by = end.y() - uy * arrow_len
        p1 = QPointF(bx + uy * arrow_w, by - ux * arrow_w)
        p2 = QPointF(bx - uy * arrow_w, by + ux * arrow_w)
        from PyQt5.QtGui import QPolygonF, QBrush
        polygon = QPolygonF([end, p1, p2])
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(color)))
        painter.drawPolygon(polygon)

    # ---- mouse events ----

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        img_pos = self._widget_to_image(event.pos())
        if self._tool in (TOOL_LINE, TOOL_ARROW):
            self._drawing = True
            self._draw_start = img_pos
            self._draw_current = img_pos
        elif self._tool == TOOL_TEXT:
            text, ok = QInputDialog.getText(self, "Add Text", "Enter text:")
            if ok and text.strip():
                self._texts.append((img_pos, text.strip(), self._color, self._font_size))
                self._undo_stack.append(('text', len(self._texts) - 1))
                self.update()

    def mouseMoveEvent(self, event):
        if self._drawing:
            self._draw_current = self._widget_to_image(event.pos())
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._drawing:
            self._drawing = False
            end_pos = self._widget_to_image(event.pos())
            # Only add if has some length
            dx = end_pos.x() - self._draw_start.x()
            dy = end_pos.y() - self._draw_start.y()
            if (dx * dx + dy * dy) > 25:
                if self._tool == TOOL_LINE:
                    self._lines.append((self._draw_start, end_pos, self._color, self._line_width))
                    self._undo_stack.append(('line', len(self._lines) - 1))
                elif self._tool == TOOL_ARROW:
                    self._arrows.append((self._draw_start, end_pos, self._color, self._line_width))
                    self._undo_stack.append(('arrow', len(self._arrows) - 1))
            self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_to_widget()


class ScreenshotEditorDialog(QDialog):
    """Modal dialog for annotating a screenshot with text and lines before saving."""

    pixmap_updated = pyqtSignal(QPixmap)  # emitted when user saves edits

    def __init__(self, pixmap: QPixmap, title: str = "Edit Screenshot", parent=None):
        super().__init__(parent)
        self._original = pixmap
        self.setWindowTitle(title)
        self.setModal(True)
        self._current_tool = TOOL_NONE
        self._current_color = '#FF0000'

        from ui.annotation_icon import get_app_window_icon
        icon = get_app_window_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)

        self._init_ui()
        self._resize_to_screen()

    def _resize_to_screen(self):
        screen = QApplication.primaryScreen()
        if screen:
            sg = screen.availableGeometry()
            w = int(sg.width() * 0.85)
            h = int(sg.height() * 0.85)
        else:
            w, h = 1200, 800
        self.resize(w, h)

    def _init_ui(self):
        self.setStyleSheet(f"background-color: {default_theme.background};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)

        btn_css = f"""
            QPushButton {{
                background-color: {default_theme.row_bg_standard};
                color: {default_theme.text_primary};
                border: 1px solid {default_theme.border_standard};
                border-radius: 6px;
                font-size: 12px;
                padding: 5px 12px;
                min-width: 32px;
            }}
            QPushButton:hover {{
                background-color: {default_theme.row_bg_hover};
            }}
        """
        active_css = f"""
            QPushButton {{
                background-color: {default_theme.button_primary};
                color: #FFFFFF;
                border: 1px solid {default_theme.button_primary};
                border-radius: 6px;
                font-size: 12px;
                padding: 5px 12px;
                min-width: 32px;
            }}
            QPushButton:hover {{
                background-color: {default_theme.button_primary_hover};
            }}
        """
        self._btn_css = btn_css
        self._active_css = active_css

        # Tool buttons
        self._line_btn = QPushButton("✏ Line")
        self._line_btn.setToolTip("Draw straight lines")
        self._line_btn.setCursor(Qt.PointingHandCursor)
        self._line_btn.setStyleSheet(btn_css)
        self._line_btn.clicked.connect(lambda: self._set_tool(TOOL_LINE))
        toolbar.addWidget(self._line_btn)

        self._arrow_btn = QPushButton("➜ Arrow")
        self._arrow_btn.setToolTip("Draw arrows")
        self._arrow_btn.setCursor(Qt.PointingHandCursor)
        self._arrow_btn.setStyleSheet(btn_css)
        self._arrow_btn.clicked.connect(lambda: self._set_tool(TOOL_ARROW))
        toolbar.addWidget(self._arrow_btn)

        self._text_btn = QPushButton("T Text")
        self._text_btn.setToolTip("Click on image to add text")
        self._text_btn.setCursor(Qt.PointingHandCursor)
        self._text_btn.setStyleSheet(btn_css)
        self._text_btn.clicked.connect(lambda: self._set_tool(TOOL_TEXT))
        toolbar.addWidget(self._text_btn)

        # Separator
        sep = QLabel("│")
        sep.setStyleSheet(f"color: {default_theme.border_standard}; font-size: 16px;")
        toolbar.addWidget(sep)

        # Color button
        self._color_btn = QPushButton("🎨")
        self._color_btn.setToolTip("Change color")
        self._color_btn.setFixedSize(32, 32)
        self._color_btn.setCursor(Qt.PointingHandCursor)
        self._color_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self._current_color};
                border: 2px solid {default_theme.border_standard};
                border-radius: 6px;
            }}
            QPushButton:hover {{
                border: 2px solid {default_theme.button_primary};
            }}
        """)
        self._color_btn.clicked.connect(self._show_color_picker)
        toolbar.addWidget(self._color_btn)

        # Separator
        sep2 = QLabel("│")
        sep2.setStyleSheet(f"color: {default_theme.border_standard}; font-size: 16px;")
        toolbar.addWidget(sep2)

        # Fixed line width (20px) and font size (70pt) — no user choice
        # Smaller values were too thin/small to be readable on screenshots.

        # Undo
        undo_btn = QPushButton("↩ Undo")
        undo_btn.setToolTip("Undo last annotation")
        undo_btn.setCursor(Qt.PointingHandCursor)
        undo_btn.setStyleSheet(btn_css)
        undo_btn.clicked.connect(self._undo)
        toolbar.addWidget(undo_btn)

        # Clear
        clear_btn = QPushButton("🗑 Clear")
        clear_btn.setToolTip("Remove all annotations")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setStyleSheet(btn_css)
        clear_btn.clicked.connect(self._clear)
        toolbar.addWidget(clear_btn)

        toolbar.addStretch()

        # Hint label
        self._hint = QLabel("Select a tool to start annotating")
        self._hint.setStyleSheet(f"color: {default_theme.text_subtext}; font-size: 11px;")
        toolbar.addWidget(self._hint)

        layout.addLayout(toolbar)

        # Canvas
        self._canvas = _EditorCanvas(self._original, self)
        self._canvas.setMinimumSize(400, 300)
        layout.addWidget(self._canvas, 1)

        # Bottom buttons
        bottom = QHBoxLayout()
        bottom.addStretch()

        save_file_btn = QPushButton("💾  Save to File")
        save_file_btn.setCursor(Qt.PointingHandCursor)
        save_file_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #D1FAE5; color: #059669;
                border: 1px solid #A7F3D0; border-radius: 6px;
                padding: 8px 20px; font-size: 12px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #6EE7B7; }}
        """)
        save_file_btn.clicked.connect(self._save_to_file)
        bottom.addWidget(save_file_btn)

        apply_btn = QPushButton("✓  Apply & Close")
        apply_btn.setCursor(Qt.PointingHandCursor)
        apply_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {default_theme.button_primary}; color: #FFFFFF;
                border: none; border-radius: 6px;
                padding: 8px 20px; font-size: 12px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {default_theme.button_primary_hover}; }}
        """)
        apply_btn.clicked.connect(self._apply_and_close)
        bottom.addWidget(apply_btn)

        close_btn = QPushButton("✕  Cancel")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {default_theme.button_default_bg}; color: {default_theme.text_secondary};
                border: 1px solid {default_theme.button_default_border}; border-radius: 6px;
                padding: 8px 20px; font-size: 12px;
            }}
            QPushButton:hover {{ background-color: {default_theme.row_bg_hover}; }}
        """)
        close_btn.clicked.connect(self.reject)
        bottom.addWidget(close_btn)

        bottom.addStretch()
        layout.addLayout(bottom)

    def _set_tool(self, tool: str):
        self._current_tool = tool
        self._canvas.set_tool(tool)
        # Update button styles
        self._line_btn.setStyleSheet(self._active_css if tool == TOOL_LINE else self._btn_css)
        self._arrow_btn.setStyleSheet(self._active_css if tool == TOOL_ARROW else self._btn_css)
        self._text_btn.setStyleSheet(self._active_css if tool == TOOL_TEXT else self._btn_css)
        # Update hint
        hints = {
            TOOL_LINE: "Click and drag to draw a line",
            TOOL_ARROW: "Click and drag to draw an arrow",
            TOOL_TEXT: "Click on the image to place text",
        }
        self._hint.setText(hints.get(tool, "Select a tool to start annotating"))

    def _show_color_picker(self):
        picker = DrawColorPicker(self)
        picker.color_selected.connect(self._on_color_selected)
        btn_pos = self._color_btn.mapToGlobal(QPoint(0, self._color_btn.height()))
        picker.move(btn_pos)
        picker.show()

    def _on_color_selected(self, color: str):
        self._current_color = color
        self._canvas.set_color(color)
        self._color_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                border: 2px solid {default_theme.border_standard};
                border-radius: 6px;
            }}
            QPushButton:hover {{
                border: 2px solid {default_theme.button_primary};
            }}
        """)

    def _undo(self):
        self._canvas.undo()

    def _clear(self):
        self._canvas.clear_annotations()

    def _save_to_file(self):
        result = self._canvas.get_result_pixmap()
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Screenshot", "screenshot.png",
            "PNG (*.png);;JPEG (*.jpg);;All Files (*)"
        )
        if path:
            result.save(path)
            logger.info(f"Annotated screenshot saved to {path}")

    def _apply_and_close(self):
        result = self._canvas.get_result_pixmap()
        self.pixmap_updated.emit(result)
        self.accept()

    def get_result_pixmap(self) -> QPixmap:
        return self._canvas.get_result_pixmap()

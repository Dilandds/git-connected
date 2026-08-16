"""
Technical Overview - 2D image viewer with arrow callout annotations.
Users can upload an image (JPEG, PNG) or PDF page, then click to place
numbered annotation arrows that auto-draw from the margin to the clicked point.
"""
import os
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QFileDialog, QSizePolicy,
    QGridLayout,
    QTextEdit, QApplication
)
from PyQt5.QtCore import Qt, QPoint, QPointF, QRectF, pyqtSignal, QEvent
from PyQt5.QtGui import (
    QPixmap, QPainter, QPen, QColor, QFont, QFontMetrics,
    QBrush, QPainterPath, QPolygonF, QImage, QWheelEvent, QMouseEvent
)
from ui.styles import default_theme, make_font, TOOLTIP_STYLE
from ui.modal_utils import show_message_dialog, ask_yes_no_dialog

from i18n import t

logger = logging.getLogger(__name__)

# Arrow annotation colours
ARROW_COLOR = "#000000"
ARROW_SELECTED_COLOR = "#E53E3E"
ARROW_BADGE_BG = "#000000"
ARROW_BADGE_TEXT = "#FFFFFF"
IS_WINDOWS = os.name == "nt"
ARROW_BADGE_SIZE = 30 if IS_WINDOWS else 26
ARROW_BADGE_FONT_PX = 17 if IS_WINDOWS else 14


@dataclass
class ArrowAnnotation:
    """A single arrow annotation on the 2D image."""
    id: int
    target_x: float  # 0-1 normalised position on image (arrow tip)
    target_y: float
    origin_x: float = 0.0  # 0-1 normalised position for the numbered badge
    origin_y: float = 0.0
    text: str = ""
    margin_side: str = "left"  # kept for backward compat with old .ecto files
    color: str = ARROW_COLOR  # per-annotation color
    image_paths: list = field(default_factory=list)
    label: str = "Point"
    created_at: Optional[datetime] = None
    is_validated: bool = False
    # Reader-mode read/unread state — same purpose and same session-only
    # lifetime as ui/annotation_panel.py's Annotation.is_read (never
    # serialized in get_annotations_data/load_from_ecto below, so it
    # always starts unread on a fresh open, just like the 3D pins).
    is_read: bool = False
    # Same shape/purpose as ui/annotation_panel.py's Annotation fields of
    # the same name — added for parity with the 3D viewer's Supplier
    # Review Workflow conversation (see ui/annotation_popup.py). added_by
    # is 'supplier' for an arrow a reviewer placed themselves in LYNS
    # Lite; supplier_notes/pm_notes are the back-and-forth thread on top
    # of this arrow's own text/image_paths, each entry
    # {'id', 'author_name'/'supplier_name', 'text', 'image_paths', 'added_at'}.
    added_by: Optional[str] = None
    supplier_notes: list = field(default_factory=list)
    pm_notes: list = field(default_factory=list)


class ImageCanvas(QWidget):
    """
    Zoomable, pannable canvas that displays an image and draws arrow
    annotations from the margin to clicked target points.
    """
    annotation_placed = pyqtSignal(float, float, float, float)  # target_nx, target_ny, origin_nx, origin_ny
    annotation_selected = pyqtSignal(int)  # annotation id
    click_to_upload = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: Optional[QPixmap] = None
        self._zoom = 1.0
        self._pan_offset = QPointF(0, 0)
        self._panning = False
        self._pan_start = QPointF()
        self._annotations: List[ArrowAnnotation] = []
        self._annotation_mode = False
        self._selected_id: Optional[int] = None
        self._hover_id: Optional[int] = None
        # Two-click annotation state
        self._pending_target: Optional[Tuple[float, float]] = None  # first click (arrow tip)
        self._mouse_pos: Optional[QPointF] = None  # for live preview line
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(400, 300)
        self.setStyleSheet("background-color: #ffffff;")

    # ---- public API ----

    def set_image(self, pixmap: QPixmap):
        self._pixmap = pixmap
        self._zoom = 1.0
        self._pan_offset = QPointF(0, 0)
        self._fit_image()
        self.update()

    def clear_image(self):
        self._pixmap = None
        self._annotations.clear()
        self._zoom = 1.0
        self._pan_offset = QPointF(0, 0)
        self.update()

    def set_annotation_mode(self, enabled: bool):
        self._annotation_mode = enabled
        self._pending_target = None  # reset two-click state
        self._mouse_pos = None
        self.setCursor(Qt.CrossCursor if enabled else Qt.ArrowCursor)
        self.update()

    def set_annotations(self, annotations: List[ArrowAnnotation]):
        self._annotations = annotations
        self.update()

    def set_selected(self, ann_id: Optional[int]):
        self._selected_id = ann_id
        self.update()

    def set_hover_id(self, ann_id: Optional[int]):
        """Set hovered annotation (e.g. when hovering over panel card)."""
        if self._hover_id != ann_id:
            self._hover_id = ann_id
            self.update()

    def has_image(self) -> bool:
        return self._pixmap is not None and not self._pixmap.isNull()

    # ---- coordinate helpers ----

    def _image_rect(self) -> QRectF:
        """Compute the on-screen rectangle of the image."""
        if not self._pixmap:
            return QRectF()
        iw, ih = self._pixmap.width(), self._pixmap.height()
        scaled_w = iw * self._zoom
        scaled_h = ih * self._zoom
        x = (self.width() - scaled_w) / 2 + self._pan_offset.x()
        y = (self.height() - scaled_h) / 2 + self._pan_offset.y()
        return QRectF(x, y, scaled_w, scaled_h)

    def _widget_to_normalised(self, pos: QPointF) -> Optional[Tuple[float, float]]:
        """Convert widget coords to normalised 0-1 image coords (clamped to image)."""
        rect = self._image_rect()
        if rect.width() == 0 or rect.height() == 0:
            return None
        nx = (pos.x() - rect.x()) / rect.width()
        ny = (pos.y() - rect.y()) / rect.height()
        if 0 <= nx <= 1 and 0 <= ny <= 1:
            return (nx, ny)
        return None

    def _widget_to_normalised_unclamped(self, pos: QPointF) -> Optional[Tuple[float, float]]:
        """Convert widget coords to normalised image coords (allows outside 0-1)."""
        rect = self._image_rect()
        if rect.width() == 0 or rect.height() == 0:
            return None
        nx = (pos.x() - rect.x()) / rect.width()
        ny = (pos.y() - rect.y()) / rect.height()
        return (nx, ny)

    def _normalised_to_widget(self, nx: float, ny: float) -> QPointF:
        rect = self._image_rect()
        return QPointF(rect.x() + nx * rect.width(), rect.y() + ny * rect.height())

    def _fit_image(self):
        if not self._pixmap:
            return
        iw, ih = self._pixmap.width(), self._pixmap.height()
        if iw == 0 or ih == 0:
            return
        margin = 60  # px margin on each side for callout arrows
        avail_w = max(self.width() - margin * 2, 100)
        avail_h = max(self.height() - margin * 2, 100)
        self._zoom = min(avail_w / iw, avail_h / ih)
        self._pan_offset = QPointF(0, 0)

    # ---- determine margin side ----

    @staticmethod
    def _best_margin_side(nx: float, ny: float) -> str:
        """Pick the margin side that's furthest from the target point."""
        distances = {
            "left": nx,
            "right": 1.0 - nx,
            "top": ny,
            "bottom": 1.0 - ny,
        }
        return max(distances, key=distances.get)

    # ---- painting ----

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Always fill background white
        painter.fillRect(self.rect(), QColor("#ffffff"))

        if not self._pixmap:
            self._draw_drop_zone(painter)
            painter.end()
            return

        # Draw image
        rect = self._image_rect()
        painter.drawPixmap(rect.toRect(), self._pixmap)

        # Draw arrows
        for i, ann in enumerate(self._annotations):
            self._draw_arrow(painter, ann, i + 1, rect)

        # Draw preview line from pending target to mouse cursor (two-click mode)
        if self._pending_target and self._mouse_pos and self._annotation_mode:
            target_widget = self._normalised_to_widget(self._pending_target[0], self._pending_target[1])
            pen = QPen(QColor(ARROW_COLOR), 1.5, Qt.DashLine)
            painter.setPen(pen)
            painter.drawLine(target_widget, self._mouse_pos)
            # Draw small dot at target
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(ARROW_COLOR)))
            painter.drawEllipse(target_widget, 4, 4)

        painter.end()

    def _draw_drop_zone(self, painter: QPainter):
        """Draw upload prompt when no image is loaded — white area, black text, dashed border."""
        _ink = "#111827"
        margin = 40
        r = self.rect().adjusted(margin, margin, -margin, -margin)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor("#94a3b8"), 2, Qt.DashLine))
        painter.drawRoundedRect(r, 12, 12)

        font_primary = make_font(pixel_size=18, bold=True)
        primary_height = QFontMetrics(font_primary).height()
        font_helper = make_font(pixel_size=12, bold=True)
        helper_height = QFontMetrics(font_helper).height()
        spacing = 12
        block_height = primary_height + spacing + helper_height
        start_y = r.top() + (r.height() - block_height) // 2
        primary_rect = QRectF(r.left(), start_y, r.width(), primary_height)
        helper_rect = QRectF(r.left(), start_y + primary_height + spacing, r.width(), helper_height)
        painter.setFont(font_primary)
        painter.setPen(QColor(_ink))
        painter.drawText(primary_rect, Qt.AlignCenter, t("technical.upload_prompt"))
        painter.setFont(font_helper)
        painter.setPen(QColor(_ink))
        painter.drawText(helper_rect, Qt.AlignCenter, t("technical.upload_formats"))

    @staticmethod
    def _effective_color(ann: ArrowAnnotation) -> str:
        """Resolve the color an arrow/badge should actually render with.

        Outside LYNS Lite this is unchanged: the annotation's own color
        (validated green, a picked color, or the ARROW_COLOR default).
        In Lite, an annotation still at the untouched default falls back
        to the read/unread pair (see ArrowAnnotation.is_read) instead of
        plain black, so a supplier can tell at a glance which of the PM's
        existing points they've already opened — same green/blue split
        ui/annotation_panel.py uses for 3D pins in reader mode."""
        from core.edition import is_lite
        if is_lite() and (not ann.color or ann.color == ARROW_COLOR):
            from ui.annotation_panel import READER_READ_COLOR, READER_UNREAD_COLOR
            return READER_READ_COLOR if ann.is_read else READER_UNREAD_COLOR
        return ann.color if ann.color else ARROW_COLOR

    def _draw_arrow(self, painter: QPainter, ann: ArrowAnnotation, number: int, img_rect: QRectF):
        """Draw a callout arrow from the origin (badge) to the annotation target (tip)."""
        target = self._normalised_to_widget(ann.target_x, ann.target_y)
        is_selected = ann.id == self._selected_id
        is_hovered = ann.id == self._hover_id

        # Use stored origin coordinates
        origin = self._normalised_to_widget(ann.origin_x, ann.origin_y)

        # Use per-annotation color — in LYNS Lite, an annotation that never
        # got an explicit color (still at the ARROW_COLOR default) falls
        # back to the read/unread pair instead, same priority order as
        # ui/annotation_panel.py's AnnotationCard._get_indicator_color: an
        # explicit/validated color always wins, read/unread only fills in
        # for ones that never got one.
        base_color = QColor(self._effective_color(ann))
        if is_selected:
            color = QColor(ARROW_SELECTED_COLOR)
        elif is_hovered:
            color = base_color.lighter(120)
        else:
            color = base_color

        # Thicker line on hover or selected
        line_width = 5.0 if is_hovered else (3.5 if is_selected else 2.0)
        pen = QPen(color, line_width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(origin, target)

        # Rounded cap at target = clean bullet that scales with line width
        self._draw_arrow_end(painter, target, color, line_width)

        # Draw numbered badge at origin
        badge_size = ARROW_BADGE_SIZE
        badge_rect = QRectF(origin.x() - badge_size / 2, origin.y() - badge_size / 2, badge_size, badge_size)
        painter.setPen(Qt.NoPen)
        badge_color = QColor(self._effective_color(ann)) if not is_selected else QColor(ARROW_SELECTED_COLOR)
        painter.setBrush(QBrush(badge_color))
        painter.drawEllipse(badge_rect)

        painter.setPen(QColor(ARROW_BADGE_TEXT))
        font = make_font(pixel_size=ARROW_BADGE_FONT_PX, bold=True)
        painter.setFont(font)
        painter.drawText(badge_rect, Qt.AlignCenter, str(number))

    def _draw_arrow_end(self, painter: QPainter, target: QPointF, color: QColor, line_width: float):
        """Draw a filled circle at the arrow endpoint. Clean bullet shape that scales with line width."""
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(color))
        r = line_width * 1.2  # Slightly larger than half-width for a clear dot
        painter.drawEllipse(target, r, r)

    # ---- interaction ----

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.RightButton or (event.button() == Qt.LeftButton and event.modifiers() & Qt.AltModifier):
            self._panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            return

        if event.button() == Qt.LeftButton:
            if not self._pixmap:
                self.click_to_upload.emit()
                return

            if self._annotation_mode:
                if self._pending_target is None:
                    # First click: target (arrow tip) — must be inside image
                    norm = self._widget_to_normalised(QPointF(event.pos()))
                    if norm:
                        self._pending_target = norm
                        self._mouse_pos = QPointF(event.pos())
                        self.update()
                else:
                    # Second click: origin (badge) — allowed outside image
                    norm = self._widget_to_normalised_unclamped(QPointF(event.pos()))
                    if norm:
                        self.annotation_placed.emit(
                            self._pending_target[0], self._pending_target[1],
                            norm[0], norm[1]
                        )
                        self._pending_target = None
                        self._mouse_pos = None
                return

            # Check if clicking on an annotation badge
            hit = self._hit_test(event.pos())
            if hit is not None:
                self.annotation_selected.emit(hit)
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._panning:
            delta = QPointF(event.pos()) - self._pan_start
            self._pan_offset += delta
            self._pan_start = QPointF(event.pos())
            self.update()
            return

        # Update mouse pos for preview line during two-click annotation
        if self._annotation_mode and self._pending_target is not None:
            self._mouse_pos = QPointF(event.pos())
            self.update()

        # Hover detection
        hit = self._hit_test(event.pos())
        if hit != self._hover_id:
            self._hover_id = hit
            self.update()

        super().mouseMoveEvent(event)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._panning:
            self._panning = False
            self.setCursor(Qt.CrossCursor if self._annotation_mode else Qt.ArrowCursor)
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        if not self._pixmap:
            return
        factor = 1.1 if event.angleDelta().y() > 0 else 0.9
        self._zoom = max(0.1, min(self._zoom * factor, 10.0))
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._pixmap and self._zoom == 1.0:
            self._fit_image()
            self.update()

    def _hit_test(self, pos) -> Optional[int]:
        """Check if pos hits an annotation badge or arrow line. Returns annotation id or None."""
        if not self._pixmap:
            return None
        p = QPointF(pos.x(), pos.y())
        for ann in self._annotations:
            target = self._normalised_to_widget(ann.target_x, ann.target_y)
            origin = self._normalised_to_widget(ann.origin_x, ann.origin_y)
            # Hit badge
            if (p - origin).manhattanLength() < 16:
                return ann.id
            # Hit line (distance from point to line segment)
            if self._point_line_distance(p, origin, target) < 6:
                return ann.id
        return None

    @staticmethod
    def _point_line_distance(p: QPointF, a: QPointF, b: QPointF) -> float:
        """Distance from point p to line segment a-b."""
        import math
        dx, dy = b.x() - a.x(), b.y() - a.y()
        len_sq = dx * dx + dy * dy
        if len_sq == 0:
            return math.hypot(p.x() - a.x(), p.y() - a.y())
        t = max(0, min(1, ((p.x() - a.x()) * dx + (p.y() - a.y()) * dy) / len_sq))
        proj_x = a.x() + t * dx
        proj_y = a.y() + t * dy
        return math.hypot(p.x() - proj_x, p.y() - proj_y)

    # ---- drag-drop ----

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if len(urls) == 1:
                path = urls[0].toLocalFile().lower()
                if path.endswith(('.png', '.jpg', '.jpeg', '.bmp', '.pdf')):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            path = event.mimeData().urls()[0].toLocalFile()
            self.click_to_upload.emit()  # will be handled by parent with path


class TechnicalAnnotationPanel(QWidget):
    """
    Right-side panel listing arrow annotations for the Technical Overview.
    Each annotation has a number, optional comment, color picker, and delete button.
    Clicking a card opens the AnnotationPopup for text/image editing.
    """
    annotation_deleted = pyqtSignal(int)
    annotation_selected = pyqtSignal(int)
    annotation_comment_changed = pyqtSignal(int, str)
    annotation_color_changed = pyqtSignal(int, str)  # id, hex color
    annotation_hovered = pyqtSignal(object)  # ann_id or None when hovering over card
    open_popup_requested = pyqtSignal(int)  # annotation id
    exit_mode = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # Windows renders the card's fonts/buttons a bit wider than macOS, which
        # was squeezing the delete (✕) button off the right edge of the fixed-
        # width panel (no horizontal scrollbar to reveal it). Give Windows a
        # little extra width so the full card — including the delete cross —
        # stays visible.
        self.setFixedWidth(344 if IS_WINDOWS else 320)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.setObjectName("technicalAnnotationPanel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            QWidget#technicalAnnotationPanel {{
                background-color: {default_theme.background};
                border-left: 1px solid {default_theme.border_light};
            }}
        """)
        self._palette_popup = None
        self._cards: List[QFrame] = []
        self._annotations: List[ArrowAnnotation] = []
        self._init_ui()

    def _show_color_palette(self, anchor: QPushButton, ann_id: int, current_color: str):
        if self._palette_popup is not None:
            try:
                self._palette_popup.close()
            except Exception:
                pass
            self._palette_popup = None

        from ui.draw_color_picker import DrawColorPicker
        picker = DrawColorPicker(self)

        def _apply_color(color: str):
            self.annotation_color_changed.emit(ann_id, color)
            picker.close()

        picker.color_selected.connect(_apply_color)
        picker.destroyed.connect(lambda *_: setattr(self, "_palette_popup", None))
        self._palette_popup = picker

        pos = anchor.mapToGlobal(QPoint(0, anchor.height()))
        picker.move(pos + QPoint(-6, 8))
        picker.show()

    def _init_ui(self):
        from ui.annotation_panel import (
            _ANNO_LEATHER_TOP, _ANNO_LEATHER_UPPER, _ANNO_LEATHER_MID,
            _ANNO_LEATHER_DEEP, _ANNO_LEATHER_BOTTOM,
        )
        from ui.annotation_icon import get_annotation_icon_pixmap

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ---- Leather-style annotation mode header banner ----
        header = QFrame()
        header.setObjectName("technicalAnnoBanner")
        header.setAttribute(Qt.WA_StyledBackground, True)
        header.setStyleSheet(f"""
            QFrame#technicalAnnoBanner {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {_ANNO_LEATHER_TOP},
                    stop:0.12 {_ANNO_LEATHER_UPPER},
                    stop:0.38 {_ANNO_LEATHER_MID},
                    stop:0.72 {_ANNO_LEATHER_DEEP},
                    stop:1 {_ANNO_LEATHER_BOTTOM});
                border-top: 1px solid rgba(255, 255, 255, 0.52);
                border-left: 1px solid rgba(255, 255, 255, 0.42);
                border-right: 1px solid rgba(255, 255, 255, 0.38);
                border-bottom: 1px solid rgba(255, 255, 255, 0.32);
                border-radius: 14px;
            }}
        """)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 10, 16, 10)
        header_layout.setSpacing(0)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(2, 0, 0, 0)
        title_row.setSpacing(10)
        anno_icon = QLabel()
        pix = get_annotation_icon_pixmap(22)
        if not pix.isNull():
            anno_icon.setPixmap(pix)
        else:
            anno_icon.setText("📝")
        anno_icon.setFixedSize(22, 22)
        anno_icon.setAlignment(Qt.AlignCenter)
        anno_icon.setStyleSheet("background: transparent; border: none;")
        title_row.addWidget(anno_icon)

        title_label = QLabel("Annotation mode")
        title_label.setFont(make_font(size=15, bold=True))
        title_label.setStyleSheet("color: #FFFFFF; background: transparent; border: none;")
        title_row.addWidget(title_label)
        title_row.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent; border: none;
                color: rgba(255, 255, 255, 0.92);
                font-size: 16px; font-weight: bold;
                padding: 0; min-width: 28px; min-height: 28px;
            }
            QPushButton:hover {
                color: #FFFFFF;
                background-color: rgba(0, 0, 0, 0.18);
                border-radius: 14px;
            }
        """)
        close_btn.clicked.connect(lambda: self.exit_mode.emit())
        title_row.addWidget(close_btn)
        header_layout.addLayout(title_row)

        divider = QFrame()
        divider.setObjectName("technicalAnnoDivider")
        divider.setFrameShape(QFrame.NoFrame)
        divider.setMinimumHeight(3)
        divider.setMaximumHeight(3)
        divider.setStyleSheet("""
            QFrame#technicalAnnoDivider {
                border: none;
                border-top: 1px dashed rgba(255, 255, 255, 0.55);
                margin-top: 8px; margin-bottom: 8px;
                background: transparent;
            }
        """)
        header_layout.addWidget(divider)

        instructions = QLabel("Click on the image to place arrows.\nEach annotation is shown in this panel.")
        instructions.setWordWrap(True)
        instructions.setStyleSheet(
            "color: rgba(255, 255, 255, 0.95); font-size: 11px; background: transparent; border: none;"
        )
        header_layout.addWidget(instructions)

        layout.addWidget(header)

        # ---- Scroll area for cards ----
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._scroll_widget = QWidget()
        self._scroll_widget.setStyleSheet("background: transparent;")
        self._scroll_layout = QVBoxLayout(self._scroll_widget)
        self._scroll_layout.setContentsMargins(0, 0, 0, 0)
        self._scroll_layout.setSpacing(8)
        self._scroll_layout.addStretch()
        self._scroll.setWidget(self._scroll_widget)
        layout.addWidget(self._scroll, 1)

        # ---- Clear All button (matches 3D viewer) ----
        btn_frame = QFrame()
        btn_frame.setAttribute(Qt.WA_StyledBackground, True)
        btn_frame.setStyleSheet(f"background-color: {default_theme.background};")
        btn_layout = QHBoxLayout(btn_frame)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(8)

        clear_btn = QPushButton("Clear All")
        clear_btn.setFixedHeight(32)
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {default_theme.row_bg_standard};
                border: 1px solid {default_theme.border_light};
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
                color: {default_theme.text_primary};
            }}
            QPushButton:hover {{
                background-color: {default_theme.row_bg_hover};
            }}
        """)
        clear_btn.clicked.connect(self._on_clear_all)
        btn_layout.addWidget(clear_btn)
        btn_layout.addStretch()
        layout.addWidget(btn_frame)

    def eventFilter(self, obj, event):
        """Forward card hover to canvas so arrow gets thicker when hovering over panel card."""
        if event.type() == QEvent.Enter:
            aid = obj.property("ann_id")
            if aid is not None:
                self.annotation_hovered.emit(aid)
        elif event.type() == QEvent.Leave:
            # Don't clear when moving to a child (e.g. color button) - still "in" the card
            rw = event.relatedWidget() if hasattr(event, "relatedWidget") else None
            if not (rw and obj.isAncestorOf(rw)):
                self.annotation_hovered.emit(None)
        return super().eventFilter(obj, event)

    def refresh(self, annotations: List[ArrowAnnotation]):
        self._annotations = annotations
        # Clear existing cards
        while self._scroll_layout.count() > 1:  # keep the stretch
            item = self._scroll_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        for i, ann in enumerate(annotations):
            card = self._create_card(ann, i + 1)
            self._scroll_layout.insertWidget(self._scroll_layout.count() - 1, card)

    def _create_card(self, ann: ArrowAnnotation, number: int) -> QFrame:
        from ui.annotation_panel import (
            _format_annotation_date, _format_annotation_time,
            _ANNO_CARD_PENDING, _ANNO_CARD_VALIDATED, _ANNO_CARD_HOVER,
            _ANNO_CARD_READER_UNREAD, _ANNO_CARD_BORDER, _ANNO_CARD_BORDER_HOVER,
            _rounded_text_pixmap, _checkmark_pixmap,
            READER_READ_COLOR, READER_UNREAD_COLOR,
        )
        from core.edition import is_lite

        VALIDATED_GREEN = '#4ade80'
        lite = is_lite()
        if lite:
            # A supplier is viewing the PM's existing points — same
            # green(unread)/blue(read) split as the 3D viewer's reader
            # mode, mirrored in ImageCanvas._effective_color for the
            # badge/arrow on the canvas itself.
            ann_color = ann.color if (ann.color and ann.color != ARROW_COLOR) else (
                READER_READ_COLOR if ann.is_read else READER_UNREAD_COLOR
            )
            card_bg = _ANNO_CARD_VALIDATED if ann.is_read else _ANNO_CARD_READER_UNREAD
        else:
            ann_color = VALIDATED_GREEN if ann.is_validated else (ann.color or ARROW_COLOR)
            card_bg = _ANNO_CARD_VALIDATED if ann.is_validated else _ANNO_CARD_PENDING

        card = QFrame()
        card.setObjectName("technicalAnnoCard")
        card.setAttribute(Qt.WA_StyledBackground, True)
        card.setProperty("ann_id", ann.id)
        card.installEventFilter(self)
        card.setStyleSheet(f"""
            QFrame#technicalAnnoCard {{
                background: {card_bg};
                {_ANNO_CARD_BORDER}
            }}
            QFrame#technicalAnnoCard:hover {{
                background: {_ANNO_CARD_HOVER};
                {_ANNO_CARD_BORDER_HOVER}
            }}
            QFrame#technicalAnnoCard QLabel {{
                background-color: transparent;
            }}
        """)
        card.setCursor(Qt.PointingHandCursor)
        card.setMinimumHeight(64)

        layout = QHBoxLayout(card)
        # Slightly tighter margins/spacing on Windows to leave room for the
        # wider native font/button rendering (see the panel width note above).
        if IS_WINDOWS:
            layout.setContentsMargins(8, 8, 6, 8)
            layout.setSpacing(6)
        else:
            layout.setContentsMargins(10, 8, 10, 8)
            layout.setSpacing(8)

        # Color swatch (change arrow color)
        color_btn = QPushButton()
        color_btn.setFixedSize(18, 18)
        color_btn.setCursor(Qt.PointingHandCursor)
        color_btn.setToolTip("Change arrow color")
        color_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {ann_color};
                border: 2px solid rgba(255,255,255,0.35);
                border-radius: 9px;
            }}
            QPushButton:hover {{ border: 2px solid rgba(255,255,255,0.7); }}
        """ + TOOLTIP_STYLE)

        color_btn.clicked.connect(lambda checked=False, aid=ann.id, btn=color_btn, color=ann_color: self._show_color_palette(btn, aid, color))
        layout.addWidget(color_btn)

        # Rounded number badge (matches 3D annotation card)
        badge = QLabel()
        badge.setPixmap(_rounded_text_pixmap(str(number), fill_color=ann_color))
        badge.setFixedSize(28, 28)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet("background-color: transparent;")
        layout.addWidget(badge)

        # Title + description
        info = QVBoxLayout()
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(2)

        title = QLabel(ann.label or "Point")
        title.setFont(make_font(size=14, bold=True))
        title.setStyleSheet(f"color: {default_theme.text_primary}; background-color: transparent; border: none;")
        info.addWidget(title)

        # Note: when there's no text yet, leave this preview blank rather than
        # falling back to "Click to edit" — the status row right below already
        # shows that same "Click to edit" message, so filling this in too made
        # the card show the sentence twice.
        desc_text = (ann.text[:60] + "…") if len(ann.text) > 60 else ann.text
        desc = QLabel(desc_text)
        desc.setStyleSheet(f"font-size: 13px; color: {default_theme.text_secondary}; background-color: transparent; border: none;")
        desc.setWordWrap(True)
        desc.setVisible(bool(desc_text))
        info.addWidget(desc)

        # Status row — green checkmark when validated, grey pending otherwise
        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 2, 0, 0)
        status_row.setSpacing(4)
        status_icon = QLabel()
        status_lbl = QLabel()
        if lite:
            # Reader-mode read/unread status — matches AnnotationCard._update_style
            # in ui/annotation_panel.py (same status_secondary color for both
            # states, checkmark only once read).
            status_color = default_theme.text_secondary
            if ann.is_read:
                status_icon.setPixmap(_checkmark_pixmap(11, status_color))
                status_icon.setVisible(True)
                status_lbl.setText(t("annotation.read"))
            else:
                status_icon.setVisible(False)
                status_lbl.setText(t("annotation.unread"))
            status_lbl.setStyleSheet(f"color: {status_color}; font-size: 13px; background: transparent; border: none;")
        elif ann.is_validated:
            status_icon.setPixmap(_checkmark_pixmap(11, VALIDATED_GREEN))
            status_icon.setVisible(True)
            status_lbl.setText(t("annotation.validated"))
            status_lbl.setStyleSheet(f"color: {VALIDATED_GREEN}; font-size: 13px; background: transparent; border: none;")
        else:
            status_icon.setVisible(False)
            status_lbl.setText(t("annotation.click_to_edit"))
            status_lbl.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 13px; background: transparent; border: none;")
        status_row.addWidget(status_icon)
        status_row.addWidget(status_lbl)
        status_row.addStretch()
        info.addLayout(status_row)

        layout.addLayout(info, 1)
        layout.addStretch()

        # Date and time
        if ann.created_at:
            date_text = _format_annotation_date(ann.created_at, include_time=False)
            time_text = _format_annotation_time(ann.created_at)
            date_time_text = f"{date_text}\n{time_text}"
        else:
            date_time_text = str(number)
        date_label = QLabel(date_time_text)
        date_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        date_label.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 14px; background-color: transparent; border: none;")
        layout.addWidget(date_label)

        # Delete button (transparent, matches 3D annotation card)
        del_btn = QPushButton("✕")
        del_btn.setFixedSize(28, 28)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setToolTip("Remove annotation")
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                font-size: 15px;
                font-weight: bold;
                color: {default_theme.text_secondary};
                padding: 0; min-width: 28px; min-height: 28px;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.12);
                color: #F87171;
                border-radius: 14px;
            }}
        """ + TOOLTIP_STYLE)
        del_btn.clicked.connect(lambda: self.annotation_deleted.emit(ann.id))
        layout.addWidget(del_btn)

        # Click card to open popup
        card.mousePressEvent = lambda e, aid=ann.id: self.open_popup_requested.emit(aid)

        return card

    def _on_clear_all(self):
        if self._annotations:
            if ask_yes_no_dialog(self, "Clear All Annotations",
                                 f"Delete all {len(self._annotations)} annotations?"):
                for ann in list(self._annotations):
                    self.annotation_deleted.emit(ann.id)


class TechnicalOverviewWidget(QWidget):
    """
    Full Technical Overview workspace: image canvas + annotation panel.
    Managed by the main window; the sidebar is separate (TechnicalSidebar).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._annotations: List[ArrowAnnotation] = []
        self._next_id = 1
        self._annotation_mode = False
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setStyleSheet("background-color: #ffffff;")

        # Image canvas
        self.canvas = ImageCanvas()
        self.canvas.annotation_placed.connect(self._on_annotation_placed)
        self.canvas.annotation_selected.connect(self._on_annotation_selected)
        self.canvas.click_to_upload.connect(self._upload_image)
        self.canvas.setAcceptDrops(True)
        layout.addWidget(self.canvas, 1)

        # Annotation panel (right side, hidden until annotation mode)
        self.annotation_panel = TechnicalAnnotationPanel()
        self.annotation_panel.annotation_deleted.connect(self._on_delete_annotation)
        self.annotation_panel.annotation_selected.connect(self._on_annotation_selected)
        self.annotation_panel.annotation_color_changed.connect(self._on_color_changed)
        self.annotation_panel.annotation_hovered.connect(self.canvas.set_hover_id)
        self.annotation_panel.open_popup_requested.connect(self._on_open_popup)
        self.annotation_panel.exit_mode.connect(self.exit_annotation_mode)
        self.annotation_panel.hide()
        layout.addWidget(self.annotation_panel)

    # ---- public API ----

    def upload_image(self):
        self._upload_image()

    def load_image_from_path(self, path: str):
        """Load an image (or first page of PDF) from a file path."""
        self._document_path = path  # remember for export
        if path.lower().endswith('.pdf'):
            pixmap = self._load_pdf_first_page(path)
        else:
            pixmap = QPixmap(path)

        if pixmap and not pixmap.isNull():
            self.canvas.set_image(pixmap)
            self._annotations.clear()
            self._next_id = 1
            self.annotation_panel.refresh(self._annotations)
            logger.info(f"TechnicalOverview: Loaded image {path}")
        else:
            show_message_dialog(self, "Load Error", f"Could not load image:\n{path}")

    def enter_annotation_mode(self):
        self._annotation_mode = True
        self.canvas.set_annotation_mode(True)
        self.annotation_panel.show()

    def exit_annotation_mode(self):
        self._annotation_mode = False
        self.canvas.set_annotation_mode(False)
        self.annotation_panel.hide()

    def get_annotations(self) -> List[ArrowAnnotation]:
        return list(self._annotations)

    def get_annotations_data(self) -> List[dict]:
        """Serialize annotations to plain dicts for .ecto export."""
        result = []
        for ann in self._annotations:
            result.append({
                'id': ann.id,
                'target_x': ann.target_x,
                'target_y': ann.target_y,
                'origin_x': ann.origin_x,
                'origin_y': ann.origin_y,
                'text': ann.text,
                'margin_side': ann.margin_side,
                'color': ann.color,
                'image_paths': list(ann.image_paths),
                'label': ann.label,
                'created_at': ann.created_at.isoformat() if ann.created_at else None,
                'is_validated': ann.is_validated,
                'added_by': ann.added_by,
                'supplier_notes': ann.supplier_notes,
                'pm_notes': ann.pm_notes,
            })
        return result

    def load_from_ecto(self, doc_path: str, annotations_data: List[dict],
                       passcode_hash: str = None):
        """Restore state from an imported .ecto technical overview bundle."""
        self.load_image_from_path(doc_path)
        self._annotations.clear()
        self._next_id = 1
        for ad in annotations_data:
            created = None
            if ad.get('created_at'):
                try:
                    created = datetime.fromisoformat(ad['created_at'])
                except Exception:
                    pass
            ann = ArrowAnnotation(
                id=ad['id'],
                target_x=ad['target_x'],
                target_y=ad['target_y'],
                origin_x=ad.get('origin_x', 0.0),
                origin_y=ad.get('origin_y', 0.0),
                text=ad.get('text', ''),
                margin_side=ad.get('margin_side', 'left'),
                color=ad.get('color', ARROW_COLOR),
                image_paths=ad.get('image_paths', []),
                label=ad.get('label', 'Point'),
                created_at=created,
                is_validated=ad.get('is_validated', False),
                added_by=ad.get('added_by'),
                supplier_notes=ad.get('supplier_notes', []),
                pm_notes=ad.get('pm_notes', []),
            )
            self._annotations.append(ann)
            self._next_id = max(self._next_id, ann.id + 1)
        self.canvas.set_annotations(self._annotations)
        self.annotation_panel.refresh(self._annotations)
        self._passcode_hash = passcode_hash
        self._reader_mode = bool(passcode_hash)

    def import_annotation(self, data: dict) -> ArrowAnnotation:
        """Append one arrow annotation from a supplier's returned
        .lyns.review (via ui/project_widget.py's supplier-review import
        merge flow). Mirrors ui/annotation_panel.py's AnnotationPanel.
        import_annotation: renumbers the id if it collides with one
        already present, since the supplier's id sequence started from
        the same base as this document's did at export time."""
        created = None
        if data.get('created_at'):
            try:
                created = datetime.fromisoformat(data['created_at'])
            except Exception:
                pass
        existing_ids = {a.id for a in self._annotations}
        new_id = data['id']
        if new_id in existing_ids:
            new_id = (max(existing_ids) + 1) if existing_ids else 1
            logger.info(f"TechnicalOverview.import_annotation: id {data['id']} collides with an "
                        f"existing annotation, renumbering to {new_id}")
        ann = ArrowAnnotation(
            id=new_id,
            target_x=data['target_x'],
            target_y=data['target_y'],
            origin_x=data.get('origin_x', 0.0),
            origin_y=data.get('origin_y', 0.0),
            text=data.get('text', ''),
            margin_side=data.get('margin_side', 'left'),
            color=data.get('color', ARROW_COLOR),
            image_paths=data.get('image_paths', []),
            label=data.get('label', 'Point'),
            created_at=created,
            is_validated=data.get('is_validated', False),
            added_by=data.get('added_by'),
            supplier_notes=data.get('supplier_notes', []),
            pm_notes=data.get('pm_notes', []),
        )
        self._annotations.append(ann)
        self._next_id = max(self._next_id, ann.id + 1)
        self.canvas.set_annotations(self._annotations)
        self.annotation_panel.refresh(self._annotations)
        logger.info(f"TechnicalOverview.import_annotation: merged in annotation id={ann.id}")
        return ann

    def add_supplier_notes(self, annotation_id: int, notes: list) -> bool:
        """Append supplier feedback note(s) to an EXISTING arrow's thread —
        used by the merge-import flow when a supplier commented on one of
        the PM's own annotations rather than adding a new one. Mirrors
        ui/annotation_panel.py's AnnotationPanel.add_supplier_notes.
        Returns False if the annotation no longer exists locally (e.g. the
        PM deleted it after exporting)."""
        ann = next((a for a in self._annotations if a.id == annotation_id), None)
        if ann is None:
            return False
        ann.supplier_notes.extend(notes)
        self.annotation_panel.refresh(self._annotations)
        return True

    def get_document_path(self) -> Optional[str]:
        """Return the file path of the currently loaded document image, if available."""
        return getattr(self, '_document_path', None)

    def clear_all(self):
        self._annotations.clear()
        self._next_id = 1
        self.canvas.set_annotations([])
        self.annotation_panel.refresh([])

    # ---- private ----

    def _upload_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Image or PDF", "",
            "Images & PDFs (*.png *.jpg *.jpeg *.bmp *.pdf);;All Files (*)"
        )
        if path:
            self.load_image_from_path(path)

    def _load_pdf_first_page(self, pdf_path: str) -> Optional[QPixmap]:
        """Render the first page of a PDF to a QPixmap."""
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(pdf_path)
            if len(doc) == 0:
                return None
            page = doc[0]
            # Render at 2x for quality
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
            return QPixmap.fromImage(img)
        except ImportError:
            logger.warning("PyMuPDF (fitz) not installed; PDF rendering unavailable")
            show_message_dialog(self, "PDF Support",
                                "PDF rendering requires PyMuPDF.\nInstall with: pip install PyMuPDF")
            return None
        except Exception as e:
            logger.error(f"Failed to render PDF: {e}")
            return None

    def _on_annotation_placed(self, tx: float, ty: float, ox: float, oy: float):
        from core.edition import is_lite
        ann = ArrowAnnotation(
            id=self._next_id, target_x=tx, target_y=ty,
            origin_x=ox, origin_y=oy,
            created_at=datetime.now(),
            added_by='supplier' if is_lite() else None,
        )
        self._next_id += 1
        self._annotations.append(ann)
        self.canvas.set_annotations(self._annotations)
        self.annotation_panel.refresh(self._annotations)

    def _on_annotation_selected(self, ann_id: int):
        self.canvas.set_selected(ann_id)

    def _on_color_changed(self, ann_id: int, color: str):
        """Update an annotation's arrow color."""
        logger.info(f"Color changed for annotation {ann_id}: {color}")
        updated = False
        for ann in self._annotations:
            if ann.id == ann_id:
                ann.color = color
                updated = True
                logger.info(f"Annotation {ann_id} color set to {color}")
                break
        # Also try by index in case ann_id is 0-based index
        if not updated and 0 <= ann_id < len(self._annotations):
            self._annotations[ann_id].color = color
            updated = True
            logger.info(f"Annotation at index {ann_id} color set to {color}")
        if updated:
            # Deselect so arrow shows new color (selected arrows use red)
            self.canvas.set_selected(None)
            # Ensure canvas has updated annotations and repaint
            self.canvas._annotations = self._annotations
            self.canvas.repaint()
            self.annotation_panel.refresh(self._annotations)

    def _on_open_popup(self, ann_id: int):
        """Open this arrow's popup — AnnotationPopup (editable) in 360,
        AnnotationViewerPopup (original locked, reply-only) in LYNS Lite,
        the same split ui/annotation_panel.py's AnnotationPanel makes for
        the 3D viewer's own annotations (see its _on_card_clicked)."""
        ann = next((a for a in self._annotations if a.id == ann_id), None)
        if not ann:
            return
        from datetime import datetime
        from core.edition import is_lite

        if is_lite():
            from ui.annotation_viewer_popup import AnnotationViewerPopup
            # Mark read on open, same as AnnotationPanel.mark_as_read for
            # the 3D viewer's pins — flips this arrow's badge/card from
            # unread (green) to read (blue) the moment the supplier looks
            # at it.
            if not ann.is_read:
                ann.is_read = True
                self.canvas.repaint()
                self.annotation_panel.refresh(self._annotations)
            # Same place stl_viewer.py's _on_open_viewer_popup_requested
            # reads this from — the loaded .lyns.review envelope's own
            # 'supplier', found via the top-level window since this widget
            # has no direct reference to it.
            current_supplier = None
            envelope = getattr(self.window(), '_lite_review_envelope', None)
            if envelope:
                current_supplier = envelope.get('supplier')
            display_number = self._annotations.index(ann) + 1
            popup = AnnotationViewerPopup(
                annotation_id=ann.id,
                point=(ann.target_x, ann.target_y),
                text=ann.text,
                image_paths=list(ann.image_paths),
                label=ann.label,
                created_at=ann.created_at or datetime.now(),
                display_number=display_number,
                supplier_notes=ann.supplier_notes,
                pm_notes=ann.pm_notes,
                added_by=ann.added_by,
                current_supplier=current_supplier,
                parent=self,
            )
            popup.note_added.connect(self._on_supplier_note_added)
            popup.show()
            return

        from ui.annotation_popup import AnnotationPopup
        display_number = self._annotations.index(ann) + 1
        popup = AnnotationPopup(
            annotation_id=ann.id,
            point=(ann.target_x, ann.target_y),
            text=ann.text,
            image_paths=list(ann.image_paths),
            label=ann.label,
            created_at=ann.created_at or datetime.now(),
            display_number=display_number,
            supplier_notes=ann.supplier_notes,
            pm_notes=ann.pm_notes,
            added_by=ann.added_by,
            parent=self
        )
        popup.annotation_validated.connect(self._on_popup_validated)
        popup.annotation_deleted.connect(self._on_delete_annotation)
        # Was never connected before — every follow-up comment posted in
        # the popup's conversation composer rendered fine while the popup
        # stayed open (AnnotationPopup keeps its own in-memory pm_notes)
        # but vanished the moment it closed, since nothing wrote it back
        # onto this ArrowAnnotation. Mirrors stl_viewer.py's
        # _on_annotation_pm_note_added for the 3D viewer's annotations.
        popup.note_added.connect(self._on_note_added)
        popup.show()

    def _on_note_added(self, ann_id: int, note: dict):
        """A PM's follow-up comment (360's AnnotationPopup) — persist it so
        it survives the popup closing and round-trips through export/
        import (see get_annotations_data/load_from_ecto)."""
        ann = next((a for a in self._annotations if a.id == ann_id), None)
        if ann is not None:
            ann.pm_notes.append(note)

    def _on_supplier_note_added(self, ann_id: int, note: dict):
        """A supplier's feedback (Lite's AnnotationViewerPopup) — stored
        separately from the PM's own pm_notes, same split
        ui/annotation_panel.py's Annotation makes."""
        ann = next((a for a in self._annotations if a.id == ann_id), None)
        if ann is not None:
            ann.supplier_notes.append(note)

    def _on_popup_validated(self, ann_id: int, text: str, image_paths: list, label: str):
        """Handle popup Done — save text, images, label back to the annotation and mark validated."""
        for ann in self._annotations:
            if ann.id == ann_id:
                ann.text = text
                ann.image_paths = image_paths
                ann.label = label
                ann.is_validated = True
                ann.color = '#4ade80'   # green on canvas — matches validated card
                break
        self.canvas.set_annotations(self._annotations)
        self.annotation_panel.refresh(self._annotations)

    def _on_delete_annotation(self, ann_id: int):
        self._annotations = [a for a in self._annotations if a.id != ann_id]
        self.canvas.set_annotations(self._annotations)
        self.canvas.set_selected(None)
        self.annotation_panel.refresh(self._annotations)

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
    QScrollArea, QFrame, QFileDialog, QSizePolicy, QMessageBox,
    QTextEdit, QApplication
)
from PyQt5.QtCore import Qt, QPoint, QPointF, QRectF, pyqtSignal, QEvent
from PyQt5.QtGui import (
    QPixmap, QPainter, QPen, QColor, QFont, QFontMetrics,
    QBrush, QPainterPath, QPolygonF, QImage, QWheelEvent, QMouseEvent
)
from ui.styles import default_theme

logger = logging.getLogger(__name__)

# Arrow annotation colours
ARROW_COLOR = "#5294E2"
ARROW_SELECTED_COLOR = "#E53E3E"
ARROW_BADGE_BG = "#5294E2"
ARROW_BADGE_TEXT = "#FFFFFF"


@dataclass
class ArrowAnnotation:
    """A single arrow annotation on the 2D image."""
    id: int
    target_x: float  # 0-1 normalised position on image
    target_y: float
    text: str = ""
    margin_side: str = "left"  # which margin the arrow originates from
    color: str = ARROW_COLOR  # per-annotation color
    image_paths: list = field(default_factory=list)
    label: str = "Point"
    created_at: Optional[datetime] = None


class ImageCanvas(QWidget):
    """
    Zoomable, pannable canvas that displays an image and draws arrow
    annotations from the margin to clicked target points.
    """
    annotation_placed = pyqtSignal(float, float)  # normalised x, y on image
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
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(400, 300)
        self.setStyleSheet(f"background-color: {default_theme.background};")

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
        """Convert widget coords to normalised 0-1 image coords."""
        rect = self._image_rect()
        if rect.width() == 0 or rect.height() == 0:
            return None
        nx = (pos.x() - rect.x()) / rect.width()
        ny = (pos.y() - rect.y()) / rect.height()
        if 0 <= nx <= 1 and 0 <= ny <= 1:
            return (nx, ny)
        return None

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

        painter.end()

    def _draw_drop_zone(self, painter: QPainter):
        """Draw upload prompt when no image is loaded. Match 3D viewer drop zone styles."""
        painter.setPen(QPen(QColor(default_theme.border_light), 2, Qt.DashLine))
        margin = 40
        r = self.rect().adjusted(margin, margin, -margin, -margin)
        painter.drawRoundedRect(r, 12, 12)

        # Primary text: same as 3D viewer (18px, weight 600, #1a1a2e)
        font_primary = QFont()
        font_primary.setPixelSize(18)
        font_primary.setWeight(600)
        painter.setFont(font_primary)
        painter.setPen(QColor("#1a1a2e"))
        primary_height = painter.fontMetrics().height()
        # Helper text: same as 3D viewer (11px, weight 400, #a0aec0)
        font_helper = QFont()
        font_helper.setPixelSize(11)
        font_helper.setWeight(400)
        painter.setFont(font_helper)
        helper_height = painter.fontMetrics().height()
        spacing = 12
        block_height = primary_height + spacing + helper_height
        start_y = r.top() + (r.height() - block_height) // 2
        primary_rect = QRectF(r.left(), start_y, r.width(), primary_height)
        helper_rect = QRectF(r.left(), start_y + primary_height + spacing, r.width(), helper_height)
        painter.setFont(font_primary)
        painter.setPen(QColor("#1a1a2e"))
        painter.drawText(primary_rect, Qt.AlignCenter, "Click or drag to upload")
        painter.setFont(font_helper)
        painter.setPen(QColor("#a0aec0"))
        painter.drawText(helper_rect, Qt.AlignCenter, "JPEG · PNG · PDF")

    def _draw_arrow(self, painter: QPainter, ann: ArrowAnnotation, number: int, img_rect: QRectF):
        """Draw a callout arrow from the margin to the annotation target."""
        target = self._normalised_to_widget(ann.target_x, ann.target_y)
        is_selected = ann.id == self._selected_id
        is_hovered = ann.id == self._hover_id

        # Determine origin point on margin
        margin_gap = 35  # px outside image edge
        if ann.margin_side == "left":
            origin = QPointF(img_rect.left() - margin_gap, target.y())
        elif ann.margin_side == "right":
            origin = QPointF(img_rect.right() + margin_gap, target.y())
        elif ann.margin_side == "top":
            origin = QPointF(target.x(), img_rect.top() - margin_gap)
        else:  # bottom
            origin = QPointF(target.x(), img_rect.bottom() + margin_gap)

        # Use per-annotation color
        base_color = QColor(ann.color if ann.color else ARROW_COLOR)
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

        # Rounded cap at target = clean bullet that scales with line width (no blocky triangle)
        self._draw_arrow_end(painter, target, color, line_width)

        # Draw numbered badge at origin
        badge_size = 22
        badge_rect = QRectF(origin.x() - badge_size / 2, origin.y() - badge_size / 2, badge_size, badge_size)
        painter.setPen(Qt.NoPen)
        badge_color = QColor(ann.color if ann.color else ARROW_COLOR) if not is_selected else QColor(ARROW_SELECTED_COLOR)
        painter.setBrush(QBrush(badge_color))
        painter.drawEllipse(badge_rect)

        painter.setPen(QColor(ARROW_BADGE_TEXT))
        font = QFont()
        font.setBold(True)
        font.setPointSize(9)
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
        if event.button() == Qt.MiddleButton or (event.button() == Qt.LeftButton and event.modifiers() & Qt.AltModifier):
            self._panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            return

        if event.button() == Qt.LeftButton:
            if not self._pixmap:
                self.click_to_upload.emit()
                return

            if self._annotation_mode:
                norm = self._widget_to_normalised(QPointF(event.pos()))
                if norm:
                    self.annotation_placed.emit(norm[0], norm[1])
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

        # Hover detection
        hit = self._hit_test(event.pos())
        if hit != self._hover_id:
            self._hover_id = hit
            self.update()

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
        img_rect = self._image_rect()
        margin_gap = 35
        p = QPointF(pos.x(), pos.y())
        for ann in self._annotations:
            target = self._normalised_to_widget(ann.target_x, ann.target_y)
            if ann.margin_side == "left":
                origin = QPointF(img_rect.left() - margin_gap, target.y())
            elif ann.margin_side == "right":
                origin = QPointF(img_rect.right() + margin_gap, target.y())
            elif ann.margin_side == "top":
                origin = QPointF(target.x(), img_rect.top() - margin_gap)
            else:
                origin = QPointF(target.x(), img_rect.bottom() + margin_gap)
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
        self.setFixedWidth(260)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self._cards: List[QFrame] = []
        self._annotations: List[ArrowAnnotation] = []
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header
        header = QLabel("📌 Annotations")
        header.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {default_theme.text_title};")
        layout.addWidget(header)

        hint = QLabel("Click on the image to place arrow annotations.\nClick a card to edit text & photos.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"font-size: 10px; color: {default_theme.text_secondary};")
        layout.addWidget(hint)

        # Scroll area for cards
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_widget = QWidget()
        self._scroll_layout = QVBoxLayout(self._scroll_widget)
        self._scroll_layout.setContentsMargins(0, 0, 0, 0)
        self._scroll_layout.setSpacing(4)
        self._scroll_layout.addStretch()
        self._scroll.setWidget(self._scroll_widget)
        layout.addWidget(self._scroll, 1)

        # Bottom buttons
        btn_row = QHBoxLayout()
        clear_btn = QPushButton("Clear All")
        clear_btn.setFixedHeight(28)
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #FEE2E2; border: 1px solid #FECACA;
                border-radius: 4px; padding: 4px 10px; font-size: 10px; color: #DC2626;
            }}
            QPushButton:hover {{ background-color: #FECACA; }}
        """)
        clear_btn.clicked.connect(self._on_clear_all)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()

        exit_btn = QPushButton("Exit")
        exit_btn.setFixedHeight(28)
        exit_btn.setCursor(Qt.PointingHandCursor)
        exit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {default_theme.row_bg_standard}; border: 1px solid {default_theme.border_light};
                border-radius: 4px; padding: 4px 10px; font-size: 10px; color: {default_theme.text_primary};
            }}
            QPushButton:hover {{ background-color: {default_theme.row_bg_hover}; }}
        """)
        exit_btn.clicked.connect(lambda: self.exit_mode.emit())
        btn_row.addWidget(exit_btn)
        layout.addLayout(btn_row)

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
        from PyQt5.QtWidgets import QColorDialog
        from PyQt5.QtGui import QFont
        from ui.annotation_panel import _format_annotation_date, _format_annotation_time

        card = QFrame()
        card.setProperty("ann_id", ann.id)
        card.installEventFilter(self)
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {default_theme.row_bg_standard};
                border: 1px solid {default_theme.border_light};
                border-radius: 6px;
            }}
            QFrame:hover {{
                background-color: {default_theme.row_bg_hover};
            }}
        """)
        card.setCursor(Qt.PointingHandCursor)
        card.setMinimumHeight(70)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        # Color swatch (change arrow color)
        ann_color = ann.color or ARROW_COLOR
        color_btn = QPushButton()
        color_btn.setFixedSize(20, 20)
        color_btn.setCursor(Qt.PointingHandCursor)
        color_btn.setToolTip("Change arrow color")
        color_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {ann_color};
                border: 2px solid {default_theme.border_light};
                border-radius: 10px;
            }}
            QPushButton:hover {{ border: 2px solid {default_theme.border_highlight}; }}
        """)

        def _pick_color(aid=ann.id, btn=color_btn):
            c = QColorDialog.getColor(QColor(ann_color), self, "Arrow Color")
            if c.isValid():
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {c.name()};
                        border: 2px solid {default_theme.border_light};
                        border-radius: 10px;
                    }}
                    QPushButton:hover {{ border: 2px solid {default_theme.border_highlight}; }}
                """)
                self.annotation_color_changed.emit(aid, c.name())

        color_btn.clicked.connect(_pick_color)
        layout.addWidget(color_btn)

        # Number badge
        badge = QLabel(str(number))
        badge.setFixedSize(24, 24)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(f"""
            QLabel {{
                background-color: {ann_color}; color: {ARROW_BADGE_TEXT};
                border-radius: 12px; font-weight: bold; font-size: 11px;
            }}
        """)
        layout.addWidget(badge)

        # Title and description (like 3D annotation viewer)
        info = QVBoxLayout()
        info.setSpacing(4)

        title = QLabel(ann.label or f"Annotation {number}")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(11)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {default_theme.text_primary}; border: none;")
        info.addWidget(title)

        desc_text = (ann.text[:60] + "…") if len(ann.text) > 60 else (ann.text or "No description")
        desc = QLabel(desc_text)
        desc.setStyleSheet(f"font-size: 10px; color: {default_theme.text_secondary}; border: none;")
        desc.setWordWrap(True)
        info.addWidget(desc)

        layout.addLayout(info, 1)

        # Date and time (like 3D annotation viewer)
        if ann.created_at:
            date_text = _format_annotation_date(ann.created_at, include_time=False)
            time_text = _format_annotation_time(ann.created_at)
            date_time_text = f"{date_text}\n{time_text}"
        else:
            date_time_text = str(number)
        date_label = QLabel(date_time_text)
        date_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        date_label.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 10px; border: none;")
        layout.addWidget(date_label)

        # Delete button
        del_btn = QPushButton("✕")
        del_btn.setFixedSize(26, 26)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #FEE2E2; border: none; border-radius: 13px;
                color: #DC2626; font-size: 14px; font-weight: bold;
                padding: 0; min-width: 26px; min-height: 26px;
            }}
            QPushButton:hover {{ background-color: #FECACA; }}
        """)
        del_btn.clicked.connect(lambda: self.annotation_deleted.emit(ann.id))
        layout.addWidget(del_btn, 0, Qt.AlignTop)

        # Click card to open popup (not on buttons)
        card.mousePressEvent = lambda e, aid=ann.id: self.open_popup_requested.emit(aid)

        return card

    def _on_clear_all(self):
        if self._annotations:
            reply = QMessageBox.question(
                self, "Clear All Annotations",
                f"Delete all {len(self._annotations)} annotations?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
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
            QMessageBox.warning(self, "Load Error", f"Could not load image:\n{path}")

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
                'text': ann.text,
                'margin_side': ann.margin_side,
                'color': ann.color,
                'image_paths': list(ann.image_paths),
                'label': ann.label,
                'created_at': ann.created_at.isoformat() if ann.created_at else None,
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
                text=ad.get('text', ''),
                margin_side=ad.get('margin_side', 'left'),
                color=ad.get('color', ARROW_COLOR),
                image_paths=ad.get('image_paths', []),
                label=ad.get('label', 'Point'),
                created_at=created,
            )
            self._annotations.append(ann)
            self._next_id = max(self._next_id, ann.id + 1)
        self.canvas.set_annotations(self._annotations)
        self.annotation_panel.refresh(self._annotations)
        self._passcode_hash = passcode_hash
        self._reader_mode = bool(passcode_hash)

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
            QMessageBox.warning(self, "PDF Support",
                                "PDF rendering requires PyMuPDF.\nInstall with: pip install PyMuPDF")
            return None
        except Exception as e:
            logger.error(f"Failed to render PDF: {e}")
            return None

    def _on_annotation_placed(self, nx: float, ny: float):
        side = ImageCanvas._best_margin_side(nx, ny)
        ann = ArrowAnnotation(id=self._next_id, target_x=nx, target_y=ny, margin_side=side, created_at=datetime.now())
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
        """Open the AnnotationPopup for editing text and images on this arrow."""
        ann = next((a for a in self._annotations if a.id == ann_id), None)
        if not ann:
            return
        from datetime import datetime
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
            parent=self
        )
        popup.annotation_validated.connect(self._on_popup_validated)
        popup.annotation_deleted.connect(self._on_delete_annotation)
        popup.show()

    def _on_popup_validated(self, ann_id: int, text: str, image_paths: list, label: str):
        """Handle popup Done — save text, images, label back to the annotation."""
        for ann in self._annotations:
            if ann.id == ann_id:
                ann.text = text
                ann.image_paths = image_paths
                ann.label = label
                break
        self.canvas.set_annotations(self._annotations)
        self.annotation_panel.refresh(self._annotations)

    def _on_delete_annotation(self, ann_id: int):
        self._annotations = [a for a in self._annotations if a.id != ann_id]
        self.canvas.set_annotations(self._annotations)
        self.canvas.set_selected(None)
        self.annotation_panel.refresh(self._annotations)

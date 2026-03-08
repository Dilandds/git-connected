"""
Technical Overview - 2D image viewer with arrow callout annotations.
Users can upload an image (JPEG, PNG) or PDF page, then click to place
numbered annotation arrows that auto-draw from the margin to the clicked point.
"""
import os
import logging
from dataclasses import dataclass, field
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

        # Draw line
        color = QColor(ARROW_SELECTED_COLOR if is_selected else ARROW_COLOR)
        if is_hovered and not is_selected:
            color = color.lighter(120)
        pen = QPen(color, 2.5 if is_selected else 2.0)
        painter.setPen(pen)
        painter.drawLine(origin, target)

        # Draw arrowhead at target
        self._draw_arrowhead(painter, origin, target, color, 10)

        # Draw numbered badge at origin
        badge_size = 22
        badge_rect = QRectF(origin.x() - badge_size / 2, origin.y() - badge_size / 2, badge_size, badge_size)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawEllipse(badge_rect)

        painter.setPen(QColor(ARROW_BADGE_TEXT))
        font = QFont()
        font.setBold(True)
        font.setPointSize(9)
        painter.setFont(font)
        painter.drawText(badge_rect, Qt.AlignCenter, str(number))

    def _draw_arrowhead(self, painter: QPainter, origin: QPointF, target: QPointF, color: QColor, size: float):
        """Draw a filled arrowhead at the target pointing away from origin."""
        import math
        dx = target.x() - origin.x()
        dy = target.y() - origin.y()
        angle = math.atan2(dy, dx)
        spread = math.radians(25)

        p1 = QPointF(
            target.x() - size * math.cos(angle - spread),
            target.y() - size * math.sin(angle - spread)
        )
        p2 = QPointF(
            target.x() - size * math.cos(angle + spread),
            target.y() - size * math.sin(angle + spread)
        )

        path = QPainterPath()
        path.moveTo(target)
        path.lineTo(p1)
        path.lineTo(p2)
        path.closeSubpath()

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawPath(path)

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
        """Check if pos hits an annotation badge. Returns annotation id or None."""
        if not self._pixmap:
            return None
        img_rect = self._image_rect()
        margin_gap = 35
        for ann in self._annotations:
            if ann.margin_side == "left":
                origin = QPointF(img_rect.left() - margin_gap,
                                 self._normalised_to_widget(ann.target_x, ann.target_y).y())
            elif ann.margin_side == "right":
                origin = QPointF(img_rect.right() + margin_gap,
                                 self._normalised_to_widget(ann.target_x, ann.target_y).y())
            elif ann.margin_side == "top":
                origin = QPointF(self._normalised_to_widget(ann.target_x, ann.target_y).x(),
                                 img_rect.top() - margin_gap)
            else:
                origin = QPointF(self._normalised_to_widget(ann.target_x, ann.target_y).x(),
                                 img_rect.bottom() + margin_gap)
            if (QPointF(pos.x(), pos.y()) - origin).manhattanLength() < 16:
                return ann.id
        return None

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
    Each annotation has a number, optional comment, and delete button.
    """
    annotation_deleted = pyqtSignal(int)
    annotation_selected = pyqtSignal(int)
    annotation_comment_changed = pyqtSignal(int, str)
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

        hint = QLabel("Click on the image to place arrow annotations")
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
        card = QFrame()
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
        card.setFixedHeight(70)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        # Number badge
        badge = QLabel(str(number))
        badge.setFixedSize(24, 24)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(f"""
            QLabel {{
                background-color: {ARROW_BADGE_BG}; color: {ARROW_BADGE_TEXT};
                border-radius: 12px; font-weight: bold; font-size: 11px;
            }}
        """)
        layout.addWidget(badge)

        # Text area
        info = QVBoxLayout()
        info.setSpacing(2)
        label = QLabel(ann.text or f"Annotation {number}")
        label.setStyleSheet(f"font-size: 11px; color: {default_theme.text_primary}; border: none;")
        label.setWordWrap(True)
        info.addWidget(label)

        coord_text = f"({ann.target_x:.2f}, {ann.target_y:.2f})"
        coord = QLabel(coord_text)
        coord.setStyleSheet(f"font-size: 9px; color: {default_theme.text_secondary}; border: none;")
        info.addWidget(coord)
        layout.addLayout(info, 1)

        # Delete button
        del_btn = QPushButton("✕")
        del_btn.setFixedSize(20, 20)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #FEE2E2; border: none; border-radius: 10px;
                color: #DC2626; font-size: 11px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #FECACA; }}
        """)
        del_btn.clicked.connect(lambda: self.annotation_deleted.emit(ann.id))
        layout.addWidget(del_btn, 0, Qt.AlignTop)

        # Click to select
        card.mousePressEvent = lambda e, aid=ann.id: self.annotation_selected.emit(aid)

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
        self.annotation_panel.exit_mode.connect(self.exit_annotation_mode)
        self.annotation_panel.hide()
        layout.addWidget(self.annotation_panel)

    # ---- public API ----

    def upload_image(self):
        self._upload_image()

    def load_image_from_path(self, path: str):
        """Load an image (or first page of PDF) from a file path."""
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
        ann = ArrowAnnotation(id=self._next_id, target_x=nx, target_y=ny, margin_side=side)
        self._next_id += 1
        self._annotations.append(ann)
        self.canvas.set_annotations(self._annotations)
        self.annotation_panel.refresh(self._annotations)

    def _on_annotation_selected(self, ann_id: int):
        self.canvas.set_selected(ann_id)

    def _on_delete_annotation(self, ann_id: int):
        self._annotations = [a for a in self._annotations if a.id != ann_id]
        self.canvas.set_annotations(self._annotations)
        self.canvas.set_selected(None)
        self.annotation_panel.refresh(self._annotations)

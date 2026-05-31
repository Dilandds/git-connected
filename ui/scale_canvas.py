"""
Scale Canvas — zoomable/pannable canvas with graduated ruler frame for
drawing scale calibration. Users load a technical drawing (PDF/JPG/PNG),
resize it proportionally until a known reference dimension matches the
graduated frame, then use the ruler tool for real-world measurements.
"""
import os
import logging
import math
from typing import Optional, List, Tuple
from dataclasses import dataclass, field

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy, QApplication,
    QFileDialog, QLabel, QInputDialog
)
from PyQt5.QtCore import Qt, QPointF, QRectF, pyqtSignal, QPoint
from PyQt5.QtGui import (
    QPainter, QPixmap, QColor, QPen, QFont, QFontMetrics,
    QDragEnterEvent, QDropEvent, QWheelEvent, QMouseEvent, QPaintEvent,
    QImage, QPolygonF,
)

from ui.styles import default_theme

logger = logging.getLogger(__name__)

# Ruler area in pixels on each edge
RULER_THICKNESS = 40

# Supported image extensions
_IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff'}
_PDF_EXTS = {'.pdf'}

# Reference line hit tolerance
_REF_HIT_TOLERANCE = 10


@dataclass
class Measurement:
    """A point-to-point measurement on the canvas."""
    id: int
    x1: float  # normalised image coords
    y1: float
    x2: float
    y2: float
    distance_real: float = 0.0  # real-world distance in current unit


@dataclass
class ExtraRefLine:
    """A user-placed reference line that can be dragged anywhere."""
    id: int
    pos: QPointF  # absolute screen position (top-left of the line)


@dataclass
class DrawingArrow:
    """An arrow shape on the canvas."""
    id: int
    x1: float  # start point in screen coords
    y1: float
    x2: float  # end point in screen coords
    y2: float
    color: QColor = field(default_factory=lambda: QColor("#000000"))
    
    def get_dimensions(self) -> dict:
        """Return dimensions dict with length."""
        dist = ((self.x2 - self.x1) ** 2 + (self.y2 - self.y1) ** 2) ** 0.5
        import math
        angle = math.degrees(math.atan2(self.y2 - self.y1, self.x2 - self.x1))
        return {"length": dist, "angle": angle}


@dataclass
class DrawingRectangle:
    """A rectangle shape on the canvas."""
    id: int
    x: float  # top-left in screen coords
    y: float
    width: float
    height: float
    color: QColor = field(default_factory=lambda: QColor("#000000"))
    angle: float = 0.0
    
    def get_dimensions(self) -> dict:
        """Return dimensions dict with width and height."""
        return {"width": abs(self.width), "height": abs(self.height)}


@dataclass
class DrawingCircle:
    """A circle shape on the canvas."""
    id: int
    cx: float  # center in screen coords
    cy: float
    radius: float
    color: QColor = field(default_factory=lambda: QColor("#000000"))
    angle: float = 0.0
    
    def get_dimensions(self) -> dict:
        """Return dimensions dict with radius and diameter."""
        return {"radius": abs(self.radius), "diameter": abs(self.radius * 2)}


@dataclass
class DrawingText:
    """A text annotation on the canvas."""
    id: int
    x: float
    y: float
    text: str
    color: QColor = field(default_factory=lambda: QColor("#000000"))


class ScaleCanvas(QWidget):
    """
    Canvas with graduated ruler border, zoomable/pannable drawing display,
    and integrated measurement tool.
    """
    file_loaded = pyqtSignal(str)  # emitted when a file is loaded
    click_to_upload = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: Optional[QPixmap] = None
        self._source_path: Optional[str] = None  # original file path
        self._zoom = 1.0
        self._pan_offset = QPointF(0, 0)
        self._panning = False
        self._pan_start = QPointF()

        # Drawing scale
        self._unit = "cm"  # cm | mm | inches | m
        self._scale_ratio = 1.0  # 1:1 → 1.0, 1:2 → 2.0

        # Ruler measurement tool
        self._ruler_mode = False
        self._measurements: List[Measurement] = []
        self._next_measurement_id = 1
        self._pending_point: Optional[QPointF] = None  # first click in image coords
        self._mouse_pos: Optional[QPointF] = None

        # Reference line (1 cm guide) — draggable
        self._show_reference_line = True
        self._ref_line_pos = QPointF(0.0, 0.0)  # screen offset from default position
        self._ref_line_dragging = False
        self._ref_line_drag_start = QPointF(0, 0)  # mouse pos at drag start
        self._ref_line_pos_start = QPointF(0, 0)   # ref pos at drag start

        # Extra user-placed reference lines
        self._extra_ref_lines: List[ExtraRefLine] = []
        self._next_extra_ref_id = 1
        self._dragging_extra_ref: Optional[ExtraRefLine] = None
        self._extra_ref_drag_start = QPointF(0, 0)
        self._extra_ref_pos_start = QPointF(0, 0)

        # Static border: records the image rect at load time (doesn't move with zoom)
        self._static_border_rect: Optional[QRectF] = None
        
        # Visibility flags for different border elements
        self._show_static_border = True  # Show/hide static border
        self._show_moving_border = True  # Show/hide moving border
        self._show_ref_lines = True  # Show/hide dotted reference lines
        self._pdf_locked = False  # Lock PDF position (disable panning)
        
        # Drawing shapes mode
        self._drawing_mode: Optional[str] = None  # None | "arrow" | "rectangle" | "circle" | "text"
        self._drawing_color = QColor("#000000")  # Current drawing color (default black)
        self._arrows: List[DrawingArrow] = []
        self._rectangles: List[DrawingRectangle] = []
        self._circles: List[DrawingCircle] = []
        self._texts: List[DrawingText] = []
        self._next_arrow_id = 1
        self._next_rectangle_id = 1
        self._next_circle_id = 1
        self._next_text_id = 1
        
        # Drawing state
        self._drawing_start_pos: Optional[QPointF] = None
        self._current_preview_pos: Optional[QPointF] = None
        self._selected_shape: Optional[Tuple[str, int]] = None  # (shape_type, id) or None
        self._resizing_handle: Optional[str] = None  # "start" | "end" | "edge" for current resize
        self._dragging_shape: Optional[Tuple[str, int]] = None
        self._shape_drag_start = QPointF(0, 0)
        self._shape_drag_origin: Optional[Tuple[float, ...]] = None
        
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(500, 400)
        self.setAcceptDrops(True)
        self.setStyleSheet("background-color: #ffffff;")

    # ---- public API ----

    def set_image(self, pixmap: QPixmap, source_path: str = None):
        self._pixmap = pixmap
        self._source_path = source_path
        self._zoom = 1.0
        self._pan_offset = QPointF(0, 0)
        self._measurements.clear()
        self._pending_point = None
        self._ref_line_pos = QPointF(0.0, 0.0)
        self._extra_ref_lines.clear()
        self._fit_image()
        # Record the static border at initial load size
        self._static_border_rect = QRectF(self._image_rect())
        self.update()

    def reset_workspace(self):
        """Remove the loaded drawing and reset calibration, ruler, measurements, and refs."""
        self._pixmap = None
        self._source_path = None
        self._static_border_rect = None
        self._measurements.clear()
        self._pending_point = None
        self._next_measurement_id = 1
        self._zoom = 1.0
        self._pan_offset = QPointF(0, 0)
        self._ref_line_pos = QPointF(0.0, 0.0)
        self._ref_line_dragging = False
        self._ref_line_drag_start = QPointF(0, 0)
        self._extra_ref_lines.clear()
        self._next_extra_ref_id = 1
        self._dragging_extra_ref = None
        self._extra_ref_drag_start = QPointF(0, 0)
        self._extra_ref_pos_start = QPointF(0, 0)
        self._ruler_mode = False
        self._mouse_pos = None
        self._panning = False
        self._unit = "cm"
        self._scale_ratio = 1.0
        self._drawing_mode = None
        self._arrows.clear()
        self._rectangles.clear()
        self._circles.clear()
        self._texts.clear()
        self._next_arrow_id = 1
        self._next_rectangle_id = 1
        self._next_circle_id = 1
        self._next_text_id = 1
        self._drawing_start_pos = None
        self._current_preview_pos = None
        self._selected_shape = None
        self._resizing_handle = None
        self._dragging_shape = None
        self._shape_drag_start = QPointF(0, 0)
        self._shape_drag_origin = None
        self.setCursor(Qt.ArrowCursor)
        self.update()

    def clear_image(self):
        """Clear the drawing; same as :meth:`reset_workspace`."""
        self.reset_workspace()

    def set_show_static_border(self, show: bool):
        """Show or hide the static border (original image boundary)."""
        self._show_static_border = show
        self.update()

    def set_show_moving_border(self, show: bool):
        """Show or hide the moving border (zoomed/panned image border)."""
        self._show_moving_border = show
        self.update()

    def set_show_ref_lines(self, show: bool):
        """Show or hide the dotted reference lines (projection lines from corners to ruler)."""
        self._show_ref_lines = show
        self.update()

    def set_pdf_locked(self, locked: bool):
        """Lock or unlock PDF position (disable/enable panning)."""
        self._pdf_locked = locked
        self.update()

    def set_drawing_mode(self, mode: Optional[str]):
        """Set drawing tool mode: draw shapes, move, erase, or None."""
        self._drawing_mode = mode
        self._drawing_start_pos = None
        self._current_preview_pos = None
        self._selected_shape = None
        self._resizing_handle = None
        if mode in {"arrow", "rectangle", "circle"}:
            self.setCursor(Qt.CrossCursor)
        elif mode == "text":
            self.setCursor(Qt.IBeamCursor)
        elif mode == "move":
            self.setCursor(Qt.OpenHandCursor)
        elif mode == "erase":
            self.setCursor(Qt.ForbiddenCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        self.update()

    def _is_shape_draw_mode(self) -> bool:
        return self._drawing_mode in {"arrow", "rectangle", "circle"}

    def set_drawing_color(self, color: QColor):
        """Set the color for new drawing shapes."""
        self._drawing_color = color
        self.update()

    def clear_drawings(self):
        """Clear all drawn shapes."""
        self._arrows.clear()
        self._rectangles.clear()
        self._circles.clear()
        self._texts.clear()
        self._next_arrow_id = 1
        self._next_rectangle_id = 1
        self._next_circle_id = 1
        self._next_text_id = 1
        self._drawing_start_pos = None
        self._current_preview_pos = None
        self._selected_shape = None
        self.update()

    def set_unit(self, unit: str):
        """Set unit: 'cm', 'mm', 'inches', or 'm'."""
        self._unit = unit
        self._recalc_measurements()
        self.update()

    def set_scale_ratio(self, ratio: float):
        """Set scale ratio (e.g. 2.0 for 1:2 scale)."""
        self._scale_ratio = ratio
        self._recalc_measurements()
        self.update()

    def set_ruler_mode(self, enabled: bool):
        self._ruler_mode = enabled
        self._pending_point = None
        self._mouse_pos = None
        self.setCursor(Qt.CrossCursor if enabled else Qt.ArrowCursor)
        self.update()

    def clear_measurements(self):
        self._measurements.clear()
        self._pending_point = None
        self.update()

    def add_extra_ref_line(self):
        """Add a new draggable reference line at center of canvas."""
        canvas = self._canvas_rect()
        pos = QPointF(canvas.center().x() - self._pixels_per_unit() / 2,
                      canvas.center().y())
        ref = ExtraRefLine(id=self._next_extra_ref_id, pos=pos)
        self._extra_ref_lines.append(ref)
        self._next_extra_ref_id += 1
        self.update()

    def remove_extra_ref_line(self, ref_id: int):
        """Remove an extra reference line by id."""
        self._extra_ref_lines = [r for r in self._extra_ref_lines if r.id != ref_id]
        self.update()

    def undo_last_measurement(self):
        if self._measurements:
            self._measurements.pop()
            self.update()

    def has_image(self) -> bool:
        return self._pixmap is not None and not self._pixmap.isNull()

    def load_file(self, path: str):
        """Load a PDF or image file."""
        ext = os.path.splitext(path)[1].lower()
        if ext in _PDF_EXTS:
            self._load_pdf(path)
        elif ext in _IMAGE_EXTS:
            pix = QPixmap(path)
            if not pix.isNull():
                self.set_image(pix, source_path=path)
                self.file_loaded.emit(path)
        else:
            logger.warning(f"Unsupported file type: {ext}")

    def export_scaled(self, output_path: str) -> Tuple[bool, str]:
        """Export the current view (drawing + measurements + reference line) as an image or PDF."""
        if not self._pixmap:
            return False, "No drawing loaded"

        try:
            ext = os.path.splitext(output_path)[1].lower()

            # Render the canvas content to an image
            canvas = self._canvas_rect()
            cw, ch = int(canvas.width()), int(canvas.height())
            if cw <= 0 or ch <= 0:
                return False, "Canvas too small"

            img = QImage(cw, ch, QImage.Format_ARGB32)
            img.fill(QColor("#ffffff"))

            painter = QPainter(img)
            painter.setRenderHint(QPainter.Antialiasing)

            # Draw the image
            ir = self._image_rect()
            # Translate to canvas-local coordinates
            offset_x = -canvas.x()
            offset_y = -canvas.y()
            target = QRectF(ir.x() + offset_x, ir.y() + offset_y, ir.width(), ir.height())
            painter.drawPixmap(target.toRect(), self._pixmap)

            # Draw measurements on the export
            for m in self._measurements:
                p1 = self._image_to_screen(m.x1, m.y1)
                p2 = self._image_to_screen(m.x2, m.y2)
                # Shift to canvas-local
                p1 = QPointF(p1.x() + offset_x, p1.y() + offset_y)
                p2 = QPointF(p2.x() + offset_x, p2.y() + offset_y)

                pen = QPen(QColor("#2E7D32"), 2)
                painter.setPen(pen)
                painter.drawLine(p1.toPoint(), p2.toPoint())
                painter.setBrush(QColor("#2E7D32"))
                painter.drawEllipse(p1.toPoint(), 4, 4)
                painter.drawEllipse(p2.toPoint(), 4, 4)

                mid = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
                dist_px = ((p2.x() - p1.x()) ** 2 + (p2.y() - p1.y()) ** 2) ** 0.5
                dist_real = self._pixel_distance_to_real(dist_px)
                unit_abbr = {"cm": "cm", "mm": "mm", "inches": "in"}.get(self._unit, "cm")
                label = f"{dist_real:.2f} {unit_abbr}"

                font = QFont("Segoe UI", 10, QFont.Bold)
                painter.setFont(font)
                fm = QFontMetrics(font)
                tw = fm.horizontalAdvance(label) + 8
                th = fm.height() + 4
                bg_rect = QRectF(mid.x() - tw / 2, mid.y() - th - 4, tw, th)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(255, 255, 255, 220))
                painter.drawRoundedRect(bg_rect, 4, 4)
                painter.setPen(QColor("#2E7D32"))
                painter.drawText(bg_rect, Qt.AlignCenter, label)

            painter.end()

            if ext == '.pdf':
                # Save as PDF using QPrinter-like approach via image
                try:
                    import fitz
                    # Create a PDF with the image
                    doc = fitz.open()
                    # A4-ish page that fits the image
                    page = doc.new_page(width=cw, height=ch)
                    img_bytes = QImage_to_bytes(img)
                    page.insert_image(fitz.Rect(0, 0, cw, ch), stream=img_bytes)
                    doc.save(output_path)
                    doc.close()
                except Exception:
                    # Fallback: save as PNG
                    output_path = output_path.rsplit('.', 1)[0] + '.png'
                    img.save(output_path, "PNG")
            else:
                fmt = "PNG" if ext == '.png' else "JPEG"
                img.save(output_path, fmt)

            return True, output_path
        except Exception as e:
            logger.error(f"Export failed: {e}")
            return False, str(e)

    # ---- coordinate helpers ----

    def _canvas_rect(self) -> QRectF:
        """Drawing area inside the ruler borders."""
        return QRectF(
            RULER_THICKNESS, RULER_THICKNESS,
            self.width() - 2 * RULER_THICKNESS,
            self.height() - 2 * RULER_THICKNESS
        )

    def _image_rect(self) -> QRectF:
        """On-screen rectangle of the image."""
        if not self._pixmap:
            return QRectF()
        canvas = self._canvas_rect()
        w = self._pixmap.width() * self._zoom
        h = self._pixmap.height() * self._zoom
        x = canvas.x() + (canvas.width() - w) / 2 + self._pan_offset.x()
        y = canvas.y() + (canvas.height() - h) / 2 + self._pan_offset.y()
        return QRectF(x, y, w, h)

    def _fit_image(self):
        """Fit image into canvas area."""
        if not self._pixmap:
            return
        canvas = self._canvas_rect()
        sx = canvas.width() / self._pixmap.width()
        sy = canvas.height() / self._pixmap.height()
        self._zoom = min(sx, sy) * 0.9
        self._pan_offset = QPointF(0, 0)

    def _screen_to_image(self, screen_pos: QPointF) -> Optional[QPointF]:
        """Convert screen position to normalised image coordinates (0-1)."""
        ir = self._image_rect()
        if ir.width() == 0 or ir.height() == 0:
            return None
        nx = (screen_pos.x() - ir.x()) / ir.width()
        ny = (screen_pos.y() - ir.y()) / ir.height()
        return QPointF(nx, ny)

    def _image_to_screen(self, nx: float, ny: float) -> QPointF:
        """Convert normalised image coords to screen coords."""
        ir = self._image_rect()
        return QPointF(ir.x() + nx * ir.width(), ir.y() + ny * ir.height())

    # ---- DPI / unit helpers ----

    def _pixels_per_unit(self) -> float:
        """Pixels per real-world unit (cm/mm/inch/m) at current scale ratio."""
        screen = QApplication.primaryScreen()
        dpi = screen.logicalDotsPerInch() if screen else 96.0
        if self._unit == "inches":
            ppu = dpi / self._scale_ratio
        elif self._unit == "mm":
            ppu = (dpi / 25.4) / self._scale_ratio
        elif self._unit == "m":
            ppu = (dpi / 0.0254) / self._scale_ratio
        else:  # cm
            ppu = (dpi / 2.54) / self._scale_ratio
        return ppu

    def _pixel_distance_to_real(self, pixel_dist: float) -> float:
        """Convert a screen pixel distance to real-world distance using calibrated ppu."""
        ppu = self._pixels_per_unit()
        return pixel_dist / ppu if ppu > 0 else 0.0

    def _format_real_dimension(self, pixel_value: float, decimals: int = 2) -> str:
        """Format a screen-pixel length using the current calibration and unit."""
        real_value = self._pixel_distance_to_real(pixel_value)
        unit_abbr = {"cm": "cm", "mm": "mm", "inches": "in", "m": "m"}.get(self._unit, "cm")
        return f"{real_value:.{decimals}f} {unit_abbr}"

    def _recalc_measurements(self):
        """Recalculate all measurement distances with current scale/unit."""
        for m in self._measurements:
            p1 = self._image_to_screen(m.x1, m.y1)
            p2 = self._image_to_screen(m.x2, m.y2)
            dist_px = ((p2.x() - p1.x()) ** 2 + (p2.y() - p1.y()) ** 2) ** 0.5
            m.distance_real = self._pixel_distance_to_real(dist_px)

    # ---- PDF loading ----

    def _load_pdf(self, path: str):
        try:
            import fitz
            doc = fitz.open(path)
            if len(doc) == 0:
                return
            page = doc[0]
            mat = fitz.Matrix(2.0, 2.0)  # 2x resolution
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            doc.close()
            qpix = QPixmap()
            qpix.loadFromData(img_data, "PNG")
            if not qpix.isNull():
                self.set_image(qpix, source_path=path)
                self.file_loaded.emit(path)
        except Exception as e:
            logger.error(f"Failed to load PDF: {e}")

    # ---- reference line helpers ----

    def _ref_line_rect(self) -> QRectF:
        """Return the bounding rect of the reference line in screen coords."""
        ppu = self._pixels_per_unit()
        line_len = ppu
        canvas = self._canvas_rect()
        x_start = canvas.x() + 20 + self._ref_line_pos.x()
        y_pos = canvas.bottom() - 20 + self._ref_line_pos.y()
        return QRectF(x_start - 4, y_pos - 24, line_len + 8, 48)

    def _hit_ref_line(self, pos: QPointF) -> bool:
        """Check if a screen position hits the reference line."""
        return self._ref_line_rect().contains(pos)

    def _extra_ref_rect(self, ref: ExtraRefLine) -> QRectF:
        """Return bounding rect of an extra reference line."""
        ppu = self._pixels_per_unit()
        return QRectF(ref.pos.x() - 4, ref.pos.y() - 24, ppu + 8, 48)

    def _hit_extra_ref(self, pos: QPointF) -> Optional[ExtraRefLine]:
        """Check if pos hits any extra reference line."""
        for ref in self._extra_ref_lines:
            if self._extra_ref_rect(ref).contains(pos):
                return ref
        return None

    # ---- paint ----

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Background
        painter.fillRect(self.rect(), QColor("#f5f5f5"))

        # Draw canvas area (white like Technical Overview)
        canvas = self._canvas_rect()
        painter.fillRect(canvas, QColor("#ffffff"))

        # Draw image
        if self._pixmap:
            ir = self._image_rect()
            painter.drawPixmap(ir.toRect(), self._pixmap)

            # --- Image border (moving with zoom) ---
            if self._show_moving_border:
                pen_moving = QPen(QColor("#333333"), 1.5, Qt.SolidLine)
                painter.setPen(pen_moving)
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(ir.toRect())

            # --- Static border (original size, doesn't move with zoom) ---
            if self._show_static_border and self._static_border_rect is not None:
                pen_static = QPen(QColor("#333333"), 1.5, Qt.SolidLine)
                painter.setPen(pen_static)
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(self._static_border_rect.toRect())

            # --- Dashed projection lines from image corners to ruler edges ---
            if self._show_ref_lines:
                self._draw_image_projection_lines(painter, ir)
        else:
            self._draw_drop_zone(painter, canvas)

        # Reference line (1 cm guide on the drawing) — draggable
        if self._show_reference_line and self._pixmap:
            self._draw_reference_line(painter, canvas)

        # Extra user-placed reference lines
        if self._pixmap:
            for ref in self._extra_ref_lines:
                self._draw_extra_ref_line(painter, ref)

        # Measurements + projection lines
        self._draw_measurements(painter)

        # Draw shapes (arrows, rectangles, circles, text)
        self._draw_all_shapes(painter)

        # Live preview line (ruler mode, pending first click)
        if self._ruler_mode and self._pending_point is not None and self._mouse_pos is not None:
            p1 = self._image_to_screen(self._pending_point.x(), self._pending_point.y())
            pen = QPen(QColor("#1976D2"), 2, Qt.DashLine)
            painter.setPen(pen)
            painter.drawLine(p1.toPoint(), self._mouse_pos.toPoint())
            # Live projection lines
            self._draw_projection_lines(painter, p1)
            self._draw_projection_lines(painter, self._mouse_pos)

        # Graduated ruler frame
        self._draw_ruler_frame(painter)

        painter.end()

    def _draw_all_shapes(self, painter: QPainter):
        """Draw all shapes: arrows, rectangles, circles, text."""
        # Draw arrows
        for arrow in self._arrows:
            self._draw_arrow_shape(painter, arrow)
        
        # Draw rectangles
        for rect in self._rectangles:
            self._draw_rectangle_shape(painter, rect)
        
        # Draw circles
        for circle in self._circles:
            self._draw_circle_shape(painter, circle)

        for text in self._texts:
            self._draw_text_shape(painter, text)

        # Selection highlight
        self._draw_selected_shape_highlight(painter)
        
        # Draw preview shape being created
        if self._is_shape_draw_mode() and self._drawing_start_pos and self._current_preview_pos:
            if self._drawing_mode == "arrow":
                self._draw_arrow_preview(painter)
            elif self._drawing_mode == "rectangle":
                self._draw_rectangle_preview(painter)
            elif self._drawing_mode == "circle":
                self._draw_circle_preview(painter)

    def _draw_arrow_shape(self, painter: QPainter, arrow: DrawingArrow):
        """Draw a directional filled arrow (shaft + triangular head)."""
        poly = self._arrow_polygon(arrow)
        if poly is None:
            return

        # Fill-only look
        painter.setPen(Qt.NoPen)
        painter.setBrush(arrow.color)
        painter.drawPolygon(poly)

    def _draw_rectangle_shape(self, painter: QPainter, rect: DrawingRectangle):
        """Draw a rectangle shape with dimensions."""
        poly = self._rectangle_polygon(rect)
        if poly is None:
            return

        # Fill-only look
        painter.setPen(Qt.NoPen)
        painter.setBrush(rect.color)
        painter.drawPolygon(poly)

        x, y, w, h = rect.x, rect.y, rect.width, rect.height
        norm_x = min(x, x + w)
        norm_y = min(y, y + h)
        norm_w = abs(w)
        norm_h = abs(h)
        
        # Draw dimension labels
        font = QFont("Segoe UI", 9, QFont.Bold)
        painter.setFont(font)
        painter.setPen(QColor("#000000"))
        
        dims = rect.get_dimensions()
        width_label = self._format_real_dimension(dims['width'], decimals=2)
        height_label = self._format_real_dimension(dims['height'], decimals=2)
        
        painter.drawText(int(norm_x + norm_w / 2 - 20), int(norm_y - 8), width_label)
        painter.drawText(int(norm_x + norm_w + 5), int(norm_y + norm_h / 2 - 5), height_label)

    def _draw_circle_shape(self, painter: QPainter, circle: DrawingCircle):
        """Draw a circle shape with dimensions."""
        # Fill-only look
        painter.setPen(Qt.NoPen)
        painter.setBrush(circle.color)
        
        painter.drawEllipse(
            int(circle.cx - circle.radius),
            int(circle.cy - circle.radius),
            int(circle.radius * 2),
            int(circle.radius * 2)
        )
        
        # Draw dimension labels
        font = QFont("Segoe UI", 9, QFont.Bold)
        painter.setFont(font)
        painter.setPen(QColor("#000000"))
        
        dims = circle.get_dimensions()
        radius_label = f"r: {self._format_real_dimension(dims['radius'], decimals=2)}"
        diameter_label = f"d: {self._format_real_dimension(dims['diameter'], decimals=2)}"
        
        painter.drawText(int(circle.cx - 35), int(circle.cy), radius_label)
        painter.drawText(int(circle.cx - 35), int(circle.cy + circle.radius + 15), diameter_label)

    def _draw_text_shape(self, painter: QPainter, text: DrawingText):
        """Draw a text annotation."""
        font = QFont("Segoe UI", 13, QFont.Bold)
        painter.setFont(font)
        fm = QFontMetrics(font)
        rect = QRectF(text.x - 6, text.y - fm.ascent() - 5, fm.horizontalAdvance(text.text) + 12, fm.height() + 10)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 215))
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(text.color)
        painter.drawText(QPointF(text.x, text.y), text.text)

    def _draw_preview_label(self, painter: QPainter, pos: QPointF, text: str):
        """Draw a small dimension label with white background near the cursor."""
        font = QFont("Segoe UI", 9, QFont.Bold)
        painter.setFont(font)
        fm = QFontMetrics(font)
        tw = fm.horizontalAdvance(text) + 8
        th = fm.height() + 4
        bg = QRectF(pos.x() + 12, pos.y() + 12, tw, th)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 230))
        painter.drawRoundedRect(bg, 4, 4)
        painter.setPen(QColor("#000000"))
        painter.drawText(bg, Qt.AlignCenter, text)

    def _draw_arrow_preview(self, painter: QPainter):
        """Draw preview of arrow being drawn."""
        preview_arrow = DrawingArrow(
            id=-1,
            x1=self._drawing_start_pos.x(),
            y1=self._drawing_start_pos.y(),
            x2=self._current_preview_pos.x(),
            y2=self._current_preview_pos.y(),
            color=self._drawing_color,
        )
        poly = self._arrow_polygon(preview_arrow)
        if poly is None:
            return

        painter.setPen(QPen(QColor("#000000"), 1.5, Qt.DashLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawPolygon(poly)

        dims = preview_arrow.get_dimensions()
        label = f"L: {self._format_real_dimension(dims['length'], decimals=2)}"
        self._draw_preview_label(painter, self._current_preview_pos, label)

    def _draw_rectangle_preview(self, painter: QPainter):
        """Draw preview of rectangle being drawn."""
        x1, y1 = self._drawing_start_pos.x(), self._drawing_start_pos.y()
        x2, y2 = self._current_preview_pos.x(), self._current_preview_pos.y()
        
        # Draw with dashed outline
        painter.setPen(QPen(QColor("#000000"), 1.5, Qt.DashLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(int(min(x1, x2)), int(min(y1, y2)), int(abs(x2 - x1)), int(abs(y2 - y1)))

        w_label = self._format_real_dimension(abs(x2 - x1), decimals=2)
        h_label = self._format_real_dimension(abs(y2 - y1), decimals=2)
        self._draw_preview_label(painter, self._current_preview_pos, f"W: {w_label}  H: {h_label}")

    def _draw_selected_shape_highlight(self, painter: QPainter):
        """Draw selected-shape visual guide."""
        if not self._selected_shape:
            return

        shape_type, shape_id = self._selected_shape
        painter.setPen(QPen(QColor("#1E88E5"), 1.5, Qt.DashLine))
        painter.setBrush(Qt.NoBrush)

        if shape_type == "arrow":
            arrow = next((a for a in self._arrows if a.id == shape_id), None)
            if not arrow:
                return
            poly = self._arrow_polygon(arrow)
            if poly:
                painter.drawPolygon(poly)
        elif shape_type == "rectangle":
            rect = next((r for r in self._rectangles if r.id == shape_id), None)
            if not rect:
                return
            poly = self._rectangle_polygon(rect)
            if poly:
                painter.drawPolygon(poly)
        elif shape_type == "circle":
            circle = next((c for c in self._circles if c.id == shape_id), None)
            if not circle:
                return
            painter.drawEllipse(
                int(circle.cx - circle.radius),
                int(circle.cy - circle.radius),
                int(circle.radius * 2),
                int(circle.radius * 2),
            )
        elif shape_type == "text":
            text = next((t for t in self._texts if t.id == shape_id), None)
            if not text:
                return
            font = QFont("Segoe UI", 13, QFont.Bold)
            fm = QFontMetrics(font)
            painter.drawRoundedRect(
                QRectF(text.x - 6, text.y - fm.ascent() - 5, fm.horizontalAdvance(text.text) + 12, fm.height() + 10),
                4,
                4,
            )

    def _arrow_polygon(self, arrow: DrawingArrow) -> Optional[QPolygonF]:
        """Build a right/left/up/down directional arrow polygon from start->end."""
        dx = arrow.x2 - arrow.x1
        dy = arrow.y2 - arrow.y1
        length = math.hypot(dx, dy)
        if length < 6:
            return None

        ux = dx / length
        uy = dy / length
        px = -uy
        py = ux

        shaft_half = max(6.0, min(18.0, length * 0.08))
        head_half = shaft_half * 1.6
        head_len = max(14.0, min(length * 0.35, 36.0))

        tail_x, tail_y = arrow.x1, arrow.y1
        tip_x, tip_y = arrow.x2, arrow.y2
        neck_x = tip_x - ux * head_len
        neck_y = tip_y - uy * head_len

        points = [
            QPointF(tail_x + px * shaft_half, tail_y + py * shaft_half),
            QPointF(neck_x + px * shaft_half, neck_y + py * shaft_half),
            QPointF(neck_x + px * head_half, neck_y + py * head_half),
            QPointF(tip_x, tip_y),
            QPointF(neck_x - px * head_half, neck_y - py * head_half),
            QPointF(neck_x - px * shaft_half, neck_y - py * shaft_half),
            QPointF(tail_x - px * shaft_half, tail_y - py * shaft_half),
        ]
        return QPolygonF(points)

    def _rectangle_polygon(self, rect: DrawingRectangle) -> Optional[QPolygonF]:
        """Build rectangle polygon with optional rotation."""
        norm_x = min(rect.x, rect.x + rect.width)
        norm_y = min(rect.y, rect.y + rect.height)
        norm_w = abs(rect.width)
        norm_h = abs(rect.height)
        if norm_w < 2 or norm_h < 2:
            return None

        cx = norm_x + norm_w / 2
        cy = norm_y + norm_h / 2
        angle_rad = math.radians(rect.angle)
        ca = math.cos(angle_rad)
        sa = math.sin(angle_rad)

        corners = [
            QPointF(norm_x, norm_y),
            QPointF(norm_x + norm_w, norm_y),
            QPointF(norm_x + norm_w, norm_y + norm_h),
            QPointF(norm_x, norm_y + norm_h),
        ]

        rotated = []
        for p in corners:
            rx = p.x() - cx
            ry = p.y() - cy
            x = cx + rx * ca - ry * sa
            y = cy + rx * sa + ry * ca
            rotated.append(QPointF(x, y))
        return QPolygonF(rotated)

    def _shape_center(self, shape_type: str, shape_id: int) -> Optional[QPointF]:
        """Return center point of a shape."""
        if shape_type == "arrow":
            s = next((a for a in self._arrows if a.id == shape_id), None)
            if not s:
                return None
            return QPointF((s.x1 + s.x2) / 2, (s.y1 + s.y2) / 2)
        if shape_type == "rectangle":
            s = next((r for r in self._rectangles if r.id == shape_id), None)
            if not s:
                return None
            return QPointF(s.x + s.width / 2, s.y + s.height / 2)
        if shape_type == "circle":
            s = next((c for c in self._circles if c.id == shape_id), None)
            if not s:
                return None
            return QPointF(s.cx, s.cy)
        if shape_type == "text":
            s = next((t for t in self._texts if t.id == shape_id), None)
            if not s:
                return None
            return QPointF(s.x, s.y)
        return None

    def _hit_shape(self, pos: QPointF) -> Optional[Tuple[str, int]]:
        """Hit test topmost shape at a screen position."""
        font = QFont("Segoe UI", 13, QFont.Bold)
        fm = QFontMetrics(font)
        for text in reversed(self._texts):
            rect = QRectF(text.x - 6, text.y - fm.ascent() - 5, fm.horizontalAdvance(text.text) + 12, fm.height() + 10)
            if rect.contains(pos):
                return ("text", text.id)

        for circle in reversed(self._circles):
            if math.hypot(pos.x() - circle.cx, pos.y() - circle.cy) <= circle.radius:
                return ("circle", circle.id)

        for rect in reversed(self._rectangles):
            poly = self._rectangle_polygon(rect)
            if poly and poly.containsPoint(pos, Qt.OddEvenFill):
                return ("rectangle", rect.id)

        for arrow in reversed(self._arrows):
            poly = self._arrow_polygon(arrow)
            if poly and poly.containsPoint(pos, Qt.OddEvenFill):
                return ("arrow", arrow.id)
        return None

    def _delete_selected_shape(self):
        """Delete currently selected shape."""
        if not self._selected_shape:
            return
        shape_type, shape_id = self._selected_shape
        if shape_type == "arrow":
            self._arrows = [a for a in self._arrows if a.id != shape_id]
        elif shape_type == "rectangle":
            self._rectangles = [r for r in self._rectangles if r.id != shape_id]
        elif shape_type == "circle":
            self._circles = [c for c in self._circles if c.id != shape_id]
        elif shape_type == "text":
            self._texts = [t for t in self._texts if t.id != shape_id]
        self._selected_shape = None
        self.update()

    def _rotate_selected_shape(self, angle_deg: float):
        """Rotate selected shape by angle degrees around its center."""
        if not self._selected_shape:
            return
        shape_type, shape_id = self._selected_shape

        if shape_type == "arrow":
            arrow = next((a for a in self._arrows if a.id == shape_id), None)
            if not arrow:
                return
            cx = (arrow.x1 + arrow.x2) / 2
            cy = (arrow.y1 + arrow.y2) / 2
            rad = math.radians(angle_deg)
            ca = math.cos(rad)
            sa = math.sin(rad)
            for keyx, keyy in (("x1", "y1"), ("x2", "y2")):
                x = getattr(arrow, keyx) - cx
                y = getattr(arrow, keyy) - cy
                setattr(arrow, keyx, cx + x * ca - y * sa)
                setattr(arrow, keyy, cy + x * sa + y * ca)
        elif shape_type == "rectangle":
            rect = next((r for r in self._rectangles if r.id == shape_id), None)
            if not rect:
                return
            rect.angle = (rect.angle + angle_deg) % 360
        elif shape_type == "circle":
            circle = next((c for c in self._circles if c.id == shape_id), None)
            if not circle:
                return
            circle.angle = (circle.angle + angle_deg) % 360

        self.update()

    def _draw_circle_preview(self, painter: QPainter):
        """Draw preview of circle being drawn."""
        x1, y1 = self._drawing_start_pos.x(), self._drawing_start_pos.y()
        x2, y2 = self._current_preview_pos.x(), self._current_preview_pos.y()
        
        import math
        radius = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
        
        # Draw with dashed black outline
        painter.setPen(QPen(QColor("#000000"), 1.5, Qt.DashLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(int(x1 - radius), int(y1 - radius), int(radius * 2), int(radius * 2))

        r_label = self._format_real_dimension(radius, decimals=2)
        d_label = self._format_real_dimension(radius * 2, decimals=2)
        self._draw_preview_label(painter, self._current_preview_pos, f"r: {r_label}  d: {d_label}")

    def _draw_image_projection_lines(self, painter: QPainter, ir: QRectF):
        """Draw dashed projection lines from the 4 edges of the image to the ruler frame."""
        canvas = self._canvas_rect()
        pen = QPen(QColor("#333333"), 1.5, Qt.DashLine)
        painter.setPen(pen)

        left = ir.left()
        right = ir.right()
        top = ir.top()
        bottom = ir.bottom()

        # Vertical lines from image left & right edges → top and bottom rulers
        painter.drawLine(int(left), int(canvas.y()), int(left), int(top))
        painter.drawLine(int(left), int(bottom), int(left), int(canvas.bottom()))
        painter.drawLine(int(right), int(canvas.y()), int(right), int(top))
        painter.drawLine(int(right), int(bottom), int(right), int(canvas.bottom()))

        # Horizontal lines from image top & bottom edges → left and right rulers
        painter.drawLine(int(canvas.x()), int(top), int(left), int(top))
        painter.drawLine(int(right), int(top), int(canvas.right()), int(top))
        painter.drawLine(int(canvas.x()), int(bottom), int(left), int(bottom))
        painter.drawLine(int(right), int(bottom), int(canvas.right()), int(bottom))

    def _draw_drop_zone(self, painter: QPainter, canvas: QRectF):
        """Draw upload prompt when no image is loaded."""
        painter.setPen(QPen(QColor("#cccccc"), 2, Qt.DashLine))
        margin = 40
        painter.drawRoundedRect(
            canvas.adjusted(margin, margin, -margin, -margin).toRect(),
            12, 12
        )
        font = QFont("Segoe UI", 14)
        painter.setFont(font)
        painter.setPen(QColor("#666666"))
        painter.drawText(canvas.toRect(), Qt.AlignCenter,
                         "Drop a drawing here\nor click Upload")

    def _draw_reference_line(self, painter: QPainter, canvas: QRectF):
        """Draw a 1-unit reference line (static, not draggable).
        At scale ratios > 1 (e.g. 1:2), the line keeps its physical 1-unit
        length but shows subdivision marks to indicate the scale."""
        # Physical 1-unit at 1:1 scale (ignoring ratio for the ref line itself)
        screen = QApplication.primaryScreen()
        dpi = screen.logicalDotsPerInch() if screen else 96.0
        if self._unit == "inches":
            ppu_base = dpi
        elif self._unit == "mm":
            ppu_base = dpi / 25.4
        elif self._unit == "m":
            ppu_base = dpi / 0.0254
        else:  # cm
            ppu_base = dpi / 2.54
        line_len = ppu_base  # always 1 physical unit regardless of ratio

        # Position (default bottom-left, static)
        x_start = canvas.x() + 20 + self._ref_line_pos.x()
        y_pos = canvas.bottom() - 20 + self._ref_line_pos.y()
        x_end = x_start + line_len

        # Main line — darker red for visibility on white
        pen = QPen(QColor("#C62828"), 3)
        painter.setPen(pen)
        painter.drawLine(int(x_start), int(y_pos), int(x_end), int(y_pos))
        # End caps
        painter.drawLine(int(x_start), int(y_pos - 8), int(x_start), int(y_pos + 8))
        painter.drawLine(int(x_end), int(y_pos - 8), int(x_end), int(y_pos + 8))

        # Subdivision marks for scale ratios > 1
        ratio = self._scale_ratio
        if ratio > 1:
            subdivisions = int(ratio)
            sub_pen = QPen(QColor("#C62828"), 1.5)
            painter.setPen(sub_pen)
            for i in range(1, subdivisions):
                sx = x_start + (line_len * i / subdivisions)
                painter.drawLine(int(sx), int(y_pos - 5), int(sx), int(y_pos + 5))

        # Label
        unit_label = {
            "cm": "1 cm", "mm": "10 mm", "inches": "1 inch", "m": "1 m"
        }.get(self._unit, "1 cm")
        if ratio > 1:
            unit_label += f"  (1:{int(ratio)})"
        font = QFont("Segoe UI", 9, QFont.Bold)
        painter.setFont(font)
        painter.setPen(QColor("#C62828"))
        painter.drawText(
            QRectF(x_start, y_pos - 20, line_len, 18),
            Qt.AlignCenter, unit_label
        )

    def _draw_extra_ref_line(self, painter: QPainter, ref: ExtraRefLine):
        """Draw an extra user-placed reference line with delete button."""
        ppu = self._pixels_per_unit()
        x_start = ref.pos.x()
        y_pos = ref.pos.y()
        x_end = x_start + ppu

        # Line — blue to distinguish from the red default
        pen = QPen(QColor("#1565C0"), 3)
        painter.setPen(pen)
        painter.drawLine(int(x_start), int(y_pos), int(x_end), int(y_pos))
        # End caps
        painter.drawLine(int(x_start), int(y_pos - 8), int(x_start), int(y_pos + 8))
        painter.drawLine(int(x_end), int(y_pos - 8), int(x_end), int(y_pos + 8))

        # Subdivision marks for scale ratios > 1
        ratio = self._scale_ratio
        if ratio > 1:
            subdivisions = int(ratio)
            sub_pen = QPen(QColor("#1565C0"), 1.5)
            painter.setPen(sub_pen)
            for i in range(1, subdivisions):
                sx = x_start + (ppu * i / subdivisions)
                painter.drawLine(int(sx), int(y_pos - 5), int(sx), int(y_pos + 5))

        # Label
        unit_label = {
            "cm": "1 cm", "mm": "10 mm", "inches": "1 inch", "m": "1 m"
        }.get(self._unit, "1 cm")
        font = QFont("Segoe UI", 9, QFont.Bold)
        painter.setFont(font)
        painter.setPen(QColor("#1565C0"))
        painter.drawText(
            QRectF(x_start, y_pos - 20, ppu, 18),
            Qt.AlignCenter, unit_label
        )

        # Delete button (X) — drawn as a small circle with X at the right end
        delete_x = int(x_end + 8)
        delete_y = int(y_pos)
        delete_r = 8
        painter.setBrush(QColor("#E53935"))
        painter.setPen(QPen(QColor("#B71C1C"), 1))
        painter.drawEllipse(QPointF(delete_x, delete_y), delete_r, delete_r)
        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.drawLine(delete_x - 4, delete_y - 4, delete_x + 4, delete_y + 4)
        painter.drawLine(delete_x - 4, delete_y + 4, delete_x + 4, delete_y - 4)
        painter.setBrush(Qt.NoBrush)

        # Drag hint
        painter.setPen(QColor("#999999"))
        hint_font = QFont("Segoe UI", 7)
        painter.setFont(hint_font)
        painter.drawText(
            QRectF(x_start, y_pos + 10, ppu, 12),
            Qt.AlignCenter, "\u21d4 drag to move"
        )

    def _draw_projection_lines(self, painter: QPainter, screen_pt: QPointF):
        """Draw dashed projection lines from a point to the ruler edges."""
        canvas = self._canvas_rect()
        pen = QPen(QColor("#1976D2"), 1, Qt.DotLine)
        painter.setPen(pen)

        sx, sy = screen_pt.x(), screen_pt.y()

        # Horizontal line: point → left ruler edge
        if sx > canvas.x():
            painter.drawLine(int(canvas.x()), int(sy), int(sx), int(sy))
        # Horizontal line: point → right ruler edge
        if sx < canvas.right():
            painter.drawLine(int(sx), int(sy), int(canvas.right()), int(sy))

        # Vertical line: point → top ruler edge
        if sy > canvas.y():
            painter.drawLine(int(sx), int(canvas.y()), int(sx), int(sy))
        # Vertical line: point → bottom ruler edge
        if sy < canvas.bottom():
            painter.drawLine(int(sx), int(sy), int(sx), int(canvas.bottom()))

    def _draw_measurements(self, painter: QPainter):
        """Draw all measurement lines with distance labels and projection lines."""
        for m in self._measurements:
            p1 = self._image_to_screen(m.x1, m.y1)
            p2 = self._image_to_screen(m.x2, m.y2)

            # Projection lines to ruler edges
            self._draw_projection_lines(painter, p1)
            self._draw_projection_lines(painter, p2)

            # Measurement line — dark green on white
            pen = QPen(QColor("#2E7D32"), 2)
            painter.setPen(pen)
            painter.drawLine(p1.toPoint(), p2.toPoint())

            # End dots
            painter.setBrush(QColor("#2E7D32"))
            painter.drawEllipse(p1.toPoint(), 4, 4)
            painter.drawEllipse(p2.toPoint(), 4, 4)

            # Distance label
            mid = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
            dist_px = ((p2.x() - p1.x()) ** 2 + (p2.y() - p1.y()) ** 2) ** 0.5
            dist_real = self._pixel_distance_to_real(dist_px)
            unit_abbr = {"cm": "cm", "mm": "mm", "inches": "in", "m": "m"}.get(self._unit, "cm")
            label = f"{dist_real:.2f} {unit_abbr}"

            font = QFont("Segoe UI", 10, QFont.Bold)
            painter.setFont(font)
            fm = QFontMetrics(font)
            tw = fm.horizontalAdvance(label) + 8
            th = fm.height() + 4

            bg_rect = QRectF(mid.x() - tw / 2, mid.y() - th - 4, tw, th)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 220))
            painter.drawRoundedRect(bg_rect, 4, 4)
            painter.setBrush(Qt.NoBrush)

            painter.setPen(QColor("#2E7D32"))
            painter.drawText(bg_rect, Qt.AlignCenter, label)

    # ---- Adaptive ruler step computation ----

    # Minimum on-screen pixels between two labels.
    _MIN_LABEL_PX = 40
    # Minimum on-screen pixels between two minor ticks (skip if tighter).
    _MIN_MINOR_PX = 3

    def _compute_label_step(self, ppu: float):
        """
        Pick a "nice" label step (in base sub-units) so labels are at least
        _MIN_LABEL_PX pixels apart on screen.

        Returns: (step_in_base_sub_units, ppu_per_base_sub_unit, format_label_callback)
        - For "cm":     base sub-unit = 1 cm,  candidates in cm
        - For "mm":     base sub-unit = 1 mm,  candidates in mm
        - For "inches": base sub-unit = 1 in,  candidates in inches
        - For "m":      base sub-unit = 1 cm,  candidates in cm (label may render as m)
        """
        unit = self._unit

        if unit == "cm":
            ppu_base = ppu  # ppu is per-cm
            candidates = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]
            def fmt(idx, step):
                return str(idx * step)
        elif unit == "mm":
            ppu_base = ppu  # ppu is per-mm
            candidates = [1, 2, 5, 10, 20, 50, 100, 200, 500]
            def fmt(idx, step):
                val_mm = idx * step
                if val_mm >= 100 and val_mm % 10 == 0:
                    return f"{val_mm // 10}cm"
                return str(val_mm)
        elif unit == "inches":
            ppu_base = ppu  # ppu is per-inch
            candidates = [1, 2, 5, 10, 20, 50, 100]
            def fmt(idx, step):
                return str(idx * step)
        else:  # "m" — work in cm sub-units for finer control
            ppu_base = ppu / 100.0  # convert per-m → per-cm
            candidates = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000]
            def fmt(idx, step):
                val_cm = idx * step
                if val_cm >= 100 and val_cm % 100 == 0:
                    return f"{val_cm // 100}m"
                return f"{val_cm}cm"

        if ppu_base <= 0:
            return candidates[-1], ppu_base, fmt

        chosen = candidates[-1]
        for c in candidates:
            if c * ppu_base >= self._MIN_LABEL_PX:
                chosen = c
                break
        return chosen, ppu_base, fmt

    def _draw_ruler_frame(self, painter: QPainter):
        """Draw graduated ruler borders on all 4 edges with adaptive labeling."""
        w, h = self.width(), self.height()
        ppu = self._pixels_per_unit()

        # Ruler background — light grey
        ruler_color = QColor("#e8e8e8")
        painter.fillRect(0, 0, w, RULER_THICKNESS, ruler_color)
        painter.fillRect(0, h - RULER_THICKNESS, w, RULER_THICKNESS, ruler_color)
        painter.fillRect(0, 0, RULER_THICKNESS, h, ruler_color)
        painter.fillRect(w - RULER_THICKNESS, 0, RULER_THICKNESS, h, ruler_color)

        # Corner squares
        corner_color = QColor("#d0d0d0")
        for cx, cy in [(0, 0), (w - RULER_THICKNESS, 0),
                        (0, h - RULER_THICKNESS), (w - RULER_THICKNESS, h - RULER_THICKNESS)]:
            painter.fillRect(int(cx), int(cy), RULER_THICKNESS, RULER_THICKNESS, corner_color)

        # Tick parameters — dark for readability on light background
        tick_color = QColor("#555555")
        label_color = QColor("#222222")
        pen_thin = QPen(tick_color, 1)

        font = QFont("Segoe UI", 8)
        painter.setFont(font)

        # Adaptive step computation
        label_step, ppu_base, fmt = self._compute_label_step(ppu)
        label_step_px = label_step * ppu_base
        medium_step_px = label_step_px / 2.0
        minor_step_px = label_step_px / 10.0

        if label_step_px <= 0:
            return  # nothing meaningful to draw

        draw_minor = minor_step_px >= self._MIN_MINOR_PX

        for top in (True, False):
            self._draw_ruler_ticks_horizontal(
                painter, pen_thin, label_color, font,
                label_step_px, medium_step_px, minor_step_px,
                draw_minor, fmt, label_step, top=top,
            )
        for left in (True, False):
            self._draw_ruler_ticks_vertical(
                painter, pen_thin, label_color, font,
                label_step_px, medium_step_px, minor_step_px,
                draw_minor, fmt, label_step, left=left,
            )

        # Border lines
        border_pen = QPen(QColor("#bbbbbb"), 1)
        painter.setPen(border_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(RULER_THICKNESS, RULER_THICKNESS,
                         w - 2 * RULER_THICKNESS, h - 2 * RULER_THICKNESS)

    def _draw_ruler_ticks_horizontal(self, painter, pen, label_color, font,
                                      label_step_px, medium_step_px, minor_step_px,
                                      draw_minor, fmt, label_step, top: bool):
        w = self.width()
        start_x = RULER_THICKNESS
        end_x = w - RULER_THICKNESS

        if top:
            base_y = RULER_THICKNESS
        else:
            base_y = self.height() - RULER_THICKNESS

        # Minor ticks
        if draw_minor and minor_step_px > 0:
            painter.setPen(pen)
            i = 0
            while True:
                x = start_x + i * minor_step_px
                if x > end_x:
                    break
                ix = int(x)
                if top:
                    painter.drawLine(ix, base_y - 5, ix, base_y)
                else:
                    painter.drawLine(ix, base_y, ix, base_y + 5)
                i += 1

        # Medium ticks
        if medium_step_px > 0:
            painter.setPen(pen)
            i = 0
            while True:
                x = start_x + i * medium_step_px
                if x > end_x:
                    break
                if i % 2 != 0:  # skip those overlapping major
                    ix = int(x)
                    if top:
                        painter.drawLine(ix, base_y - 9, ix, base_y)
                    else:
                        painter.drawLine(ix, base_y, ix, base_y + 9)
                i += 1

        # Major ticks + labels
        painter.setFont(font)
        major_idx = 0
        while True:
            x = start_x + major_idx * label_step_px
            if x > end_x:
                break
            ix = int(x)
            painter.setPen(pen)
            if top:
                painter.drawLine(ix, base_y - 14, ix, base_y)
            else:
                painter.drawLine(ix, base_y, ix, base_y + 14)

            if major_idx > 0:
                label_text = fmt(major_idx, label_step)
                painter.setPen(label_color)
                if top:
                    painter.drawText(ix - 24, base_y - 14 - 14, 48, 12,
                                     Qt.AlignCenter, label_text)
                else:
                    painter.drawText(ix - 24, base_y + 14 + 2, 48, 12,
                                     Qt.AlignCenter, label_text)
            major_idx += 1

    def _draw_ruler_ticks_vertical(self, painter, pen, label_color, font,
                                    label_step_px, medium_step_px, minor_step_px,
                                    draw_minor, fmt, label_step, left: bool):
        h = self.height()
        start_y = RULER_THICKNESS
        end_y = h - RULER_THICKNESS

        if left:
            base_x = RULER_THICKNESS
        else:
            base_x = self.width() - RULER_THICKNESS

        # Minor ticks
        if draw_minor and minor_step_px > 0:
            painter.setPen(pen)
            i = 0
            while True:
                y = start_y + i * minor_step_px
                if y > end_y:
                    break
                iy = int(y)
                if left:
                    painter.drawLine(base_x - 5, iy, base_x, iy)
                else:
                    painter.drawLine(base_x, iy, base_x + 5, iy)
                i += 1

        # Medium ticks
        if medium_step_px > 0:
            painter.setPen(pen)
            i = 0
            while True:
                y = start_y + i * medium_step_px
                if y > end_y:
                    break
                if i % 2 != 0:
                    iy = int(y)
                    if left:
                        painter.drawLine(base_x - 9, iy, base_x, iy)
                    else:
                        painter.drawLine(base_x, iy, base_x + 9, iy)
                i += 1

        # Major ticks + labels
        painter.setFont(font)
        major_idx = 0
        while True:
            y = start_y + major_idx * label_step_px
            if y > end_y:
                break
            iy = int(y)
            painter.setPen(pen)
            if left:
                painter.drawLine(base_x - 14, iy, base_x, iy)
            else:
                painter.drawLine(base_x, iy, base_x + 14, iy)

            if major_idx > 0:
                label_text = fmt(major_idx, label_step)
                painter.setPen(label_color)
                if left:
                    # Keep text fully inside the left ruler panel (prevents clipping).
                    text_rect = QRectF(2, iy - 7, max(8, base_x - 18), 14)
                    painter.drawText(text_rect, Qt.AlignRight | Qt.AlignVCenter, label_text)
                else:
                    text_rect = QRectF(base_x + 16, iy - 7, RULER_THICKNESS - 18, 14)
                    painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, label_text)
            major_idx += 1

    # ---- interaction ----

    def wheelEvent(self, event: QWheelEvent):
        """Zoom drawing proportionally (homothetic)."""
        if not self._pixmap:
            return
        delta = event.angleDelta().y()
        factor = 1.1 if delta > 0 else 0.9
        new_zoom = self._zoom * factor
        new_zoom = max(0.05, min(new_zoom, 50.0))
        self._zoom = new_zoom
        self._recalc_measurements()
        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        pos = QPointF(event.pos())

        # Handle shape drawing modes
        if event.button() == Qt.LeftButton and self._is_shape_draw_mode() and self._pixmap:
            self._drawing_start_pos = pos
            self._current_preview_pos = pos
            self.update()
            return

        # Text tool: click to place a text annotation
        if event.button() == Qt.LeftButton and self._drawing_mode == "text" and self._pixmap:
            dialog = QInputDialog(self)
            dialog.setWindowTitle("Add Text")
            dialog.setLabelText("Text:")
            # Keep text-entry readable on both macOS and Windows regardless of app theme.
            dialog.setStyleSheet("""
                QInputDialog QLabel {
                    color: #111827;
                }
                QInputDialog QLineEdit {
                    color: #111827;
                    background-color: #ffffff;
                    border: 1px solid #d1d5db;
                    border-radius: 4px;
                    padding: 4px 6px;
                }
                QInputDialog QPushButton {
                    color: #111827;
                }
            """)
            ok = dialog.exec_()
            text = dialog.textValue().strip()
            if ok and text:
                self._texts.append(DrawingText(
                    id=self._next_text_id,
                    x=pos.x(),
                    y=pos.y(),
                    text=text,
                    color=QColor("#000000"),
                ))
                self._next_text_id += 1
                self.update()
            return

        # Eraser tool: delete one shape on click
        if event.button() == Qt.LeftButton and self._drawing_mode == "erase" and self._pixmap:
            hit_shape = self._hit_shape(pos)
            if hit_shape is not None:
                self._selected_shape = hit_shape
                self._delete_selected_shape()
            return

        # Shape selection + move (hand tool)
        if (
            event.button() == Qt.LeftButton
            and self._pixmap
            and self._drawing_mode == "move"
            and not self._ruler_mode
        ):
            hit_shape = self._hit_shape(pos)
            if hit_shape is not None:
                self._selected_shape = hit_shape
                self._dragging_shape = hit_shape
                self._shape_drag_start = QPointF(pos)

                shape_type, shape_id = hit_shape
                if shape_type == "arrow":
                    a = next((x for x in self._arrows if x.id == shape_id), None)
                    if a:
                        self._shape_drag_origin = (a.x1, a.y1, a.x2, a.y2)
                elif shape_type == "rectangle":
                    r = next((x for x in self._rectangles if x.id == shape_id), None)
                    if r:
                        self._shape_drag_origin = (r.x, r.y)
                elif shape_type == "circle":
                    c = next((x for x in self._circles if x.id == shape_id), None)
                    if c:
                        self._shape_drag_origin = (c.cx, c.cy)
                elif shape_type == "text":
                    t = next((x for x in self._texts if x.id == shape_id), None)
                    if t:
                        self._shape_drag_origin = (t.x, t.y)

                self.setCursor(Qt.ClosedHandCursor)
                self.update()
                return
            else:
                self._selected_shape = None
                self.update()

        # Rotate selected shape with right click in move mode
        if event.button() == Qt.RightButton and self._drawing_mode == "move":
            hit_shape = self._hit_shape(pos)
            if hit_shape is not None:
                self._selected_shape = hit_shape
                self._rotate_selected_shape(15)
                return

        if event.button() == Qt.LeftButton and self._pixmap and not self._ruler_mode and not self._pdf_locked:
            # Check if clicking delete button on any extra ref line
            for ref in self._extra_ref_lines:
                ppu = self._pixels_per_unit()
                delete_x = ref.pos.x() + ppu + 8
                delete_y = ref.pos.y()
                dist = ((pos.x() - delete_x) ** 2 + (pos.y() - delete_y) ** 2) ** 0.5
                if dist <= 10:
                    self.remove_extra_ref_line(ref.id)
                    return

            # Check extra ref lines for dragging
            hit_extra = self._hit_extra_ref(pos)
            if hit_extra is not None:
                self._dragging_extra_ref = hit_extra
                self._extra_ref_drag_start = QPointF(pos)
                self._extra_ref_pos_start = QPointF(hit_extra.pos)
                self.setCursor(Qt.SizeAllCursor)
                return

            # Red reference line is static — no dragging

        if (event.button() == Qt.MiddleButton and not self._pdf_locked) or (
            event.button() == Qt.LeftButton and not self._ruler_mode and self._pixmap and not self._pdf_locked and not self._drawing_mode
        ):
            self._panning = True
            self._pan_start = event.pos() - self._pan_offset.toPoint()
            self.setCursor(Qt.ClosedHandCursor)
            return

        if event.button() == Qt.LeftButton and not self._pixmap:
            self.click_to_upload.emit()
            return

        if event.button() == Qt.LeftButton and self._ruler_mode and self._pixmap:
            img_pt = self._screen_to_image(QPointF(event.pos()))
            if img_pt is None:
                return
            if self._pending_point is None:
                self._pending_point = img_pt
            else:
                m = Measurement(
                    id=self._next_measurement_id,
                    x1=self._pending_point.x(),
                    y1=self._pending_point.y(),
                    x2=img_pt.x(),
                    y2=img_pt.y(),
                )
                p1 = self._image_to_screen(m.x1, m.y1)
                p2 = self._image_to_screen(m.x2, m.y2)
                dist_px = ((p2.x() - p1.x()) ** 2 + (p2.y() - p1.y()) ** 2) ** 0.5
                m.distance_real = self._pixel_distance_to_real(dist_px)
                self._measurements.append(m)
                self._next_measurement_id += 1
                self._pending_point = None
                self._mouse_pos = None
                self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = QPointF(event.pos())

        # Update drawing preview
        if self._is_shape_draw_mode() and self._drawing_start_pos:
            self._current_preview_pos = pos
            self.update()
            return

        # Move selected shape
        if self._dragging_shape is not None and self._shape_drag_origin is not None:
            delta = pos - self._shape_drag_start
            shape_type, shape_id = self._dragging_shape

            if shape_type == "arrow":
                a = next((x for x in self._arrows if x.id == shape_id), None)
                if a:
                    ox1, oy1, ox2, oy2 = self._shape_drag_origin
                    a.x1 = ox1 + delta.x()
                    a.y1 = oy1 + delta.y()
                    a.x2 = ox2 + delta.x()
                    a.y2 = oy2 + delta.y()
            elif shape_type == "rectangle":
                r = next((x for x in self._rectangles if x.id == shape_id), None)
                if r:
                    ox, oy = self._shape_drag_origin
                    r.x = ox + delta.x()
                    r.y = oy + delta.y()
            elif shape_type == "circle":
                c = next((x for x in self._circles if x.id == shape_id), None)
                if c:
                    ocx, ocy = self._shape_drag_origin
                    c.cx = ocx + delta.x()
                    c.cy = ocy + delta.y()
            elif shape_type == "text":
                t = next((x for x in self._texts if x.id == shape_id), None)
                if t:
                    ox, oy = self._shape_drag_origin
                    t.x = ox + delta.x()
                    t.y = oy + delta.y()

            self.update()
            return

        # Dragging extra reference line
        if self._dragging_extra_ref is not None:
            delta = pos - self._extra_ref_drag_start
            self._dragging_extra_ref.pos = QPointF(
                self._extra_ref_pos_start.x() + delta.x(),
                self._extra_ref_pos_start.y() + delta.y()
            )
            self.update()
            return

        # (Red reference line is static — not draggable)

        if self._panning:
            self._pan_offset = QPointF(event.pos() - self._pan_start)
            self.update()
            return

        if self._ruler_mode and self._pending_point is not None:
            self._mouse_pos = QPointF(event.pos())
            self.update()
            return

        # Update cursor based on hover
        if self._pixmap and not self._ruler_mode and not self._drawing_mode:
            if self._hit_extra_ref(pos) is not None:
                self.setCursor(Qt.SizeAllCursor)
            else:
                self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, event: QMouseEvent):
        pos = QPointF(event.pos())
        
        # Finish drawing shape
        if event.button() == Qt.LeftButton and self._is_shape_draw_mode() and self._drawing_start_pos:
            self._finish_drawing_shape(pos)
            return

        if self._dragging_extra_ref is not None:
            self._dragging_extra_ref = None
            self.setCursor(Qt.ArrowCursor)
            self.update()
            return

        if self._dragging_shape is not None:
            self._dragging_shape = None
            self._shape_drag_origin = None
            self.setCursor(Qt.OpenHandCursor if self._drawing_mode == "move" else Qt.ArrowCursor)
            self.update()
            return


        if self._panning:
            self._panning = False
            self.setCursor(Qt.CrossCursor if self._ruler_mode else (Qt.CrossCursor if self._drawing_mode else Qt.ArrowCursor))
            self.update()

    def _finish_drawing_shape(self, end_pos: QPointF):
        """Finalize a drawn shape."""
        if not self._drawing_start_pos or not self._current_preview_pos:
            return
        
        start = self._drawing_start_pos
        end = self._current_preview_pos
        
        if self._drawing_mode == "arrow":
            arrow = DrawingArrow(
                id=self._next_arrow_id,
                x1=start.x(),
                y1=start.y(),
                x2=end.x(),
                y2=end.y(),
                color=QColor(self._drawing_color)
            )
            self._arrows.append(arrow)
            self._next_arrow_id += 1
        elif self._drawing_mode == "rectangle":
            rect = DrawingRectangle(
                id=self._next_rectangle_id,
                x=start.x(),
                y=start.y(),
                width=end.x() - start.x(),
                height=end.y() - start.y(),
                color=QColor(self._drawing_color)
            )
            self._rectangles.append(rect)
            self._next_rectangle_id += 1
        elif self._drawing_mode == "circle":
            import math
            radius = math.sqrt((end.x() - start.x()) ** 2 + (end.y() - start.y()) ** 2)
            circle = DrawingCircle(
                id=self._next_circle_id,
                cx=start.x(),
                cy=start.y(),
                radius=radius,
                color=QColor(self._drawing_color)
            )
            self._circles.append(circle)
            self._next_circle_id += 1
        
        # Reset drawing state
        self._drawing_start_pos = None
        self._current_preview_pos = None
        self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._pending_point = None
            self._mouse_pos = None
            self._drawing_start_pos = None
            self._current_preview_pos = None
            self.update()
        elif event.key() == Qt.Key_Z and event.modifiers() & Qt.ControlModifier:
            self.undo_last_measurement()
        elif event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self._delete_selected_shape()
        elif event.key() == Qt.Key_R:
            step = -15 if (event.modifiers() & Qt.ShiftModifier) else 15
            self._rotate_selected_shape(step)

    # ---- drag and drop ----

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                ext = os.path.splitext(url.toLocalFile())[1].lower()
                if ext in _IMAGE_EXTS | _PDF_EXTS:
                    event.acceptProposedAction()
                    return

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path:
                self.load_file(path)
                break


def QImage_to_bytes(qimage: QImage) -> bytes:
    """Convert QImage to PNG bytes."""
    from PyQt5.QtCore import QBuffer, QIODevice
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    qimage.save(buf, "PNG")
    return bytes(buf.data())

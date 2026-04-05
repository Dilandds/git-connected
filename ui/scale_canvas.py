"""
Scale Canvas — zoomable/pannable canvas with graduated ruler frame for
drawing scale calibration. Users load a technical drawing (PDF/JPG/PNG),
resize it proportionally until a known reference dimension matches the
graduated frame, then use the ruler tool for real-world measurements.
"""
import os
import logging
from typing import Optional, List, Tuple
from dataclasses import dataclass, field

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy, QApplication,
    QFileDialog, QLabel
)
from PyQt5.QtCore import Qt, QPointF, QRectF, pyqtSignal, QPoint
from PyQt5.QtGui import (
    QPainter, QPixmap, QColor, QPen, QFont, QFontMetrics,
    QDragEnterEvent, QDropEvent, QWheelEvent, QMouseEvent, QPaintEvent,
    QImage,
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
        self._unit = "cm"  # cm | mm | inches
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

        self.setMouseTracking(True)
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

    def clear_image(self):
        self._pixmap = None
        self._source_path = None
        self._measurements.clear()
        self._pending_point = None
        self._zoom = 1.0
        self._pan_offset = QPointF(0, 0)
        self._ref_line_pos = QPointF(0.0, 0.0)
        self._extra_ref_lines.clear()
        self.update()

    def set_unit(self, unit: str):
        """Set unit: 'cm', 'mm', or 'inches'."""
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
        """Pixels per real-world unit (cm/mm/inch) at current scale ratio."""
        screen = QApplication.primaryScreen()
        dpi = screen.logicalDotsPerInch() if screen else 96.0
        if self._unit == "inches":
            ppu = dpi / self._scale_ratio
        elif self._unit == "mm":
            ppu = (dpi / 25.4) / self._scale_ratio
        else:  # cm
            ppu = (dpi / 2.54) / self._scale_ratio
        return ppu

    def _pixel_distance_to_real(self, pixel_dist: float) -> float:
        """Convert a screen pixel distance to real-world distance using calibrated ppu."""
        ppu = self._pixels_per_unit()
        return pixel_dist / ppu if ppu > 0 else 0.0

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
            pen_moving = QPen(QColor("#333333"), 1.5, Qt.SolidLine)
            painter.setPen(pen_moving)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(ir.toRect())

            # --- Static border (original size, doesn't move with zoom) ---
            if self._static_border_rect is not None:
                pen_static = QPen(QColor("#333333"), 1.5, Qt.SolidLine)
                painter.setPen(pen_static)
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(self._static_border_rect.toRect())

            # --- Dashed projection lines from image corners to ruler edges ---
            self._draw_image_projection_lines(painter, ir)
        else:
            self._draw_drop_zone(painter, canvas)

        # Reference line (1 cm guide on the drawing) — draggable
        if self._show_reference_line and self._pixmap:
            self._draw_reference_line(painter, canvas)

        # Measurements + projection lines
        self._draw_measurements(painter)

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
        """Draw a 1-unit reference line — draggable."""
        ppu = self._pixels_per_unit()
        line_len = ppu  # 1 unit worth of pixels

        # Position (default bottom-left, offset by drag)
        x_start = canvas.x() + 20 + self._ref_line_pos.x()
        y_pos = canvas.bottom() - 20 + self._ref_line_pos.y()
        x_end = x_start + line_len

        # Line — darker red for visibility on white
        pen = QPen(QColor("#C62828"), 3)
        painter.setPen(pen)
        painter.drawLine(int(x_start), int(y_pos), int(x_end), int(y_pos))
        # End caps
        painter.drawLine(int(x_start), int(y_pos - 8), int(x_start), int(y_pos + 8))
        painter.drawLine(int(x_end), int(y_pos - 8), int(x_end), int(y_pos + 8))

        # Label — no background rectangle, just dark red text
        unit_label = {"cm": "1 cm", "mm": "10 mm", "inches": "1 inch"}.get(self._unit, "1 cm")
        font = QFont("Segoe UI", 9, QFont.Bold)
        painter.setFont(font)
        painter.setPen(QColor("#C62828"))
        painter.drawText(
            QRectF(x_start, y_pos - 20, line_len, 18),
            Qt.AlignCenter, unit_label
        )

        # Drag hint
        painter.setPen(QColor("#999999"))
        hint_font = QFont("Segoe UI", 7)
        painter.setFont(hint_font)
        painter.drawText(
            QRectF(x_start, y_pos + 10, line_len, 12),
            Qt.AlignCenter, "⇔ drag to move"
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

    def _draw_ruler_frame(self, painter: QPainter):
        """Draw graduated ruler borders on all 4 edges."""
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

        font = QFont("Segoe UI", 7)
        painter.setFont(font)

        if self._unit == "mm":
            minor_px = ppu
            major_px = ppu * 10
            label_every = 10
        elif self._unit == "inches":
            minor_px = ppu / 8
            major_px = ppu
            label_every = 1
        else:
            minor_px = ppu / 10
            major_px = ppu
            label_every = 1

        if minor_px < 2:
            minor_px = 2

        self._draw_ruler_ticks_horizontal(painter, pen_thin, label_color, font,
                                           minor_px, major_px, label_every, top=True)
        self._draw_ruler_ticks_horizontal(painter, pen_thin, label_color, font,
                                           minor_px, major_px, label_every, top=False)
        self._draw_ruler_ticks_vertical(painter, pen_thin, label_color, font,
                                         minor_px, major_px, label_every, left=True)
        self._draw_ruler_ticks_vertical(painter, pen_thin, label_color, font,
                                         minor_px, major_px, label_every, left=False)

        # Border lines
        border_pen = QPen(QColor("#bbbbbb"), 1)
        painter.setPen(border_pen)
        painter.drawRect(RULER_THICKNESS, RULER_THICKNESS,
                         w - 2 * RULER_THICKNESS, h - 2 * RULER_THICKNESS)

    def _draw_ruler_ticks_horizontal(self, painter, pen, label_color, font,
                                      minor_px, major_px, label_every, top: bool):
        w = self.width()
        start_x = RULER_THICKNESS
        end_x = w - RULER_THICKNESS

        if top:
            base_y = RULER_THICKNESS
        else:
            base_y = self.height() - RULER_THICKNESS

        tick_idx = 0
        x = start_x
        while x <= end_x:
            if major_px > 0 and minor_px > 0:
                ticks_per_major = max(1, round(major_px / minor_px))
            else:
                ticks_per_major = 10

            is_major = (tick_idx % ticks_per_major == 0) if ticks_per_major > 0 else False
            is_medium = (tick_idx % max(1, ticks_per_major // 2) == 0) if not is_major else False

            if is_major:
                tick_len = 14
            elif is_medium:
                tick_len = 9
            else:
                tick_len = 5

            painter.setPen(pen)
            ix = int(x)
            if top:
                painter.drawLine(ix, base_y - tick_len, ix, base_y)
            else:
                painter.drawLine(ix, base_y, ix, base_y + tick_len)

            if is_major and tick_idx > 0:
                major_idx = tick_idx // ticks_per_major
                if self._unit == "mm":
                    label_text = str(major_idx * 10)
                elif self._unit == "inches":
                    label_text = str(major_idx)
                else:
                    label_text = str(major_idx)

                painter.setPen(label_color)
                painter.setFont(font)
                if top:
                    painter.drawText(ix - 10, base_y - tick_len - 2, 20, 12,
                                     Qt.AlignCenter, label_text)
                else:
                    painter.drawText(ix - 10, base_y + tick_len + 1, 20, 12,
                                     Qt.AlignCenter, label_text)

            x += minor_px
            tick_idx += 1

    def _draw_ruler_ticks_vertical(self, painter, pen, label_color, font,
                                    minor_px, major_px, label_every, left: bool):
        h = self.height()
        start_y = RULER_THICKNESS
        end_y = h - RULER_THICKNESS

        if left:
            base_x = RULER_THICKNESS
        else:
            base_x = self.width() - RULER_THICKNESS

        tick_idx = 0
        y = start_y
        while y <= end_y:
            if major_px > 0 and minor_px > 0:
                ticks_per_major = max(1, round(major_px / minor_px))
            else:
                ticks_per_major = 10

            is_major = (tick_idx % ticks_per_major == 0) if ticks_per_major > 0 else False
            is_medium = (tick_idx % max(1, ticks_per_major // 2) == 0) if not is_major else False

            if is_major:
                tick_len = 14
            elif is_medium:
                tick_len = 9
            else:
                tick_len = 5

            painter.setPen(pen)
            iy = int(y)
            if left:
                painter.drawLine(base_x - tick_len, iy, base_x, iy)
            else:
                painter.drawLine(base_x, iy, base_x + tick_len, iy)

            if is_major and tick_idx > 0:
                major_idx = tick_idx // ticks_per_major
                if self._unit == "mm":
                    label_text = str(major_idx * 10)
                elif self._unit == "inches":
                    label_text = str(major_idx)
                else:
                    label_text = str(major_idx)

                painter.setPen(label_color)
                painter.setFont(font)
                painter.save()
                if left:
                    painter.translate(base_x - tick_len - 14, iy + 5)
                else:
                    painter.translate(base_x + tick_len + 2, iy + 5)
                painter.drawText(0, 0, label_text)
                painter.restore()

            y += minor_px
            tick_idx += 1

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

        # Check if clicking on the reference line (for dragging)
        if event.button() == Qt.LeftButton and self._show_reference_line and self._pixmap:
            if not self._ruler_mode and self._hit_ref_line(pos):
                self._ref_line_dragging = True
                ref_rect = self._ref_line_rect()
                self._ref_line_drag_offset = QPointF(
                    pos.x() - ref_rect.x(),
                    pos.y() - ref_rect.y()
                )
                self.setCursor(Qt.SizeAllCursor)
                return

        if event.button() == Qt.MiddleButton or (
            event.button() == Qt.LeftButton and not self._ruler_mode and self._pixmap
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

        # Dragging reference line
        if self._ref_line_dragging:
            canvas = self._canvas_rect()
            ref_rect = self._ref_line_rect()
            new_x = pos.x() - self._ref_line_drag_offset.x() - (canvas.x() + 20 - self._ref_line_pos.x()) + 4
            new_y = pos.y() - self._ref_line_drag_offset.y() - (canvas.bottom() - 20 - self._ref_line_pos.y()) + 24
            self._ref_line_pos = QPointF(new_x, new_y)
            self.update()
            return

        if self._panning:
            self._pan_offset = QPointF(event.pos() - self._pan_start)
            self.update()
            return

        if self._ruler_mode and self._pending_point is not None:
            self._mouse_pos = QPointF(event.pos())
            self.update()
            return

        # Update cursor based on hover
        if self._show_reference_line and self._pixmap and not self._ruler_mode:
            if self._hit_ref_line(pos):
                self.setCursor(Qt.SizeAllCursor)
            else:
                self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._ref_line_dragging:
            self._ref_line_dragging = False
            self.setCursor(Qt.ArrowCursor)
            self.update()
            return

        if self._panning:
            self._panning = False
            self.setCursor(Qt.CrossCursor if self._ruler_mode else Qt.ArrowCursor)
            self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._pending_point = None
            self._mouse_pos = None
            self.update()
        elif event.key() == Qt.Key_Z and event.modifiers() & Qt.ControlModifier:
            self.undo_last_measurement()

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

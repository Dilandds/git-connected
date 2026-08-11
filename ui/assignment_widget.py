"""
Assignment screen — annotate a product image with labeled area cards
connected by curved bezier arrows, showing who is responsible for each part.
"""
import logging
import math
import os
import uuid
from dataclasses import dataclass, asdict, field
from typing import List, Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QFileDialog, QComboBox, QLineEdit, QDialog,
    QStackedWidget,
)
from PyQt5.QtCore import Qt, pyqtSignal, QPointF, QRectF, QTimer
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QBrush, QPainterPath,
    QFont, QPixmap, QFontMetrics,
)

from ui.styles import default_theme, TOOLTIP_STYLE, make_font
from ui.modal_utils import FormModal
from i18n import t

logger = logging.getLogger(__name__)

# ── Palette ───────────────────────────────────────────────────────────────────
_BG      = '#f0f2f5'
_CANVAS  = '#ffffff'
_BORDER  = '#e5e7eb'
_TEXT    = '#1e2430'
_MUTED   = '#6b7280'
_ACCENT  = default_theme.button_primary
_ACCENT_H = default_theme.button_primary_hover

_BADGE_COLORS = [
    '#22c55e',  # green
    '#3b82f6',  # blue
    '#f97316',  # orange
    '#8b5cf6',  # purple
    '#ef4444',  # red
    '#0d9488',  # teal
    '#eab308',  # yellow
    '#ec4899',  # pink
    '#06b6d4',  # cyan
    '#f43f5e',  # rose
]

_STATUS_COLORS = {
    'Completed':   '#22c55e',
    'In progress': '#3b82f6',
    'Pending':     '#f59e0b',
    'Cancelled':   '#ef4444',
}

# ── Layout constants ──────────────────────────────────────────────────────────
_CARD_W, _CARD_H = 190, 112   # client asked for bigger area cards (was 148x88)
_CARD_R   = 8
# Connection-dot radius. Made bigger so it's a comfortable click target now
# that clicking it directly (rather than a separate "Line" tool button) is
# how a line/arrow gets started.
_DOT_R = 9
_A4_W_PORTRAIT,  _A4_H_PORTRAIT  = 560, 793
_A4_W_LANDSCAPE, _A4_H_LANDSCAPE = 793, 560
_CANVAS_W_P, _CANVAS_H_P = 1300, 980    # portrait canvas
_CANVAS_W_L, _CANVAS_H_L = 1550, 760   # landscape canvas
_IMG_GAP  = 72       # horizontal gap between card and A4 frame
# Margins reserved around the frame for the area cards, used when the frame
# is sized to an imported image's own aspect ratio (see _fit_frame_to_image)
# rather than one of the two fixed A4 presets above.
_FRAME_SIDE_MARGIN = 370
_FRAME_VERT_MARGIN = 93

_ZOOM_MIN  = 0.5
_ZOOM_MAX  = 2.5
_ZOOM_STEP = 0.1

# ── Styles ────────────────────────────────────────────────────────────────────
_BTN = f"""
    QPushButton {{
        background: #f3f4f6; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 6px;
        font-size: 13px; padding: 5px 14px;
    }}
    QPushButton:hover {{ background: #e5e7eb; border-color: {_ACCENT}; }}
    QPushButton:checked {{ background: {_ACCENT}; color: white; border-color: {_ACCENT}; }}
    QPushButton:pressed {{ background: {_ACCENT}; color: white; }}
""" + TOOLTIP_STYLE

_BTN_PRIMARY = f"""
    QPushButton {{
        background: {_ACCENT}; color: white; border: none;
        border-radius: 6px; font-size: 13px; padding: 5px 14px;
    }}
    QPushButton:hover {{ background: {_ACCENT_H}; }}
""" + TOOLTIP_STYLE


# ── Data model ────────────────────────────────────────────────────────────────
@dataclass
class AreaCard:
    id: str
    title: str = ''
    supplier: str = ''
    status: str = 'In progress'
    number: int = 1
    x: float = 0.0
    y: float = 0.0
    color: str = '#3b82f6'
    arrows: list = field(default_factory=list)  # list of {'rx': float, 'ry': float}

    def rect(self) -> QRectF:
        return QRectF(self.x, self.y, _CARD_W, _CARD_H)

    def is_left_of(self, img_rect: QRectF) -> bool:
        return (self.x + _CARD_W / 2) < img_rect.center().x()

    def connection_point(self, img_rect: QRectF) -> QPointF:
        """Right-edge center for left cards, left-edge center for right cards."""
        if self.is_left_of(img_rect):
            return QPointF(self.x + _CARD_W, self.y + _CARD_H / 2)
        return QPointF(self.x, self.y + _CARD_H / 2)

    def arrow_point(self, img_rect: QRectF, arrow: dict) -> QPointF:
        return QPointF(
            img_rect.x() + arrow['rx'] * img_rect.width(),
            img_rect.y() + arrow['ry'] * img_rect.height(),
        )


# ── Card edit dialog ──────────────────────────────────────────────────────────
class CardEditDialog(FormModal):
    def __init__(self, card: AreaCard, parent=None):
        super().__init__(parent, t('assignment.edit_card'), theme=FormModal.LIGHT)

        self._f_title = self.add_field(t('assignment.card_title'), QLineEdit(), height=32)
        self._f_title.setPlaceholderText(t('assignment.card_title_ph'))
        self._f_title.setText(card.title)

        self._f_supplier = self.add_field(t('assignment.card_supplier'), QLineEdit(), height=32)
        self._f_supplier.setPlaceholderText(t('assignment.card_supplier_ph'))
        self._f_supplier.setText(card.supplier)

        self._combo = QComboBox()
        self._combo.addItems(list(_STATUS_COLORS.keys()))
        idx = self._combo.findText(card.status)
        if idx >= 0:
            self._combo.setCurrentIndex(idx)
        self.add_field(t('assignment.card_status'), self._combo, height=32)

        self.finish(ok=t('common.save'), cancel=t('common.cancel'))

        self._f_title.returnPressed.connect(self.ok_btn.click)
        self._f_supplier.returnPressed.connect(self.ok_btn.click)
        self._f_title.setFocus()

    def get_title(self) -> str:
        return self._f_title.text().strip()

    def get_supplier(self) -> str:
        return self._f_supplier.text().strip()

    def get_status(self) -> str:
        return self._combo.currentText()


def ensure_tab_ids(tabs_data: list) -> list:
    """Return tabs_data with every item guaranteed an 'id' — a save from
    before tabs had stable ids won't have one, so it gets a positional
    fallback ('tab-0', 'tab-1', ...) instead. Deterministic so two
    independent loads of the SAME unmigrated file derive the identical
    id — needed both by AssignmentCanvas.set_data (the live widget) and
    by ui/project_widget.py's save-conflict merge prep, which must apply
    this to `base`/`remote` too (raw JSON straight off disk, not just the
    live widget's own data) or an untouched legacy tab looks like a
    brand-new id collision on every side, tripping
    core.project_merge's collision renumbering (which assumes numeric
    ids) instead of being recognized as the same tab."""
    return [dict(td, id=(td.get('id') or f'tab-{i}')) for i, td in enumerate(tabs_data or [])]


# ── Drawing canvas ────────────────────────────────────────────────────────────
class AssignmentCanvas(QWidget):
    """The interactive paint surface — A4 frame + area cards + bezier arrows."""

    changed = pyqtSignal()
    upload_requested = pyqtSignal()
    remove_image_clicked = pyqtSignal()
    # Emitted whenever orientation is changed (auto or manual) so the parent
    # widget can update its orientation button label.
    orientation_changed = pyqtSignal(str)   # 'portrait' | 'landscape'

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._orientation: str = 'portrait'
        self._a4_w: int = _A4_W_PORTRAIT
        self._a4_h: int = _A4_H_PORTRAIT
        self._font_family: str = ''
        self._font_size: int = 13
        # Base (unzoomed) canvas size in logical units — the widget's actual
        # pixel size is base * zoom (see _apply_zoom_size). paintEvent draws
        # everything in base-space and applies a single QPainter.scale(), so
        # cards/arrows/image all zoom together and stay in registration.
        self._base_w: int = _CANVAS_W_P
        self._base_h: int = _CANVAS_H_P
        self._zoom: float = 1.0
        self._apply_zoom_size()
        self.setMouseTracking(True)
        self.setCursor(Qt.ArrowCursor)
        self.setFocusPolicy(Qt.StrongFocus)

        # Stable identity for this tab/canvas — needed so a save-conflict
        # merge can match "the same tab" across local/remote instead of
        # only being able to compare tabs by list position (see
        # core.project_merge._merge_assignment). Overwritten by whatever
        # id (or positional fallback) set_data loads, if any.
        self._id: str = str(uuid.uuid4())
        self._image: Optional[QPixmap] = None
        self._image_name: str = ''
        self._image_b64: str = ''
        self._x_btn_rect: Optional[QRectF] = None   # canvas-space hit rect for × button
        self._cards: List[AreaCard] = []
        self._tool: str = 'select'
        self._selected_id: Optional[str] = None

        # Drag state
        self._drag_id: Optional[str] = None
        self._drag_offset: QPointF = QPointF()

        # Line-draw state
        self._line_card: Optional[AreaCard] = None
        self._line_pos: Optional[QPointF] = None

        # Undo / redo
        self._undo_stack: list = []
        self._redo_stack: list = []

        # Marquee — scrolls a hovered card's title/supplier/status text left
        # when it's too long to fit, mirroring the hover marquee used for
        # long names in Traceability and the Timeline Operations column.
        self._marquee_card: Optional[AreaCard] = None
        self._marquee_offsets: dict = {'title': 0, 'supplier': 0, 'status': 0}
        self._marquee_timer = QTimer(self)
        self._marquee_timer.timeout.connect(self._marquee_step)

    def _font(self, size: int, bold: bool = False) -> QFont:
        """Build a QFont for canvas text — falls back to the app's standard
        cross-platform family (make_font) when no explicit family was chosen,
        instead of an empty-string QFont whose fallback rendered inconsistently
        on Windows."""
        if self._font_family:
            f = QFont(self._font_family, size)
            f.setBold(bold)
            return f
        return make_font(size=size, bold=bold)

    # ── A4 frame geometry ─────────────────────────────────────────────────────

    def _img_rect(self) -> QRectF:
        x = (self._base_w - self._a4_w) / 2
        y = (self._base_h - self._a4_h) / 2
        return QRectF(x, y, self._a4_w, self._a4_h)

    # ── Zoom ──────────────────────────────────────────────────────────────────

    def _apply_zoom_size(self):
        """Resize the widget to base-size * zoom. The surrounding QScrollArea
        (setWidgetResizable(False)) then shows scrollbars as needed — the
        same mechanism already used for portrait vs. landscape sizing."""
        self.setFixedSize(round(self._base_w * self._zoom), round(self._base_h * self._zoom))
        self.update()

    def set_zoom(self, value: float):
        value = max(_ZOOM_MIN, min(_ZOOM_MAX, value))
        if value == self._zoom:
            return
        self._zoom = value
        self._apply_zoom_size()

    def wheelEvent(self, e):
        """Plain scroll zooms the whole canvas (photo + cards + arrows scale
        together so arrows stay pinned to the right spot on the photo) —
        same "scroll to zoom" gesture used by the Quality Control image
        annotation view, so panning happens via the scrollbars instead."""
        self.set_zoom(self._zoom + (_ZOOM_STEP if e.angleDelta().y() > 0 else -_ZOOM_STEP))
        e.accept()

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        # Everything below is drawn in base-space (unzoomed logical units);
        # this single scale is what makes the image, cards and arrows zoom
        # together and stay in registration with each other.
        p.fillRect(self.rect(), QColor(_BG))
        p.scale(self._zoom, self._zoom)

        img_rect = self._img_rect()

        # Drop shadow
        p.fillRect(
            QRectF(img_rect.x() + 6, img_rect.y() + 6,
                   img_rect.width(), img_rect.height()),
            QColor(0, 0, 0, 35),
        )

        # A4 white frame
        p.fillRect(img_rect, QColor(_CANVAS))
        p.setPen(QPen(QColor(_BORDER), 1))
        p.drawRect(img_rect)

        # Image or drop hint
        if self._image:
            p.drawPixmap(img_rect.toRect(), self._image)
            # × remove button — top-right corner of the image
            _xr = QRectF(img_rect.right() - 28, img_rect.y() + 6, 22, 22)
            self._x_btn_rect = _xr
            p.setBrush(QBrush(QColor(0, 0, 0, 140)))
            p.setPen(Qt.NoPen)
            p.drawEllipse(_xr)
            p.setPen(QPen(QColor('#ffffff'), 1.8))
            p.setFont(self._font(11, bold=True))
            p.drawText(_xr, Qt.AlignCenter, '×')
        else:
            self._x_btn_rect = None
            p.setPen(QColor(_MUTED))
            p.setFont(self._font(13))
            p.drawText(img_rect, Qt.AlignCenter, t('assignment.drop_hint'))

        # File label above frame
        p.setPen(QColor(_MUTED))
        p.setFont(self._font(9))
        if self._image_name:
            p.drawText(
                QRectF(img_rect.x() + 4, img_rect.y() - 22, 320, 18),
                Qt.AlignLeft | Qt.AlignVCenter,
                self._image_name,
            )
        orient_label = ('A4 ' + t('assignment.portrait')) if self._orientation == 'portrait' \
            else ('A4 ' + t('assignment.landscape'))
        p.drawText(
            QRectF(img_rect.right() - 110, img_rect.y() - 22, 110, 18),
            Qt.AlignRight | Qt.AlignVCenter,
            orient_label,
        )

        # Arrows (drawn behind cards)
        for card in self._cards:
            cp = card.connection_point(img_rect)
            for arrow in card.arrows:
                self._paint_arrow(p, cp, card.arrow_point(img_rect, arrow), card.color)

        # In-progress arrow preview
        if self._line_card and self._line_pos:
            self._paint_arrow(
                p,
                self._line_card.connection_point(img_rect),
                self._line_pos,
                self._line_card.color,
                alpha=90,
            )

        # Cards
        for card in self._cards:
            self._paint_card(p, card, img_rect)

    def _paint_card(self, p: QPainter, card: AreaCard, img_rect: QRectF):
        r = card.rect()
        selected = card.id == self._selected_id

        # Shadow
        p.fillRect(r.adjusted(2, 2, 2, 2), QColor(0, 0, 0, 18))

        # Card body
        path = QPainterPath()
        path.addRoundedRect(r, _CARD_R, _CARD_R)
        p.setBrush(QBrush(QColor(_CANVAS)))
        border_color = QColor(_ACCENT) if selected else QColor(_BORDER)
        p.setPen(QPen(border_color, 1.8 if selected else 1.0))
        p.drawPath(path)

        # Number badge
        badge = QRectF(r.x() + 9, r.y() + 9, 26, 26)
        p.setBrush(QBrush(QColor(card.color)))
        p.setPen(Qt.NoPen)
        p.drawEllipse(badge)
        p.setPen(QColor('#ffffff'))
        p.setFont(self._font(11, bold=True))
        p.drawText(badge, Qt.AlignCenter, str(card.number))

        # Arrow count badge (show if >1 arrow)
        if len(card.arrows) > 1:
            ab = QRectF(r.right() - 20, r.y() + 4, 16, 16)
            p.setBrush(QBrush(QColor('#6b7280')))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(ab, 8, 8)
            p.setPen(QColor('#ffffff'))
            p.setFont(self._font(9, bold=True))
            p.drawText(ab, Qt.AlignCenter, str(len(card.arrows)))

        # Title
        p.setPen(QColor(_TEXT))
        title_font = self._font(self._font_size, bold=True)
        p.setFont(title_font)
        title_rect = QRectF(r.x() + 42, r.y() + 9, r.width() - 52, 26)
        self._draw_marquee_field(p, card, 'title', card.title or '—', title_font, title_rect)

        # Supplier / task
        p.setPen(QColor(_MUTED))
        supplier_font = self._font(max(self._font_size - 2, 9))
        p.setFont(supplier_font)
        supplier_rect = QRectF(r.x() + 9, r.y() + 42, r.width() - 18, 22)
        self._draw_marquee_field(p, card, 'supplier', card.supplier, supplier_font, supplier_rect)

        # Status
        p.setPen(QColor(_STATUS_COLORS.get(card.status, _MUTED)))
        status_font = self._font(max(self._font_size - 2, 9), bold=True)
        p.setFont(status_font)
        status_rect = QRectF(r.x() + 9, r.y() + 66, r.width() - 18, 22)
        self._draw_marquee_field(p, card, 'status', card.status, status_font, status_rect)

        # Connection dot on the edge facing the image — click it directly to
        # start/finish a line (no separate "Line" tool needed).
        cp = card.connection_point(img_rect)
        p.setBrush(QBrush(QColor(card.color)))
        p.setPen(QPen(QColor('#ffffff'), 1.5))
        p.drawEllipse(cp, _DOT_R, _DOT_R)

    # ── Card-text marquee (hover-to-scroll long title/supplier/status) ─────────

    def _draw_marquee_field(self, p: QPainter, card: AreaCard, field: str,
                             text: str, font: QFont, rect: QRectF):
        """Draw one card text field, clipped to `rect`, scrolling it left if
        it's the currently-hovered card's field and the text overflows."""
        avail_w = rect.width()
        dx = 0
        if card is self._marquee_card:
            overflow = QFontMetrics(font).horizontalAdvance(text) - avail_w
            if overflow > 0:
                dx = -self._marquee_offsets.get(field, 0)
        p.save()
        p.setClipRect(rect)
        p.drawText(rect.translated(dx, 0), Qt.AlignLeft | Qt.AlignVCenter, text)
        p.restore()

    def _set_marquee_hover(self, card: Optional[AreaCard]):
        """Update which card is being marquee-scrolled, starting immediately
        the moment the cursor lands on a card with any overflowing field."""
        if card is self._marquee_card:
            return
        self._marquee_card = card
        self._marquee_offsets = {'title': 0, 'supplier': 0, 'status': 0}
        if card is not None and self._card_has_overflow(card):
            self._marquee_timer.start(25)
        else:
            self._marquee_timer.stop()
        self.update()

    def _card_has_overflow(self, card: AreaCard) -> bool:
        r = card.rect()
        fields = [
            ('title', card.title or '—', self._font(self._font_size, bold=True), r.width() - 52),
            ('supplier', card.supplier, self._font(max(self._font_size - 2, 9)), r.width() - 18),
            ('status', card.status, self._font(max(self._font_size - 2, 9), bold=True), r.width() - 18),
        ]
        return any(QFontMetrics(f).horizontalAdvance(txt) > w for _, txt, f, w in fields)

    def _marquee_step(self):
        card = self._marquee_card
        if card is None:
            self._marquee_timer.stop()
            return
        r = card.rect()
        fields = [
            ('title', card.title or '—', self._font(self._font_size, bold=True), r.width() - 52),
            ('supplier', card.supplier, self._font(max(self._font_size - 2, 9)), r.width() - 18),
            ('status', card.status, self._font(max(self._font_size - 2, 9), bold=True), r.width() - 18),
        ]
        any_overflow = False
        for key, txt, f, avail_w in fields:
            overflow = QFontMetrics(f).horizontalAdvance(txt) - avail_w
            if overflow <= 0:
                continue
            any_overflow = True
            off = self._marquee_offsets.get(key, 0) + 1
            if off > overflow + 16:
                off = 0
            self._marquee_offsets[key] = off
        if not any_overflow:
            self._marquee_timer.stop()
        self.update()

    def _paint_arrow(
        self, p: QPainter, start: QPointF, end: QPointF,
        color_str: str, alpha: int = 210,
    ):
        c = QColor(color_str)
        c.setAlpha(alpha)

        dx = abs(end.x() - start.x()) * 0.5
        going_right = end.x() > start.x()
        ctrl1 = QPointF(start.x() + (dx if going_right else -dx), start.y())
        ctrl2 = QPointF(end.x()   - (dx if going_right else -dx), end.y())

        path = QPainterPath(start)
        path.cubicTo(ctrl1, ctrl2, end)

        pen = QPen(c, 2.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

        # Arrowhead at the image end
        adx = end.x() - ctrl2.x()
        ady = end.y() - ctrl2.y()
        angle = math.atan2(ady, adx)
        sz = 7
        a1 = QPointF(end.x() - sz * math.cos(angle - 0.42),
                     end.y() - sz * math.sin(angle - 0.42))
        a2 = QPointF(end.x() - sz * math.cos(angle + 0.42),
                     end.y() - sz * math.sin(angle + 0.42))
        head = QPainterPath()
        head.moveTo(end)
        head.lineTo(a1)
        head.lineTo(a2)
        head.closeSubpath()
        p.setBrush(QBrush(c))
        p.setPen(Qt.NoPen)
        p.drawPath(head)

        # Dot at the card end
        p.drawEllipse(start, 4, 4)

    # ── Hit testing ───────────────────────────────────────────────────────────

    def _card_at(self, pos: QPointF) -> Optional[AreaCard]:
        for card in reversed(self._cards):
            if card.rect().contains(pos):
                return card
        return None

    def _dot_at(self, pos: QPointF) -> Optional[AreaCard]:
        """Return the card whose connection dot contains pos, if any. A
        generous hit radius (a bit larger than the drawn dot) makes the dot
        easy to click precisely now that it's the only way to start a line."""
        img = self._img_rect()
        hit_r = _DOT_R + 4
        for card in reversed(self._cards):
            cp = card.connection_point(img)
            dx, dy = pos.x() - cp.x(), pos.y() - cp.y()
            if dx * dx + dy * dy <= hit_r * hit_r:
                return card
        return None

    # ── Mouse events ──────────────────────────────────────────────────────────

    # ── Drag & drop / click-to-upload ───────────────────────────────────────
    _IMPORTABLE_EXTS = ('.jpg', '.jpeg', '.png', '.bmp', '.webp', '.gif', '.heic', '.heif', '.pdf')

    def _dropped_path(self, event) -> Optional[str]:
        """Return the local file path from a drag event's mime data if it's
        a single file with an importable extension, else None."""
        md = event.mimeData()
        if not md.hasUrls():
            return None
        urls = md.urls()
        if len(urls) != 1:
            return None
        path = urls[0].toLocalFile()
        if not path:
            return None
        if os.path.splitext(path)[1].lower() in self._IMPORTABLE_EXTS:
            return path
        return None

    def dragEnterEvent(self, event):
        if self._dropped_path(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._dropped_path(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        path = self._dropped_path(event)
        if path:
            event.acceptProposedAction()
            self.import_image(path)
        else:
            event.ignore()

    def mousePressEvent(self, e):
        pos = QPointF(e.pos()) / self._zoom

        # × button on the loaded image — remove the image
        if (self._x_btn_rect is not None
                and self._x_btn_rect.contains(pos)
                and e.button() == Qt.LeftButton):
            self.remove_image_clicked.emit()
            return

        # Empty canvas (no photo imported yet) — clicking anywhere on the A4
        # frame opens the same file picker as the "Import" button, mirroring
        # the drag-and-drop target below so the whole workspace is clickable.
        # Only when there's no card there — otherwise a card dragged onto the
        # frame area could never be selected (or deleted) again.
        if (self._image is None and self._tool == 'select'
                and self._img_rect().contains(pos) and self._card_at(pos) is None):
            self.upload_requested.emit()
            return

        # Clicking a card's connection dot starts a line; clicking again
        # (either on the image, or on another card's dot) finishes it. This
        # replaces the old dedicated "Line" toolbar button/mode.
        dot_card = self._dot_at(pos)
        if self._line_card is not None:
            img = self._img_rect()
            if img.contains(pos):
                self._push_undo()
                rx = max(0.0, min(1.0, (pos.x() - img.x()) / img.width()))
                ry = max(0.0, min(1.0, (pos.y() - img.y()) / img.height()))
                self._line_card.arrows.append({'rx': rx, 'ry': ry})
                self._line_card = None
                self._line_pos = None
                self.changed.emit()
            elif dot_card is not None:
                self._line_card = dot_card
                self._line_pos = pos
            else:
                self._line_card = None
                self._line_pos = None
            self.update()
            return
        if dot_card is not None:
            self._line_card = dot_card
            self._line_pos = pos
            self.update()
            return

        if self._tool == 'select':
            card = self._card_at(pos)
            self._selected_id = card.id if card else None
            if card:
                self._drag_id = card.id
                self._drag_offset = pos - QPointF(card.x, card.y)
            else:
                self._drag_id = None
            self.update()

        elif self._tool == 'delete':
            card = self._card_at(pos)
            if card:
                self._push_undo()
                self._cards = [c for c in self._cards if c.id != card.id]
                self._selected_id = None
                self.changed.emit()
                self.update()

    def mouseDoubleClickEvent(self, e):
        if self._tool == 'select':
            card = self._card_at(QPointF(e.pos()) / self._zoom)
            if card:
                self._open_edit_dialog(card)

    def mouseMoveEvent(self, e):
        pos = QPointF(e.pos()) / self._zoom

        if self._drag_id and self._tool == 'select':
            card = self._find_card(self._drag_id)
            if card:
                card.x = pos.x() - self._drag_offset.x()
                card.y = pos.y() - self._drag_offset.y()
                self.update()

        elif self._line_card is not None:
            self._line_pos = pos
            self.update()

        else:
            # Cannot see the entire sentence in the panel — scroll the text
            # left on hover (marquee) when any card field is longer than the
            # card itself, same effect as Traceability/Timeline.
            card = self._card_at(pos)
            self.setToolTip(self._overflow_tooltip(card) if card else '')
            self._set_marquee_hover(card)

    def leaveEvent(self, e):
        super().leaveEvent(e)
        self._set_marquee_hover(None)
        self.setToolTip('')

    def _overflow_tooltip(self, card: AreaCard) -> str:
        """Return the full title/supplier/status text if any of it would be
        clipped at the card's current width, else ''."""
        r = card.rect()
        avail_title = r.width() - 52
        avail_body  = r.width() - 18
        lines = []
        fm_title = QFontMetrics(self._font(self._font_size, bold=True))
        if card.title and fm_title.horizontalAdvance(card.title) > avail_title:
            lines.append(card.title)
        fm_body = QFontMetrics(self._font(max(self._font_size - 2, 9)))
        if card.supplier and fm_body.horizontalAdvance(card.supplier) > avail_body:
            lines.append(card.supplier)
        if card.status and fm_body.horizontalAdvance(card.status) > avail_body:
            lines.append(card.status)
        return '\n'.join(lines)

    def mouseReleaseEvent(self, e):
        if self._drag_id and self._tool == 'select':
            self._drag_id = None
            self.changed.emit()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_selected()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _find_card(self, card_id: str) -> Optional[AreaCard]:
        return next((c for c in self._cards if c.id == card_id), None)

    def _open_edit_dialog(self, card: AreaCard):
        dlg = CardEditDialog(card, self.window())
        if dlg.exec_() == QDialog.Accepted:
            self._push_undo()
            card.title = dlg.get_title()
            card.supplier = dlg.get_supplier()
            card.status = dlg.get_status()
            self.changed.emit()
            self.update()

    def _default_position(self, side: str) -> tuple:
        img = self._img_rect()
        existing = [
            c for c in self._cards
            if (c.is_left_of(img) if side == 'left' else not c.is_left_of(img))
        ]
        row = len(existing)
        y = img.y() + 28 + row * (_CARD_H + 18)
        y = min(y, img.bottom() - _CARD_H - 8)

        if side == 'left':
            x = img.x() - _IMG_GAP - _CARD_W
        else:
            x = img.right() + _IMG_GAP
        return x, y

    def _decode_image_file(self, path: str) -> Optional[QPixmap]:
        """Decode any supported source format — including HEIC/HEIF and a
        PDF's first page — into a QPixmap. Pure: no widget state touched.
        Once decoded, the result is what gets embedded as base64 from here
        on, so the original file's format/bytes don't matter again."""
        ext = os.path.splitext(path)[1].lower()
        pix: Optional[QPixmap] = None

        if ext in ('.jpg', '.jpeg', '.png', '.bmp', '.webp', '.gif'):
            pix = QPixmap(path)

        elif ext in ('.heic', '.heif'):
            try:
                from PIL import Image
                import pillow_heif
                pillow_heif.register_heif_opener()
                import io
                img = Image.open(path).convert('RGB')
                buf = io.BytesIO()
                img.save(buf, format='JPEG')
                pix = QPixmap()
                pix.loadFromData(buf.getvalue(), 'JPEG')
            except Exception as ex:
                logger.warning(f'HEIC load failed: {ex}')

        elif ext == '.pdf':
            try:
                import fitz
                doc = fitz.open(path)
                page = doc.load_page(0)
                pmap = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                pix = QPixmap()
                pix.loadFromData(bytes(pmap.tobytes('png')), 'PNG')
            except Exception as ex:
                logger.warning(f'PDF load failed (PyMuPDF not installed?): {ex}')

        return pix if pix and not pix.isNull() else None

    def _load_pixmap(self, path: str) -> bool:
        """Decode a file from disk and adopt it as the canvas image,
        embedding it as base64 immediately — used for a fresh import."""
        pix = self._decode_image_file(path)
        if pix is None:
            return False
        from core.image_utils import pixmap_to_b64
        self._apply_image(pix, os.path.basename(path), pixmap_to_b64(pix) or '')
        return True

    def _apply_image(self, pix: QPixmap, name: str, b64: str):
        self._image = pix
        self._image_name = name
        self._image_b64 = b64
        # Size the frame to the image's own aspect ratio so the full
        # image is shown without being stretched to fit a fixed A4 box
        self._fit_frame_to_image(pix)

    def _restore_image_from_b64(self, b64: str, name: str) -> bool:
        """Adopt an already-embedded image directly (undo/redo, project
        load, sidebar auto-fill) — no re-encoding, no disk access."""
        if not b64:
            return False
        from core.image_utils import b64_to_pixmap
        pix = b64_to_pixmap(b64)
        if pix is None:
            return False
        self._apply_image(pix, name, b64)
        return True

    def _fit_frame_to_image(self, pix: QPixmap):
        """Resize the A4 frame to match the imported image's own aspect
        ratio (capped to the largest extent either A4 preset ever used, so
        the frame stays a similar on-screen size), instead of stretching
        the image to fill a fixed-ratio frame and distorting it."""
        img_w, img_h = pix.width(), pix.height()
        if img_w <= 0 or img_h <= 0:
            return
        scale = min(_A4_W_LANDSCAPE / img_w, _A4_H_PORTRAIT / img_h)
        frame_w = max(1, round(img_w * scale))
        frame_h = max(1, round(img_h * scale))
        self._a4_w, self._a4_h = frame_w, frame_h
        self._base_w = frame_w + 2 * _FRAME_SIDE_MARGIN
        self._base_h = frame_h + 2 * _FRAME_VERT_MARGIN
        orientation = 'landscape' if frame_w >= frame_h else 'portrait'
        changed = orientation != self._orientation
        self._orientation = orientation
        self._apply_zoom_size()
        if changed:
            self.orientation_changed.emit(orientation)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_tool(self, tool: str):
        self._tool = tool
        cursors = {'line': Qt.CrossCursor, 'delete': Qt.ForbiddenCursor}
        self.setCursor(cursors.get(tool, Qt.ArrowCursor))
        self._line_card = None
        self._line_pos = None
        self.update()

    def import_image(self, path: str):
        self._push_undo()
        if self._load_pixmap(path):
            self.changed.emit()
        self.update()

    def import_b64(self, b64: str, name: str = ''):
        """Adopt an already-embedded image directly (e.g. the sidebar's
        auto-filled project photo) — same undo/update wrapping as
        import_image, but no disk access since the bytes are already in
        memory and don't need decoding from a source file format."""
        self._push_undo()
        if self._restore_image_from_b64(b64, name):
            self.changed.emit()
        self.update()

    def remove_image(self):
        """Clear the imported product image. Cards/arrows are kept (arrow
        positions are fractions of the A4 frame, not the image itself, so
        they stay valid — the frame just shows the drop hint again)."""
        if self._image is None:
            return
        self._push_undo()
        self._image = None
        self._image_name = ''
        self._image_b64 = ''
        self.changed.emit()
        self.update()

    def add_card(self):
        n = len(self._cards) + 1
        color = _BADGE_COLORS[(n - 1) % len(_BADGE_COLORS)]
        side = 'left' if n % 2 == 1 else 'right'
        x, y = self._default_position(side)

        card = AreaCard(id=str(uuid.uuid4()), number=n, color=color, x=x, y=y)
        dlg = CardEditDialog(card, self.window())
        if dlg.exec_() != QDialog.Accepted:
            return

        card.title    = dlg.get_title()
        card.supplier = dlg.get_supplier()
        card.status   = dlg.get_status()

        self._push_undo()
        self._cards.append(card)
        self._selected_id = card.id
        self.changed.emit()
        self.update()

    def delete_selected(self):
        if self._selected_id:
            self._push_undo()
            self._cards = [c for c in self._cards if c.id != self._selected_id]
            self._selected_id = None
            self.changed.emit()
            self.update()

    def set_color_selected(self, color: str):
        if self._selected_id:
            card = self._find_card(self._selected_id)
            if card:
                self._push_undo()
                card.color = color
                self.changed.emit()
                self.update()

    def set_font_family(self, family: str):
        self._font_family = family
        self.update()

    def set_font_size(self, size: int):
        self._font_size = size
        self.update()

    def _set_orientation(self, orientation: str):
        if orientation == self._orientation:
            return
        self._orientation = orientation
        if orientation == 'landscape':
            self._a4_w, self._a4_h = _A4_W_LANDSCAPE, _A4_H_LANDSCAPE
            self._base_w, self._base_h = _CANVAS_W_L, _CANVAS_H_L
        else:
            self._a4_w, self._a4_h = _A4_W_PORTRAIT, _A4_H_PORTRAIT
            self._base_w, self._base_h = _CANVAS_W_P, _CANVAS_H_P
        self._apply_zoom_size()
        self.orientation_changed.emit(orientation)

    def toggle_orientation(self):
        if self._image is not None:
            # Frame is locked to the imported image's own aspect ratio —
            # nothing to toggle without stretching the image again.
            return
        target = 'landscape' if self._orientation == 'portrait' else 'portrait'
        self._set_orientation(target)

    def undo(self):
        if self._undo_stack:
            self._redo_stack.append(self._snapshot())
            self._restore(self._undo_stack.pop())
            self.update()

    def redo(self):
        if self._redo_stack:
            self._undo_stack.append(self._snapshot())
            self._restore(self._redo_stack.pop())
            self.update()

    # ── Undo helpers ──────────────────────────────────────────────────────────

    def _snapshot(self) -> dict:
        return {
            'cards': [asdict(c) for c in self._cards],
            'image_name': self._image_name,
            'image_b64': self._image_b64,
            'orientation': self._orientation,
        }

    def _restore(self, state: dict):
        self._cards = [AreaCard(**d) for d in state['cards']]
        name = state.get('image_name', '')
        b64 = state.get('image_b64', '')
        if not self._restore_image_from_b64(b64, name):
            self._image = None
            self._image_name = name
            self._image_b64 = b64
        self._selected_id = None

    def _push_undo(self):
        self._undo_stack.append(self._snapshot())
        self._redo_stack.clear()
        if len(self._undo_stack) > 50:
            self._undo_stack.pop(0)

    # ── Serialisation ─────────────────────────────────────────────────────────

    def get_data(self) -> dict:
        return {
            'id': self._id,
            'cards': [asdict(c) for c in self._cards],
            'image_name': self._image_name,
            'image_b64': self._image_b64,
            'orientation': self._orientation,
            'font_family': self._font_family,
            'font_size': self._font_size,
        }

    def set_data(self, data: dict, idx: int = 0):
        # A save from before tabs had stable ids won't have one — fall back
        # to a positional id so the very first merge after upgrading still
        # matches "the same tab" correctly on both sides (both derive the
        # same fallback from the same list position). Once this session
        # saves, the real id above is what gets stored and compared from
        # then on — see core.project_merge._merge_assignment.
        self._id = data.get('id') or f'tab-{idx}'
        cards = []
        for d in data.get('cards', []):
            d = dict(d)
            # Migrate old single-arrow format
            if 'has_arrow' in d:
                arrows = []
                if d.pop('has_arrow', False):
                    rx = d.pop('arrow_rx', 0.5)
                    ry = d.pop('arrow_ry', 0.5)
                    arrows = [{'rx': rx, 'ry': ry}]
                else:
                    d.pop('arrow_rx', None)
                    d.pop('arrow_ry', None)
                d['arrows'] = arrows
            cards.append(AreaCard(**d))
        self._cards = cards
        from core.image_utils import migrate_path_to_b64
        data = migrate_path_to_b64(data, 'image_path', 'image_b64')
        self._image_name = data.get('image_name', '')
        self._image_b64 = data.get('image_b64', '')
        self._font_family = data.get('font_family', '')
        self._font_size = data.get('font_size', 13)

        # Restore orientation
        orientation = data.get('orientation', 'portrait')
        if orientation != self._orientation:
            self._orientation = orientation
            if orientation == 'landscape':
                self._a4_w, self._a4_h = _A4_W_LANDSCAPE, _A4_H_LANDSCAPE
                self._base_w, self._base_h = _CANVAS_W_L, _CANVAS_H_L
            else:
                self._a4_w, self._a4_h = _A4_W_PORTRAIT, _A4_H_PORTRAIT
                self._base_w, self._base_h = _CANVAS_W_P, _CANVAS_H_P
            self._apply_zoom_size()

        if not self._restore_image_from_b64(self._image_b64, self._image_name):
            # Without this, loading/new-project data with no image left the
            # *previous* project's pixmap still painted, since self._image
            # is a raw attribute here (not a QLabel, where setText()/clear()
            # would implicitly drop the old pixmap).
            self._image = None
        self.update()


# ── Top-level widget ──────────────────────────────────────────────────────────
_TAB_ACTIVE = f"""
    QPushButton {{
        background: {_ACCENT}; color: white;
        border: none; border-radius: 5px;
        font-size: 12px; font-weight: bold; padding: 0 14px;
    }}
"""
_TAB_INACTIVE = f"""
    QPushButton {{
        background: #f3f4f6; color: {_MUTED};
        border: 1px solid {_BORDER}; border-radius: 5px;
        font-size: 12px; padding: 0 14px;
    }}
    QPushButton:hover {{ background: #e5e7eb; color: {_TEXT}; border-color: {_ACCENT}; }}
"""
_TAB_CLOSE = f"""
    QPushButton {{
        background: transparent; color: {_MUTED};
        border: none; border-radius: 3px;
        font-size: 13px; font-weight: bold;
        padding: 0; margin: 0;
    }}
    QPushButton:hover {{ color: #ef4444; background: #fee2e2; }}
"""


class AssignmentWidget(QWidget):
    """The Project — Assignment screen."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tool_btns: dict = {}
        self._orient_btn: Optional[QPushButton] = None
        self._color_btn: Optional[QPushButton] = None
        self._last_auto_photo: str = ''
        self._removed_photo: str = ''

        # Multi-tab state
        self._canvases: List[AssignmentCanvas] = []
        self._scrolls: List[QScrollArea] = []
        self._current_tab: int = 0
        self._tab_bar_layout: Optional[QHBoxLayout] = None
        self._stack: Optional[QStackedWidget] = None

        self._build_ui()

    @property
    def _canvas(self) -> AssignmentCanvas:
        return self._canvases[self._current_tab]

    @property
    def _scroll(self) -> QScrollArea:
        return self._scrolls[self._current_tab]

    def _make_canvas(self) -> AssignmentCanvas:
        canvas = AssignmentCanvas()
        canvas.changed.connect(self.changed)
        canvas.upload_requested.connect(self._on_import)
        canvas.remove_image_clicked.connect(self._on_remove_image)
        canvas.orientation_changed.connect(self._on_canvas_orientation_changed)
        return canvas

    def _make_scroll(self, canvas: AssignmentCanvas) -> QScrollArea:
        sc = QScrollArea()
        sc.setWidget(canvas)
        sc.setWidgetResizable(False)
        sc.setStyleSheet(f'background: {_BG}; border: none;')
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        sc.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        sc.setAlignment(Qt.AlignCenter)
        return sc

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Create first canvas
        first_canvas = self._make_canvas()
        self._canvases.append(first_canvas)
        first_scroll = self._make_scroll(first_canvas)
        self._scrolls.append(first_scroll)

        root.addWidget(self._build_header())
        root.addWidget(self._build_tab_bar())

        body = QWidget()
        body_row = QHBoxLayout(body)
        body_row.setContentsMargins(0, 0, 0, 0)
        body_row.setSpacing(0)
        body_row.addWidget(self._build_toolbar())

        self._stack = QStackedWidget()
        self._stack.addWidget(first_scroll)
        body_row.addWidget(self._stack, 1)

        root.addWidget(body, 1)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._center_scroll)

    def _center_scroll(self):
        sc = self._scroll
        hb = sc.horizontalScrollBar()
        vb = sc.verticalScrollBar()
        hb.setValue((hb.minimum() + hb.maximum()) // 2)
        vb.setValue((vb.minimum() + vb.maximum()) // 2)

    # ── Tab bar ───────────────────────────────────────────────────────────────

    def _build_tab_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(38)
        bar.setStyleSheet(
            f'background: {_CANVAS}; border-bottom: 1px solid {_BORDER};'
        )
        row = QHBoxLayout(bar)
        row.setContentsMargins(10, 5, 10, 5)
        row.setSpacing(6)
        self._tab_bar_layout = row
        self._refresh_tab_bar()
        return bar

    def _refresh_tab_bar(self):
        if self._tab_bar_layout is None:
            return
        # Clear all widgets from layout
        while self._tab_bar_layout.count():
            item = self._tab_bar_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        n = len(self._canvases)
        for i in range(n):
            is_active = (i == self._current_tab)
            container = QWidget()
            container.setStyleSheet('background: transparent;')
            ch = QHBoxLayout(container)
            ch.setContentsMargins(0, 0, 0, 0)
            ch.setSpacing(0)

            tab_btn = QPushButton(f'Plan {i + 1}')
            tab_btn.setFixedHeight(26)
            tab_btn.setCursor(Qt.PointingHandCursor)
            tab_btn.setStyleSheet(_TAB_ACTIVE if is_active else _TAB_INACTIVE)
            tab_btn.clicked.connect(lambda _, idx=i: self._switch_tab(idx))
            ch.addWidget(tab_btn)

            if n > 1:
                close_btn = QPushButton('×')
                close_btn.setFixedSize(20, 26)
                close_btn.setCursor(Qt.PointingHandCursor)
                close_btn.setStyleSheet(_TAB_CLOSE)
                close_btn.clicked.connect(lambda _, idx=i: self._close_tab(idx))
                ch.addWidget(close_btn)

            self._tab_bar_layout.addWidget(container)

        add_btn = QPushButton('+ Plan')
        add_btn.setFixedHeight(26)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setStyleSheet(_TAB_INACTIVE)
        add_btn.clicked.connect(self._add_tab)
        self._tab_bar_layout.addWidget(add_btn)
        self._tab_bar_layout.addStretch()

    def _add_tab(self):
        canvas = self._make_canvas()
        scroll = self._make_scroll(canvas)
        self._canvases.append(canvas)
        self._scrolls.append(scroll)
        self._stack.addWidget(scroll)
        self._switch_tab(len(self._canvases) - 1)

    def _close_tab(self, idx: int):
        if len(self._canvases) <= 1:
            return
        canvas = self._canvases.pop(idx)
        scroll = self._scrolls.pop(idx)
        self._stack.removeWidget(scroll)
        canvas.deleteLater()
        scroll.deleteLater()
        new_idx = min(self._current_tab, len(self._canvases) - 1)
        self._current_tab = -1
        self._switch_tab(new_idx)
        self.changed.emit()

    def _switch_tab(self, idx: int):
        self._current_tab = idx
        self._stack.setCurrentWidget(self._scrolls[idx])
        self._refresh_tab_bar()
        QTimer.singleShot(50, self._center_scroll)

    def _build_header(self) -> QWidget:
        h = QWidget()
        h.setFixedHeight(58)
        h.setStyleSheet(f'background: {_CANVAS}; border-bottom: 1px solid {_BORDER};')
        lay = QVBoxLayout(h)
        lay.setContentsMargins(24, 10, 24, 10)
        lay.setSpacing(2)

        self._title_lbl = QLabel(t('assignment.title'))
        self._title_lbl.setStyleSheet(
            f'color: {_TEXT}; font-size: 18px; font-weight: bold; '
            f'background: transparent; border: none;'
        )
        self._subtitle_lbl = QLabel(t('assignment.subtitle'))
        self._subtitle_lbl.setStyleSheet(
            f'color: {_MUTED}; font-size: 12px; background: transparent; border: none;'
        )
        lay.addWidget(self._title_lbl)
        lay.addWidget(self._subtitle_lbl)
        return h

    def _build_toolbar(self) -> QWidget:
        """Vertical tool column, stacked under the Import button, so the
        drawing/photo area gets the full remaining width instead of losing a
        horizontal strip to the toolbar. The dedicated "Line" tool button is
        gone — clicking directly on a card's (now larger) connection dot
        starts/finishes a line, see AssignmentCanvas._dot_at."""
        bar = QWidget()
        # Wide enough for the longest French label ("Importer un fichier",
        # "Supprimer la carte", ...) — 150px clipped button text in French.
        bar.setFixedWidth(200)
        bar.setStyleSheet(f'background: {_CANVAS}; border-right: 1px solid {_BORDER};')
        col = QVBoxLayout(bar)
        col.setContentsMargins(10, 12, 10, 12)
        col.setSpacing(8)

        imp_btn = QPushButton('⬆  ' + t('assignment.import_btn'))
        imp_btn.setStyleSheet(_BTN_PRIMARY)
        imp_btn.setFixedHeight(30)
        imp_btn.setCursor(Qt.PointingHandCursor)
        imp_btn.setToolTip(t('assignment.import_tooltip'))
        imp_btn.clicked.connect(self._on_import)
        col.addWidget(imp_btn)

        col.addWidget(self._hsep())

        add_btn = QPushButton('+ ' + t('assignment.add_area'))
        add_btn.setStyleSheet(_BTN)
        add_btn.setFixedHeight(30)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setToolTip(t('assignment.add_area_tooltip'))
        add_btn.clicked.connect(lambda: self._canvas.add_card())
        col.addWidget(add_btn)

        undo_btn = QPushButton('↩ ' + t('assignment.undo'))
        undo_btn.setStyleSheet(_BTN)
        undo_btn.setFixedHeight(30)
        undo_btn.setCursor(Qt.PointingHandCursor)
        undo_btn.clicked.connect(self._canvas.undo)
        col.addWidget(undo_btn)

        redo_btn = QPushButton('↪ ' + t('assignment.redo'))
        redo_btn.setStyleSheet(_BTN)
        redo_btn.setFixedHeight(30)
        redo_btn.setCursor(Qt.PointingHandCursor)
        redo_btn.clicked.connect(self._canvas.redo)
        col.addWidget(redo_btn)

        del_btn = QPushButton('🗑 ' + t('assignment.delete_card'))
        del_btn.setStyleSheet(_BTN)
        del_btn.setFixedHeight(30)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setToolTip(t('assignment.delete_tooltip'))
        del_btn.clicked.connect(self._canvas.delete_selected)
        col.addWidget(del_btn)

        col.addWidget(self._hsep())

        clr_lbl = QLabel(t('assignment.color_label'))
        clr_lbl.setStyleSheet(f'color: {_MUTED}; font-size: 12px; background: transparent;')
        col.addWidget(clr_lbl)

        self._color_btn = QPushButton('🎨  ' + t('assignment.pick_color'))
        self._color_btn.setFixedHeight(30)
        self._color_btn.setStyleSheet(f"""
            QPushButton {{
                background: #f3f4f6; color: {_TEXT};
                border: 1px solid {_BORDER}; border-radius: 6px;
                font-size: 12px; padding: 0 12px;
            }}
            QPushButton:hover {{ background: #e5e7eb; border-color: {_ACCENT}; }}
        """ + TOOLTIP_STYLE)
        self._color_btn.setCursor(Qt.PointingHandCursor)
        self._color_btn.setToolTip(t('assignment.pick_color_tooltip'))
        self._color_btn.clicked.connect(self._on_color_btn_clicked)
        col.addWidget(self._color_btn)

        col.addWidget(self._hsep())

        self._orient_btn = QPushButton('⇄  ' + t('assignment.landscape'))
        self._orient_btn.setStyleSheet(_BTN)
        self._orient_btn.setFixedHeight(30)
        self._orient_btn.setCursor(Qt.PointingHandCursor)
        self._orient_btn.setToolTip(t('assignment.orientation_tooltip'))
        self._orient_btn.clicked.connect(self._toggle_orientation)
        col.addWidget(self._orient_btn)

        col.addStretch()
        return bar

    def _build_style_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(42)
        bar.setStyleSheet(f'background: {_CANVAS}; border-bottom: 1px solid {_BORDER};')
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 0, 16, 0)
        row.setSpacing(8)

        # ── Color picker ──────────────────────────────────────────────────────
        clr_lbl = QLabel(t('assignment.color_label'))
        clr_lbl.setStyleSheet(f'color: {_MUTED}; font-size: 12px; background: transparent;')
        row.addWidget(clr_lbl)

        self._color_btn = QPushButton('🎨  ' + t('assignment.pick_color'))
        self._color_btn.setFixedHeight(28)
        self._color_btn.setStyleSheet(f"""
            QPushButton {{
                background: #f3f4f6; color: {_TEXT};
                border: 1px solid {_BORDER}; border-radius: 6px;
                font-size: 12px; padding: 0 12px;
            }}
            QPushButton:hover {{ background: #e5e7eb; border-color: {_ACCENT}; }}
        """ + TOOLTIP_STYLE)
        self._color_btn.setCursor(Qt.PointingHandCursor)
        self._color_btn.setToolTip(t('assignment.pick_color_tooltip'))
        self._color_btn.clicked.connect(self._on_color_btn_clicked)
        row.addWidget(self._color_btn)

        row.addWidget(self._vsep())

        # ── Orientation toggle ────────────────────────────────────────────────
        self._orient_btn = QPushButton('⇄  ' + t('assignment.landscape'))
        self._orient_btn.setStyleSheet(_BTN)
        self._orient_btn.setFixedHeight(28)
        self._orient_btn.setCursor(Qt.PointingHandCursor)
        self._orient_btn.setToolTip(t('assignment.orientation_tooltip'))
        self._orient_btn.clicked.connect(self._toggle_orientation)
        row.addWidget(self._orient_btn)

        row.addStretch()
        return bar

    def _vsep(self) -> QFrame:
        s = QFrame()
        s.setFrameShape(QFrame.VLine)
        s.setFixedHeight(20)
        s.setStyleSheet(
            f'color: {_BORDER}; background: {_BORDER}; max-width: 1px; border: none;'
        )
        return s

    def _hsep(self) -> QFrame:
        s = QFrame()
        s.setFrameShape(QFrame.HLine)
        s.setFixedHeight(1)
        s.setStyleSheet(
            f'color: {_BORDER}; background: {_BORDER}; max-height: 1px; border: none;'
        )
        return s

    def _toggle_tool(self, tool: str):
        if self._canvas._tool == tool:
            self._canvas.set_tool('select')
            for btn in self._tool_btns.values():
                btn.setChecked(False)
        else:
            self._canvas.set_tool(tool)
            for k, btn in self._tool_btns.items():
                btn.setChecked(k == tool)

    def _on_canvas_orientation_changed(self, orientation: str):
        if self._orient_btn is not None:
            self._orient_btn.setText(
                '⇅  ' + t('assignment.portrait') if orientation == 'landscape'
                else '⇄  ' + t('assignment.landscape')
            )
        QTimer.singleShot(50, self._center_scroll)

    def _toggle_orientation(self):
        self._canvas.toggle_orientation()

    def _on_color_btn_clicked(self):
        from ui.draw_color_picker import DrawColorPicker
        picker = DrawColorPicker(self)
        picker.color_selected.connect(self._canvas.set_color_selected)
        global_pos = self._color_btn.mapToGlobal(self._color_btn.rect().bottomLeft())
        picker.move(global_pos)
        picker.show()

    def _on_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            t('assignment.import_title'),
            '',
            'Images (*.jpg *.jpeg *.png *.heic *.heif *.pdf)',
        )
        if path:
            self._removed_photo = ''
            self._canvas.import_image(path)

    # ── Project widget API ────────────────────────────────────────────────────

    def update_project_info(self, info: dict):
        """Copy the sidebar's main project photo into the active canvas as its
        background image, unless the user has already imported a different one."""
        photo = (info.get('photo_b64') or '').strip()
        current = self._canvas._image_b64 or ''
        if photo == self._removed_photo:
            return
        if photo and photo != current and current == self._last_auto_photo:
            self._canvas.import_b64(photo)
            self._last_auto_photo = photo
        elif photo and not current:
            self._canvas.import_b64(photo)
            self._last_auto_photo = photo

    def _on_remove_image(self):
        """Remove the image and remember it so auto-fill doesn't restore it."""
        self._removed_photo = self._canvas._image_b64 or ''
        self._canvas.remove_image()

    def get_data(self) -> dict:
        tabs = [c.get_data() for c in self._canvases]
        return {'tabs': tabs, 'current_tab': self._current_tab}

    def set_data(self, data: dict):
        if 'tabs' not in data:
            # Legacy single-canvas save — wrap it
            tabs_data = [data]
            current_tab = 0
        else:
            tabs_data = data.get('tabs', [{}])
            current_tab = data.get('current_tab', 0)

        # Build the correct number of canvases
        needed = len(tabs_data)
        # Add canvases if we need more than the initial one
        while len(self._canvases) < needed:
            canvas = self._make_canvas()
            scroll = self._make_scroll(canvas)
            self._canvases.append(canvas)
            self._scrolls.append(scroll)
            self._stack.addWidget(scroll)
        # Remove extras if saved data has fewer tabs than current state
        while len(self._canvases) > needed:
            canvas = self._canvases.pop()
            scroll = self._scrolls.pop()
            self._stack.removeWidget(scroll)
            canvas.deleteLater()
            scroll.deleteLater()

        for i, td in enumerate(tabs_data):
            self._canvases[i].set_data(td, idx=i)

        self._current_tab = max(0, min(current_tab, len(self._canvases) - 1))
        self._stack.setCurrentWidget(self._scrolls[self._current_tab])
        self._refresh_tab_bar()

        # Sync orient button label to the active canvas
        orientation = self._canvas._orientation
        if self._orient_btn is not None:
            self._orient_btn.setText(
                '⇅  ' + t('assignment.portrait') if orientation == 'landscape'
                else '⇄  ' + t('assignment.landscape')
            )
        QTimer.singleShot(100, self._center_scroll)

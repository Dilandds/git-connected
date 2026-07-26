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
_CARD_W, _CARD_H = 148, 88
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


# ── Drawing canvas ────────────────────────────────────────────────────────────
class AssignmentCanvas(QWidget):
    """The interactive paint surface — A4 frame + area cards + bezier arrows."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._orientation: str = 'portrait'
        self._a4_w: int = _A4_W_PORTRAIT
        self._a4_h: int = _A4_H_PORTRAIT
        self._font_family: str = ''
        self._font_size: int = 10
        self.setFixedSize(_CANVAS_W_P, _CANVAS_H_P)
        self.setMouseTracking(True)
        self.setCursor(Qt.ArrowCursor)
        self.setFocusPolicy(Qt.StrongFocus)

        self._image: Optional[QPixmap] = None
        self._image_name: str = ''
        self._image_path: str = ''
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
        x = (self.width() - self._a4_w) / 2
        y = (self.height() - self._a4_h) / 2
        return QRectF(x, y, self._a4_w, self._a4_h)

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        p.fillRect(self.rect(), QColor(_BG))

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
        else:
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
        orient_label = 'A4 Portrait' if self._orientation == 'portrait' else 'A4 Landscape'
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
        badge = QRectF(r.x() + 9, r.y() + 9, 22, 22)
        p.setBrush(QBrush(QColor(card.color)))
        p.setPen(Qt.NoPen)
        p.drawEllipse(badge)
        p.setPen(QColor('#ffffff'))
        p.setFont(self._font(9, bold=True))
        p.drawText(badge, Qt.AlignCenter, str(card.number))

        # Arrow count badge (show if >1 arrow)
        if len(card.arrows) > 1:
            ab = QRectF(r.right() - 18, r.y() + 4, 14, 14)
            p.setBrush(QBrush(QColor('#6b7280')))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(ab, 7, 7)
            p.setPen(QColor('#ffffff'))
            p.setFont(self._font(7, bold=True))
            p.drawText(ab, Qt.AlignCenter, str(len(card.arrows)))

        # Title
        p.setPen(QColor(_TEXT))
        p.setFont(self._font(self._font_size, bold=True))
        p.drawText(
            QRectF(r.x() + 38, r.y() + 8, r.width() - 46, 24),
            Qt.AlignLeft | Qt.AlignVCenter,
            card.title or '—',
        )

        # Supplier / task
        p.setPen(QColor(_MUTED))
        p.setFont(self._font(max(self._font_size - 1, 7)))
        p.drawText(
            QRectF(r.x() + 9, r.y() + 37, r.width() - 18, 18),
            Qt.AlignLeft | Qt.AlignVCenter,
            card.supplier,
        )

        # Status
        p.setPen(QColor(_STATUS_COLORS.get(card.status, _MUTED)))
        p.setFont(self._font(max(self._font_size - 1, 7), bold=True))
        p.drawText(
            QRectF(r.x() + 9, r.y() + 57, r.width() - 18, 18),
            Qt.AlignLeft | Qt.AlignVCenter,
            card.status,
        )

        # Connection dot on the edge facing the image — click it directly to
        # start/finish a line (no separate "Line" tool needed).
        cp = card.connection_point(img_rect)
        p.setBrush(QBrush(QColor(card.color)))
        p.setPen(QPen(QColor('#ffffff'), 1.5))
        p.drawEllipse(cp, _DOT_R, _DOT_R)

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

    def mousePressEvent(self, e):
        pos = QPointF(e.pos())

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
            card = self._card_at(QPointF(e.pos()))
            if card:
                self._open_edit_dialog(card)

    def mouseMoveEvent(self, e):
        pos = QPointF(e.pos())

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
            # Cannot see the entire sentence in the panel — show the full text
            # on hover when any card field is longer than the card itself.
            card = self._card_at(pos)
            self.setToolTip(self._overflow_tooltip(card) if card else '')

    def _overflow_tooltip(self, card: AreaCard) -> str:
        """Return the full title/supplier/status text if any of it would be
        clipped at the card's current width, else ''."""
        r = card.rect()
        avail_title = r.width() - 46
        avail_body  = r.width() - 18
        lines = []
        fm_title = QFontMetrics(self._font(self._font_size, bold=True))
        if card.title and fm_title.horizontalAdvance(card.title) > avail_title:
            lines.append(card.title)
        fm_body = QFontMetrics(self._font(max(self._font_size - 1, 7)))
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

    def _load_pixmap(self, path: str) -> bool:
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

        if pix and not pix.isNull():
            self._image = pix
            self._image_name = os.path.basename(path)
            self._image_path = path
            return True
        return False

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

    def toggle_orientation(self):
        if self._orientation == 'portrait':
            self._orientation = 'landscape'
            self._a4_w = _A4_W_LANDSCAPE
            self._a4_h = _A4_H_LANDSCAPE
            self.setFixedSize(_CANVAS_W_L, _CANVAS_H_L)
        else:
            self._orientation = 'portrait'
            self._a4_w = _A4_W_PORTRAIT
            self._a4_h = _A4_H_PORTRAIT
            self.setFixedSize(_CANVAS_W_P, _CANVAS_H_P)
        self.update()

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
            'image_path': self._image_path,
            'orientation': self._orientation,
        }

    def _restore(self, state: dict):
        self._cards = [AreaCard(**d) for d in state['cards']]
        self._image_name = state.get('image_name', '')
        self._selected_id = None

    def _push_undo(self):
        self._undo_stack.append(self._snapshot())
        self._redo_stack.clear()
        if len(self._undo_stack) > 50:
            self._undo_stack.pop(0)

    # ── Serialisation ─────────────────────────────────────────────────────────

    def get_data(self) -> dict:
        return {
            'cards': [asdict(c) for c in self._cards],
            'image_name': self._image_name,
            'image_path': self._image_path,
            'orientation': self._orientation,
            'font_family': self._font_family,
            'font_size': self._font_size,
        }

    def set_data(self, data: dict):
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
        self._image_name = data.get('image_name', '')
        self._image_path = data.get('image_path', '')
        self._font_family = data.get('font_family', '')
        self._font_size = data.get('font_size', 10)

        # Restore orientation
        orientation = data.get('orientation', 'portrait')
        if orientation != self._orientation:
            self._orientation = orientation
            if orientation == 'landscape':
                self._a4_w, self._a4_h = _A4_W_LANDSCAPE, _A4_H_LANDSCAPE
                self.setFixedSize(_CANVAS_W_L, _CANVAS_H_L)
            else:
                self._a4_w, self._a4_h = _A4_W_PORTRAIT, _A4_H_PORTRAIT
                self.setFixedSize(_CANVAS_W_P, _CANVAS_H_P)

        if self._image_path:
            self._load_pixmap(self._image_path)
        self.update()


# ── Top-level widget ──────────────────────────────────────────────────────────
class AssignmentWidget(QWidget):
    """The Project — Assignment screen."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tool_btns: dict = {}
        self._scroll: Optional[QScrollArea] = None
        self._orient_btn: Optional[QPushButton] = None
        self._color_btn: Optional[QPushButton] = None
        self._last_auto_photo: str = ''
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._canvas = AssignmentCanvas()
        self._canvas.changed.connect(self.changed)

        root.addWidget(self._build_header())

        body = QWidget()
        body_row = QHBoxLayout(body)
        body_row.setContentsMargins(0, 0, 0, 0)
        body_row.setSpacing(0)
        body_row.addWidget(self._build_toolbar())

        self._scroll = QScrollArea()
        self._scroll.setWidget(self._canvas)
        self._scroll.setWidgetResizable(False)
        self._scroll.setStyleSheet(f'background: {_BG}; border: none;')
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setAlignment(Qt.AlignCenter)
        body_row.addWidget(self._scroll, 1)

        root.addWidget(body, 1)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._center_scroll)

    def _center_scroll(self):
        if self._scroll is None:
            return
        hb = self._scroll.horizontalScrollBar()
        vb = self._scroll.verticalScrollBar()
        hb.setValue((hb.minimum() + hb.maximum()) // 2)
        vb.setValue((vb.minimum() + vb.maximum()) // 2)

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
        bar.setFixedWidth(150)
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

        del_btn = QPushButton('🗑 ' + t('assignment.delete'))
        del_btn.setStyleSheet(_BTN)
        del_btn.setFixedHeight(30)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setToolTip(t('assignment.delete_tooltip'))
        del_btn.clicked.connect(self._canvas.delete_selected)
        col.addWidget(del_btn)

        col.addWidget(self._hsep())

        clr_lbl = QLabel('Color:')
        clr_lbl.setStyleSheet(f'color: {_MUTED}; font-size: 12px; background: transparent;')
        col.addWidget(clr_lbl)

        self._color_btn = QPushButton('🎨  Pick color')
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
        self._color_btn.setToolTip('Pick a color for the selected card')
        self._color_btn.clicked.connect(self._on_color_btn_clicked)
        col.addWidget(self._color_btn)

        col.addWidget(self._hsep())

        self._orient_btn = QPushButton('⇄  Landscape')
        self._orient_btn.setStyleSheet(_BTN)
        self._orient_btn.setFixedHeight(30)
        self._orient_btn.setCursor(Qt.PointingHandCursor)
        self._orient_btn.setToolTip('Toggle between A4 portrait and landscape')
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
        clr_lbl = QLabel('Color:')
        clr_lbl.setStyleSheet(f'color: {_MUTED}; font-size: 12px; background: transparent;')
        row.addWidget(clr_lbl)

        self._color_btn = QPushButton('🎨  Pick color')
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
        self._color_btn.setToolTip('Pick a color for the selected card')
        self._color_btn.clicked.connect(self._on_color_btn_clicked)
        row.addWidget(self._color_btn)

        row.addWidget(self._vsep())

        # ── Orientation toggle ────────────────────────────────────────────────
        self._orient_btn = QPushButton('⇄  Landscape')
        self._orient_btn.setStyleSheet(_BTN)
        self._orient_btn.setFixedHeight(28)
        self._orient_btn.setCursor(Qt.PointingHandCursor)
        self._orient_btn.setToolTip('Toggle between A4 portrait and landscape')
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

    def _toggle_orientation(self):
        self._canvas.toggle_orientation()
        if self._canvas._orientation == 'landscape':
            self._orient_btn.setText('⇅  Portrait')
        else:
            self._orient_btn.setText('⇄  Landscape')
        QTimer.singleShot(50, self._center_scroll)

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
            self._canvas.import_image(path)

    # ── Project widget API ────────────────────────────────────────────────────

    def update_project_info(self, info: dict):
        """Copy the sidebar's main project photo into the assignment canvas
        as its background image, unless the user has already imported a
        different image of their own. Mirrors the auto-fill-unless-manually-
        changed pattern used by the Brief/Report/Traceability screens."""
        photo = (info.get('photo_path') or '').strip()
        current = self._canvas._image_path or ''
        if photo and photo != current and current == self._last_auto_photo:
            self._canvas.import_image(photo)
            self._last_auto_photo = photo
        elif photo and not current:
            self._canvas.import_image(photo)
            self._last_auto_photo = photo

    def get_data(self) -> dict:
        return self._canvas.get_data()

    def set_data(self, data: dict):
        self._canvas.set_data(data)
        orientation = data.get('orientation', 'portrait')
        if self._orient_btn is not None:
            self._orient_btn.setText('⇅  Portrait' if orientation == 'landscape' else '⇄  Landscape')
        QTimer.singleShot(100, self._center_scroll)

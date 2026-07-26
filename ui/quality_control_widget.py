"""
Quality Control Inspection Panel — part of The Project section.

3-column layout:
  Left   — Live 3D viewer + standard-view thumbnail strip + inspection metadata
  Center — Control Points checklist (numbered items with status)
  Right  — Company / Part Information + overall status

The live viewer widget is temporarily reparented into the left panel while
this screen is visible, then restored to its original QStackedWidget when
hidden. This avoids any extra OpenGL context or model re-loading.
"""
from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from PyQt5.QtCore import Qt, pyqtSignal, QDate, QRectF, QPointF, QSize, QTimer
from PyQt5.QtGui import (
    QColor, QPainter, QPixmap, QFont,
    QIcon, QPen, QBrush, QPainterPath, QPolygonF,
)
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QScrollArea, QFrame, QSizePolicy,
    QFileDialog, QDateEdit, QCheckBox, QMenu, QAction, QStackedWidget,
)

from ui.styles import default_theme

logger = logging.getLogger(__name__)

# ── light palette ─────────────────────────────────────────────────────────────
_BG          = '#f8f9fb'
_SURFACE     = '#ffffff'
_BORDER      = '#e5e7eb'
_BORDER_DARK = '#d1d5db'
_TEXT        = '#111827'
_MUTED       = '#6b7280'
_ACCENT      = default_theme.button_primary

_BADGE_PALETTE = [
    '#22c55e', '#f59e0b', '#ef4444', '#3b82f6',
    '#a855f7', '#06b6d4', '#ec4899', '#84cc16',
]

_STATUS_META = {
    'compliant':     ('Compliant',     '#dcfce7', '#16a34a'),
    'to_check':      ('To Check',      '#fef3c7', '#b45309'),
    'non_compliant': ('Non-compliant', '#fee2e2', '#dc2626'),
}

_INPUT = f"""
    QLineEdit {{
        background: {_SURFACE}; color: {_TEXT};
        border: 1px solid {_BORDER_DARK}; border-radius: 6px;
        padding: 6px 10px; font-size: 13px;
    }}
    QLineEdit:focus {{ border-color: {_ACCENT}; }}
"""

_TEXTEDIT = f"""
    QTextEdit {{
        background: {_SURFACE}; color: {_TEXT};
        border: 1px solid {_BORDER_DARK}; border-radius: 6px;
        padding: 6px 10px; font-size: 13px;
    }}
    QTextEdit:focus {{ border-color: {_ACCENT}; }}
"""


def _make_tb_icon(name: str, size: int = 18, color: str = '#111827') -> QIcon:
    """Draw a toolbar icon with QPainter and return as QIcon."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    s = float(size)

    if name == 'select':
        p.setPen(QPen(c, 1.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(QBrush(c))
        path = QPainterPath()
        path.moveTo(s*0.20, s*0.10)
        path.lineTo(s*0.20, s*0.80)
        path.lineTo(s*0.42, s*0.60)
        path.lineTo(s*0.55, s*0.88)
        path.lineTo(s*0.65, s*0.83)
        path.lineTo(s*0.52, s*0.55)
        path.lineTo(s*0.72, s*0.55)
        path.closeSubpath()
        p.drawPath(path)

    elif name == 'pan':
        # Four-directional move/pan arrows
        p.setPen(QPen(c, 1.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(QBrush(c))
        cx, cy = s * 0.5, s * 0.5
        reach = s * 0.38   # tip of each arrow from center
        ah = s * 0.16      # arrowhead height
        aw = s * 0.10      # arrowhead half-width
        for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
            tx, ty = cx + dx * reach, cy + dy * reach
            bx, by = tx - dx * ah,   ty - dy * ah
            px, py = -dy * aw, dx * aw
            path = QPainterPath()
            path.moveTo(tx, ty)
            path.lineTo(bx + px, by + py)
            path.lineTo(bx - px, by - py)
            path.closeSubpath()
            p.drawPath(path)
        # Cross lines connecting arrow bases
        p.setPen(QPen(c, 1.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        gap = s * 0.12
        p.drawLine(QPointF(cx, cy - reach + ah), QPointF(cx, cy - gap))
        p.drawLine(QPointF(cx, cy + gap),         QPointF(cx, cy + reach - ah))
        p.drawLine(QPointF(cx - reach + ah, cy), QPointF(cx - gap, cy))
        p.drawLine(QPointF(cx + gap, cy),         QPointF(cx + reach - ah, cy))

    elif name in ('zoom_in', 'zoom_out'):
        pen = QPen(c, 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        cx, cy, r = s*0.40, s*0.40, s*0.28
        p.drawEllipse(QRectF(cx - r, cy - r, 2*r, 2*r))
        p.drawLine(QPointF(cx + r*0.72, cy + r*0.72), QPointF(s*0.88, s*0.88))
        bar = r * 0.55
        p.drawLine(QPointF(cx - bar, cy), QPointF(cx + bar, cy))
        if name == 'zoom_in':
            p.drawLine(QPointF(cx, cy - bar), QPointF(cx, cy + bar))

    elif name == 'fit':
        p.setPen(QPen(c, 1.3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        for pts in [
            [QPointF(s*.50, s*.10), QPointF(s*.85, s*.30), QPointF(s*.50, s*.50), QPointF(s*.15, s*.30)],
            [QPointF(s*.15, s*.30), QPointF(s*.50, s*.50), QPointF(s*.50, s*.90), QPointF(s*.15, s*.70)],
            [QPointF(s*.50, s*.50), QPointF(s*.85, s*.30), QPointF(s*.85, s*.70), QPointF(s*.50, s*.90)],
        ]:
            p.drawPolygon(QPolygonF(pts))

    elif name == 'camera':
        p.setPen(QPen(c, 1.3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(s*0.08, s*0.28, s*0.84, s*0.54), 2, 2)
        p.drawEllipse(QRectF(s*0.30, s*0.36, s*0.40, s*0.38))
        p.drawRoundedRect(QRectF(s*0.33, s*0.18, s*0.22, s*0.12), 2, 2)

    elif name == 'fullscreen':
        p.setPen(QPen(c, 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        m, d = s*0.12, s*0.25
        for ax, ay, bx, by in [
            (m, m+d, m, m), (m, m, m+d, m),            # top-left
            (s-m-d, m, s-m, m), (s-m, m, s-m, m+d),    # top-right
            (m, s-m-d, m, s-m), (m, s-m, m+d, s-m),    # bottom-left
            (s-m-d, s-m, s-m, s-m), (s-m, s-m, s-m, s-m-d),  # bottom-right
        ]:
            p.drawLine(QPointF(ax, ay), QPointF(bx, by))

    p.end()
    return QIcon(pix)

_DATE = f"""
    QDateEdit {{
        background: {_SURFACE}; color: {_TEXT};
        border: 1px solid {_BORDER_DARK}; border-radius: 6px;
        padding: 6px 10px; font-size: 13px;
    }}
    QDateEdit:focus {{ border-color: {_ACCENT}; }}
    QDateEdit::drop-down {{ border: none; width: 20px; }}
    QDateEdit::down-arrow {{ width: 10px; height: 10px; }}
"""

_SECTION_TITLE = f"font-size: 15px; font-weight: 700; color: {_TEXT}; background: transparent;"
_LABEL_STYLE   = f"font-size: 12px; color: {_MUTED}; background: transparent;"


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class ControlPoint:
    id: int
    name: str
    status: str = 'to_check'
    comment: str = ''
    annotation_id: Optional[int] = None
    color: str = ''

    def to_dict(self) -> dict:
        return {
            'id': self.id, 'name': self.name, 'status': self.status,
            'comment': self.comment, 'annotation_id': self.annotation_id,
            'color': self.color,
        }

    @staticmethod
    def from_dict(d: dict) -> 'ControlPoint':
        return ControlPoint(
            id=d.get('id', 0), name=d.get('name', ''),
            status=d.get('status', 'to_check'), comment=d.get('comment', ''),
            annotation_id=d.get('annotation_id'), color=d.get('color', ''),
        )


@dataclass
class QCData:
    control_points: List[ControlPoint] = field(default_factory=list)
    inspection_date: str = ''
    inspected_by: str = ''
    comments: str = ''
    designation: str = ''
    reference_number: str = ''
    manufacturer: str = ''
    logo_data: str = ''
    inspection_due_date: str = ''
    overall_status: str = ''
    waived_by: str = ''
    multi_view_snapshots: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'control_points': [cp.to_dict() for cp in self.control_points],
            'inspection_date': self.inspection_date,
            'inspected_by': self.inspected_by,
            'comments': self.comments,
            'designation': self.designation,
            'reference_number': self.reference_number,
            'manufacturer': self.manufacturer,
            'logo_data': self.logo_data,
            'inspection_due_date': self.inspection_due_date,
            'overall_status': self.overall_status,
            'waived_by': self.waived_by,
            'multi_view_snapshots': self.multi_view_snapshots,
        }

    @staticmethod
    def from_dict(d: dict) -> 'QCData':
        return QCData(
            control_points=[ControlPoint.from_dict(c) for c in d.get('control_points', [])],
            inspection_date=d.get('inspection_date', ''),
            inspected_by=d.get('inspected_by', ''),
            comments=d.get('comments', ''),
            designation=d.get('designation', ''),
            reference_number=d.get('reference_number', ''),
            manufacturer=d.get('manufacturer', ''),
            logo_data=d.get('logo_data', ''),
            inspection_due_date=d.get('inspection_due_date', ''),
            overall_status=d.get('overall_status', ''),
            waived_by=d.get('waived_by', ''),
            multi_view_snapshots=d.get('multi_view_snapshots', []),
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(_SECTION_TITLE)
    return lbl


def _make_field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(_LABEL_STYLE)
    return lbl


def _badge_pixmap(text: str, color: str, size: int = 28) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.NoPen)
    p.drawEllipse(0, 0, size, size)
    p.setPen(QColor('white'))
    f = QFont()
    f.setPointSize(10)
    f.setBold(True)
    p.setFont(f)
    p.drawText(0, 0, size, size, Qt.AlignCenter, text)
    p.end()
    return pix


def _pixmap_to_b64(pix: QPixmap) -> str:
    from PyQt5.QtCore import QBuffer, QIODevice
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    pix.save(buf, 'PNG')
    buf.close()
    return base64.b64encode(bytes(buf.data())).decode()


def _b64_to_pixmap(data: str) -> Optional[QPixmap]:
    try:
        raw = base64.b64decode(data)
        pix = QPixmap()
        pix.loadFromData(raw, 'PNG')
        return pix if not pix.isNull() else None
    except Exception:
        return None


def _vsep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.VLine)
    f.setStyleSheet(f'background: {_BORDER}; max-width: 1px; border: none;')
    return f


def _hsep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f'background: {_BORDER_DARK}; max-height: 1px; border: none;')
    return f


# ── _ControlPointCard ─────────────────────────────────────────────────────────

class _ControlPointCard(QWidget):
    changed = pyqtSignal()
    delete_requested = pyqtSignal(int)

    def __init__(self, cp: ControlPoint, parent=None):
        super().__init__(parent)
        self._cp = cp
        # Start collapsed so the QTextEdit (comment_edit) is never shown during
        # card construction.  On macOS, setVisible(True) on a QTextEdit triggers
        # full NSTextView initialisation (~150ms), which blocks the click-event
        # handler long enough for the OS gesture recogniser to reclassify the
        # trackpad tap as a swipe, switching Spaces in full-screen mode.
        self._expanded = False
        logger.debug('[QC Card] __init__ PRE-build  id=%d', cp.id)
        self._build_ui()
        logger.debug('[QC Card] __init__ POST-build  id=%d', cp.id)
        # The comment field should be visible without an extra click — but
        # showing the QTextEdit synchronously here (still inside whatever
        # click handler created this card) risks the same macOS Mission
        # Control Space-switch bug the collapsed-by-default workaround above
        # exists to avoid. Deferring the reveal to the next event-loop tick
        # keeps that protection while still auto-expanding.
        QTimer.singleShot(0, self._reveal_comment)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {_SURFACE};
                border: 1px solid {_BORDER};
                border-radius: 8px;
            }}
        """)
        card_l = QVBoxLayout(card)
        card_l.setContentsMargins(12, 10, 12, 10)
        card_l.setSpacing(8)

        # Header row
        header = QWidget()
        header.setStyleSheet('background: transparent; border: none;')
        header_l = QHBoxLayout(header)
        header_l.setContentsMargins(0, 0, 0, 0)
        header_l.setSpacing(8)

        self._badge = QPushButton()
        self._badge.setFixedSize(28, 28)
        self._badge.setFlat(True)
        self._badge.setFocusPolicy(Qt.NoFocus)
        self._badge.setCursor(Qt.PointingHandCursor)
        self._badge.setToolTip('Click to change color')
        self._badge.setStyleSheet('border: none; background: transparent; padding: 0;')
        self._badge.clicked.connect(self._pick_color)
        self._refresh_badge()
        header_l.addWidget(self._badge)

        self._name_edit = QLineEdit(self._cp.name)
        self._name_edit.setPlaceholderText('Control point name...')
        self._name_edit.setStyleSheet(_INPUT)
        # ClickFocus prevents the new QLineEdit from auto-grabbing keyboard focus
        # when it is inserted into a layout — on macOS full-screen mode an automatic
        # focus grab triggers an NSWindow first-responder change that causes macOS
        # to switch Spaces.
        self._name_edit.setFocusPolicy(Qt.ClickFocus)
        logger.debug('[QC Card] name_edit focusPolicy=%s', int(self._name_edit.focusPolicy()))
        self._name_edit.textChanged.connect(self._on_name_changed)
        header_l.addWidget(self._name_edit, 1)

        self._status_btn = QPushButton()
        self._status_btn.setFixedHeight(28)
        self._status_btn.setCursor(Qt.PointingHandCursor)
        self._status_btn.clicked.connect(self._show_status_menu)
        self._refresh_status_btn()
        header_l.addWidget(self._status_btn)

        del_btn = QPushButton('×')
        del_btn.setFixedSize(26, 26)
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {_MUTED};
                border: none; font-size: 16px; font-weight: bold;
            }}
            QPushButton:hover {{ color: #ef4444; }}
        """)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._cp.id))
        header_l.addWidget(del_btn)

        card_l.addWidget(header)

        self._comment_edit = QTextEdit()
        self._comment_edit.setPlaceholderText('Enter your comments...')
        self._comment_edit.setFixedHeight(58)
        self._comment_edit.setStyleSheet(_TEXTEDIT)
        self._comment_edit.setFocusPolicy(Qt.ClickFocus)
        logger.debug('[QC Card] comment_edit focusPolicy=%s', int(self._comment_edit.focusPolicy()))

        import time as _time
        _t = _time.perf_counter()
        self._comment_edit.setText(self._cp.comment)
        logger.debug('[QC Card] setText took %.0fms', (_time.perf_counter() - _t) * 1000)

        self._comment_edit.textChanged.connect(self._on_comment_changed)

        _t = _time.perf_counter()
        self._comment_edit.setVisible(self._expanded)
        logger.debug('[QC Card] setVisible(%s) took %.0fms', self._expanded, (_time.perf_counter() - _t) * 1000)

        _t = _time.perf_counter()
        card_l.addWidget(self._comment_edit)
        logger.debug('[QC Card] addWidget(comment) took %.0fms', (_time.perf_counter() - _t) * 1000)

        _t = _time.perf_counter()
        outer.addWidget(card)
        logger.debug('[QC Card] addWidget(card) took %.0fms', (_time.perf_counter() - _t) * 1000)

    def _refresh_badge(self):
        color = self._cp.color or _BADGE_PALETTE[self._cp.id % len(_BADGE_PALETTE)]
        from PyQt5.QtGui import QIcon
        self._badge.setIcon(QIcon(_badge_pixmap(str(self._cp.id), color)))
        self._badge.setIconSize(self._badge.size())

    def _pick_color(self):
        from ui.draw_color_picker import DrawColorPicker
        picker = DrawColorPicker(self)
        picker.color_selected.connect(self._on_color_picked)
        # Position popup below-left of the badge
        pos = self._badge.mapToGlobal(self._badge.rect().bottomLeft())
        picker.move(pos)
        picker.show()

    def _on_color_picked(self, hex_color: str):
        self._cp = self._cp.__class__(
            id=self._cp.id,
            name=self._cp.name,
            status=self._cp.status,
            comment=self._cp.comment,
            annotation_id=self._cp.annotation_id,
            color=hex_color,
        )
        self._refresh_badge()
        self.changed.emit()

    def _refresh_status_btn(self):
        label, bg, fg = _STATUS_META.get(self._cp.status, ('To Check', '#fef3c7', '#b45309'))
        self._status_btn.setText(label)
        self._status_btn.setStyleSheet(f"""
            QPushButton {{
                background: {bg}; color: {fg};
                border: 1px solid {fg}55; border-radius: 5px;
                padding: 2px 10px; font-size: 12px; font-weight: 600;
                min-width: 100px;
            }}
        """)

    def _show_status_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {_SURFACE}; border: 1px solid {_BORDER};
                border-radius: 8px; padding: 4px;
            }}
            QMenu::item {{
                color: {_TEXT}; padding: 7px 18px;
                border-radius: 5px; font-size: 13px;
            }}
            QMenu::item:selected {{ background: {_BG}; }}
        """)
        for key, (label, bg, fg) in _STATUS_META.items():
            act = QAction(label, self)
            act.setData(key)
            menu.addAction(act)
        chosen = menu.exec_(self._status_btn.mapToGlobal(self._status_btn.rect().bottomLeft()))
        if chosen:
            self._cp.status = chosen.data()
            self._refresh_status_btn()
            self.changed.emit()

    def _reveal_comment(self):
        """Show the comment field automatically — no arrow/click needed."""
        self._expanded = True
        self._comment_edit.setVisible(True)

    def _on_name_changed(self, text: str):
        self._cp.name = text
        self.changed.emit()

    def _on_comment_changed(self):
        self._cp.comment = self._comment_edit.toPlainText()
        self.changed.emit()

    def set_number(self, n: int):
        self._cp.id = n
        self._refresh_badge()

    def get_data(self) -> ControlPoint:
        return self._cp


# ── _ControlPointsPanel ───────────────────────────────────────────────────────

class _ControlPointsPanel(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: list[_ControlPointCard] = []
        self._next_id = 1
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f'background: {_BG};')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(14)

        hdr = QWidget()
        hdr.setStyleSheet('background: transparent;')
        hdr_l = QHBoxLayout(hdr)
        hdr_l.setContentsMargins(0, 0, 0, 0)
        hdr_l.setSpacing(8)

        lbl = QLabel('Control Points')
        lbl.setStyleSheet(_SECTION_TITLE)
        hdr_l.addWidget(lbl)

        self._count_lbl = QLabel('0')
        self._count_lbl.setFixedSize(24, 24)
        self._count_lbl.setAlignment(Qt.AlignCenter)
        self._count_lbl.setStyleSheet(f"""
            background: {_ACCENT}; color: white;
            border-radius: 12px; font-size: 11px; font-weight: bold;
        """)
        hdr_l.addWidget(self._count_lbl)
        hdr_l.addStretch()
        layout.addWidget(hdr)

        layout.addWidget(_hsep())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{
                background: transparent; width: 6px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {_BORDER_DARK}; border-radius: 3px; min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        self._cards_container = QWidget()
        self._cards_container.setStyleSheet('background: transparent;')
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 4, 8, 4)
        self._cards_layout.setSpacing(8)
        self._cards_layout.addStretch()

        scroll.setWidget(self._cards_container)
        layout.addWidget(scroll, 1)

        # ── Instruction card ──────────────────────────────────────────────
        instr = QFrame()
        instr.setStyleSheet(f"""
            QFrame {{
                background: {_SURFACE};
                border: 1px solid {_BORDER_DARK};
                border-radius: 8px;
            }}
        """)
        instr_l = QVBoxLayout(instr)
        instr_l.setContentsMargins(14, 12, 14, 12)
        instr_l.setSpacing(6)

        def _instr_label(text, bold=False, color=None):
            lbl = QLabel(text)
            lbl.setWordWrap(True)
            lbl.setStyleSheet(
                f'background: transparent; border: none; '
                f'color: {color or _MUTED}; '
                f'font-size: 12px; '
                f'{"font-weight: 600;" if bold else ""}'
            )
            return lbl

        instr_l.addWidget(_instr_label('How to add control points', bold=True, color=_TEXT))

        steps = [
            ('1', 'Capture an image',
             'Press the \U0001f4f7 camera button in the viewer toolbar — '
             'or drag & drop an image onto the drop zone below.'),
            ('2', 'Switch to Image View',
             'Click a thumbnail in the Inspection Images strip. '
             'The viewer switches from 3D Model to Image View.'),
            ('3', 'Place a marker on the image',
             'Click once on the inspection point (anchor), '
             'then click again where the number label should appear. '
             'A numbered marker is placed and a control point is added here automatically.'),
        ]
        for num, title, body in steps:
            row = QWidget()
            row.setStyleSheet('background: transparent; border: none;')
            row_l = QHBoxLayout(row)
            row_l.setContentsMargins(0, 2, 0, 2)
            row_l.setSpacing(10)

            badge = QLabel(num)
            badge.setFixedSize(20, 20)
            badge.setAlignment(Qt.AlignCenter)
            badge.setStyleSheet(f"""
                background: {_ACCENT}; color: white;
                border-radius: 10px; font-size: 11px; font-weight: bold;
                border: none;
            """)
            row_l.addWidget(badge, 0, Qt.AlignTop)

            txt = QWidget()
            txt.setStyleSheet('background: transparent; border: none;')
            txt_l = QVBoxLayout(txt)
            txt_l.setContentsMargins(0, 0, 0, 0)
            txt_l.setSpacing(1)
            txt_l.addWidget(_instr_label(title, bold=True, color=_TEXT))
            txt_l.addWidget(_instr_label(body))
            row_l.addWidget(txt, 1)
            instr_l.addWidget(row)

        note = _instr_label(
            'ℹ️  To return to the 3D model, press the ■ 3D button '
            'in the viewer toolbar.',
            color='#6b7280',
        )
        note.setStyleSheet(
            note.styleSheet() + 'padding-top: 4px;'
        )
        instr_l.addWidget(note)
        layout.addWidget(instr)

    def _add_point(self, cp: Optional[ControlPoint] = None):
        from PyQt5.QtWidgets import QApplication as _QApp
        _app = _QApp.instance()
        _aw = _app.activeWindow()
        _fw = _app.focusWidget()
        logger.debug(
            '[QC add_point] START  activeWindow=%s  focusWidget=%s  cards=%d',
            type(_aw).__name__ if _aw else None,
            type(_fw).__name__ if _fw else None,
            len(self._cards),
        )

        if cp is None:
            color = _BADGE_PALETTE[(self._next_id - 1) % len(_BADGE_PALETTE)]
            cp = ControlPoint(id=self._next_id, name='', status='to_check', color=color)
        card = _ControlPointCard(cp, self)
        card.changed.connect(self.changed)
        card.delete_requested.connect(self._delete_card)
        idx = self._cards_layout.count() - 1

        logger.debug('[QC add_point] PRE-INSERT  idx=%d', idx)
        self._cards_layout.insertWidget(idx, card)

        _aw2 = _app.activeWindow()
        _fw2 = _app.focusWidget()
        _top = self.window()
        logger.debug(
            '[QC add_point] POST-INSERT  activeWindow=%s  focusWidget=%s'
            '  fullscreen=%s  windowActive=%s  windowFlags=0x%x',
            type(_aw2).__name__ if _aw2 else None,
            type(_fw2).__name__ if _fw2 else None,
            _top.isFullScreen(),
            _top.isActiveWindow(),
            int(_top.windowFlags()),
        )

        self._cards.append(card)
        self._next_id = max(self._next_id, cp.id) + 1
        self._refresh_count()
        self.changed.emit()
        logger.debug('[QC add_point] END  cards=%d', len(self._cards))

    def _delete_card(self, cp_id: int):
        for card in self._cards:
            if card.get_data().id == cp_id:
                self._cards_layout.removeWidget(card)
                card.deleteLater()
                self._cards.remove(card)
                break
        self._renumber()
        self._refresh_count()
        self.changed.emit()

    def _renumber(self):
        for i, card in enumerate(self._cards, 1):
            card.set_number(i)

    def _refresh_count(self):
        self._count_lbl.setText(str(len(self._cards)))

    def get_control_points(self) -> List[ControlPoint]:
        return [c.get_data() for c in self._cards]

    def set_control_points(self, points: List[ControlPoint]):
        for card in self._cards:
            self._cards_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()
        self._next_id = 1
        for cp in points:
            self._add_point(cp)


# ── Image annotation view ────────────────────────────────────────────────────

class _ImageAnnotationView(QWidget):
    """Shows an inspection image with two-click leader-line annotation.

    Click 1 — anchor dot (the exact point being inspected).
    Click 2 — badge/number position (where the callout label lands).
    Right-click cancels a pending first click.
    """
    # dot_xf, dot_yf, badge_xf, badge_yf — all fractions of image rect
    point_added = pyqtSignal(float, float, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: Optional[QPixmap] = None
        self._annotations: list = []       # [(dot_xf, dot_yf, badge_xf, badge_yf), ...]
        self._pending_dot: Optional[tuple] = None   # (x_frac, y_frac) after first click
        self._mouse_pos = None             # QPoint — live preview target
        self._zoom = 1.0                   # 1.0 = fit to view, up to 4.0
        self._pan = QPointF(0, 0)          # extra offset (px) applied when zoomed in
        self._panning = False
        self._pan_start = None
        self._pan_start_offset = None
        self.setMinimumSize(100, 100)
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)
        # NoFocus: clicking the canvas must not change the NSWindow first-responder.
        # Any first-responder change in a macOS full-screen window can cause
        # Mission Control to switch the user to a different Space.
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet('background: transparent;')
        self.setToolTip('Scroll to zoom · middle-click drag to pan')

    def set_image(self, pixmap: Optional[QPixmap]):
        self._pixmap = pixmap
        self._pending_dot = None
        self._zoom = 1.0
        self._pan = QPointF(0, 0)
        self.update()

    def set_annotations(self, annotations: list):
        self._annotations = list(annotations)
        self._pending_dot = None
        self.update()

    def _base_img_rect(self):
        """Image rect fitted (unzoomed) to the current widget size."""
        from PyQt5.QtCore import QRect
        if self._pixmap is None or self._pixmap.isNull():
            return QRect()
        sw, sh = self._pixmap.width(), self._pixmap.height()
        ww, wh = self.width(), self.height()
        scale = min(ww / sw, wh / sh)
        nw, nh = int(sw * scale), int(sh * scale)
        return QRect((ww - nw) // 2, (wh - nh) // 2, nw, nh)

    def _img_rect(self):
        """Current on-screen image rect, including zoom + pan."""
        from PyQt5.QtCore import QRect
        base = self._base_img_rect()
        if base.isNull() or (self._zoom == 1.0 and self._pan.isNull()):
            return base
        cx = base.center().x() + self._pan.x()
        cy = base.center().y() + self._pan.y()
        nw = int(base.width()  * self._zoom)
        nh = int(base.height() * self._zoom)
        return QRect(int(cx - nw / 2), int(cy - nh / 2), nw, nh)

    def wheelEvent(self, event):
        """Scroll to zoom the inspection image, centered on the cursor."""
        if self._pixmap is None or self._pixmap.isNull():
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return
        old_rect = self._img_rect()
        if old_rect.isNull() or old_rect.width() == 0 or old_rect.height() == 0:
            return
        cursor = event.pos()
        fx = (cursor.x() - old_rect.x()) / old_rect.width()
        fy = (cursor.y() - old_rect.y()) / old_rect.height()
        factor = 1.15 if delta > 0 else (1 / 1.15)
        new_zoom = max(1.0, min(4.0, self._zoom * factor))
        if new_zoom == self._zoom:
            return
        self._zoom = new_zoom
        if self._zoom <= 1.0001:
            self._zoom = 1.0
            self._pan = QPointF(0, 0)
        else:
            base = self._base_img_rect()
            new_w = base.width()  * self._zoom
            new_h = base.height() * self._zoom
            new_cx = (cursor.x() - fx * new_w) + new_w / 2
            new_cy = (cursor.y() - fy * new_h) + new_h / 2
            self._pan = QPointF(new_cx - base.center().x(), new_cy - base.center().y())
        self.update()

    def mouseMoveEvent(self, event):
        if self._panning and self._pan_start is not None:
            delta = event.pos() - self._pan_start
            self._pan = QPointF(self._pan_start_offset.x() + delta.x(),
                                 self._pan_start_offset.y() + delta.y())
            self.update()
            return
        self._mouse_pos = event.pos()
        if self._pending_dot is not None:
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton and self._panning:
            self._panning = False
            self.setCursor(Qt.CrossCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            # Pan when zoomed in — only useful once the image is larger than the view.
            if self._zoom > 1.0:
                self._panning = True
                self._pan_start = event.pos()
                self._pan_start_offset = QPointF(self._pan)
                self.setCursor(Qt.ClosedHandCursor)
            return
        if event.button() == Qt.RightButton:
            self._pending_dot = None
            # Defer repaint — synchronous update() inside a mouse press can
            # trigger an NSWindow first-responder cycle on macOS full-screen
            # that causes Mission Control to switch Spaces.
            QTimer.singleShot(0, self.update)
            return
        if event.button() != Qt.LeftButton:
            return
        r = self._img_rect()
        if r.isNull() or not r.contains(event.pos()):
            return
        x_frac = (event.x() - r.x()) / r.width()
        y_frac = (event.y() - r.y()) / r.height()
        if self._pending_dot is None:
            # First click: mark the anchor dot, wait for second click
            self._pending_dot = (x_frac, y_frac)
            QTimer.singleShot(0, self.update)
        else:
            # Second click: badge position → defer the emit to the next
            # event-loop tick so that all downstream effects (widget
            # creation, layout changes) happen AFTER the mouse press has
            # fully returned to macOS.  Doing any layout work synchronously
            # inside a mousePressEvent triggers NSView geometry updates that
            # macOS full-screen interprets as a window-activation, switching
            # the user to a different Space.
            dot_xf, dot_yf = self._pending_dot
            self._pending_dot = None
            QTimer.singleShot(0,
                lambda dxf=dot_xf, dyf=dot_yf, bxf=x_frac, byf=y_frac:
                    self.point_added.emit(dxf, dyf, bxf, byf)
            )

    def paintEvent(self, event):
        from PyQt5.QtCore import QRect
        from PyQt5.QtGui import QFont as _QFont
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(_BG))

        r = self._img_rect()
        if not r.isNull() and self._pixmap:
            p.drawPixmap(r, self._pixmap)

            BADGE_R = 14
            DOT_R   = 4

            # Draw committed annotations
            for i, ann in enumerate(self._annotations):
                dot_xf, dot_yf, badge_xf, badge_yf = ann
                mx = r.x() + int(dot_xf   * r.width())
                my = r.y() + int(dot_yf   * r.height())
                bx = r.x() + int(badge_xf * r.width())
                by = r.y() + int(badge_yf * r.height())
                color = QColor(_BADGE_PALETTE[i % len(_BADGE_PALETTE)])

                # Leader line
                p.setPen(QPen(color, 1.5, Qt.SolidLine))
                p.setBrush(Qt.NoBrush)
                p.drawLine(QPointF(mx, my), QPointF(bx, by))

                # Anchor dot
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(color))
                p.drawEllipse(QPointF(mx, my), DOT_R, DOT_R)

                # Badge circle
                p.setPen(QPen(QColor('#ffffff'), 1.5))
                p.setBrush(QBrush(color))
                p.drawEllipse(QPointF(bx, by), BADGE_R, BADGE_R)

                # Badge number
                p.setPen(QPen(QColor('#ffffff')))
                f = _QFont('Calibri', 9)
                f.setBold(True)
                p.setFont(f)
                p.drawText(
                    QRect(int(bx - BADGE_R), int(by - BADGE_R),
                          BADGE_R * 2, BADGE_R * 2),
                    Qt.AlignCenter, str(i + 1)
                )

            # Draw pending first click: dot + dashed preview line to cursor
            if self._pending_dot is not None:
                next_color = QColor(_BADGE_PALETTE[len(self._annotations) % len(_BADGE_PALETTE)])
                mx = r.x() + int(self._pending_dot[0] * r.width())
                my = r.y() + int(self._pending_dot[1] * r.height())

                if self._mouse_pos is not None:
                    pen = QPen(next_color, 1.5, Qt.DashLine)
                    p.setPen(pen)
                    p.setBrush(Qt.NoBrush)
                    p.drawLine(QPointF(mx, my),
                               QPointF(self._mouse_pos.x(), self._mouse_pos.y()))

                # Pending dot (slightly larger ring to indicate "awaiting second click")
                p.setPen(QPen(QColor('#ffffff'), 1.5))
                p.setBrush(QBrush(next_color))
                p.drawEllipse(QPointF(mx, my), DOT_R + 2, DOT_R + 2)
        else:
            p.setPen(QColor(_MUTED))
            p.drawText(self.rect(), Qt.AlignCenter,
                       'Click an image below to annotate')
        p.end()


# ── Inspection Images helpers ─────────────────────────────────────────────────

_TOOLTIP_SS = """
    QToolTip {
        background: #ffffff; color: #111827;
        border: 1px solid #e5e7eb; border-radius: 4px;
        padding: 4px 8px; font-size: 11px;
    }
"""


class _InspectionDropZone(QLabel):
    """Dashed-border drop zone for dragging or browsing inspection images."""
    paths_chosen = pyqtSignal(list)

    _IDLE_SS = f"""
        QLabel {{
            background: {_SURFACE};
            border: 1.5px dashed {_BORDER_DARK};
            border-radius: 8px; color: {_MUTED}; font-size: 12px;
        }}
        QLabel:hover {{ border-color: {_ACCENT}; }}
    """
    _HOVER_SS = f"""
        QLabel {{
            background: #f0f7ff;
            border: 1.5px dashed {_ACCENT};
            border-radius: 8px; color: {_MUTED}; font-size: 12px;
        }}
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(68)
        self.setCursor(Qt.PointingHandCursor)
        self.setTextFormat(Qt.RichText)
        self.setText(
            'Drag &amp; drop images here<br/>'
            f'<span style="color:{_ACCENT};">or click to browse</span>'
        )
        self.setStyleSheet(self._IDLE_SS)

    def mousePressEvent(self, event):
        paths, _ = QFileDialog.getOpenFileNames(
            self, 'Select Images', '',
            'Images (*.png *.jpg *.jpeg *.bmp *.webp)'
        )
        if paths:
            self.paths_chosen.emit(paths)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet(self._HOVER_SS)

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self._IDLE_SS)

    def dropEvent(self, event):
        self.setStyleSheet(self._IDLE_SS)
        paths = [u.toLocalFile() for u in event.mimeData().urls()
                 if u.toLocalFile().lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp'))]
        if paths:
            self.paths_chosen.emit(paths)


class _DeleteBtn(QPushButton):
    """Circular delete button that paints its own × via QPainter (no font dependency)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(22, 22)
        self.setCursor(Qt.PointingHandCursor)
        self._hovered = False
        self.setStyleSheet("""
            QPushButton { background: transparent; border: none; }
        """)

    def enterEvent(self, event):
        self._hovered = True
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        bg = QColor('#dc2626') if self._hovered else QColor('#4b5563')
        p.setBrush(QBrush(bg))
        p.setPen(QPen(QColor('#ffffff'), 1.8))
        p.drawEllipse(1, 1, 20, 20)
        p.setPen(QPen(QColor('#ffffff'), 2.0, Qt.SolidLine, Qt.RoundCap))
        m = 6
        p.drawLine(m, m, 22 - m, 22 - m)
        p.drawLine(22 - m, m, m, 22 - m)
        p.end()


class _InspHoverPreview(QLabel):
    """Floating enlarged preview shown while hovering an inspection thumbnail."""

    _SIZE = 240

    def __init__(self, pixmap: QPixmap):
        super().__init__(None, Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        scaled = pixmap.scaled(self._SIZE, self._SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(scaled)
        self.setStyleSheet(
            f'background: {_SURFACE}; border: 2px solid {_ACCENT}; border-radius: 10px; padding: 4px;'
        )
        self.setFixedSize(scaled.size().width() + 12, scaled.size().height() + 12)

    def show_near(self, global_pos):
        # Offset so the preview appears above-right of the cursor without covering the thumbnail.
        self.move(global_pos.x() + 16, global_pos.y() - self.height() - 16)
        self.show()
        self.raise_()


class _InspThumbCard(QFrame):
    """Single inspection image thumbnail with an × delete button and click-to-view.

    On hover, an enlarged floating preview of the image is shown next to the cursor.
    """
    delete_requested = pyqtSignal()
    image_clicked    = pyqtSignal()

    _IDLE_SS   = f'QFrame {{ background: {_SURFACE}; border: 1px solid {_BORDER}; border-radius: 8px; }}'
    _ACTIVE_SS = f'QFrame {{ background: {_SURFACE}; border: 2px solid {_ACCENT}; border-radius: 8px; }}'

    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.setFixedSize(84, 84)
        self.setStyleSheet(self._IDLE_SS)
        self.setMouseTracking(True)
        self._pixmap = pixmap
        self._hover_preview: Optional[_InspHoverPreview] = None

        img = QLabel(self)
        img.setGeometry(2, 2, 80, 80)
        img.setAlignment(Qt.AlignCenter)
        scaled = pixmap.scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        img.setPixmap(scaled)
        img.setStyleSheet('border: none; background: transparent;')
        img.setCursor(Qt.PointingHandCursor)
        img.mousePressEvent = lambda e: self.image_clicked.emit()
        img.setMouseTracking(True)
        img.enterEvent = self._on_hover_enter
        img.leaveEvent = self._on_hover_leave

        del_btn = _DeleteBtn(self)
        del_btn.move(64, -2)
        del_btn.clicked.connect(self.delete_requested)
        del_btn.raise_()

    def set_active(self, active: bool):
        self.setStyleSheet(self._ACTIVE_SS if active else self._IDLE_SS)

    def _on_hover_enter(self, event):
        if self._hover_preview is None:
            self._hover_preview = _InspHoverPreview(self._pixmap)
        self._hover_preview.show_near(self.mapToGlobal(self.rect().topRight()))

    def _on_hover_leave(self, event):
        if self._hover_preview is not None:
            self._hover_preview.hide()

    def leaveEvent(self, event):
        if self._hover_preview is not None:
            self._hover_preview.hide()
        super().leaveEvent(event)


# ── _QCLeftPanel ──────────────────────────────────────────────────────────────


class _QCLeftPanel(QWidget):
    """Left column: live 3D viewer + standard-view toolbar + thumbnail strip + inspection metadata."""
    changed              = pyqtSignal()
    fullscreen_requested = pyqtSignal(bool)
    model_selected       = pyqtSignal(int)
    annotation_added     = pyqtSignal(int)   # emitted with annotation number (1-based) when image point placed

    def __init__(self, parent=None):
        super().__init__(parent)
        self._viewer_ref         = None
        self._orig_stacked       = None
        self._orig_idx           = -1
        self._inspection_images: list[str]        = []   # base64 PNGs
        self._image_annotations: list[list]       = []   # per-image [(x_frac, y_frac), ...]
        self._active_img_idx: int                 = -1   # -1 = 3D mode
        self._thumb_cards: list                   = []   # _InspThumbCard instances
        self._model_pills: list                   = []
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        self.setStyleSheet(f'background: {_BG};')
        self.setFixedWidth(560)   # widened — bigger 3D inspection view of the photo

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Title row
        title_w = QWidget()
        title_w.setStyleSheet('background: transparent;')
        title_l = QVBoxLayout(title_w)
        title_l.setContentsMargins(0, 0, 0, 0)
        title_l.setSpacing(2)
        title_l.addWidget(_make_section_label('3D Inspection'))
        hint = QLabel('Select an area to view inspection details')
        hint.setStyleSheet(f'color: {_MUTED}; font-size: 12px; background: transparent;')
        title_l.addWidget(hint)
        layout.addWidget(title_w)

        # ── Model selector strip (hidden when only 1 model loaded) ────────────
        self._model_selector_w = QWidget()
        self._model_selector_w.setStyleSheet('background: transparent;')
        self._model_selector_l = QHBoxLayout(self._model_selector_w)
        self._model_selector_l.setContentsMargins(0, 0, 0, 0)
        self._model_selector_l.setSpacing(4)
        self._model_selector_w.hide()
        layout.addWidget(self._model_selector_w)

        # ── Viewer area: [left toolbar] + [viewer host / bottom toolbar] ──────
        viewer_row = QWidget()
        viewer_row.setStyleSheet('background: transparent;')
        viewer_row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        viewer_row_l = QHBoxLayout(viewer_row)
        viewer_row_l.setContentsMargins(0, 0, 0, 0)
        viewer_row_l.setSpacing(6)

        viewer_row_l.addWidget(self._build_left_toolbar())

        # Viewer column
        viewer_col = QWidget()
        viewer_col.setStyleSheet('background: transparent;')
        viewer_col.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        viewer_col_l = QVBoxLayout(viewer_col)
        viewer_col_l.setContentsMargins(0, 0, 0, 0)
        viewer_col_l.setSpacing(4)

        # Viewer host — contains a mode stack: page 0 = 3D viewer, page 1 = image annotation
        self._viewer_host = QWidget()
        self._viewer_host.setMinimumHeight(220)
        self._viewer_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._viewer_host.setStyleSheet(f"""
            QWidget#qcViewerHost {{
                background: {_SURFACE};
                border: 1px solid {_BORDER};
                border-radius: 10px;
            }}
        """)
        self._viewer_host.setObjectName('qcViewerHost')
        vh_outer = QVBoxLayout(self._viewer_host)
        vh_outer.setContentsMargins(0, 0, 0, 0)
        vh_outer.setSpacing(0)

        # Mode badge — floats at top-left of viewer host, updates on mode switch
        self._mode_badge = QLabel('3D Model')
        self._mode_badge.setStyleSheet(f"""
            background: #1d4ed8; color: white;
            border-radius: 10px; font-size: 10px; font-weight: 700;
            padding: 3px 10px; border: none;
        """)
        self._mode_badge.setAlignment(Qt.AlignCenter)
        mode_row = QWidget()
        mode_row.setStyleSheet('background: transparent; border: none;')
        mode_row_l = QHBoxLayout(mode_row)
        mode_row_l.setContentsMargins(8, 6, 8, 0)
        mode_row_l.addWidget(self._mode_badge)
        mode_row_l.addStretch()
        vh_outer.addWidget(mode_row)

        self._mode_stack = QStackedWidget()
        self._mode_stack.setStyleSheet('background: transparent; border: none;')
        vh_outer.addWidget(self._mode_stack)

        # Page 0 — 3D viewer page
        self._3d_page = QWidget()
        self._3d_page.setStyleSheet('background: transparent;')
        self._3d_page_layout = QVBoxLayout(self._3d_page)
        self._3d_page_layout.setContentsMargins(0, 0, 0, 0)
        self._3d_page_layout.setSpacing(0)
        self._placeholder = QLabel('No model loaded')
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setStyleSheet(
            f'color: {_MUTED}; font-size: 13px; background: transparent; border: none;'
        )
        self._3d_page_layout.addWidget(self._placeholder)
        self._mode_stack.addWidget(self._3d_page)   # index 0

        # Page 1 — image annotation page
        self._img_view = _ImageAnnotationView()
        self._img_view.point_added.connect(self._on_image_point_added)
        self._mode_stack.addWidget(self._img_view)   # index 1

        viewer_col_l.addWidget(self._viewer_host, 1)

        viewer_col_l.addWidget(self._build_bottom_toolbar())
        viewer_row_l.addWidget(viewer_col, 1)
        layout.addWidget(viewer_row, 1)

        # ── Inspection Images ─────────────────────────────────────────────────
        layout.addWidget(_make_section_label('Inspection Images'))

        self._drop_zone = _InspectionDropZone()
        self._drop_zone.paths_chosen.connect(self._add_images_from_paths)
        layout.addWidget(self._drop_zone)

        # Scrollable thumbnail strip
        self._insp_scroll = QScrollArea()
        self._insp_scroll.setWidgetResizable(True)
        self._insp_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._insp_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._insp_scroll.setFixedHeight(100)
        self._insp_scroll.setStyleSheet('background: transparent; border: none;')

        self._insp_container = QWidget()
        self._insp_container.setStyleSheet('background: transparent;')
        self._insp_layout = QHBoxLayout(self._insp_container)
        self._insp_layout.setContentsMargins(0, 4, 0, 4)
        self._insp_layout.setSpacing(8)
        self._insp_layout.addStretch()

        self._insp_scroll.setWidget(self._insp_container)
        layout.addWidget(self._insp_scroll)
        layout.addWidget(_hsep())

        # ── Inspection metadata ───────────────────────────────────────────────
        row1 = QWidget()
        row1.setStyleSheet('background: transparent;')
        row1_l = QHBoxLayout(row1)
        row1_l.setContentsMargins(0, 0, 0, 0)
        row1_l.setSpacing(12)

        def _col(*widgets):
            w = QWidget()
            w.setStyleSheet('background: transparent;')
            l = QVBoxLayout(w)
            l.setContentsMargins(0, 0, 0, 0)
            l.setSpacing(4)
            for ww in widgets:
                l.addWidget(ww)
            return w

        self._date_edit = QDateEdit(QDate.currentDate())
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat('dd/MM/yyyy')
        self._date_edit.setStyleSheet(_DATE)
        self._date_edit.dateChanged.connect(lambda _: self.changed.emit())

        self._inspected_by = QLineEdit()
        self._inspected_by.setPlaceholderText('Inspector name...')
        self._inspected_by.setStyleSheet(_INPUT)
        self._inspected_by.textChanged.connect(lambda _: self.changed.emit())

        row1_l.addWidget(_col(_make_field_label('Inspection Date'), self._date_edit), 1)
        row1_l.addWidget(_col(_make_field_label('Inspected By'), self._inspected_by), 1)
        layout.addWidget(row1)

        layout.addWidget(_make_field_label('Comments'))
        self._comments = QTextEdit()
        self._comments.setPlaceholderText('Enter your comments...')
        self._comments.setFixedHeight(56)
        self._comments.setStyleSheet(_TEXTEDIT)
        self._comments.textChanged.connect(lambda: self.changed.emit())
        layout.addWidget(self._comments)

    # ── Toolbar builders ──────────────────────────────────────────────────────

    def _build_left_toolbar(self) -> QWidget:
        """Vertical tool strip — intentionally empty; the Select/Pan/Zoom/Fit
        buttons were removed as clutter (mouse drag/scroll already does this
        directly on the 3D viewport). Kept as a zero-width spacer so the
        layout math elsewhere in this class doesn't need to change."""
        w = QWidget()
        w.setFixedWidth(0)
        w.setStyleSheet('background: transparent;')
        return w

    def _build_bottom_toolbar(self) -> QWidget:
        """Horizontal view strip — trimmed down to just capture + fullscreen.
        The 3D/Front/Right/Back/Top view-snap buttons were removed as
        clutter; clicking an already-active inspection-image thumbnail now
        returns to the 3D view instead (see _toggle_image)."""
        w = QWidget()
        w.setStyleSheet('background: transparent;')
        l = QHBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(3)

        snap_btn = QPushButton()
        snap_btn.setFixedHeight(26)
        snap_btn.setFixedWidth(30)
        snap_btn.setToolTip('Capture current view to thumbnail strip')
        snap_btn.setCursor(Qt.PointingHandCursor)
        snap_btn.setIcon(_make_tb_icon('camera', 16))
        snap_btn.setIconSize(QSize(16, 16))
        snap_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_SURFACE}; border: 1px solid {_BORDER}; border-radius: 5px;
            }}
            QPushButton:hover {{ background: {_BG}; border-color: {_BORDER_DARK}; }}
        """ + _TOOLTIP_SS)
        snap_btn.clicked.connect(self._capture_current_view)

        self._fullscreen_btn = QPushButton()
        self._fullscreen_btn.setFixedHeight(26)
        self._fullscreen_btn.setFixedWidth(30)
        self._fullscreen_btn.setToolTip('Toggle fullscreen viewer')
        self._fullscreen_btn.setCursor(Qt.PointingHandCursor)
        self._fullscreen_btn.setCheckable(True)
        self._fullscreen_btn.setIcon(_make_tb_icon('fullscreen', 16))
        self._fullscreen_btn.setIconSize(QSize(16, 16))
        self._fullscreen_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_SURFACE}; border: 1px solid {_BORDER}; border-radius: 5px;
            }}
            QPushButton:hover {{ background: {_BG}; border-color: {_BORDER_DARK}; }}
            QPushButton:checked {{ background: #eff6ff; border-color: #2596BE; }}
        """ + _TOOLTIP_SS)
        self._fullscreen_btn.clicked.connect(
            lambda: self.fullscreen_requested.emit(self._fullscreen_btn.isChecked()))

        for item in (snap_btn, self._fullscreen_btn):
            l.addWidget(item)
        l.addStretch()
        return w

    # ── Model selector ────────────────────────────────────────────────────────

    def set_model_list(self, labels: list, current_idx: int):
        """Rebuild the pill selector strip. Hidden when len(labels) <= 1."""
        # Clear old pills
        while self._model_selector_l.count():
            item = self._model_selector_l.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._model_pills.clear()

        for i, label in enumerate(labels):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(i == current_idx)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {_SURFACE}; color: {_MUTED};
                    border: 1px solid {_BORDER}; border-radius: 12px;
                    padding: 3px 12px; font-size: 11px; font-weight: 500;
                }}
                QPushButton:checked {{
                    background: #eff6ff; color: #2596BE;
                    border-color: #2596BE; font-weight: 700;
                }}
                QPushButton:hover:!checked {{
                    border-color: {_BORDER_DARK}; color: {_TEXT};
                }}
            """)
            btn.clicked.connect(lambda _, idx=i: self._on_model_pill_clicked(idx))
            self._model_pills.append(btn)
            self._model_selector_l.addWidget(btn)

        # Stretch + scroll hint when many objects
        self._model_selector_l.addStretch()
        self._model_selector_w.setVisible(len(labels) > 1)

    def _on_model_pill_clicked(self, idx: int):
        for i, btn in enumerate(self._model_pills):
            btn.setChecked(i == idx)
        self.model_selected.emit(idx)

    # ── Mode switching (3D ↔ image annotation) ───────────────────────────────

    def _show_3d(self):
        """Switch viewer area back to the live 3D page."""
        self._active_img_idx = -1
        self._mode_stack.setCurrentIndex(0)
        for card in self._thumb_cards:
            card.set_active(False)
        if hasattr(self, '_btn_3d'):
            self._btn_3d.setChecked(True)
        if hasattr(self, '_mode_badge'):
            self._mode_badge.setText('3D Model')
            self._mode_badge.setStyleSheet("""
                background: #1d4ed8; color: white;
                border-radius: 10px; font-size: 10px; font-weight: 700;
                padding: 3px 10px; border: none;
            """)

    def _toggle_image(self, idx: int):
        """Clicking the already-active thumbnail returns to the 3D view —
        the only way back now that the standalone "3D" button is gone."""
        if self._active_img_idx == idx:
            self._show_3d()
        else:
            self._show_image(idx)

    def _show_image(self, idx: int):
        """Switch viewer area to display inspection image at idx for annotation."""
        if idx < 0 or idx >= len(self._inspection_images):
            return
        pix = _b64_to_pixmap(self._inspection_images[idx])
        if pix is None:
            return
        self._active_img_idx = idx
        self._img_view.set_image(pix)
        annots = self._image_annotations[idx] if idx < len(self._image_annotations) else []
        self._img_view.set_annotations(annots)
        self._mode_stack.setCurrentIndex(1)
        for i, card in enumerate(self._thumb_cards):
            card.set_active(i == idx)
        if hasattr(self, '_btn_3d'):
            self._btn_3d.setChecked(False)
        if hasattr(self, '_mode_badge'):
            self._mode_badge.setText('Image View')
            self._mode_badge.setStyleSheet("""
                background: #059669; color: white;
                border-radius: 10px; font-size: 10px; font-weight: 700;
                padding: 3px 10px; border: none;
            """)

    def _on_image_point_added(self, dot_xf: float, dot_yf: float,
                               badge_xf: float, badge_yf: float):
        """Store a completed two-click annotation on the currently displayed image."""
        idx = self._active_img_idx
        if idx < 0 or idx >= len(self._image_annotations):
            return
        self._image_annotations[idx].append((dot_xf, dot_yf, badge_xf, badge_yf))
        self._img_view.set_annotations(self._image_annotations[idx])
        number = len(self._image_annotations[idx])
        self.annotation_added.emit(number)
        self.changed.emit()

    # ── Camera / interaction actions ──────────────────────────────────────────

    def _do_zoom(self, factor: float):
        viewer = self._viewer_ref
        if viewer is None:
            return
        try:
            viewer._screenshot_zoom(factor)
        except Exception as e:
            logger.debug(f'QC _do_zoom: {e}')

    def _fit_to_view(self):
        viewer = self._viewer_ref
        if viewer is None:
            return
        try:
            viewer.reset_view()
        except Exception as e:
            logger.debug(f'QC _fit_to_view: {e}')

    def _snap_view(self, view_dir: tuple, up: tuple):
        """Snap camera to a standard direction using pygfx show_object."""
        viewer = self._viewer_ref
        if viewer is None:
            return
        try:
            viewer._camera.show_object(viewer._mesh_obj, view_dir=view_dir, scale=1.8, up=up)
            if viewer._canvas:
                viewer._canvas.request_draw()
        except Exception as e:
            logger.debug(f'QC _snap_view: {e}')

    def _capture_current_view(self):
        """Capture the current live view and append it to the inspection images strip."""
        viewer = self._viewer_ref
        if viewer is None:
            return
        try:
            pix = viewer.capture_thumbnail(480, 320)
            if pix and not pix.isNull():
                self._add_inspection_image(pix)
        except Exception as e:
            logger.debug(f'QC _capture_current_view: {e}')

    # ── Inspection Images helpers ─────────────────────────────────────────────

    def _add_images_from_paths(self, paths: list):
        for path in paths:
            pix = QPixmap(path)
            if not pix.isNull():
                self._add_inspection_image(pix)

    def _add_inspection_image(self, pix: QPixmap):
        b64 = _pixmap_to_b64(pix)
        self._inspection_images.append(b64)
        self._image_annotations.append([])
        self._insert_thumb_card(len(self._inspection_images) - 1, pix)
        self.changed.emit()

    def _insert_thumb_card(self, idx: int, pix: QPixmap):
        """Insert a thumbnail card before the trailing stretch."""
        card = _InspThumbCard(pix)
        card.delete_requested.connect(lambda i=idx: self._delete_inspection_image(i))
        card.image_clicked.connect(lambda i=idx: self._toggle_image(i))
        self._thumb_cards.insert(idx, card)
        self._insp_layout.insertWidget(idx, card)

    def _delete_inspection_image(self, idx: int):
        if idx < 0 or idx >= len(self._inspection_images):
            return
        self._inspection_images.pop(idx)
        self._image_annotations.pop(idx)
        if self._active_img_idx == idx:
            self._show_3d()
        elif self._active_img_idx > idx:
            self._active_img_idx -= 1
        self._rebuild_insp_strip()
        self.changed.emit()

    def _rebuild_insp_strip(self):
        """Clear all cards and rebuild from _inspection_images. Stretch stays at end."""
        self._thumb_cards.clear()
        while self._insp_layout.count() > 1:
            item = self._insp_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        for i, b64 in enumerate(self._inspection_images):
            pix = _b64_to_pixmap(b64)
            if pix:
                self._insert_thumb_card(i, pix)
        # Restore active highlight
        if 0 <= self._active_img_idx < len(self._thumb_cards):
            self._thumb_cards[self._active_img_idx].set_active(True)

    # ── viewer embedding / release ────────────────────────────────────────────

    def embed_viewer(self, viewer):
        """Reparent the live viewer widget into this panel's host container."""
        if viewer is None:
            return
        if self._viewer_ref is viewer:
            return  # already embedded

        self.release_viewer()  # release any previously embedded viewer

        try:
            orig_parent = viewer.parent()

            # Record position in the original QStackedWidget so we can restore
            orig_stacked = None
            orig_idx = -1
            if isinstance(orig_parent, QStackedWidget):
                orig_stacked = orig_parent
                orig_idx = orig_parent.indexOf(viewer)

            # Reparent: addWidget reparents to _3d_page
            self._placeholder.hide()
            self._3d_page_layout.addWidget(viewer)
            viewer.show()
            self._mode_stack.setCurrentIndex(0)

            self._viewer_ref   = viewer
            self._orig_stacked = orig_stacked
            self._orig_idx     = orig_idx

        except Exception as e:
            logger.debug(f'QC embed_viewer: {e}')

    def release_viewer(self):
        """Restore the viewer widget to its original QStackedWidget."""
        if self._viewer_ref is None:
            return
        viewer = self._viewer_ref
        orig_stacked = self._orig_stacked
        orig_idx = self._orig_idx

        self._viewer_ref   = None
        self._orig_stacked = None
        self._orig_idx     = -1

        try:
            if orig_stacked is not None:
                # Re-parent back; insertWidget preserves the original slot index
                orig_stacked.insertWidget(orig_idx, viewer)
                # Do NOT call setCurrentWidget here — the caller (_switch_mode)
                # is responsible for selecting the right viewer after the
                # workspace switch completes.
            else:
                viewer.hide()
        except Exception as e:
            logger.debug(f'QC release_viewer: {e}')

        try:
            self._placeholder.show()
            self._3d_page_layout.removeWidget(viewer)
        except Exception:
            pass

    def capture_standard_views(self):
        """Capture current + 4 standard views and append all to the inspection strip."""
        from PyQt5.QtCore import QCoreApplication
        viewer = self._viewer_ref
        if viewer is None:
            return

        _SNAP_DIRS = [
            ('Front', (0, -1, 0), (0, 0, 1)),
            ('Right', (1,  0, 0), (0, 0, 1)),
            ('Back',  (0,  1, 0), (0, 0, 1)),
            ('Left',  (-1, 0, 0), (0, 0, 1)),
        ]

        try:
            pix = viewer.capture_thumbnail(480, 320)
            if pix and not pix.isNull():
                self._add_inspection_image(pix)
        except Exception as e:
            logger.debug(f'QC capture current: {e}')

        for _name, view_dir, up in _SNAP_DIRS:
            try:
                viewer._camera.show_object(viewer._mesh_obj, view_dir=view_dir, scale=1.8, up=up)
                if viewer._canvas:
                    viewer._canvas.request_draw()
                QCoreApplication.processEvents()
                pix = viewer.capture_thumbnail(480, 320)
                if pix and not pix.isNull():
                    self._add_inspection_image(pix)
            except Exception as e:
                logger.debug(f'QC capture {_name}: {e}')

        try:
            viewer.reset_view()
        except Exception:
            pass

    def get_data(self) -> dict:
        return {
            'inspection_date': self._date_edit.date().toString('yyyy-MM-dd'),
            'inspected_by': self._inspected_by.text(),
            'comments': self._comments.toPlainText(),
            'inspection_images': self._inspection_images,
            'image_annotations': self._image_annotations,
        }

    def set_data(self, d: dict):
        if d.get('inspection_date'):
            dt = QDate.fromString(d['inspection_date'], 'yyyy-MM-dd')
            if dt.isValid():
                self._date_edit.setDate(dt)
        self._inspected_by.setText(d.get('inspected_by', ''))
        self._comments.setPlainText(d.get('comments', ''))
        images = d.get('inspection_images', [])
        if images:
            self._inspection_images = list(images)
            annots = d.get('image_annotations', [])
            self._image_annotations = [
                list(annots[i]) if i < len(annots) else []
                for i in range(len(images))
            ]
            self._rebuild_insp_strip()


# ── _CompanyInfoPanel ─────────────────────────────────────────────────────────

class _LogoDropZone(QLabel):
    logo_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(110)
        self.setAlignment(Qt.AlignCenter)
        self.setAcceptDrops(True)
        self._logo_data = ''
        self._refresh_style(False)

    def _refresh_style(self, has_logo: bool):
        if not has_logo:
            self.setStyleSheet(f"""
                QLabel {{
                    background: {_SURFACE};
                    border: 2px dashed {_BORDER_DARK};
                    border-radius: 8px;
                    color: {_MUTED}; font-size: 12px;
                }}
            """)
            self.setText('Drag & drop your logo here\nor click to browse')
        else:
            self.setStyleSheet(f"""
                QLabel {{
                    background: {_SURFACE};
                    border: 1px solid {_BORDER};
                    border-radius: 8px;
                }}
            """)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            path, _ = QFileDialog.getOpenFileName(
                self, 'Select Logo', '',
                'Images (*.png *.jpg *.jpeg *.bmp)'
            )
            if path:
                self._load_image(path)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = e.mimeData().urls()
        if urls:
            self._load_image(urls[0].toLocalFile())

    def _load_image(self, path: str):
        try:
            pix = QPixmap(path)
            if pix.isNull():
                return
            scaled = pix.scaled(220, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.setPixmap(scaled)
            self._refresh_style(True)
            self._logo_data = _pixmap_to_b64(pix)
            self.logo_changed.emit(self._logo_data)
        except Exception as e:
            logger.debug(f'_LogoDropZone: {e}')

    def set_logo_data(self, data: str):
        self._logo_data = data
        if data:
            pix = _b64_to_pixmap(data)
            if pix:
                scaled = pix.scaled(220, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.setPixmap(scaled)
                self._refresh_style(True)
                return
        self._refresh_style(False)

    def get_logo_data(self) -> str:
        return self._logo_data


class _CompanyInfoPanel(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f'background: {_BG};')
        self.setFixedWidth(290)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{
                background: transparent; width: 6px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {_BORDER_DARK}; border-radius: 3px; min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        inner = QWidget()
        inner.setStyleSheet('background: transparent;')
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        layout.addWidget(_make_section_label('Company / Part Information'))
        layout.addSpacing(2)

        self._logo = _LogoDropZone()
        self._logo.logo_changed.connect(lambda _: self.changed.emit())
        layout.addWidget(self._logo)

        def _field(placeholder: str) -> QLineEdit:
            f = QLineEdit()
            f.setPlaceholderText(placeholder)
            f.setStyleSheet(_INPUT)
            f.textChanged.connect(lambda _: self.changed.emit())
            return f

        layout.addWidget(_make_field_label('Designation'))
        self._designation = _field('Enter designation...')
        layout.addWidget(self._designation)

        layout.addWidget(_make_field_label('Reference Number'))
        self._reference = _field('Enter reference number...')
        layout.addWidget(self._reference)

        layout.addWidget(_make_field_label('Manufactured By'))
        self._manufacturer = _field('Enter manufacturer name...')
        layout.addWidget(self._manufacturer)

        layout.addWidget(_make_field_label('Inspection Due Date'))
        self._due_date = QDateEdit()
        self._due_date.setCalendarPopup(True)
        self._due_date.setDisplayFormat('dd/MM/yyyy')
        self._due_date.setSpecialValueText('Select a date...')
        self._due_date.setDate(QDate(2000, 1, 1))
        self._due_date.setStyleSheet(_DATE)
        self._due_date.dateChanged.connect(lambda _: self.changed.emit())
        layout.addWidget(self._due_date)

        layout.addWidget(_hsep())
        layout.addWidget(_make_section_label('Overall Status'))
        layout.addSpacing(2)

        cb_style = f"""
            QCheckBox {{
                color: {_TEXT}; font-size: 13px; spacing: 8px;
                background: transparent;
            }}
            QCheckBox::indicator {{
                width: 16px; height: 16px;
                border: 1.5px solid {_BORDER_DARK}; border-radius: 3px;
                background: {_SURFACE};
            }}
            QCheckBox::indicator:checked {{
                background: {_ACCENT}; border-color: {_ACCENT};
            }}
            QCheckBox::indicator:hover {{ border-color: {_ACCENT}; }}
        """
        self._cb_in_progress = QCheckBox('In Progress')
        self._cb_approved    = QCheckBox('Approved')
        self._cb_rejected    = QCheckBox('Rejected')
        for cb in (self._cb_in_progress, self._cb_approved, self._cb_rejected):
            cb.setStyleSheet(cb_style)
            cb.toggled.connect(self._on_status_toggled)
            layout.addWidget(cb)

        layout.addWidget(_hsep())
        layout.addWidget(_make_field_label('Waived By'))
        self._waived_by = _field('Enter name...')
        layout.addWidget(self._waived_by)
        layout.addStretch()

        scroll.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _on_status_toggled(self, checked: bool):
        sender = self.sender()
        if checked:
            for cb in (self._cb_in_progress, self._cb_approved, self._cb_rejected):
                if cb is not sender:
                    cb.blockSignals(True)
                    cb.setChecked(False)
                    cb.blockSignals(False)
        self.changed.emit()

    def _get_status(self) -> str:
        if self._cb_in_progress.isChecked(): return 'in_progress'
        if self._cb_approved.isChecked():    return 'approved'
        if self._cb_rejected.isChecked():    return 'rejected'
        return ''

    def _set_status(self, status: str):
        for cb in (self._cb_in_progress, self._cb_approved, self._cb_rejected):
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
        mapping = {'in_progress': self._cb_in_progress,
                   'approved': self._cb_approved,
                   'rejected': self._cb_rejected}
        if status in mapping:
            mapping[status].setChecked(True)

    def get_data(self) -> dict:
        return {
            'logo_data':           self._logo.get_logo_data(),
            'designation':         self._designation.text(),
            'reference_number':    self._reference.text(),
            'manufacturer':        self._manufacturer.text(),
            'inspection_due_date': self._due_date.date().toString('yyyy-MM-dd'),
            'overall_status':      self._get_status(),
            'waived_by':           self._waived_by.text(),
        }

    def set_data(self, d: dict):
        self._logo.set_logo_data(d.get('logo_data', ''))
        self._designation.setText(d.get('designation', ''))
        self._reference.setText(d.get('reference_number', ''))
        self._manufacturer.setText(d.get('manufacturer', ''))
        due = d.get('inspection_due_date', '')
        if due:
            dt = QDate.fromString(due, 'yyyy-MM-dd')
            if dt.isValid():
                self._due_date.setDate(dt)
        self._set_status(d.get('overall_status', ''))
        self._waived_by.setText(d.get('waived_by', ''))


# ── QualityControlWidget ──────────────────────────────────────────────────────

class QualityControlWidget(QWidget):
    """Top-level QC screen inside TheProjectWidget."""
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._viewer_ref   = None
        self._viewers: list = []   # list of (label, viewer_widget)
        self._selected_idx: int = 0
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f'background: {_BG};')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._left_panel   = _QCLeftPanel()
        self._center_panel = _ControlPointsPanel()
        self._right_panel  = _CompanyInfoPanel()

        self._left_panel.changed.connect(self.changed)
        self._center_panel.changed.connect(self.changed)
        self._right_panel.changed.connect(self.changed)
        self._left_panel.fullscreen_requested.connect(self._set_fullscreen)
        self._left_panel.model_selected.connect(self._on_model_selected)
        # Clicking on an image auto-adds a matching control point in the center panel
        self._left_panel.annotation_added.connect(
            lambda _n: self._center_panel._add_point()
        )

        self._sep_lc = _vsep()
        self._sep_cr = _vsep()

        layout.addWidget(self._left_panel)
        layout.addWidget(self._sep_lc)
        layout.addWidget(self._center_panel, 1)
        layout.addWidget(self._sep_cr)
        layout.addWidget(self._right_panel)

    # ── viewer lifecycle ──────────────────────────────────────────────────────

    def set_viewers(self, viewers: list, active_viewer=None):
        """Update the full list of (label, viewer_widget) pairs.

        active_viewer — hint for which viewer to show by default (used only when
        the current selection is no longer valid or this is the first call).
        """
        self._viewers = viewers

        # Determine which index to show
        # 1. Keep current selection if that viewer is still present
        if 0 <= self._selected_idx < len(viewers):
            pass  # selection still valid — keep it
        else:
            # Fall back to the active_viewer hint, then index 0
            self._selected_idx = 0
            if active_viewer is not None:
                for i, (_, vw) in enumerate(viewers):
                    if vw is active_viewer:
                        self._selected_idx = i
                        break

        labels = [label for label, _ in viewers]
        self._left_panel.set_model_list(labels, self._selected_idx)

        if viewers:
            _, viewer = viewers[self._selected_idx]
            self._viewer_ref = viewer
            if self.isVisible():
                self._left_panel.embed_viewer(viewer)

    def set_viewer(self, viewer):
        """Legacy single-viewer setter — finds viewer in list or embeds directly."""
        for i, (_, vw) in enumerate(self._viewers):
            if vw is viewer:
                self._selected_idx = i
                self._left_panel.set_model_list(
                    [l for l, _ in self._viewers], i)
                self._viewer_ref = viewer
                if self.isVisible():
                    self._left_panel.embed_viewer(viewer)
                return
        # Not in list yet — embed directly
        self._viewer_ref = viewer
        if self.isVisible():
            self._left_panel.embed_viewer(viewer)

    def _on_model_selected(self, idx: int):
        self._selected_idx = idx
        if 0 <= idx < len(self._viewers):
            _, viewer = self._viewers[idx]
            self._viewer_ref = viewer
            self._left_panel.embed_viewer(viewer)

    def showEvent(self, event):
        super().showEvent(event)
        if self._viewer_ref is not None:
            self._left_panel.embed_viewer(self._viewer_ref)

    def hideEvent(self, event):
        super().hideEvent(event)
        self._left_panel.release_viewer()

    def _set_fullscreen(self, on: bool):
        """Expand left panel (hide center/right) or restore 3-column layout."""
        self._center_panel.setVisible(not on)
        self._right_panel.setVisible(not on)
        self._sep_lc.setVisible(not on)
        self._sep_cr.setVisible(not on)
        # Widen left panel to fill available space when fullscreen
        if on:
            self._left_panel.setFixedWidth(self.width() - 32)
        else:
            self._left_panel.setFixedWidth(440)

    # ── data persistence ──────────────────────────────────────────────────────

    def get_data(self) -> dict:
        d = {}
        d.update(self._left_panel.get_data())
        d.update(self._right_panel.get_data())
        d['control_points'] = [cp.to_dict() for cp in self._center_panel.get_control_points()]
        return d

    def set_data(self, d: dict):
        self._left_panel.set_data(d)
        self._right_panel.set_data(d)
        cps = [ControlPoint.from_dict(c) for c in d.get('control_points', [])]
        self._center_panel.set_control_points(cps)

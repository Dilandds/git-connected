"""
Version Comparison screen — side-by-side version cards with star rankings,
photos, pros/cons fields, and reordering.
"""
import logging
import math
from dataclasses import dataclass, field
from typing import List, Optional
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QLineEdit, QTextEdit, QFileDialog,
    QSizePolicy, QMessageBox, QSpinBox, QDialog,
)
from PyQt5.QtCore import Qt, QRect, pyqtSignal
from PyQt5.QtGui import QIcon, QColor, QPainter, QPainterPath, QBrush, QFont
from ui.styles import default_theme, make_font, TOOLTIP_STYLE
from ui.modal_utils import FormModal
from i18n import t

logger = logging.getLogger(__name__)

# ── palette ───────────────────────────────────────────────────────────────────
_BG     = '#f8f9fa'
_CARD   = '#ffffff'
_BORDER = '#e5e7eb'
_TEXT   = '#1e2430'
_MUTED  = '#6b7280'
_ACCENT = default_theme.button_primary
_ACCENT_H = default_theme.button_primary_hover

MAX_VERSIONS = 20
CARD_W = 245

_STAR_COLORS = {
    1: "#22c55e",
    2: "#f97316",
    3: "#ef4444",
}

def _star_color(n: int) -> str:
    if n <= 0:
        return "#d1d5db"
    return _STAR_COLORS.get(n, "#ef4444")

# ── styles ────────────────────────────────────────────────────────────────────
_INPUT = f"""
    QLineEdit, QTextEdit {{
        background-color: #f5f6f8; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 4px;
        padding: 3px 6px; font-size: 14px;
    }}
    QLineEdit:focus, QTextEdit:focus {{ border-color: {_ACCENT}; }}
"""
_BTN_ICON = f"""
    QPushButton {{
        background: transparent; border: none;
        color: {_MUTED}; font-size: 14px; padding: 2px 4px;
    }}
    QPushButton:hover {{ color: {_ACCENT}; background: #e8f0fe; border-radius: 4px; }}
    QPushButton:disabled {{ color: #d1d5db; }}
""" + TOOLTIP_STYLE
_BTN_DELETE = f"""
    QPushButton {{
        background: transparent; border: none;
        color: {_MUTED}; font-size: 14px; padding: 2px 4px;
    }}
    QPushButton:hover {{ color: #ef4444; background: #fee2e2; border-radius: 4px; }}
""" + TOOLTIP_STYLE


# ── data model ────────────────────────────────────────────────────────────────

@dataclass
class VersionCard:
    id:              int
    star_number:     int       = 0
    photo_b64s:      List[str] = field(default_factory=list)
    version:         str       = ""
    positive_points: str       = ""
    negative_points: str       = ""
    comments:        str       = ""
    cost:            str       = ""


# ── Star badge ────────────────────────────────────────────────────────────────

class StarBadge(QWidget):
    """Clickable star with a rank number inside, drawn with QPainter."""

    clicked = pyqtSignal()

    def __init__(self, number: int = 0, parent=None):
        super().__init__(parent)
        self._number = number
        self.setFixedSize(58, 58)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(t('project.version.click_ranking'))

    def set_number(self, n: int):
        self._number = n
        self.update()

    def number(self) -> int:
        return self._number

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        color = QColor(_star_color(self._number))
        cx, cy = self.width() / 2.0, self.height() / 2.0
        outer, inner, pts = 25.0, 11.0, 5

        path = QPainterPath()
        for i in range(pts * 2):
            angle = math.pi * i / pts - math.pi / 2
            r = outer if i % 2 == 0 else inner
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        path.closeSubpath()
        p.fillPath(path, QBrush(color))

        if self._number > 0:
            p.setPen(QColor("white"))
            f = QFont("Arial", 14, QFont.Bold)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignCenter, str(self._number))

        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()


# ── Photo slot ────────────────────────────────────────────────────────────────

class PhotoSlot(QPushButton):
    """Clickable photo upload slot with image preview."""

    photo_changed = pyqtSignal(str)

    def __init__(self, w: int, h: int, parent=None):
        super().__init__(parent)
        self._b64 = ""
        self._zoom_preview: Optional[QLabel] = None
        self.setFixedSize(w, h)
        self.setCursor(Qt.PointingHandCursor)

        # Remove button (top-right corner overlay), only shown once a photo
        # is set — must be parented to self so it overlays this button
        # instead of popping an independent floating window. Built before
        # _set_empty() below, which references it to start hidden.
        self._remove_btn = QPushButton('×', self)
        self._remove_btn.setFixedSize(18, 18)
        self._remove_btn.setCursor(Qt.PointingHandCursor)
        self._remove_btn.hide()
        self._remove_btn.setStyleSheet("""
            QPushButton {
                background: #ef4444; color: white; border: none;
                border-radius: 9px; font-size: 12px; font-weight: bold; padding: 0;
            }
            QPushButton:hover { background: #dc2626; }
        """)
        self._remove_btn.clicked.connect(self._on_remove_clicked)
        self._remove_btn.move(w - 22, 4)

        self._set_empty()
        self.clicked.connect(self._upload)

    def _set_empty(self):
        self.setIcon(QIcon())
        self.setText(t('project.version.add_photo'))
        self.setStyleSheet(f"""
            QPushButton {{
                background: #f1f3f5; border: 1px dashed {_BORDER};
                border-radius: 6px; color: {_MUTED}; font-size: 13px;
            }}
            QPushButton:hover {{ border-color: {_ACCENT}; color: {_ACCENT}; }}
        """)
        self._remove_btn.hide()

    def set_b64(self, b64: str):
        self._b64 = b64
        from core.image_utils import b64_to_pixmap
        pix = b64_to_pixmap(b64)
        if pix is None:
            self._set_empty()
            return
        self.setIcon(QIcon(pix.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)))
        self.setIconSize(self.size())
        self.setText("")
        self.setStyleSheet(f"""
            QPushButton {{
                background: #f1f3f5; border: 1px solid {_BORDER}; border-radius: 6px;
            }}
            QPushButton:hover {{ border-color: {_ACCENT}; }}
        """)
        self._remove_btn.show()
        self._remove_btn.raise_()

    def _on_remove_clicked(self):
        self._hide_zoom_preview()
        self.set_b64('')
        self.photo_changed.emit('')

    def _upload(self):
        self._hide_zoom_preview()
        path, _ = QFileDialog.getOpenFileName(
            self, t('project.timeline.detail_photo_title'), "", "Images (*.png *.jpg *.jpeg *.webp)"
        )
        if path:
            from core.image_utils import path_to_b64
            b64 = path_to_b64(path)
            if b64:
                self.set_b64(b64)
                self.photo_changed.emit(b64)

    # ── hover zoom preview ────────────────────────────────────────────────
    def _show_zoom_preview(self):
        if not self._b64:
            return
        from core.image_utils import b64_to_pixmap
        pix = b64_to_pixmap(self._b64)
        if pix is None:
            return
        self._hide_zoom_preview()
        scaled = pix.scaled(320, 320, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        preview = QLabel(None)
        preview.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        preview.setAttribute(Qt.WA_TransparentForMouseEvents)
        preview.setPixmap(scaled)
        preview.setFixedSize(scaled.size())
        preview.setStyleSheet(
            "background: white; border: 2px solid #ffffff; border-radius: 8px;"
        )
        global_pos = self.mapToGlobal(self.rect().topRight())
        preview.move(global_pos.x() + 10, max(0, global_pos.y() - scaled.height() // 2))
        preview.show()
        self._zoom_preview = preview

    def _hide_zoom_preview(self):
        if self._zoom_preview is not None:
            self._zoom_preview.close()
            self._zoom_preview.deleteLater()
            self._zoom_preview = None

    def enterEvent(self, event):
        self._show_zoom_preview()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hide_zoom_preview()
        super().leaveEvent(event)


# ── Star ranking dialog ───────────────────────────────────────────────────────

class _StarRankingDialog(FormModal):
    def __init__(self, current_number: int, parent=None):
        super().__init__(parent, t('project.version.set_ranking'), theme=FormModal.LIGHT, min_width=280)
        hint = QLabel(t('project.version.ranking_hint'))
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"color: {_MUTED}; font-size: 14px; background: transparent; border: none;"
        )
        self.add_widget(hint)
        self._preview = StarBadge(current_number)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(self._preview)
        row.addStretch()
        self.add_layout(row)
        self.f_spin = QSpinBox()
        self.f_spin.setRange(0, 20)
        self.f_spin.setValue(current_number)
        self.f_spin.valueChanged.connect(self._preview.set_number)
        self.add_field(t('project.version.ranking_field'), self.f_spin)
        self.finish()

    @property
    def ranking(self) -> int:
        return self.f_spin.value()


# ── Version card widget ───────────────────────────────────────────────────────

class VersionCardWidget(QFrame):
    """One version card in the comparison grid."""

    changed              = pyqtSignal()
    move_left_requested  = pyqtSignal()
    move_right_requested = pyqtSignal()
    delete_requested     = pyqtSignal()

    def __init__(self, card: VersionCard, is_first: bool = True, is_last: bool = True, parent=None):
        super().__init__(parent)
        self._card = card
        self.setFixedWidth(CARD_W)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self.setStyleSheet(f"""
            QFrame {{
                background: {_CARD};
                border: 1px solid {_BORDER};
                border-radius: 10px;
            }}
        """)
        self._build(is_first, is_last)

    def _build(self, is_first: bool, is_last: bool):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(3)

        # ── Star ──
        star_row = QHBoxLayout()
        star_row.addStretch()
        self._star = StarBadge(self._card.star_number)
        self._star.clicked.connect(self._edit_star)
        star_row.addWidget(self._star)
        star_row.addStretch()
        root.addLayout(star_row)

        # ── Photos: 1 portrait primary (centred) + 2 secondary ──
        self._photo_slots: List[PhotoSlot] = []

        # Primary photo — portrait rectangle (height > width)
        _PH_W = CARD_W - 60   # 185 px wide
        _PH_H = CARD_W + 10   # 255 px tall  →  clearly portrait
        slot0 = PhotoSlot(_PH_W, _PH_H)
        if len(self._card.photo_b64s) > 0:
            slot0.set_b64(self._card.photo_b64s[0])
        slot0.photo_changed.connect(lambda p: self._on_photo(0, p))
        self._photo_slots.append(slot0)
        ph_row = QHBoxLayout()
        ph_row.setContentsMargins(0, 0, 0, 0)
        ph_row.addStretch()
        ph_row.addWidget(slot0)
        ph_row.addStretch()
        root.addLayout(ph_row)

        sec_row = QHBoxLayout()
        sec_row.setSpacing(4)
        sw = (CARD_W - 24) // 2
        for i in (1, 2):
            s = PhotoSlot(sw, 70)
            if len(self._card.photo_b64s) > i:
                s.set_b64(self._card.photo_b64s[i])
            s.photo_changed.connect(lambda p, idx=i: self._on_photo(idx, p))
            self._photo_slots.append(s)
            sec_row.addWidget(s)
        root.addLayout(sec_row)

        # ── Blue divider ──
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setStyleSheet(f"color: {_ACCENT}; background: {_ACCENT}; max-height: 2px; border: none;")
        root.addWidget(div)

        # ── Fields ──
        def _section_lbl(text):
            l = QLabel(text)
            l.setStyleSheet(f"color: {_MUTED}; font-size: 13px; font-weight: bold; background: transparent; border: none;")
            return l

        def _inp():
            w = QLineEdit()
            w.setStyleSheet(_INPUT)
            w.setFixedHeight(24)
            return w

        def _area(h=50):
            w = QTextEdit()
            w.setStyleSheet(_INPUT)
            w.setFixedHeight(h)
            return w

        def _field_block(label_widget, input_widget):
            """Label + input grouped with tight spacing."""
            bl = QVBoxLayout()
            bl.setSpacing(1)
            bl.setContentsMargins(0, 0, 0, 0)
            bl.addWidget(label_widget)
            bl.addWidget(input_widget)
            return bl

        self._f_version = _inp()
        self._f_version.setPlaceholderText(t('project.version.version_ph'))
        self._f_version.setText(self._card.version)
        self._f_version.textChanged.connect(lambda v: setattr(self._card, 'version', v) or self.changed.emit())
        root.addLayout(_field_block(_section_lbl(t('project.version.version_field')), self._f_version))

        self._f_pos = _area()
        self._f_pos.setPlaceholderText(t('project.version.positives_ph'))
        self._f_pos.setPlainText(self._card.positive_points)
        self._f_pos.textChanged.connect(
            lambda: setattr(self._card, 'positive_points', self._f_pos.toPlainText()) or self.changed.emit()
        )
        root.addLayout(_field_block(_section_lbl(t('project.version.positives')), self._f_pos))

        self._f_neg = _area()
        self._f_neg.setPlaceholderText(t('project.version.negatives_ph'))
        self._f_neg.setPlainText(self._card.negative_points)
        self._f_neg.textChanged.connect(
            lambda: setattr(self._card, 'negative_points', self._f_neg.toPlainText()) or self.changed.emit()
        )
        root.addLayout(_field_block(_section_lbl(t('project.version.negatives')), self._f_neg))

        self._f_comments = _area(h=44)
        self._f_comments.setPlaceholderText(t('project.version.comments_ph'))
        self._f_comments.setPlainText(self._card.comments)
        self._f_comments.textChanged.connect(
            lambda: setattr(self._card, 'comments', self._f_comments.toPlainText()) or self.changed.emit()
        )
        root.addLayout(_field_block(_section_lbl(t('project.version.comments')), self._f_comments))

        self._f_cost = _inp()
        self._f_cost.setPlaceholderText(t('project.version.cost_ph'))
        self._f_cost.setText(self._card.cost)
        self._f_cost.textChanged.connect(lambda v: setattr(self._card, 'cost', v) or self.changed.emit())
        root.addLayout(_field_block(_section_lbl(t('project.version.cost')), self._f_cost))

        # ── Bottom toolbar: move ← → | delete ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(2)

        self._left_btn = QPushButton("←")
        self._left_btn.setToolTip(t('project.version.move_left'))
        self._left_btn.setFixedSize(28, 24)
        self._left_btn.setStyleSheet(_BTN_ICON)
        self._left_btn.setCursor(Qt.PointingHandCursor)
        self._left_btn.setEnabled(not is_first)
        self._left_btn.clicked.connect(self.move_left_requested)

        self._right_btn = QPushButton("→")
        self._right_btn.setToolTip(t('project.version.move_right'))
        self._right_btn.setFixedSize(28, 24)
        self._right_btn.setStyleSheet(_BTN_ICON)
        self._right_btn.setCursor(Qt.PointingHandCursor)
        self._right_btn.setEnabled(not is_last)
        self._right_btn.clicked.connect(self.move_right_requested)

        del_btn = QPushButton("🗑")
        del_btn.setToolTip(t('project.version.delete_version'))
        del_btn.setFixedSize(28, 24)
        del_btn.setStyleSheet(_BTN_DELETE)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.clicked.connect(self.delete_requested)

        toolbar.addWidget(self._left_btn)
        toolbar.addWidget(self._right_btn)
        toolbar.addStretch()
        toolbar.addWidget(del_btn)
        root.addLayout(toolbar)

    def _on_photo(self, idx: int, b64: str):
        while len(self._card.photo_b64s) <= idx:
            self._card.photo_b64s.append("")
        self._card.photo_b64s[idx] = b64
        self.changed.emit()

    def _edit_star(self):
        dlg = _StarRankingDialog(self._card.star_number, self)
        if dlg.exec_() == QDialog.Accepted:
            n = dlg.ranking
            self._card.star_number = n
            self._star.set_number(n)
            self.changed.emit()


# ── Add-version placeholder card ─────────────────────────────────────────────

class _AddVersionCard(QFrame):
    """Dashed placeholder card — click to add a new version."""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(CARD_W)
        self.setMinimumHeight(220)
        self.setCursor(Qt.PointingHandCursor)
        self._normal_style = f"""
            QFrame {{
                background: #f9fafb;
                border: 2px dashed {_BORDER};
                border-radius: 10px;
            }}
        """
        self._hover_style = f"""
            QFrame {{
                background: #eff6ff;
                border: 2px dashed {_ACCENT};
                border-radius: 10px;
            }}
        """
        self.setStyleSheet(self._normal_style)

        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)

        plus = QLabel("＋")
        plus.setAlignment(Qt.AlignCenter)
        plus.setStyleSheet(f"color: {_MUTED}; font-size: 32px; background: transparent; border: none;")
        text = QLabel(t('project.version.add_version'))
        text.setAlignment(Qt.AlignCenter)
        text.setStyleSheet(f"color: {_MUTED}; font-size: 15px; background: transparent; border: none;")
        lay.addWidget(plus)
        lay.addWidget(text)

    def enterEvent(self, _):
        self.setStyleSheet(self._hover_style)

    def leaveEvent(self, _):
        self.setStyleSheet(self._normal_style)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()


# ── Main widget ───────────────────────────────────────────────────────────────

class VersionComparisonWidget(QWidget):
    """Top-level Version Comparison screen."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: List[VersionCard] = []
        self._card_widgets: List[VersionCardWidget] = []
        self._next_id = 1
        self.setStyleSheet(f"background: {_BG};")
        self._build_ui()

    # ── build ──────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top bar
        top = QWidget()
        top.setFixedHeight(46)
        top.setStyleSheet(f"background: {_BG}; border-bottom: 1px solid {_BORDER};")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(16, 0, 16, 0)
        title = QLabel(t('project.version.title'))
        title.setFont(make_font(size=19, bold=True))
        title.setStyleSheet(f"color: {_TEXT}; background: transparent; border: none;")
        subtitle = QLabel(t('project.version.subtitle'))
        subtitle.setStyleSheet(f"color: {_MUTED}; font-size: 14px; background: transparent; border: none;")
        t_col = QVBoxLayout()
        t_col.setSpacing(1)
        t_col.addWidget(title)
        t_col.addWidget(subtitle)
        tl.addLayout(t_col)
        tl.addStretch()
        root.addWidget(top)

        # Scrollable card area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ background: {_BG}; border: none; }}
            QScrollBar:horizontal {{ background: {_BG}; height: 8px; border-radius: 4px; }}
            QScrollBar::handle:horizontal {{ background: {_BORDER}; border-radius: 4px; min-width: 30px; }}
            QScrollBar:vertical {{ background: {_BG}; width: 8px; border-radius: 4px; }}
            QScrollBar::handle:vertical {{ background: {_BORDER}; border-radius: 4px; min-height: 30px; }}
        """)

        self._container = QWidget()
        self._container.setStyleSheet(f"background: {_BG};")
        self._cards_layout = QHBoxLayout(self._container)
        self._cards_layout.setContentsMargins(16, 16, 16, 16)
        self._cards_layout.setSpacing(16)
        self._cards_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        self._add_placeholder = _AddVersionCard()
        self._add_placeholder.clicked.connect(self._add_version)
        self._cards_layout.addWidget(self._add_placeholder)
        self._cards_layout.addStretch()

        self._scroll.setWidget(self._container)
        root.addWidget(self._scroll, 1)

    # ── card management ────────────────────────────────────────────────────────

    def _rebuild(self):
        """Remove and recreate all card widgets from self._cards."""
        for w in self._card_widgets:
            self._cards_layout.removeWidget(w)
            w.deleteLater()
        self._card_widgets.clear()

        n = len(self._cards)
        for i, card in enumerate(self._cards):
            w = self._make_widget(card, is_first=(i == 0), is_last=(i == n - 1))
            self._cards_layout.insertWidget(i, w)
            self._card_widgets.append(w)

        self._add_placeholder.setVisible(n < MAX_VERSIONS)

    def _make_widget(self, card: VersionCard, is_first: bool, is_last: bool) -> VersionCardWidget:
        w = VersionCardWidget(card, is_first=is_first, is_last=is_last)
        w.changed.connect(self.changed)
        w.move_left_requested.connect(lambda c=card: self._move(c, -1))
        w.move_right_requested.connect(lambda c=card: self._move(c, 1))
        w.delete_requested.connect(lambda c=card: self._delete(c))
        return w

    def _add_version(self):
        if len(self._cards) >= MAX_VERSIONS:
            return
        card = VersionCard(id=self._next_id)
        self._next_id += 1
        self._cards.append(card)
        self._rebuild()
        self.changed.emit()

    def _move(self, card: VersionCard, direction: int):
        idx = self._cards.index(card)
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(self._cards):
            return
        self._cards.pop(idx)
        self._cards.insert(new_idx, card)
        self._rebuild()
        self.changed.emit()

    def _delete(self, card: VersionCard):
        from ui.modal_utils import ask_yes_no_dialog
        if not ask_yes_no_dialog(
            self, t('project.version.delete_dlg'), "Delete this version? This cannot be undone."
        ):
            return
        self._cards.remove(card)
        self._rebuild()
        self.changed.emit()

    # ── serialisation ──────────────────────────────────────────────────────────

    def get_data(self) -> dict:
        def _ser(c: VersionCard) -> dict:
            return {
                "id": c.id, "star_number": c.star_number,
                "photo_b64s": c.photo_b64s,
                "version": c.version,
                "positive_points": c.positive_points,
                "negative_points": c.negative_points,
                "comments": c.comments,
                "cost": c.cost,
            }
        return {"next_id": self._next_id, "cards": [_ser(c) for c in self._cards]}

    def set_data(self, data: dict):
        from core.image_utils import path_to_b64
        self._next_id = data.get("next_id", 1)
        self._cards = []
        for cd in data.get("cards", []):
            photo_b64s = cd.get("photo_b64s")
            if photo_b64s is None:
                # Legacy save from before photos were embedded — best-effort
                # migrate whatever paths still exist on THIS machine.
                photo_b64s = [b for b in (path_to_b64(p) for p in cd.get("photo_paths", []) if p) if b]
            self._cards.append(VersionCard(
                id=cd["id"],
                star_number=cd.get("star_number", 0),
                photo_b64s=photo_b64s,
                version=cd.get("version", ""),
                positive_points=cd.get("positive_points", ""),
                negative_points=cd.get("negative_points", ""),
                comments=cd.get("comments", ""),
                cost=cd.get("cost", ""),
            ))
        self._rebuild()

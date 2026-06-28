"""
Overview Widget — shows all open 3D-viewer tabs filling the entire area.
1 tab → full view. 2 tabs → side-by-side halves. N tabs → equal grid cells.
Clicking a card navigates to that tab; dragging rotates the 3D model.
"""
import logging
import math
from math import gcd
from typing import Dict, Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QFrame, QSizePolicy,
)
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QTimer
from PyQt5.QtGui import QPixmap, QColor, QPainter, QPen, QFont

from ui.styles import default_theme, TOOLTIP_STYLE
from i18n import t, on_language_changed

logger = logging.getLogger(__name__)

# ── palette ──────────────────────────────────────────────────────────────────
_BG      = default_theme.background
_CARD    = default_theme.card_background
_BORDER  = default_theme.border_standard
_TEXT    = default_theme.text_primary
_MUTED   = default_theme.text_secondary
_ACCENT  = default_theme.button_primary
_ACCENT_H = default_theme.button_primary_hover

_DRAG_THRESHOLD = 4


def _make_placeholder_pixmap(width: int, height: int) -> QPixmap:
    w, h = max(1, width), max(1, height)
    pix = QPixmap(w, h)
    pix.fill(QColor("#1a1d24"))
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#3a3f4c"), 1))
    painter.setBrush(Qt.NoBrush)
    painter.drawRect(0, 0, w - 1, h - 1)
    font = QFont("Arial", max(12, min(48, h // 4)))
    painter.setFont(font)
    painter.setPen(QColor("#3a3f4c"))
    painter.drawText(0, 0, w, h, Qt.AlignCenter, "⬡")
    painter.end()
    return pix


def _grid_dims(n: int):
    """Return (cols, rows, virtual_cols, base_span, last_span) for n items."""
    if n == 0:
        return 1, 1, 1, 1, 1
    cols = max(1, math.ceil(math.sqrt(n)))
    if n == 3:
        cols = 3   # prefer 3-in-a-row over 2+1
    rows = math.ceil(n / cols)
    last = n - (rows - 1) * cols   # items in the last row

    if last == 0 or last == cols or rows == 1:
        return cols, rows, cols, 1, 1

    g = gcd(cols, last)
    vcols = (cols * last) // g
    return cols, rows, vcols, vcols // cols, vcols // last


class _ThumbnailCard(QFrame):
    clicked          = pyqtSignal(int)
    rotate_requested = pyqtSignal(int, float, float)

    def __init__(self, tab_index: int, filename: str,
                 thumbnail: Optional[QPixmap],
                 annotation_count: int = 0,
                 parent=None):
        super().__init__(parent)
        self._tab_index = tab_index
        self._raw_pix: Optional[QPixmap] = thumbnail
        self._dragging = False
        self._last_drag_pos: Optional[QPoint] = None
        self._press_pos:     Optional[QPoint] = None

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(120, 90)
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("overviewCard")
        self._apply_style(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Thumbnail fills all remaining vertical space
        self._thumb_label = QLabel()
        self._thumb_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._thumb_label.setAlignment(Qt.AlignCenter)
        self._thumb_label.setStyleSheet(
            "background: #1a1d24; border-radius: 6px; border: none;"
        )
        layout.addWidget(self._thumb_label, 1)

        # Drag hint — absolute child, repositioned in resizeEvent
        self._drag_hint = QLabel("⟳  Drag to rotate", self)
        self._drag_hint.setAlignment(Qt.AlignCenter)
        self._drag_hint.setStyleSheet("""
            QLabel {
                background-color: rgba(0,0,0,140);
                color: #ffffff; font-size: 11px; font-weight: bold;
                border-radius: 4px; padding: 3px 8px; border: none;
            }
        """)
        self._drag_hint.adjustSize()
        self._drag_hint.hide()

        # Info row (compact, fixed height)
        info_row = QHBoxLayout()
        info_row.setContentsMargins(2, 0, 2, 0)
        info_row.setSpacing(4)

        badge = QLabel(f"Tab {tab_index + 1}")
        badge.setStyleSheet(f"""
            QLabel {{
                background-color: {_ACCENT}; color: #ffffff;
                border-radius: 4px; font-size: 10px; font-weight: bold;
                padding: 2px 6px; border: none;
            }}
        """)
        badge.setFixedHeight(18)
        info_row.addWidget(badge)

        name = filename or "Untitled"
        name_label = QLabel(name)
        name_label.setStyleSheet(
            f"color: {_TEXT}; font-size: 12px; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        name_label.setToolTip(name)
        name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        fm = name_label.fontMetrics()
        name_label.setText(fm.elidedText(name, Qt.ElideMiddle, 260))
        info_row.addWidget(name_label, 1)
        layout.addLayout(info_row)

        if annotation_count > 0:
            ann = QLabel(
                f"  {annotation_count} annotation{'s' if annotation_count != 1 else ''}"
            )
            ann.setStyleSheet(
                f"color: {_MUTED}; font-size: 10px; background: transparent; border: none;"
            )
            layout.addWidget(ann)

        # Defer initial thumbnail until widget has been laid out
        QTimer.singleShot(0, self._update_thumb)

    # ── thumbnail ─────────────────────────────────────────────────────────────

    def _update_thumb(self):
        w = self._thumb_label.width()
        h = self._thumb_label.height()
        if w < 2 or h < 2:
            return
        if self._raw_pix and not self._raw_pix.isNull():
            scaled = self._raw_pix.scaled(
                w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        else:
            scaled = _make_placeholder_pixmap(w, h)
        self._thumb_label.setPixmap(scaled)

    def set_thumbnail(self, pix: Optional[QPixmap]):
        self._raw_pix = pix
        self._update_thumb()

    # ── style ─────────────────────────────────────────────────────────────────

    def _apply_style(self, hovered: bool):
        border = _ACCENT if hovered else _BORDER
        bg = "#31364a" if hovered else _CARD
        self.setStyleSheet(f"""
            QFrame#overviewCard {{
                background-color: {bg};
                border: 2px solid {border};
                border-radius: 10px;
            }}
        """)

    # ── events ────────────────────────────────────────────────────────────────

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._update_thumb)
        # Reposition drag hint over thumbnail area
        if hasattr(self, '_drag_hint') and hasattr(self, '_thumb_label'):
            geo = self._thumb_label.geometry()
            hint_y = geo.bottom() - self._drag_hint.height() - 8
            self._drag_hint.move(18, max(geo.top() + 4, hint_y))

    def enterEvent(self, event):
        self._apply_style(True)
        self._drag_hint.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._apply_style(False)
        self._drag_hint.hide()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_pos = event.pos()
            self._last_drag_pos = event.pos()
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._last_drag_pos is not None:
            delta = event.pos() - self._last_drag_pos
            dist = (
                (event.pos() - self._press_pos).manhattanLength()
                if self._press_pos else 0
            )
            if not self._dragging and dist >= _DRAG_THRESHOLD:
                self._dragging = True
                self.setCursor(Qt.SizeAllCursor)
            if self._dragging:
                dx, dy = float(delta.x()), float(delta.y())
                if dx != 0 or dy != 0:
                    self.rotate_requested.emit(self._tab_index, dx, dy)
                self._last_drag_pos = event.pos()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if not self._dragging:
                self.clicked.emit(self._tab_index)
            self._dragging = False
            self._last_drag_pos = None
            self._press_pos = None
            self.setCursor(Qt.PointingHandCursor)
        super().mouseReleaseEvent(event)


class OverviewWidget(QWidget):
    """
    Grid overview of all open 3D tabs — always fills the entire available area.
    1 tab = full view, 2 tabs = side-by-side halves, N tabs = equal grid cells.
    Drag on a thumbnail to rotate the model; click to navigate.
    """

    tab_requested    = pyqtSignal(int)
    rotate_requested = pyqtSignal(int, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {_BG};")

        self._tabs_ref: list = []
        self._request_refresh = None
        self._rotate_callback = None
        self._cards: Dict[int, _ThumbnailCard] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header bar ────────────────────────────────────────────────────────
        header = QWidget()
        header.setFixedHeight(52)
        header.setStyleSheet(
            f"background-color: {_CARD}; border-bottom: 1px solid {_BORDER};"
        )
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(24, 0, 24, 0)
        hlay.setSpacing(12)

        self._title_label = QLabel(t("overview.title"))
        self._title_label.setStyleSheet(
            f"color: {_TEXT}; font-size: 15px; font-weight: bold; background: transparent;"
        )
        hlay.addWidget(self._title_label)

        self._count_label = QLabel("")
        self._count_label.setStyleSheet(
            f"color: {_MUTED}; font-size: 12px; background: transparent;"
        )
        hlay.addWidget(self._count_label)
        hlay.addStretch(1)

        refresh_btn = QPushButton("⟳  Refresh")
        refresh_btn.setFixedHeight(30)
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.setToolTip("Re-capture thumbnails from all open tabs")
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_ACCENT}; color: #ffffff;
                border: none; border-radius: 6px; font-size: 12px;
                font-weight: bold; padding: 0 16px;
            }}
            QPushButton:hover {{ background-color: {_ACCENT_H}; }}
        """)
        refresh_btn.clicked.connect(self._on_refresh_clicked)
        hlay.addWidget(refresh_btn)
        outer.addWidget(header)

        # ── Grid area (fills all remaining space — no scroll) ─────────────────
        self._grid_container = QWidget()
        self._grid_container.setStyleSheet(f"background-color: {_BG};")
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setContentsMargins(10, 10, 10, 10)
        self._grid_layout.setSpacing(8)
        outer.addWidget(self._grid_container, 1)

        on_language_changed(self._retranslate)
        self._retranslate()

    def _retranslate(self):
        self._title_label.setText(t("overview.title"))

    # ── public API ────────────────────────────────────────────────────────────

    def set_refresh_callback(self, cb):
        self._request_refresh = cb

    def set_rotate_callback(self, cb):
        self._rotate_callback = cb

    def refresh(self, tabs: list):
        self._tabs_ref = tabs
        self._rebuild(tabs)

    def update_card_thumbnail(self, tab_index: int, pix: QPixmap):
        card = self._cards.get(tab_index)
        if card and pix and not pix.isNull():
            card.set_thumbnail(pix)

    # ── internal ──────────────────────────────────────────────────────────────

    def _on_refresh_clicked(self):
        if self._request_refresh:
            self._request_refresh()
        self._rebuild(self._tabs_ref)

    def _on_rotate(self, tab_index: int, dx: float, dy: float):
        if self._rotate_callback:
            self._rotate_callback(tab_index, dx, dy)
        self.rotate_requested.emit(tab_index, dx, dy)

    def _rebuild(self, tabs: list):
        self._cards.clear()

        # Clear grid and reset stretches
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if w := item.widget():
                w.deleteLater()
        for i in range(self._grid_layout.columnCount()):
            self._grid_layout.setColumnStretch(i, 0)
        for i in range(self._grid_layout.rowCount()):
            self._grid_layout.setRowStretch(i, 0)

        display_tabs = list(enumerate(tabs))
        n = len(display_tabs)
        loaded = [(i, tab) for i, tab in enumerate(tabs) if tab.file_path is not None]

        self._count_label.setText(
            f"{len(loaded)} model{'s' if len(loaded) != 1 else ''} open"
            + (f"  ·  {n - len(loaded)} empty" if n > len(loaded) else "")
        )

        if n == 0:
            empty = QLabel("No tabs open.\nClick + to open a file.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(
                f"color: {_MUTED}; font-size: 14px; background: transparent;"
            )
            self._grid_layout.addWidget(empty, 0, 0)
            self._grid_layout.setRowStretch(0, 1)
            self._grid_layout.setColumnStretch(0, 1)
            return

        cols, rows, vcols, base_span, last_span = _grid_dims(n)
        last_row_count = n - (rows - 1) * cols   # items in the last row
        is_partial_last = last_row_count < cols and rows > 1

        for c in range(vcols):
            self._grid_layout.setColumnStretch(c, 1)
        for r in range(rows):
            self._grid_layout.setRowStretch(r, 1)

        for pos, (tab_index, tab) in enumerate(display_tabs):
            ann_count = 0
            if tab.annotation_panel and hasattr(tab.annotation_panel, 'get_annotations'):
                try:
                    ann_count = len(tab.annotation_panel.get_annotations())
                except Exception:
                    pass

            card = _ThumbnailCard(
                tab_index=tab_index,
                filename=tab.filename or "Untitled",
                thumbnail=getattr(tab, 'thumbnail', None),
                annotation_count=ann_count,
            )
            card.clicked.connect(self.tab_requested)
            card.rotate_requested.connect(self._on_rotate)
            self._cards[tab_index] = card

            row, col_idx = divmod(pos, cols)
            in_partial_last = is_partial_last and row == rows - 1

            span = last_span if in_partial_last else base_span
            col_start = col_idx * span
            self._grid_layout.addWidget(card, row, col_start, 1, span)

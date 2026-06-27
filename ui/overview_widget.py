"""
Overview Widget — shows all open 3D-viewer tabs as a thumbnail grid.
Up to 10 models can be displayed simultaneously.
Clicking a card navigates to that tab.
"""
import logging
from typing import List, Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QSizePolicy,
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QPixmap, QColor, QPainter, QBrush, QPen, QFont

from ui.styles import default_theme, TOOLTIP_STYLE

logger = logging.getLogger(__name__)

# ── palette ──────────────────────────────────────────────────────────────────
_BG      = default_theme.background        # '#22262c'
_CARD    = default_theme.card_background   # '#2a2e38'
_BORDER  = default_theme.border_standard
_TEXT    = default_theme.text_primary
_MUTED   = default_theme.text_secondary
_ACCENT  = default_theme.button_primary
_ACCENT_H = default_theme.button_primary_hover

_THUMB_W = 300
_THUMB_H = 200
_CARD_W  = 320
_CARD_H  = 270

_PLACEHOLDER_ICON = "⬡"   # hex / 3D shape placeholder


def _make_placeholder_pixmap(width: int, height: int) -> QPixmap:
    """Solid-colour placeholder with a centred 3D-cube glyph."""
    pix = QPixmap(width, height)
    pix.fill(QColor("#1a1d24"))
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)

    # Faint border
    pen = QPen(QColor("#3a3f4c"), 1)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawRect(0, 0, width - 1, height - 1)

    # Icon
    font = QFont("Arial", 48)
    painter.setFont(font)
    painter.setPen(QColor("#3a3f4c"))
    painter.drawText(0, 0, width, height, Qt.AlignCenter, "⬡")

    painter.end()
    return pix


class _ThumbnailCard(QFrame):
    """A single clickable card showing one tab's thumbnail + info."""

    clicked = pyqtSignal(int)   # emits tab index in STLViewerWindow.tabs

    def __init__(self, tab_index: int, filename: str,
                 thumbnail: Optional[QPixmap],
                 annotation_count: int = 0,
                 parent=None):
        super().__init__(parent)
        self._tab_index = tab_index
        self.setFixedSize(_CARD_W, _CARD_H)
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("overviewCard")
        self._apply_style(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # ── Thumbnail image ──────────────────────────────────────────────────
        self._thumb_label = QLabel()
        self._thumb_label.setFixedSize(_THUMB_W, _THUMB_H)
        self._thumb_label.setAlignment(Qt.AlignCenter)
        self._thumb_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.set_thumbnail(thumbnail)
        layout.addWidget(self._thumb_label, 0, Qt.AlignHCenter)

        # ── Bottom info row ──────────────────────────────────────────────────
        info_row = QHBoxLayout()
        info_row.setContentsMargins(2, 0, 2, 0)
        info_row.setSpacing(4)

        # Tab badge
        badge = QLabel(f"Tab {tab_index + 1}")
        badge.setStyleSheet(f"""
            QLabel {{
                background-color: {_ACCENT};
                color: #ffffff;
                border-radius: 4px;
                font-size: 10px;
                font-weight: bold;
                padding: 2px 6px;
            }}
        """)
        badge.setFixedHeight(18)
        info_row.addWidget(badge, 0)

        # Filename
        name = filename or "Untitled"
        name_label = QLabel(name)
        name_label.setStyleSheet(f"color: {_TEXT}; font-size: 12px; font-weight: bold;")
        name_label.setToolTip(name)
        name_label.setMaximumWidth(_CARD_W - 100)
        from PyQt5.QtWidgets import QSizePolicy
        name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Elide long filenames
        fm = name_label.fontMetrics()
        elided = fm.elidedText(name, Qt.ElideMiddle, _CARD_W - 110)
        name_label.setText(elided)
        info_row.addWidget(name_label, 1)

        layout.addLayout(info_row)

        # ── Annotation count ─────────────────────────────────────────────────
        if annotation_count > 0:
            ann_label = QLabel(
                f"  {annotation_count} annotation{'s' if annotation_count > 1 else ''}"
            )
            ann_label.setStyleSheet(f"color: {_MUTED}; font-size: 10px;")
            layout.addWidget(ann_label)

    # ── helpers ──────────────────────────────────────────────────────────────

    def set_thumbnail(self, pix: Optional[QPixmap]):
        if pix and not pix.isNull():
            scaled = pix.scaled(
                _THUMB_W, _THUMB_H,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self._thumb_label.setPixmap(scaled)
        else:
            self._thumb_label.setPixmap(_make_placeholder_pixmap(_THUMB_W, _THUMB_H))

    def _apply_style(self, hovered: bool):
        border_color = _ACCENT if hovered else _BORDER
        bg = "#31364a" if hovered else _CARD
        self.setStyleSheet(f"""
            QFrame#overviewCard {{
                background-color: {bg};
                border: 2px solid {border_color};
                border-radius: 10px;
            }}
        """)

    # ── events ───────────────────────────────────────────────────────────────

    def enterEvent(self, event):
        self._apply_style(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._apply_style(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._tab_index)
        super().mousePressEvent(event)


class OverviewWidget(QWidget):
    """
    Grid overview of all open 3D tabs.
    Call refresh() each time it becomes visible.
    """

    tab_requested = pyqtSignal(int)   # tab index in STLViewerWindow.tabs

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {_BG};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header bar ───────────────────────────────────────────────────────
        header = QWidget()
        header.setFixedHeight(52)
        header.setStyleSheet(f"background-color: {_CARD}; border-bottom: 1px solid {_BORDER};")
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(24, 0, 24, 0)
        hlay.setSpacing(12)

        self._title_label = QLabel("Overview")
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
                background-color: {_ACCENT};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: bold;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background-color: {_ACCENT_H};
            }}
        """)
        refresh_btn.clicked.connect(self._on_refresh_clicked)
        hlay.addWidget(refresh_btn)

        outer.addWidget(header)

        # ── Scroll area with card grid ────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"background-color: {_BG};")

        self._grid_container = QWidget()
        self._grid_container.setStyleSheet(f"background-color: {_BG};")
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setContentsMargins(24, 24, 24, 24)
        self._grid_layout.setSpacing(18)
        self._grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        scroll.setWidget(self._grid_container)
        outer.addWidget(scroll, 1)

        # ── Empty-state label (hidden when there are tabs) ───────────────────
        self._empty_label = QLabel(
            "No 3D models open.\nClick + to open a file."
        )
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setStyleSheet(f"color: {_MUTED}; font-size: 14px; background: transparent;")
        self._grid_layout.addWidget(self._empty_label, 0, 0)

        # Internal state
        self._tabs_ref = []          # list of TabState
        self._request_refresh = None  # callable injected by STLViewerWindow

    # ── public API ───────────────────────────────────────────────────────────

    def set_refresh_callback(self, cb):
        """
        Register a callable that captures fresh thumbnails for all tabs
        before this widget redraws. Called when Refresh button is clicked.
        Signature: cb() → None
        """
        self._request_refresh = cb

    def refresh(self, tabs: list):
        """
        Rebuild the card grid from the current tab list.
        `tabs` is the STLViewerWindow.tabs list (list of TabState).
        """
        self._tabs_ref = tabs
        self._rebuild(tabs)

    # ── internal ─────────────────────────────────────────────────────────────

    def _on_refresh_clicked(self):
        if self._request_refresh:
            self._request_refresh()
        self._rebuild(self._tabs_ref)

    def _rebuild(self, tabs: list):
        """Clear and repopulate the grid."""
        # Remove all existing cards
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        loaded_tabs = [(i, t) for i, t in enumerate(tabs) if t.file_path is not None]
        all_tabs = list(enumerate(tabs))

        display_tabs = all_tabs  # show ALL tabs (even empty), so users can see what's open

        count = len(display_tabs)
        self._count_label.setText(
            f"{len(loaded_tabs)} model{'s' if len(loaded_tabs) != 1 else ''} open"
            + (f"  ·  {count - len(loaded_tabs)} empty" if count > len(loaded_tabs) else "")
        )

        if count == 0:
            self._empty_label = QLabel("No tabs open.\nClick + to open a file.")
            self._empty_label.setAlignment(Qt.AlignCenter)
            self._empty_label.setStyleSheet(
                f"color: {_MUTED}; font-size: 14px; background: transparent;"
            )
            self._grid_layout.addWidget(self._empty_label, 0, 0)
            return

        # Determine column count
        if count <= 2:
            cols = 2
        elif count <= 6:
            cols = 3
        else:
            cols = 4

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

            row, col = divmod(pos, cols)
            self._grid_layout.addWidget(card, row, col)

"""
The Project — main container widget.
Left panel: project info + navigation.
Right panel: top bar (open/save + user account) + stacked content screens.

Screens are loaded lazily — only instantiated on first navigation.
"""
import base64
import json
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple, Type

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QStackedWidget, QFileDialog, QMessageBox,
    QLineEdit, QComboBox, QDialog, QScrollArea, QSizePolicy, QSplitter,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon, QFontMetrics
from ui.styles import default_theme, make_font, dropdown_arrow_url as _get_arrow, TOOLTIP_STYLE
from ui.modal_utils import FormModal
from i18n import t, on_language_changed
from core.identity import get_display_name

_ARROW_URL = _get_arrow()

logger = logging.getLogger(__name__)

# ── palette ───────────────────────────────────────────────────────────────────
_BG       = default_theme.background
_SIDEBAR  = '#1c2029'
_CARD     = default_theme.card_background
_BORDER   = default_theme.border_standard
_TEXT     = default_theme.text_primary
_MUTED    = default_theme.text_secondary
_ACCENT   = default_theme.button_primary
_ACCENT_H = default_theme.button_primary_hover

# ── nav items — order defines sidebar display order ───────────────────────────
_NAV_KEYS = [
    'brief', 'assignment', 'timeline', 'rd', 'estimated_cost', 'traceability',
    'report', 'files', 'validation', 'prototype', 'version_comparison', 'quality_control', 'todo', 'glossary',
]
# Keep a fallback list for print label lookup; labels filled at runtime via t()
_NAV_ITEMS = [(k, k) for k in _NAV_KEYS]

# ── shared styles ─────────────────────────────────────────────────────────────
_NAV_ACTIVE = f"""
    QPushButton {{
        background-color: {_ACCENT};
        color: white; border: none; border-radius: 6px;
        padding: 10px 14px; font-size: 15px; font-weight: bold; text-align: left;
    }}
"""

_NAV_INACTIVE = f"""
    QPushButton {{
        background-color: transparent; color: {_MUTED}; border: none;
        border-radius: 6px; padding: 10px 14px; font-size: 15px; font-weight: bold; text-align: left;
    }}
    QPushButton:hover {{ background-color: #2a2e38; color: {_TEXT}; }}
"""

_NAV_SUBNAV_ACTIVE = f"""
    QPushButton {{
        background-color: {_ACCENT}; color: white; border: none;
        border-radius: 5px; padding: 7px 12px; font-size: 14px; text-align: left;
        font-weight: 600;
    }}
"""

_NAV_SUBNAV_INACTIVE = f"""
    QPushButton {{
        background-color: transparent; color: {_MUTED}; border: none;
        border-radius: 5px; padding: 7px 12px; font-size: 14px; text-align: left;
    }}
    QPushButton:hover {{ background-color: #2a2e38; color: {_TEXT}; }}
"""

_BTN_TOOLBAR = f"""
    QPushButton {{
        background-color: #2e323a; color: {_TEXT};
        border: 1px solid {default_theme.border_light};
        border-radius: 6px; font-size: 15px; padding: 4px 12px;
    }}
    QPushButton:hover {{ background-color: #3a3e48; border-color: {_ACCENT}; color: white; }}
    QPushButton:pressed {{ background-color: {default_theme.button_primary_pressed}; color: white; }}
    QPushButton:disabled {{ color: {_MUTED}; border-color: {_BORDER}; background-color: #252830; }}
""" + TOOLTIP_STYLE

_BTN_SAVE = f"""
    QPushButton {{
        background-color: {_ACCENT}; color: white; border: none;
        border-radius: 6px; font-size: 15px; font-weight: bold; padding: 4px 14px;
    }}
    QPushButton:hover {{ background-color: {_ACCENT_H}; }}
    QPushButton:pressed {{ background-color: {default_theme.button_primary_pressed}; }}
    QPushButton:disabled {{ background-color: #253545; color: #4a6070; }}
""" + TOOLTIP_STYLE

_BTN_LOCK_ACTIVE = f"""
    QPushButton {{
        background-color: #92400e; color: #fde68a; border: 1px solid #b45309;
        border-radius: 6px; font-size: 15px; font-weight: bold; padding: 4px 12px;
    }}
    QPushButton:hover {{ background-color: #78350f; border-color: #d97706; }}
    QPushButton:pressed {{ background-color: #451a03; }}
""" + TOOLTIP_STYLE

_INFO_INPUT_STYLE = f"""
    QLineEdit {{
        background-color: #1e2228; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 4px;
        padding: 3px 6px; font-size: 14px;
    }}
    QLineEdit:focus {{ border: 1px solid {_ACCENT}; }}
"""

_STATUS_KEYS = ['in_progress', 'awaiting', 'completed', 'cancelled']

_STATUS_COLORS = {
    'in_progress': '#4ade80',
    'awaiting':    '#facc15',
    'completed':   '#22d3ee',
    'cancelled':   '#f87171',
}

_STATUS_I18N = {
    'in_progress': 'project.timeline.dlg_status_progress',
    'awaiting':    'project.timeline.dlg_status_awaiting',
    'completed':   'project.timeline.dlg_status_completed',
    'cancelled':   'project.timeline.dlg_status_cancelled',
}

# Map legacy English strings saved by older project files to internal keys
_STATUS_LEGACY_MAP = {
    'In progress': 'in_progress',
    'Awaiting':    'awaiting',
    'Completed':   'completed',
    'Cancelled':   'cancelled',
}

_CONTENT_BG   = '#ffffff'
_CONTENT_MUTED = '#6b7280'

# ── credentials (single admin user) ──────────────────────────────────────────
_PROJECT_CREDENTIALS = {'chris': 'admin'}

_PROJECT_EXTS = ('.lyns.pjt', '.ectopjt', '.pjt')


def _strip_project_ext(name: str) -> str:
    """Strip any (possibly repeated) project-file extension from `name`,
    leaving the bare stem. Repeats until no known suffix remains, since a
    name can pick up more than one layer (see _normalize_project_path)."""
    while True:
        for sfx in _PROJECT_EXTS:
            if name.lower().endswith(sfx):
                name = name[:-len(sfx)]
                break
        else:
            break
    return name


def _normalize_project_path(path: str) -> str:
    """Strip any project-file extension from `path` and re-apply the
    canonical .lyns.pjt suffix exactly once.

    Windows' native save dialog treats compound extensions like ".lyns.pjt"
    as unrecognized and appends the filter's default extension again on top
    of whatever the default filename already had, so a re-save of
    "Demo.lyns.pjt" can come back from the dialog as
    "Demo.lyns.pjt.lyns.pjt". Stripping just once (as this used to) only
    undoes one layer of that, leaving the duplicate in place — so this
    strips repeatedly until no known suffix remains, however many times the
    dialog (or a user pasting a name) piled it on.
    """
    return _strip_project_ext(path) + '.lyns.pjt'


def _status_combo_style(color: str) -> str:
    """Generate the QComboBox stylesheet for the current status color."""
    return f"""
        QComboBox {{
            background-color: #1e2228; color: {color};
            border: 1px solid {_BORDER}; border-radius: 4px;
            padding: 3px 6px; font-size: 14px; font-weight: bold;
        }}
        QComboBox:focus {{ border: 1px solid {_ACCENT}; }}
        QComboBox::drop-down {{ border: none; width: 16px; }}
        QComboBox::down-arrow {{ image: url({_ARROW_URL}); width: 10px; height: 10px; }}
        QComboBox QAbstractItemView {{
            background-color: #1e2228; color: {_TEXT};
            border: 1px solid {_BORDER};
            selection-background-color: {_ACCENT};
        }}
    """


# ── Screen registry ───────────────────────────────────────────────────────────
# (key, import_path_callable) — widgets are imported and instantiated lazily.
# Using callables avoids importing all modules at startup.

def _import_screen(key: str) -> Type[QWidget]:
    if key == 'brief':
        from ui.brief import ProjectBriefWidget
        return ProjectBriefWidget
    if key == 'assignment':
        from ui.assignment_widget import AssignmentWidget
        return AssignmentWidget
    if key == 'timeline':
        from ui.timeline import TimelineWidget
        return TimelineWidget
    if key == 'validation':
        from ui.project_validation import ValidationWidget
        return ValidationWidget
    if key == 'quality_control':
        from ui.quality_control_widget import QualityControlWidget
        return QualityControlWidget
    if key == 'report':
        from ui.report import ReportWidget
        return ReportWidget
    if key == 'estimated_cost':
        from ui.estimated_cost import EstimatedCostWidget
        return EstimatedCostWidget
    if key == 'files':
        from ui.files_widget import FilesVersionsWidget
        return FilesVersionsWidget
    if key == 'rd':
        from ui.rd_widget import RdWidget
        return RdWidget
    if key == 'prototype':
        from ui.prototype_widget import PrototypeWidget
        return PrototypeWidget
    if key == 'version_comparison':
        from ui.version_comparison import VersionComparisonWidget
        return VersionComparisonWidget
    if key == 'traceability':
        from ui.traceability import TraceabilityWidget
        return TraceabilityWidget
    if key == 'todo':
        from ui.todo_widget import TodoWidget
        return TodoWidget
    if key == 'glossary':
        from ui.glossary_widget import GlossaryWidget
        return GlossaryWidget
    raise KeyError(f'Unknown screen key: {key}')


# ── Self-eliding nav button ───────────────────────────────────────────────────

class _NavButton(QPushButton):
    """QPushButton that elides its own label ("…") to fit the current width
    instead of hard-clipping mid-word — needed because these buttons use
    QSizePolicy.Ignored (so a long translation can't widen the sidebar), and
    plain QPushButton doesn't auto-elide text that no longer fits."""

    def __init__(self, text: str = '', h_padding: int = 14, parent=None):
        super().__init__(parent)
        self._full_text = text
        self._h_padding = h_padding
        super().setText(text)

    def setText(self, text: str):
        self._full_text = text
        self._reelide()

    def fullText(self) -> str:
        return self._full_text

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reelide()

    def _reelide(self):
        avail = self.width() - 2 * self._h_padding
        if avail <= 0:
            super().setText(self._full_text)
            return
        fm = QFontMetrics(self.font())
        super().setText(fm.elidedText(self._full_text, Qt.ElideRight, avail))


# ── ProjectNavPanel ───────────────────────────────────────────────────────────

class ProjectNavPanel(QWidget):
    """Left sidebar: project info card + navigation buttons."""

    info_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(230)
        self.setStyleSheet(f'background-color: {_SIDEBAR};')
        self._buttons: dict[str, QPushButton] = {}
        self._on_navigate = None
        self._photo_b64: str = ''
        self._build_ui()
        on_language_changed(self.retranslate)

    # ── construction ──────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 14, 10, 14)
        layout.setSpacing(2)

        # Info card — fixed height, never shrinks
        info_card = self._build_info_card()
        info_card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(info_card, 0)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(
            f'color: {_BORDER}; background-color: {_BORDER}; max-height: 1px; border: none; margin: 8px 0;'
        )
        layout.addWidget(sep)

        # Nav buttons in a scroll area so R&D sub-tabs never overflow
        nav_scroll = QScrollArea()
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setFrameShape(QFrame.NoFrame)
        nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        nav_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        nav_scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{
                background: transparent; width: 9px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: #6BC4E8; border-radius: 4px; min-height: 24px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {_ACCENT};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        nav_inner = QWidget()
        nav_inner.setStyleSheet('background: transparent;')
        nav_inner_l = QVBoxLayout(nav_inner)
        nav_inner_l.setContentsMargins(0, 0, 0, 0)
        nav_inner_l.setSpacing(2)

        self._build_nav_buttons(nav_inner_l)
        nav_inner_l.addStretch()

        nav_scroll.setWidget(nav_inner)
        layout.addWidget(nav_scroll, 1)

    def _build_info_card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {_CARD};
                border: 1px solid {_BORDER};
                border-radius: 10px;
            }}
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 10, 10, 10)
        card_layout.setSpacing(5)

        self._photo_btn = QPushButton(t('project.sidebar.add_photo'))
        self._photo_btn.setFixedHeight(150)
        self._photo_btn.setCursor(Qt.PointingHandCursor)
        self._photo_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #1e2228;
                border: 1px dashed {_BORDER};
                border-radius: 6px;
                color: {_MUTED}; font-size: 13px;
            }}
            QPushButton:hover {{ border-color: {_ACCENT}; color: {_ACCENT}; }}
        """)
        self._photo_btn.clicked.connect(self._upload_photo)
        card_layout.addWidget(self._photo_btn)

        self._f_company          = self._make_field(t('project.sidebar.company'))
        self._f_title            = self._make_field(t('project.sidebar.title'))
        self._f_number           = self._make_field(t('project.sidebar.number'))
        self._f_project_manager  = self._make_field(t('project.sidebar.manager'))
        self._f_start_date       = self._make_field(t('project.sidebar.start_date'))
        self._f_due_date         = self._make_field(t('project.sidebar.due_date'))
        for f in (self._f_company, self._f_title, self._f_number,
                  self._f_project_manager, self._f_start_date, self._f_due_date):
            card_layout.addWidget(f)

        self._status_combo = QComboBox()
        self._populate_status_combo()
        self._status_combo.setFixedHeight(26)
        self._status_combo.setStyleSheet(_status_combo_style(_STATUS_COLORS['in_progress']))
        self._status_combo.currentIndexChanged.connect(self._on_status_changed)
        self._status_combo.currentIndexChanged.connect(lambda _: self.info_changed.emit())
        card_layout.addWidget(self._status_combo)

        return card

    def _make_field(self, placeholder: str) -> QLineEdit:
        f = QLineEdit()
        f.setPlaceholderText(placeholder)
        f.setStyleSheet(_INFO_INPUT_STYLE)
        f.setFixedHeight(26)
        f.textChanged.connect(lambda _: self.info_changed.emit())
        return f

    def _build_nav_buttons(self, layout: QVBoxLayout):
        # R&D tab sub-navigation config (key → tab index in RdWidget)
        _RD_SUB_TABS = [
            ('rd.tab_textures',   0),
            ('rd.tab_techniques', 1),
        ]

        self._rd_sub_btns: list = []
        self._rd_subnav: Optional[QWidget] = None
        self._on_rd_tab_switch = None  # set by TheProjectWidget
        self._rd_subnav_suppress_reopen = False

        for key, _label in _NAV_ITEMS:
            label = t(f'project.nav.{key}').replace('&', '&&')
            btn = _NavButton(label, h_padding=14)
            btn.setStyleSheet(_NAV_INACTIVE)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(40)
            btn.setCheckable(True)
            # Ignored: a translated label (e.g. French "ESTIMATION DES COÛTS")
            # must never widen this button's sizeHint enough to pull the
            # sidebar itself wider — text just elides instead.
            btn.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            btn.clicked.connect(lambda _, k=key: self._navigate(k))
            self._buttons[key] = btn
            layout.addWidget(btn)

            if key == 'rd':
                # Double-click the R&D button to close the sub-nav list again.
                btn.mouseDoubleClickEvent = lambda _e: self._close_rd_subnav()

                # ── R&D sub-navigation ────────────────────────────────────────
                sub = QWidget()
                sub.setVisible(False)
                sub_lay = QVBoxLayout(sub)
                sub_lay.setContentsMargins(18, 2, 4, 4)
                sub_lay.setSpacing(1)
                for tab_key, tab_idx in _RD_SUB_TABS:
                    sub_label = t(tab_key)
                    sb = _NavButton(sub_label, h_padding=12)
                    sb.setCursor(Qt.PointingHandCursor)
                    sb.setMinimumHeight(36)
                    sb.setCheckable(True)
                    sb.setStyleSheet(_NAV_SUBNAV_INACTIVE)
                    sb.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
                    sb.clicked.connect(
                        lambda _, i=tab_idx: self._on_rd_sub_clicked(i)
                    )
                    self._rd_sub_btns.append(sb)
                    sub_lay.addWidget(sb)
                self._rd_subnav = sub
                layout.addWidget(sub)

    # ── event handlers ────────────────────────────────────────────────────────

    def _populate_status_combo(self):
        """Fill the status combo with translated labels, storing internal keys as user data."""
        current_key = self._status_combo.currentData() if self._status_combo.count() else 'in_progress'
        self._status_combo.blockSignals(True)
        self._status_combo.clear()
        for key in _STATUS_KEYS:
            self._status_combo.addItem(t(_STATUS_I18N[key]), key)
        # Restore selection
        for i in range(self._status_combo.count()):
            if self._status_combo.itemData(i) == current_key:
                self._status_combo.setCurrentIndex(i)
                break
        self._status_combo.blockSignals(False)
        self._on_status_changed(self._status_combo.currentIndex())

    def _on_status_changed(self, _index: int):
        key = self._status_combo.currentData() or 'in_progress'
        color = _STATUS_COLORS.get(key, _TEXT)
        self._status_combo.setStyleSheet(_status_combo_style(color))

    def _upload_photo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select Project Photo', '', 'Images (*.png *.jpg *.jpeg *.webp)'
        )
        if path:
            from core.image_utils import path_to_b64, b64_to_pixmap
            b64 = path_to_b64(path)
            pix = b64_to_pixmap(b64) if b64 else None
            if pix is not None:
                self._photo_b64 = b64
                scaled = pix.scaled(
                    self._photo_btn.width(), self._photo_btn.height(),
                    Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
                )
                self._photo_btn.setIcon(QIcon(scaled))
                self._photo_btn.setIconSize(self._photo_btn.size())
                self._photo_btn.setText('')
                self.info_changed.emit()

    def _navigate(self, key: str):
        for k, btn in self._buttons.items():
            btn.setStyleSheet(_NAV_ACTIVE if k == key else _NAV_INACTIVE)
            btn.setChecked(k == key)
        if self._rd_subnav is not None:
            # A double-click on the R&D button delivers press/release/press/
            # doubleClick/release. QAbstractButton emits `clicked` on *every*
            # release, so the second release of that double-click calls
            # _navigate('rd') again right after _close_rd_subnav() ran on the
            # doubleClick event — silently reopening the sub-nav and making
            # the close "not stick". Swallow just that one reopen.
            if key == 'rd' and self._rd_subnav_suppress_reopen:
                self._rd_subnav_suppress_reopen = False
            else:
                self._rd_subnav.setVisible(key == 'rd')
        if self._on_navigate:
            self._on_navigate(key)

    def _on_rd_sub_clicked(self, tab_idx: int):
        self.set_rd_active_tab(tab_idx)
        if self._on_rd_tab_switch:
            self._on_rd_tab_switch(tab_idx)

    def _close_rd_subnav(self):
        """Double-click on the R&D nav button closes its sub-nav list."""
        if self._rd_subnav is not None:
            self._rd_subnav.setVisible(False)
            # The button's own mouseRelease (right after this doubleClick
            # event) will still fire `clicked` -> _navigate('rd'); suppress
            # that one reopen so the close actually sticks.
            self._rd_subnav_suppress_reopen = True

    def show_rd_subnav(self, visible: bool):
        if self._rd_subnav is not None:
            self._rd_subnav.setVisible(visible)

    def set_rd_active_tab(self, idx: int):
        for i, sb in enumerate(self._rd_sub_btns):
            active = (i == idx)
            sb.setStyleSheet(_NAV_SUBNAV_ACTIVE if active else _NAV_SUBNAV_INACTIVE)
            sb.setChecked(active)

    def set_rd_tab_switch_callback(self, fn):
        self._on_rd_tab_switch = fn

    # ── public API ────────────────────────────────────────────────────────────

    def set_navigate_callback(self, fn):
        self._on_navigate = fn

    def select(self, key: str):
        self._navigate(key)

    def get_info_data(self) -> dict:
        return {
            'company':          self._f_company.text(),
            'title':            self._f_title.text(),
            'number':           self._f_number.text(),
            'project_manager':  self._f_project_manager.text(),
            'start_date':       self._f_start_date.text(),
            'due_date':         self._f_due_date.text(),
            'status':           self._status_combo.currentData() or 'in_progress',
            'photo_b64':        self._photo_b64,
        }

    def set_info_data(self, data: dict):
        self._f_company.setText(data.get('company', ''))
        self._f_title.setText(data.get('title', ''))
        self._f_number.setText(data.get('number', ''))
        self._f_project_manager.setText(data.get('project_manager', ''))
        self._f_start_date.setText(data.get('start_date', ''))
        self._f_due_date.setText(data.get('due_date', ''))
        status = data.get('status', 'in_progress')
        # Migrate legacy English display strings saved by older project files
        status = _STATUS_LEGACY_MAP.get(status, status)
        for i in range(self._status_combo.count()):
            if self._status_combo.itemData(i) == status:
                self._status_combo.setCurrentIndex(i)
                break
        from core.image_utils import path_to_b64, b64_to_pixmap
        photo_b64 = data.get('photo_b64', '')
        if not photo_b64 and data.get('photo_path'):
            # Legacy save from before photos were embedded — best-effort
            # migrate on load if the file still exists on THIS machine (it
            # was never portable across machines to begin with, so this
            # can't recover a photo that only ever lived on someone else's
            # disk, but it does stop re-saving from silently dropping a
            # photo that's still right there locally).
            photo_b64 = path_to_b64(data['photo_path']) or ''
        pix = b64_to_pixmap(photo_b64) if photo_b64 else None
        if pix is not None:
            self._photo_b64 = photo_b64
            scaled = pix.scaled(
                self._photo_btn.width(), self._photo_btn.height(),
                Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            self._photo_btn.setIcon(QIcon(scaled))
            self._photo_btn.setIconSize(self._photo_btn.size())
            self._photo_btn.setText('')
        else:
            # No photo in the data being loaded (e.g. a brand new project) —
            # clear whatever the previous project's photo left behind instead
            # of leaving it stuck on screen.
            self._photo_b64 = ''
            self._photo_btn.setIcon(QIcon())
            self._photo_btn.setText(t('project.sidebar.add_photo'))

    def retranslate(self):
        """Update all visible labels/buttons when language changes."""
        if not self._photo_b64:
            self._photo_btn.setText(t('project.sidebar.add_photo'))
        self._f_company.setPlaceholderText(t('project.sidebar.company'))
        self._f_title.setPlaceholderText(t('project.sidebar.title'))
        self._f_number.setPlaceholderText(t('project.sidebar.number'))
        self._f_project_manager.setPlaceholderText(t('project.sidebar.manager'))
        self._f_start_date.setPlaceholderText(t('project.sidebar.start_date'))
        self._f_due_date.setPlaceholderText(t('project.sidebar.due_date'))
        for key, btn in self._buttons.items():
            label = t(f'project.nav.{key}').replace('&', '&&')
            btn.setText(label)
        _rd_tab_keys = ['rd.tab_textures', 'rd.tab_techniques']
        for i, sb in enumerate(self._rd_sub_btns):
            sub_label = t(_rd_tab_keys[i])
            sb.setText(sub_label)
        self._populate_status_combo()


# ── Login dialog ──────────────────────────────────────────────────────────────

class ProjectLoginDialog(FormModal):
    """Login gate for The Project workspace."""

    def __init__(self, parent=None):
        super().__init__(parent, t('project.login.title'), theme=FormModal.LIGHT, min_width=380)

        # Header text (above the standard field area)
        sub = QLabel(t('project.login.subtitle'))
        sub.setStyleSheet(f'color: {_MUTED}; font-size: 15px; background: transparent; border: none;')
        self._root.addWidget(sub)
        self._root.addWidget(self._make_hline())

        self._f_user = self.add_field(t('project.login.username'), QLineEdit(), height=36)
        self._f_user.setPlaceholderText(t('project.login.username_ph'))

        self._f_pass = self.add_field(t('project.login.password'), QLineEdit(), height=36)
        self._f_pass.setPlaceholderText(t('project.login.password_ph'))
        self._f_pass.setEchoMode(QLineEdit.Password)
        self._f_pass.returnPressed.connect(self._try_login)

        self._error_lbl = QLabel('')
        self._error_lbl.setStyleSheet(
            'color: #ef4444; font-size: 14px; background: transparent; border: none;'
        )
        self._error_lbl.setVisible(False)
        self._root.addWidget(self._error_lbl)

        # Custom full-width sign-in button (no Cancel)
        sign_in = self._make_ok_btn(t('project.login.sign_in'))
        sign_in.setFixedHeight(38)
        sign_in.clicked.disconnect()          # disconnect auto-accept
        sign_in.clicked.connect(self._try_login)
        self._root.addWidget(sign_in)

        self._f_user.setFocus()

    def _try_login(self):
        username = self._f_user.text().strip().lower()
        password = self._f_pass.text()
        expected = _PROJECT_CREDENTIALS.get(username)
        if expected and password == expected:
            self.accept()
        else:
            self._error_lbl.setText(t('project.login.error'))
            self._error_lbl.setVisible(True)
            self._f_pass.clear()
            self._f_pass.setFocus()

    def get_username(self) -> str:
        return self._f_user.text().strip().lower()


# ── TheProjectWidget ──────────────────────────────────────────────────────────

class TheProjectWidget(QWidget):
    """Main container for The Project tab."""

    open_in_viewer         = pyqtSignal(str)
    restore_viewer_tab     = pyqtSignal(str, str, str)  # temp bundle path, original tab name, tab id ('' if none)
    clear_viewer_tabs      = pyqtSignal()  # close whatever's open before restoring a loaded project's tabs
    qc_model_remove_requested = pyqtSignal(object)
    qc_upload_requested    = pyqtSignal()
    project_info_changed   = pyqtSignal(dict)  # sidebar info, for widgets outside The Project (e.g. Technical Overview)
    restore_technical_overview = pyqtSignal(str)  # temp .ecto bundle path
    restore_drawing_scale = pyqtSignal(str, object)  # temp source-file path, state dict
    # Emitted at the very start of every save, before _bundle_viewer_tabs()
    # reads self._viewer_tabs — that list is only ever a snapshot the main
    # window pushed in (set_viewer_tabs), refreshed on mode-switches/tab
    # changes/file loads, but NOT on every single edit (e.g. adding an
    # annotation to an already-open tab, or opening a project without ever
    # visiting this screen). Saving via the File menu or this screen's own
    # Save button without an intervening refresh silently bundled whatever
    # stale (possibly empty) list was last pushed — up to and including
    # losing 3D tabs from the save entirely. The main window connects this
    # to its own _push_viewers_to_project so every save starts fresh.
    viewer_tabs_sync_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_path: Optional[str] = None
        self._unsaved_changes = False
        self._current_screen_key: Optional[str] = None
        self._project_password_hash: Optional[str] = None  # SHA-256 hash; None = no protection
        self._created_by: Optional[str] = None  # OS username who first created the file
        self._created_at: Optional[str] = None  # ISO timestamp of first save
        self._read_only = False  # True when opened while someone else's lock is active
        self._loaded_snapshot: Optional[dict] = None  # data as last read from/written to disk — merge base
        self._component_syncing = False  # guard against brief↔traceability sync loops
        self._viewer_tabs: list = []  # TabState list injected from main window before save
        # Direct refs to the Technical Overview workspace, injected from the main
        # window (it lives outside The Project) so save/load can reach it the
        # same way _viewer_tabs lets us reach the 3D viewer tabs.
        self._technical_overview = None
        self._technical_sidebar = None
        # Same pattern for the Drawing Scale workspace.
        self._scale_canvas = None
        self._scale_sidebar = None
        # Lazy screen registry: key → widget instance (None until first visited)
        self._screen_widgets: dict[str, Optional[QWidget]] = {k: None for k, _ in _NAV_ITEMS}
        self._screen_idx: dict[str, int] = {}
        self._pending_restoration: dict[str, dict] = {}
        # Cached viewer list so QC screen gets viewers even when first created after set_viewers
        self._pending_viewers: list = []
        self._pending_active_viewer = None
        self.setStyleSheet(f'background-color: {_BG};')
        self._build_ui()
        self._setup_autosave()
        self._setup_lock_heartbeat()
        on_language_changed(self._on_language_changed)

    # ── construction ──────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(4)
        self._splitter.setStyleSheet(f"""
            QSplitter::handle:horizontal {{
                background-color: {_BORDER};
                width: 4px;
            }}
            QSplitter::handle:horizontal:hover {{
                background-color: {default_theme.button_primary};
            }}
        """)
        outer.addWidget(self._splitter)

        self._nav = ProjectNavPanel()
        self._nav.set_navigate_callback(self._on_navigate)
        self._nav.info_changed.connect(self.mark_unsaved)
        self._nav.info_changed.connect(self._on_project_info_changed)
        # Fixed width — prevents any screen change or translation from nudging
        # the splitter and shrinking the sidebar.
        self._nav.setFixedWidth(300)
        self._splitter.addWidget(self._nav)

        right_panel = QWidget()
        right_panel.setStyleSheet(f'background-color: {_CONTENT_BG};')
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self._build_top_bar())

        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f'background-color: {_CONTENT_BG};')
        right_layout.addWidget(self._stack, 1)

        self._splitter.addWidget(right_panel)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)

        # Eagerly load only the default screen shown at startup
        self._nav.select('brief')
        self._ensure_screen('brief')
        info = self._nav.get_info_data()
        if (ec := self._screen_widgets.get('estimated_cost')) is not None:
            ec.update_project_info(info)
        if (rw := self._screen_widgets.get('report')) is not None:
            rw.update_project_info(info)

    def _build_top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(34)
        bar.setStyleSheet(f"""
            QWidget {{
                background-color: {_SIDEBAR};
                border-bottom: 1px solid {_BORDER};
            }}
        """)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)

        # New Project / Open Project / Save Project / Password are now available from
        # the always-visible File menu button in the main mode bar (stl_viewer.py),
        # so the duplicate buttons here are hidden rather than deleted — this keeps
        # _update_lock_btn()/_retranslate_topbar()/etc. working unchanged since they
        # still reference these widgets, while freeing up this bar visually.
        self._new_btn = QPushButton(t('project.topbar.new'))
        self._new_btn.setStyleSheet(_BTN_TOOLBAR); self._new_btn.setFixedHeight(28)
        self._new_btn.setCursor(Qt.PointingHandCursor)
        self._new_btn.setToolTip(t('project.topbar.tip_new'))
        self._new_btn.clicked.connect(self._on_new_project)
        self._new_btn.hide()

        self._open_btn = QPushButton(t('project.topbar.open'))
        self._open_btn.setStyleSheet(_BTN_TOOLBAR); self._open_btn.setFixedHeight(28)
        self._open_btn.setCursor(Qt.PointingHandCursor)
        self._open_btn.setToolTip(t('project.topbar.tip_open'))
        self._open_btn.clicked.connect(self._on_open_project)
        self._open_btn.hide()

        self._save_btn = QPushButton(t('project.topbar.save'))
        self._save_btn.setStyleSheet(_BTN_SAVE); self._save_btn.setFixedHeight(28)
        self._save_btn.setCursor(Qt.PointingHandCursor)
        self._save_btn.setToolTip(t('project.topbar.tip_save'))
        self._save_btn.clicked.connect(self._on_save_project)
        self._save_btn.hide()

        self._print_btn = QPushButton(t('project.topbar.print'))
        self._print_btn.setStyleSheet(_BTN_TOOLBAR); self._print_btn.setFixedHeight(28)
        self._print_btn.setCursor(Qt.PointingHandCursor)
        self._print_btn.setToolTip(t('project.topbar.tip_print'))
        self._print_btn.clicked.connect(self._on_print)

        self._lock_btn = QPushButton(t('project.topbar.password'))
        self._lock_btn.setStyleSheet(_BTN_TOOLBAR); self._lock_btn.setFixedHeight(28)
        self._lock_btn.setCursor(Qt.PointingHandCursor)
        self._lock_btn.setToolTip(t('project.topbar.tip_password'))
        self._lock_btn.clicked.connect(self._on_password_btn)
        self._lock_btn.hide()

        layout.addWidget(self._print_btn)

        self._project_name_lbl = QLabel(t('project.topbar.no_project'))
        self._project_name_lbl.setStyleSheet(
            f'color: {_MUTED}; font-size: 14px; background: transparent; border: none;'
        )
        layout.addSpacing(6)
        layout.addWidget(self._project_name_lbl)
        layout.addStretch()

        return bar

    # ── lazy screen management ────────────────────────────────────────────────

    def _ensure_screen(self, key: str) -> QWidget:
        """Return the screen widget for key, creating it on first call."""
        if self._screen_widgets.get(key) is None:
            cls = _import_screen(key)
            widget = cls()
            self._wire_screen(key, widget)
            idx = self._stack.addWidget(widget)
            self._screen_widgets[key] = widget
            self._screen_idx[key] = idx
            # Restore data saved during a language change
            if key in self._pending_restoration:
                saved = self._pending_restoration.pop(key)
                if hasattr(widget, 'set_data'):
                    widget.set_data(saved)
        return self._screen_widgets[key]

    def _wire_screen(self, key: str, widget: QWidget):
        """Connect signals for a newly created screen widget."""
        if hasattr(widget, 'changed'):
            widget.changed.connect(self.mark_unsaved)
        if key == 'estimated_cost' and hasattr(widget, 'changed'):
            widget.changed.connect(self._on_estimated_cost_changed)
        if key == 'files' and hasattr(widget, 'open_in_viewer'):
            widget.open_in_viewer.connect(self.open_in_viewer)
        if key == 'brief' and hasattr(widget, 'changed'):
            widget.changed.connect(self._sync_traceability_from_brief)
        if key == 'traceability' and hasattr(widget, 'changed'):
            widget.changed.connect(self._sync_brief_from_traceability)
        if key in ('traceability', 'assignment', 'timeline', 'report', 'quality_control') and hasattr(widget, 'update_project_info'):
            # The sidebar's main photo only reaches an already-open screen via
            # _on_project_info_changed — a freshly (lazily) created screen
            # never got that first push, so its photo (Traceability's main
            # product thumbnail, Assignment's canvas background, Report's
            # header photo, ...) stayed blank until some unrelated info field
            # changed afterwards. Seed it once with the current info right at
            # construction time.
            widget.update_project_info(self._nav.get_info_data())
        if key == 'rd' and hasattr(widget, 'tab_changed'):
            widget.tab_changed.connect(self._on_rd_tab_changed)
            # Set the callback so sidebar sub-items call switch_tab on the widget
            self._nav.set_rd_tab_switch_callback(widget.switch_tab)
        if key == 'quality_control' and hasattr(widget, 'model_remove_requested'):
            widget.model_remove_requested.connect(self.qc_model_remove_requested)
            widget.upload_requested.connect(self.qc_upload_requested)
        if key == 'quality_control' and hasattr(widget, 'set_viewers') and self._pending_viewers:
            # Replay the cached viewer list so the QC screen is fully wired
            # even when the user first opens it after models are already loaded.
            widget.set_viewers(self._pending_viewers, active_viewer=self._pending_active_viewer)
        if key == 'report' and hasattr(widget, 'changed'):
            widget.changed.connect(self._sync_qc_logo_from_report)
        if key == 'quality_control':
            # Seed the QC logo from whatever's already on the Report screen
            # (e.g. loaded from a saved project) right at creation time —
            # otherwise it stays blank until the report's logo changes again.
            self._sync_qc_logo_from_report(qc_widget=widget)

    # ── navigation ────────────────────────────────────────────────────────────

    def _on_navigate(self, key: str):
        self._current_screen_key = key
        widget = self._ensure_screen(key)
        self._stack.setCurrentIndex(self._screen_idx[key])
        if key == 'rd':
            # Sync sidebar highlight to whatever tab is currently active
            current_tab = getattr(widget, '_tabs', None)
            if current_tab is not None:
                self._nav.set_rd_active_tab(current_tab.currentIndex())
        elif key == 'validation':
            self._push_validation_costs()
        elif key == 'traceability':
            self._sync_traceability_from_brief()

    def _on_rd_tab_changed(self, idx: int):
        """Keep sidebar sub-nav in sync when user clicks a tab directly."""
        self._nav.set_rd_active_tab(idx)

    def _on_print(self):
        key = self._current_screen_key
        if key is None:
            from ui.modal_utils import show_message_dialog
            show_message_dialog(self, t('project.msg.nothing_to_print'),
                                t('project.msg.open_section'))
            return
        widget = self._screen_widgets.get(key)
        if widget is None:
            return
        # Human-readable label for the dialog title
        label = t(f'project.nav.{key}')
        # Strip emoji prefix for the window title
        title = label.split('\xa0')[-1].strip() if '\xa0' in label else label.strip()
        landscape = (key == 'timeline')
        from ui.print_utils import print_section
        print_section(key, widget, title, self,
                      landscape=landscape,
                      project_info=self._nav.get_info_data())

    def _on_project_info_changed(self):
        info = self._nav.get_info_data()
        if w := self._screen_widgets.get('brief'):
            w.update_project_info(info)
        if w := self._screen_widgets.get('timeline'):
            w.update_project_info(info)
        if w := self._screen_widgets.get('estimated_cost'):
            w.update_project_info(info)
        if w := self._screen_widgets.get('report'):
            w.update_project_info(info)
        if w := self._screen_widgets.get('traceability'):
            w.update_project_info(info)
        if w := self._screen_widgets.get('assignment'):
            w.update_project_info(info)
        if w := self._screen_widgets.get('quality_control'):
            w.update_project_info(info)
        self.project_info_changed.emit(info)

    def _push_validation_costs(self):
        ec = self._screen_widgets.get('estimated_cost')
        val = self._screen_widgets.get('validation')
        brief = self._screen_widgets.get('brief')
        if val and ec:
            val.update_cost_summary(
                ec.get_best_summary(),
                ec._currency,
                self._parse_target_budget(brief),
            )

    def _parse_target_budget(self, brief_widget) -> float:
        if brief_widget is None:
            return 0.0
        raw = brief_widget.get_data().get('cost', '') or ''
        cleaned = raw.strip().replace(',', '').replace(' ', '')
        for sym in ('€', '$', '£', 'Fr', '¥', 'د.إ'):
            cleaned = cleaned.replace(sym, '')
        try:
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0

    def _sync_qc_logo_from_report(self, qc_widget=None):
        """Copy the company logo set on the Report screen into the Quality
        Control screen's own logo field, so the same logo doesn't have to be
        uploaded a second time there. The Report screen's logo is treated as
        the source of truth — QC's own logo field just mirrors it.

        qc_widget — pass the QC widget directly when called from _wire_screen
        during QC's own construction: at that point self._screen_widgets['quality_control']
        hasn't been set yet (_ensure_screen assigns it only after _wire_screen
        returns), so the dict lookup alone would silently find nothing and the
        seed would never happen."""
        report = self._screen_widgets.get('report')
        qc = qc_widget if qc_widget is not None else self._screen_widgets.get('quality_control')
        if report is None or qc is None:
            return
        if not hasattr(report, 'get_logo_pixmap') or not hasattr(qc, 'set_company_logo'):
            return
        pix = report.get_logo_pixmap()
        if pix is not None and not pix.isNull():
            qc.set_company_logo(pix)

    def _sync_traceability_from_brief(self):
        """Push brief component names into traceability (full reconcile)."""
        if self._component_syncing:
            return
        brief = self._screen_widgets.get('brief')
        trace = self._screen_widgets.get('traceability')
        if brief and trace:
            self._component_syncing = True
            try:
                trace.update_components_from_brief(brief.get_data().get('components', []))
            finally:
                self._component_syncing = False

    def _sync_brief_from_traceability(self):
        """Fully reconcile brief components to match traceability non-main components.

        Preserves existing Material/Colour values for components whose name is unchanged.
        Removes rows deleted in traceability; adds rows for components added in traceability.
        """
        if self._component_syncing:
            return
        brief = self._screen_widgets.get('brief')
        trace = self._screen_widgets.get('traceability')
        if not (brief and trace):
            return
        trace_names = trace.get_non_main_component_names()
        current_rows = brief.get_data().get('components', [])

        # Preserve material/colour for any name that still exists
        existing_by_name = {
            row[0].strip(): row
            for row in current_rows
            if row and row[0].strip()
        }

        new_rows = []
        for name in trace_names:
            if name in existing_by_name:
                new_rows.append(existing_by_name[name])
            else:
                new_rows.append([name, '', ''])

        old_names = [r[0].strip() for r in current_rows if r and r[0].strip()]
        if old_names == trace_names:
            return  # nothing changed

        self._component_syncing = True
        try:
            brief._s_components.replace_components(new_rows)
        finally:
            self._component_syncing = False

    def _on_estimated_cost_changed(self):
        ec_idx = self._screen_idx.get('estimated_cost', -1)
        if self._stack.currentIndex() == ec_idx:
            self._push_validation_costs()

    # ── language change ───────────────────────────────────────────────────────

    def _retranslate_topbar(self):
        """Update only the topbar static labels/buttons."""
        self._new_btn.setText(t('project.topbar.new'))
        self._new_btn.setToolTip(t('project.topbar.tip_new'))
        self._open_btn.setText(t('project.topbar.open'))
        self._open_btn.setToolTip(t('project.topbar.tip_open'))
        self._save_btn.setText(t('project.topbar.save'))
        self._save_btn.setToolTip(t('project.topbar.tip_save'))
        self._print_btn.setText(t('project.topbar.print'))
        self._print_btn.setToolTip(t('project.topbar.tip_print'))
        self._update_lock_btn()
        if not self._project_path:
            self._project_name_lbl.setText(t('project.topbar.no_project'))

    def _on_language_changed(self):
        """Retranslate the shell UI and reload all content screens with preserved data."""
        # 1. Save data from every loaded screen
        saved = {}
        for key, w in self._screen_widgets.items():
            if w is not None and hasattr(w, 'get_data'):
                saved[key] = w.get_data()

        # 2. Save project nav info
        project_info = self._nav.get_info_data()
        current_key = self._current_screen_key

        # 3. Destroy all screen widgets
        for key in list(self._screen_widgets.keys()):
            w = self._screen_widgets[key]
            if w is not None:
                self._stack.removeWidget(w)
                w.deleteLater()
            self._screen_widgets[key] = None
        self._screen_idx.clear()

        # 4. Retranslate the static shell (nav + topbar)
        self._nav.retranslate()
        self._retranslate_topbar()

        # 5. Keep saved data available for lazy restoration. MERGE into any
        # restoration still pending from an earlier language switch instead
        # of replacing it outright — only the widgets alive *this* round show
        # up in `saved` (destroyed/not-yet-reopened tabs are None and get
        # skipped above), so a plain assignment here would silently drop the
        # still-unclaimed data for any tab the user hadn't revisited yet.
        # That was the root cause of "switching language wipes other tabs'
        # data" — a second toggle before reopening every tab discarded
        # whatever was still waiting to be restored.
        self._pending_restoration.update({k: v for k, v in saved.items() if v})

        # 6. Restore project info (placeholders are now updated)
        self._nav.set_info_data(project_info)

        # 7. Reload the current screen (creates it fresh in new language)
        if current_key:
            self._ensure_screen(current_key)
            self._stack.setCurrentIndex(self._screen_idx[current_key])
            self._on_project_info_changed()
            if current_key == 'validation':
                self._push_validation_costs()
            elif current_key == 'traceability':
                self._sync_traceability_from_brief()

    # ── viewer passthrough (for QC screen) ───────────────────────────────────

    def set_viewer(self, viewer_widget):
        """Pass the current tab's viewer to QC screen (legacy single-viewer path)."""
        if 'quality_control' in self._screen_widgets and self._screen_widgets['quality_control']:
            self._screen_widgets['quality_control'].set_viewer(viewer_widget)

    def set_viewers(self, viewers: list, active_viewer=None):
        """Pass all loaded (label, viewer_widget) pairs to the QC screen."""
        # Always cache so the QC screen gets the list even if it's created lazily later
        self._pending_viewers = viewers
        self._pending_active_viewer = active_viewer
        if 'quality_control' in self._screen_widgets and self._screen_widgets['quality_control']:
            self._screen_widgets['quality_control'].set_viewers(viewers, active_viewer=active_viewer)

    def set_viewer_tabs(self, tabs: list) -> None:
        """Store the full TabState list so _save_project can embed viewer bundles."""
        self._viewer_tabs = list(tabs)

    def set_technical_overview_refs(self, technical_overview, technical_sidebar) -> None:
        """Store direct refs to the Technical Overview workspace so _save_project
        can pull its current state, same as set_viewer_tabs does for the 3D viewer."""
        self._technical_overview = technical_overview
        self._technical_sidebar = technical_sidebar

    def set_scale_refs(self, scale_canvas, scale_sidebar) -> None:
        """Store direct refs to the Drawing Scale workspace so _save_project
        can pull its current state, same as set_technical_overview_refs."""
        self._scale_canvas = scale_canvas
        self._scale_sidebar = scale_sidebar

    def show_qc_loading(self):
        """Show the loading overlay on the QC viewer area while a model is loading."""
        qc = self._screen_widgets.get('quality_control')
        if qc:
            qc.show_loading()

    def hide_qc_loading(self):
        """Hide the QC viewer loading overlay after a model finishes loading."""
        qc = self._screen_widgets.get('quality_control')
        if qc:
            qc.hide_loading()

    # ── top bar ───────────────────────────────────────────────────────────────

    # ── project file operations ───────────────────────────────────────────────

    def _on_new_project(self):
        if self._unsaved_changes and not self._confirm_discard():
            return

        # Reset the sidebar info card (company, title, photo, dates, ...)
        self._nav.set_info_data({})

        # Reset every screen that's already been created back to its blank
        # state — same per-key pattern _load_project uses to populate them,
        # just with empty data instead of data read from a file. Screens
        # never opened this session don't need touching; they start blank.
        for key, _ in _NAV_ITEMS:
            w = self._screen_widgets.get(key)
            if w is not None and hasattr(w, 'set_data'):
                w.set_data({})
        # Also drop any data queued for a screen torn down by a language
        # switch — otherwise it would silently reappear (or get saved into
        # the new project) once that screen is reopened.
        self._pending_restoration.clear()

        # Whatever's open in the 3D viewer belongs to the project being
        # closed, not to the new one.
        self.clear_viewer_tabs.emit()

        # Same for the Technical Overview workspace — it's now part of the
        # saved project too, so it must reset along with everything else.
        if self._technical_overview is not None and self._technical_sidebar is not None:
            if hasattr(self._technical_overview, 'clear_all'):
                self._technical_overview.clear_all()
            if hasattr(self._technical_overview, 'canvas'):
                self._technical_overview.canvas.clear_image()
            if hasattr(self._technical_sidebar, 'reset'):
                self._technical_sidebar.reset()

        # Same for the Drawing Scale workspace.
        if self._scale_canvas is not None and self._scale_sidebar is not None:
            if hasattr(self._scale_canvas, 'reset_workspace'):
                self._scale_canvas.reset_workspace()
            if hasattr(self._scale_sidebar, 'reset'):
                self._scale_sidebar.reset()

        # Release this session's lock on whatever project is being closed —
        # otherwise it stays marked as "open" until the app itself quits.
        self.release_lock()

        self._project_path = None
        self._unsaved_changes = False
        self._project_password_hash = None
        self._created_by = None
        self._created_at = None
        self._read_only = False
        self._loaded_snapshot = None
        self._update_lock_btn()
        self._update_title()

    def _on_open_project(self):
        if self._unsaved_changes and not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, 'Open Project', '',
            'LYNS Project (*.lyns.pjt);;All Files (*)'
        )
        if not path:
            return
        try:
            self._load_project(path)
        except Exception as e:
            logger.error(f'Failed to open project: {e}', exc_info=True)
            QMessageBox.critical(self, t('project.msg.open_failed'), t('project.msg.open_error').format(e=e))

    def _on_save_project(self):
        if self._read_only:
            self._warn_read_only()
            return
        if not self._project_path:
            # Pass the bare stem (no extension) as the suggested filename —
            # Windows' native dialog appends the filter's ".lyns.pjt" itself,
            # but if the suggested name already ends in ".lyns.pjt" it
            # doesn't recognize that as "already there" and appends it
            # again, showing "project.lyns.pjt.lyns.pjt" in the box.
            path, _ = QFileDialog.getSaveFileName(
                self, 'Save Project', 'project',
                'LYNS Project (*.lyns.pjt);;All Files (*)'
            )
            if not path:
                return
            self._project_path = _normalize_project_path(path)
            self._acquire_lock_for_current_path()
        try:
            saved = self._save_project(self._project_path)
        except Exception as e:
            logger.error(f'Failed to save project: {e}', exc_info=True)
            QMessageBox.critical(self, t('project.msg.save_failed'), t('project.msg.save_error').format(e=e))
        else:
            if saved:
                from ui.modal_utils import show_message_dialog
                show_message_dialog(self, t('project.msg.save_success_title'), t('project.msg.save_success_body'))

    def _on_save_project_as(self):
        """Always prompt for a new file path and save there, regardless of
        whether the project already has one (unlike _on_save_project, which
        reuses the existing path once set)."""
        if self._read_only:
            self._warn_read_only()
            return
        # Bare stem, same reasoning as _on_save_project above — an already-
        # saved project's path already ends in ".lyns.pjt", so it has to be
        # stripped before being offered back to the dialog as a suggestion.
        default_name = (
            _strip_project_ext(os.path.basename(self._project_path))
            if self._project_path else 'project'
        )
        path, _ = QFileDialog.getSaveFileName(
            self, t('project.topbar.save_as'), default_name,
            'LYNS Project (*.lyns.pjt);;All Files (*)'
        )
        if not path:
            return
        new_path = _normalize_project_path(path)
        if new_path != self._project_path:
            old_path = self._project_path
            self._project_path = new_path
            if old_path:
                # This session no longer has the old path open — release its
                # lock rather than leaving it orphaned (nothing else still
                # points at old_path to refresh or release it later).
                from core.file_lock import release_lock as _release_lock
                _release_lock(old_path)
            self._acquire_lock_for_current_path()
        try:
            saved = self._save_project(self._project_path)
        except Exception as e:
            logger.error(f'Failed to save project as: {e}', exc_info=True)
            QMessageBox.critical(self, t('project.msg.save_failed'), t('project.msg.save_error').format(e=e))
        else:
            if saved:
                from ui.modal_utils import show_message_dialog
                show_message_dialog(self, t('project.msg.save_success_title'), t('project.msg.save_success_body'))

    def _save_project(self, path: str) -> bool:
        """Write the project to `path`. Returns False without writing
        anything if the user cancelled a conflict-resolution prompt along
        the way — callers must check this before reporting success."""
        # Must happen before self._viewer_tabs is read below (via
        # _bundle_viewer_tabs) — see viewer_tabs_sync_requested's docstring.
        self.viewer_tabs_sync_requested.emit()
        now = datetime.now(timezone.utc).isoformat()
        user = get_display_name()
        if self._created_by is None:
            self._created_by = user
        if self._created_at is None:
            self._created_at = now
        data = {
            'file_type': 'lyns.pjt',
            'version': '1.0',
            'created_by': self._created_by,
            'created_at': self._created_at,
            'last_saved_by': user,
            'last_saved_at': now,
            'project_info': self._nav.get_info_data(),
        }
        if self._project_password_hash:
            data['password_hash'] = self._project_password_hash
        for key, _ in _NAV_ITEMS:
            w = self._screen_widgets.get(key)
            if w is not None and hasattr(w, 'get_data'):
                data[key] = w.get_data()
            elif key in self._pending_restoration:
                # A language switch tore this screen down and it hasn't been
                # reopened since, so there's no live widget to ask — but its
                # last-known data is still waiting here for lazy restoration.
                # Falling through to {} would silently wipe it from the save
                # file, which was the root cause of saved projects coming
                # back with some tabs' data missing.
                data[key] = self._pending_restoration[key]
            else:
                data[key] = {}

        # Bundle each viewer tab (model + annotations + drawings + texture) as base64
        data['viewer_tabs'] = self._bundle_viewer_tabs()

        # Bundle the Technical Overview workspace (document + annotations + metadata)
        data['technical_overview'] = self._bundle_technical_overview()

        # Bundle the Drawing Scale workspace (source drawing + calibration/shapes)
        data['drawing_scale'] = self._bundle_drawing_scale()

        final_data = self._resolve_save_conflicts(path, data)
        if final_data is None:
            return False  # user cancelled the conflict-resolution prompt — nothing written

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(final_data, f, indent=2, ensure_ascii=False)
        self._loaded_snapshot = final_data
        self._unsaved_changes = False
        self._update_title()
        from core.file_lock import refresh_lock
        refresh_lock(path)
        logger.info(f'Project saved to {path} by {user}')
        return True

    def _resolve_save_conflicts(self, path: str, local_data: dict) -> Optional[dict]:
        """Re-reads what's actually on disk and three-way merges it with
        local_data if someone else saved since this session last touched
        the file. Returns the data to write, or None if the user cancelled
        a conflict prompt (nothing should be written in that case).
        Returns local_data unchanged — today's plain-overwrite behavior,
        zero extra cost — whenever there's nothing to merge against."""
        if self._loaded_snapshot is None or not os.path.exists(path):
            return local_data  # first save to this path, or brand new file — nothing to diff

        try:
            with open(path, 'r', encoding='utf-8') as f:
                remote_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f'_resolve_save_conflicts: could not re-read {path}, overwriting: {e}')
            return local_data

        if remote_data == self._loaded_snapshot:
            return local_data  # nobody else touched it since we loaded/last saved

        base_data = dict(self._loaded_snapshot)
        local_data = dict(local_data)
        remote_data = dict(remote_data)

        # technical_overview is stored as one opaque {'bundle_b64': ...}
        # blob, but re-zipping it on every save embeds a fresh timestamp
        # plus non-deterministic zip-entry mtimes even when nothing inside
        # actually changed — comparing those raw bytes made this section
        # look "conflicting" on almost every concurrent save regardless of
        # whether Technical Overview was ever touched. Decode all three
        # sides to their real parts (sidebar metadata / document /
        # annotations) before merging, so equality is judged on content,
        # not incidental re-encoding noise. Each decode may return a temp
        # dir holding the extracted document/images — kept alive until
        # after re-encoding below, since whichever side "wins" the merge
        # may still need those files on disk.
        temp_dirs = []

        def _decode(entry):
            structural, temp_dir = self._decode_technical_overview(entry)
            if temp_dir:
                temp_dirs.append(temp_dir)
            return structural

        base_data['technical_overview'] = _decode(base_data.get('technical_overview'))
        local_data['technical_overview'] = _decode(local_data.get('technical_overview'))
        remote_data['technical_overview'] = _decode(remote_data.get('technical_overview'))

        # viewer_tabs (the 3D model tabs) have the exact same non-determinism
        # problem — each tab is its own re-zipped .lyns bundle — plus each
        # tab needs its own decode so the merge can tell "same tab, edited"
        # apart from "different tab" (see core/project_merge.py's
        # _merge_viewer_tabs). Re-encoding isn't needed afterward: whichever
        # side wins keeps its own already-encoded bundle_b64 verbatim.
        def _decode_tabs(entries):
            structural, tab_temp_dirs = self._decode_viewer_tabs(entries)
            temp_dirs.extend(tab_temp_dirs)
            return structural

        base_data['viewer_tabs'] = _decode_tabs(base_data.get('viewer_tabs'))
        local_data['viewer_tabs'] = _decode_tabs(local_data.get('viewer_tabs'))
        remote_data['viewer_tabs'] = _decode_tabs(remote_data.get('viewer_tabs'))

        # assignment tabs need every item to have an 'id' before merging.
        # local_data's tabs already have one (they come straight from the
        # live widget), but base/remote are raw JSON off disk — a save
        # from before tabs had stable ids has none at all there, so two
        # sides independently deriving the same positional fallback id for
        # an untouched legacy tab would otherwise look like a brand-new id
        # collision to the merge engine (which assumes numeric ids for
        # renumbering) instead of being recognized as the same tab.
        from ui.assignment_widget import ensure_tab_ids
        for d in (base_data, local_data, remote_data):
            assignment = d.get('assignment')
            if assignment and 'tabs' in assignment:
                d['assignment'] = dict(assignment)
                d['assignment']['tabs'] = ensure_tab_ids(assignment['tabs'])

        try:
            from core.project_merge import merge_project, field_conflicts_only, fold_linked_conflicts
            merged, conflicts = merge_project(base_data, local_data, remote_data)

            # Collapse conflicts on fields that are just auto-filled mirrors of
            # an already-conflicting field elsewhere (e.g. the sidebar Title
            # copied into Report/Brief/Quality Control) into one prompt instead
            # of asking the same question several times for one edit.
            interactive = field_conflicts_only(fold_linked_conflicts(conflicts))
            if interactive:
                from ui.merge_conflict_dialog import MergeConflictDialog
                dlg = MergeConflictDialog(self, interactive)
                if dlg.exec_() != QDialog.Accepted:
                    return None  # cancelled — abort this save entirely, try again later
                dlg.apply_resolutions()

            merged['technical_overview'] = self._encode_technical_overview(merged.get('technical_overview'))
            # Strip the decode-only fields back down to the saved shape —
            # no re-encoding needed, since bundle_b64 was carried through
            # unchanged on whichever side won each tab.
            merged['viewer_tabs'] = [
                {'id': tab['id'], 'tab_name': tab.get('tab_name', ''), 'bundle_b64': tab['bundle_b64']}
                for tab in merged.get('viewer_tabs', [])
            ]
        finally:
            import shutil
            for d in temp_dirs:
                shutil.rmtree(d, ignore_errors=True)

        # Push any remotely-changed sections back into whichever screens are
        # currently live, so the visible UI doesn't silently diverge from
        # what was just written (e.g. a to-do task someone else added must
        # actually appear on the still-open To-Do screen, not just exist in
        # the file). Scoped to the Project's own nav screens + info card —
        # viewer_tabs/technical_overview/drawing_scale aren't live-refreshed
        # here, since pushing those back means reloading 3D/document
        # content mid-session, a heavier operation than this safety net
        # needs to solve right now.
        self._apply_merged_data_to_screens(merged)

        return merged

    def _decode_technical_overview(self, entry: Optional[dict]) -> Tuple[dict, Optional[str]]:
        """Decode a saved technical_overview {'bundle_b64': ...} entry into
        its real parts for merge comparison. Returns (structural_dict,
        temp_dir) — temp_dir (holding the extracted document + any
        annotation images) must stay alive until after
        _encode_technical_overview runs, since its files may be the ones
        that end up re-zipped if this side wins the merge. Returns the
        all-empty structural shape (document_bytes=None, matching
        _bundle_technical_overview's own "nothing to save" contract) for a
        None/absent entry or on any decode failure."""
        empty: dict = {'metadata': {}, 'document_bytes': None, 'document_ext': '', 'annotations': []}
        if not entry or not entry.get('bundle_b64'):
            return empty, None
        from core.ecto_format import EctoFormat
        fd, tmp_ecto = tempfile.mkstemp(suffix='.ecto')
        os.close(fd)
        try:
            Path(tmp_ecto).write_bytes(base64.b64decode(entry['bundle_b64']))
            doc_path, annotations, metadata, _passcode, temp_dir_or_err = EctoFormat.import_technical(tmp_ecto)
            if doc_path is None:
                logger.warning(f'_decode_technical_overview: could not decode: {temp_dir_or_err}')
                return empty, None
            return {
                'metadata': metadata or {},
                'document_bytes': Path(doc_path).read_bytes(),
                'document_ext': os.path.splitext(doc_path)[1],
                'annotations': annotations or [],
            }, temp_dir_or_err
        except Exception as e:
            logger.warning(f'_decode_technical_overview: could not decode: {e}')
            return empty, None
        finally:
            try:
                os.remove(tmp_ecto)
            except OSError:
                pass

    def _encode_technical_overview(self, structural: Optional[dict]) -> Optional[dict]:
        """Re-encode a merged structural technical_overview dict back into
        the saved {'bundle_b64': ...} shape. Returns None when there's no
        document — mirrors _bundle_technical_overview's own contract
        exactly, so downstream save/load code needs no changes."""
        if not structural or not structural.get('document_bytes'):
            return None
        from core.ecto_format import EctoFormat
        fd, tmp_doc = tempfile.mkstemp(suffix=structural.get('document_ext') or '')
        os.write(fd, structural['document_bytes'])
        os.close(fd)
        fd2, tmp_ecto = tempfile.mkstemp(suffix='.ecto')
        os.close(fd2)
        try:
            success, msg = EctoFormat.export_technical(
                document_path=tmp_doc,
                annotations=structural.get('annotations', []),
                metadata=structural.get('metadata', {}),
                output_path=tmp_ecto,
            )
            if not success:
                logger.warning(f'_encode_technical_overview: export failed: {msg}')
                return None
            return {'bundle_b64': base64.b64encode(Path(tmp_ecto).read_bytes()).decode()}
        finally:
            for p in (tmp_doc, tmp_ecto):
                try:
                    os.remove(p)
                except OSError:
                    pass

    def _decode_viewer_tabs(self, entries: Optional[list]) -> Tuple[list, list]:
        """Decode a saved viewer_tabs list into comparison-friendly
        structural entries for _merge_viewer_tabs. Returns (structural_list,
        temp_dirs) — each entry's temp_dir (holding its extracted model/
        images) must stay alive until after the save finishes, since the
        decoded dict's annotation image_paths/texture paths point into it."""
        structural = []
        temp_dirs = []
        for entry in entries or []:
            item, temp_dir = self._decode_viewer_tab(entry)
            if item is not None:
                structural.append(item)
            if temp_dir:
                temp_dirs.append(temp_dir)
        return structural, temp_dirs

    def _decode_viewer_tab(self, entry: Optional[dict]) -> Tuple[Optional[dict], Optional[str]]:
        """Decode one saved viewer_tabs entry ({'id', 'tab_name',
        'bundle_b64'}) into a structural dict for merge comparison. 'id'
        and 'bundle_b64' are kept verbatim — bundle_b64 is reused wholesale
        by whichever side wins a conflict, never re-encoded or itself
        compared (see core/project_merge.py's _merge_viewer_tabs); every
        other field is decoded from the bundle so comparison judges real
        content instead of the zip's own non-deterministic bytes. A
        pre-this-change entry with no 'id' gets a fresh one — it can't
        recover a "true" cross-device identity it never had, so it's
        merged once as if it were a brand-new tab (no data lost, worst
        case a harmless one-time duplicate, same fallback used for other
        legacy id-less lists elsewhere in this file). Returns (None, None)
        for an entry that can't be decoded at all."""
        if not entry or not entry.get('bundle_b64'):
            return None, None
        from core.ecto_format import EctoFormat
        fd, tmp_ecto = tempfile.mkstemp(suffix='.lyns')
        os.close(fd)
        try:
            Path(tmp_ecto).write_bytes(base64.b64decode(entry['bundle_b64']))
            model_path, annotations, _reader_mode, temp_dir_or_err, drawings, texture_data = \
                EctoFormat.import_ecto(tmp_ecto)
            if model_path is None:
                logger.warning(f'_decode_viewer_tab: could not decode '
                                f'"{entry.get("tab_name")}": {temp_dir_or_err}')
                return None, None
            return {
                'id': entry.get('id') or uuid.uuid4().hex,
                'bundle_b64': entry['bundle_b64'],
                'tab_name': entry.get('tab_name', ''),
                'model_bytes': Path(model_path).read_bytes(),
                'model_ext': os.path.splitext(model_path)[1],
                'annotations': annotations or [],
                'drawings': drawings or [],
                'texture_data': texture_data,
            }, temp_dir_or_err
        except Exception as e:
            logger.warning(f'_decode_viewer_tab: could not decode "{entry.get("tab_name")}": {e}')
            return None, None
        finally:
            try:
                os.remove(tmp_ecto)
            except OSError:
                pass

    def _apply_merged_data_to_screens(self, merged: dict) -> None:
        self._nav.set_info_data(merged.get('project_info', {}))
        for key, _ in _NAV_ITEMS:
            w = self._screen_widgets.get(key)
            if w is not None and hasattr(w, 'set_data'):
                w.set_data(merged.get(key, {}))

    def _bundle_viewer_tabs(self) -> list:
        """For each viewer tab with a loaded mesh, create a .lyns bundle and return as base64 entries."""
        from core.ecto_format import EctoFormat
        result = []
        for tab in self._viewer_tabs:
            vw = getattr(tab, 'viewer_widget', None)
            mesh = getattr(vw, 'current_mesh', None) if vw is not None else None
            if mesh is None:
                continue
            annotations = []
            ap = getattr(tab, 'annotation_panel', None)
            if ap is not None and hasattr(ap, 'export_annotations'):
                try:
                    annotations = ap.export_annotations() or []
                except Exception:
                    annotations = []
            drawings = []
            if vw is not None and hasattr(vw, 'get_draw_strokes'):
                try:
                    drawings = vw.get_draw_strokes() or []
                except Exception:
                    pass
            texture_data = None
            if vw is not None and hasattr(vw, 'get_texture_data'):
                try:
                    texture_data = vw.get_texture_data()
                except Exception:
                    pass
            tab_name = tab.filename or 'model.stl'
            fd, tmp_path = tempfile.mkstemp(suffix='.lyns')
            os.close(fd)
            try:
                success, _, creator_token = EctoFormat.export(
                    mesh=mesh,
                    annotations=annotations,
                    output_path=tmp_path,
                    source_format='stl',
                    original_filename=tab_name,
                    drawings=drawings,
                    texture_data=texture_data,
                    reader_mode=False,
                )
                if success:
                    # This bundle is just this session's own storage format for
                    # restoring the tab on reload, not a file shared with anyone
                    # else — register the token so import_ecto's sender/reader
                    # check recognizes it as ours and reopens it editable instead
                    # of read-only. Without this, every restored tab silently
                    # landed in "Reader Mode - View Only".
                    if creator_token:
                        try:
                            from core.creator_registry import register_creator_token
                            register_creator_token(creator_token)
                        except ImportError:
                            pass
                    bundle_bytes = Path(tmp_path).read_bytes()
                    # id — assigned once when the tab was created (see
                    # stl_viewer.py's _create_new_tab), never reassigned —
                    # is what lets the merge engine recognize "this is the
                    # same tab, edited" across two devices instead of only
                    # ever being able to compare the whole viewer_tabs list
                    # as one opaque blob. Fall back to a fresh id for the
                    # rare case a tab somehow has none (shouldn't happen on
                    # a live session, but never write an id-less entry).
                    tab_id = getattr(tab, 'tab_id', None) or uuid.uuid4().hex
                    result.append({
                        'id': tab_id,
                        'tab_name': tab_name,
                        'bundle_b64': base64.b64encode(bundle_bytes).decode(),
                    })
                else:
                    logger.warning(f'_bundle_viewer_tabs: export failed for tab "{tab_name}"')
            except Exception as e:
                logger.warning(f'_bundle_viewer_tabs: could not bundle tab "{tab_name}": {e}')
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        return result

    def _bundle_technical_overview(self) -> Optional[dict]:
        """Bundle the Technical Overview workspace (document + annotations +
        metadata) as a base64 .ecto entry, mirroring _bundle_viewer_tabs.
        Returns None if there's no document loaded (nothing to save)."""
        to = self._technical_overview
        ts = self._technical_sidebar
        if to is None or ts is None or not hasattr(to, 'get_document_path'):
            return None
        doc_path = to.get_document_path()
        if not doc_path:
            return None
        from core.ecto_format import EctoFormat
        annotations = []
        if hasattr(to, 'get_annotations_data'):
            try:
                annotations = to.get_annotations_data() or []
            except Exception:
                annotations = []
        metadata = ts.get_metadata() if hasattr(ts, 'get_metadata') else {}
        fd, tmp_path = tempfile.mkstemp(suffix='.ecto')
        os.close(fd)
        try:
            success, msg = EctoFormat.export_technical(
                document_path=doc_path,
                annotations=annotations,
                metadata=metadata,
                output_path=tmp_path,
            )
            if not success:
                logger.warning(f'_bundle_technical_overview: export failed: {msg}')
                return None
            bundle_bytes = Path(tmp_path).read_bytes()
            return {'bundle_b64': base64.b64encode(bundle_bytes).decode()}
        except Exception as e:
            logger.warning(f'_bundle_technical_overview: could not bundle: {e}')
            return None
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    def _restore_technical_overview(self, entry: Optional[dict]) -> None:
        """Decode the base64 .ecto entry and emit restore_technical_overview
        for the main window to apply, mirroring _restore_viewer_tabs."""
        if not entry:
            return
        b64 = entry.get('bundle_b64', '')
        if not b64:
            return
        fd, tmp_path = tempfile.mkstemp(suffix='.ecto')
        os.close(fd)
        try:
            Path(tmp_path).write_bytes(base64.b64decode(b64))
            self.restore_technical_overview.emit(tmp_path)
        except Exception as e:
            logger.warning(f'_restore_technical_overview: could not restore: {e}')
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    def _bundle_drawing_scale(self) -> Optional[dict]:
        """Bundle the Drawing Scale workspace (source drawing file + calibration/
        border/reference-line/shape state) for project save. Returns None if
        there's no drawing loaded (nothing to save)."""
        sc = self._scale_canvas
        if sc is None or not hasattr(sc, 'get_source_path'):
            return None
        src_path = sc.get_source_path()
        if not src_path or not os.path.exists(src_path):
            return None
        try:
            file_bytes = Path(src_path).read_bytes()
        except OSError as e:
            logger.warning(f'_bundle_drawing_scale: could not read source file: {e}')
            return None
        return {
            'file_name': os.path.basename(src_path),
            'file_ext': Path(src_path).suffix.lower(),
            'file_b64': base64.b64encode(file_bytes).decode(),
            'state': sc.get_state(),
        }

    def _restore_drawing_scale(self, entry: Optional[dict]) -> None:
        """Decode the bundled source file and emit restore_drawing_scale for
        the main window to apply, mirroring _restore_technical_overview.

        Unlike _restore_viewer_tabs/_restore_technical_overview (which extract
        into their own throwaway/self-managed temp storage), ScaleCanvas keeps
        pointing at this exact tmp_path as its "source file" after loading it
        (get_source_path() returns it), and a later save re-reads that path —
        so the temp file must be left in place rather than deleted here. The
        main window takes ownership of it and cleans it up on app close, same
        as the Technical Overview's _tech_ecto_temp_dir.
        """
        if not entry:
            return
        b64 = entry.get('file_b64', '')
        if not b64:
            return
        ext = entry.get('file_ext') or '.png'
        fd, tmp_path = tempfile.mkstemp(suffix=ext)
        os.close(fd)
        try:
            Path(tmp_path).write_bytes(base64.b64decode(b64))
            self.restore_drawing_scale.emit(tmp_path, entry.get('state', {}))
        except Exception as e:
            logger.warning(f'_restore_drawing_scale: could not restore: {e}')
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    def _restore_viewer_tabs(self, viewer_tabs: list) -> None:
        """Decode base64 .lyns bundles and emit restore_viewer_tab for each."""
        for entry in viewer_tabs:
            b64 = entry.get('bundle_b64', '')
            if not b64:
                continue
            tab_name = entry.get('tab_name', 'model.lyns')
            tab_id = entry.get('id') or ''  # '' for saves from before tabs had stable ids
            fd, tmp_path = tempfile.mkstemp(suffix='.lyns')
            os.close(fd)
            try:
                Path(tmp_path).write_bytes(base64.b64decode(b64))
                self.restore_viewer_tab.emit(tmp_path, tab_name, tab_id)
            except Exception as e:
                logger.warning(f'_restore_viewer_tabs: could not restore "{tab_name}": {e}')
            finally:
                # Safe to delete — restore_viewer_tab is a direct connection and
                # _load_ecto_file extracts the bundle to its own temp dir synchronously.
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    def _load_project(self, path: str):
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Password-protected project — verify before loading
        stored_hash = data.get('password_hash')
        if stored_hash:
            from ui.passcode_dialog import PasscodeDialog
            dlg = PasscodeDialog(mode='enter', stored_hash=stored_hash, parent=self)
            dlg.setWindowTitle(t('project.msg.pwd_enter_title'))
            if dlg.exec_() != QDialog.Accepted:
                return  # user cancelled — do not load

        # File lock — is someone else already editing this project?
        from core.file_lock import check_lock_status, read_lock, acquire_lock, HELD_ACTIVE, HELD_STALE
        lock_status = check_lock_status(path)
        opening_read_only = False
        if lock_status == HELD_STALE:
            if not self._confirm_lock_override(read_lock(path)):
                return
            acquire_lock(path, force=True)
        elif lock_status == HELD_ACTIVE:
            if not self._confirm_read_only_open(read_lock(path)):
                return
            opening_read_only = True
        else:
            acquire_lock(path)

        # Committed to opening `path` now — release whatever this session
        # previously had open (if it's a different project).
        if self._project_path and self._project_path != path:
            self.release_lock()

        self._nav.set_info_data(data.get('project_info', {}))
        for key, _ in _NAV_ITEMS:
            screen_data = data.get(key)
            if screen_data is None:
                continue
            w = self._ensure_screen(key)
            if hasattr(w, 'set_data'):
                w.set_data(screen_data)

        # Whatever's currently open in the 3D viewer belongs to the session
        # being replaced, not to the project being opened — close it first so
        # the restored tabs replace it instead of piling up alongside it.
        self.clear_viewer_tabs.emit()

        # Restore viewer tabs — decode each .lyns bundle to a temp file and open in viewer
        self._restore_viewer_tabs(data.get('viewer_tabs', []))

        # Restore the Technical Overview workspace, if the save included one
        self._restore_technical_overview(data.get('technical_overview'))

        # Restore the Drawing Scale workspace, if the save included one
        self._restore_drawing_scale(data.get('drawing_scale'))

        self._project_path = path
        self._project_password_hash = stored_hash
        self._created_by = data.get('created_by')
        self._created_at = data.get('created_at')
        self._read_only = opening_read_only
        self._loaded_snapshot = data  # merge base for the next save
        self._unsaved_changes = False
        self._update_lock_btn()
        self._update_title()
        self._update_read_only_ui()
        logger.info(f'Project loaded from {path} (read_only={opening_read_only})')

    def _update_lock_btn(self):
        """Update the password button appearance to reflect the current lock state."""
        if self._project_password_hash:
            self._lock_btn.setText(t('project.topbar.protected'))
            self._lock_btn.setStyleSheet(_BTN_LOCK_ACTIVE)
            self._lock_btn.setToolTip(t('project.topbar.tip_protected'))
        else:
            self._lock_btn.setText(t('project.topbar.password'))
            self._lock_btn.setStyleSheet(_BTN_TOOLBAR)
            self._lock_btn.setToolTip(t('project.topbar.tip_unlocked'))

    def _on_password_btn(self):
        """Set, change, or remove the project password."""
        if self._read_only:
            self._warn_read_only()
            return
        from ui.passcode_dialog import PasscodeDialog

        if self._project_password_hash is None:
            # No password yet — set one
            dlg = PasscodeDialog(mode='set', parent=self)
            if dlg.exec_() == QDialog.Accepted:
                self._project_password_hash = dlg.get_passcode_hash()
                self._update_lock_btn()
                self.mark_unsaved()
        else:
            # Already protected — verify first
            dlg = PasscodeDialog(mode='enter',
                                  stored_hash=self._project_password_hash,
                                  parent=self)
            if dlg.exec_() != QDialog.Accepted:
                return

            # Offer Remove / Change / Cancel
            msg = QMessageBox(self)
            msg.setWindowTitle(t('project.msg.pwd_title'))
            msg.setText(t('project.msg.pwd_body'))
            remove_btn = msg.addButton(t('project.msg.pwd_remove'), QMessageBox.DestructiveRole)
            change_btn = msg.addButton(t('project.msg.pwd_change'), QMessageBox.AcceptRole)
            msg.addButton(t('common.cancel'), QMessageBox.RejectRole)
            msg.exec_()
            clicked = msg.clickedButton()

            if clicked == remove_btn:
                self._project_password_hash = None
                self._update_lock_btn()
                self.mark_unsaved()
            elif clicked == change_btn:
                dlg2 = PasscodeDialog(mode='set', parent=self)
                if dlg2.exec_() == QDialog.Accepted:
                    self._project_password_hash = dlg2.get_passcode_hash()
                    self._update_lock_btn()
                    self.mark_unsaved()

    def _confirm_discard(self) -> bool:
        # Uses the app's own light-themed modal (white background, dark text)
        # with translated button labels, instead of QMessageBox.question —
        # Qt's native standard-button labels ("Discard"/"Cancel") don't pick
        # up the app's French translation since no Qt translation file is
        # loaded for them.
        from ui.modal_utils import MessageModal, BaseModal
        dlg = MessageModal(
            self, t('project.msg.unsaved_title'), t('project.msg.unsaved_body'),
            theme=BaseModal.LIGHT,
            primary_text=t('project.msg.unsaved_discard'),
            secondary_text=t('common.cancel'),
        )
        result = {'discard': False}
        dlg.primary_btn.clicked.connect(lambda: (result.update(discard=True), dlg.accept()))
        if dlg.secondary_btn:
            dlg.secondary_btn.clicked.connect(lambda: (result.update(discard=False), dlg.reject()))
        dlg.exec_()
        return result['discard']

    @staticmethod
    def _format_lock_time(iso_ts: str) -> str:
        try:
            dt = datetime.fromisoformat(iso_ts)
        except (TypeError, ValueError):
            return iso_ts or ''
        return dt.astimezone().strftime('%Y-%m-%d %H:%M')

    def _confirm_lock_override(self, lock_data: Optional[dict]) -> bool:
        """Lock looks abandoned (stale heartbeat) — Override or Cancel.
        Distinct copy/color from _confirm_read_only_open so the two can't be
        confused: this one offers an override, the active-lock one doesn't."""
        from ui.modal_utils import MessageModal, BaseModal
        user = (lock_data or {}).get('user', '?')
        when = self._format_lock_time((lock_data or {}).get('last_active_at', ''))
        dlg = MessageModal(
            self, t('project.msg.lock_stale_title'),
            t('project.msg.lock_stale_body').format(user=user, time=when),
            theme=BaseModal.LIGHT,
            primary_text=t('project.msg.lock_override'),
            secondary_text=t('common.cancel'),
        )
        result = {'override': False}
        dlg.primary_btn.clicked.connect(lambda: (result.update(override=True), dlg.accept()))
        if dlg.secondary_btn:
            dlg.secondary_btn.clicked.connect(lambda: (result.update(override=False), dlg.reject()))
        dlg.exec_()
        return result['override']

    def _confirm_read_only_open(self, lock_data: Optional[dict]) -> bool:
        """Lock is actively held by someone else — Open Read-Only or Cancel.
        No override offered here (unlike the stale case) — that's the whole
        point of the lock while someone is genuinely still editing."""
        from ui.modal_utils import MessageModal, BaseModal
        user = (lock_data or {}).get('user', '?')
        when = self._format_lock_time((lock_data or {}).get('acquired_at', ''))
        dlg = MessageModal(
            self, t('project.msg.lock_active_title'),
            t('project.msg.lock_active_body').format(user=user, time=when),
            theme=BaseModal.LIGHT,
            primary_text=t('project.msg.lock_read_only'),
            secondary_text=t('common.cancel'),
        )
        result = {'read_only': False}
        dlg.primary_btn.clicked.connect(lambda: (result.update(read_only=True), dlg.accept()))
        if dlg.secondary_btn:
            dlg.secondary_btn.clicked.connect(lambda: (result.update(read_only=False), dlg.reject()))
        dlg.exec_()
        return result['read_only']

    def _update_read_only_ui(self):
        """Grey out/disable the write affordances that a read-only-opened
        project must not allow: saving and changing project protection."""
        read_only = self._read_only
        if hasattr(self, '_save_btn'):
            self._save_btn.setEnabled(not read_only)
        if hasattr(self, '_lock_btn'):
            self._lock_btn.setEnabled(not read_only)

    def _warn_read_only(self):
        from ui.modal_utils import show_message_dialog
        show_message_dialog(self, t('project.msg.read_only_title'), t('project.msg.read_only_body'))

    def _update_title(self):
        if self._project_path:
            p = Path(self._project_path)
            name = p.name
            for ext in ('.lyns.pjt', '.lyns.review', '.ectopjt'):
                if name.endswith(ext):
                    name = name[: -len(ext)]
                    break
            else:
                name = p.stem
            self._project_name_lbl.setText(f'📄  {name}')
            self._project_name_lbl.setStyleSheet(
                f'color: {_TEXT}; font-size: 14px; background: transparent; border: none;'
            )
        else:
            self._project_name_lbl.setText(t('project.topbar.no_project'))
            self._project_name_lbl.setStyleSheet(
                f'color: {_MUTED}; font-size: 14px; background: transparent; border: none;'
            )

    # ── autosave ──────────────────────────────────────────────────────────────

    def _setup_autosave(self):
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(30_000)
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_timer.start()

    def _autosave(self):
        if self._project_path and self._unsaved_changes:
            try:
                self._save_project(self._project_path)
                logger.debug('Autosaved project')
            except Exception as e:
                logger.warning(f'Autosave failed: {e}')

    def mark_unsaved(self):
        self._unsaved_changes = True

    # ── file lock ─────────────────────────────────────────────────────────────

    def _setup_lock_heartbeat(self):
        """Refresh this session's lock every few minutes while a project is
        open, independent of Save — an active-but-not-saving session (e.g.
        just reading/annotating) must not look abandoned to a colleague."""
        self._lock_heartbeat_timer = QTimer(self)
        self._lock_heartbeat_timer.setInterval(3 * 60_000)
        self._lock_heartbeat_timer.timeout.connect(self._lock_heartbeat)
        self._lock_heartbeat_timer.start()

    def _lock_heartbeat(self):
        if self._project_path and not self._read_only:
            from core.file_lock import refresh_lock
            refresh_lock(self._project_path)

    def release_lock(self):
        """Release this session's lock on whatever project is currently
        open, if any. Safe to call even if nothing is open or the project
        was opened read-only (no-ops in both cases)."""
        if self._project_path and not self._read_only:
            from core.file_lock import release_lock as _release_lock
            _release_lock(self._project_path)

    def _acquire_lock_for_current_path(self):
        """Acquire this session's lock at self._project_path. Needed by Save
        and Save As, which — unlike _load_project's Open flow — never went
        through a lock acquisition step for the path they're about to write
        to (a brand-new project's first save, or Save As to a different
        location, both land here without ever calling acquire_lock). Without
        this, no .lock sidecar ever appeared next to a project saved that
        way, and the heartbeat/release_lock (both keyed off
        self._project_path) would silently drift onto a path nothing had
        actually locked. Not forced — if the target path happens to be
        actively locked by someone else already, this just no-ops and the
        save proceeds without lock protection, same as the prior behavior."""
        if not self._project_path:
            return
        from core.file_lock import acquire_lock
        acquire_lock(self._project_path)

    def closeEvent(self, event):
        super().closeEvent(event)

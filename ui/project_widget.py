"""
The Project — main container widget.
Left panel: project info + navigation.
Right panel: top bar (open/save + user account) + stacked content screens.

Screens are loaded lazily — only instantiated on first navigation.
"""
import base64
import getpass
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Type

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QStackedWidget, QFileDialog, QMessageBox,
    QLineEdit, QComboBox, QDialog, QScrollArea, QSizePolicy, QSplitter,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPixmap, QIcon, QFontMetrics
from ui.styles import default_theme, make_font, dropdown_arrow_url as _get_arrow, TOOLTIP_STYLE
from ui.modal_utils import FormModal
from i18n import t, on_language_changed

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
    'brief', 'assignment', 'timeline', 'validation', 'report', 'estimated_cost',
    'files', 'rd', 'prototype', 'traceability', 'quality_control', 'version_comparison', 'todo', 'glossary',
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
        self._photo_path: str = ''
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

        for key, _label in _NAV_ITEMS:
            label = t(f'project.nav.{key}').replace('&', '&&')
            btn = _NavButton(label, h_padding=14)
            btn.setStyleSheet(_NAV_INACTIVE)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(40)
            btn.setCheckable(True)
            # Ignored: a translated label (e.g. French "ESTIMATION DES COÛTS")
            # must never widen this button's sizeHint enough to pull the
            # sidebar itself wider — text just elides instead, full label
            # still available via tooltip.
            btn.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            btn.setToolTip(label)
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
                    sb.setToolTip(sub_label)
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
            pix = QPixmap(path)
            if not pix.isNull():
                self._photo_path = path
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
            'photo_path':       self._photo_path,
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
        photo = data.get('photo_path', '')
        if photo:
            pix = QPixmap(photo)
            if not pix.isNull():
                self._photo_path = photo
                scaled = pix.scaled(
                    self._photo_btn.width(), self._photo_btn.height(),
                    Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
                )
                self._photo_btn.setIcon(QIcon(scaled))
                self._photo_btn.setIconSize(self._photo_btn.size())
                self._photo_btn.setText('')

    def retranslate(self):
        """Update all visible labels/buttons when language changes."""
        if not self._photo_path:
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
            btn.setToolTip(label)
        _rd_tab_keys = ['rd.tab_textures', 'rd.tab_techniques']
        for i, sb in enumerate(self._rd_sub_btns):
            sub_label = t(_rd_tab_keys[i])
            sb.setText(sub_label)
            sb.setToolTip(sub_label)
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

    open_in_viewer = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_path: Optional[str] = None
        self._unsaved_changes = False
        self._current_screen_key: Optional[str] = None
        self._project_password_hash: Optional[str] = None  # SHA-256 hash; None = no protection
        self._created_by: Optional[str] = None  # OS username who first created the file
        self._created_at: Optional[str] = None  # ISO timestamp of first save
        self._component_syncing = False  # guard against brief↔traceability sync loops
        self._viewer_tabs: list = []  # TabState list injected from main window before save
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
        if key == 'traceability' and hasattr(widget, 'update_project_info'):
            # The sidebar's main photo only reaches an already-open screen via
            # _on_project_info_changed — a freshly (lazily) created Traceability
            # screen never got that first push, so its photo + main product
            # thumbnail stayed blank until some unrelated info field changed.
            # Seed it once with the current info right at construction time.
            widget.update_project_info(self._nav.get_info_data())
        if key == 'rd' and hasattr(widget, 'tab_changed'):
            widget.tab_changed.connect(self._on_rd_tab_changed)
            # Set the callback so sidebar sub-items call switch_tab on the widget
            self._nav.set_rd_tab_switch_callback(widget.switch_tab)
        if key == 'quality_control' and hasattr(widget, 'set_viewers') and self._pending_viewers:
            # Replay the cached viewer list so the QC screen is fully wired
            # even when the user first opens it after models are already loaded.
            widget.set_viewers(self._pending_viewers, active_viewer=self._pending_active_viewer)

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

    # ── top bar ───────────────────────────────────────────────────────────────

    # ── project file operations ───────────────────────────────────────────────

    def _on_new_project(self):
        if self._unsaved_changes and not self._confirm_discard():
            return
        self._release_lock()
        self._project_path = None
        self._unsaved_changes = False
        self._project_password_hash = None
        self._created_by = None
        self._created_at = None
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
        if not self._project_path:
            path, _ = QFileDialog.getSaveFileName(
                self, 'Save Project', 'project.lyns.pjt',
                'LYNS Project (*.lyns.pjt);;All Files (*)'
            )
            if not path:
                return
            # Strip any project-file extension the user may have typed before enforcing .lyns.pjt
            for _sfx in ('.lyns.pjt', '.ectopjt', '.pjt'):
                if path.lower().endswith(_sfx):
                    path = path[:-len(_sfx)]
                    break
            path += '.lyns.pjt'
            self._project_path = path
        try:
            self._save_project(self._project_path)
        except Exception as e:
            logger.error(f'Failed to save project: {e}', exc_info=True)
            QMessageBox.critical(self, t('project.msg.save_failed'), t('project.msg.save_error').format(e=e))
        else:
            from ui.modal_utils import show_message_dialog
            show_message_dialog(self, t('project.msg.save_success_title'), t('project.msg.save_success_body'))

    def _on_save_project_as(self):
        """Always prompt for a new file path and save there, regardless of
        whether the project already has one (unlike _on_save_project, which
        reuses the existing path once set)."""
        default_name = os.path.basename(self._project_path) if self._project_path else 'project.lyns.pjt'
        path, _ = QFileDialog.getSaveFileName(
            self, t('project.topbar.save_as'), default_name,
            'LYNS Project (*.lyns.pjt);;All Files (*)'
        )
        if not path:
            return
        for _sfx in ('.lyns.pjt', '.ectopjt', '.pjt'):
            if path.lower().endswith(_sfx):
                path = path[:-len(_sfx)]
                break
        path += '.lyns.pjt'
        self._project_path = path
        try:
            self._save_project(self._project_path)
        except Exception as e:
            logger.error(f'Failed to save project as: {e}', exc_info=True)
            QMessageBox.critical(self, t('project.msg.save_failed'), t('project.msg.save_error').format(e=e))
        else:
            from ui.modal_utils import show_message_dialog
            show_message_dialog(self, t('project.msg.save_success_title'), t('project.msg.save_success_body'))

    def _save_project(self, path: str):
        now = datetime.now(timezone.utc).isoformat()
        user = getpass.getuser()
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
            data[key] = w.get_data() if w and hasattr(w, 'get_data') else {}

        # Bundle each viewer tab (model + annotations + drawings + texture) as base64
        data['viewer_tabs'] = self._bundle_viewer_tabs()

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self._unsaved_changes = False
        self._update_title()
        logger.info(f'Project saved to {path} by {user}')

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
                success, _, _ = EctoFormat.export(
                    mesh=mesh,
                    annotations=annotations,
                    output_path=tmp_path,
                    source_format='stl',
                    original_filename=tab_name,
                    drawings=drawings,
                    texture_data=texture_data,
                )
                if success:
                    bundle_bytes = Path(tmp_path).read_bytes()
                    result.append({
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

    def _restore_viewer_tabs(self, viewer_tabs: list) -> None:
        """Decode base64 .lyns bundles and emit open_in_viewer for each."""
        for entry in viewer_tabs:
            b64 = entry.get('bundle_b64', '')
            if not b64:
                continue
            tab_name = entry.get('tab_name', 'model.lyns')
            fd, tmp_path = tempfile.mkstemp(suffix='.lyns')
            os.close(fd)
            try:
                Path(tmp_path).write_bytes(base64.b64decode(b64))
                self.open_in_viewer.emit(tmp_path)
            except Exception as e:
                logger.warning(f'_restore_viewer_tabs: could not restore "{tab_name}": {e}')
            finally:
                # Safe to delete — open_in_viewer is a direct connection and
                # _load_ecto_file extracts the bundle to its own temp dir synchronously.
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    def _load_project(self, path: str):
        # Check for an existing lock file (another user/instance has this open)
        lock_path = path + '.lock'
        if os.path.exists(lock_path):
            try:
                lock_info = json.loads(Path(lock_path).read_text(encoding='utf-8'))
                locked_by = lock_info.get('locked_by', 'another user')
                locked_at = lock_info.get('locked_at', '')
            except Exception:
                locked_by = 'another user'
                locked_at = ''
            msg = f'This project is currently open by "{locked_by}"'
            if locked_at:
                msg += f' (since {locked_at[:16].replace("T", " ")} UTC)'
            msg += '.\n\nOpening it may cause conflicts. Continue anyway?'
            reply = QMessageBox.warning(
                self, 'File In Use', msg,
                QMessageBox.Open | QMessageBox.Cancel, QMessageBox.Cancel
            )
            if reply != QMessageBox.Open:
                return

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

        # Release lock on previously open file
        self._release_lock()

        self._nav.set_info_data(data.get('project_info', {}))
        for key, _ in _NAV_ITEMS:
            screen_data = data.get(key)
            if screen_data is None:
                continue
            w = self._ensure_screen(key)
            if hasattr(w, 'set_data'):
                w.set_data(screen_data)

        # Restore viewer tabs — decode each .lyns bundle to a temp file and open in viewer
        self._restore_viewer_tabs(data.get('viewer_tabs', []))

        self._project_path = path
        self._project_password_hash = stored_hash
        self._created_by = data.get('created_by')
        self._created_at = data.get('created_at')
        self._unsaved_changes = False
        self._update_lock_btn()
        self._update_title()
        self._acquire_lock(path)
        logger.info(f'Project loaded from {path}')

    def _acquire_lock(self, path: str):
        lock_path = path + '.lock'
        try:
            lock_data = {
                'locked_by': getpass.getuser(),
                'locked_at': datetime.now(timezone.utc).isoformat(),
            }
            Path(lock_path).write_text(
                json.dumps(lock_data, indent=2), encoding='utf-8'
            )
        except Exception as e:
            logger.warning(f'Could not write lock file: {e}')

    def _release_lock(self):
        if not self._project_path:
            return
        lock_path = self._project_path + '.lock'
        try:
            if os.path.exists(lock_path):
                os.remove(lock_path)
        except Exception as e:
            logger.warning(f'Could not remove lock file: {e}')

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

    def closeEvent(self, event):
        self._release_lock()
        super().closeEvent(event)

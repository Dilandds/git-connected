"""
The Project — main container widget.
Left panel: project info + navigation.
Right panel: top bar (open/save + user account) + stacked content screens.

Screens are loaded lazily — only instantiated on first navigation.
"""
import json
import logging
import os
from pathlib import Path
from typing import Optional, Type

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QStackedWidget, QFileDialog, QMessageBox,
    QLineEdit, QComboBox, QDialog,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPixmap, QIcon
from ui.styles import default_theme, make_font, dropdown_arrow_url as _get_arrow, TOOLTIP_STYLE
from ui.modal_utils import FormModal

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
_NAV_ITEMS = [
    ('brief',              '📄  Project Brief'),
    ('timeline',           '⏱  Timeline'),
    ('validation',         '✔  Validation'),
    ('report',             '📋  Report'),
    ('estimated_cost',     '💰  Estimated Cost'),
    ('files',              '📁  Files & Versions'),
    ('version_comparison', '⭐  Version Comparison'),
    ('traceability',       '🔍  Traceability'),
    ('glossary',           'A-Z  Glossary'),
]

# ── shared styles ─────────────────────────────────────────────────────────────
_NAV_ACTIVE = f"""
    QPushButton {{
        background-color: {_ACCENT};
        color: white; border: none; border-radius: 6px;
        padding: 8px 12px; font-size: 13px; font-weight: bold; text-align: left;
    }}
"""

_NAV_INACTIVE = f"""
    QPushButton {{
        background-color: transparent; color: {_MUTED}; border: none;
        border-radius: 6px; padding: 8px 12px; font-size: 13px; text-align: left;
    }}
    QPushButton:hover {{ background-color: #2a2e38; color: {_TEXT}; }}
"""

_BTN_TOOLBAR = f"""
    QPushButton {{
        background-color: #2e323a; color: {_TEXT};
        border: 1px solid {default_theme.border_light};
        border-radius: 6px; font-size: 13px; padding: 4px 12px;
    }}
    QPushButton:hover {{ background-color: #3a3e48; border-color: {_ACCENT}; color: white; }}
    QPushButton:pressed {{ background-color: {default_theme.button_primary_pressed}; color: white; }}
    QPushButton:disabled {{ color: {_MUTED}; border-color: {_BORDER}; background-color: #252830; }}
""" + TOOLTIP_STYLE

_BTN_SAVE = f"""
    QPushButton {{
        background-color: {_ACCENT}; color: white; border: none;
        border-radius: 6px; font-size: 13px; font-weight: bold; padding: 4px 14px;
    }}
    QPushButton:hover {{ background-color: {_ACCENT_H}; }}
    QPushButton:pressed {{ background-color: {default_theme.button_primary_pressed}; }}
    QPushButton:disabled {{ background-color: #253545; color: #4a6070; }}
""" + TOOLTIP_STYLE

_BTN_LOCK_ACTIVE = f"""
    QPushButton {{
        background-color: #92400e; color: #fde68a; border: 1px solid #b45309;
        border-radius: 6px; font-size: 13px; font-weight: bold; padding: 4px 12px;
    }}
    QPushButton:hover {{ background-color: #78350f; border-color: #d97706; }}
    QPushButton:pressed {{ background-color: #451a03; }}
""" + TOOLTIP_STYLE

_INFO_INPUT_STYLE = f"""
    QLineEdit {{
        background-color: #1e2228; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 4px;
        padding: 3px 6px; font-size: 12px;
    }}
    QLineEdit:focus {{ border: 1px solid {_ACCENT}; }}
"""

_STATUS_COLORS = {
    'In progress': '#4ade80',
    'Awaiting':    '#facc15',
    'Completed':   '#22d3ee',
    'Cancelled':   '#f87171',
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
            padding: 3px 6px; font-size: 12px; font-weight: bold;
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
    if key == 'timeline':
        from ui.timeline import TimelineWidget
        return TimelineWidget
    if key == 'validation':
        from ui.project_validation import ValidationWidget
        return ValidationWidget
    if key == 'report':
        from ui.report import ReportWidget
        return ReportWidget
    if key == 'estimated_cost':
        from ui.estimated_cost import EstimatedCostWidget
        return EstimatedCostWidget
    if key == 'files':
        from ui.files_widget import FilesVersionsWidget
        return FilesVersionsWidget
    if key == 'version_comparison':
        from ui.version_comparison import VersionComparisonWidget
        return VersionComparisonWidget
    if key == 'traceability':
        from ui.traceability import TraceabilityWidget
        return TraceabilityWidget
    if key == 'glossary':
        from ui.glossary_widget import GlossaryWidget
        return GlossaryWidget
    raise KeyError(f'Unknown screen key: {key}')


# ── ProjectNavPanel ───────────────────────────────────────────────────────────

class ProjectNavPanel(QWidget):
    """Left sidebar: project info card + navigation buttons."""

    info_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(210)
        self.setStyleSheet(f'background-color: {_SIDEBAR};')
        self._buttons: dict[str, QPushButton] = {}
        self._on_navigate = None
        self._photo_path: str = ''
        self._build_ui()

    # ── construction ──────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 14, 10, 14)
        layout.setSpacing(2)
        layout.addWidget(self._build_info_card())

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(
            f'color: {_BORDER}; background-color: {_BORDER}; max-height: 1px; border: none; margin: 8px 0;'
        )
        layout.addWidget(sep)

        self._build_nav_buttons(layout)
        layout.addStretch()

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

        self._photo_btn = QPushButton('+Add photo')
        self._photo_btn.setFixedHeight(150)
        self._photo_btn.setCursor(Qt.PointingHandCursor)
        self._photo_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #1e2228;
                border: 1px dashed {_BORDER};
                border-radius: 6px;
                color: {_MUTED}; font-size: 11px;
            }}
            QPushButton:hover {{ border-color: {_ACCENT}; color: {_ACCENT}; }}
        """)
        self._photo_btn.clicked.connect(self._upload_photo)
        card_layout.addWidget(self._photo_btn)

        self._f_company          = self._make_field('Company name')
        self._f_title            = self._make_field('Project title')
        self._f_number           = self._make_field('Project number')
        self._f_project_manager  = self._make_field('Project Manager')
        self._f_start_date       = self._make_field('Start date (dd/mm/yyyy)')
        self._f_due_date         = self._make_field('Due date (dd/mm/yyyy)')
        for f in (self._f_company, self._f_title, self._f_number,
                  self._f_project_manager, self._f_start_date, self._f_due_date):
            card_layout.addWidget(f)

        self._status_combo = QComboBox()
        self._status_combo.addItems(list(_STATUS_COLORS.keys()))
        self._status_combo.setFixedHeight(26)
        self._status_combo.setStyleSheet(_status_combo_style(_STATUS_COLORS['In progress']))
        self._status_combo.currentTextChanged.connect(self._on_status_changed)
        self._status_combo.currentTextChanged.connect(lambda _: self.info_changed.emit())
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
        for key, label in _NAV_ITEMS:
            btn = QPushButton(label)
            btn.setStyleSheet(_NAV_INACTIVE)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(34)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, k=key: self._navigate(k))
            self._buttons[key] = btn
            layout.addWidget(btn)

    # ── event handlers ────────────────────────────────────────────────────────

    def _on_status_changed(self, text: str):
        color = _STATUS_COLORS.get(text, _TEXT)
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
        if self._on_navigate:
            self._on_navigate(key)

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
            'status':           self._status_combo.currentText(),
            'photo_path':       self._photo_path,
        }

    def set_info_data(self, data: dict):
        self._f_company.setText(data.get('company', ''))
        self._f_title.setText(data.get('title', ''))
        self._f_number.setText(data.get('number', ''))
        self._f_project_manager.setText(data.get('project_manager', ''))
        self._f_start_date.setText(data.get('start_date', ''))
        self._f_due_date.setText(data.get('due_date', ''))
        status = data.get('status', 'In progress')
        idx = self._status_combo.findText(status)
        if idx >= 0:
            self._status_combo.setCurrentIndex(idx)
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


# ── Login dialog ──────────────────────────────────────────────────────────────

class ProjectLoginDialog(FormModal):
    """Login gate for The Project workspace."""

    def __init__(self, parent=None):
        super().__init__(parent, 'The Project — Login', min_width=380)

        # Header text (above the standard field area)
        sub = QLabel('Sign in to access your project workspace.')
        sub.setStyleSheet(f'color: {_MUTED}; font-size: 13px; background: transparent; border: none;')
        self._root.addWidget(sub)
        self._root.addWidget(self._make_hline())

        self._f_user = self.add_field('USERNAME', QLineEdit(), height=36)
        self._f_user.setPlaceholderText('Enter username')

        self._f_pass = self.add_field('PASSWORD', QLineEdit(), height=36)
        self._f_pass.setPlaceholderText('Enter password')
        self._f_pass.setEchoMode(QLineEdit.Password)
        self._f_pass.returnPressed.connect(self._try_login)

        self._error_lbl = QLabel('')
        self._error_lbl.setStyleSheet(
            'color: #ef4444; font-size: 12px; background: transparent; border: none;'
        )
        self._error_lbl.setVisible(False)
        self._root.addWidget(self._error_lbl)

        # Custom full-width sign-in button (no Cancel)
        sign_in = self._make_ok_btn('Sign in')
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
            self._error_lbl.setText('Incorrect username or password. Please try again.')
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
        self._component_syncing = False  # guard against brief↔traceability sync loops
        # Lazy screen registry: key → widget instance (None until first visited)
        self._screen_widgets: dict[str, Optional[QWidget]] = {k: None for k, _ in _NAV_ITEMS}
        self._screen_idx: dict[str, int] = {}
        self.setStyleSheet(f'background-color: {_BG};')
        self._build_ui()
        self._setup_autosave()

    # ── construction ──────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._nav = ProjectNavPanel()
        self._nav.set_navigate_callback(self._on_navigate)
        self._nav.info_changed.connect(self.mark_unsaved)
        self._nav.info_changed.connect(self._on_project_info_changed)
        layout.addWidget(self._nav)

        div = QFrame()
        div.setFrameShape(QFrame.VLine)
        div.setStyleSheet(f'color: {_BORDER}; background-color: {_BORDER}; max-width: 1px; border: none;')
        layout.addWidget(div)

        right_panel = QWidget()
        right_panel.setStyleSheet(f'background-color: {_CONTENT_BG};')
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self._build_top_bar())

        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f'background-color: {_CONTENT_BG};')
        right_layout.addWidget(self._stack, 1)

        layout.addWidget(right_panel, 1)

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
        bar.setFixedHeight(42)
        bar.setStyleSheet(f"""
            QWidget {{
                background-color: {_SIDEBAR};
                border-bottom: 1px solid {_BORDER};
            }}
        """)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)

        new_btn = QPushButton('＋ New Project')
        new_btn.setStyleSheet(_BTN_TOOLBAR); new_btn.setFixedHeight(28)
        new_btn.setCursor(Qt.PointingHandCursor)
        new_btn.setToolTip('Create a new empty project')
        new_btn.clicked.connect(self._on_new_project)

        open_btn = QPushButton('📂 Open Project')
        open_btn.setStyleSheet(_BTN_TOOLBAR); open_btn.setFixedHeight(28)
        open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.setToolTip('Open an existing .ectopjt file')
        open_btn.clicked.connect(self._on_open_project)

        self._save_btn = QPushButton('💾 Save Project')
        self._save_btn.setStyleSheet(_BTN_SAVE); self._save_btn.setFixedHeight(28)
        self._save_btn.setCursor(Qt.PointingHandCursor)
        self._save_btn.setToolTip('Save the current project')
        self._save_btn.clicked.connect(self._on_save_project)

        self._print_btn = QPushButton('🖨  Print')
        self._print_btn.setStyleSheet(_BTN_TOOLBAR); self._print_btn.setFixedHeight(28)
        self._print_btn.setCursor(Qt.PointingHandCursor)
        self._print_btn.setToolTip('Print or export the current section as PDF')
        self._print_btn.clicked.connect(self._on_print)

        self._lock_btn = QPushButton('🔓  Password')
        self._lock_btn.setStyleSheet(_BTN_TOOLBAR); self._lock_btn.setFixedHeight(28)
        self._lock_btn.setCursor(Qt.PointingHandCursor)
        self._lock_btn.setToolTip('Set or remove project password protection')
        self._lock_btn.clicked.connect(self._on_password_btn)

        layout.addWidget(new_btn)
        layout.addWidget(open_btn)
        layout.addWidget(self._save_btn)
        layout.addWidget(self._lock_btn)
        layout.addWidget(self._print_btn)

        self._project_name_lbl = QLabel('No project open')
        self._project_name_lbl.setStyleSheet(
            f'color: {_MUTED}; font-size: 12px; background: transparent; border: none;'
        )
        layout.addSpacing(6)
        layout.addWidget(self._project_name_lbl)
        layout.addStretch()

        vsep = QFrame()
        vsep.setFrameShape(QFrame.VLine); vsep.setFixedHeight(18)
        vsep.setStyleSheet(
            f'color: {default_theme.border_light}; background: {default_theme.border_light}; '
            f'max-width: 1px; border: none;'
        )
        layout.addWidget(vsep)

        self._avatar = QLabel('?')
        self._avatar.setFixedSize(24, 24)
        self._avatar.setAlignment(Qt.AlignCenter)
        self._avatar.setStyleSheet(f"""
            QLabel {{
                background-color: {_MUTED}; color: white; border-radius: 12px;
                font-size: 13px; font-weight: bold; border: none;
            }}
        """)
        self._user_btn = QPushButton('Not logged in  ▾')
        self._user_btn.setFlat(True)
        self._user_btn.setCursor(Qt.PointingHandCursor)
        self._user_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {_MUTED}; border: none;
                font-size: 13px; font-weight: bold; padding: 0 2px;
            }}
            QPushButton:hover {{ color: white; }}
        """)
        layout.addWidget(self._avatar)
        layout.addWidget(self._user_btn)

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

    # ── navigation ────────────────────────────────────────────────────────────

    def _on_navigate(self, key: str):
        self._current_screen_key = key
        widget = self._ensure_screen(key)
        self._stack.setCurrentIndex(self._screen_idx[key])
        if key == 'validation':
            self._push_validation_costs()
        elif key == 'traceability':
            self._sync_traceability_from_brief()

    def _on_print(self):
        key = self._current_screen_key
        if key is None:
            from ui.modal_utils import show_message_dialog
            show_message_dialog(self, 'Nothing to print',
                                'Please open a section first, then click Print.')
            return
        widget = self._screen_widgets.get(key)
        if widget is None:
            return
        # Human-readable label for the dialog title
        label = next((lbl for k, lbl in _NAV_ITEMS if k == key), key)
        # Strip emoji prefix for the window title
        title = label.split('\xa0')[-1].strip() if '\xa0' in label else label.strip()
        landscape = key == 'timeline'
        from ui.print_utils import print_section
        print_section(key, widget, title, self, landscape=landscape)

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

    # ── top bar ───────────────────────────────────────────────────────────────

    def set_user(self, username: str):
        letter = username[0].upper() if username else '?'
        self._avatar.setText(letter)
        self._avatar.setStyleSheet(f"""
            QLabel {{
                background-color: {_ACCENT}; color: white; border-radius: 12px;
                font-size: 13px; font-weight: bold; border: none;
            }}
        """)
        self._user_btn.setText(f'{username}  ▾')
        self._user_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {_TEXT}; border: none;
                font-size: 13px; font-weight: bold; padding: 0 2px;
            }}
            QPushButton:hover {{ color: white; }}
        """)

    # ── project file operations ───────────────────────────────────────────────

    def _on_new_project(self):
        if self._unsaved_changes and not self._confirm_discard():
            return
        self._project_path = None
        self._unsaved_changes = False
        self._project_password_hash = None
        self._update_lock_btn()
        self._update_title()

    def _on_open_project(self):
        if self._unsaved_changes and not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, 'Open Project', '',
            'ECTOFORM Project (*.ectopjt);;All Files (*)'
        )
        if not path:
            return
        try:
            self._load_project(path)
        except Exception as e:
            logger.error(f'Failed to open project: {e}', exc_info=True)
            QMessageBox.critical(self, 'Open Failed', f'Could not open project:\n{e}')

    def _on_save_project(self):
        if not self._project_path:
            path, _ = QFileDialog.getSaveFileName(
                self, 'Save Project', 'project.ectopjt',
                'ECTOFORM Project (*.ectopjt);;All Files (*)'
            )
            if not path:
                return
            if not path.endswith('.ectopjt'):
                path += '.ectopjt'
            self._project_path = path
        try:
            self._save_project(self._project_path)
        except Exception as e:
            logger.error(f'Failed to save project: {e}', exc_info=True)
            QMessageBox.critical(self, 'Save Failed', f'Could not save project:\n{e}')

    def _save_project(self, path: str):
        data = {'version': '1.0', 'project_info': self._nav.get_info_data()}
        if self._project_password_hash:
            data['password_hash'] = self._project_password_hash
        for key, _ in _NAV_ITEMS:
            w = self._screen_widgets.get(key)
            data[key] = w.get_data() if w and hasattr(w, 'get_data') else {}
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self._unsaved_changes = False
        self._update_title()
        logger.info(f'Project saved to {path}')

    def _load_project(self, path: str):
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Password-protected project — verify before loading
        stored_hash = data.get('password_hash')
        if stored_hash:
            from ui.passcode_dialog import PasscodeDialog
            dlg = PasscodeDialog(mode='enter', stored_hash=stored_hash, parent=self)
            dlg.setWindowTitle('Protected Project — Enter Password')
            if dlg.exec_() != QDialog.Accepted:
                return  # user cancelled — do not load

        self._nav.set_info_data(data.get('project_info', {}))
        for key, _ in _NAV_ITEMS:
            screen_data = data.get(key)
            if screen_data is None:
                continue
            w = self._ensure_screen(key)
            if hasattr(w, 'set_data'):
                w.set_data(screen_data)
        self._project_path = path
        self._project_password_hash = stored_hash  # keep hash in sync
        self._unsaved_changes = False
        self._update_lock_btn()
        self._update_title()
        logger.info(f'Project loaded from {path}')

    def _update_lock_btn(self):
        """Update the password button appearance to reflect the current lock state."""
        if self._project_password_hash:
            self._lock_btn.setText('🔒  Protected')
            self._lock_btn.setStyleSheet(_BTN_LOCK_ACTIVE)
            self._lock_btn.setToolTip('Project is password-protected — click to change or remove')
        else:
            self._lock_btn.setText('🔓  Password')
            self._lock_btn.setStyleSheet(_BTN_TOOLBAR)
            self._lock_btn.setToolTip('Set a password to protect this project')

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
            msg.setWindowTitle('Password Protection')
            msg.setText('Password verified.\n\nWhat would you like to do?')
            remove_btn = msg.addButton('Remove Password', QMessageBox.DestructiveRole)
            change_btn = msg.addButton('Change Password', QMessageBox.AcceptRole)
            msg.addButton('Cancel', QMessageBox.RejectRole)
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
        reply = QMessageBox.question(
            self, 'Unsaved Changes', 'You have unsaved changes. Discard them?',
            QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel
        )
        return reply == QMessageBox.Discard

    def _update_title(self):
        if self._project_path:
            name = Path(self._project_path).stem
            self._project_name_lbl.setText(f'📄  {name}')
            self._project_name_lbl.setStyleSheet(
                f'color: {_TEXT}; font-size: 12px; background: transparent; border: none;'
            )
        else:
            self._project_name_lbl.setText('No project open')
            self._project_name_lbl.setStyleSheet(
                f'color: {_MUTED}; font-size: 12px; background: transparent; border: none;'
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

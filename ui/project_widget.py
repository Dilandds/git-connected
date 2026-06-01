"""
The Project — main container widget.
Left panel: project info + navigation.
Right panel: top bar (open/save + user account) + stacked content screens.
"""
import json
import logging
import os
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QStackedWidget, QFileDialog, QMessageBox,
    QLineEdit, QComboBox, QDialog
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPixmap
from ui.styles import default_theme, make_font, dropdown_arrow_url as _get_arrow
_ARROW_URL = _get_arrow()
from ui.project_brief import ProjectBriefWidget
from ui.project_timeline import TimelineWidget
from ui.project_validation import ValidationWidget
from ui.estimated_cost import EstimatedCostWidget
from ui.report_widget import ReportWidget
from ui.version_comparison import VersionComparisonWidget
from ui.glossary_widget import GlossaryWidget
from ui.traceability_widget import TraceabilityWidget
from ui.files_widget import FilesVersionsWidget

logger = logging.getLogger(__name__)

_BG       = default_theme.background
_SIDEBAR  = '#1c2029'
_CARD     = default_theme.card_background
_BORDER   = default_theme.border_standard
_TEXT     = default_theme.text_primary
_MUTED    = default_theme.text_secondary
_ACCENT   = default_theme.button_primary
_ACCENT_H = default_theme.button_primary_hover

_NAV_ITEMS = [
    ("brief",              "📄  Project Brief"),
    ("timeline",           "⏱  Timeline"),
    ("validation",         "✔  Validation"),
    ("report",             "📋  Report"),
    ("estimated_cost",     "💰  Estimated Cost"),
    ("files",              "📁  Files & Versions"),
    ("version_comparison", "⭐  Version Comparison"),
    ("traceability",       "🔍  Traceability"),
    ("glossary",           "A-Z  Glossary"),
]

_NAV_ACTIVE = f"""
    QPushButton {{
        background-color: {_ACCENT};
        color: white;
        border: none;
        border-radius: 6px;
        padding: 8px 12px;
        font-size: 11px;
        font-weight: bold;
        text-align: left;
    }}
"""

_NAV_INACTIVE = f"""
    QPushButton {{
        background-color: transparent;
        color: {_MUTED};
        border: none;
        border-radius: 6px;
        padding: 8px 12px;
        font-size: 11px;
        text-align: left;
    }}
    QPushButton:hover {{
        background-color: #2a2e38;
        color: {_TEXT};
    }}
"""

_PLACEHOLDER_STYLE = f"""
    QLabel {{
        color: {_MUTED};
        font-size: 13px;
        background: transparent;
        border: none;
    }}
"""

_BTN_TOOLBAR = f"""
    QPushButton {{
        background-color: #2e323a;
        color: {_TEXT};
        border: 1px solid {default_theme.border_light};
        border-radius: 6px;
        font-size: 11px;
        padding: 4px 12px;
    }}
    QPushButton:hover {{
        background-color: #3a3e48;
        border-color: {_ACCENT};
        color: white;
    }}
    QPushButton:pressed {{
        background-color: {default_theme.button_primary_pressed};
        color: white;
    }}
    QPushButton:disabled {{
        color: {_MUTED};
        border-color: {_BORDER};
        background-color: #252830;
    }}
"""

_BTN_SAVE = f"""
    QPushButton {{
        background-color: {_ACCENT};
        color: white;
        border: none;
        border-radius: 6px;
        font-size: 11px;
        font-weight: bold;
        padding: 4px 14px;
    }}
    QPushButton:hover {{ background-color: {_ACCENT_H}; }}
    QPushButton:pressed {{ background-color: {default_theme.button_primary_pressed}; }}
    QPushButton:disabled {{
        background-color: #253545;
        color: #4a6070;
    }}
"""


_CONTENT_BG   = '#ffffff'
_CONTENT_TEXT = '#1e2430'
_CONTENT_MUTED = '#6b7280'

class _PlaceholderWidget(QWidget):
    """Temporary placeholder for screens not yet built."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {_CONTENT_BG};")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        lbl = QLabel(f"{title}\n\nComing soon")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(f"color: {_CONTENT_MUTED}; font-size: 13px; background: transparent; border: none;")
        lbl.setFont(make_font(size=13))
        layout.addWidget(lbl)


_INFO_INPUT_STYLE = f"""
    QLineEdit {{
        background-color: #1e2228;
        color: {_TEXT};
        border: 1px solid {_BORDER};
        border-radius: 4px;
        padding: 3px 6px;
        font-size: 10px;
    }}
    QLineEdit:focus {{
        border: 1px solid {_ACCENT};
    }}
"""

_STATUS_COMBO_STYLE = f"""
    QComboBox {{
        background-color: #1e2228;
        color: #4ade80;
        border: 1px solid {_BORDER};
        border-radius: 4px;
        padding: 3px 6px;
        font-size: 10px;
        font-weight: bold;
    }}
    QComboBox:focus {{ border: 1px solid {_ACCENT}; }}
    QComboBox::drop-down {{ border: none; width: 16px; }}
    QComboBox::down-arrow {{ image: url({_ARROW_URL}); width: 10px; height: 10px; }}
    QComboBox QAbstractItemView {{
        background-color: #1e2228;
        color: {_TEXT};
        border: 1px solid {_BORDER};
        selection-background-color: {_ACCENT};
    }}
"""

_STATUS_COLORS = {
    "In progress": "#4ade80",
    "Awaiting":    "#facc15",
    "Completed":   "#22d3ee",
    "Cancelled":   "#f87171",
}


class ProjectNavPanel(QWidget):
    """Left sidebar: project info card + navigation buttons."""

    info_changed = pyqtSignal()  # emitted whenever any info field changes

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(210)
        self.setStyleSheet(f"background-color: {_SIDEBAR};")
        self._buttons: dict[str, QPushButton] = {}
        self._on_navigate = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 14, 10, 14)
        layout.setSpacing(2)

        # ── project info card ──
        info_card = QFrame()
        info_card.setStyleSheet(f"""
            QFrame {{
                background-color: {_CARD};
                border: 1px solid {_BORDER};
                border-radius: 10px;
            }}
        """)
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(10, 10, 10, 10)
        info_layout.setSpacing(5)

        # ── photo button ──
        self._photo_btn = QPushButton("+Add photo")
        self._photo_btn.setFixedHeight(58)
        self._photo_btn.setCursor(Qt.PointingHandCursor)
        self._photo_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #1e2228;
                border: 1px dashed {_BORDER};
                border-radius: 6px;
                color: {_MUTED};
                font-size: 9px;
            }}
            QPushButton:hover {{
                border-color: {_ACCENT};
                color: {_ACCENT};
            }}
        """)
        self._photo_btn.clicked.connect(self._upload_photo)
        info_layout.addWidget(self._photo_btn)

        # ── editable fields ──
        self._f_company = QLineEdit()
        self._f_company.setPlaceholderText("Company name")
        self._f_company.setStyleSheet(_INFO_INPUT_STYLE)
        self._f_company.setFixedHeight(26)

        self._f_title = QLineEdit()
        self._f_title.setPlaceholderText("Project title")
        self._f_title.setStyleSheet(_INFO_INPUT_STYLE)
        self._f_title.setFixedHeight(26)

        self._f_number = QLineEdit()
        self._f_number.setPlaceholderText("Project number")
        self._f_number.setStyleSheet(_INFO_INPUT_STYLE)
        self._f_number.setFixedHeight(26)

        self._f_start_date = QLineEdit()
        self._f_start_date.setPlaceholderText("Start date (dd/mm/yyyy)")
        self._f_start_date.setStyleSheet(_INFO_INPUT_STYLE)
        self._f_start_date.setFixedHeight(26)

        for field in (self._f_company, self._f_title, self._f_number, self._f_start_date):
            info_layout.addWidget(field)
            field.textChanged.connect(lambda _: self.info_changed.emit())

        # ── status combo ──
        self._status_combo = QComboBox()
        self._status_combo.addItems(list(_STATUS_COLORS.keys()))
        self._status_combo.setFixedHeight(26)
        self._status_combo.setStyleSheet(_STATUS_COMBO_STYLE)
        self._status_combo.currentTextChanged.connect(self._on_status_changed)
        self._status_combo.currentTextChanged.connect(lambda _: self.info_changed.emit())
        info_layout.addWidget(self._status_combo)

        layout.addWidget(info_card)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {_BORDER}; background-color: {_BORDER}; max-height: 1px; border: none; margin: 8px 0;")
        layout.addWidget(sep)

        for key, label in _NAV_ITEMS:
            btn = QPushButton(label)
            btn.setStyleSheet(_NAV_INACTIVE)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(34)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, k=key: self._navigate(k))
            self._buttons[key] = btn
            layout.addWidget(btn)

        layout.addStretch()

    def _on_status_changed(self, text: str):
        color = _STATUS_COLORS.get(text, _TEXT)
        self._status_combo.setStyleSheet(
            _STATUS_COMBO_STYLE.replace("color: #4ade80;", f"color: {color};")
                               .replace("border-top: 5px solid #4ade80;", f"border-top: 5px solid {color};")
        )

    def _upload_photo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Project Photo", "",
            "Images (*.png *.jpg *.jpeg *.webp)"
        )
        if path:
            pix = QPixmap(path)
            if not pix.isNull():
                pix = pix.scaled(
                    self._photo_btn.width(), self._photo_btn.height(),
                    Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
                )
                icon_size = self._photo_btn.size()
                from PyQt5.QtGui import QIcon
                self._photo_btn.setIcon(QIcon(pix))
                self._photo_btn.setIconSize(icon_size)
                self._photo_btn.setText("")
                self.info_changed.emit()

    def get_info_data(self) -> dict:
        return {
            "company":    self._f_company.text(),
            "title":      self._f_title.text(),
            "number":     self._f_number.text(),
            "start_date": self._f_start_date.text(),
            "status":     self._status_combo.currentText(),
        }

    def set_info_data(self, data: dict):
        self._f_company.setText(data.get("company", ""))
        self._f_title.setText(data.get("title", ""))
        self._f_number.setText(data.get("number", ""))
        self._f_start_date.setText(data.get("start_date", ""))
        status = data.get("status", "In progress")
        idx = self._status_combo.findText(status)
        if idx >= 0:
            self._status_combo.setCurrentIndex(idx)

    def _navigate(self, key: str):
        for k, btn in self._buttons.items():
            btn.setStyleSheet(_NAV_ACTIVE if k == key else _NAV_INACTIVE)
            btn.setChecked(k == key)
        if self._on_navigate:
            self._on_navigate(key)

    def set_navigate_callback(self, fn):
        self._on_navigate = fn

    def select(self, key: str):
        self._navigate(key)


# ── Hardcoded credentials (single admin user for now) ────────────────────────
_PROJECT_CREDENTIALS = {
    "chris": "admin",
}


class ProjectLoginDialog(QDialog):
    """Styled login gate for The Project workspace."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("The Project — Login")
        self.setFixedWidth(380)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {_SIDEBAR}; border: 1px solid {_BORDER}; }}
            QLabel  {{ background: transparent; border: none; }}
        """)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 28, 28, 24)
        lay.setSpacing(14)

        # Header
        title = QLabel("The Project")
        title.setFont(make_font(size=16, bold=True))
        title.setStyleSheet(f"color: {_TEXT}; font-size: 16px; font-weight: bold;")
        sub = QLabel("Sign in to access your project workspace.")
        sub.setStyleSheet(f"color: {_MUTED}; font-size: 11px;")
        lay.addWidget(title)
        lay.addWidget(sub)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {_BORDER}; background: {_BORDER}; max-height: 1px; border: none;")
        lay.addWidget(sep)

        _field_style = f"""
            QLineEdit {{
                background: #1e2228; color: {_TEXT};
                border: 1px solid {_BORDER}; border-radius: 6px;
                padding: 6px 10px; font-size: 12px;
            }}
            QLineEdit:focus {{ border-color: {_ACCENT}; }}
        """

        def _lbl(text):
            l = QLabel(text)
            l.setStyleSheet(f"color: {_MUTED}; font-size: 10px; font-weight: bold;")
            return l

        lay.addWidget(_lbl("USERNAME"))
        self._f_user = QLineEdit()
        self._f_user.setPlaceholderText("Enter username")
        self._f_user.setFixedHeight(36)
        self._f_user.setStyleSheet(_field_style)
        lay.addWidget(self._f_user)

        lay.addWidget(_lbl("PASSWORD"))
        self._f_pass = QLineEdit()
        self._f_pass.setPlaceholderText("Enter password")
        self._f_pass.setEchoMode(QLineEdit.Password)
        self._f_pass.setFixedHeight(36)
        self._f_pass.setStyleSheet(_field_style)
        self._f_pass.returnPressed.connect(self._try_login)
        lay.addWidget(self._f_pass)

        self._error_lbl = QLabel("")
        self._error_lbl.setStyleSheet("color: #ef4444; font-size: 10px; background: transparent; border: none;")
        self._error_lbl.setVisible(False)
        lay.addWidget(self._error_lbl)

        login_btn = QPushButton("Sign in")
        login_btn.setFixedHeight(38)
        login_btn.setCursor(Qt.PointingHandCursor)
        login_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_ACCENT}; color: white; border: none;
                border-radius: 6px; font-size: 13px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {_ACCENT_H}; }}
        """)
        login_btn.clicked.connect(self._try_login)
        lay.addWidget(login_btn)

        self._f_user.setFocus()

    def _try_login(self):
        username = self._f_user.text().strip().lower()
        password = self._f_pass.text()
        expected = _PROJECT_CREDENTIALS.get(username)
        if expected and password == expected:
            self.accept()
        else:
            self._error_lbl.setText("Incorrect username or password. Please try again.")
            self._error_lbl.setVisible(True)
            self._f_pass.clear()
            self._f_pass.setFocus()

    def get_username(self) -> str:
        return self._f_user.text().strip().lower()


class TheProjectWidget(QWidget):
    """Main container for The Project tab."""

    open_in_viewer = pyqtSignal(str)   # propagated from Files & Versions → main window

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_path: str | None = None   # current .ectoproject file path
        self._unsaved_changes = False
        self.setStyleSheet(f"background-color: {_BG};")
        self._build_ui()
        self._setup_autosave()

    # ── top bar ───────────────────────────────────────────────────────────

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

        # ── Open / New / Save buttons ──
        new_btn = QPushButton("＋ New Project")
        new_btn.setStyleSheet(_BTN_TOOLBAR)
        new_btn.setFixedHeight(28)
        new_btn.setCursor(Qt.PointingHandCursor)
        new_btn.setToolTip("Create a new empty project")
        new_btn.clicked.connect(self._on_new_project)

        open_btn = QPushButton("📂 Open Project")
        open_btn.setStyleSheet(_BTN_TOOLBAR)
        open_btn.setFixedHeight(28)
        open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.setToolTip("Open an existing .ectoproject file")
        open_btn.clicked.connect(self._on_open_project)

        self._save_btn = QPushButton("💾 Save Project")
        self._save_btn.setStyleSheet(_BTN_SAVE)
        self._save_btn.setFixedHeight(28)
        self._save_btn.setCursor(Qt.PointingHandCursor)
        self._save_btn.setToolTip("Save the current project")
        self._save_btn.clicked.connect(self._on_save_project)

        layout.addWidget(new_btn)
        layout.addWidget(open_btn)
        layout.addWidget(self._save_btn)

        # ── current file name ──
        self._project_name_lbl = QLabel("No project open")
        self._project_name_lbl.setStyleSheet(
            f"color: {_MUTED}; font-size: 10px; background: transparent; border: none;"
        )
        layout.addSpacing(6)
        layout.addWidget(self._project_name_lbl)

        layout.addStretch()

        # ── vertical separator ──
        vsep = QFrame()
        vsep.setFrameShape(QFrame.VLine)
        vsep.setFixedHeight(18)
        vsep.setStyleSheet(f"color: {default_theme.border_light}; background: {default_theme.border_light}; max-width: 1px; border: none;")
        layout.addWidget(vsep)

        # ── user account ──
        self._avatar = QLabel("?")
        self._avatar.setFixedSize(24, 24)
        self._avatar.setAlignment(Qt.AlignCenter)
        self._avatar.setStyleSheet(f"""
            QLabel {{
                background-color: {_MUTED};
                color: white;
                border-radius: 12px;
                font-size: 11px;
                font-weight: bold;
                border: none;
            }}
        """)
        self._user_btn = QPushButton("Not logged in  ▾")
        self._user_btn.setFlat(True)
        self._user_btn.setCursor(Qt.PointingHandCursor)
        self._user_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {_MUTED};
                border: none;
                font-size: 11px;
                font-weight: bold;
                padding: 0 2px;
            }}
            QPushButton:hover {{ color: white; }}
        """)
        layout.addWidget(self._avatar)
        layout.addWidget(self._user_btn)

        return bar

    def set_user(self, username: str):
        """Update the avatar and button after a successful login."""
        letter = username[0].upper() if username else "?"
        self._avatar.setText(letter)
        self._avatar.setStyleSheet(f"""
            QLabel {{
                background-color: {_ACCENT};
                color: white;
                border-radius: 12px;
                font-size: 11px;
                font-weight: bold;
                border: none;
            }}
        """)
        self._user_btn.setText(f"{username}  ▾")
        self._user_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {_TEXT};
                border: none;
                font-size: 11px;
                font-weight: bold;
                padding: 0 2px;
            }}
            QPushButton:hover {{ color: white; }}
        """)

    # ── main layout ───────────────────────────────────────────────────────

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
        div.setStyleSheet(f"color: {_BORDER}; background-color: {_BORDER}; max-width: 1px; border: none;")
        layout.addWidget(div)

        right_panel = QWidget()
        right_panel.setStyleSheet(f"background-color: {_CONTENT_BG};")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self._build_top_bar())

        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background-color: {_CONTENT_BG};")
        right_layout.addWidget(self._stack, 1)

        layout.addWidget(right_panel, 1)

        self._brief_widget          = ProjectBriefWidget()
        self._timeline_widget       = TimelineWidget()
        self._validation_widget     = ValidationWidget()
        self._estimated_cost_widget = EstimatedCostWidget()
        self._report_widget            = ReportWidget()
        self._version_comparison_widget = VersionComparisonWidget()
        self._glossary_widget           = GlossaryWidget()
        self._traceability_widget       = TraceabilityWidget()
        self._files_widget              = FilesVersionsWidget()
        self._timeline_widget.changed.connect(self.mark_unsaved)
        self._validation_widget.changed.connect(self.mark_unsaved)
        self._estimated_cost_widget.changed.connect(self.mark_unsaved)
        self._estimated_cost_widget.changed.connect(self._on_estimated_cost_changed)
        self._report_widget.changed.connect(self.mark_unsaved)
        self._version_comparison_widget.changed.connect(self.mark_unsaved)
        self._glossary_widget.changed.connect(self.mark_unsaved)
        self._traceability_widget.changed.connect(self.mark_unsaved)
        self._files_widget.changed.connect(self.mark_unsaved)
        self._files_widget.open_in_viewer.connect(self.open_in_viewer)
        self._screens: dict[str, int] = {}
        screens = [
            ("timeline",           self._timeline_widget),
            ("validation",         self._validation_widget),
            ("report",             self._report_widget),
            ("estimated_cost",     self._estimated_cost_widget),
            ("files",              self._files_widget),
            ("version_comparison", self._version_comparison_widget),
            ("brief",              self._brief_widget),
            ("traceability",       self._traceability_widget),
            ("glossary",           self._glossary_widget),
        ]
        for key, widget in screens:
            idx = self._stack.addWidget(widget)
            self._screens[key] = idx

        self._nav.select("brief")
        _initial_info = self._nav.get_info_data()
        self._estimated_cost_widget.update_project_info(_initial_info)
        self._report_widget.update_project_info(_initial_info)

    # ── navigation ────────────────────────────────────────────────────────

    def _parse_target_budget(self) -> float:
        """Parse the 'Target total cost' free-text field from the Project Brief."""
        raw = self._brief_widget.get_data().get("cost", "") or ""
        cleaned = raw.strip().replace(",", "").replace(" ", "")
        for sym in ("€", "$", "£", "Fr", "¥", "د.إ"):
            cleaned = cleaned.replace(sym, "")
        try:
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0

    def _push_validation_costs(self):
        self._validation_widget.update_cost_summary(
            self._estimated_cost_widget.get_best_summary(),
            self._estimated_cost_widget._currency,
            self._parse_target_budget(),
        )

    def _on_navigate(self, key: str):
        self._stack.setCurrentIndex(self._screens.get(key, 0))
        if key == "validation":
            self._push_validation_costs()
        elif key == "traceability":
            self._sync_traceability_components()

    def _on_project_info_changed(self):
        info = self._nav.get_info_data()
        self._estimated_cost_widget.update_project_info(info)
        self._report_widget.update_project_info(info)

    def _sync_traceability_components(self):
        brief_data = self._brief_widget.get_data()
        self._traceability_widget.update_components_from_brief(
            brief_data.get("components", [])
        )

    def _on_estimated_cost_changed(self):
        if self._stack.currentIndex() == self._screens.get("validation"):
            self._push_validation_costs()

    # ── project file operations ───────────────────────────────────────────

    def _on_new_project(self):
        if self._unsaved_changes:
            if not self._confirm_discard():
                return
        self._project_path = None
        self._brief_widget  # reset would go here when data model exists
        self._unsaved_changes = False
        self._update_title()

    def _on_open_project(self):
        if self._unsaved_changes:
            if not self._confirm_discard():
                return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "",
            "ECTOFORM Project (*.ectoproject);;All Files (*)"
        )
        if not path:
            return
        try:
            self._load_project(path)
        except Exception as e:
            logger.error(f"Failed to open project: {e}", exc_info=True)
            QMessageBox.critical(self, "Open Failed", f"Could not open project:\n{e}")

    def _on_save_project(self):
        if not self._project_path:
            # First save — ask where
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Project", "project.ectoproject",
                "ECTOFORM Project (*.ectoproject);;All Files (*)"
            )
            if not path:
                return
            if not path.endswith(".ectoproject"):
                path += ".ectoproject"
            self._project_path = path
        try:
            self._save_project(self._project_path)
        except Exception as e:
            logger.error(f"Failed to save project: {e}", exc_info=True)
            QMessageBox.critical(self, "Save Failed", f"Could not save project:\n{e}")

    def _save_project(self, path: str):
        data = {
            "version": "1.0",
            "project_info": self._nav.get_info_data(),
            "brief":        self._brief_widget.get_data(),
            "timeline":     self._timeline_widget.get_data(),
            "validation":   self._validation_widget.get_data(),
            "estimated_cost": self._estimated_cost_widget.get_data(),
            "report":             self._report_widget.get_data(),
            "version_comparison": self._version_comparison_widget.get_data(),
            "glossary":           self._glossary_widget.get_data(),
            "traceability":       self._traceability_widget.get_data(),
            "files":              self._files_widget.get_data(),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self._unsaved_changes = False
        self._update_title()
        logger.info(f"Project saved to {path}")

    def _load_project(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._nav.set_info_data(data.get("project_info", {}))
        self._brief_widget.set_data(data.get("brief", {}))
        self._timeline_widget.set_data(data.get("timeline", {}))
        self._validation_widget.set_data(data.get("validation", {}))
        self._estimated_cost_widget.set_data(data.get("estimated_cost", {}))
        self._report_widget.set_data(data.get("report", {}))
        self._version_comparison_widget.set_data(data.get("version_comparison", {}))
        self._glossary_widget.set_data(data.get("glossary", {}))
        self._traceability_widget.set_data(data.get("traceability", {}))
        self._files_widget.set_data(data.get("files", {}))
        self._project_path = path
        self._unsaved_changes = False
        self._update_title()
        logger.info(f"Project loaded from {path}")

    def _confirm_discard(self) -> bool:
        reply = QMessageBox.question(
            self, "Unsaved Changes",
            "You have unsaved changes. Discard them?",
            QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Cancel
        )
        return reply == QMessageBox.Discard

    def _update_title(self):
        if self._project_path:
            name = Path(self._project_path).stem
            self._project_name_lbl.setText(f"📄  {name}")
            self._project_name_lbl.setStyleSheet(
                f"color: {_TEXT}; font-size: 10px; background: transparent; border: none;"
            )
        else:
            self._project_name_lbl.setText("No project open")
            self._project_name_lbl.setStyleSheet(
                f"color: {_MUTED}; font-size: 10px; background: transparent; border: none;"
            )

    # ── autosave ──────────────────────────────────────────────────────────

    def _setup_autosave(self):
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(30_000)  # every 30 seconds
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_timer.start()

    def _autosave(self):
        if self._project_path and self._unsaved_changes:
            try:
                self._save_project(self._project_path)
                logger.debug("Autosaved project")
            except Exception as e:
                logger.warning(f"Autosave failed: {e}")

    def mark_unsaved(self):
        """Call this whenever any screen data changes."""
        self._unsaved_changes = True

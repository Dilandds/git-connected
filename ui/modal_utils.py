"""
Reusable styled modal helpers for ECTOFORM.
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit
)
from PyQt5.QtCore import Qt
from ui.styles import default_theme


def _modal_colors(light: bool):
    if light:
        return {
            "bg": "#ffffff",
            "fg": "#111827",
            "muted": "#4b5563",
            "border": "#d1d5db",
            "secondary_bg": "#e5e7eb",
            "secondary_border": "#cbd5e1",
            "secondary_fg": "#111827",
        }
    return {
        "bg": default_theme.background,
        "fg": default_theme.text_primary,
        "muted": default_theme.text_secondary,
        "border": default_theme.border_standard,
        "secondary_bg": default_theme.button_default_bg,
        "secondary_border": default_theme.button_default_border,
        "secondary_fg": default_theme.text_primary,
    }


class StyledModalDialog(QDialog):
    def __init__(self, parent, title: str, message: str, *, light: bool = False,
                 primary_text: str = "OK", secondary_text: str = None, tertiary_text: str = None):
        super().__init__(parent)
        self._colors = _modal_colors(light)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(360)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {self._colors['bg']};
                border: 1px solid {self._colors['border']};
            }}
            QLabel {{
                color: {self._colors['fg']};
                background: transparent;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title_label = QLabel(title)
        title_label.setWordWrap(True)
        title_label.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {self._colors['fg']};")
        layout.addWidget(title_label)

        message_label = QLabel(message)
        message_label.setWordWrap(True)
        message_label.setStyleSheet(f"font-size: 13px; color: {self._colors['fg']};")
        layout.addWidget(message_label)

        layout.addSpacing(2)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        if secondary_text:
            self.secondary_btn = QPushButton(secondary_text)
            self.secondary_btn.setCursor(Qt.PointingHandCursor)
            self.secondary_btn.setMinimumWidth(90)
            self.secondary_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {self._colors['secondary_bg']};
                    color: {self._colors['secondary_fg']};
                    border: 1px solid {self._colors['secondary_border']};
                    border-radius: 6px;
                    padding: 8px 20px;
                    font-size: 13px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {default_theme.row_bg_hover if not light else '#f3f4f6'};
                }}
            """)
            btn_row.addWidget(self.secondary_btn)
        else:
            self.secondary_btn = None

        # Optional tertiary button (e.g. Cancel)
        if tertiary_text:
            self.tertiary_btn = QPushButton(tertiary_text)
            self.tertiary_btn.setCursor(Qt.PointingHandCursor)
            self.tertiary_btn.setMinimumWidth(90)
            self.tertiary_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {self._colors['muted']};
                    border: none;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background-color: rgba(255,255,255,0.04);
                }}
            """)
            # Insert tertiary before secondary if present, otherwise add before primary
            if self.secondary_btn is not None:
                btn_row.insertWidget(btn_row.count() - 1, self.tertiary_btn)
            else:
                btn_row.addWidget(self.tertiary_btn)
        else:
            self.tertiary_btn = None

        self.primary_btn = QPushButton(primary_text)
        self.primary_btn.setCursor(Qt.PointingHandCursor)
        self.primary_btn.setMinimumWidth(90)
        self.primary_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {default_theme.button_primary};
                color: {default_theme.text_white};
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {default_theme.button_primary_hover};
            }}
        """)
        btn_row.addWidget(self.primary_btn)
        layout.addLayout(btn_row)


def show_message_dialog(parent, title: str, message: str, *, light: bool = False):
    dlg = StyledModalDialog(parent, title, message, light=light, primary_text="OK")
    dlg.primary_btn.clicked.connect(dlg.accept)
    dlg.exec_()


def show_warning_dialog(parent, title: str, message: str, *, light: bool = False):
    show_message_dialog(parent, title, message, light=light)


def show_error_dialog(parent, title: str, message: str, *, light: bool = False):
    show_message_dialog(parent, title, message, light=light)


def ask_yes_no_dialog(parent, title: str, message: str, *, light: bool = False) -> bool:
    dlg = StyledModalDialog(parent, title, message, light=light, primary_text="Yes", secondary_text="No")
    result = {"value": False}

    def _accept():
        result["value"] = True
        dlg.accept()

    def _reject():
        result["value"] = False
        dlg.reject()

    dlg.primary_btn.clicked.connect(_accept)
    dlg.secondary_btn.clicked.connect(_reject)
    dlg.exec_()
    return result["value"]


def ask_yes_no_cancel_dialog(parent, title: str, message: str, *, light: bool = False) -> str:
    """Return 'yes', 'no', or 'cancel' depending on user choice."""
    dlg = StyledModalDialog(parent, title, message, light=light,
                            primary_text="Yes", secondary_text="No", tertiary_text="Cancel")
    result = {"value": 'cancel'}

    def _yes():
        result["value"] = 'yes'
        dlg.accept()

    def _no():
        result["value"] = 'no'
        dlg.reject()

    def _cancel():
        result["value"] = 'cancel'
        dlg.reject()

    dlg.primary_btn.clicked.connect(_yes)
    if dlg.secondary_btn:
        dlg.secondary_btn.clicked.connect(_no)
    if dlg.tertiary_btn:
        dlg.tertiary_btn.clicked.connect(_cancel)
    dlg.exec_()
    return result["value"]


def ask_text_input_dialog(parent, title: str, label: str,
                          placeholder: str = "", *, light: bool = True) -> tuple:
    """Styled single-line text input. Returns (text, accepted)."""
    colors = _modal_colors(light)
    accent = default_theme.button_primary
    accent_h = default_theme.button_primary_hover

    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setFixedWidth(360)
    dlg.setStyleSheet(f"""
        QDialog {{ background: {colors['bg']}; color: {colors['fg']}; }}
        QLabel  {{ color: {colors['muted']}; font-size: 10px; font-weight: bold;
                   background: transparent; border: none; }}
    """)
    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(16, 16, 16, 16)
    lay.setSpacing(10)

    lay.addWidget(QLabel(label.upper()))
    inp = QLineEdit()
    inp.setPlaceholderText(placeholder)
    inp.setStyleSheet(f"""
        QLineEdit {{
            background: {'#f5f6f8' if light else '#1e2228'};
            color: {colors['fg']}; border: 1px solid {colors['border']};
            border-radius: 4px; padding: 4px 8px; font-size: 11px;
        }}
        QLineEdit:focus {{ border-color: {accent}; }}
    """)
    inp.setFixedHeight(30)
    lay.addWidget(inp)

    btn_row = QHBoxLayout()
    btn_row.addStretch()
    cancel_btn = QPushButton("Cancel")
    cancel_btn.setCursor(Qt.PointingHandCursor)
    cancel_btn.setStyleSheet(f"""
        QPushButton {{
            background: {colors['secondary_bg']}; color: {colors['secondary_fg']};
            border: 1px solid {colors['secondary_border']}; border-radius: 5px;
            padding: 6px 16px; font-size: 11px;
        }}
        QPushButton:hover {{ background: {colors['border']}; }}
    """)
    ok_btn = QPushButton("OK")
    ok_btn.setCursor(Qt.PointingHandCursor)
    ok_btn.setStyleSheet(f"""
        QPushButton {{
            background: {accent}; color: white; border: none;
            border-radius: 5px; padding: 6px 16px; font-size: 11px; font-weight: bold;
        }}
        QPushButton:hover {{ background: {accent_h}; }}
    """)
    cancel_btn.clicked.connect(dlg.reject)
    ok_btn.clicked.connect(dlg.accept)
    btn_row.addWidget(cancel_btn)
    btn_row.addWidget(ok_btn)
    lay.addLayout(btn_row)

    inp.setFocus()
    accepted = dlg.exec_() == QDialog.Accepted
    return inp.text().strip(), accepted


def ask_password_dialog(parent, title: str, label: str, *, light: bool = True) -> tuple:
    """Styled password input (masked). Returns (text, accepted)."""
    colors = _modal_colors(light)
    accent = default_theme.button_primary
    accent_h = default_theme.button_primary_hover

    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setFixedWidth(360)
    dlg.setStyleSheet(f"""
        QDialog {{ background: {colors['bg']}; color: {colors['fg']}; }}
        QLabel  {{ color: {colors['muted']}; font-size: 10px; font-weight: bold;
                   background: transparent; border: none; }}
    """)
    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(16, 16, 16, 16)
    lay.setSpacing(10)

    lay.addWidget(QLabel(label.upper()))
    inp = QLineEdit()
    inp.setEchoMode(QLineEdit.Password)
    inp.setStyleSheet(f"""
        QLineEdit {{
            background: {'#f5f6f8' if light else '#1e2228'};
            color: {colors['fg']}; border: 1px solid {colors['border']};
            border-radius: 4px; padding: 4px 8px; font-size: 11px;
        }}
        QLineEdit:focus {{ border-color: {accent}; }}
    """)
    inp.setFixedHeight(30)
    lay.addWidget(inp)

    btn_row = QHBoxLayout()
    btn_row.addStretch()
    cancel_btn = QPushButton("Cancel")
    cancel_btn.setCursor(Qt.PointingHandCursor)
    cancel_btn.setStyleSheet(f"""
        QPushButton {{
            background: {colors['secondary_bg']}; color: {colors['secondary_fg']};
            border: 1px solid {colors['secondary_border']}; border-radius: 5px;
            padding: 6px 16px; font-size: 11px;
        }}
        QPushButton:hover {{ background: {colors['border']}; }}
    """)
    ok_btn = QPushButton("OK")
    ok_btn.setCursor(Qt.PointingHandCursor)
    ok_btn.setStyleSheet(f"""
        QPushButton {{
            background: {accent}; color: white; border: none;
            border-radius: 5px; padding: 6px 16px; font-size: 11px; font-weight: bold;
        }}
        QPushButton:hover {{ background: {accent_h}; }}
    """)
    cancel_btn.clicked.connect(dlg.reject)
    ok_btn.clicked.connect(dlg.accept)
    btn_row.addWidget(cancel_btn)
    btn_row.addWidget(ok_btn)
    lay.addLayout(btn_row)

    inp.setFocus()
    accepted = dlg.exec_() == QDialog.Accepted
    return inp.text(), accepted
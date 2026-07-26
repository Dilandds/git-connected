"""
Reusable styled modal system for ECTOFORM.

Class hierarchy:
    BaseModal       — theme contract (dark/light), tooltip fix, button/label factories
    ├── MessageModal  — title + body text + button row  (replaces StyledModalDialog)
    └── FormModal     — labeled field builder + standard button row

Every dialog in the app must inherit BaseModal so styling is never set manually.

Public helper functions (ask_yes_no_dialog etc.) are unchanged — they now use MessageModal.
"""
from __future__ import annotations
from typing import Optional

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QScrollArea, QWidget,
)
from PyQt5.QtCore import Qt
from ui.styles import default_theme, dropdown_arrow_url, TOOLTIP_STYLE

# ── Design tokens ─────────────────────────────────────────────────────────────
MODAL_BG    = default_theme.background
MODAL_FG    = default_theme.text_primary
MODAL_MUTED = default_theme.text_secondary

MODAL_BTN_PRIMARY = f"""
    QPushButton {{
        background-color: {default_theme.button_primary};
        color: white; border: none; border-radius: 10px;
        padding: 10px 28px; font-size: 13px; font-weight: bold; min-width: 80px;
    }}
    QPushButton:hover   {{ background-color: {default_theme.button_primary_hover}; }}
    QPushButton:pressed {{ background-color: {default_theme.button_primary_pressed}; }}
"""

MODAL_BTN_SECONDARY = f"""
    QPushButton {{
        background-color: {default_theme.button_default_bg};
        color: {default_theme.text_primary};
        border: 1px solid {default_theme.button_default_border};
        border-radius: 10px; padding: 10px 28px; font-size: 13px;
        font-weight: bold; min-width: 80px;
    }}
    QPushButton:hover {{ background-color: {default_theme.row_bg_hover}; }}
"""

MODAL_BTN_CANCEL = f"""
    QPushButton {{
        background-color: transparent; color: {default_theme.text_secondary};
        border: none; border-radius: 10px; padding: 10px 20px; font-size: 13px;
    }}
    QPushButton:hover {{ background-color: rgba(255,255,255,0.06); }}
"""

MODAL_BTN_CANCEL_LIGHT = """
    QPushButton {
        background-color: transparent; color: #4b5563;
        border: none; border-radius: 10px; padding: 10px 20px; font-size: 13px;
    }
    QPushButton:hover { background-color: #f3f4f6; }
"""

MODAL_BTN_DESTRUCTIVE = """
    QPushButton {
        background: transparent; color: #ef4444;
        border: 1px solid #fca5a5; border-radius: 6px;
        padding: 8px 16px; font-size: 12px;
    }
    QPushButton:hover   { background: #fee2e2; border-color: #ef4444; }
    QPushButton:pressed { background: #fecaca; }
"""

_TOOLTIP_CSS = TOOLTIP_STYLE  # imported from styles.py — single source of truth

_ARROW = dropdown_arrow_url()


def _build_dark_stylesheet() -> str:
    t = default_theme
    return f"""
        QDialog {{
            background-color: {t.background};
            color: {t.text_primary};
        }}
        QLabel {{
            color: {t.text_primary};
            background: transparent; border: none;
        }}
        QLineEdit, QTextEdit, QPlainTextEdit,
        QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit {{
            background-color: {t.input_bg};
            color: {t.text_primary};
            border: 1px solid {t.input_border};
            border-radius: 6px; padding: 3px 8px;
            selection-background-color: {t.button_primary};
            selection-color: white;
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
        QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QDateEdit:focus {{
            border: 2px solid {t.button_primary};
        }}
        QComboBox::drop-down, QDateEdit::drop-down {{ border: none; width: 20px; }}
        QComboBox::down-arrow, QDateEdit::down-arrow {{
            image: url({_ARROW}); width: 10px; height: 10px;
        }}
        QComboBox QAbstractItemView, QDateEdit QAbstractItemView {{
            background-color: {t.input_bg}; color: {t.text_primary};
            border: 1px solid {t.input_border};
            selection-background-color: {t.button_primary};
            selection-color: white;
        }}
        QCheckBox, QRadioButton {{
            color: {t.text_primary}; background: transparent;
        }}
        QPushButton {{ border: none; }}
        {_TOOLTIP_CSS}
    """


def _build_light_stylesheet() -> str:
    accent = default_theme.button_primary
    return f"""
        QDialog {{
            background-color: #ffffff;
            color: #111827;
        }}
        QLabel {{
            color: #111827;
            background: transparent; border: none;
        }}
        QLineEdit, QTextEdit, QPlainTextEdit,
        QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit {{
            background-color: #f5f6f8;
            color: #111827;
            border: 1px solid #d1d5db;
            border-radius: 4px; padding: 4px 8px; font-size: 13px;
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
        QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QDateEdit:focus {{
            border-color: {accent};
        }}
        QComboBox::drop-down, QDateEdit::drop-down {{ border: none; width: 20px; }}
        QComboBox::down-arrow, QDateEdit::down-arrow {{
            image: url({_ARROW}); width: 10px; height: 10px;
        }}
        QComboBox QAbstractItemView, QDateEdit QAbstractItemView {{
            background-color: #ffffff; color: #111827;
            border: 1px solid #d1d5db;
            selection-background-color: {accent}; selection-color: white;
        }}
        QCheckBox, QRadioButton {{
            color: #111827; background: transparent;
        }}
        QPushButton {{ border: none; }}
        {_TOOLTIP_CSS}
    """


# ── BaseModal ─────────────────────────────────────────────────────────────────

class BaseModal(QDialog):
    """
    Interface contract for every dialog in the app.

    Guarantees:
      • Consistent dark or light theme (no manual setStyleSheet in subclasses)
      • QToolTip never falls back to macOS native dark rendering
      • No platform help button
      • Standard button / label factories

    Themes:
      'dark'  — default, matches app background
      'light' — white background for content-focused dialogs
    """

    DARK  = 'dark'
    LIGHT = 'light'

    def __init__(self, parent, title: str, *,
                 theme: str = 'dark', min_width: int = 360):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(min_width)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._theme = theme
        self._fg    = MODAL_FG    if theme == 'dark' else '#111827'
        self._muted = MODAL_MUTED if theme == 'dark' else '#4b5563'
        self.setStyleSheet(
            _build_dark_stylesheet() if theme == 'dark' else _build_light_stylesheet()
        )
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(20, 20, 20, 20)
        self._root.setSpacing(14)

    # ── factories (used by subclasses) ────────────────────────────────────────

    def _make_label(self, text: str) -> QLabel:
        """ALL-CAPS muted field label."""
        l = QLabel(text.upper())
        l.setStyleSheet(
            f'color: {self._muted}; font-size: 11px; font-weight: bold; '
            f'background: transparent; border: none;'
        )
        return l

    def _make_btn(self, text: str, style: str, *, connect=None) -> QPushButton:
        b = QPushButton(text)
        b.setCursor(Qt.PointingHandCursor)
        b.setStyleSheet(style)
        if connect:
            b.clicked.connect(connect)
        return b

    def _make_ok_btn(self, text: str = 'OK') -> QPushButton:
        return self._make_btn(text, MODAL_BTN_PRIMARY, connect=self.accept)

    def _make_cancel_btn(self, text: str = 'Cancel') -> QPushButton:
        style = MODAL_BTN_CANCEL_LIGHT if self._theme == 'light' else MODAL_BTN_CANCEL
        return self._make_btn(text, style, connect=self.reject)

    def _make_delete_btn(self, text: str) -> QPushButton:
        """Destructive action button — emits done(2) so callers can branch on result."""
        return self._make_btn(text, MODAL_BTN_DESTRUCTIVE, connect=lambda: self.done(2))

    def _make_hline(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        color = '#3a3e48' if self._theme == 'dark' else '#e5e7eb'
        line.setStyleSheet(f'color: {color}; background: {color}; max-height: 1px; border: none;')
        return line


# ── FormModal ─────────────────────────────────────────────────────────────────

class FormModal(BaseModal):
    """
    Labeled-field form dialog.

    Usage — subclass and implement __init__:

        class MyDialog(FormModal):
            def __init__(self, parent=None):
                super().__init__(parent, 'My Title')
                self.f_name = self.add_field('NAME', QLineEdit())
                self.finish()           # appends OK / Cancel

    After finish() these attributes are set:
        self.ok_btn, self.cancel_btn, self.delete_btn (or None)
    """

    def add_field(self, label: str, widget: QWidget, *,
                  height: int = 28, height_override: int = None) -> QWidget:
        """Add a vertical label-above-widget field. Returns the widget."""
        h = height_override if height_override is not None else height
        if h:
            widget.setFixedHeight(h)
        self._root.addWidget(self._make_label(label))
        self._root.addWidget(widget)
        return widget

    def add_row_fields(self, *pairs: tuple) -> list:
        """
        Add multiple fields side-by-side.
        pairs = [('LABEL', widget), ...]
        Returns list of widgets in same order.
        """
        row = QHBoxLayout()
        row.setSpacing(10)
        widgets = []
        for label, widget in pairs:
            col = QVBoxLayout()
            col.setSpacing(3)
            col.addWidget(self._make_label(label))
            col.addWidget(widget)
            row.addLayout(col)
            widgets.append(widget)
        self._root.addLayout(row)
        return widgets

    def add_hfield(self, label: str, widget: QWidget, *,
                   label_width: int = 110) -> QWidget:
        """
        Horizontal label + widget (label fixed-width on left).
        Used for compact inline forms like the timeline task dialog.
        """
        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setFixedWidth(label_width)
        lbl.setStyleSheet(
            f'color: {self._fg}; font-size: 11px; background: transparent; border: none;'
        )
        row.addWidget(lbl)
        row.addWidget(widget, 1)
        self._root.addLayout(row)
        return widget

    def add_widget(self, widget: QWidget) -> QWidget:
        self._root.addWidget(widget)
        return widget

    def add_layout(self, layout) -> None:
        self._root.addLayout(layout)

    def add_separator(self):
        self._root.addWidget(self._make_hline())

    def finish(self, *, ok: str = 'OK', cancel: str = 'Cancel',
               delete: Optional[str] = None):
        """
        Append the button row and wire standard buttons.
        Call once, last, after all add_field() calls.
        OK (primary action) on the LEFT, Cancel on the RIGHT.
        """
        row = QHBoxLayout()
        self.delete_btn = None
        if delete:
            self.delete_btn = self._make_delete_btn(delete)
            row.addWidget(self.delete_btn)
        row.addStretch()
        self.ok_btn     = self._make_ok_btn(ok)
        self.cancel_btn = self._make_cancel_btn(cancel)
        row.addWidget(self.ok_btn)
        row.addWidget(self.cancel_btn)
        self._root.addLayout(row)


# ── MessageModal ──────────────────────────────────────────────────────────────

class MessageModal(BaseModal):
    """
    Title + body message + up to three buttons.
    Replaces StyledModalDialog — identical external API.
    """

    def __init__(self, parent, title: str, message: str, *,
                 theme: str = 'dark', min_width: int = 360,
                 primary_text: str = 'OK',
                 secondary_text: Optional[str] = None,
                 tertiary_text: Optional[str] = None):
        super().__init__(parent, title, theme=theme, min_width=min_width)

        title_lbl = QLabel(title)
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet(
            f'font-size: 15px; font-weight: bold; color: {self._fg}; '
            f'background: transparent; border: none;'
        )
        self._root.addWidget(title_lbl)

        msg_lbl = QLabel(message)
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet(
            f'font-size: 13px; color: {self._fg}; background: transparent; border: none;'
        )
        self._root.addWidget(msg_lbl)
        self._root.addSpacing(2)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        # Primary (Yes/OK) on the LEFT, secondary (No) on the RIGHT
        self.primary_btn = self._make_btn(primary_text, MODAL_BTN_PRIMARY)
        btn_row.addWidget(self.primary_btn)

        self.secondary_btn = None
        if secondary_text:
            self.secondary_btn = self._make_btn(secondary_text, MODAL_BTN_SECONDARY)
            btn_row.addWidget(self.secondary_btn)

        self.tertiary_btn = None
        if tertiary_text:
            self.tertiary_btn = self._make_btn(tertiary_text, MODAL_BTN_CANCEL)
            btn_row.addWidget(self.tertiary_btn)

        self._root.addLayout(btn_row)


# Backward-compatible alias
StyledModalDialog = MessageModal


# ── Public dialog helpers ─────────────────────────────────────────────────────

def show_message_dialog(parent, title: str, message: str, *, light: bool = True):
    dlg = MessageModal(parent, title, message,
                       theme=BaseModal.LIGHT if light else BaseModal.DARK,
                       primary_text='OK')
    dlg.primary_btn.clicked.connect(dlg.accept)
    dlg.exec_()


def show_warning_dialog(parent, title: str, message: str, *, light: bool = True):
    show_message_dialog(parent, title, message, light=light)


def show_error_dialog(parent, title: str, message: str, *, light: bool = True):
    show_message_dialog(parent, title, message, light=light)


def ask_yes_no_dialog(parent, title: str, message: str, *, light: bool = True) -> bool:
    dlg = MessageModal(parent, title, message,
                       theme=BaseModal.LIGHT if light else BaseModal.DARK,
                       primary_text='Yes', secondary_text='No')
    result = {'v': False}
    dlg.primary_btn.clicked.connect(lambda: (result.update(v=True),  dlg.accept()))
    dlg.secondary_btn.clicked.connect(lambda: (result.update(v=False), dlg.reject()))
    dlg.exec_()
    return result['v']


def ask_yes_no_cancel_dialog(parent, title: str, message: str,
                              *, light: bool = True) -> str:
    """Return 'yes', 'no', or 'cancel'."""
    dlg = MessageModal(parent, title, message,
                       theme=BaseModal.LIGHT if light else BaseModal.DARK,
                       primary_text='Yes', secondary_text='No', tertiary_text='Cancel')
    result = {'v': 'cancel'}
    dlg.primary_btn.clicked.connect(lambda: (result.update(v='yes'),    dlg.accept()))
    if dlg.secondary_btn:
        dlg.secondary_btn.clicked.connect(lambda: (result.update(v='no'), dlg.reject()))
    if dlg.tertiary_btn:
        dlg.tertiary_btn.clicked.connect(lambda: (result.update(v='cancel'), dlg.reject()))
    dlg.exec_()
    return result['v']


def ask_text_input_dialog(parent, title: str, label: str,
                          placeholder: str = '', *,
                          default_text: str = '', light: bool = True) -> tuple:
    """Single-line text input. Returns (text, accepted)."""
    dlg = FormModal(parent, title,
                    theme=BaseModal.LIGHT if light else BaseModal.DARK)
    inp = QLineEdit()
    inp.setPlaceholderText(placeholder)
    if default_text:
        inp.setText(default_text)
    dlg.add_field(label, inp)
    dlg.finish()
    inp.returnPressed.connect(dlg.ok_btn.click)
    inp.setFocus()
    accepted = dlg.exec_() == QDialog.Accepted
    return inp.text().strip(), accepted


def ask_password_dialog(parent, title: str, label: str,
                        *, light: bool = True) -> tuple:
    """Password input (masked). Returns (text, accepted)."""
    dlg = FormModal(parent, title,
                    theme=BaseModal.LIGHT if light else BaseModal.DARK)
    inp = QLineEdit()
    inp.setEchoMode(QLineEdit.Password)
    dlg.add_field(label, inp)
    dlg.finish()
    inp.returnPressed.connect(dlg.ok_btn.click)
    inp.setFocus()
    accepted = dlg.exec_() == QDialog.Accepted
    return inp.text(), accepted

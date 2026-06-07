"""
Palette, styles, and primitive factory functions for the Project Brief module.
All section modules import from here — nothing is redefined per file.
"""
from PyQt5.QtWidgets import QFrame, QLabel, QLineEdit, QTextEdit, QDateEdit
from PyQt5.QtCore import Qt, QDate
from ui.styles import default_theme, dropdown_arrow_url as _get_arrow, TOOLTIP_STYLE

_ARROW_URL = _get_arrow()

# ── palette (light theme) ─────────────────────────────────────────────────────
_BG       = '#f8f9fa'
_CARD     = '#ffffff'
_CARD2    = '#f1f3f5'
_BORDER   = '#e5e7eb'
_BORDER_L = '#d1d5db'
_TEXT     = '#1e2430'
_MUTED    = '#6b7280'
_ACCENT   = default_theme.button_primary
_ACCENT_H = default_theme.button_primary_hover
_INPUT_BG = '#f5f6f8'

# ── shared styles ─────────────────────────────────────────────────────────────
SECTION_HEADER_STYLE = f"""
    QLabel {{
        color: {_ACCENT}; font-size: 11px; font-weight: bold;
        letter-spacing: 1px; background: transparent; border: none; padding: 0;
    }}
"""

CARD_STYLE = f"""
    QFrame {{
        background-color: {_CARD};
        border: 1px solid {_BORDER};
        border-radius: 10px;
    }}
"""

INPUT_STYLE = f"""
    QLineEdit, QTextEdit {{
        background-color: {_INPUT_BG}; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 5px;
        padding: 5px 8px; font-size: 11px;
    }}
    QLineEdit:focus, QTextEdit:focus {{ border: 1px solid {_ACCENT}; }}
    QLineEdit:disabled, QTextEdit:disabled {{ color: {_MUTED}; background-color: {_CARD}; }}
"""

DATE_STYLE = f"""
    QDateEdit {{
        background-color: {_INPUT_BG}; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 5px;
        padding: 4px 8px; font-size: 11px;
    }}
    QDateEdit:focus {{ border: 1px solid {_ACCENT}; }}
    QDateEdit:disabled {{ color: {_MUTED}; background-color: {_CARD}; }}
    QDateEdit::drop-down {{ border: none; width: 20px; }}
    QDateEdit::down-arrow {{ image: url({_ARROW_URL}); width: 10px; height: 10px; }}
"""

BTN_PRIMARY = f"""
    QPushButton {{
        background-color: {_ACCENT}; color: white; border: none;
        border-radius: 6px; padding: 6px 16px; font-size: 11px; font-weight: bold;
    }}
    QPushButton:hover {{ background-color: {_ACCENT_H}; }}
    QPushButton:pressed {{ background-color: {default_theme.button_primary_pressed}; }}
"""

BTN_SECONDARY = f"""
    QPushButton {{
        background-color: {_CARD2}; color: {_TEXT};
        border: 1px solid {_BORDER_L}; border-radius: 6px;
        padding: 6px 16px; font-size: 11px;
    }}
    QPushButton:hover {{ background-color: {_BORDER_L}; border-color: {_ACCENT}; color: {_ACCENT}; }}
"""

ADD_BTN_STYLE = f"""
    QPushButton {{
        background-color: transparent; color: {_ACCENT}; border: none;
        font-size: 11px; font-weight: bold; padding: 2px 0; text-align: left;
    }}
    QPushButton:hover {{ color: {_ACCENT_H}; }}
""" + TOOLTIP_STYLE

LABEL_STYLE = f"color: {_MUTED}; font-size: 10px; background: transparent; border: none;"
VALUE_STYLE = f"color: {_TEXT}; font-size: 11px; background: transparent; border: none;"


# ── factory functions ─────────────────────────────────────────────────────────

def section_label(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(SECTION_HEADER_STYLE)
    return lbl


def field_label(text: str, fixed_width: int = 160) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(LABEL_STYLE)
    if fixed_width:
        lbl.setFixedWidth(fixed_width)
    return lbl


def card(parent=None) -> QFrame:
    f = QFrame(parent)
    f.setStyleSheet(CARD_STYLE)
    return f


def make_input(placeholder: str = '', min_height: int = 28) -> QLineEdit:
    w = QLineEdit()
    w.setPlaceholderText(placeholder)
    w.setMinimumHeight(min_height)
    w.setStyleSheet(INPUT_STYLE)
    return w


def make_textarea(placeholder: str = '', min_height: int = 70) -> QTextEdit:
    w = QTextEdit()
    w.setPlaceholderText(placeholder)
    w.setMinimumHeight(min_height)
    w.setStyleSheet(INPUT_STYLE)
    return w


def make_date_edit():
    from ui.date_picker import EctoDateEdit
    w = EctoDateEdit(QDate.currentDate())
    w.setMinimumHeight(28)
    return w


def separator() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.HLine)
    sep.setStyleSheet(
        f'color: {_BORDER}; background-color: {_BORDER}; border: none; max-height: 1px;'
    )
    return sep

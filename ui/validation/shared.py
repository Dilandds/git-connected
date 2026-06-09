"""
Palette, styles, and primitive helpers for the Validation module.
"""
from typing import List

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFrame, QLabel, QComboBox, QWidget,
    QVBoxLayout, QHBoxLayout, QSpinBox, QProgressBar,
)

from ui.styles import (
    default_theme, make_font,
    dropdown_arrow_url as _get_arrow,
    arrow_up_url, arrow_down_url,
    TOOLTIP_STYLE,
)

_ARROW_URL     = _get_arrow()
_ARROW_UP      = arrow_up_url()
_ARROW_DOWN    = arrow_down_url()
_TOOLTIP_STYLE = TOOLTIP_STYLE

# ── palette ───────────────────────────────────────────────────────────────────
_BG       = '#f8f9fa'
_CARD     = '#ffffff'
_BORDER   = '#e5e7eb'
_TEXT     = '#1e2430'
_MUTED    = '#6b7280'
_ACCENT   = default_theme.button_primary
_ACCENT_H = default_theme.button_primary_hover

# ── styles ────────────────────────────────────────────────────────────────────
_INPUT = f"""
    QLineEdit, QTextEdit, QComboBox, QDateEdit, QTimeEdit, QSpinBox {{
        background-color: #f5f6f8; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 4px;
        padding: 4px 8px; font-size: 15px;
    }}
    QLineEdit:focus, QTextEdit:focus, QComboBox:focus,
    QDateEdit:focus, QTimeEdit:focus, QSpinBox:focus {{
        border-color: {_ACCENT};
    }}
    QLineEdit:disabled, QTextEdit:disabled, QComboBox:disabled {{
        background-color: #f1f3f5; color: #9ca3af;
    }}
    QComboBox::drop-down {{ border: none; width: 20px; }}
    QComboBox::down-arrow {{ image: url({_ARROW_URL}); width: 10px; height: 10px; }}
    QDateEdit::drop-down {{ border: none; width: 20px; }}
    QDateEdit::down-arrow {{ image: url({_ARROW_URL}); width: 10px; height: 10px; }}
    QComboBox QAbstractItemView {{
        background: {_CARD}; color: {_TEXT};
        border: 1px solid {_BORDER};
        selection-background-color: {_ACCENT};
        selection-color: white;
    }}
"""

_TABLE_STYLE = f"""
    QTableWidget {{
        background-color: {_CARD}; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 6px;
        gridline-color: {_BORDER}; font-size: 15px;
    }}
    QTableWidget::item {{ padding: 4px 6px; }}
    QTableWidget::item:selected {{
        background-color: #dbeafe; color: {_TEXT};
    }}
    QHeaderView::section {{
        background-color: #f1f3f5; color: {_MUTED};
        border: none; border-bottom: 1px solid {_BORDER};
        border-right: 1px solid {_BORDER};
        padding: 5px 8px; font-size: 14px; font-weight: bold;
    }}
"""

_BTN_PRIMARY = f"""
    QPushButton {{
        background-color: {_ACCENT}; color: white;
        border: none; border-radius: 5px;
        padding: 5px 14px; font-size: 15px; font-weight: bold;
    }}
    QPushButton:hover {{ background-color: {_ACCENT_H}; }}
    QPushButton:pressed {{ background-color: {default_theme.button_primary_pressed}; }}
""" + _TOOLTIP_STYLE

_BTN_OUTLINE = f"""
    QPushButton {{
        background-color: transparent; color: {_ACCENT};
        border: 1px solid {_ACCENT}; border-radius: 5px;
        padding: 4px 12px; font-size: 14px; font-weight: bold;
    }}
    QPushButton:hover {{ background-color: #dbeafe; }}
""" + _TOOLTIP_STYLE

_BTN_SMALL = f"""
    QPushButton {{
        background-color: #f1f3f5; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 4px;
        padding: 3px 8px; font-size: 14px;
    }}
    QPushButton:hover {{ background-color: #e5e7eb; border-color: {_ACCENT}; color: {_ACCENT}; }}
""" + _TOOLTIP_STYLE

_SECTION_TITLE = f"color: {_TEXT}; font-size: 15px; font-weight: bold; background: transparent; border: none;"
_LBL_STYLE     = f"color: {_MUTED}; font-size: 14px; background: transparent; border: none;"

_TIMEEDIT_STYLE = f"""
    QTimeEdit {{
        background-color: #f5f6f8; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 4px;
        padding: 3px 18px 3px 6px; font-size: 15px;
    }}
    QTimeEdit:focus {{ border-color: {_ACCENT}; }}
    QTimeEdit::up-button {{
        subcontrol-origin: border; subcontrol-position: top right;
        width: 16px; height: 11px;
        background: #e5e7eb;
        border-left: 1px solid {_BORDER};
        border-bottom: 1px solid {_BORDER};
        border-top-right-radius: 3px;
    }}
    QTimeEdit::up-button:hover {{ background: {_ACCENT}; }}
    QTimeEdit::up-arrow {{ image: url({_ARROW_UP}); width: 8px; height: 8px; }}
    QTimeEdit::down-button {{
        subcontrol-origin: border; subcontrol-position: bottom right;
        width: 16px; height: 11px;
        background: #e5e7eb;
        border-left: 1px solid {_BORDER};
        border-top: 1px solid {_BORDER};
        border-bottom-right-radius: 3px;
    }}
    QTimeEdit::down-button:hover {{ background: {_ACCENT}; }}
    QTimeEdit::down-arrow {{ image: url({_ARROW_DOWN}); width: 8px; height: 8px; }}
"""

_TAB_ACTIVE = f"""
    QPushButton {{
        background-color: {_ACCENT}; color: white;
        border: none; border-radius: 5px;
        padding: 5px 14px; font-size: 15px; font-weight: bold;
    }}
""" + _TOOLTIP_STYLE

_TAB_INACTIVE = f"""
    QPushButton {{
        background-color: transparent; color: {_MUTED};
        border: 1px solid {_BORDER}; border-radius: 5px;
        padding: 5px 14px; font-size: 15px;
    }}
    QPushButton:hover {{ color: {_TEXT}; border-color: {_ACCENT}; background-color: #e8f0fe; }}
""" + _TOOLTIP_STYLE

_COMBO_STYLE = f"""
    QComboBox {{
        background-color: {_CARD};
        color: {_TEXT};
        border: 1px solid {_BORDER};
        border-radius: 5px;
        padding: 3px 28px 3px 8px;
        font-size: 15px;
    }}
    QComboBox:hover {{ border-color: #9ca3af; }}
    QComboBox:focus {{ border-color: {_ACCENT}; }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 22px;
        border-left: 1px solid {_BORDER};
        border-top-right-radius: 5px;
        border-bottom-right-radius: 5px;
        background: #f1f3f5;
    }}
    QComboBox::down-arrow {{ image: url({_ARROW_URL}); width: 10px; height: 10px; }}
    QComboBox QAbstractItemView {{
        background-color: {_CARD};
        color: {_TEXT};
        border: 1px solid {_BORDER};
        border-radius: 4px;
        padding: 2px;
        outline: none;
        selection-background-color: #dbeafe;
        selection-color: {_TEXT};
        font-size: 15px;
    }}
    QComboBox QAbstractItemView::item {{
        padding: 5px 10px;
        border-radius: 3px;
        min-height: 24px;
    }}
    QComboBox QAbstractItemView::item:hover {{
        background-color: #eff6ff;
        color: {_TEXT};
    }}
    QComboBox QAbstractItemView::item:selected {{
        background-color: #dbeafe;
        color: {_TEXT};
        font-weight: bold;
    }}
"""

# ── primitive helpers ─────────────────────────────────────────────────────────

def _sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f"color: {_BORDER}; background: {_BORDER}; max-height: 1px; border: none;")
    return f


def _vdiv() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.VLine)
    f.setStyleSheet(f"color: {_BORDER}; background: {_BORDER}; max-width: 1px; border: none;")
    return f


def _card_frame() -> QFrame:
    f = QFrame()
    f.setStyleSheet(
        f"QFrame {{ background-color: {_CARD}; border: 1px solid {_BORDER}; border-radius: 8px; }}"
    )
    return f


def _section_title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(_SECTION_TITLE)
    return lbl


def _lbl(text: str) -> QLabel:
    l = QLabel(text)
    l.setStyleSheet(_LBL_STYLE)
    return l


def _combo(options: List[str]) -> QComboBox:
    c = QComboBox()
    c.addItems(options)
    c.setStyleSheet(_COMBO_STYLE)
    c.setFrame(False)
    return c


# ── _ProgressCell ─────────────────────────────────────────────────────────────

class _ProgressCell(QWidget):
    """Spinbox + coloured progress bar for the stakeholder table."""

    valueChanged = pyqtSignal(int)

    _BAR_COLORS = [
        (0,   _BORDER),
        (30,  "#ef4444"),
        (70,  "#f59e0b"),
        (101, "#22c55e"),
    ]

    def __init__(self, value: int = 0, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 3, 4, 3)
        lay.setSpacing(3)

        self._spin = QSpinBox()
        self._spin.setRange(0, 100)
        self._spin.setValue(value)
        self._spin.setSuffix(" %")
        self._spin.setFixedHeight(20)
        self._spin.setStyleSheet(f"""
            QSpinBox {{
                background: #f5f6f8; color: {_TEXT};
                border: 1px solid {_BORDER}; border-radius: 3px;
                padding: 0 18px 0 4px; font-size: 14px;
            }}
            QSpinBox:focus {{ border-color: {_ACCENT}; }}
            QSpinBox::up-button {{
                subcontrol-origin: border; subcontrol-position: top right;
                width: 16px; height: 10px;
                background: #e5e7eb;
                border-left: 1px solid {_BORDER};
                border-bottom: 1px solid {_BORDER};
                border-top-right-radius: 3px;
            }}
            QSpinBox::up-button:hover {{ background: {_ACCENT}; }}
            QSpinBox::up-arrow {{ image: url({_ARROW_UP}); width: 8px; height: 8px; }}
            QSpinBox::down-button {{
                subcontrol-origin: border; subcontrol-position: bottom right;
                width: 16px; height: 10px;
                background: #e5e7eb;
                border-left: 1px solid {_BORDER};
                border-top: 1px solid {_BORDER};
                border-bottom-right-radius: 3px;
            }}
            QSpinBox::down-button:hover {{ background: {_ACCENT}; }}
            QSpinBox::down-arrow {{ image: url({_ARROW_DOWN}); width: 8px; height: 8px; }}
        """)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(value)
        self._bar.setFixedHeight(5)
        self._bar.setTextVisible(False)
        self._apply_bar_color(value)

        lay.addWidget(self._spin)
        lay.addWidget(self._bar)

        self._spin.valueChanged.connect(self._on_change)

    def _on_change(self, v: int):
        self._bar.setValue(v)
        self._apply_bar_color(v)
        self.valueChanged.emit(v)

    def _apply_bar_color(self, v: int):
        color = _BORDER
        for threshold, col in self._BAR_COLORS:
            if v < threshold:
                break
            color = col
        self._bar.setStyleSheet(f"""
            QProgressBar {{ background: {_BORDER}; border: none; border-radius: 2px; }}
            QProgressBar::chunk {{ background: {color}; border-radius: 2px; }}
        """)

    def value(self) -> int:
        return self._spin.value()

    def setValue(self, v: int):
        self._spin.blockSignals(True)
        self._spin.setValue(v)
        self._bar.setValue(v)
        self._apply_bar_color(v)
        self._spin.blockSignals(False)

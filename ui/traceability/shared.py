"""
Palette constants, shared button styles, and primitive helper widgets
used across all traceability sub-modules.
"""
from PyQt5.QtWidgets import QFrame, QLabel, QSizePolicy, QWidget
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPainter, QBrush
from ui.styles import default_theme, make_font, dropdown_arrow_url as _get_arrow, TOOLTIP_STYLE

_ARROW_URL = _get_arrow()

# Alias kept for internal use — imported from styles.py (single source of truth).
_TOOLTIP_STYLE = TOOLTIP_STYLE

# ── palette ───────────────────────────────────────────────────────────────────
_BG      = '#f8f9fa'
_CARD    = '#ffffff'
_BORDER  = '#e5e7eb'
_TEXT    = '#1e2430'
_MUTED   = '#6b7280'
_ACCENT  = default_theme.button_primary
_ACCENT_H = default_theme.button_primary_hover

_STATUS_COLORS = {
    'Completed':   '#22c55e',
    'In Progress': _ACCENT,
    'Upcoming':    '#9ca3af',
}

_PART_PALETTE = [
    '#3b82f6', '#8b5cf6', '#10b981', '#f59e0b',
    '#ef4444', '#06b6d4', '#f97316', '#14b8a6',
]

# ── shared button / input styles ──────────────────────────────────────────────
_INPUT = f"""
    QLineEdit, QTextEdit, QComboBox, QSpinBox {{
        background: #f5f6f8; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 4px;
        padding: 3px 6px; font-size: 11px;
    }}
    QLineEdit:focus, QTextEdit:focus, QComboBox:focus,
    QSpinBox:focus {{ border-color: {_ACCENT}; }}
    QComboBox::drop-down {{ border: none; width: 20px; }}
    QComboBox::down-arrow {{ image: url({_ARROW_URL}); width: 10px; height: 10px; }}
    QComboBox QAbstractItemView {{
        background: {_CARD}; color: {_TEXT};
        border: 1px solid {_BORDER};
        selection-background-color: {_ACCENT}; selection-color: white;
    }}
"""

_BTN_PRIMARY = f"""
    QPushButton {{
        background: {_ACCENT}; color: white; border: none;
        border-radius: 5px; padding: 5px 14px; font-size: 11px; font-weight: bold;
    }}
    QPushButton:hover {{ background: {_ACCENT_H}; }}
"""

_BTN_SMALL = f"""
    QPushButton {{
        background: #f1f3f5; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 4px;
        padding: 3px 8px; font-size: 10px;
    }}
    QPushButton:hover {{ background: #e5e7eb; border-color: {_ACCENT}; color: {_ACCENT}; }}
"""

_BTN_OUTLINE = f"""
    QPushButton {{
        background: transparent; color: {_ACCENT};
        border: 1px solid {_ACCENT}; border-radius: 4px;
        padding: 3px 10px; font-size: 10px; font-weight: bold;
    }}
    QPushButton:hover {{ background: #dbeafe; }}
"""

_BTN_ICON = f"""
    QPushButton {{
        background: transparent; border: none;
        color: {_MUTED}; font-size: 12px; padding: 2px 4px;
    }}
    QPushButton:hover {{ color: {_ACCENT}; background: #e8f0fe; border-radius: 3px; }}
"""

_BTN_DELETE = f"""
    QPushButton {{
        background: transparent; border: none;
        color: {_MUTED}; font-size: 12px; padding: 2px 4px;
    }}
    QPushButton:hover {{ color: #ef4444; background: #fee2e2; border-radius: 3px; }}
"""

# Red circle × button used on card corners (component + stage delete).
# Includes QToolTip so macOS never falls back to native dark tooltip.
_BTN_DEL_CIRCLE = """
    QPushButton {
        background-color: transparent; color: #6b7280;
        border: none;
        font-size: 11px; font-weight: bold;
        padding: 0; min-width: 18px; min-height: 18px;
    }
    QPushButton:hover { background-color: transparent; color: #ef4444; }
""" + _TOOLTIP_STYLE

# Sub-stage tab button styles — include QToolTip for the same reason.
def tab_active_style(accent: str) -> str:
    return f"""
        QPushButton {{
            background: {accent}; color: white; border: none;
            border-radius: 5px 0 0 5px; padding: 4px 10px;
            font-size: 10px; font-weight: bold;
        }}
    """ + _TOOLTIP_STYLE

def tab_inactive_style(border: str, muted: str, text: str, accent: str) -> str:
    return f"""
        QPushButton {{
            background: transparent; color: {muted};
            border: 1px solid {border}; border-radius: 5px 0 0 5px;
            padding: 4px 10px; font-size: 10px;
        }}
        QPushButton:hover {{ color: {text}; border-color: {accent}; background: #e8f0fe; }}
    """ + _TOOLTIP_STYLE

_MENU_STYLE = f"""
    QMenu {{ background: {_CARD}; border: 1px solid {_BORDER}; border-radius: 6px; padding: 4px; }}
    QMenu::item {{ padding: 6px 16px; font-size: 11px; color: {_TEXT}; border-radius: 4px; }}
    QMenu::item:selected {{ background: #e8f0fe; color: {_ACCENT}; }}
"""

_FIELD_LABEL_STYLE = (
    f'color: {_MUTED}; font-size: 9px; font-weight: bold; '
    f'background: transparent; border: none;'
)


# ── primitive helpers ─────────────────────────────────────────────────────────

def _vline() -> QFrame:
    v = QFrame()
    v.setFrameShape(QFrame.VLine)
    v.setStyleSheet(f'color: {_BORDER}; background: {_BORDER}; max-width: 1px; border: none;')
    return v


def _hline() -> QFrame:
    h = QFrame()
    h.setFrameShape(QFrame.HLine)
    h.setStyleSheet(f'color: {_BORDER}; background: {_BORDER}; max-height: 1px; border: none;')
    return h


def _field_label(text: str) -> QLabel:
    """Small ALL-CAPS label used above form fields in dialogs."""
    l = QLabel(text)
    l.setStyleSheet(_FIELD_LABEL_STYLE)
    return l


def _status_badge(status: str) -> QLabel:
    color = _STATUS_COLORS.get(status, _MUTED)
    badge = QLabel(status)
    badge.setStyleSheet(f"""
        QLabel {{
            background: {color}22; color: {color};
            border: 1px solid {color}88; border-radius: 4px;
            padding: 2px 8px; font-size: 9px; font-weight: bold;
        }}
    """)
    badge.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    return badge


class _PartBadge(QWidget):
    """Numbered colour circle for a part row. Pass label='1.1.3' for dot notation."""

    def __init__(self, number: int, color: str, label: str = None, size: int = 38, parent=None):
        super().__init__(parent)
        self._label = label if label is not None else str(number)
        self._color = QColor(color)
        self.setFixedSize(size, size)
        self._size  = size

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QBrush(self._color))
        p.setPen(Qt.NoPen)
        m = 1
        p.drawEllipse(m, m, self._size - 2*m, self._size - 2*m)
        p.setPen(QColor('white'))
        font_size = 7 if len(self._label) > 2 else 9
        p.setFont(make_font(size=font_size, bold=True))
        p.drawText(self.rect(), Qt.AlignCenter, self._label)
        p.end()


class _ProgressBar(QWidget):
    """Thin horizontal progress bar drawn via QPainter."""

    def __init__(self, value: int = 0, parent=None):
        super().__init__(parent)
        self._value = max(0, min(100, value))
        self._bar_w = 110
        self.setFixedSize(self._bar_w, 7)

    def set_value(self, v: int):
        self._value = max(0, min(100, v))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.setBrush(QBrush(QColor(_BORDER)))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, w, h, 3, 3)
        if self._value > 0:
            fill_w = max(7, int(w * self._value / 100))
            color = QColor('#22c55e') if self._value == 100 else QColor(_ACCENT)
            p.setBrush(QBrush(color))
            p.drawRoundedRect(0, 0, fill_w, h, 3, 3)
        p.end()

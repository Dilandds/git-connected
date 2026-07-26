"""
Palette constants, shared button/input styles, and primitive helper widgets
used across all report sub-modules.
"""
from PyQt5.QtWidgets import QFrame, QLabel, QLineEdit, QSizePolicy, QWidget
from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QColor, QPainter
from ui.styles import default_theme, make_font, dropdown_arrow_url as _get_arrow, TOOLTIP_STYLE

_ARROW_URL = _get_arrow()

# Alias kept for internal use — imported from styles.py (single source of truth).
_TOOLTIP_STYLE = TOOLTIP_STYLE

# ── palette ───────────────────────────────────────────────────────────────────
_BG       = '#f8f9fa'
_CARD     = '#ffffff'
_BORDER   = '#e5e7eb'
_TEXT     = '#1e2430'
_MUTED    = '#6b7280'
_ACCENT   = default_theme.button_primary
_ACCENT_H = default_theme.button_primary_hover
_HDR_BG   = '#e8f5ee'
_HDR_TEXT = '#1a7a4a'

# ── input style ───────────────────────────────────────────────────────────────
_INPUT = f"""
    QLineEdit, QTextEdit, QDateEdit {{
        background-color: #f5f6f8; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 4px;
        padding: 4px 8px; font-size: 17px;
    }}
    QLineEdit:focus, QTextEdit:focus, QDateEdit:focus {{ border-color: {_ACCENT}; }}
    QLineEdit:read-only, QTextEdit:read-only {{
        background-color: #f1f3f5; color: {_MUTED};
    }}
    QDateEdit::drop-down {{ border: none; width: 20px; }}
    QDateEdit::down-arrow {{ image: url({_ARROW_URL}); width: 12px; height: 12px; }}
"""

# ── button styles ─────────────────────────────────────────────────────────────
_BTN_PRIMARY = f"""
    QPushButton {{
        background-color: {_ACCENT}; color: white; border: none;
        border-radius: 5px; padding: 5px 14px; font-size: 15px; font-weight: bold;
    }}
    QPushButton:hover {{ background-color: {_ACCENT_H}; }}
    QPushButton:disabled {{ background-color: #b0c4cc; }}
"""
_BTN_SMALL = f"""
    QPushButton {{
        background-color: #f1f3f5; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 4px;
        padding: 3px 8px; font-size: 14px;
    }}
    QPushButton:hover {{ background-color: #e5e7eb; border-color: {_ACCENT}; color: {_ACCENT}; }}
    QPushButton:disabled {{ color: #9ca3af; background: #f9fafb; }}
"""
_BTN_OUTLINE = f"""
    QPushButton {{
        background-color: transparent; color: {_ACCENT};
        border: 1px solid {_ACCENT}; border-radius: 5px;
        padding: 4px 12px; font-size: 14px; font-weight: bold;
    }}
    QPushButton:hover {{ background-color: #dbeafe; }}
"""
# ── tab styles ────────────────────────────────────────────────────────────────
_TAB_ACTIVE = f"""
    QPushButton {{
        background-color: {_ACCENT}; color: white; border: none;
        border-radius: 5px; padding: 5px 14px; font-size: 15px; font-weight: bold;
    }}
"""
_TAB_INACTIVE = f"""
    QPushButton {{
        background-color: transparent; color: {_MUTED};
        border: 1px solid {_BORDER}; border-radius: 5px; padding: 5px 14px; font-size: 15px;
    }}
    QPushButton:hover {{ color: {_TEXT}; border-color: {_ACCENT}; background-color: #e8f0fe; }}
"""
# Left-rounded variants (paired with a × close button that provides the right radius).
_TAB_ACTIVE_L   = _TAB_ACTIVE.replace("border-radius: 5px;", "border-radius: 5px 0 0 5px;")
_TAB_INACTIVE_L = _TAB_INACTIVE.replace("border-radius: 5px;", "border-radius: 5px 0 0 5px;")

# Tab × close buttons — include QToolTip so macOS never falls back to native dark tooltip.
_CLOSE_ACTIVE = f"""
    QPushButton {{
        background-color: {_ACCENT}; color: rgba(255,255,255,0.55);
        border: none; border-left: 1px solid rgba(255,255,255,0.18);
        border-radius: 0 5px 5px 0; font-size: 13px; font-weight: bold; padding: 0 5px;
    }}
    QPushButton:hover {{ color: white; background-color: #ef4444; }}
""" + _TOOLTIP_STYLE
_CLOSE_INACTIVE = f"""
    QPushButton {{
        background-color: transparent; color: {_MUTED};
        border: 1px solid {_BORDER}; border-left: none;
        border-radius: 0 5px 5px 0; font-size: 13px; font-weight: bold; padding: 0 5px;
    }}
    QPushButton:hover {{ color: #ef4444; background-color: #fee2e2; border-color: #fca5a5; }}
""" + _TOOLTIP_STYLE

# Lock button — include QToolTip for the same reason.
_BTN_LOCK = f"""
    QPushButton {{
        background-color: #fef3c7; color: #b45309;
        border: 1px solid #fde68a; border-radius: 5px;
        padding: 4px 12px; font-size: 14px; font-weight: bold;
    }}
    QPushButton:hover {{ background-color: #fde68a; }}
    QPushButton:disabled {{ background-color: #f1f3f5; color: #9ca3af; border-color: {_BORDER}; }}
""" + _TOOLTIP_STYLE


# ── primitive helpers ─────────────────────────────────────────────────────────

class _VerticalLabel(QWidget):
    """Label that renders text rotated 90° (bottom-to-top), used for section sidebars."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._text = text
        self.setFixedWidth(22)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#f1f3f5'))
        p.setPen(QColor(_MUTED))
        p.setFont(make_font(size=9, bold=True))
        p.translate(0, self.height())
        p.rotate(-90)
        p.drawText(QRect(0, 0, self.height(), self.width()), Qt.AlignCenter, self._text)
        p.end()


def _sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f"color: {_BORDER}; background: {_BORDER}; max-height: 1px; border: none;")
    return f


def _card(parent=None) -> QFrame:
    f = QFrame(parent)
    f.setStyleSheet(
        f"QFrame {{ background-color: {_CARD}; border: 1px solid {_BORDER}; border-radius: 8px; }}"
    )
    return f


def _lbl(text: str, muted=True, bold=False, size=13) -> QLabel:
    l = QLabel(text)
    l.setStyleSheet(
        f"color: {'#6b7280' if muted else _TEXT}; font-size: {size}px; "
        f"font-weight: {'bold' if bold else 'normal'}; background: transparent; border: none;"
    )
    return l


def _field(placeholder: str = "", h: int = 38) -> QLineEdit:
    w = QLineEdit()
    w.setPlaceholderText(placeholder)
    w.setStyleSheet(_INPUT)
    w.setFixedHeight(h)
    return w

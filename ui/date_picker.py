"""
EctoDateEdit — fully custom date picker, consistent on Windows and macOS.
Drop-in replacement for QDateEdit + setCalendarPopup(True).

The day-number grid is drawn with QPainter instead of QPushButton widgets.
This completely bypasses Qt's stylesheet cascade, so the app's global dark
QPushButton rule (color: #F0F6FA) never touches the calendar cells.

Public API mirrors QDateEdit:
    date()                  -> QDate
    setDate(QDate)
    setEnabled(bool)
    setFixedHeight(int)
    setFixedWidth(int)
    setDisplayFormat(str)   # no-op, always dd/MM/yyyy
    setCalendarPopup(bool)  # no-op, always a popup
    setStyleSheet(str)      # absorbed — widget manages its own style
    dateChanged             # pyqtSignal(QDate)
"""
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QLineEdit
from PyQt5.QtCore import Qt, QDate, pyqtSignal
from PyQt5.QtGui import QPainter, QPen, QColor, QFont

# ── palette (all hardcoded — no stylesheet involvement in the grid) ────────────
_WHITE   = '#ffffff'
_BORDER  = '#d1d5db'
_BG_HDR  = '#f8f9fa'
_TEXT    = '#111827'
_MUTED   = '#9ca3af'
_ACCENT  = '#2596BE'

# ── EctoDateEdit field style ──────────────────────────────────────────────────
_FIELD_STYLE = f"""
    QLineEdit {{
        background-color: {_WHITE};
        color: {_TEXT};
        border: 1px solid {_BORDER};
        border-right: none;
        border-radius: 4px 0 0 4px;
        padding: 2px 6px;
        font-size: 12px;
    }}
    QLineEdit:disabled {{
        background-color: #f9fafb;
        color: {_MUTED};
    }}
"""

_BTN_STYLE = f"""
    QPushButton {{
        background-color: {_WHITE};
        color: {_MUTED};
        border: 1px solid {_BORDER};
        border-radius: 0 4px 4px 0;
        font-size: 13px;
        padding: 0 3px;
    }}
    QPushButton:hover {{
        background-color: #f3f4f6;
        color: {_ACCENT};
    }}
    QPushButton:disabled {{
        background-color: #f9fafb;
        color: #d1d5db;
    }}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Custom-painted calendar grid — bypasses Qt stylesheet cascade entirely
# ─────────────────────────────────────────────────────────────────────────────

class _CalendarGrid(QWidget):
    """6×7 grid of day cells drawn with QPainter. No QPushButton — no style bleed."""

    date_clicked = pyqtSignal(QDate)

    _CELL = 34   # px per cell
    _ROWS = 6
    _COLS = 7

    # Colors as QColor objects — explicitly set on QPainter, ignoring QSS
    C_TEXT   = QColor(_TEXT)
    C_MUTED  = QColor(_MUTED)
    C_HOVER  = QColor('#e5e7eb')
    C_ACCENT = QColor(_ACCENT)
    C_WHITE  = QColor(_WHITE)
    C_SEL_BG = QColor(_ACCENT)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cells: list = []     # list of (QDate, is_other_month: bool)
        self._selected = QDate()
        self._today    = QDate.currentDate()
        self._hover    = -1
        self.setMouseTracking(True)
        self.setFixedSize(self._COLS * self._CELL, self._ROWS * self._CELL)
        # Force white background regardless of inherited palette
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(self.backgroundRole(), QColor(_WHITE))
        self.setPalette(pal)

    def set_month(self, displayed: QDate, selected: QDate):
        self._selected = selected
        self._cells = []

        first_wd  = displayed.dayOfWeek()   # 1 = Mon … 7 = Sun
        prev      = displayed.addMonths(-1)
        prev_days = prev.daysInMonth()

        # Previous-month filler
        for i in range(first_wd - 1):
            d = QDate(prev.year(), prev.month(), prev_days - (first_wd - 2 - i))
            self._cells.append((d, True))

        # Current month
        for day in range(1, displayed.daysInMonth() + 1):
            self._cells.append((QDate(displayed.year(), displayed.month(), day), False))

        # Next-month filler to complete the 6×7 grid
        nxt, nd = displayed.addMonths(1), 1
        while len(self._cells) < self._ROWS * self._COLS:
            self._cells.append((QDate(nxt.year(), nxt.month(), nd), True))
            nd += 1

        self._hover = -1
        self.update()

    # ── painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)

        r = self._CELL
        font = QFont()
        font.setPixelSize(12)

        for i, (date, other) in enumerate(self._cells):
            col = i % self._COLS
            row = i // self._COLS
            x, y   = col * r, row * r
            cx, cy = x + r // 2, y + r // 2
            radius = r // 2 - 2

            is_sel   = (date == self._selected)
            is_today = (date == self._today)
            is_hover = (i == self._hover) and not is_sel

            # ── background circle ──────────────────────────────────────────
            if is_sel:
                p.setPen(Qt.NoPen)
                p.setBrush(self.C_SEL_BG)
                p.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)
            elif is_today:
                p.setPen(QPen(self.C_ACCENT, 2))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)
            elif is_hover:
                p.setPen(Qt.NoPen)
                p.setBrush(self.C_HOVER)
                p.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)

            # ── day number text ────────────────────────────────────────────
            font.setBold(is_sel or is_today)
            p.setFont(font)

            if is_sel:
                p.setPen(self.C_WHITE)
            elif is_today:
                p.setPen(self.C_ACCENT)
            elif other:
                p.setPen(self.C_MUTED)
            else:
                p.setPen(self.C_TEXT)

            p.drawText(x, y, r, r, Qt.AlignCenter, str(date.day()))

        p.end()

    # ── interaction ───────────────────────────────────────────────────────────

    def mouseMoveEvent(self, event):
        idx = self._cell_at(event.pos())
        if idx != self._hover:
            self._hover = idx
            self.update()
        self.setCursor(Qt.PointingHandCursor if idx >= 0 else Qt.ArrowCursor)

    def leaveEvent(self, _):
        if self._hover != -1:
            self._hover = -1
            self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            idx = self._cell_at(event.pos())
            if 0 <= idx < len(self._cells):
                self.date_clicked.emit(self._cells[idx][0])

    def _cell_at(self, pos) -> int:
        col = pos.x() // self._CELL
        row = pos.y() // self._CELL
        if 0 <= col < self._COLS and 0 <= row < self._ROWS:
            return row * self._COLS + col
        return -1


# ─────────────────────────────────────────────────────────────────────────────
# Calendar popup window
# ─────────────────────────────────────────────────────────────────────────────

class _EctoCalendarPopup(QWidget):
    date_selected = pyqtSignal(QDate)

    _CELL     = _CalendarGrid._CELL
    _GRID_W   = _CalendarGrid._COLS * _CalendarGrid._CELL   # 238
    _GRID_H   = _CalendarGrid._ROWS * _CalendarGrid._CELL   # 204
    _NAV_H    = 36
    _DOW_H    = 22
    _PAD      = 10

    def __init__(self, selected: QDate, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        # Force white background and dark text for nav buttons/labels.
        # The grid itself uses QPainter — no stylesheet involved there.
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {_WHITE};
                color: {_TEXT};
                border: none;
            }}
            QPushButton {{
                background: transparent;
                color: {_TEXT};
                border: none;
                border-radius: 14px;
                font-size: 18px;
                font-weight: bold;
                padding: 0;
            }}
            QPushButton:hover {{
                background: #e5e7eb;
            }}
        """)

        self._selected  = selected if (selected and selected.isValid()) else QDate.currentDate()
        self._displayed = QDate(self._selected.year(), self._selected.month(), 1)

        total_w = self._GRID_W + self._PAD * 2
        total_h = self._NAV_H + self._DOW_H + self._GRID_H + self._PAD * 2
        self.setFixedSize(total_w, total_h)
        self._build()

    def paintEvent(self, _):
        """Outer 1-px border (not via stylesheet to avoid child bleed)."""
        p = QPainter(self)
        p.setPen(QPen(QColor(_BORDER), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        p.end()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(self._PAD, self._PAD, self._PAD, self._PAD)
        outer.setSpacing(4)

        # ── Navigation row ────────────────────────────────────────────────
        nav = QHBoxLayout(); nav.setSpacing(0)

        self._prev = QPushButton('‹')
        self._prev.setFixedSize(28, 28)
        self._prev.setCursor(Qt.PointingHandCursor)
        self._prev.clicked.connect(self._go_prev)

        self._month_lbl = QLabel()
        self._month_lbl.setAlignment(Qt.AlignCenter)
        self._month_lbl.setStyleSheet(
            f'color: {_TEXT}; font-size: 13px; font-weight: bold; background: transparent; border: none;'
        )

        self._next = QPushButton('›')
        self._next.setFixedSize(28, 28)
        self._next.setCursor(Qt.PointingHandCursor)
        self._next.clicked.connect(self._go_next)

        nav.addWidget(self._prev)
        nav.addStretch()
        nav.addWidget(self._month_lbl)
        nav.addStretch()
        nav.addWidget(self._next)
        outer.addLayout(nav)

        # ── Day-of-week header ────────────────────────────────────────────
        dow = QHBoxLayout(); dow.setSpacing(0); dow.setContentsMargins(0, 0, 0, 0)
        for name in ('Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'):
            lbl = QLabel(name)
            lbl.setFixedSize(self._CELL, self._DOW_H)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(
                f'color: {_MUTED}; font-size: 11px; font-weight: 600; background: transparent; border: none;'
            )
            dow.addWidget(lbl)
        outer.addLayout(dow)

        # ── Custom-painted grid (no QPushButton) ──────────────────────────
        self._grid = _CalendarGrid()
        self._grid.date_clicked.connect(self._pick)
        outer.addWidget(self._grid)

        self._refresh_grid()

    def _refresh_grid(self):
        self._month_lbl.setText(self._displayed.toString('MMMM yyyy'))
        self._grid.set_month(self._displayed, self._selected)

    def _pick(self, date: QDate):
        self.date_selected.emit(date)
        self.close()

    def _go_prev(self):
        self._displayed = self._displayed.addMonths(-1)
        self._refresh_grid()

    def _go_next(self):
        self._displayed = self._displayed.addMonths(1)
        self._refresh_grid()


# ─────────────────────────────────────────────────────────────────────────────
# Public widget
# ─────────────────────────────────────────────────────────────────────────────

class EctoDateEdit(QWidget):
    """Custom date picker — consistent on Windows and macOS."""

    dateChanged = pyqtSignal(QDate)

    def __init__(self, date=None, parent=None):
        super().__init__(parent)
        self._date = (date if (date and date.isValid()) else QDate.currentDate())
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._line = QLineEdit(self._date.toString('dd/MM/yyyy'))
        self._line.setReadOnly(True)
        self._line.setStyleSheet(_FIELD_STYLE)
        self._line.setCursor(Qt.PointingHandCursor)
        self._line.mousePressEvent = lambda _e: self._open_popup()

        self._btn = QPushButton('▾')
        self._btn.setFixedWidth(22)
        self._btn.setStyleSheet(_BTN_STYLE)
        self._btn.setCursor(Qt.PointingHandCursor)
        self._btn.clicked.connect(self._open_popup)

        layout.addWidget(self._line)
        layout.addWidget(self._btn)

    def _open_popup(self):
        if not self.isEnabled():
            return
        popup = _EctoCalendarPopup(self._date, self)
        popup.date_selected.connect(self._on_picked)
        pos = self.mapToGlobal(self.rect().bottomLeft())
        popup.move(pos)
        popup.show()

    def _on_picked(self, date: QDate):
        old = self._date
        self._date = date
        self._line.setText(date.toString('dd/MM/yyyy'))
        if date != old:
            self.dateChanged.emit(date)

    # ── public API (mirrors QDateEdit) ────────────────────────────────────────

    def date(self) -> QDate:
        return self._date

    def setDate(self, date: QDate):
        if date and date.isValid():
            self._date = date
            self._line.setText(date.toString('dd/MM/yyyy'))

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        self._line.setEnabled(enabled)
        self._btn.setEnabled(enabled)

    def setFixedHeight(self, h: int):
        super().setFixedHeight(h)
        self._line.setFixedHeight(h)
        self._btn.setFixedHeight(h)

    def setFixedWidth(self, w: int):
        super().setFixedWidth(w)

    # No-ops for drop-in compatibility with QDateEdit call sites
    def setDisplayFormat(self, _fmt: str):      pass
    def setCalendarPopup(self, _on: bool):      pass
    def setStyleSheet(self, _style: str):       pass

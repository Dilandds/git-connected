"""
To Do List — calendar-based task manager with optional reminders.
"""
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Dict, Set

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QCheckBox, QLineEdit,
    QComboBox, QTextEdit, QSizePolicy, QApplication,
)
from PyQt5.QtCore import Qt, QTimer, QRectF, QPointF, QSize, pyqtSignal, QDate
from PyQt5.QtGui import QColor, QPainter, QBrush, QPen, QPixmap, QIcon

from ui.styles import default_theme, TOOLTIP_STYLE
from ui.modal_utils import FormModal
from i18n import t, get_language

_BG       = '#f4f6f9'
_CARD     = '#ffffff'
_CARD2    = '#f8fafc'
_TEXT     = '#1a2033'
_MUTED    = '#6b7280'
_ACCENT   = default_theme.button_primary
_ACCENT_H = default_theme.button_primary_hover
_BORDER   = '#e2e8f0'

_PRIORITY = {
    'low':    ('#22c55e', '#f0fdf4', '#bbf7d0'),   # (dot/border, bg, badge-bg)
    'medium': ('#f59e0b', '#fffbeb', '#fde68a'),
    'high':   ('#ef4444', '#fef2f2', '#fecaca'),
}


# ─── Data model ───────────────────────────────────────────────────────────────

@dataclass
class TodoTask:
    id: str
    title: str
    date: str           # 'YYYY-MM-DD'
    time: str = ''      # 'HH:MM' or ''
    reminder: int = 0   # 0=none, -1=at time, 15/30/60/1440=min before
    done: bool = False
    notes: str = ''
    priority: str = 'medium'  # 'low' | 'medium' | 'high'


# ─── Task dialog ──────────────────────────────────────────────────────────────

_REMINDER_OPTS = [
    ('todo.reminder_none',    0),
    ('todo.reminder_at_time', -1),
    ('todo.reminder_15min',   15),
    ('todo.reminder_30min',   30),
    ('todo.reminder_1hr',     60),
    ('todo.reminder_1day',    1440),
]


class TaskDialog(FormModal):
    def __init__(self, date_str: str = '', task: TodoTask = None, parent=None):
        label = t('todo.dlg_edit_task') if task else t('todo.dlg_add_task')
        super().__init__(parent, label, theme=FormModal.LIGHT)
        self._task = task
        self._date_str = date_str
        self._build()

    def _build(self):
        tk = self._task

        self._title_edit = QLineEdit(tk.title if tk else '')
        self._title_edit.setPlaceholderText(t('todo.task_title_ph'))
        self.add_field(t('todo.task_title'), self._title_edit)

        self._time_edit = QLineEdit(tk.time if tk else '')
        self._time_edit.setPlaceholderText(t('todo.task_time_ph'))
        self.add_field(t('todo.task_time'), self._time_edit)

        self._priority_combo = QComboBox()
        for key, val in [
            ('todo.priority_low', 'low'),
            ('todo.priority_medium', 'medium'),
            ('todo.priority_high', 'high'),
        ]:
            self._priority_combo.addItem(t(key), val)
        current_priority = tk.priority if tk else 'medium'
        for i in range(self._priority_combo.count()):
            if self._priority_combo.itemData(i) == current_priority:
                self._priority_combo.setCurrentIndex(i)
                break
        self.add_field(t('todo.task_priority'), self._priority_combo)

        self._reminder_combo = QComboBox()
        for key, val in _REMINDER_OPTS:
            self._reminder_combo.addItem(t(key), val)
        if tk:
            for i, (_, val) in enumerate(_REMINDER_OPTS):
                if val == tk.reminder:
                    self._reminder_combo.setCurrentIndex(i)
                    break
        self.add_field(t('todo.task_reminder'), self._reminder_combo)

        self._notes_edit = QTextEdit(tk.notes if tk else '')
        self._notes_edit.setPlaceholderText(t('todo.task_notes_ph'))
        self._notes_edit.setFixedHeight(80)
        self.add_field(t('todo.task_notes'), self._notes_edit)

        self.finish(ok=t('common.save'), cancel=t('common.cancel'))

    def get_result(self) -> dict:
        return {
            'title':    self._title_edit.text().strip(),
            'time':     self._time_edit.text().strip(),
            'priority': self._priority_combo.currentData(),
            'reminder': self._reminder_combo.currentData(),
            'notes':    self._notes_edit.toPlainText().strip(),
        }


# ─── Notification bubble ──────────────────────────────────────────────────────

class NotificationBubble(QWidget):
    """Frameless toast that appears top-right of the screen for ~6 seconds."""

    def __init__(self, title: str, body: str):
        super().__init__(None,
                         Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(320, 84)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 12, 16, 12)
        root.setSpacing(4)

        lbl_title = QLabel(f'<b>{title}</b>')
        lbl_title.setStyleSheet('color: white; font-size: 13px;')
        root.addWidget(lbl_title)

        lbl_body = QLabel(body)
        lbl_body.setWordWrap(True)
        lbl_body.setStyleSheet('color: #b0c4de; font-size: 12px;')
        root.addWidget(lbl_body)

        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 340, 44)
        self.show()
        QTimer.singleShot(6000, self.close)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QBrush(QColor('#1c2536')))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(self.rect(), 12, 12)
        p.setBrush(QBrush(QColor(_ACCENT)))
        p.drawRoundedRect(0, 0, 5, self.height(), 3, 3)


# ─── Custom calendar — date cell ─────────────────────────────────────────────

class _DateCell(QWidget):
    """Single day cell: paints number + coloured task dots via QPainter."""
    clicked = pyqtSignal(object)   # emits QDate

    def __init__(self, parent=None):
        super().__init__(parent)
        self._qdate   = None
        self._cur_mo  = True
        self._today   = False
        self._sel     = False
        self._weekend = False
        self._dots    = []   # list of (hex_color, done_bool)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(60)

    def configure(self, qdate, cur_mo, today, sel, weekend, dots):
        self._qdate, self._cur_mo = qdate, cur_mo
        self._today, self._sel    = today, sel
        self._weekend, self._dots = weekend, dots
        self.update()

    def paintEvent(self, _event):
        if self._qdate is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())

        if self._sel:
            p.setBrush(QBrush(QColor(_ACCENT)))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(r.adjusted(3, 3, -3, -3), 10, 10)
            txt = QColor('white')
        elif self._today:
            p.setBrush(QBrush(QColor(_ACCENT + '28')))
            p.setPen(QPen(QColor(_ACCENT), 1.5))
            p.drawRoundedRect(r.adjusted(3, 3, -3, -3), 10, 10)
            txt = QColor(_ACCENT)
        else:
            if not self._cur_mo:
                txt = QColor('#c8d0da')
            elif self._weekend:
                txt = QColor('#ef4444')
            else:
                txt = QColor(_TEXT)

        p.setPen(txt)
        f = p.font()
        f.setPixelSize(14)
        f.setBold(self._today or self._sel)
        p.setFont(f)
        p.drawText(
            QRectF(r.left(), r.top() + 10, r.width(), r.height() - 22),
            Qt.AlignHCenter | Qt.AlignTop,
            str(self._qdate.day()),
        )

        if self._dots:
            dr, gap = 3, 3
            n  = min(len(self._dots), 5)
            tw = n * (2 * dr) + (n - 1) * gap
            sx = r.center().x() - tw / 2 + dr
            cy = r.bottom() - 8
            p.setPen(Qt.NoPen)
            for i, (color, done) in enumerate(self._dots[:n]):
                if self._sel:
                    dc = QColor('white'); dc.setAlphaF(0.75)
                else:
                    dc = QColor('#c4cdd8' if done else color)
                p.setBrush(QBrush(dc))
                p.drawEllipse(QRectF(sx + i * (2*dr+gap) - dr, cy - dr, 2*dr, 2*dr))
        p.end()

    def mousePressEvent(self, _e):
        if self._qdate is not None:
            self.clicked.emit(self._qdate)


# ─── Custom calendar widget ───────────────────────────────────────────────────

class _CustomCalendar(QWidget):
    """Full-featured month calendar — pure PyQt5, no QCalendarWidget."""
    selectionChanged = pyqtSignal()
    clicked          = pyqtSignal(object)   # QDate

    _MONTHS_EN = ['January','February','March','April','May','June',
                  'July','August','September','October','November','December']
    _DAYS_EN   = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
    _MONTHS_FR = ['Janvier','Février','Mars','Avril','Mai','Juin',
                  'Juillet','Août','Septembre','Octobre','Novembre','Décembre']
    _DAYS_FR   = ['Lun','Mar','Mer','Jeu','Ven','Sam','Dim']

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tasks: Dict[str, list] = {}
        self._today    = QDate.currentDate()
        self._selected = QDate.currentDate()
        self._year     = self._today.year()
        self._month    = self._today.month()
        self._cells: list = []
        if get_language() == 'fr':
            self._MONTHS = self._MONTHS_FR
            self._DAYS   = self._DAYS_FR
        else:
            self._MONTHS = self._MONTHS_EN
            self._DAYS   = self._DAYS_EN
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Navigation bar
        nav = QFrame()
        nav.setObjectName('cal_nav')
        nav.setStyleSheet(f'QFrame#cal_nav {{ background: {_ACCENT}; border-radius: 12px 12px 0 0; }}')
        nav_row = QHBoxLayout(nav)
        nav_row.setContentsMargins(14, 10, 14, 10)
        nav_row.setSpacing(6)

        _btn_ss = f"""
            QPushButton {{
                background: transparent; color: white; border: none;
                font-size: 22px; font-weight: bold; border-radius: 6px; padding: 0 4px;
            }}
            QPushButton:hover {{ background: rgba(255,255,255,0.2); }}
        """
        self._prev_btn = QPushButton('‹')
        self._prev_btn.setFixedSize(34, 34)
        self._prev_btn.setCursor(Qt.PointingHandCursor)
        self._prev_btn.setStyleSheet(_btn_ss)
        self._prev_btn.clicked.connect(self._go_prev)

        self._next_btn = QPushButton('›')
        self._next_btn.setFixedSize(34, 34)
        self._next_btn.setCursor(Qt.PointingHandCursor)
        self._next_btn.setStyleSheet(_btn_ss)
        self._next_btn.clicked.connect(self._go_next)

        self._hdr_lbl = QLabel()
        self._hdr_lbl.setStyleSheet(
            'color: white; font-size: 15px; font-weight: bold; background: transparent;'
        )

        nav_row.addWidget(self._prev_btn)
        nav_row.addStretch()
        nav_row.addWidget(self._hdr_lbl)
        nav_row.addStretch()
        nav_row.addWidget(self._next_btn)
        root.addWidget(nav)

        # Day-name header row
        day_row = QWidget()
        day_row.setStyleSheet(f'background: {_CARD};')
        day_hl = QHBoxLayout(day_row)
        day_hl.setContentsMargins(10, 10, 10, 6)
        day_hl.setSpacing(0)
        for i, name in enumerate(self._DAYS):
            lbl = QLabel(name)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(
                f'color: {"#ef4444" if i >= 5 else _MUTED};'
                f' font-size: 12px; font-weight: 600; background: transparent;'
            )
            day_hl.addWidget(lbl, 1)
        root.addWidget(day_row)

        # Cell grid
        grid_w = QWidget()
        grid_w.setStyleSheet(f'background: {_CARD}; border-radius: 0 0 12px 12px;')
        self._grid = QGridLayout(grid_w)
        self._grid.setContentsMargins(8, 4, 8, 10)
        self._grid.setSpacing(2)
        for row in range(6):
            for col in range(7):
                cell = _DateCell()
                cell.clicked.connect(self._on_cell_clicked)
                self._cells.append(cell)
                self._grid.addWidget(cell, row, col)
        root.addWidget(grid_w, 1)

        self._refresh_grid()

    def _refresh_grid(self):
        self._hdr_lbl.setText(f'{self._MONTHS[self._month - 1]}   {self._year}')
        first  = QDate(self._year, self._month, 1)
        cur    = first.addDays(-(first.dayOfWeek() - 1))
        for i, cell in enumerate(self._cells):
            col    = i % 7
            is_cur = (cur.month() == self._month and cur.year() == self._year)
            cell.configure(
                qdate   = cur,
                cur_mo  = is_cur,
                today   = (cur == self._today),
                sel     = (cur == self._selected),
                weekend = col >= 5,
                dots    = self._tasks.get(cur.toString('yyyy-MM-dd'), []),
            )
            cur = cur.addDays(1)

    def _on_cell_clicked(self, qdate):
        old = self._selected
        self._selected = qdate
        if qdate.month() != self._month or qdate.year() != self._year:
            self._year  = qdate.year()
            self._month = qdate.month()
        self._refresh_grid()
        if old != self._selected:
            self.selectionChanged.emit()
        self.clicked.emit(qdate)

    def _go_prev(self):
        self._month -= 1
        if self._month < 1:
            self._month, self._year = 12, self._year - 1
        self._refresh_grid()

    def _go_next(self):
        self._month += 1
        if self._month > 12:
            self._month, self._year = 1, self._year + 1
        self._refresh_grid()

    def selectedDate(self):
        return self._selected

    def refresh(self, tasks: dict):
        self._tasks = {}
        for task in tasks.values():
            self._tasks.setdefault(task.date, []).append(
                (_PRIORITY[task.priority][0], task.done)
            )
        self._refresh_grid()

    def setVerticalHeaderFormat(self, _):
        pass


# ─── Custom check button ──────────────────────────────────────────────────────

class _CheckButton(QPushButton):
    """Toggleable button that paints a rounded checkbox with a clear checkmark."""

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(22, 22)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet('border: none; background: transparent;')

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1.5, 1.5, 19, 19)

        if self.isChecked():
            p.setBrush(QBrush(QColor(_ACCENT)))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(r, 5, 5)
            # White checkmark
            pen = QPen(QColor('white'), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            p.setPen(pen)
            p.drawLine(QPointF(5.5, 11.5), QPointF(9.0, 15.0))
            p.drawLine(QPointF(9.0, 15.0), QPointF(16.5, 7.0))
        else:
            p.setBrush(QBrush(QColor('#ffffff')))
            p.setPen(QPen(QColor('#c4cdd8'), 1.8))
            p.drawRoundedRect(r, 5, 5)


# ─── Task row ─────────────────────────────────────────────────────────────────

class _TaskRow(QFrame):
    edit_requested   = pyqtSignal(str)
    delete_requested = pyqtSignal(str)
    done_toggled     = pyqtSignal(str, bool)

    def __init__(self, task: TodoTask, parent=None):
        super().__init__(parent)
        self._task = task
        self._build()

    def _build(self):
        p_color, p_bg, p_badge = _PRIORITY.get(
            self._task.priority, _PRIORITY['medium']
        )
        self.setStyleSheet(f"""
            QFrame {{
                background: {_CARD};
                border-radius: 8px;
                border-top: 1px solid {_BORDER};
                border-right: 1px solid {_BORDER};
                border-bottom: 1px solid {_BORDER};
                border-left: 3px solid {p_color};
            }}
        """)
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 10, 10)
        row.setSpacing(12)

        cb = _CheckButton(checked=self._task.done)
        cb.toggled.connect(lambda v: self.done_toggled.emit(self._task.id, v))
        row.addWidget(cb)
        self._check_btn = cb

        info_col = QVBoxLayout()
        info_col.setSpacing(3)

        # Title row: text + priority badge
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        strikethrough = 'text-decoration: line-through;' if self._task.done else ''
        color = '#a0aab4' if self._task.done else _TEXT
        lbl_title = QLabel(self._task.title)
        lbl_title.setStyleSheet(
            f'background: transparent; color: {color}; font-size: 13px;'
            f' font-weight: 600; {strikethrough}'
        )
        title_row.addWidget(lbl_title)

        badge = QLabel(t(f'todo.priority_{self._task.priority}').upper())
        badge.setStyleSheet(
            f'background: {p_badge}; color: {p_color};'
            f' border-radius: 3px; padding: 1px 6px;'
            f' font-size: 9px; font-weight: bold;'
        )
        badge.setFixedHeight(16)
        title_row.addWidget(badge)
        title_row.addStretch()
        info_col.addLayout(title_row)

        meta_parts = []
        if self._task.time:
            meta_parts.append(f'🕐 {self._task.time}')
        if self._task.reminder and self._task.reminder != 0:
            meta_parts.append('🔔')
        if meta_parts:
            lbl_meta = QLabel('   '.join(meta_parts))
            lbl_meta.setStyleSheet(
                f'background: transparent; color: {_MUTED}; font-size: 11px;'
            )
            info_col.addWidget(lbl_meta)

        row.addLayout(info_col, 1)

        self._action_btns = []
        for label, signal in [('Edit', self.edit_requested), ('Delete', self.delete_requested)]:
            btn = QPushButton(label)
            btn.setFixedHeight(24)
            btn.setCursor(Qt.PointingHandCursor)
            is_del = label == 'Delete'
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {'#fff5f5' if is_del else '#f1f5f9'};
                    color: {'#dc2626' if is_del else '#475569'};
                    border: 1px solid {'#fecaca' if is_del else '#cbd5e1'};
                    font-size: 11px;
                    font-weight: 600;
                    border-radius: 5px;
                    padding: 1px 10px;
                }}
                QPushButton:hover {{
                    background: {'#fee2e2' if is_del else '#e2e8f0'};
                    color: {'#b91c1c' if is_del else '#1e293b'};
                }}
            """)
            btn.clicked.connect(lambda _checked, s=signal: s.emit(self._task.id))
            row.addWidget(btn)
            self._action_btns.append(btn)

    def set_read_only(self, read_only: bool):
        """Locks the done-toggle checkbox and the Edit/Delete buttons; the
        row itself stays visible and readable."""
        enabled = not read_only
        self._check_btn.setEnabled(enabled)
        for btn in self._action_btns:
            btn.setEnabled(enabled)


# ─── Day panel (right side) ───────────────────────────────────────────────────

class _DayPanel(QWidget):
    changed = pyqtSignal()

    _MONTHS_EN = ['January', 'February', 'March', 'April', 'May', 'June',
                  'July', 'August', 'September', 'October', 'November', 'December']
    _MONTHS_FR = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                  'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']
    _WEEKDAYS_EN = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    _WEEKDAYS_FR = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tasks: Dict[str, TodoTask] = {}
        self._date_str = ''
        self._read_only = False
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        hdr = QHBoxLayout()
        self._date_label = QLabel('')
        self._date_label.setStyleSheet(
            f'background: transparent; color: {_TEXT};'
            f' font-size: 16px; font-weight: bold; letter-spacing: 0.2px;'
        )
        hdr.addWidget(self._date_label, 1)

        btn_add = QPushButton(t('todo.add_task'))
        btn_add.setCursor(Qt.PointingHandCursor)
        btn_add.setStyleSheet(f"""
            QPushButton {{
                background: {_ACCENT}; color: white; border: none;
                border-radius: 6px; padding: 5px 14px; font-size: 12px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {_ACCENT_H}; }}
        """)
        btn_add.clicked.connect(self._add_task)
        hdr.addWidget(btn_add)
        root.addLayout(hdr)
        self._btn_add = btn_add

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setMaximumHeight(1)
        sep.setStyleSheet(f'background: {_BORDER}; border: none;')
        root.addWidget(sep)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet('background: transparent; border: none;')
        scroll.viewport().setStyleSheet('background: transparent;')

        self._list_container = QWidget()
        self._list_container.setStyleSheet('background: transparent; border: none;')
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 6, 0, 4)
        self._list_layout.setSpacing(8)

        scroll.setWidget(self._list_container)
        root.addWidget(scroll, 1)

    def set_date(self, date_str: str, tasks: Dict[str, TodoTask]):
        self._date_str = date_str
        self._tasks = tasks
        try:
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            # strftime('%A, %B %d') always renders in English regardless of
            # the app's language — build the header from our own translated
            # weekday/month names instead.
            if get_language() == 'fr':
                weekdays, months = self._WEEKDAYS_FR, self._MONTHS_FR
            else:
                weekdays, months = self._WEEKDAYS_EN, self._MONTHS_EN
            weekday_name = weekdays[dt.weekday()]
            month_name = months[dt.month - 1]
            self._date_label.setText(f'{weekday_name}, {month_name} {dt.day:02d}')
        except ValueError:
            self._date_label.setText(date_str)
        self._refresh()

    def _refresh(self):
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if w := item.widget():
                w.setParent(None)

        _P_ORDER = {'high': 0, 'medium': 1, 'low': 2}
        day_tasks = [tk for tk in self._tasks.values() if tk.date == self._date_str]
        day_tasks.sort(key=lambda tk: (tk.done, _P_ORDER.get(tk.priority, 1), tk.time or '99:99'))

        if not day_tasks:
            lbl = QLabel(t('todo.no_tasks'))
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f'background: transparent; color: {_MUTED}; font-size: 13px; padding: 40px;')
            self._list_layout.addWidget(lbl)
        else:
            for task in day_tasks:
                row = _TaskRow(task)
                row.edit_requested.connect(self._edit_task)
                row.delete_requested.connect(self._delete_task)
                row.done_toggled.connect(self._toggle_done)
                row.set_read_only(self._read_only)
                self._list_layout.addWidget(row)

        self._list_layout.addStretch()

    def set_read_only(self, read_only: bool):
        """Locks "Add task" and every currently-shown task row's
        done-toggle/Edit/Delete controls; the day panel's own scroll area
        (wrapping the task list) is left untouched. Applied to any task row
        created by a future _refresh() call too."""
        self._read_only = read_only
        self._btn_add.setEnabled(not read_only)
        for i in range(self._list_layout.count()):
            item = self._list_layout.itemAt(i)
            w = item.widget() if item else None
            if isinstance(w, _TaskRow):
                w.set_read_only(read_only)

    def open_add_dialog(self):
        # Defense in depth: TodoWidget._on_date_clicked already skips this
        # call while read-only (that's the fix for the calendar-click ->
        # add-dialog gotcha), but guard here too since this is a public
        # entry point other callers could reach directly.
        if self._read_only:
            return
        self._add_task()

    def _add_task(self):
        dlg = TaskDialog(date_str=self._date_str, parent=self)
        if dlg.exec_():
            data = dlg.get_result()
            if data['title']:
                task = TodoTask(id=str(uuid.uuid4()), date=self._date_str, **data)
                self._tasks[task.id] = task
                self._refresh()
                self.changed.emit()

    def _edit_task(self, task_id: str):
        task = self._tasks.get(task_id)
        if not task:
            return
        dlg = TaskDialog(date_str=self._date_str, task=task, parent=self)
        if dlg.exec_():
            data = dlg.get_result()
            if data['title']:
                task.title    = data['title']
                task.time     = data['time']
                task.priority = data['priority']
                task.reminder = data['reminder']
                task.notes    = data['notes']
                self._refresh()
                self.changed.emit()

    def _delete_task(self, task_id: str):
        self._tasks.pop(task_id, None)
        self._refresh()
        self.changed.emit()

    def _toggle_done(self, task_id: str, done: bool):
        if task_id in self._tasks:
            self._tasks[task_id].done = done
            self._refresh()
            self.changed.emit()


# ─── Main widget ──────────────────────────────────────────────────────────────

class TodoWidget(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tasks: Dict[str, TodoTask] = {}
        self._fired: Set[str] = set()
        self._bubbles = []
        self._read_only = False
        self._build_ui()
        self._start_timer()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(12)

        # ── Header ───────────────────────────────────────────────────
        lbl_title = QLabel(t('todo.title'))
        lbl_title.setStyleSheet(
            f'color: {_TEXT}; font-size: 22px; font-weight: bold; letter-spacing: 0.3px;'
        )
        root.addWidget(lbl_title)

        lbl_sub = QLabel(t('todo.subtitle'))
        lbl_sub.setStyleSheet(f'color: {_MUTED}; font-size: 13px;')
        root.addWidget(lbl_sub)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setMaximumHeight(1)
        sep.setStyleSheet(f'background: {_BORDER}; border: none;')
        root.addWidget(sep)

        # ── Content ──────────────────────────────────────────────────
        content = QHBoxLayout()
        content.setSpacing(20)

        # Calendar — custom widget, no wrapper card needed (it draws its own border)
        self._calendar = _CustomCalendar()
        self._calendar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._calendar.setMinimumWidth(380)
        self._calendar.selectionChanged.connect(self._on_date_selected)
        self._calendar.clicked.connect(self._on_date_clicked)
        content.addWidget(self._calendar, 3)

        # Day panel card
        panel_card = QFrame()
        panel_card.setStyleSheet(
            f'QFrame {{ background: {_CARD}; border-radius: 12px; border: 1px solid {_BORDER}; }}'
        )
        panel_inner = QVBoxLayout(panel_card)
        panel_inner.setContentsMargins(20, 18, 18, 18)

        self._day_panel = _DayPanel()
        self._day_panel.changed.connect(self._on_tasks_changed)
        self._day_panel.setMinimumWidth(260)
        self._day_panel.setStyleSheet('background: transparent;')
        panel_inner.addWidget(self._day_panel)
        content.addWidget(panel_card, 2)

        root.addLayout(content, 1)
        self._on_date_selected()

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_date_selected(self):
        date_str = self._calendar.selectedDate().toString('yyyy-MM-dd')
        self._day_panel.set_date(date_str, self._tasks)

    def _on_date_clicked(self, _qdate):
        # Gotcha: clicking ANY calendar day cell normally opens the "Add
        # Task" dialog immediately (see _CustomCalendar._on_cell_clicked ->
        # this slot), regardless of whether the selected date actually
        # changed. That's the mutating half of a day-cell click, so it's
        # skipped while read-only. selectionChanged -> _on_date_selected
        # (only emitted when the date changes) is a separate connection and
        # keeps firing normally, so the day panel still refreshes to show
        # whichever day was clicked — "check todos" keeps working.
        if self._read_only:
            return
        self._day_panel.open_add_dialog()

    def _on_tasks_changed(self):
        self._calendar.refresh(self._tasks)
        self.changed.emit()

    def set_read_only(self, read_only: bool):
        """Calendar day selection (prev/next month navigation, and
        selectionChanged -> the day panel refreshing to show that day's
        tasks) stays usable — only the calendar-click's "open Add Task
        dialog" side effect (see _on_date_clicked) and the day panel's own
        edit controls (Add task, per-task Edit/Delete/done-toggle) are
        locked."""
        self._read_only = read_only
        self._day_panel.set_read_only(read_only)

    # ── Reminder timer ────────────────────────────────────────────────────────

    def _start_timer(self):
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check_reminders)
        self._timer.start(60_000)

    def _check_reminders(self):
        now = datetime.now()
        for task in self._tasks.values():
            if task.done or task.reminder == 0 or task.id in self._fired:
                continue
            try:
                task_dt = datetime.strptime(
                    f'{task.date} {task.time or "09:00"}', '%Y-%m-%d %H:%M'
                )
            except ValueError:
                continue

            fire_at = task_dt if task.reminder == -1 \
                else task_dt - timedelta(minutes=task.reminder)

            if (fire_at.date() == now.date()
                    and fire_at.hour == now.hour
                    and fire_at.minute == now.minute):
                self._fired.add(task.id)
                self._show_notification(task)

    def _show_notification(self, task: TodoTask):
        body = task.title + (f'  —  {task.time}' if task.time else '')
        bubble = NotificationBubble(t('todo.notif_title'), body)
        self._bubbles.append(bubble)
        # Clean up closed bubbles periodically
        self._bubbles = [b for b in self._bubbles if b.isVisible()]

    # ── Persistence ───────────────────────────────────────────────────────────

    def get_data(self) -> dict:
        return {'tasks': [asdict(tk) for tk in self._tasks.values()]}

    def set_data(self, data: dict):
        self._tasks = {}
        for d in data.get('tasks', []):
            try:
                task = TodoTask(**d)
                self._tasks[task.id] = task
            except TypeError:
                pass
        self._calendar.refresh(self._tasks)
        self._on_date_selected()

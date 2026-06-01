"""
Timeline screen — Gantt-style project timeline with operators, operations and tasks.
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QSplitter, QDialog, QDialogButtonBox,
    QLineEdit, QTextEdit, QComboBox, QCheckBox, QDateEdit,
    QSizePolicy, QAbstractScrollArea
)
from PyQt5.QtCore import Qt, QDate, QRect, QRectF, QPoint, QPointF, pyqtSignal, QSize
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QFontMetrics,
    QPainterPath, QCursor
)
from ui.styles import default_theme, make_font, dropdown_arrow_url as _get_arrow
_ARROW_URL = _get_arrow()

logger = logging.getLogger(__name__)

# ── palette ───────────────────────────────────────────────────────────────────
# Content area is light-themed; toolbar/panel strips stay dark (_SIDEBAR)
_BG      = '#f8f9fa'
_CARD    = '#ffffff'
_BORDER  = '#e5e7eb'
_TEXT    = '#1e2430'
_MUTED   = '#6b7280'
_ACCENT  = default_theme.button_primary
_SIDEBAR = '#1c2029'

TASK_TYPES = {
    "Manufacturing":   "#3b82f6",
    "Modification":    "#8b5cf6",
    "Validation":      "#10b981",
    "Quality Control": "#f59e0b",
    "Delivery":        "#06b6d4",
    "Holidays":        "#6b7280",
    "Issue":           "#ef4444",
}
DEFAULT_TYPE = "Manufacturing"
URGENT_COLOR = "#ef4444"

ROW_H        = 36   # px per operation row
OP_HEADER_H  = 22   # px for the operator name mini-strip
HEADER_H     = 52   # date header height
OP_LABEL_W   = 150  # frozen left column
DAY_W_DAY    = 38   # px per day in Day view
DAY_W_WEEK   = 16   # px per day in Week view
DAY_W_MONTH  = 6    # px per day in Month view

# ── data classes ─────────────────────────────────────────────────────────────

@dataclass
class Task:
    id:                int
    name:              str
    start:             QDate
    end:               QDate
    task_type:         str = DEFAULT_TYPE
    is_urgent:         bool = False
    status:            str = "In progress"
    comments:          List[str] = field(default_factory=list)
    deadline:          Optional[QDate] = None
    duration_days:     int = 1
    project_manager:   str = ""
    technical_manager: str = ""
    contributors:      str = ""

    def __post_init__(self):
        self.duration_days = max(1, self.start.daysTo(self.end))


@dataclass
class Operation:
    id:    int
    name:  str
    tasks: List[Task] = field(default_factory=list)


@dataclass
class Operator:
    id:         int
    name:       str
    operations: List[Operation] = field(default_factory=list)


# ── helpers ───────────────────────────────────────────────────────────────────

def _today() -> QDate:
    return QDate.currentDate()


def _sample_data() -> List[Operator]:
    t = _today()
    op1 = Operator(1, "Operator 1", [
        Operation(1, "Operation 1", [
            Task(1, "Initial concept",     t.addDays(-10), t.addDays(-7),  "Modification"),
            Task(2, "3D Modification",     t.addDays(-4),  t.addDays(1),   "Modification"),
            Task(3, "Check and update",    t.addDays(3),   t.addDays(6),   "Validation"),
        ]),
        Operation(2, "Operation 2", [
            Task(4, "Factory production",  t.addDays(-6),  t.addDays(-2),  "Manufacturing"),
            Task(5, "Quality check",       t.addDays(0),   t.addDays(4),   "Quality Control"),
        ]),
        Operation(3, "Operation 3", [
            Task(6, "URGENT DELIVERY",     t.addDays(2),   t.addDays(5),   "Delivery", is_urgent=True),
        ]),
    ])
    op2 = Operator(2, "Operator 2", [
        Operation(4, "Operation 1", [
            Task(7, "Design review",       t.addDays(-8),  t.addDays(-3),  "Validation"),
            Task(8, "Prototype build",     t.addDays(1),   t.addDays(8),   "Manufacturing"),
        ]),
        Operation(5, "Operation 2", [
            Task(9, "Supplier sourcing",   t.addDays(-2),  t.addDays(6),   "Manufacturing"),
        ]),
    ])
    return [op1, op2]


# ── Gantt Canvas ─────────────────────────────────────────────────────────────

class GanttCanvas(QWidget):
    """Custom painted Gantt chart body + frozen left column."""

    task_clicked       = pyqtSignal(object)  # emits Task
    task_moved         = pyqtSignal()        # emits after a drag-drop
    task_edit_requested = pyqtSignal(object) # emits Task on double-click

    def __init__(self, parent=None):
        super().__init__(parent)
        self._operators: List[Operator] = []
        self._current_op_idx: int = -1
        self._view_mode: str = "Day"
        self._start_date: QDate = _today().addDays(-7)
        self._deadline: Optional[QDate] = None
        self._selected_task: Optional[Task] = None
        self._h_offset: int = 0
        # drag state
        self._dragging_task: Optional[Task] = None
        self._drag_start_x: int = 0
        self._drag_orig_start: Optional[QDate] = None
        self._drag_orig_end: Optional[QDate] = None
        self._drag_active: bool = False   # True once threshold exceeded
        self.setMouseTracking(True)
        self.setCursor(Qt.ArrowCursor)

    # ── public setters ────────────────────────────────────────────────────

    def set_operators(self, ops: List[Operator]):
        self._operators = ops
        self._recalc_size()
        self.update()

    def set_current_operator(self, idx: int):
        self._current_op_idx = idx
        self._recalc_size()
        self.update()

    def set_view_mode(self, mode: str):
        self._view_mode = mode
        self._recalc_size()
        self.update()

    def set_h_offset(self, px: int):
        self._h_offset = px
        self.update()

    def set_deadline(self, date: Optional[QDate]):
        self._deadline = date
        self.update()

    # ── sizing ────────────────────────────────────────────────────────────

    def _day_w(self) -> int:
        return {"Day": DAY_W_DAY, "Week": DAY_W_WEEK, "Month": DAY_W_MONTH}.get(self._view_mode, DAY_W_DAY)

    def _visible_operators(self) -> List[Operator]:
        if self._current_op_idx == -1:
            return self._operators
        if 0 <= self._current_op_idx < len(self._operators):
            return [self._operators[self._current_op_idx]]
        return []

    def _total_content_h(self) -> int:
        """Total pixel height of all operator strips (header + operation rows)."""
        return sum(OP_HEADER_H + len(op.operations) * ROW_H
                   for op in self._visible_operators())

    def _total_days(self) -> int:
        return 90

    def _recalc_size(self):
        w = OP_LABEL_W + self._total_days() * self._day_w()
        h = HEADER_H + self._total_content_h() + 20
        self.setMinimumSize(w, max(h, 300))

    def sizeHint(self) -> QSize:
        return QSize(
            OP_LABEL_W + self._total_days() * self._day_w(),
            HEADER_H + self._total_content_h() + 20,
        )

    # ── paint ─────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)

        w = self.width()
        h = self.height()
        day_w = self._day_w()

        # Background
        p.fillRect(0, 0, w, h, QColor(_BG))

        # Date header
        self._draw_header(p, day_w)

        # Rows — use pixel y_pos instead of row index
        y_pos = 0
        for op in self._visible_operators():
            y_pos = self._draw_operator(p, op, y_pos, day_w)

        # Deadline line
        if self._deadline:
            self._draw_deadline(p, day_w)

        # Frozen left column overdraw — only cover content height, not full canvas
        content_h = self._total_content_h()
        p.fillRect(0, HEADER_H, OP_LABEL_W, content_h, QColor(_BG))

        # Left column labels
        y_pos = 0
        for op in self._visible_operators():
            y_pos = self._draw_operator_labels(p, op, y_pos)

        # Header label overlay
        self._draw_header_left(p)

        # Vertical divider
        p.setPen(QPen(QColor(_BORDER), 1))
        p.drawLine(OP_LABEL_W, 0, OP_LABEL_W, h)

        p.end()

    def _x_for_date(self, date: QDate, day_w: int) -> int:
        return OP_LABEL_W + self._start_date.daysTo(date) * day_w

    def _draw_header(self, p: QPainter, day_w: int):
        p.fillRect(0, 0, self.width(), HEADER_H, QColor('#e8eaed'))
        p.setPen(QPen(QColor(_BORDER), 1))
        p.drawLine(0, HEADER_H, self.width(), HEADER_H)

        font_week = make_font(size=9, bold=True)
        font_day  = make_font(size=8)
        p.setFont(font_week)

        date = self._start_date
        for _ in range(self._total_days()):
            x = self._x_for_date(date, day_w)
            if x < OP_LABEL_W:
                date = date.addDays(1)
                continue

            # Week label on Monday
            if date.dayOfWeek() == 1 or date == self._start_date:
                week_rect = QRect(x, 4, day_w * 7, 20)
                p.setPen(QColor(_TEXT))
                p.setFont(font_week)
                p.drawText(week_rect, Qt.AlignLeft | Qt.AlignVCenter,
                           f"W{date.weekNumber()[0]}  {date.toString('d MMM')}")

            # Day column grid line
            p.setPen(QPen(QColor(_BORDER), 1))
            p.drawLine(x, HEADER_H - 16, x, HEADER_H)

            # Day number
            if day_w >= DAY_W_DAY:
                day_rect = QRect(x + 2, HEADER_H - 16, day_w - 4, 14)
                p.setPen(QColor(_MUTED))
                p.setFont(font_day)
                label = date.toString("d")
                # highlight today
                if date == _today():
                    p.fillRect(x + 1, HEADER_H - 17, day_w - 2, 16, QColor(_ACCENT).darker(140))
                    p.setPen(QColor(_ACCENT))
                p.drawText(day_rect, Qt.AlignCenter, label)

            date = date.addDays(1)

        # "Today" vertical highlight in body
        tx = self._x_for_date(_today(), day_w)
        if tx > OP_LABEL_W:
            p.setPen(QPen(QColor(_ACCENT), 1, Qt.DotLine))
            p.drawLine(tx, HEADER_H, tx, self.height())

    def _draw_header_left(self, p: QPainter):
        p.fillRect(0, 0, OP_LABEL_W, HEADER_H, QColor('#e8eaed'))
        p.setPen(QPen(QColor(_BORDER), 1))
        p.drawLine(0, HEADER_H, OP_LABEL_W, HEADER_H)
        p.setPen(QColor(_MUTED))
        p.setFont(make_font(size=9, bold=True))
        p.drawText(QRect(8, 0, OP_LABEL_W - 8, HEADER_H),
                   Qt.AlignLeft | Qt.AlignVCenter, "OPERATIONS")

    def _draw_operator(self, p: QPainter, op: Operator, y_pos: int, day_w: int) -> int:
        """Draw the Gantt body for one operator. Returns updated y_pos."""
        abs_y = HEADER_H + y_pos

        # Operator header strip (right side only — left column drawn separately)
        p.fillRect(OP_LABEL_W, abs_y, self.width() - OP_LABEL_W, OP_HEADER_H,
                   QColor('#e8f4fb'))
        p.setPen(QPen(QColor(_BORDER), 1))
        p.drawLine(OP_LABEL_W, abs_y + OP_HEADER_H - 1,
                   self.width(), abs_y + OP_HEADER_H - 1)

        y_pos += OP_HEADER_H

        for i, oper in enumerate(op.operations):
            oy = HEADER_H + y_pos
            # Alternating stripe
            if i % 2 == 0:
                p.fillRect(OP_LABEL_W, oy, self.width() - OP_LABEL_W, ROW_H,
                           QColor('#f6f8fa'))
            # Row separator
            p.setPen(QPen(QColor(_BORDER), 1))
            p.drawLine(OP_LABEL_W, oy + ROW_H - 1, self.width(), oy + ROW_H - 1)
            # Task blocks
            for task in oper.tasks:
                self._draw_task_block(p, task, oy, day_w)
            y_pos += ROW_H

        return y_pos

    def _draw_task_block(self, p: QPainter, task: Task, row_y: int, day_w: int):
        x = self._x_for_date(task.start, day_w)
        w = max(task.start.daysTo(task.end) * day_w, day_w)
        y = row_y + 5
        h = ROW_H - 10
        if x + w < OP_LABEL_W:
            return

        color = QColor(URGENT_COLOR if task.is_urgent else TASK_TYPES.get(task.task_type, _ACCENT))
        is_sel = task is self._selected_task

        # Shadow
        p.fillRect(x + 2, y + 2, w, h, QColor(0, 0, 0, 60))

        # Block fill
        path = QPainterPath()
        path.addRoundedRect(QRectF(x, y, w, h), 4, 4)
        p.fillPath(path, QBrush(color if not is_sel else color.lighter(130)))

        # Selected border
        if is_sel:
            p.setPen(QPen(QColor("white"), 1.5))
            p.drawPath(path)

        # Urgent striping
        if task.is_urgent:
            p.save()
            p.setClipPath(path)
            stripe_pen = QPen(QColor(255, 255, 255, 40), 4, Qt.SolidLine)
            p.setPen(stripe_pen)
            for sx in range(x - h, x + w + h, 8):
                p.drawLine(sx, y, sx + h, y + h)
            p.restore()

        # Label
        if w > 24:
            p.setPen(QColor("white"))
            p.setFont(make_font(size=9, bold=task.is_urgent))
            text_rect = QRect(x + 5, y, w - 10, h)
            p.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft,
                       p.fontMetrics().elidedText(task.name, Qt.ElideRight, w - 10))

    def _draw_operator_labels(self, p: QPainter, op: Operator, y_pos: int) -> int:
        """Draw frozen left-column labels for one operator. Returns updated y_pos."""
        abs_y = HEADER_H + y_pos

        # ── Operator mini-header strip ──
        p.fillRect(0, abs_y, OP_LABEL_W, OP_HEADER_H, QColor('#dbeafe'))
        p.fillRect(0, abs_y, 3, OP_HEADER_H, QColor(_ACCENT))
        p.setPen(QColor('#1d4ed8'))
        p.setFont(make_font(size=9, bold=True))
        p.drawText(QRect(8, abs_y, OP_LABEL_W - 10, OP_HEADER_H),
                   Qt.AlignVCenter | Qt.AlignLeft, op.name.upper())
        p.setPen(QPen(QColor(_BORDER), 1))
        p.drawLine(0, abs_y + OP_HEADER_H - 1, OP_LABEL_W, abs_y + OP_HEADER_H - 1)

        y_pos += OP_HEADER_H

        # ── Operation rows ──
        for i, oper in enumerate(op.operations):
            oy = HEADER_H + y_pos
            if i % 2 == 0:
                p.fillRect(0, oy, OP_LABEL_W, ROW_H, QColor('#f6f8fa'))
            p.setPen(QPen(QColor(_BORDER), 1))
            p.drawLine(0, oy + ROW_H - 1, OP_LABEL_W, oy + ROW_H - 1)
            p.setPen(QColor(_TEXT))
            p.setFont(make_font(size=9))
            p.drawText(QRect(10, oy, OP_LABEL_W - 14, ROW_H),
                       Qt.AlignVCenter | Qt.AlignLeft, oper.name)
            y_pos += ROW_H

        return y_pos

    def _draw_deadline(self, p: QPainter, day_w: int):
        if not self._deadline:
            return
        x = self._x_for_date(self._deadline, day_w)
        pen = QPen(QColor("#ef4444"), 2, Qt.SolidLine)
        p.setPen(pen)
        p.drawLine(x, HEADER_H, x, self.height())
        # Label
        p.setPen(QColor("#ef4444"))
        p.setFont(make_font(size=8, bold=True))
        p.drawText(x + 3, HEADER_H + 12, "DEADLINE")

    # ── interaction ───────────────────────────────────────────────────────

    def _task_at(self, pos: QPoint) -> Optional[Task]:
        day_w = self._day_w()
        py = pos.y()
        if py < HEADER_H:
            return None
        # Walk operators using pixel Y — mirrors _draw_operator logic
        y_pos = 0
        for op in self._visible_operators():
            y_pos += OP_HEADER_H          # skip operator mini-header
            for oper in op.operations:
                oy = HEADER_H + y_pos
                if oy <= py < oy + ROW_H:
                    for task in oper.tasks:
                        x = self._x_for_date(task.start, day_w)
                        w = max(task.start.daysTo(task.end) * day_w, day_w)
                        if x <= pos.x() <= x + w:
                            return task
                y_pos += ROW_H
        return None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            task = self._task_at(event.pos())
            self._selected_task = task
            if task:
                self._dragging_task   = task
                self._drag_start_x    = event.pos().x()
                self._drag_orig_start = QDate(task.start)
                self._drag_orig_end   = QDate(task.end)
                self._drag_active     = False
                self.setCursor(Qt.OpenHandCursor)
                self.task_clicked.emit(task)
            self.update()

    def mouseMoveEvent(self, event):
        if self._dragging_task:
            dx = event.pos().x() - self._drag_start_x
            day_w = self._day_w()
            # activate drag only after moving more than half a day width
            if not self._drag_active and abs(dx) > max(day_w // 2, 4):
                self._drag_active = True
            if self._drag_active:
                delta = round(dx / day_w)
                self._dragging_task.start = self._drag_orig_start.addDays(delta)
                self._dragging_task.end   = self._drag_orig_end.addDays(delta)
                self._dragging_task.duration_days = max(
                    1, self._dragging_task.start.daysTo(self._dragging_task.end)
                )
                self.setCursor(Qt.ClosedHandCursor)
                self.update()
        else:
            task = self._task_at(event.pos())
            self.setCursor(Qt.OpenHandCursor if task else Qt.ArrowCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._dragging_task:
            moved = self._drag_active
            self._dragging_task = None
            self._drag_orig_start = None
            self._drag_orig_end = None
            self._drag_active = False
            self.setCursor(Qt.ArrowCursor)
            self.update()
            if moved:
                self.task_moved.emit()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            task = self._task_at(event.pos())
            if task:
                self.task_edit_requested.emit(task)


# ── Task form dialog ──────────────────────────────────────────────────────────

class TaskFormDialog(QDialog):
    """Form to add or edit a task.

    Pass `operations` when adding a new task so the user can pick which row
    to place it in.  Omit it (or pass None) when editing an existing task.
    """

    def __init__(self, task: Optional[Task] = None,
                 operations: Optional[List[Operation]] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Task" if task else "Add Task")
        self.setMinimumWidth(380)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {_CARD}; color: {_TEXT}; }}
            QLabel {{ color: {_TEXT}; font-size: 11px; background: transparent; border: none; }}
            QLineEdit, QTextEdit, QDateEdit {{
                background-color: #f5f6f8; color: {_TEXT};
                border: 1px solid {_BORDER}; border-radius: 4px;
                padding: 4px 8px; font-size: 11px;
            }}
            QLineEdit:focus, QTextEdit:focus, QDateEdit:focus {{
                border-color: {_ACCENT};
            }}
            QComboBox {{
                background-color: {_CARD}; color: {_TEXT};
                border: 1px solid {_BORDER}; border-radius: 5px;
                padding: 4px 28px 4px 8px; font-size: 11px;
            }}
            QComboBox:hover {{ border-color: #9ca3af; }}
            QComboBox:focus {{ border-color: {_ACCENT}; }}
            QComboBox::drop-down {{
                subcontrol-origin: padding; subcontrol-position: top right;
                width: 22px; background: #f1f3f5;
                border-left: 1px solid {_BORDER};
                border-top-right-radius: 5px; border-bottom-right-radius: 5px;
            }}
            QComboBox::down-arrow {{ image: url({_ARROW_URL}); width: 10px; height: 10px; }}
            QDateEdit::drop-down {{ border: none; width: 22px; }}
            QDateEdit::down-arrow {{ image: url({_ARROW_URL}); width: 10px; height: 10px; }}
            QComboBox QAbstractItemView {{
                background-color: {_CARD}; color: {_TEXT};
                border: 1px solid {_BORDER}; border-radius: 4px;
                outline: none; padding: 2px;
                selection-background-color: #dbeafe; selection-color: {_TEXT};
                font-size: 11px;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 5px 10px; min-height: 24px; border-radius: 3px;
            }}
            QComboBox QAbstractItemView::item:hover {{ background-color: #eff6ff; }}
            QComboBox QAbstractItemView::item:selected {{
                background-color: #dbeafe; font-weight: bold;
            }}
            QCheckBox {{ color: {_TEXT}; font-size: 11px; background: transparent; }}
            QDialogButtonBox QPushButton {{
                background-color: {_ACCENT}; color: white;
                border: none; border-radius: 5px;
                padding: 6px 16px; font-size: 11px; font-weight: bold;
            }}
            QDialogButtonBox QPushButton:hover {{ background-color: {default_theme.button_primary_hover}; }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        def row(label, widget):
            r = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setFixedWidth(100)
            r.addWidget(lbl)
            r.addWidget(widget, 1)
            layout.addLayout(r)

        # ── Operation selector (add mode only) ──
        self.f_operation: Optional[QComboBox] = None
        self._operations: List[Operation] = operations or []
        if operations:
            self.f_operation = QComboBox()
            for op in operations:
                self.f_operation.addItem(op.name)
            row("Operation", self.f_operation)

            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setStyleSheet(f"color: {_BORDER}; background: {_BORDER}; max-height: 1px; border: none;")
            layout.addWidget(sep)

        # ── Task fields ──
        self.f_name = QLineEdit(task.name if task else "")
        self.f_name.setPlaceholderText("Task name")
        row("Name", self.f_name)

        self.f_type = QComboBox()
        self.f_type.addItems(list(TASK_TYPES.keys()))
        if task:
            self.f_type.setCurrentText(task.task_type)
        row("Type", self.f_type)

        self.f_start = QDateEdit(task.start if task else _today())
        self.f_start.setDisplayFormat("dd/MM/yyyy")
        self.f_start.setCalendarPopup(True)
        row("Start", self.f_start)

        self.f_end = QDateEdit(task.end if task else _today().addDays(3))
        self.f_end.setDisplayFormat("dd/MM/yyyy")
        self.f_end.setCalendarPopup(True)
        row("End", self.f_end)

        self.f_status = QComboBox()
        self.f_status.addItems(["In progress", "Awaiting", "Completed", "Cancelled"])
        if task:
            self.f_status.setCurrentText(task.status)
        row("Status", self.f_status)

        self.f_urgent = QCheckBox("Mark as urgent")
        self.f_urgent.setChecked(task.is_urgent if task else False)
        layout.addWidget(self.f_urgent)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def selected_operation(self) -> Optional[Operation]:
        """Returns the chosen Operation when in add mode, else None."""
        if self.f_operation and self._operations:
            return self._operations[self.f_operation.currentIndex()]
        return None

    def get_task_data(self) -> dict:
        return {
            "name":      self.f_name.text().strip() or "New Task",
            "task_type": self.f_type.currentText(),
            "start":     self.f_start.date(),
            "end":       self.f_end.date(),
            "status":    self.f_status.currentText(),
            "is_urgent": self.f_urgent.isChecked(),
        }


# ── Bottom detail panel ───────────────────────────────────────────────────────

class TaskDetailPanel(QWidget):
    """Shows selected task details and comments in the bottom strip."""

    edit_requested   = pyqtSignal(object)  # emits current Task
    delete_requested = pyqtSignal(object)  # emits current Task

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_task: Optional[Task] = None
        self.setFixedHeight(140)
        self.setStyleSheet(f"""
            QWidget {{ background-color: {_CARD}; border-top: 1px solid {_BORDER}; }}
            QLabel {{ color: {_TEXT}; font-size: 10px; background: transparent; border: none; }}
            QTextEdit {{
                background-color: #f5f6f8; color: {_TEXT};
                border: 1px solid {_BORDER}; border-radius: 4px;
                font-size: 10px; padding: 4px;
            }}
        """)
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(16)

        # Task info column
        info_col = QVBoxLayout()
        info_col.setSpacing(3)
        self._lbl_task    = QLabel("Click a task to see details")
        self._lbl_task.setStyleSheet(f"color: {_TEXT}; font-size: 11px; font-weight: bold; background: transparent; border: none;")
        self._lbl_dates   = QLabel("")
        self._lbl_type    = QLabel("")
        self._lbl_status  = QLabel("")
        self._lbl_duration = QLabel("")
        for lbl in (self._lbl_task, self._lbl_dates, self._lbl_type, self._lbl_status, self._lbl_duration):
            info_col.addWidget(lbl)

        self._edit_btn = QPushButton("✎  Edit Task")
        self._edit_btn.setFixedHeight(24)
        self._edit_btn.setEnabled(False)
        self._edit_btn.setCursor(Qt.PointingHandCursor)
        self._edit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #e5e7eb; color: {_MUTED};
                border: 1px solid {_BORDER}; border-radius: 4px;
                font-size: 10px; padding: 2px 10px;
            }}
            QPushButton:enabled {{ color: {_TEXT}; border-color: #9ca3af; }}
            QPushButton:enabled:hover {{
                background-color: {_ACCENT}; color: white; border-color: {_ACCENT};
            }}
            QPushButton:disabled {{ color: #9ca3af; background-color: #f1f3f5; }}
        """)
        self._edit_btn.clicked.connect(lambda: self._current_task and self.edit_requested.emit(self._current_task))

        self._delete_btn = QPushButton("🗑  Remove Task")
        self._delete_btn.setFixedHeight(24)
        self._delete_btn.setEnabled(False)
        self._delete_btn.setCursor(Qt.PointingHandCursor)
        self._delete_btn.setStyleSheet(_BTN_DELETE)
        self._delete_btn.clicked.connect(
            lambda: self._current_task and self.delete_requested.emit(self._current_task)
        )

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        btn_row.addWidget(self._edit_btn)
        btn_row.addWidget(self._delete_btn)
        btn_row.addStretch()
        info_col.addLayout(btn_row)
        info_col.addStretch()
        layout.addLayout(info_col, 2)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet(f"color: {_BORDER}; background: {_BORDER}; max-width: 1px; border: none;")
        layout.addWidget(sep)

        # Comments column
        comment_col = QVBoxLayout()
        comment_col.setSpacing(4)

        comment_header = QHBoxLayout()
        comment_lbl = QLabel("COMMENTS")
        comment_lbl.setStyleSheet(f"color: {_MUTED}; font-size: 9px; font-weight: bold; background: transparent; border: none;")
        self._save_comment_btn = QPushButton("Save")
        self._save_comment_btn.setFixedHeight(22)
        self._save_comment_btn.setFixedWidth(54)
        self._save_comment_btn.setEnabled(False)
        self._save_comment_btn.setCursor(Qt.PointingHandCursor)
        self._save_comment_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_ACCENT};
                color: white; border: none;
                border-radius: 4px; font-size: 10px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {default_theme.button_primary_hover}; }}
            QPushButton:disabled {{
                background-color: #e5e7eb; color: #9ca3af;
            }}
        """)
        self._save_comment_btn.clicked.connect(self._save_comment)
        comment_header.addWidget(comment_lbl)
        comment_header.addStretch()
        comment_header.addWidget(self._save_comment_btn)

        self._comment_box = QTextEdit()
        self._comment_box.setPlaceholderText("Add a comment...")
        self._comment_box.setFixedHeight(72)
        self._comment_box.textChanged.connect(self._on_comment_changed)

        comment_col.addLayout(comment_header)
        comment_col.addWidget(self._comment_box)
        layout.addLayout(comment_col, 3)

        # Project meta column — editable per-task fields
        meta_col = QVBoxLayout()
        meta_col.setSpacing(5)

        _field_style = f"""
            QLineEdit {{
                background-color: #f5f6f8; color: {_TEXT};
                border: 1px solid {_BORDER}; border-radius: 4px;
                padding: 2px 6px; font-size: 10px;
            }}
            QLineEdit:focus {{ border-color: {_ACCENT}; }}
            QLineEdit:disabled {{ background-color: #f1f3f5; color: #9ca3af; }}
        """

        def _meta_row(label_text: str) -> tuple:
            row = QHBoxLayout()
            row.setSpacing(4)
            lbl = QLabel(label_text)
            lbl.setFixedWidth(108)
            lbl.setStyleSheet(f"color: {_MUTED}; font-size: 10px; background: transparent; border: none;")
            inp = QLineEdit()
            inp.setPlaceholderText("—")
            inp.setFixedHeight(22)
            inp.setStyleSheet(_field_style)
            inp.setEnabled(False)
            row.addWidget(lbl)
            row.addWidget(inp)
            meta_col.addLayout(row)
            return inp

        self._f_pm      = _meta_row("Project Manager:")
        self._f_tm      = _meta_row("Technical Manager:")
        self._f_contrib = _meta_row("Contributors:")
        meta_col.addStretch()
        layout.addLayout(meta_col, 2)

    def _on_comment_changed(self):
        has_task = self._current_task is not None
        self._save_comment_btn.setEnabled(has_task)

    def _save_comment(self):
        if not self._current_task:
            return
        text = self._comment_box.toPlainText().strip()
        self._current_task.comments = [c for c in text.split("\n") if c.strip()]
        # Visual feedback — briefly change button text
        self._save_comment_btn.setText("✔")
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(1000, lambda: self._save_comment_btn.setText("Save"))

    def show_task(self, task: Task):
        self._current_task = task
        self._lbl_task.setText(task.name)
        self._lbl_dates.setText(
            f"{task.start.toString('d MMM yyyy')}  →  {task.end.toString('d MMM yyyy')}"
        )
        self._lbl_type.setText(f"Type: {task.task_type}" + ("  🔴 URGENT" if task.is_urgent else ""))
        self._lbl_status.setText(f"Status: {task.status}")
        days = task.start.daysTo(task.end)
        self._lbl_duration.setText(f"Duration: {days} day{'s' if days != 1 else ''}")
        self._comment_box.setPlainText("\n".join(task.comments))
        self._edit_btn.setEnabled(True)
        self._delete_btn.setEnabled(True)
        self._save_comment_btn.setEnabled(True)

        # Populate meta fields
        for field, value in (
            (self._f_pm,      task.project_manager),
            (self._f_tm,      task.technical_manager),
            (self._f_contrib, task.contributors),
        ):
            field.blockSignals(True)
            field.setText(value)
            field.setEnabled(True)
            field.blockSignals(False)

        # Wire changes back to task
        self._f_pm.textChanged.connect(lambda v: setattr(task, 'project_manager', v))
        self._f_tm.textChanged.connect(lambda v: setattr(task, 'technical_manager', v))
        self._f_contrib.textChanged.connect(lambda v: setattr(task, 'contributors', v))

    def clear(self):
        self._current_task = None
        self._edit_btn.setEnabled(False)
        self._delete_btn.setEnabled(False)
        self._save_comment_btn.setEnabled(False)
        self._lbl_task.setText("Click a task to see details")
        for lbl in (self._lbl_dates, self._lbl_type, self._lbl_status, self._lbl_duration):
            lbl.setText("")
        self._comment_box.clear()
        for f in (self._f_pm, self._f_tm, self._f_contrib):
            f.blockSignals(True)
            f.clear()
            f.setEnabled(False)
            f.blockSignals(False)


# ── Main Timeline Widget ──────────────────────────────────────────────────────

_BTN_VIEW_ACTIVE = f"""
    QPushButton {{
        background-color: {_ACCENT};
        color: white; border: none;
        border-radius: 4px; padding: 3px 10px; font-size: 10px; font-weight: bold;
    }}
"""
_BTN_VIEW_INACTIVE = f"""
    QPushButton {{
        background-color: #f1f3f5; color: {_MUTED};
        border: 1px solid {_BORDER};
        border-radius: 4px; padding: 3px 10px; font-size: 10px;
    }}
    QPushButton:hover {{ color: {_TEXT}; background-color: #e5e7eb; border-color: {_ACCENT}; }}
"""
_BTN_SMALL = f"""
    QPushButton {{
        background-color: #f1f3f5; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 4px;
        padding: 3px 8px; font-size: 10px;
    }}
    QPushButton:hover {{ background-color: #e5e7eb; border-color: {_ACCENT}; color: {_ACCENT}; }}
"""
_TAB_ACTIVE = f"""
    QPushButton {{
        background-color: {_ACCENT}; color: white;
        border: none; border-radius: 5px;
        padding: 5px 14px; font-size: 11px; font-weight: bold;
    }}
"""
_TAB_INACTIVE = f"""
    QPushButton {{
        background-color: transparent; color: {_MUTED};
        border: 1px solid {_BORDER}; border-radius: 5px;
        padding: 5px 14px; font-size: 11px;
    }}
    QPushButton:hover {{ color: {_TEXT}; border-color: {_ACCENT}; background-color: #e8f0fe; }}
"""
# Variants with flat right edge — used when a close "×" button is attached
_TAB_ACTIVE_L = _TAB_ACTIVE.replace("border-radius: 5px;", "border-radius: 5px 0 0 5px;")
_TAB_INACTIVE_L = (
    _TAB_INACTIVE
    .replace("border-radius: 5px;", "border-radius: 5px 0 0 5px;")
    .replace("border: 1px solid {_BORDER};", f"border: 1px solid {_BORDER}; border-right: none;")
)
_CLOSE_TAB_ACTIVE = f"""
    QPushButton {{
        background-color: {_ACCENT}; color: rgba(255,255,255,0.55);
        border: none; border-left: 1px solid rgba(255,255,255,0.18);
        border-radius: 0 5px 5px 0;
        font-size: 13px; font-weight: bold; padding: 0 5px;
    }}
    QPushButton:hover {{ color: white; background-color: #ef4444; border-left-color: transparent; }}
"""
_CLOSE_TAB_INACTIVE = f"""
    QPushButton {{
        background-color: transparent; color: {_MUTED};
        border: 1px solid {_BORDER}; border-left: none;
        border-radius: 0 5px 5px 0;
        font-size: 13px; font-weight: bold; padding: 0 5px;
    }}
    QPushButton:hover {{ color: #ef4444; background-color: #fee2e2; border-color: #fca5a5; border-left: none; }}
"""
_BTN_DELETE = f"""
    QPushButton {{
        background-color: #fee2e2; color: #ef4444;
        border: 1px solid #fca5a5; border-radius: 4px;
        font-size: 10px; padding: 2px 10px;
    }}
    QPushButton:hover {{ background-color: #ef4444; color: white; border-color: #ef4444; }}
    QPushButton:disabled {{ color: #9ca3af; background-color: #f1f3f5; border-color: {_BORDER}; }}
"""


class TimelineWidget(QWidget):
    """Full Timeline screen."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._operators: List[Operator] = _sample_data()
        self._current_tab: int = -1   # -1 = Overview
        self._view_mode: str = "Day"
        self._next_op_id = 10
        self._next_task_id = 20
        self.setStyleSheet(f"background-color: {_BG};")
        self._build_ui()
        self._refresh_tabs()
        self._switch_tab(-1)

    # ── build ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── top bar: title + add operator ──
        top = QWidget()
        top.setFixedHeight(46)
        top.setStyleSheet(f"background-color: {_BG}; border-bottom: 1px solid {_BORDER};")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(16, 0, 16, 0)
        title = QLabel("Timeline")
        title.setFont(make_font(size=15, bold=True))
        title.setStyleSheet(f"color: {_TEXT}; background: transparent; border: none;")
        subtitle = QLabel("Centralise project evolution, revisions and workflow actions.")
        subtitle.setStyleSheet(f"color: {_MUTED}; font-size: 10px; background: transparent; border: none;")
        t_col = QVBoxLayout()
        t_col.setSpacing(1)
        t_col.addWidget(title)
        t_col.addWidget(subtitle)
        top_layout.addLayout(t_col)
        top_layout.addStretch()
        add_op_btn = QPushButton("＋ Add Operator")
        add_op_btn.setStyleSheet(_BTN_SMALL)
        add_op_btn.setFixedHeight(28)
        add_op_btn.setCursor(Qt.PointingHandCursor)
        add_op_btn.clicked.connect(self._add_operator)
        top_layout.addWidget(add_op_btn)
        root.addWidget(top)

        # ── operator tabs ──
        self._tabs_bar = QWidget()
        self._tabs_bar.setStyleSheet(f"background-color: {_BG}; border-bottom: 2px solid {_BORDER};")
        self._tabs_bar.setFixedHeight(40)
        self._tabs_layout = QHBoxLayout(self._tabs_bar)
        self._tabs_layout.setContentsMargins(12, 5, 12, 5)
        self._tabs_layout.setSpacing(6)
        self._tabs_layout.addStretch()
        root.addWidget(self._tabs_bar)

        # ── legend + view controls ──
        controls = QWidget()
        controls.setFixedHeight(36)
        controls.setStyleSheet(f"background-color: {_CARD}; border-bottom: 1px solid {_BORDER};")
        ctrl_layout = QHBoxLayout(controls)
        ctrl_layout.setContentsMargins(12, 4, 12, 4)
        ctrl_layout.setSpacing(6)

        legend_lbl = QLabel("LEGEND:")
        legend_lbl.setStyleSheet(f"color: {_MUTED}; font-size: 9px; font-weight: bold; background: transparent; border: none;")
        ctrl_layout.addWidget(legend_lbl)

        for name, color in TASK_TYPES.items():
            dot = QLabel(f"● {name}")
            dot.setStyleSheet(f"color: {color}; font-size: 9px; background: transparent; border: none;")
            ctrl_layout.addWidget(dot)

        ctrl_layout.addStretch()

        # Date navigation
        prev_btn = QPushButton("◀")
        prev_btn.setFixedSize(24, 24)
        prev_btn.setStyleSheet(_BTN_SMALL)
        prev_btn.setCursor(Qt.PointingHandCursor)
        prev_btn.clicked.connect(lambda: self._shift_date(-14))

        self._date_lbl = QLabel()
        self._date_lbl.setStyleSheet(f"color: {_TEXT}; font-size: 10px; font-weight: bold; background: transparent; border: none;")
        self._update_date_label()

        next_btn = QPushButton("▶")
        next_btn.setFixedSize(24, 24)
        next_btn.setStyleSheet(_BTN_SMALL)
        next_btn.setCursor(Qt.PointingHandCursor)
        next_btn.clicked.connect(lambda: self._shift_date(14))

        ctrl_layout.addWidget(prev_btn)
        ctrl_layout.addWidget(self._date_lbl)
        ctrl_layout.addWidget(next_btn)
        ctrl_layout.addSpacing(8)

        # View mode
        self._view_btns: dict[str, QPushButton] = {}
        for mode in ("Day", "Week", "Month"):
            btn = QPushButton(mode)
            btn.setFixedHeight(24)
            btn.setStyleSheet(_BTN_VIEW_ACTIVE if mode == self._view_mode else _BTN_VIEW_INACTIVE)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, m=mode: self._set_view_mode(m))
            self._view_btns[mode] = btn
            ctrl_layout.addWidget(btn)

        root.addWidget(controls)

        # ── Gantt scroll area ──
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ background-color: {_BG}; border: none; }}
            QScrollBar:horizontal {{
                background: {_BG}; height: 8px; border-radius: 4px;
            }}
            QScrollBar::handle:horizontal {{
                background: {_BORDER}; border-radius: 4px; min-width: 30px;
            }}
            QScrollBar:vertical {{
                background: {_BG}; width: 8px; border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {_BORDER}; border-radius: 4px; min-height: 30px;
            }}
        """)

        self._canvas = GanttCanvas()
        self._canvas.set_operators(self._operators)
        self._canvas.task_clicked.connect(self._on_task_clicked)
        self._canvas.task_moved.connect(self.changed.emit)
        self._canvas.task_edit_requested.connect(self._on_task_edit)
        self._scroll.setWidget(self._canvas)
        root.addWidget(self._scroll, 1)

        # ── add operation button strip ──
        add_strip = QWidget()
        add_strip.setFixedHeight(32)
        add_strip.setStyleSheet(f"background-color: {_CARD}; border-top: 1px solid {_BORDER};")
        add_strip_layout = QHBoxLayout(add_strip)
        add_strip_layout.setContentsMargins(12, 0, 12, 0)
        add_op_row_btn = QPushButton("＋ Add Operation")
        add_op_row_btn.setStyleSheet(_BTN_SMALL)
        add_op_row_btn.setFixedHeight(24)
        add_op_row_btn.setCursor(Qt.PointingHandCursor)
        add_op_row_btn.clicked.connect(self._add_operation)
        add_task_btn = QPushButton("＋ Add Task")
        add_task_btn.setStyleSheet(_BTN_SMALL)
        add_task_btn.setFixedHeight(24)
        add_task_btn.setCursor(Qt.PointingHandCursor)
        add_task_btn.clicked.connect(self._add_task)
        add_strip_layout.addWidget(add_op_row_btn)
        add_strip_layout.addWidget(add_task_btn)
        add_strip_layout.addStretch()
        root.addWidget(add_strip)

        # ── separator ──
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {_BORDER}; background: {_BORDER}; max-height: 1px; border: none;")
        root.addWidget(sep)

        # ── bottom detail panel ──
        self._detail = TaskDetailPanel()
        self._detail.edit_requested.connect(self._on_task_edit)
        self._detail.delete_requested.connect(self._on_task_delete)
        root.addWidget(self._detail)

    # ── tabs ──────────────────────────────────────────────────────────────

    def _refresh_tabs(self):
        # Clear existing tab buttons
        while self._tabs_layout.count():
            item = self._tabs_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._tab_btns: list[QPushButton] = []

        overview_btn = QPushButton("Overview")
        overview_btn.setStyleSheet(_TAB_ACTIVE if self._current_tab == -1 else _TAB_INACTIVE)
        overview_btn.setFixedHeight(28)
        overview_btn.setCursor(Qt.PointingHandCursor)
        overview_btn.clicked.connect(lambda: self._switch_tab(-1))
        self._tabs_layout.addWidget(overview_btn)
        self._tab_btns.append(overview_btn)

        for i, op in enumerate(self._operators):
            is_active = (i == self._current_tab)

            container = QWidget()
            container.setStyleSheet("background: transparent;")
            ch = QHBoxLayout(container)
            ch.setContentsMargins(0, 0, 0, 0)
            ch.setSpacing(0)

            btn = QPushButton(op.name)
            btn.setFixedHeight(28)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(_TAB_ACTIVE_L if is_active else _TAB_INACTIVE_L)
            btn.clicked.connect(lambda _, idx=i: self._switch_tab(idx))

            close_btn = QPushButton("×")
            close_btn.setFixedHeight(28)
            close_btn.setFixedWidth(22)
            close_btn.setCursor(Qt.PointingHandCursor)
            close_btn.setToolTip(f"Remove {op.name}")
            close_btn.setStyleSheet(_CLOSE_TAB_ACTIVE if is_active else _CLOSE_TAB_INACTIVE)
            close_btn.clicked.connect(lambda _, idx=i: self._remove_operator(idx))

            ch.addWidget(btn)
            ch.addWidget(close_btn)
            self._tabs_layout.addWidget(container)
            self._tab_btns.append(btn)

        self._tabs_layout.addStretch()

    def _switch_tab(self, idx: int):
        self._current_tab = idx
        self._canvas.set_current_operator(idx)
        self._refresh_tabs()
        self._detail.clear()

    # ── controls ──────────────────────────────────────────────────────────

    def _shift_date(self, days: int):
        self._canvas._start_date = self._canvas._start_date.addDays(days)
        self._update_date_label()
        self._canvas.update()

    def _update_date_label(self):
        d = self._canvas._start_date if hasattr(self, '_canvas') else _today()
        self._date_lbl.setText(d.toString("d MMM yyyy"))

    def _set_view_mode(self, mode: str):
        self._view_mode = mode
        for m, btn in self._view_btns.items():
            btn.setStyleSheet(_BTN_VIEW_ACTIVE if m == mode else _BTN_VIEW_INACTIVE)
        self._canvas.set_view_mode(mode)

    # ── task interaction ──────────────────────────────────────────────────

    def _on_task_clicked(self, task: Task):
        self._detail.show_task(task)

    def _on_task_edit(self, task: Task):
        dlg = TaskFormDialog(task=task, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            d = dlg.get_task_data()
            task.name      = d["name"]
            task.task_type = d["task_type"]
            task.start     = d["start"]
            task.end       = d["end"]
            task.status    = d["status"]
            task.is_urgent = d["is_urgent"]
            task.duration_days = max(1, task.start.daysTo(task.end))
            self._canvas.set_operators(self._operators)
            self._detail.show_task(task)
            self.changed.emit()

    def _on_task_delete(self, task: Task):
        from ui.modal_utils import ask_yes_no_dialog
        if not ask_yes_no_dialog(
            self, "Remove Task", f"Remove task '{task.name}'?\n\nThis cannot be undone."
        ):
            return
        for op in self._operators:
            for oper in op.operations:
                if task in oper.tasks:
                    oper.tasks.remove(task)
                    break
        self._canvas.set_operators(self._operators)
        self._detail.clear()
        self.changed.emit()

    # ── add items ─────────────────────────────────────────────────────────

    def _add_operator(self):
        name, ok = self._input_dialog("Add Operator", "Operator / Company name:")
        if ok and name:
            op = Operator(self._next_op_id, name)
            self._next_op_id += 1
            op.operations.append(Operation(self._next_op_id, "Operation 1"))
            self._next_op_id += 1
            self._operators.append(op)
            self._canvas.set_operators(self._operators)
            self._refresh_tabs()
            self.changed.emit()

    def _remove_operator(self, idx: int):
        if idx < 0 or idx >= len(self._operators):
            return
        from ui.modal_utils import ask_yes_no_dialog
        op = self._operators[idx]
        if not ask_yes_no_dialog(
            self, "Remove Operator",
            f"Remove operator '{op.name}' and all its operations and tasks?\n\nThis cannot be undone."
        ):
            return
        self._operators.pop(idx)
        # Recalculate current tab index after removal
        if not self._operators or self._current_tab == idx:
            new_tab = -1
        elif self._current_tab > idx:
            new_tab = self._current_tab - 1
        else:
            new_tab = self._current_tab
        self._current_tab = new_tab
        self._canvas.set_operators(self._operators)
        self._canvas.set_current_operator(new_tab)
        self._refresh_tabs()
        self._detail.clear()
        self.changed.emit()

    def _require_operator(self) -> bool:
        """Returns True if an operator tab is selected. Shows a message if not."""
        if self._current_tab == -1:
            from PyQt5.QtWidgets import QMessageBox
            msg = QMessageBox(self)
            msg.setWindowTitle("Select an Operator")
            msg.setText("Please select an operator tab first.\n\nOperations and tasks belong to a specific operator.")
            msg.setIcon(QMessageBox.Information)
            msg.setStyleSheet(f"""
                QMessageBox {{
                    background-color: {_CARD};
                    color: {_TEXT};
                }}
                QLabel {{ color: {_TEXT}; font-size: 11px; background: transparent; border: none; }}
                QPushButton {{
                    background-color: {_ACCENT}; color: white;
                    border: none; border-radius: 5px;
                    padding: 6px 18px; font-size: 11px; font-weight: bold;
                    min-width: 80px;
                }}
                QPushButton:hover {{ background-color: {default_theme.button_primary_hover}; }}
            """)
            msg.exec_()
            return False
        return True

    def _add_operation(self):
        if not self._require_operator() or not self._operators:
            return
        op = self._operators[self._current_tab]
        name, ok = self._input_dialog("Add Operation", f"Operation name for {op.name}:")
        if ok and name:
            op.operations.append(Operation(self._next_op_id, name))
            self._next_op_id += 1
            self._canvas.set_operators(self._operators)
            self.changed.emit()

    def _add_task(self):
        if not self._require_operator() or not self._operators:
            return
        op = self._operators[self._current_tab]
        if not op.operations:
            return
        dlg = TaskFormDialog(operations=op.operations, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            d = dlg.get_task_data()
            task = Task(
                id=self._next_task_id,
                name=d["name"],
                start=d["start"],
                end=d["end"],
                task_type=d["task_type"],
                is_urgent=d["is_urgent"],
                status=d["status"],
            )
            self._next_task_id += 1
            target_op = dlg.selected_operation() or op.operations[-1]
            target_op.tasks.append(task)
            self._canvas.set_operators(self._operators)
            self.changed.emit()

    def _input_dialog(self, title: str, label: str):
        from ui.modal_utils import ask_text_input_dialog
        return ask_text_input_dialog(self, title, label)

    # ── serialisation ─────────────────────────────────────────────────────

    def get_data(self) -> dict:
        def ser_task(t: Task) -> dict:
            return {
                "id": t.id, "name": t.name,
                "start": t.start.toString("yyyy-MM-dd"),
                "end":   t.end.toString("yyyy-MM-dd"),
                "task_type": t.task_type, "is_urgent": t.is_urgent,
                "status": t.status, "comments": t.comments,
                "project_manager":   t.project_manager,
                "technical_manager": t.technical_manager,
                "contributors":      t.contributors,
            }
        def ser_op(o: Operation) -> dict:
            return {"id": o.id, "name": o.name, "tasks": [ser_task(t) for t in o.tasks]}
        def ser_operator(op: Operator) -> dict:
            return {"id": op.id, "name": op.name, "operations": [ser_op(o) for o in op.operations]}
        return {"operators": [ser_operator(op) for op in self._operators]}

    def set_data(self, data: dict):
        ops = []
        for op_d in data.get("operators", []):
            operations = []
            for o_d in op_d.get("operations", []):
                tasks = []
                for t_d in o_d.get("tasks", []):
                    tasks.append(Task(
                        id=t_d["id"], name=t_d["name"],
                        start=QDate.fromString(t_d["start"], "yyyy-MM-dd"),
                        end=QDate.fromString(t_d["end"], "yyyy-MM-dd"),
                        task_type=t_d.get("task_type", DEFAULT_TYPE),
                        is_urgent=t_d.get("is_urgent", False),
                        status=t_d.get("status", "In progress"),
                        comments=t_d.get("comments", []),
                        project_manager=t_d.get("project_manager", ""),
                        technical_manager=t_d.get("technical_manager", ""),
                        contributors=t_d.get("contributors", ""),
                    ))
                operations.append(Operation(o_d["id"], o_d["name"], tasks))
            ops.append(Operator(op_d["id"], op_d["name"], operations))
        self._operators = ops
        self._canvas.set_operators(self._operators)
        self._refresh_tabs()
        self._switch_tab(-1)

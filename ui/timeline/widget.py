"""
GanttCanvas and TimelineWidget.
GanttCanvas and TimelineWidget are kept together — they share internal state
and are too tightly coupled to split safely.
Form dialogs live in dialogs.py.
"""
import logging
from typing import List, Optional
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea,
    QSizePolicy, QAbstractScrollArea, QDialog,
)
from PyQt5.QtCore import Qt, QDate, QRect, QRectF, QPoint, QSize, pyqtSignal
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QFontMetrics,
    QPainterPath, QCursor,
)
from ui.styles import default_theme, make_font, TOOLTIP_STYLE
from ui.modal_utils import ask_yes_no_dialog
from .dialogs import TaskFormDialog, _AddOperatorDialog, _AddOperationDialog, _EditOperationDialog
from .models import (
    Task, Operation, Operator,
    TASK_TYPES, DEFAULT_TYPE, URGENT_COLOR,
    ROW_H, OP_HEADER_H, HEADER_H, OP_LABEL_W,
    DAY_W_DAY, DAY_W_WEEK, DAY_W_MONTH,
    BG, CARD, BORDER, TEXT, MUTED, ACCENT, SIDEBAR,
    today, sample_data,
)
from .task_detail import TaskDetailPanel
from i18n import t

logger = logging.getLogger(__name__)

# ── widget-local style constants ──────────────────────────────────────────────
_BTN_VIEW_ACTIVE = f"""
    QPushButton {{
        background-color: {ACCENT}; color: white; border: none;
        border-radius: 4px; padding: 3px 10px; font-size: 12px; font-weight: bold;
    }}
"""
_BTN_VIEW_INACTIVE = f"""
    QPushButton {{
        background-color: #f1f3f5; color: {MUTED};
        border: 1px solid {BORDER};
        border-radius: 4px; padding: 3px 10px; font-size: 12px;
    }}
    QPushButton:hover {{ color: {TEXT}; background-color: #e5e7eb; border-color: {ACCENT}; }}
"""
_BTN_SMALL = f"""
    QPushButton {{
        background-color: #f1f3f5; color: {TEXT};
        border: 1px solid {BORDER}; border-radius: 4px;
        padding: 3px 8px; font-size: 12px;
    }}
    QPushButton:hover {{ background-color: #e5e7eb; border-color: {ACCENT}; color: {ACCENT}; }}
"""
_TAB_ACTIVE = f"""
    QPushButton {{
        background-color: {ACCENT}; color: white; border: none;
        border-radius: 5px; padding: 5px 14px; font-size: 13px; font-weight: bold;
    }}
"""
_TAB_INACTIVE = f"""
    QPushButton {{
        background-color: transparent; color: {MUTED};
        border: 1px solid {BORDER}; border-radius: 5px;
        padding: 5px 14px; font-size: 13px;
    }}
    QPushButton:hover {{ color: {TEXT}; border-color: {ACCENT}; background-color: #e8f0fe; }}
"""
_TAB_ACTIVE_L   = _TAB_ACTIVE.replace('border-radius: 5px;', 'border-radius: 5px 0 0 5px;')
_TAB_INACTIVE_L = (
    _TAB_INACTIVE
    .replace('border-radius: 5px;', 'border-radius: 5px 0 0 5px;')
    .replace(f'border: 1px solid {BORDER};', f'border: 1px solid {BORDER}; border-right: none;')
)
_CLOSE_TAB_ACTIVE = f"""
    QPushButton {{
        background-color: {ACCENT}; color: rgba(255,255,255,0.55);
        border: none; border-left: 1px solid rgba(255,255,255,0.18);
        border-radius: 0 5px 5px 0; font-size: 15px; font-weight: bold; padding: 0 5px;
    }}
    QPushButton:hover {{ color: white; background-color: #ef4444; border-left-color: transparent; }}
""" + TOOLTIP_STYLE

_CLOSE_TAB_INACTIVE = f"""
    QPushButton {{
        background-color: transparent; color: {MUTED};
        border: 1px solid {BORDER}; border-left: none;
        border-radius: 0 5px 5px 0; font-size: 15px; font-weight: bold; padding: 0 5px;
    }}
    QPushButton:hover {{ color: #ef4444; background-color: #fee2e2; border-color: #fca5a5; border-left: none; }}
""" + TOOLTIP_STYLE


# ── Gantt Canvas ──────────────────────────────────────────────────────────────

class GanttCanvas(QWidget):
    """Custom painted Gantt chart body + frozen left column."""

    task_clicked             = pyqtSignal(object)
    task_moved               = pyqtSignal()
    task_edit_requested      = pyqtSignal(object)
    operation_edit_requested = pyqtSignal(object)   # emits (Operator, Operation) tuple
    row_clicked              = pyqtSignal(object)   # emits (Operator, Operation) tuple

    def __init__(self, parent=None):
        super().__init__(parent)
        self._operators: List[Operator] = []
        self._current_op_idx: int = -1
        self._view_mode: str = 'Day'
        self._start_date: QDate = today().addDays(-7)
        self._deadline: Optional[QDate] = None
        self._selected_task: Optional[Task] = None
        self._h_offset: int = 0
        self._dragging_task: Optional[Task] = None
        self._drag_start_x: int = 0
        self._drag_orig_start: Optional[QDate] = None
        self._drag_orig_end: Optional[QDate] = None
        self._drag_active: bool = False
        self._operation_hit_rects: list = []   # (y_top, y_bot, operator, operation)
        self._hovered_operation = None
        self._selected_operation = None       # Operation currently selected by click
        self.setMouseTracking(True)
        self.setCursor(Qt.ArrowCursor)

    # ── public setters ────────────────────────────────────────────────────────

    def set_operators(self, ops: List[Operator]):
        self._operators = ops; self._recalc_size(); self.update()

    def set_current_operator(self, idx: int):
        self._current_op_idx = idx; self._recalc_size(); self.update()

    def set_view_mode(self, mode: str):
        self._view_mode = mode; self._recalc_size(); self.update()

    def set_h_offset(self, px: int):
        self._h_offset = px; self.update()

    def set_deadline(self, date: Optional[QDate]):
        self._deadline = date; self.update()

    # ── sizing ────────────────────────────────────────────────────────────────

    def _day_w(self) -> int:
        return {'Day': DAY_W_DAY, 'Week': DAY_W_WEEK, 'Month': DAY_W_MONTH}.get(
            self._view_mode, DAY_W_DAY
        )

    def _visible_operators(self) -> List[Operator]:
        if self._current_op_idx == -1:
            return self._operators
        if 0 <= self._current_op_idx < len(self._operators):
            return [self._operators[self._current_op_idx]]
        return []

    def _total_content_h(self) -> int:
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

    # ── paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        self._operation_hit_rects = []
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        w, h, day_w = self.width(), self.height(), self._day_w()
        p.fillRect(0, 0, w, h, QColor(BG))
        self._draw_header(p, day_w)
        y_pos = 0
        for op in self._visible_operators():
            y_pos = self._draw_operator(p, op, y_pos, day_w)
        if self._deadline:
            self._draw_deadline(p, day_w)
        content_h = self._total_content_h()
        p.fillRect(0, HEADER_H, OP_LABEL_W, content_h, QColor(BG))
        y_pos = 0
        for op in self._visible_operators():
            y_pos = self._draw_operator_labels(p, op, y_pos)
        self._draw_header_left(p)
        p.setPen(QPen(QColor(BORDER), 1))
        p.drawLine(OP_LABEL_W, 0, OP_LABEL_W, h)
        p.end()

    def _x_for_date(self, date: QDate, day_w: int) -> int:
        return OP_LABEL_W + self._start_date.daysTo(date) * day_w

    def _draw_header(self, p: QPainter, day_w: int):
        p.fillRect(0, 0, self.width(), HEADER_H, QColor('#e8eaed'))
        p.setPen(QPen(QColor(BORDER), 1))
        p.drawLine(0, HEADER_H, self.width(), HEADER_H)

        font_week  = make_font(size=11, bold=True)
        font_day   = make_font(size=10)
        font_month = make_font(size=11, bold=True)

        date = self._start_date
        is_day_view   = day_w >= DAY_W_DAY
        is_week_view  = not is_day_view and day_w >= DAY_W_WEEK
        # month view = everything smaller

        for _ in range(self._total_days()):
            x = self._x_for_date(date, day_w)
            if x < OP_LABEL_W:
                date = date.addDays(1); continue

            is_week_start  = (date.dayOfWeek() == 1 or date == self._start_date)
            is_month_start = (date.day() == 1    or date == self._start_date)

            if is_day_view:
                # ── Day view: label + tick every day ──────────────────────────
                if is_week_start:
                    p.setPen(QColor(TEXT)); p.setFont(font_week)
                    p.drawText(QRect(x, 4, day_w * 7, 20),
                               Qt.AlignLeft | Qt.AlignVCenter,
                               date.toString('d MMM'))
                p.setPen(QPen(QColor(BORDER), 1))
                p.drawLine(x, HEADER_H - 16, x, HEADER_H)
                day_rect = QRect(x + 2, HEADER_H - 16, day_w - 2, 14)
                p.setPen(QColor(MUTED)); p.setFont(font_day)
                if date == today():
                    p.fillRect(x + 1, HEADER_H - 17, day_w - 2, 16, QColor(ACCENT).darker(140))
                    p.setPen(QColor(ACCENT))
                p.drawText(day_rect, Qt.AlignLeft | Qt.AlignVCenter, date.toString('d'))

            elif is_week_view:
                # ── Week view: label + tick at every week boundary ────────────
                if is_week_start:
                    week_w = day_w * 7
                    label = date.toString('d MMM') if week_w >= 80 else date.toString('d')
                    p.setPen(QColor(TEXT)); p.setFont(font_week)
                    p.drawText(QRect(x, 4, week_w, 20),
                               Qt.AlignLeft | Qt.AlignVCenter, label)
                    p.setPen(QPen(QColor(BORDER), 1))
                    p.drawLine(x, HEADER_H - 12, x, HEADER_H)

            else:
                # ── Month view: label + tick at every month boundary ──────────
                if is_month_start:
                    # Use days to next month boundary — not full daysInMonth —
                    # so partial first months don't overlap the following label.
                    next_month = QDate(date.year(), date.month(), 1).addMonths(1)
                    available_days = date.daysTo(next_month)
                    month_w = available_days * day_w
                    avail_w = month_w - 8
                    p.setFont(font_month)
                    fm = p.fontMetrics()
                    label_full  = date.toString('MMM yyyy')
                    label_short = date.toString('MMM')
                    if avail_w >= fm.horizontalAdvance(label_full):
                        label = label_full
                    elif avail_w >= fm.horizontalAdvance(label_short):
                        label = label_short
                    else:
                        label = None  # too narrow — skip label, keep tick
                    if label:
                        p.setPen(QColor(TEXT))
                        p.drawText(QRect(x + 4, 4, avail_w, 20),
                                   Qt.AlignLeft | Qt.AlignVCenter, label)
                    p.setPen(QPen(QColor(BORDER), 1))
                    p.drawLine(x, HEADER_H - 12, x, HEADER_H)
                # Minor tick every week in month view
                elif is_week_start:
                    p.setPen(QPen(QColor(BORDER), 1))
                    p.drawLine(x, HEADER_H - 6, x, HEADER_H)

            date = date.addDays(1)

        # Today marker
        tx = self._x_for_date(today(), day_w)
        if tx > OP_LABEL_W:
            p.setPen(QPen(QColor(ACCENT), 1, Qt.DotLine))
            p.drawLine(tx, HEADER_H, tx, self.height())

    def _draw_header_left(self, p: QPainter):
        p.fillRect(0, 0, OP_LABEL_W, HEADER_H, QColor('#e8eaed'))
        p.setPen(QPen(QColor(BORDER), 1))
        p.drawLine(0, HEADER_H, OP_LABEL_W, HEADER_H)
        p.setPen(QColor(MUTED)); p.setFont(make_font(size=11, bold=True))
        p.drawText(QRect(8, 0, OP_LABEL_W - 8, HEADER_H),
                   Qt.AlignLeft | Qt.AlignVCenter, t('project.timeline.operations_header'))

    def _draw_operator(self, p: QPainter, op: Operator, y_pos: int, day_w: int) -> int:
        abs_y = HEADER_H + y_pos
        p.fillRect(OP_LABEL_W, abs_y, self.width() - OP_LABEL_W, OP_HEADER_H, QColor('#e8f4fb'))
        p.setPen(QPen(QColor(BORDER), 1))
        p.drawLine(OP_LABEL_W, abs_y + OP_HEADER_H - 1, self.width(), abs_y + OP_HEADER_H - 1)
        y_pos += OP_HEADER_H
        for i, oper in enumerate(op.operations):
            oy = HEADER_H + y_pos
            if oper is self._selected_operation:
                p.fillRect(OP_LABEL_W, oy, self.width() - OP_LABEL_W, ROW_H, QColor('#eff6ff'))
            elif i % 2 == 0:
                p.fillRect(OP_LABEL_W, oy, self.width() - OP_LABEL_W, ROW_H, QColor('#f6f8fa'))
            p.setPen(QPen(QColor(BORDER), 1))
            p.drawLine(OP_LABEL_W, oy + ROW_H - 1, self.width(), oy + ROW_H - 1)
            for task in oper.tasks:
                self._draw_task_block(p, task, oy, day_w)
            y_pos += ROW_H
        return y_pos

    def _draw_task_block(self, p: QPainter, task: Task, row_y: int, day_w: int):
        x = self._x_for_date(task.start, day_w) + day_w // 4
        w = max(task.start.daysTo(task.end) * day_w, day_w)
        y = row_y + 5; h = ROW_H - 10
        if x + w < OP_LABEL_W:
            return
        color = QColor(URGENT_COLOR if task.is_urgent else TASK_TYPES.get(task.task_type, ACCENT))
        is_sel = task is self._selected_task
        path = QPainterPath()
        path.addRoundedRect(QRectF(x, y, w, h), 4, 4)
        p.fillPath(path, QBrush(color if not is_sel else color.lighter(130)))
        if is_sel:
            p.setPen(QPen(QColor('white'), 1.5)); p.drawPath(path)
        if task.is_urgent:
            p.save(); p.setClipPath(path)
            p.setPen(QPen(QColor(255, 255, 255, 40), 4))
            for sx in range(x - h, x + w + h, 8):
                p.drawLine(sx, y, sx + h, y + h)
            p.restore()
        # ── Unavailability hatching ───────────────────────────────────────
        if task.unavailable_start and task.unavailable_end:
            hx1 = max(self._x_for_date(task.unavailable_start, day_w), x)
            hx2 = min(self._x_for_date(task.unavailable_end, day_w), x + w)
            if hx2 > hx1:
                p.save()
                p.setClipRect(QRect(hx1, y, hx2 - hx1, h), Qt.IntersectClip)
                # Dark semi-transparent overlay so the zone is clearly distinct
                p.fillRect(QRect(hx1, y, hx2 - hx1, h), QColor(0, 0, 0, 90))
                # Bold diagonal black lines
                p.setPen(QPen(QColor(0, 0, 0, 220), 2))
                step = 8
                for sx in range(hx1 - h, hx2 + step, step):
                    p.drawLine(sx, y, sx + h, y + h)
                # Border around the hatched zone
                p.setPen(QPen(QColor(0, 0, 0, 180), 1))
                p.drawRect(QRect(hx1, y, hx2 - hx1, h))
                p.restore()

        # ── Delay extension bar ───────────────────────────────────────────
        if task.delay_end and task.delay_end > task.end:
            ex = self._x_for_date(task.end, day_w)
            ew = task.end.daysTo(task.delay_end) * day_w
            if ew > 0:
                ext_color = QColor('#f97316')
                ext_color.setAlpha(200)
                ext_path = QPainterPath()
                ext_path.addRoundedRect(QRectF(ex, y, ew, h), 4, 4)
                p.fillPath(ext_path, QBrush(ext_color))
                p.save()
                p.setClipPath(ext_path)
                p.setPen(QPen(QColor(255, 255, 255, 60), 3))
                for sx in range(ex - h, ex + ew + h, 8):
                    p.drawLine(sx, y, sx + h, y + h)
                p.restore()
                p.setPen(QPen(QColor('#ea580c'), 1.5))
                p.drawPath(ext_path)

        if w > 24:
            p.setPen(QColor('white')); p.setFont(make_font(size=11, bold=task.is_urgent))
            text_rect = QRect(x + 5, y, w - 10, h)
            p.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft,
                       p.fontMetrics().elidedText(task.name, Qt.ElideRight, w - 10))

    def _draw_operator_labels(self, p: QPainter, op: Operator, y_pos: int) -> int:
        abs_y = HEADER_H + y_pos
        p.fillRect(0, abs_y, OP_LABEL_W, OP_HEADER_H, QColor('#dbeafe'))
        p.fillRect(0, abs_y, 3, OP_HEADER_H, QColor(ACCENT))
        p.setPen(QColor('#1d4ed8')); p.setFont(make_font(size=11, bold=True))
        p.drawText(QRect(8, abs_y, OP_LABEL_W - 10, OP_HEADER_H),
                   Qt.AlignVCenter | Qt.AlignLeft, op.name.upper())
        p.setPen(QPen(QColor(BORDER), 1))
        p.drawLine(0, abs_y + OP_HEADER_H - 1, OP_LABEL_W, abs_y + OP_HEADER_H - 1)
        y_pos += OP_HEADER_H
        for i, oper in enumerate(op.operations):
            oy = HEADER_H + y_pos
            is_hovered  = oper is self._hovered_operation
            is_selected = oper is self._selected_operation
            if is_selected:
                p.fillRect(0, oy, OP_LABEL_W, ROW_H, QColor('#dbeafe'))
                p.fillRect(0, oy, 3, ROW_H, QColor(ACCENT))
            elif is_hovered:
                p.fillRect(0, oy, OP_LABEL_W, ROW_H, QColor('#e0eaff'))
            elif i % 2 == 0:
                p.fillRect(0, oy, OP_LABEL_W, ROW_H, QColor('#f6f8fa'))
            p.setPen(QPen(QColor(BORDER), 1))
            p.drawLine(0, oy + ROW_H - 1, OP_LABEL_W, oy + ROW_H - 1)
            p.setPen(QColor(TEXT)); p.setFont(make_font(size=11))
            p.drawText(QRect(10, oy, OP_LABEL_W - 32, ROW_H),
                       Qt.AlignVCenter | Qt.AlignLeft, oper.name)
            # Pencil hint — always faint, brighter on hover
            p.setPen(QColor(ACCENT if is_hovered else MUTED))
            p.setFont(make_font(size=11))
            p.setOpacity(0.7 if is_hovered else 0.3)
            p.drawText(QRect(OP_LABEL_W - 26, oy, 20, ROW_H),
                       Qt.AlignVCenter | Qt.AlignRight, '✎')
            p.setOpacity(1.0)
            self._operation_hit_rects.append((oy, oy + ROW_H, op, oper))
            y_pos += ROW_H
        return y_pos

    def _draw_deadline(self, p: QPainter, day_w: int):
        x = self._x_for_date(self._deadline, day_w)
        p.setPen(QPen(QColor('#ef4444'), 2))
        p.drawLine(x, HEADER_H, x, self.height())
        p.setPen(QColor('#ef4444')); p.setFont(make_font(size=10, bold=True))
        p.drawText(x + 3, HEADER_H + 12, t('project.timeline.deadline_label'))

    # ── interaction ───────────────────────────────────────────────────────────

    def _task_at(self, pos: QPoint) -> Optional[Task]:
        day_w = self._day_w()
        if pos.y() < HEADER_H:
            return None
        y_pos = 0
        for op in self._visible_operators():
            y_pos += OP_HEADER_H
            for oper in op.operations:
                oy = HEADER_H + y_pos
                if oy <= pos.y() < oy + ROW_H:
                    for task in oper.tasks:
                        x = self._x_for_date(task.start, day_w) + day_w // 2
                        w = max(task.start.daysTo(task.end) * day_w, day_w)
                        if x <= pos.x() <= x + w:
                            return task
                y_pos += ROW_H
        return None

    def _operation_at(self, pos: QPoint):
        """Return (Operator, Operation) for the row at pos (any x), or (None, None)."""
        if pos.y() < HEADER_H:
            return None, None
        y_pos = 0
        for op in self._visible_operators():
            y_pos += OP_HEADER_H
            for oper in op.operations:
                oy = HEADER_H + y_pos
                if oy <= pos.y() < oy + ROW_H:
                    return op, oper
                y_pos += ROW_H
        return None, None

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
            else:
                op, oper = self._operation_at(event.pos())
                if oper is not self._selected_operation:
                    self._selected_operation = oper
                    if oper is not None:
                        self.row_clicked.emit((op, oper))
            self.update()

    def mouseMoveEvent(self, event):
        if self._dragging_task:
            dx = event.pos().x() - self._drag_start_x
            day_w = self._day_w()
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
            if task:
                self.setCursor(Qt.OpenHandCursor)
                if self._hovered_operation is not None:
                    self._hovered_operation = None
                    self.update()
            elif event.pos().x() < OP_LABEL_W:
                hovered = None
                for y_top, y_bot, _op, oper in self._operation_hit_rects:
                    if y_top <= event.pos().y() < y_bot:
                        hovered = oper
                        break
                if hovered is not self._hovered_operation:
                    self._hovered_operation = hovered
                    self.update()
                self.setCursor(Qt.PointingHandCursor if hovered else Qt.ArrowCursor)
            else:
                if self._hovered_operation is not None:
                    self._hovered_operation = None
                    self.update()
                self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._dragging_task:
            moved = self._drag_active
            self._dragging_task = self._drag_orig_start = self._drag_orig_end = None
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
            elif event.pos().x() < OP_LABEL_W:
                for y_top, y_bot, operator, operation in self._operation_hit_rects:
                    if y_top <= event.pos().y() < y_bot:
                        self.operation_edit_requested.emit((operator, operation))
                        return


# ── Main Timeline Widget ──────────────────────────────────────────────────────

class TimelineWidget(QWidget):
    """Full Timeline screen."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._operators: List[Operator] = sample_data()
        self._current_tab: int = -1
        self._view_mode: str = 'Day'
        self._next_op_id   = 10
        self._next_task_id = 20
        self._selected_op:   Optional[Operator]   = None
        self._selected_oper: Optional[Operation]  = None
        self.setStyleSheet(f'background-color: {BG};')
        self._build_ui()
        self._refresh_tabs()
        self._switch_tab(-1)

    # ── build ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_top_bar())
        root.addWidget(self._build_tabs_bar())
        root.addWidget(self._build_controls())

        # Main area: Gantt + add-strip on the left, detail panel on the right
        main = QWidget()
        main.setStyleSheet(f'background-color: {BG};')
        main_layout = QHBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        left_layout.addWidget(self._build_gantt_scroll(), 1)

        main_layout.addWidget(left, 1)
        main_layout.addWidget(self._build_detail_panel())

        root.addWidget(main, 1)

    def _build_top_bar(self) -> QWidget:
        top = QWidget(); top.setFixedHeight(46)
        top.setStyleSheet(f'background-color: {BG}; border-bottom: 1px solid {BORDER};')
        layout = QHBoxLayout(top); layout.setContentsMargins(16, 0, 16, 0)
        title = QLabel(t('project.timeline.title')); title.setFont(make_font(size=17, bold=True))
        title.setStyleSheet(f'color: {TEXT}; background: transparent; border: none;')
        sub = QLabel(t('project.timeline.subtitle'))
        sub.setStyleSheet(f'color: {MUTED}; font-size: 12px; background: transparent; border: none;')
        col = QVBoxLayout(); col.setSpacing(1); col.addWidget(title); col.addWidget(sub)
        layout.addLayout(col); layout.addStretch()

        for label, slot in ((t('project.timeline.add_operation'), self._add_operation),
                             (t('project.timeline.add_event'),     self._add_task)):
            btn = QPushButton(label); btn.setStyleSheet(_BTN_SMALL); btn.setFixedHeight(28)
            btn.setCursor(Qt.PointingHandCursor); btn.clicked.connect(slot)
            layout.addWidget(btn)

        layout.addSpacing(8)
        sep = QFrame(); sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet(f'color: {BORDER}; background: {BORDER}; max-width: 1px; border: none;')
        sep.setFixedHeight(20)
        layout.addWidget(sep)
        layout.addSpacing(8)

        add_op = QPushButton(t('project.timeline.add_operator'))
        add_op.setStyleSheet(_BTN_SMALL); add_op.setFixedHeight(28)
        add_op.setCursor(Qt.PointingHandCursor); add_op.clicked.connect(self._add_operator)
        layout.addWidget(add_op)
        return top

    def _build_tabs_bar(self) -> QWidget:
        self._tabs_bar = QWidget()
        self._tabs_bar.setStyleSheet(f'background-color: {BG}; border-bottom: 2px solid {BORDER};')
        self._tabs_bar.setFixedHeight(40)
        self._tabs_layout = QHBoxLayout(self._tabs_bar)
        self._tabs_layout.setContentsMargins(12, 5, 12, 5)
        self._tabs_layout.setSpacing(6)
        self._tabs_layout.addStretch()
        return self._tabs_bar

    def _build_controls(self) -> QWidget:
        controls = QWidget(); controls.setFixedHeight(36)
        controls.setStyleSheet(f'background-color: {CARD}; border-bottom: 1px solid {BORDER};')
        layout = QHBoxLayout(controls); layout.setContentsMargins(12, 4, 12, 4); layout.setSpacing(6)

        lbl = QLabel(t('project.timeline.legend_label'))
        lbl.setStyleSheet(f'color: {MUTED}; font-size: 11px; font-weight: bold; background: transparent; border: none;')
        layout.addWidget(lbl)

        # Legend items live in their own container so we can rebuild without touching the rest
        self._legend_area = QWidget()
        self._legend_area.setStyleSheet('background: transparent; border: none;')
        self._legend_area_layout = QHBoxLayout(self._legend_area)
        self._legend_area_layout.setContentsMargins(0, 0, 0, 0)
        self._legend_area_layout.setSpacing(6)
        self._legend_btns: dict[str, QPushButton] = {}
        self._rebuild_legend_area()
        layout.addWidget(self._legend_area)

        layout.addStretch()

        prev = QPushButton('◀'); prev.setFixedSize(32, 28); prev.setStyleSheet(_BTN_SMALL)
        prev.setCursor(Qt.PointingHandCursor); prev.clicked.connect(lambda: self._shift_date(-14))

        self._date_lbl = QLabel()
        self._date_lbl.setStyleSheet(f'color: {TEXT}; font-size: 12px; font-weight: bold; background: transparent; border: none;')
        self._update_date_label()

        nxt = QPushButton('▶'); nxt.setFixedSize(32, 28); nxt.setStyleSheet(_BTN_SMALL)
        nxt.setCursor(Qt.PointingHandCursor); nxt.clicked.connect(lambda: self._shift_date(14))

        layout.addWidget(prev); layout.addWidget(self._date_lbl); layout.addWidget(nxt)
        layout.addSpacing(8)

        self._view_btns: dict[str, QPushButton] = {}
        for mode in ('Day', 'Week', 'Month'):
            btn = QPushButton(t(f'project.timeline.view_{mode.lower()}')); btn.setFixedHeight(24); btn.setMinimumWidth(54)
            btn.setStyleSheet(_BTN_VIEW_ACTIVE if mode == self._view_mode else _BTN_VIEW_INACTIVE)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, m=mode: self._set_view_mode(m))
            self._view_btns[mode] = btn; layout.addWidget(btn)
        return controls

    def _build_gantt_scroll(self) -> QScrollArea:
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ background-color: {BG}; border: none; }}
            QScrollBar:horizontal {{ background: {BG}; height: 8px; border-radius: 4px; }}
            QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 4px; min-width: 30px; }}
            QScrollBar:vertical {{ background: {BG}; width: 8px; border-radius: 4px; }}
            QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 30px; }}
        """)
        self._canvas = GanttCanvas()
        self._canvas.set_operators(self._operators)
        self._canvas.task_clicked.connect(self._on_task_clicked)
        self._canvas.task_moved.connect(self.changed.emit)
        self._canvas.task_edit_requested.connect(self._on_task_edit)
        self._canvas.operation_edit_requested.connect(self._on_operation_edit)
        self._canvas.row_clicked.connect(self._on_row_clicked)
        self._scroll.setWidget(self._canvas)
        return self._scroll

    def _build_hline(self) -> QFrame:
        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f'color: {BORDER}; background: {BORDER}; max-height: 1px; border: none;')
        return sep

    def _build_detail_panel(self) -> TaskDetailPanel:
        self._detail = TaskDetailPanel()
        self._detail.edit_requested.connect(self._on_task_edit)
        self._detail.delete_requested.connect(self._on_task_delete)
        self._detail.task_changed.connect(self._canvas.update)
        return self._detail

    # ── tabs ──────────────────────────────────────────────────────────────────

    def _refresh_tabs(self):
        while self._tabs_layout.count():
            item = self._tabs_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._tab_btns: list[QPushButton] = []

        overview = QPushButton(t('project.timeline.overview_tab'))
        overview.setStyleSheet(_TAB_ACTIVE if self._current_tab == -1 else _TAB_INACTIVE)
        overview.setFixedHeight(28); overview.setCursor(Qt.PointingHandCursor)
        overview.clicked.connect(lambda: self._switch_tab(-1))
        self._tabs_layout.addWidget(overview)
        self._tab_btns.append(overview)

        for i, op in enumerate(self._operators):
            is_active = (i == self._current_tab)
            container = QWidget(); container.setStyleSheet('background: transparent;')
            ch = QHBoxLayout(container); ch.setContentsMargins(0, 0, 0, 0); ch.setSpacing(0)

            btn = QPushButton(op.name); btn.setFixedHeight(28)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(_TAB_ACTIVE_L if is_active else _TAB_INACTIVE_L)
            btn.clicked.connect(lambda _, idx=i: self._switch_tab(idx))

            close_btn = QPushButton('×'); close_btn.setFixedHeight(28); close_btn.setFixedWidth(22)
            close_btn.setCursor(Qt.PointingHandCursor)
            close_btn.setToolTip(f'Remove {op.name}')
            close_btn.setStyleSheet(_CLOSE_TAB_ACTIVE if is_active else _CLOSE_TAB_INACTIVE)
            close_btn.clicked.connect(lambda _, idx=i: self._remove_operator(idx))

            ch.addWidget(btn); ch.addWidget(close_btn)
            self._tabs_layout.addWidget(container)
            self._tab_btns.append(btn)

        self._tabs_layout.addStretch()

    def _switch_tab(self, idx: int):
        self._current_tab = idx
        self._canvas.set_current_operator(idx)
        self._refresh_tabs()
        self._detail.clear()

    # ── controls ──────────────────────────────────────────────────────────────

    def _shift_date(self, days: int):
        self._canvas._start_date = self._canvas._start_date.addDays(days)
        self._canvas._start_date = self._snap_start_date(
            self._canvas._start_date, self._view_mode
        )
        self._update_date_label(); self._canvas.update()

    def _snap_start_date(self, date: QDate, mode: str) -> QDate:
        """Snap start date so month/week boundaries always land on clean column edges."""
        if mode == 'Month':
            return QDate(date.year(), date.month(), 1)
        if mode == 'Week':
            return date.addDays(-(date.dayOfWeek() - 1))  # snap to Monday
        return date

    # ── legend helpers ────────────────────────────────────────────────────────

    def _rebuild_legend_area(self):
        """Clear and repopulate the legend area from the current TASK_TYPES dict."""
        # Remove all existing widgets
        while self._legend_area_layout.count():
            item = self._legend_area_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._legend_btns.clear()

        for name, color in TASK_TYPES.items():
            btn = self._make_legend_btn(name, color)
            self._legend_btns[name] = btn
            self._legend_area_layout.addWidget(btn)

        # Add legend button
        edit_btn = QPushButton(t('project.timeline.add_legend'))
        edit_btn.setFixedHeight(22)
        edit_btn.setToolTip(t('project.timeline.edit_legend_tip'))
        edit_btn.setCursor(Qt.PointingHandCursor)
        edit_btn.setStyleSheet(f"""
            QPushButton {{
                color: {ACCENT}; background: transparent; border: none;
                font-size: 12px; font-weight: bold; padding: 0 4px;
            }}
            QPushButton:hover {{ color: {MUTED}; }}
        """ + TOOLTIP_STYLE)
        edit_btn.clicked.connect(self._open_legend_editor)
        self._legend_area_layout.addWidget(edit_btn)

    def _make_legend_btn(self, name: str, color: str) -> QPushButton:
        btn = QPushButton(f'● {name}')
        btn.setToolTip(f'Click to change colour for "{name}"')
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(self._legend_btn_style(color))
        btn.clicked.connect(lambda _, n=name, b=btn: self._edit_legend_color(n, b))
        return btn

    @staticmethod
    def _legend_btn_style(color: str) -> str:
        return f"""
            QPushButton {{
                color: {color}; font-size: 11px;
                background: transparent; border: none; padding: 0 2px;
            }}
            QPushButton:hover {{
                color: {color}; text-decoration: underline;
                background: transparent; border: none;
            }}
        """ + TOOLTIP_STYLE

    def _edit_legend_color(self, name: str, anchor: QPushButton):
        """Quick per-item colour change via the app's DrawColorPicker popup."""
        from ui.draw_color_picker import DrawColorPicker
        picker = DrawColorPicker(self)
        picker.color_selected.connect(lambda c, n=name: self._apply_legend_color(n, c))
        pos = anchor.mapToGlobal(anchor.rect().bottomLeft())
        picker.move(pos)
        picker.show()

    def _apply_legend_color(self, name: str, new_hex: str):
        TASK_TYPES[name] = new_hex
        btn = self._legend_btns.get(name)
        if btn:
            btn.setStyleSheet(self._legend_btn_style(new_hex))
        self._canvas.update()
        self.changed.emit()

    def _open_legend_editor(self):
        """Open the full legend editor (add / rename / delete / recolour)."""
        from ui.timeline.dialogs import LegendEditorDialog
        dlg = LegendEditorDialog(dict(TASK_TYPES), self)
        if dlg.exec_() == QDialog.Accepted:
            new_types = dlg.get_result()
            TASK_TYPES.clear()
            TASK_TYPES.update(new_types)
            self._rebuild_legend_area()
            self._canvas.update()
            self.changed.emit()

    def _update_date_label(self):
        d = self._canvas._start_date if hasattr(self, '_canvas') else today()
        self._date_lbl.setText(d.toString('d MMM yyyy'))

    def _set_view_mode(self, mode: str):
        self._view_mode = mode
        for m, btn in self._view_btns.items():
            btn.setStyleSheet(_BTN_VIEW_ACTIVE if m == mode else _BTN_VIEW_INACTIVE)
        self._canvas._start_date = self._snap_start_date(
            self._canvas._start_date, mode
        )
        self._canvas.set_view_mode(mode)
        self._update_date_label()

    # ── task interaction ──────────────────────────────────────────────────────

    def _on_task_clicked(self, task: Task):
        self._detail.show_task(task)

    def _on_task_edit(self, task: Task):
        dlg = TaskFormDialog(task=task, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            d = dlg.get_task_data()
            task.name = d['name']; task.task_type = d['task_type']
            task.start = d['start']; task.end = d['end']
            task.status = d['status']; task.is_urgent = d['is_urgent']
            task.unavailable_start = d['unavailable_start']
            task.unavailable_end   = d['unavailable_end']
            task.duration_days = max(1, task.start.daysTo(task.end))
            self._canvas.set_operators(self._operators)
            self._detail.show_task(task)
            self.changed.emit()

    def _on_task_delete(self, task: Task):
        if not ask_yes_no_dialog(self, t('project.timeline.remove_task'),
                                  f"Remove task '{task.name}'?\n\nThis cannot be undone."):
            return
        for op in self._operators:
            for oper in op.operations:
                if task in oper.tasks:
                    oper.tasks.remove(task); break
        self._canvas.set_operators(self._operators)
        self._detail.clear(); self.changed.emit()

    # ── add items ─────────────────────────────────────────────────────────────

    def _add_operator(self):
        dlg = _AddOperatorDialog(self)
        if dlg.exec_() == QDialog.Accepted and dlg.name:
            op = Operator(self._next_op_id, dlg.name)
            self._next_op_id += 1
            self._operators.append(op)
            self._canvas.set_operators(self._operators)
            self._refresh_tabs(); self.changed.emit()

    def _remove_operator(self, idx: int):
        if idx < 0 or idx >= len(self._operators):
            return
        op = self._operators[idx]
        if not ask_yes_no_dialog(
            self, t('project.timeline.remove_operator'),
            f"Remove operator '{op.name}' and all its operations and tasks?\n\nThis cannot be undone."
        ):
            return
        self._operators.pop(idx)
        if not self._operators or self._current_tab == idx:
            new_tab = -1
        elif self._current_tab > idx:
            new_tab = self._current_tab - 1
        else:
            new_tab = self._current_tab
        self._current_tab = new_tab
        self._canvas.set_operators(self._operators)
        self._canvas.set_current_operator(new_tab)
        self._refresh_tabs(); self._detail.clear(); self.changed.emit()

    def _require_operator(self) -> bool:
        if self._current_tab == -1:
            from ui.modal_utils import show_message_dialog
            show_message_dialog(
                self, t('project.timeline.select_operator'),
                'Please select an operator tab first.\n\nOperations and tasks belong to a specific operator.'
            )
            return False
        return True

    def _add_operation(self):
        if not self._require_operator() or not self._operators:
            return
        op = self._operators[self._current_tab]
        dlg = _AddOperationDialog(op.name, self)
        if dlg.exec_() == QDialog.Accepted and dlg.name:
            op.operations.append(Operation(self._next_op_id, dlg.name))
            self._next_op_id += 1
            self._canvas.set_operators(self._operators); self.changed.emit()

    def _on_operation_edit(self, payload):
        operator, operation = payload
        dlg = _EditOperationDialog(operation, operator.name, self)
        if dlg.exec_() == QDialog.Accepted and dlg.name:
            operation.name = dlg.name
            self._canvas.set_operators(self._operators)
            self.changed.emit()

    def _on_row_clicked(self, payload):
        self._selected_op, self._selected_oper = payload

    def _add_task(self):
        if not self._operators:
            return
        # Resolve pre-selection from last row click, fall back to current tab
        op_idx   = max(0, self._current_tab)
        oper_idx = 0
        if self._selected_op is not None and self._selected_oper is not None:
            for i, op in enumerate(self._operators):
                if op is self._selected_op:
                    op_idx = i
                    for j, oper in enumerate(op.operations):
                        if oper is self._selected_oper:
                            oper_idx = j
                    break
        dlg = TaskFormDialog(
            operators=self._operators,
            current_op_idx=op_idx,
            current_oper_idx=oper_idx,
            parent=self,
        )
        if dlg.exec_() == QDialog.Accepted:
            _op, oper = dlg.selected_operation()
            if oper is None:
                from ui.modal_utils import show_message_dialog
                show_message_dialog(
                    self, t('project.timeline.no_op_selected'),
                    'The selected operator has no operations yet.\n\n'
                    'Add at least one operation to the operator first, then add a task.'
                )
                return
            d = dlg.get_task_data()
            task = Task(id=self._next_task_id, name=d['name'],
                        start=d['start'], end=d['end'],
                        task_type=d['task_type'], is_urgent=d['is_urgent'],
                        status=d['status'])
            self._next_task_id += 1
            oper.tasks.append(task)
            self._canvas.set_operators(self._operators)
            self.changed.emit()

    # ── serialisation ─────────────────────────────────────────────────────────

    def get_data(self) -> dict:
        def _task(t: Task) -> dict:
            return {
                'id': t.id, 'name': t.name,
                'start': t.start.toString('yyyy-MM-dd'),
                'end':   t.end.toString('yyyy-MM-dd'),
                'task_type': t.task_type, 'is_urgent': t.is_urgent,
                'status': t.status, 'comments': t.comments,
                'project_manager':   t.project_manager,
                'technical_manager': t.technical_manager,
                'contributors':      t.contributors,
                'unavailable_start': t.unavailable_start.toString('yyyy-MM-dd') if t.unavailable_start else None,
                'unavailable_end':   t.unavailable_end.toString('yyyy-MM-dd')   if t.unavailable_end   else None,
                'delay_end':         t.delay_end.toString('yyyy-MM-dd')         if t.delay_end         else None,
            }
        def _op(o: Operation) -> dict:
            return {'id': o.id, 'name': o.name, 'tasks': [_task(t) for t in o.tasks]}
        def _operator(op: Operator) -> dict:
            return {'id': op.id, 'name': op.name, 'operations': [_op(o) for o in op.operations]}
        return {'operators': [_operator(op) for op in self._operators]}

    def update_project_info(self, info: dict):
        """Receive global project sidebar data and forward PM to the detail panel."""
        pm = (info.get('project_manager') or '').strip()
        self._detail.set_global_pm(pm)

    def set_data(self, data: dict):
        ops = []
        for op_d in data.get('operators', []):
            operations = []
            for o_d in op_d.get('operations', []):
                tasks = [
                    Task(
                        id=t['id'], name=t['name'],
                        start=QDate.fromString(t['start'], 'yyyy-MM-dd'),
                        end=QDate.fromString(t['end'], 'yyyy-MM-dd'),
                        task_type=t.get('task_type', DEFAULT_TYPE),
                        is_urgent=t.get('is_urgent', False),
                        status=t.get('status', 'In progress'),
                        comments=t.get('comments', []),
                        project_manager=t.get('project_manager', ''),
                        technical_manager=t.get('technical_manager', ''),
                        contributors=t.get('contributors', ''),
                        unavailable_start=QDate.fromString(t['unavailable_start'], 'yyyy-MM-dd') if t.get('unavailable_start') else None,
                        unavailable_end=QDate.fromString(t['unavailable_end'], 'yyyy-MM-dd')     if t.get('unavailable_end')   else None,
                        delay_end=QDate.fromString(t['delay_end'], 'yyyy-MM-dd')                 if t.get('delay_end')         else None,
                    )
                    for t in o_d.get('tasks', [])
                ]
                operations.append(Operation(o_d['id'], o_d['name'], tasks))
            ops.append(Operator(op_d['id'], op_d['name'], operations))
        self._operators = ops
        self._canvas.set_operators(self._operators)
        self._refresh_tabs(); self._switch_tab(-1)

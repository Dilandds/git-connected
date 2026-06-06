"""
All form dialogs for the Timeline module.
Every dialog extends FormModal so theme and tooltip styling are guaranteed consistent.
"""
from typing import List, Optional

from PyQt5.QtWidgets import QLineEdit, QComboBox, QCheckBox, QDateEdit, QLabel

from ui.modal_utils import FormModal
from .models import Task, Operation, Operator, TASK_TYPES, today


# ── Add Operator ──────────────────────────────────────────────────────────────

class _AddOperatorDialog(FormModal):
    def __init__(self, parent=None):
        super().__init__(parent, 'Add Operator', min_width=380)
        self.f_name = self.add_field('OPERATOR / COMPANY NAME', QLineEdit())
        self.f_name.setPlaceholderText('Operator or company name')
        self.finish()
        self.f_name.returnPressed.connect(self.ok_btn.click)
        self.f_name.setFocus()

    @property
    def name(self) -> str:
        return self.f_name.text().strip()


# ── Add Operation ─────────────────────────────────────────────────────────────

class _AddOperationDialog(FormModal):
    def __init__(self, operator_name: str, parent=None):
        super().__init__(parent, 'Add Operation', min_width=380)
        self.f_name = self.add_field(f'OPERATION NAME  ({operator_name})', QLineEdit())
        self.f_name.setPlaceholderText('Operation name')
        self.finish()
        self.f_name.returnPressed.connect(self.ok_btn.click)
        self.f_name.setFocus()

    @property
    def name(self) -> str:
        return self.f_name.text().strip()


# ── Edit Operation ────────────────────────────────────────────────────────────

class _EditOperationDialog(FormModal):
    def __init__(self, operation: Operation, operator_name: str, parent=None):
        super().__init__(parent, 'Edit Operation', min_width=380)
        self.f_name = self.add_field(f'OPERATION NAME  ({operator_name})', QLineEdit(operation.name))
        self.f_name.setPlaceholderText('Operation name')
        self.finish()
        self.f_name.returnPressed.connect(self.ok_btn.click)
        self.f_name.setFocus()

    @property
    def name(self) -> str:
        return self.f_name.text().strip()


# ── Add / Edit Task ───────────────────────────────────────────────────────────

class TaskFormDialog(FormModal):
    """Add or edit a task. Pass `operators` when adding to show the operator→operation pickers."""

    def __init__(self, task: Optional[Task] = None,
                 operators: Optional[List[Operator]] = None,
                 current_op_idx: int = 0,
                 current_oper_idx: int = 0,
                 parent=None):
        super().__init__(parent, 'Edit Task' if task else 'Add Task',
                         min_width=380)
        self._operators: List[Operator] = operators or []

        self.f_operator: Optional[QComboBox] = None
        self.f_operation: Optional[QComboBox] = None

        if operators:
            self.add_field('PLACE IN', QLabel('Select the operator and row for this task.'),
                           height=0)
            self.f_operator = QComboBox()
            for op in operators:
                self.f_operator.addItem(op.name)
            self.f_operator.setCurrentIndex(max(0, current_op_idx))
            self.add_hfield('Operator', self.f_operator)

            self._current_oper_idx = current_oper_idx
            self.f_operation = QComboBox()
            self.add_hfield('Operation', self.f_operation)
            self._populate_operation_combo()
            self.f_operator.currentIndexChanged.connect(self._populate_operation_combo)
            self.add_separator()

        self.f_name = self.add_hfield('Name', QLineEdit(task.name if task else ''))
        self.f_name.setPlaceholderText('Task name')

        self.f_type = self.add_hfield('Type', QComboBox())
        self.f_type.addItems(list(TASK_TYPES.keys()))
        if task:
            self.f_type.setCurrentText(task.task_type)

        self.f_start = self.add_hfield('Start', QDateEdit(task.start if task else today()))
        self.f_start.setDisplayFormat('dd/MM/yyyy')
        self.f_start.setCalendarPopup(True)

        self.f_end = self.add_hfield('End', QDateEdit(task.end if task else today().addDays(3)))
        self.f_end.setDisplayFormat('dd/MM/yyyy')
        self.f_end.setCalendarPopup(True)

        self.f_status = self.add_hfield('Status', QComboBox())
        self.f_status.addItems(['In progress', 'Awaiting', 'Completed', 'Cancelled'])
        if task:
            self.f_status.setCurrentText(task.status)

        self.f_urgent = QCheckBox('Mark as urgent')
        self.f_urgent.setChecked(task.is_urgent if task else False)
        self.add_widget(self.f_urgent)
        self.finish()

    def _populate_operation_combo(self):
        if self.f_operation is None:
            return
        self.f_operation.clear()
        idx = self.f_operator.currentIndex() if self.f_operator else -1
        if 0 <= idx < len(self._operators):
            for oper in self._operators[idx].operations:
                self.f_operation.addItem(oper.name)
        # Apply pre-selection only on first population (operator hasn't changed)
        if hasattr(self, '_current_oper_idx') and self._current_oper_idx > 0:
            self.f_operation.setCurrentIndex(
                min(self._current_oper_idx, self.f_operation.count() - 1)
            )
            self._current_oper_idx = 0   # only apply once

    def selected_operation(self):
        """Return (Operator, Operation) tuple, or (None, None) if nothing selected."""
        if self.f_operator is None or self.f_operation is None:
            return None, None
        op_idx   = self.f_operator.currentIndex()
        oper_idx = self.f_operation.currentIndex()
        if 0 <= op_idx < len(self._operators):
            ops = self._operators[op_idx].operations
            if 0 <= oper_idx < len(ops):
                return self._operators[op_idx], ops[oper_idx]
        return None, None

    def get_task_data(self) -> dict:
        return {
            'name':      self.f_name.text().strip() or 'New Task',
            'task_type': self.f_type.currentText(),
            'start':     self.f_start.date(),
            'end':       self.f_end.date(),
            'status':    self.f_status.currentText(),
            'is_urgent': self.f_urgent.isChecked(),
        }

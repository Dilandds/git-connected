"""
All form dialogs for the Timeline module.
Every dialog extends FormModal so theme and tooltip styling are guaranteed consistent.
"""
from typing import List, Optional

from PyQt5.QtWidgets import (
    QLineEdit, QComboBox, QCheckBox, QLabel,
    QPushButton, QHBoxLayout, QVBoxLayout, QWidget,
    QScrollArea, QFrame, QDialog,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor

from ui.modal_utils import FormModal, BaseModal
from ui.date_picker import EctoDateEdit
from .models import Task, Operation, Operator, TASK_TYPES, today, BORDER, MUTED, ACCENT, TEXT
from i18n import t


# ── Add Operator ──────────────────────────────────────────────────────────────

class _AddOperatorDialog(FormModal):
    def __init__(self, parent=None):
        super().__init__(parent, t('project.timeline.dlg_add_operator'), theme=FormModal.LIGHT, min_width=380)
        self.f_name = self.add_field(t('project.timeline.dlg_op_name_field'), QLineEdit())
        self.f_name.setPlaceholderText(t('project.timeline.dlg_op_name_ph'))
        self.finish()
        self.f_name.returnPressed.connect(self.ok_btn.click)
        self.f_name.setFocus()

    @property
    def name(self) -> str:
        return self.f_name.text().strip()


# ── Add Operation ─────────────────────────────────────────────────────────────

class _AddOperationDialog(FormModal):
    def __init__(self, operator_name: str, parent=None):
        super().__init__(parent, t('project.timeline.dlg_add_operation'), theme=FormModal.LIGHT, min_width=380)
        self.f_name = self.add_field(f'{t("project.timeline.dlg_op_label")}  ({operator_name})', QLineEdit())
        self.f_name.setPlaceholderText(t('project.timeline.dlg_op_ph'))
        self.finish()
        self.f_name.returnPressed.connect(self.ok_btn.click)
        self.f_name.setFocus()

    @property
    def name(self) -> str:
        return self.f_name.text().strip()


# ── Edit Operation ────────────────────────────────────────────────────────────

class _EditOperationDialog(FormModal):
    def __init__(self, operation: Operation, operator_name: str, parent=None):
        super().__init__(parent, t('project.timeline.dlg_edit_operation'), theme=FormModal.LIGHT, min_width=380)
        self.f_name = self.add_field(f'{t("project.timeline.dlg_op_label")}  ({operator_name})', QLineEdit(operation.name))
        self.f_name.setPlaceholderText(t('project.timeline.dlg_op_ph'))
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
        super().__init__(parent,
                         t('project.timeline.dlg_edit_event') if task else t('project.timeline.dlg_add_event'),
                         theme=FormModal.LIGHT, min_width=380)
        self._operators: List[Operator] = operators or []

        self.f_operator: Optional[QComboBox] = None
        self.f_operation: Optional[QComboBox] = None

        if operators:
            self.add_field(t('project.timeline.dlg_place_in'),
                           QLabel(t('project.timeline.dlg_place_hint')), height=0)
            self.f_operator = QComboBox()
            for op in operators:
                self.f_operator.addItem(op.name)
            self.f_operator.setCurrentIndex(max(0, current_op_idx))
            self.add_hfield(t('project.timeline.dlg_operator'), self.f_operator)

            self._current_oper_idx = current_oper_idx
            self.f_operation = QComboBox()
            self.add_hfield(t('project.timeline.dlg_operation'), self.f_operation)
            self._populate_operation_combo()
            self.f_operator.currentIndexChanged.connect(self._populate_operation_combo)
            self.add_separator()

        self.f_name = self.add_hfield(t('project.timeline.dlg_name'), QLineEdit(task.name if task else ''))
        self.f_name.setPlaceholderText(t('project.timeline.dlg_name_ph'))

        self.f_type = self.add_hfield(t('project.timeline.dlg_type'), QComboBox())
        self.f_type.addItems(list(TASK_TYPES.keys()))
        if task:
            self.f_type.setCurrentText(task.task_type)

        self.f_start = self.add_hfield(t('project.timeline.dlg_start'), EctoDateEdit(task.start if task else today()))
        self.f_end   = self.add_hfield(t('project.timeline.dlg_end'),   EctoDateEdit(task.end   if task else today().addDays(3)))

        # Make it impossible to leave the end date earlier than the start date —
        # nudge whichever field is now out of order back in line.
        def _on_start_changed(date):
            if self.f_end.date() < date:
                self.f_end.setDate(date)
        def _on_end_changed(date):
            if date < self.f_start.date():
                self.f_end.setDate(self.f_start.date())
        self.f_start.dateChanged.connect(_on_start_changed)
        self.f_end.dateChanged.connect(_on_end_changed)

        self.f_status = self.add_hfield(t('project.timeline.dlg_status'), QComboBox())
        self.f_status.addItems([
            t('project.timeline.dlg_status_progress'),
            t('project.timeline.dlg_status_awaiting'),
            t('project.timeline.dlg_status_completed'),
            t('project.timeline.dlg_status_cancelled'),
        ])
        if task:
            self.f_status.setCurrentText(task.status)

        self.f_urgent = QCheckBox(t('project.timeline.dlg_urgent'))
        self.f_urgent.setChecked(task.is_urgent if task else False)
        self.add_widget(self.f_urgent)

        self.add_separator()

        # ── Unavailability period ─────────────────────────────────────────
        self._unavail_check = QCheckBox(t('project.timeline.dlg_unavail'))
        _has_unavail = bool(task and task.unavailable_start and task.unavailable_end)
        self._unavail_check.setChecked(_has_unavail)
        self.add_widget(self._unavail_check)

        _ustart = task.unavailable_start if (task and task.unavailable_start) else today()
        _uend   = task.unavailable_end   if (task and task.unavailable_end)   else today().addDays(1)
        self.f_unavail_start = self.add_hfield(t('project.timeline.dlg_unavail_from'), EctoDateEdit(_ustart))
        self.f_unavail_end   = self.add_hfield(t('project.timeline.dlg_unavail_to'),   EctoDateEdit(_uend))

        def _toggle_unavail(checked):
            self.f_unavail_start.setEnabled(checked)
            self.f_unavail_end.setEnabled(checked)

        self._unavail_check.toggled.connect(_toggle_unavail)
        _toggle_unavail(_has_unavail)

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
        has_unavail = self._unavail_check.isChecked()
        return {
            'name':              self.f_name.text().strip() or 'New Task',
            'task_type':         self.f_type.currentText(),
            'start':             self.f_start.date(),
            'end':               self.f_end.date(),
            'status':            self.f_status.currentText(),
            'is_urgent':         self.f_urgent.isChecked(),
            'unavailable_start': self.f_unavail_start.date() if has_unavail else None,
            'unavailable_end':   self.f_unavail_end.date()   if has_unavail else None,
        }


# ── Legend Editor ─────────────────────────────────────────────────────────────

_SWATCH_STYLE = """
    QPushButton {{
        color: {c}; background: transparent;
        border: 2px solid {c}; border-radius: 5px;
        font-size: 18px; padding: 0;
    }}
    QPushButton:hover {{ border-width: 3px; }}
"""

_NAME_STYLE = f"""
    QLineEdit {{
        background-color: #f5f6f8; color: #1e2430;
        border: 1px solid {BORDER}; border-radius: 4px;
        padding: 2px 8px; font-size: 12px;
    }}
    QLineEdit:focus {{ border-color: {ACCENT}; }}
"""

_DEL_STYLE = f"""
    QPushButton {{
        color: {MUTED}; background: transparent; border: none;
        font-size: 16px; font-weight: bold; padding: 0 4px;
    }}
    QPushButton:hover {{ color: #ef4444; }}
"""

_ADD_STYLE = f"""
    QPushButton {{
        background-color: #f1f3f5; color: #1e2430;
        border: 1px solid {BORDER}; border-radius: 5px;
        font-size: 12px; padding: 5px 14px;
    }}
    QPushButton:hover {{ background-color: #e5e7eb; border-color: {ACCENT}; color: {ACCENT}; }}
"""


class LegendEditorDialog(BaseModal):
    """Dialog to add, recolour, rename and remove timeline legend entries."""

    def __init__(self, task_types: dict, parent=None):
        super().__init__(parent, t('project.timeline.dlg_edit_legend'), theme='light', min_width=440)
        # Working copy: list of [color_str, name_str] — mutated in-place by row widgets
        self._entries: list[list] = [[color, name] for name, color in task_types.items()]
        self._rows_widget = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_widget)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(6)
        self._build()

    # ── layout ────────────────────────────────────────────────────────────────

    def _build(self):
        scroll = QScrollArea()
        scroll.setWidget(self._rows_widget)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMaximumHeight(320)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ background: #f1f3f5; width: 6px; border-radius: 3px; }}
            QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 3px; }}
        """)
        self._root.addWidget(scroll)

        for entry in self._entries:
            self._add_row(entry)

        add_btn = QPushButton(t('project.timeline.dlg_add_entry'))
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setStyleSheet(_ADD_STYLE)
        add_btn.clicked.connect(self._add_new_entry)
        self._root.addWidget(add_btn)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f'color: {BORDER}; background: {BORDER}; max-height: 1px; border: none;')
        self._root.addWidget(sep)

        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        btn_row.addStretch()
        btn_row.addWidget(self._make_cancel_btn())
        btn_row.addWidget(self._make_ok_btn(t('project.timeline.dlg_save')))
        self._root.addLayout(btn_row)

    def _add_row(self, entry: list):
        """Build one editable row for the given [color, name] entry."""
        color, name = entry

        row = QWidget()
        row.setStyleSheet('background: transparent; border: none;')
        rl = QHBoxLayout(row)
        rl.setContentsMargins(4, 2, 4, 2)
        rl.setSpacing(8)

        # Colour swatch
        swatch = QPushButton('●')
        swatch.setFixedSize(32, 32)
        swatch.setCursor(Qt.PointingHandCursor)
        swatch.setToolTip(t('project.timeline.dlg_change_color'))
        swatch.setStyleSheet(_SWATCH_STYLE.format(c=color))

        # Name field
        name_edit = QLineEdit(name)
        name_edit.setStyleSheet(_NAME_STYLE)
        name_edit.setFixedHeight(32)
        name_edit.textChanged.connect(lambda v, e=entry: e.__setitem__(1, v))

        # Delete button
        del_btn = QPushButton('×')
        del_btn.setFixedSize(28, 28)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setStyleSheet(_DEL_STYLE)
        del_btn.setToolTip(t('project.timeline.dlg_remove_entry'))
        del_btn.clicked.connect(lambda _, e=entry, r=row: self._remove_row(e, r))

        rl.addWidget(swatch)
        rl.addWidget(name_edit, 1)
        rl.addWidget(del_btn)
        self._rows_layout.addWidget(row)

        # Wire colour picker
        swatch.clicked.connect(lambda _, e=entry, s=swatch: self._open_picker(e, s))

    def _open_picker(self, entry: list, swatch: QPushButton):
        from ui.draw_color_picker import DrawColorPicker
        picker = DrawColorPicker(self)
        picker.color_selected.connect(lambda c, e=entry, s=swatch: self._apply_swatch(c, e, s))
        pos = swatch.mapToGlobal(swatch.rect().bottomLeft())
        picker.move(pos)
        picker.show()

    @staticmethod
    def _apply_swatch(color: str, entry: list, swatch: QPushButton):
        entry[0] = color
        swatch.setStyleSheet(_SWATCH_STYLE.format(c=color))

    def _remove_row(self, entry: list, row: QWidget):
        if entry in self._entries:
            self._entries.remove(entry)
        row.setParent(None)
        row.deleteLater()

    def _add_new_entry(self):
        entry = ['#3b82f6', 'New Type']
        self._entries.append(entry)
        self._add_row(entry)
        # Scroll to bottom so new row is visible
        QTimer.singleShot(0, lambda: self._rows_widget.updateGeometry())

    # ── result ────────────────────────────────────────────────────────────────

    def get_result(self) -> dict:
        """Return {name: color} dict preserving order, skipping blank names."""
        return {
            entry[1].strip(): entry[0]
            for entry in self._entries
            if entry[1].strip()
        }

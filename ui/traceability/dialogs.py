"""
All form dialogs used by the traceability module.
Every dialog extends FormModal so styling is guaranteed consistent.
"""
import os
from typing import Optional

from PyQt5.QtWidgets import (
    QLineEdit, QTextEdit, QComboBox, QSpinBox,
    QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QWidget, QFileDialog, QDialog,
)
from PyQt5.QtCore import Qt
from ui.modal_utils import FormModal, BaseModal, MODAL_BTN_PRIMARY, MODAL_BTN_CANCEL
from .models import TracePart, TraceTask, TraceStep, TraceStage, TraceComponent, TraceSubStage
from .shared import _BTN_SMALL, _BTN_PRIMARY, _MUTED, _TEXT, _CARD
from i18n import t


# ── Add / Edit Part group (name only) ────────────────────────────────────────

class _PartDialog(FormModal):
    """Simple dialog for creating/renaming a TracePart group (name only)."""
    def __init__(self, part: Optional[TracePart] = None, parent=None):
        title = t('project.traceability.edit_part_title') if part else t('project.traceability.add_part_title')
        super().__init__(parent, title, theme=FormModal.LIGHT, min_width=340)
        self.f_name = self.add_field(t('project.traceability.part_name'), QLineEdit(part.name if part else ''))
        self.f_name.setPlaceholderText(t('project.traceability.part_name_ph'))
        self.finish()
        self.f_name.setFocus()

    def get_data(self) -> dict:
        return {'name': self.f_name.text().strip() or 'Part'}


# ── Add / Edit Task (full task data) ─────────────────────────────────────────

class _TaskDialog(FormModal):
    """Dialog for creating/editing a TraceTask within a part group."""
    def __init__(self, task: Optional[TraceTask] = None, parent=None):
        title = t('project.traceability.edit_part_title') if task else t('project.traceability.add_part_title')
        super().__init__(parent, title, theme=FormModal.LIGHT, min_width=420)

        self.f_name = self.add_field(t('project.traceability.part_name'), QLineEdit(task.name if task else ''))
        self.f_name.setPlaceholderText(t('project.traceability.part_name_ph'))

        self.f_subject = self.add_field(t('project.traceability.subject'), QLineEdit(task.subject if task else ''))
        self.f_subject.setPlaceholderText(t('project.traceability.subject_ph'))

        self.f_performed_by = self.add_field(t('project.traceability.performed_by'), QLineEdit(task.performed_by if task else ''))
        self.f_performed_by.setPlaceholderText(t('project.traceability.performed_by_ph'))

        self.f_suppliers = self.add_field(t('project.traceability.suppliers'), QLineEdit(task.suppliers if task else ''))
        self.f_suppliers.setPlaceholderText(t('project.traceability.suppliers_ph'))

        self.f_action = self.add_field(t('project.traceability.action'), QLineEdit(task.action if task else ''))
        self.f_action.setPlaceholderText(t('project.traceability.action_ph'))

        self.f_task = self.add_field(t('project.traceability.current_task'), QTextEdit(), height_override=52)
        self.f_task.setPlaceholderText(t('project.traceability.current_task_ph'))
        if task:
            self.f_task.setPlainText(task.current_task)

        self.f_start, self.f_due = self.add_row_fields(
            (t('project.traceability.start_date_field'), QLineEdit(task.start_date if task else '')),
            (t('project.traceability.due_date_field'),   QLineEdit(task.due_date   if task else '')),
        )
        self.f_start.setPlaceholderText(t('project.traceability.date_ph'))
        self.f_due.setPlaceholderText(t('project.traceability.date_ph'))

        status_cb = QComboBox()
        for _key, _i18n in [
            ('Upcoming',    'project.traceability.status_upcoming'),
            ('In Progress', 'project.traceability.status_in_progress'),
            ('Completed',   'project.traceability.status_completed'),
        ]:
            status_cb.addItem(t(_i18n), _key)
        if task:
            for _i in range(status_cb.count()):
                if status_cb.itemData(_i) == task.status:
                    status_cb.setCurrentIndex(_i)
                    break

        progress_spin = QSpinBox()
        progress_spin.setRange(0, 100)
        progress_spin.setValue(task.progress if task else 0)

        self.f_status, self.f_progress = self.add_row_fields(
            (t('project.traceability.status'),       status_cb),
            (t('project.traceability.progress_pct'), progress_spin),
        )
        self.finish()

    def get_data(self) -> dict:
        return {
            'name':         self.f_name.text().strip() or 'Task',
            'subject':      self.f_subject.text().strip(),
            'performed_by': self.f_performed_by.text().strip(),
            'suppliers':    self.f_suppliers.text().strip(),
            'action':       self.f_action.text().strip(),
            'current_task': self.f_task.toPlainText().strip(),
            'start_date':   self.f_start.text().strip(),
            'due_date':     self.f_due.text().strip(),
            'status':       self.f_status.currentData(),
            'progress':     self.f_progress.value(),
        }


# ── Add / Edit Step ───────────────────────────────────────────────────────────

class _StepDialog(FormModal):
    """Dialog for creating/editing a TraceStep within a task."""
    def __init__(self, step: Optional[TraceStep] = None, parent=None):
        title = 'Edit Sub-step' if step else 'Add Sub-step'
        super().__init__(parent, title, theme=FormModal.LIGHT, min_width=380)

        self.f_name = self.add_field('STEP NAME', QLineEdit(step.name if step else ''))
        self.f_name.setPlaceholderText('e.g. Inspect surface')

        self.f_desc = self.add_field('DESCRIPTION', QTextEdit(), height_override=60)
        self.f_desc.setPlaceholderText('Step description…')
        if step:
            self.f_desc.setPlainText(step.description)

        status_cb = QComboBox()
        for _key, _i18n in [
            ('Upcoming',    'project.traceability.status_upcoming'),
            ('In Progress', 'project.traceability.status_in_progress'),
            ('Completed',   'project.traceability.status_completed'),
        ]:
            status_cb.addItem(t(_i18n), _key)
        if step:
            for _i in range(status_cb.count()):
                if status_cb.itemData(_i) == step.status:
                    status_cb.setCurrentIndex(_i)
                    break

        progress_spin = QSpinBox()
        progress_spin.setRange(0, 100)
        progress_spin.setValue(step.progress if step else 0)

        self.f_status, self.f_progress = self.add_row_fields(
            (t('project.traceability.status'),       status_cb),
            (t('project.traceability.progress_pct'), progress_spin),
        )
        self.finish()
        self.f_name.setFocus()

    def get_data(self) -> dict:
        return {
            'name':        self.f_name.text().strip() or 'Step',
            'description': self.f_desc.toPlainText().strip(),
            'status':      self.f_status.currentData(),
            'progress':    self.f_progress.value(),
        }


# ── Comments dialog ───────────────────────────────────────────────────────────

class _CommentsDialog(FormModal):
    """Scrollable comments list + inline add-comment input."""

    def __init__(self, task: TraceTask, parent=None):
        super().__init__(parent, t('project.traceability.comments_title').format(name=task.name), theme=FormModal.LIGHT, min_width=360)
        self._part = task  # kept as _part internally for compatibility

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet('QScrollArea { border: none; }')
        self._inner = QWidget()
        self._inner_l = QVBoxLayout(self._inner)
        self._inner_l.setSpacing(4)
        self._refresh_comments()
        self._inner_l.addStretch()
        scroll.setWidget(self._inner)
        self._root.addWidget(scroll, 1)

        # New comment input
        self._inp = self.add_field(t('project.traceability.add_comment'), QLineEdit(), height=30)
        self._inp.setPlaceholderText(t('project.traceability.comment_ph'))
        self._inp.returnPressed.connect(self._add_comment)

        # Button row (custom — no OK, only Add + Close)
        btn_row = QHBoxLayout()
        add_btn = self._make_btn(t('project.traceability.add_comment_btn'), MODAL_BTN_PRIMARY, connect=self._add_comment)
        close_btn = self._make_btn(t('common.close'), MODAL_BTN_CANCEL, connect=self.accept)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(close_btn)
        self._root.addLayout(btn_row)

    def _refresh_comments(self):
        while self._inner_l.count():
            item = self._inner_l.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for c in self._part.comments:
            lbl = QLabel(f'• {c}')
            lbl.setWordWrap(True)
            lbl.setStyleSheet(
                f'color: {_TEXT}; font-size: 11px; background: transparent; border: none;'
            )
            self._inner_l.addWidget(lbl)
        if not self._part.comments:
            no = QLabel(t('project.traceability.no_comments'))
            no.setStyleSheet(f'color: {_MUTED}; font-size: 11px; background: transparent; border: none;')
            self._inner_l.addWidget(no)

    def _add_comment(self):
        txt = self._inp.text().strip()
        if not txt:
            return
        self._part.comments.append(txt)
        self._inp.clear()
        self._refresh_comments()
        self._inner_l.addStretch()


# ── Edit Stage ────────────────────────────────────────────────────────────────

class _EditStageDialog(FormModal):
    def __init__(self, stage: TraceStage, stages: list, parent=None):
        can_delete = len(stages) > 1
        super().__init__(parent, t('project.traceability.edit_stage_title'), theme=FormModal.LIGHT, min_width=300)

        self.f_name = self.add_field(t('project.traceability.stage_name'), QLineEdit(stage.name))

        self.f_status = self.add_field(t('project.traceability.status'), QComboBox())
        for _key, _i18n in [
            ('Upcoming',    'project.traceability.status_upcoming'),
            ('In Progress', 'project.traceability.status_in_progress'),
            ('Completed',   'project.traceability.status_completed'),
        ]:
            self.f_status.addItem(t(_i18n), _key)
        for _i in range(self.f_status.count()):
            if self.f_status.itemData(_i) == stage.status:
                self.f_status.setCurrentIndex(_i)
                break

        self.finish(delete=t('project.traceability.delete_stage_btn') if can_delete else None)


# ── Add Component ─────────────────────────────────────────────────────────────

class _AddComponentDialog(FormModal):
    def __init__(self, parent=None):
        super().__init__(parent, t('project.traceability.add_comp_title'), theme=FormModal.LIGHT, min_width=300)
        self._image_path = ''

        self.f_name = self.add_field(t('project.traceability.comp_name_field'), QLineEdit())
        self.f_name.setPlaceholderText(t('project.traceability.comp_name_ph'))

        self.add_widget(self._make_label(t('project.traceability.image_optional')))
        img_row = QHBoxLayout()
        self._img_lbl = QLabel(t('project.traceability.no_image'))
        self._img_lbl.setStyleSheet(
            f'color: {_MUTED}; font-size: 10px; background: transparent; border: none;'
        )
        self._img_lbl.setWordWrap(True)
        browse = self._make_btn(t('project.traceability.browse'), _BTN_SMALL, connect=self._browse)
        browse.setFixedHeight(26)
        img_row.addWidget(self._img_lbl, 1)
        img_row.addWidget(browse)
        self._root.addLayout(img_row)

        self.finish()
        self.f_name.setFocus()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, t('project.traceability.select_image'), '', 'Images (*.png *.jpg *.jpeg *.webp)'
        )
        if path:
            self._image_path = path
            self._img_lbl.setText(os.path.basename(path))

    @property
    def name(self) -> str:
        return self.f_name.text().strip()

    @property
    def image_path(self) -> str:
        return self._image_path


# ── Rename Sub-stage ──────────────────────────────────────────────────────────

class _RenameSubStageDialog(FormModal):
    def __init__(self, current_name: str, parent=None):
        super().__init__(parent, t('project.traceability.rename_substage'), theme=FormModal.LIGHT, min_width=340)
        self.f_name = self.add_field(t('project.traceability.name_field'), QLineEdit(current_name))
        self.f_name.selectAll()
        self.finish()
        self.f_name.setFocus()

    @property
    def name(self) -> str:
        return self.f_name.text().strip()


# ── Edit Component ────────────────────────────────────────────────────────────

class _EditComponentDialog(FormModal):
    def __init__(self, comp: TraceComponent, parent=None):
        super().__init__(parent, t('project.traceability.edit_comp_title'), theme=FormModal.LIGHT, min_width=340)
        self._image_path = comp.image_path

        self.f_name = self.add_field(t('project.traceability.comp_name_field'), QLineEdit(comp.name))

        self.add_widget(self._make_label(t('project.traceability.image_optional')))
        img_row = QHBoxLayout()
        self._img_lbl = QLabel(comp.image_path or t('project.traceability.no_image_set'))
        self._img_lbl.setStyleSheet(
            f'color: {_MUTED}; font-size: 10px; background: transparent; border: none;'
        )
        self._img_lbl.setWordWrap(True)
        browse = self._make_btn(t('project.traceability.browse'), _BTN_SMALL, connect=self._browse)
        browse.setFixedHeight(26)
        img_row.addWidget(self._img_lbl, 1)
        img_row.addWidget(browse)
        self._root.addLayout(img_row)

        self.finish(delete=t('project.traceability.delete_comp_btn') if not comp.is_main else None)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, t('project.traceability.select_image'), '', 'Images (*.png *.jpg *.jpeg *.webp)'
        )
        if path:
            self._image_path = path
            self._img_lbl.setText(path)

    @property
    def name(self) -> str:
        return self.f_name.text().strip()

    @property
    def image_path(self) -> str:
        return self._image_path

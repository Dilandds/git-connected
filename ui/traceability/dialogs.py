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
from .models import TracePart, TraceStage, TraceComponent, TraceSubStage
from .shared import _BTN_SMALL, _BTN_PRIMARY, _MUTED, _TEXT, _CARD
from i18n import t


# ── Add / Edit Part ───────────────────────────────────────────────────────────

class _PartDialog(FormModal):
    def __init__(self, part: Optional[TracePart] = None, parent=None):
        super().__init__(parent,
                         t('project.traceability.edit_part_title') if part else t('project.traceability.add_part_title'),
                         min_width=420)

        self.f_name = self.add_field(t('project.traceability.part_name'), QLineEdit(part.name if part else ''))
        self.f_name.setPlaceholderText(t('project.traceability.part_name_ph'))

        self.f_subject = self.add_field(t('project.traceability.subject'), QLineEdit(part.subject if part else ''))
        self.f_subject.setPlaceholderText(t('project.traceability.subject_ph'))

        self.f_performed_by = self.add_field(t('project.traceability.performed_by'), QLineEdit(part.performed_by if part else ''))
        self.f_performed_by.setPlaceholderText(t('project.traceability.performed_by_ph'))

        self.f_suppliers = self.add_field(t('project.traceability.suppliers'), QLineEdit(part.suppliers if part else ''))
        self.f_suppliers.setPlaceholderText(t('project.traceability.suppliers_ph'))

        self.f_action = self.add_field(t('project.traceability.action'), QLineEdit(part.action if part else ''))
        self.f_action.setPlaceholderText(t('project.traceability.action_ph'))

        self.f_task = self.add_field(t('project.traceability.current_task'), QTextEdit(), height_override=52)
        self.f_task.setPlaceholderText(t('project.traceability.current_task_ph'))
        if part:
            self.f_task.setPlainText(part.current_task)

        self.f_start, self.f_due = self.add_row_fields(
            (t('project.traceability.start_date_field'), QLineEdit(part.start_date if part else '')),
            (t('project.traceability.due_date_field'),   QLineEdit(part.due_date   if part else '')),
        )
        self.f_start.setPlaceholderText(t('project.traceability.date_ph'))
        self.f_due.setPlaceholderText(t('project.traceability.date_ph'))

        status_cb = QComboBox()
        status_cb.addItems([
            t('project.traceability.status_upcoming'),
            t('project.traceability.status_in_progress'),
            t('project.traceability.status_completed'),
        ])
        if part:
            idx = status_cb.findText(part.status)
            if idx >= 0:
                status_cb.setCurrentIndex(idx)

        progress_spin = QSpinBox()
        progress_spin.setRange(0, 100)
        progress_spin.setValue(part.progress if part else 0)

        self.f_status, self.f_progress = self.add_row_fields(
            (t('project.traceability.status'),       status_cb),
            (t('project.traceability.progress_pct'), progress_spin),
        )
        self.finish()

    def get_data(self) -> dict:
        return {
            'name':         self.f_name.text().strip() or 'Part',
            'subject':      self.f_subject.text().strip(),
            'performed_by': self.f_performed_by.text().strip(),
            'suppliers':    self.f_suppliers.text().strip(),
            'action':       self.f_action.text().strip(),
            'current_task': self.f_task.toPlainText().strip(),
            'start_date':   self.f_start.text().strip(),
            'due_date':     self.f_due.text().strip(),
            'status':       self.f_status.currentText(),
            'progress':     self.f_progress.value(),
        }


# ── Comments dialog ───────────────────────────────────────────────────────────

class _CommentsDialog(FormModal):
    """Scrollable comments list + inline add-comment input."""

    def __init__(self, part: TracePart, parent=None):
        super().__init__(parent, t('project.traceability.comments_title').format(name=part.name), min_width=360)
        self._part = part

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
        super().__init__(parent, t('project.traceability.edit_stage_title'), min_width=300)

        self.f_name = self.add_field(t('project.traceability.stage_name'), QLineEdit(stage.name))

        self.f_status = self.add_field(t('project.traceability.status'), QComboBox())
        self.f_status.addItems([
            t('project.traceability.status_upcoming'),
            t('project.traceability.status_in_progress'),
            t('project.traceability.status_completed'),
        ])
        self.f_status.setCurrentText(stage.status)

        self.finish(delete=t('project.traceability.delete_stage_btn') if can_delete else None)


# ── Add Component ─────────────────────────────────────────────────────────────

class _AddComponentDialog(FormModal):
    def __init__(self, parent=None):
        super().__init__(parent, t('project.traceability.add_comp_title'), min_width=300)
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
        super().__init__(parent, t('project.traceability.rename_substage'), min_width=340)
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
        super().__init__(parent, t('project.traceability.edit_comp_title'), min_width=340)
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

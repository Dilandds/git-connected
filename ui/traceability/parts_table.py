from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QDialog,
)
from PyQt5.QtCore import Qt, pyqtSignal
from ui.modal_utils import ask_yes_no_dialog
from .models import TracePart, TraceSubStage
from .shared import (
    _BG, _CARD, _BORDER, _TEXT, _MUTED, _ACCENT,
    _PART_PALETTE, _PartBadge,
)
from .models import TraceTask
from .dialogs import _PartDialog, _TaskDialog
from .part_row import _PartGroupRow, _FlatPartRow, _W_TASK, _W_SUBJECT, _W_PERFORMED_BY, _W_COMMENTS, _W_DATE, _W_STATUS, _W_PROGRESS
from i18n import t


class _PartsTable(QWidget):
    changed = pyqtSignal()

    def __init__(self, sub_stage: TraceSubStage,
                 stage_num: int = 1, sub_num: int = 1,
                 flat_mode: bool = False, parent=None):
        super().__init__(parent)
        self._sub       = sub_stage
        self._stage_num = stage_num
        self._sub_num   = sub_num
        self._flat      = flat_mode
        self._next_id   = max((p.id for p in sub_stage.parts), default=0) + 1
        self._read_only = False
        self.setStyleSheet(f'background: {_CARD};')
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Column headers ────────────────────────────────────────────────
        hdr = QWidget()
        hdr.setFixedHeight(34)
        hdr.setStyleSheet(
            f'background: #f8f9fa;'
            f' border-bottom: 1px solid {_BORDER};'
            f' border-top: 1px solid {_BORDER};'
        )
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(16, 0, 12, 0)
        hl.setSpacing(0)

        def _ch(text, w=None):
            l = QLabel(text)
            if w:
                l.setFixedWidth(w)
            l.setStyleSheet(
                f'color: {_MUTED}; font-size: 11px; font-weight: 700;'
                f' background: transparent; border: none; letter-spacing: 0.8px;'
            )
            return l

        hl.addSpacing(38 + 12)
        hl.addWidget(_ch(t('project.traceability.col_task'), _W_TASK))
        hl.addStretch(1)
        hl.addWidget(_ch(t('project.traceability.col_subject'), _W_SUBJECT))
        hl.addWidget(_ch(t('project.traceability.col_performed_by'), _W_PERFORMED_BY))
        hl.addWidget(_ch(t('project.traceability.col_comments'), _W_COMMENTS))
        hl.addWidget(_ch(t('project.traceability.col_start_date'), _W_DATE))
        hl.addWidget(_ch(t('project.traceability.col_due_date'), _W_DATE))
        hl.addWidget(_ch(t('project.traceability.col_status'), _W_STATUS))
        hl.addSpacing(12)
        hl.addWidget(_ch(t('project.traceability.col_progress'), _W_PROGRESS))
        hl.addSpacing(28)
        root.addWidget(hdr)

        # ── Part group rows ───────────────────────────────────────────────
        self._rows_w = QWidget()
        self._rows_w.setStyleSheet(f'background: {_CARD};')
        self._rows_l = QVBoxLayout(self._rows_w)
        self._rows_l.setContentsMargins(0, 0, 0, 0)
        self._rows_l.setSpacing(0)
        root.addWidget(self._rows_w)

        # ── Add Part footer ───────────────────────────────────────────────
        self._footer = self._make_add_row()
        root.addWidget(self._footer)

        # ── Bottom hint ───────────────────────────────────────────────────
        if self._flat:
            hint_text = t('project.traceability.hint_tasks')
        else:
            hint_text = t('project.traceability.hint_parts')
        hint = QLabel(hint_text)
        hint.setStyleSheet(
            f'color: {_MUTED}; font-size: 11px; background: {_BG};'
            f' border-top: 1px solid {_BORDER}; padding: 6px 16px;'
        )
        root.addWidget(hint)

        self._refresh_rows()

    def _make_add_row(self) -> QWidget:
        label = t('project.traceability.add_task') if self._flat else t('project.traceability.add_part')
        row = QWidget()
        row.setFixedHeight(48)
        row.setStyleSheet(f'background: {_BG}; border-top: 1px dashed {_BORDER};')
        lay = QHBoxLayout(row)
        lay.setContentsMargins(16, 0, 12, 0)
        lay.setSpacing(12)

        next_idx = len(self._sub.parts)
        badge_label = f'{self._stage_num}.{self._sub_num}.{next_idx + 1}'
        badge = _PartBadge(next_idx + 1, '#d1d5db', label=badge_label, size=38)
        lay.addWidget(badge, 0, Qt.AlignVCenter)

        add_lbl = QPushButton(label)
        add_lbl.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {_ACCENT}; font-size: 13px; font-weight: 600;
                padding: 0; text-align: left;
            }}
            QPushButton:hover {{ color: #1d4ed8; text-decoration: underline; }}
        """)
        add_lbl.setCursor(Qt.PointingHandCursor)
        add_lbl.setEnabled(not self._read_only)
        add_lbl.clicked.connect(self._add_part)
        lay.addWidget(add_lbl)
        lay.addStretch()

        add_btn = QPushButton(label)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {_ACCENT};
                border: 1px solid {_ACCENT}; border-radius: 5px;
                padding: 4px 12px; font-size: 12px; font-weight: 600;
            }}
            QPushButton:hover {{ background: #eff6ff; }}
        """)
        add_btn.setFixedHeight(28)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setEnabled(not self._read_only)
        add_btn.clicked.connect(self._add_part)
        lay.addWidget(add_btn, 0, Qt.AlignVCenter)

        return row

    def _refresh_rows(self):
        while self._rows_l.count():
            item = self._rows_l.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().setParent(None)

        if not self._sub.parts:
            empty_text = t('project.traceability.no_tasks_empty') if self._flat else t('project.traceability.no_parts_empty')
            empty = QLabel(empty_text)
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(
                f'color: {_MUTED}; font-size: 13px;'
                f' background: transparent; border: none; padding: 28px;'
            )
            self._rows_l.addWidget(empty)
        elif self._flat:
            for i, part in enumerate(self._sub.parts):
                row = _FlatPartRow(part, i,
                                   stage_num=self._stage_num,
                                   sub_num=self._sub_num)
                row.edit_requested.connect(self._edit_part)
                row.delete_requested.connect(self._delete_part)
                row.data_changed.connect(self.changed)
                row.set_read_only(self._read_only)
                self._rows_l.addWidget(row)
        else:
            for i, part in enumerate(self._sub.parts):
                row = _PartGroupRow(part, i,
                                    stage_num=self._stage_num,
                                    sub_num=self._sub_num)
                row.edit_requested.connect(self._edit_part)
                row.delete_requested.connect(self._delete_part)
                row.changed.connect(self.changed)
                row.set_read_only(self._read_only)
                self._rows_l.addWidget(row)

        # Rebuild footer so badge number stays correct
        old = self._footer
        self._footer = self._make_add_row()
        self.layout().replaceWidget(old, self._footer)
        old.hide(); old.setParent(None)

    def set_read_only(self, read_only: bool):
        """Disable the add-part/add-task footer controls and cascade into
        every part row (_FlatPartRow for the main/flat component,
        _PartGroupRow otherwise). _refresh_rows() rebuilds both the footer
        and the rows, so this also re-applies the flag to rows added or
        removed at runtime."""
        self._read_only = read_only
        self._refresh_rows()

    def _add_part(self):
        if self._read_only:
            return
        if self._flat:
            dlg = _TaskDialog(parent=self)
            if dlg.exec_() != QDialog.Accepted:
                return
            d = dlg.get_data()
            task = TraceTask(id=1, **d)
            self._sub.parts.append(TracePart(id=self._next_id, name=d['name'], tasks=[task]))
        else:
            dlg = _PartDialog(parent=self)
            if dlg.exec_() != QDialog.Accepted:
                return
            self._sub.parts.append(TracePart(id=self._next_id, **dlg.get_data()))
        self._next_id += 1
        self._refresh_rows()
        self.changed.emit()

    def _edit_part(self, part: TracePart):
        if self._flat:
            task = part.tasks[0] if part.tasks else None
            dlg = _TaskDialog(task=task, parent=self)
            if dlg.exec_() != QDialog.Accepted:
                return
            d = dlg.get_data()
            part.name = d['name']
            if part.tasks:
                for k, v in d.items():
                    setattr(part.tasks[0], k, v)
            else:
                part.tasks = [TraceTask(id=1, **d)]
        else:
            dlg = _PartDialog(part=part, parent=self)
            if dlg.exec_() != QDialog.Accepted:
                return
            part.name = dlg.get_data()['name']
        self._refresh_rows()
        self.changed.emit()

    def _delete_part(self, part: TracePart):
        if not ask_yes_no_dialog(self, 'Delete Part',
                                  f"Delete '{part.name}' and all its tasks? This cannot be undone."):
            return
        self._sub.parts.remove(part)
        self._refresh_rows()
        self.changed.emit()

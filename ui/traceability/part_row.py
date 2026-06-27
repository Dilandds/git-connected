from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QWidget,
    QTextEdit, QDialog,
)
from PyQt5.QtCore import Qt, pyqtSignal
from .models import TracePart, TraceTask, TraceStep
from .shared import (
    _TEXT, _MUTED, _BORDER, _CARD, _BG, _ACCENT,
    _PART_PALETTE, _BTN_SMALL, _BTN_ICON, _BTN_DELETE,
    _PartBadge, _ProgressBar, _status_badge,
)
from .dialogs import _TaskDialog, _StepDialog, _CommentsDialog, _PartDialog
from ui.modal_utils import ask_yes_no_dialog
from i18n import t

# Column widths — must match headers in parts_table.py
_W_TASK         = 200
_W_SUBJECT      = 160
_W_PERFORMED_BY = 140
_W_COMMENTS     = 200
_W_DATE         = 105
_W_STATUS       = 108
_W_PROGRESS     = 200
_ROW_H          = 100
_GROUP_H        = 44
_STEP_H         = 38


def _date_cell(date_str: str) -> QWidget:
    w = QWidget(); w.setFixedWidth(_W_DATE); w.setStyleSheet('background: transparent;')
    lay = QHBoxLayout(w); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(5)
    icon = QLabel('📅')
    icon.setStyleSheet('font-size: 11px; background: transparent; border: none;')
    lbl = QLabel(date_str or '—')
    lbl.setStyleSheet(f'color: {_MUTED}; font-size: 10px; background: transparent; border: none;')
    lay.addWidget(icon); lay.addWidget(lbl); lay.addStretch()
    return w


def _status_pill(status: str) -> QLabel:
    colors = {
        'Completed':   ('#16a34a', '#dcfce7'),
        'In Progress': ('#2563eb', '#dbeafe'),
        'Upcoming':    ('#6b7280', '#f3f4f6'),
    }
    fg, bg = colors.get(status, ('#6b7280', '#f3f4f6'))
    lbl = QLabel(status)
    lbl.setFixedWidth(_W_STATUS)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setStyleSheet(f"""
        QLabel {{
            background: {bg}; color: {fg};
            border: 1px solid {fg}55; border-radius: 6px;
            padding: 4px 10px; font-size: 10px; font-weight: 700;
        }}
    """)
    return lbl


# ── Flat part row (main component — one task per part, no nesting) ────────────

class _FlatPartRow(QWidget):
    """Old-style flat row for the Main component. Treats part.tasks[0] as the task data."""
    edit_requested   = pyqtSignal(object)   # emits TracePart
    delete_requested = pyqtSignal(object)   # emits TracePart
    data_changed     = pyqtSignal()

    def __init__(self, part: TracePart, part_idx: int,
                 stage_num: int, sub_num: int, parent=None):
        super().__init__(parent)
        self._part      = part
        self._part_idx  = part_idx
        self._stage_num = stage_num
        self._sub_num   = sub_num
        # Use first task or a default placeholder
        self._task = part.tasks[0] if part.tasks else TraceTask(id=1, name=part.name)
        self.setStyleSheet(f'background: {_CARD};')
        self._build()

    def _build(self):
        self.setFixedHeight(_ROW_H)
        self.setStyleSheet(f"""
            QWidget {{
                background: {_CARD};
                border-bottom: 1px solid {_BORDER};
            }}
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 10, 12, 10)
        lay.setSpacing(0)

        badge_label = f'{self._stage_num}.{self._sub_num}.{self._part_idx + 1}'
        badge = _PartBadge(
            self._part_idx + 1,
            _PART_PALETTE[self._part_idx % len(_PART_PALETTE)],
            label=badge_label, size=38,
        )
        lay.addWidget(badge, 0, Qt.AlignVCenter)
        lay.addSpacing(12)

        # Task name + description block
        task_w = QWidget(); task_w.setFixedWidth(_W_TASK); task_w.setStyleSheet('background: transparent;')
        task_l = QVBoxLayout(task_w); task_l.setContentsMargins(0, 0, 0, 0); task_l.setSpacing(3)
        name_lbl = QLabel(self._task.name)
        name_lbl.setStyleSheet(f'color: {_TEXT}; font-size: 12px; font-weight: 700; background: transparent; border: none;')
        task_l.addWidget(name_lbl)
        desc_parts = [x for x in [self._task.suppliers, self._task.action, self._task.current_task] if x]
        if desc_parts:
            desc_lbl = QLabel('  ·  '.join(desc_parts))
            desc_lbl.setStyleSheet(f'color: {_MUTED}; font-size: 10px; background: transparent; border: none;')
            desc_lbl.setWordWrap(True)
            task_l.addWidget(desc_lbl)
        lay.addWidget(task_w)
        lay.addStretch(1)

        subj_lbl = QLabel(self._task.subject or '—')
        subj_lbl.setFixedWidth(_W_SUBJECT); subj_lbl.setWordWrap(True)
        subj_lbl.setStyleSheet(f'color: {_TEXT}; font-size: 11px; background: transparent; border: none;')
        lay.addWidget(subj_lbl, 0, Qt.AlignVCenter)

        perf_lbl = QLabel(self._task.performed_by or '—')
        perf_lbl.setFixedWidth(_W_PERFORMED_BY); perf_lbl.setWordWrap(True)
        perf_lbl.setStyleSheet(f'color: {_TEXT}; font-size: 11px; background: transparent; border: none;')
        lay.addWidget(perf_lbl, 0, Qt.AlignVCenter)

        comm_edit = QTextEdit()
        comm_edit.setFixedWidth(_W_COMMENTS); comm_edit.setFixedHeight(62)
        comm_edit.setPlaceholderText('Add a comment…')
        comm_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        comm_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        comm_edit.setStyleSheet(f"""
            QTextEdit {{ background: #f8f9fa; border: 1px solid {_BORDER};
                border-radius: 5px; padding: 4px 6px; color: {_TEXT}; font-size: 10px; }}
            QTextEdit:focus {{ border-color: {_ACCENT}; background: white; }}
        """)
        if self._task.comments:
            comm_edit.setPlainText('\n'.join(self._task.comments))
        def _on_comment():
            lines = [l for l in comm_edit.toPlainText().splitlines() if l.strip()]
            self._task.comments = lines
            self.data_changed.emit()
        comm_edit.textChanged.connect(_on_comment)
        lay.addWidget(comm_edit, 0, Qt.AlignVCenter)

        lay.addWidget(_date_cell(self._task.start_date))
        lay.addWidget(_date_cell(self._task.due_date))
        lay.addWidget(_status_pill(self._task.status), 0, Qt.AlignVCenter)
        lay.addSpacing(12)

        prog_w = QWidget(); prog_w.setFixedWidth(_W_PROGRESS); prog_w.setStyleSheet('background: transparent;')
        prog_l = QHBoxLayout(prog_w); prog_l.setContentsMargins(0, 0, 0, 0); prog_l.setSpacing(10)
        pct_bar = QWidget(); pct_bar.setStyleSheet('background: transparent;')
        pct_bar_l = QVBoxLayout(pct_bar); pct_bar_l.setContentsMargins(0, 0, 0, 0); pct_bar_l.setSpacing(4)
        pct_lbl = QLabel(f'{self._task.progress} %')
        pct_lbl.setStyleSheet(f'color: {_TEXT}; font-size: 12px; font-weight: 700; background: transparent; border: none;')
        pct_bar_l.addWidget(pct_lbl)
        pct_bar_l.addWidget(_ProgressBar(self._task.progress))
        prog_l.addWidget(pct_bar)
        prog_l.addStretch()
        lay.addWidget(prog_w, 0, Qt.AlignVCenter)

        _ACT = 'QPushButton { background: transparent; border: none; font-size: 11px; font-weight: 600; padding: 2px 6px; }'
        edit_btn = QPushButton('Edit')
        edit_btn.setStyleSheet(_ACT + f'QPushButton {{ color: {_ACCENT}; }} QPushButton:hover {{ color: #1d6fc4; text-decoration: underline; }}')
        edit_btn.setCursor(Qt.PointingHandCursor)
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self._part))
        del_btn = QPushButton('Delete')
        del_btn.setStyleSheet(_ACT + 'QPushButton { color: #ef4444; } QPushButton:hover { color: #b91c1c; text-decoration: underline; }')
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._part))
        actions_w = QWidget(); actions_w.setStyleSheet('background: transparent;')
        actions_l = QVBoxLayout(actions_w); actions_l.setContentsMargins(0, 0, 0, 0); actions_l.setSpacing(2)
        actions_l.addWidget(edit_btn, 0, Qt.AlignLeft)
        actions_l.addWidget(del_btn, 0, Qt.AlignLeft)
        lay.addWidget(actions_w, 0, Qt.AlignVCenter)


# ── Sub-step row ──────────────────────────────────────────────────────────────

class _StepRow(QFrame):
    edit_requested   = pyqtSignal(object)
    delete_requested = pyqtSignal(object)

    def __init__(self, step: TraceStep, step_num_label: str, parent=None):
        super().__init__(parent)
        self._step = step
        self.setFixedHeight(_STEP_H)
        self.setStyleSheet(f"""
            QFrame {{
                background: #f8faff;
                border: none;
                border-bottom: 1px solid {_BORDER};
                border-left: 3px solid {_ACCENT}44;
            }}
        """)
        self._build(step_num_label)

    def _build(self, label: str):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(52, 4, 12, 4)
        lay.setSpacing(10)

        num = QLabel(label)
        num.setFixedWidth(60)
        num.setStyleSheet(f'color: {_MUTED}; font-size: 10px; font-weight: 700; background: transparent; border: none;')
        lay.addWidget(num)

        name = QLabel(self._step.name)
        name.setStyleSheet(f'color: {_TEXT}; font-size: 11px; font-weight: 600; background: transparent; border: none;')
        lay.addWidget(name, 1)

        if self._step.description:
            desc = QLabel(self._step.description)
            desc.setStyleSheet(f'color: {_MUTED}; font-size: 10px; background: transparent; border: none;')
            desc.setWordWrap(True)
            lay.addWidget(desc, 1)

        lay.addWidget(_status_badge(self._step.status))

        pct = QLabel(f'{self._step.progress}%')
        pct.setStyleSheet(f'color: {_MUTED}; font-size: 10px; background: transparent; border: none;')
        lay.addWidget(pct)

        _ACT = 'QPushButton { background: transparent; border: none; font-size: 10px; padding: 1px 4px; }'
        edit_btn = QPushButton('Edit')
        edit_btn.setStyleSheet(_ACT + f'QPushButton {{ color: {_ACCENT}; }} QPushButton:hover {{ text-decoration: underline; }}')
        edit_btn.setCursor(Qt.PointingHandCursor)
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self._step))
        lay.addWidget(edit_btn)

        del_btn = QPushButton('✕')
        del_btn.setStyleSheet(_ACT + 'QPushButton { color: #ef4444; } QPushButton:hover { color: #b91c1c; }')
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._step))
        lay.addWidget(del_btn)


# ── Task row (within a part group) ───────────────────────────────────────────

class _TaskRow(QWidget):
    edit_requested    = pyqtSignal(object)
    delete_requested  = pyqtSignal(object)
    comment_requested = pyqtSignal(object)
    data_changed      = pyqtSignal()

    def __init__(self, task: TraceTask, task_idx: int,
                 stage_num: int, sub_num: int, part_num: int, parent=None):
        super().__init__(parent)
        self._task      = task
        self._task_idx  = task_idx
        self._stage_num = stage_num
        self._sub_num   = sub_num
        self._part_num  = part_num
        self._steps_expanded = False
        self.setStyleSheet(f'background: {_CARD};')
        self._build()

    def _build(self):
        self._root_l = QVBoxLayout(self)
        self._root_l.setContentsMargins(0, 0, 0, 0)
        self._root_l.setSpacing(0)

        # ── Main task row ──────────────────────────────────────────────────
        self._row_frame = QFrame()
        self._row_frame.setFixedHeight(_ROW_H)
        self._row_frame.setStyleSheet(f"""
            QFrame {{
                background: {_CARD}; border: none;
                border-bottom: 1px solid {_BORDER};
            }}
        """)
        lay = QHBoxLayout(self._row_frame)
        lay.setContentsMargins(16, 10, 12, 10)
        lay.setSpacing(0)

        badge_label = f'{self._stage_num}.{self._sub_num}.{self._part_num}.{self._task_idx + 1}'
        badge = _PartBadge(
            self._task_idx + 1,
            _PART_PALETTE[self._task_idx % len(_PART_PALETTE)],
            label=badge_label,
            size=32,
        )
        lay.addWidget(badge, 0, Qt.AlignVCenter)
        lay.addSpacing(12)

        # TASK column
        task_w = QWidget(); task_w.setFixedWidth(_W_TASK); task_w.setStyleSheet('background: transparent;')
        task_l = QVBoxLayout(task_w); task_l.setContentsMargins(0, 0, 0, 0); task_l.setSpacing(3)
        name_lbl = QLabel(self._task.name)
        name_lbl.setStyleSheet(f'color: {_TEXT}; font-size: 12px; font-weight: 700; background: transparent; border: none;')
        task_l.addWidget(name_lbl)
        desc_parts = [x for x in [self._task.suppliers, self._task.action, self._task.current_task] if x]
        if desc_parts:
            desc_lbl = QLabel('  ·  '.join(desc_parts))
            desc_lbl.setStyleSheet(f'color: {_MUTED}; font-size: 10px; background: transparent; border: none;')
            desc_lbl.setWordWrap(True)
            task_l.addWidget(desc_lbl)
        lay.addWidget(task_w)
        lay.addStretch(1)

        subj_lbl = QLabel(self._task.subject or '—')
        subj_lbl.setFixedWidth(_W_SUBJECT); subj_lbl.setWordWrap(True)
        subj_lbl.setStyleSheet(f'color: {_TEXT}; font-size: 11px; background: transparent; border: none;')
        lay.addWidget(subj_lbl, 0, Qt.AlignVCenter)

        perf_lbl = QLabel(self._task.performed_by or '—')
        perf_lbl.setFixedWidth(_W_PERFORMED_BY); perf_lbl.setWordWrap(True)
        perf_lbl.setStyleSheet(f'color: {_TEXT}; font-size: 11px; background: transparent; border: none;')
        lay.addWidget(perf_lbl, 0, Qt.AlignVCenter)

        comm_edit = QTextEdit()
        comm_edit.setFixedWidth(_W_COMMENTS); comm_edit.setFixedHeight(62)
        comm_edit.setPlaceholderText('Add a comment…')
        comm_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        comm_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        comm_edit.setStyleSheet(f"""
            QTextEdit {{ background: #f8f9fa; border: 1px solid {_BORDER};
                border-radius: 5px; padding: 4px 6px; color: {_TEXT}; font-size: 10px; }}
            QTextEdit:focus {{ border-color: {_ACCENT}; background: white; }}
        """)
        if self._task.comments:
            comm_edit.setPlainText('\n'.join(self._task.comments))
        def _on_comment():
            lines = [l for l in comm_edit.toPlainText().splitlines() if l.strip()]
            self._task.comments = lines
            self.data_changed.emit()
        comm_edit.textChanged.connect(_on_comment)
        lay.addWidget(comm_edit, 0, Qt.AlignVCenter)

        lay.addWidget(_date_cell(self._task.start_date))
        lay.addWidget(_date_cell(self._task.due_date))
        lay.addWidget(_status_pill(self._task.status), 0, Qt.AlignVCenter)
        lay.addSpacing(12)

        prog_w = QWidget(); prog_w.setFixedWidth(_W_PROGRESS); prog_w.setStyleSheet('background: transparent;')
        prog_l = QHBoxLayout(prog_w); prog_l.setContentsMargins(0, 0, 0, 0); prog_l.setSpacing(10)
        pct_bar = QWidget(); pct_bar.setStyleSheet('background: transparent;')
        pct_bar_l = QVBoxLayout(pct_bar); pct_bar_l.setContentsMargins(0, 0, 0, 0); pct_bar_l.setSpacing(4)
        pct_lbl = QLabel(f'{self._task.progress} %')
        pct_lbl.setStyleSheet(f'color: {_TEXT}; font-size: 12px; font-weight: 700; background: transparent; border: none;')
        pct_bar_l.addWidget(pct_lbl)
        pct_bar_l.addWidget(_ProgressBar(self._task.progress))
        prog_l.addWidget(pct_bar)
        n_comments = len(self._task.comments)
        count_btn = QPushButton(f'  {n_comments}')
        count_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none; color: {_MUTED}; font-size: 10px; padding: 0; }}
            QPushButton:hover {{ color: {_ACCENT}; }}
        """)
        count_btn.setFixedWidth(34); count_btn.setCursor(Qt.PointingHandCursor)
        count_btn.clicked.connect(lambda: self.comment_requested.emit(self._task))
        prog_l.addWidget(count_btn, 0, Qt.AlignVCenter)
        prog_l.addStretch()
        lay.addWidget(prog_w, 0, Qt.AlignVCenter)

        _ACT = 'QPushButton { background: transparent; border: none; font-size: 11px; font-weight: 600; padding: 2px 6px; }'
        edit_btn = QPushButton('Edit')
        edit_btn.setStyleSheet(_ACT + f'QPushButton {{ color: {_ACCENT}; }} QPushButton:hover {{ color: #1d6fc4; text-decoration: underline; }}')
        edit_btn.setCursor(Qt.PointingHandCursor)
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self._task))
        del_btn = QPushButton('Delete')
        del_btn.setStyleSheet(_ACT + 'QPushButton { color: #ef4444; } QPushButton:hover { color: #b91c1c; text-decoration: underline; }')
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._task))
        actions_w = QWidget(); actions_w.setStyleSheet('background: transparent;')
        actions_l = QVBoxLayout(actions_w); actions_l.setContentsMargins(0, 0, 0, 0); actions_l.setSpacing(2)
        actions_l.addWidget(edit_btn, 0, Qt.AlignLeft)
        actions_l.addWidget(del_btn, 0, Qt.AlignLeft)
        lay.addWidget(actions_w, 0, Qt.AlignVCenter)

        # Steps toggle button
        self._steps_btn = QPushButton('▶ Steps')
        self._steps_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: 1px solid {_BORDER};
                border-radius: 4px; color: {_MUTED}; font-size: 10px; padding: 2px 8px; }}
            QPushButton:hover {{ border-color: {_ACCENT}; color: {_ACCENT}; background: #eff6ff; }}
        """)
        self._steps_btn.setFixedHeight(22)
        self._steps_btn.setCursor(Qt.PointingHandCursor)
        self._steps_btn.clicked.connect(self._toggle_steps)
        lay.addSpacing(6)
        lay.addWidget(self._steps_btn, 0, Qt.AlignVCenter)

        self._root_l.addWidget(self._row_frame)

        # ── Steps container (hidden by default) ────────────────────────────
        self._steps_container = QWidget()
        self._steps_container.setStyleSheet(f'background: #f8faff;')
        self._steps_container.hide()
        self._steps_l = QVBoxLayout(self._steps_container)
        self._steps_l.setContentsMargins(0, 0, 0, 0)
        self._steps_l.setSpacing(0)
        self._root_l.addWidget(self._steps_container)

        self._refresh_steps()

    def _toggle_steps(self):
        self._steps_expanded = not self._steps_expanded
        self._steps_container.setVisible(self._steps_expanded)
        self._steps_btn.setText(f'{"▼" if self._steps_expanded else "▶"} Steps ({len(self._task.steps)})')

    def _refresh_steps(self):
        while self._steps_l.count():
            item = self._steps_l.takeAt(0)
            if item.widget():
                item.widget().hide(); item.widget().setParent(None)

        for i, step in enumerate(self._task.steps):
            step_label = f'{self._stage_num}.{self._sub_num}.{self._part_num}.{self._task_idx + 1}.{i + 1}'
            row = _StepRow(step, step_label)
            row.edit_requested.connect(self._edit_step)
            row.delete_requested.connect(self._delete_step)
            self._steps_l.addWidget(row)

        # Add step footer
        add_row = QWidget()
        add_row.setFixedHeight(32)
        add_row.setStyleSheet(f'background: #f0f4ff; border-bottom: 1px solid {_BORDER};')
        add_lay = QHBoxLayout(add_row); add_lay.setContentsMargins(52, 0, 12, 0); add_lay.setSpacing(8)
        add_btn = QPushButton('＋  Add Sub-step')
        add_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none; color: {_ACCENT};
                font-size: 11px; font-weight: 600; padding: 0; text-align: left; }}
            QPushButton:hover {{ color: #1d4ed8; text-decoration: underline; }}
        """)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._add_step)
        add_lay.addWidget(add_btn)
        add_lay.addStretch()
        self._steps_l.addWidget(add_row)

        self._steps_btn.setText(f'{"▼" if self._steps_expanded else "▶"} Steps ({len(self._task.steps)})')

    def _add_step(self):
        dlg = _StepDialog(parent=self)
        if dlg.exec_() != QDialog.Accepted:
            return
        next_id = max((s.id for s in self._task.steps), default=0) + 1
        self._task.steps.append(TraceStep(id=next_id, **dlg.get_data()))
        self._refresh_steps()
        self.data_changed.emit()

    def _edit_step(self, step: TraceStep):
        dlg = _StepDialog(step=step, parent=self)
        if dlg.exec_() != QDialog.Accepted:
            return
        for k, v in dlg.get_data().items():
            setattr(step, k, v)
        self._refresh_steps()
        self.data_changed.emit()

    def _delete_step(self, step: TraceStep):
        if not ask_yes_no_dialog(self, 'Delete Sub-step', f"Delete '{step.name}'? This cannot be undone."):
            return
        self._task.steps.remove(step)
        self._refresh_steps()
        self.data_changed.emit()


# ── Part group row (collapsible header for a TracePart) ───────────────────────

class _PartGroupRow(QWidget):
    changed          = pyqtSignal()
    edit_requested   = pyqtSignal(object)
    delete_requested = pyqtSignal(object)

    def __init__(self, part: TracePart, part_idx: int,
                 stage_num: int, sub_num: int, parent=None):
        super().__init__(parent)
        self._part      = part
        self._part_num  = part_idx + 1
        self._stage_num = stage_num
        self._sub_num   = sub_num
        self._expanded  = True
        self._next_task_id = max((tk.id for tk in part.tasks), default=0) + 1
        self.setStyleSheet(f'background: {_CARD};')
        self._build()

    def _build(self):
        self._root_l = QVBoxLayout(self)
        self._root_l.setContentsMargins(0, 0, 0, 0)
        self._root_l.setSpacing(0)

        # ── Group header row ───────────────────────────────────────────────
        header = QFrame()
        header.setFixedHeight(_GROUP_H)
        header.setStyleSheet(f"""
            QFrame {{
                background: #f1f5fd;
                border: none;
                border-bottom: 1px solid {_BORDER};
                border-left: 4px solid {_ACCENT};
            }}
        """)
        header.setCursor(Qt.PointingHandCursor)
        header.mousePressEvent = lambda _e: self._toggle()

        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(12, 0, 12, 0)
        h_lay.setSpacing(10)

        self._chevron = QLabel('▼')
        self._chevron.setStyleSheet(f'color: {_ACCENT}; font-size: 11px; background: transparent; border: none;')
        h_lay.addWidget(self._chevron)

        badge_label = f'{self._stage_num}.{self._sub_num}.{self._part_num}'
        badge = _PartBadge(
            self._part_num,
            _PART_PALETTE[(self._part_num - 1) % len(_PART_PALETTE)],
            label=badge_label,
            size=34,
        )
        h_lay.addWidget(badge, 0, Qt.AlignVCenter)

        name_lbl = QLabel(self._part.name)
        name_lbl.setStyleSheet(f'color: {_TEXT}; font-size: 13px; font-weight: 700; background: transparent; border: none;')
        h_lay.addWidget(name_lbl)

        self._count_lbl = QLabel()
        self._count_lbl.setStyleSheet(f'color: {_MUTED}; font-size: 11px; background: transparent; border: none;')
        h_lay.addWidget(self._count_lbl)

        h_lay.addStretch()

        add_task_btn = QPushButton('＋ Add Task')
        add_task_btn.setStyleSheet(_BTN_SMALL)
        add_task_btn.setFixedHeight(26)
        add_task_btn.setCursor(Qt.PointingHandCursor)
        add_task_btn.mousePressEvent = lambda e: (e.accept(), self._add_task())
        h_lay.addWidget(add_task_btn)

        edit_btn = QPushButton('✎')
        edit_btn.setStyleSheet(_BTN_ICON)
        edit_btn.setFixedSize(26, 26)
        edit_btn.setCursor(Qt.PointingHandCursor)
        edit_btn.setToolTip('Rename part group')
        edit_btn.mousePressEvent = lambda e: (e.accept(), self.edit_requested.emit(self._part))
        h_lay.addWidget(edit_btn)

        del_btn = QPushButton('🗑')
        del_btn.setStyleSheet(_BTN_DELETE)
        del_btn.setFixedSize(26, 26)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setToolTip('Delete part group')
        del_btn.mousePressEvent = lambda e: (e.accept(), self.delete_requested.emit(self._part))
        h_lay.addWidget(del_btn)

        self._root_l.addWidget(header)

        # ── Task rows container ────────────────────────────────────────────
        self._tasks_container = QWidget()
        self._tasks_container.setStyleSheet(f'background: {_CARD};')
        self._tasks_l = QVBoxLayout(self._tasks_container)
        self._tasks_l.setContentsMargins(0, 0, 0, 0)
        self._tasks_l.setSpacing(0)
        self._root_l.addWidget(self._tasks_container)

        self._refresh_tasks()

    def _toggle(self):
        self._expanded = not self._expanded
        self._tasks_container.setVisible(self._expanded)
        self._chevron.setText('▼' if self._expanded else '▶')

    def _refresh_tasks(self):
        while self._tasks_l.count():
            item = self._tasks_l.takeAt(0)
            if item.widget():
                item.widget().hide(); item.widget().setParent(None)

        for i, task in enumerate(self._part.tasks):
            row = _TaskRow(task, i, self._stage_num, self._sub_num, self._part_num)
            row.edit_requested.connect(self._edit_task)
            row.delete_requested.connect(self._delete_task)
            row.comment_requested.connect(self._show_comments)
            row.data_changed.connect(self.changed)
            self._tasks_l.addWidget(row)

        # Add task footer
        add_row = QWidget()
        add_row.setFixedHeight(36)
        add_row.setStyleSheet(f'background: {_BG}; border-top: 1px dashed {_BORDER};')
        add_lay = QHBoxLayout(add_row); add_lay.setContentsMargins(24, 0, 12, 0); add_lay.setSpacing(8)
        add_btn = QPushButton('＋  Add Task')
        add_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none; color: {_ACCENT};
                font-size: 12px; font-weight: 600; padding: 0; text-align: left; }}
            QPushButton:hover {{ color: #1d4ed8; text-decoration: underline; }}
        """)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._add_task)
        add_lay.addWidget(add_btn)
        add_lay.addStretch()
        self._tasks_l.addWidget(add_row)

        n = len(self._part.tasks)
        self._count_lbl.setText(f'{n} task{"s" if n != 1 else ""}')

    def _add_task(self):
        dlg = _TaskDialog(parent=self)
        if dlg.exec_() != QDialog.Accepted:
            return
        self._part.tasks.append(TraceTask(id=self._next_task_id, **dlg.get_data()))
        self._next_task_id += 1
        self._refresh_tasks()
        self.changed.emit()

    def _edit_task(self, task: TraceTask):
        dlg = _TaskDialog(task=task, parent=self)
        if dlg.exec_() != QDialog.Accepted:
            return
        for k, v in dlg.get_data().items():
            setattr(task, k, v)
        self._refresh_tasks()
        self.changed.emit()

    def _delete_task(self, task: TraceTask):
        if not ask_yes_no_dialog(self, 'Delete Task', f"Delete '{task.name}'? This cannot be undone."):
            return
        self._part.tasks.remove(task)
        self._refresh_tasks()
        self.changed.emit()

    def _show_comments(self, task: TraceTask):
        from .dialogs import _CommentsDialog
        _CommentsDialog(task, parent=self).exec_()
        self._refresh_tasks()
        self.changed.emit()

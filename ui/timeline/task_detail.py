"""
TaskDetailPanel — right-side inspector panel showing selected task info,
comments, and editable project-management fields.
"""
from typing import Optional
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QLineEdit, QTextEdit, QScrollArea, QFileDialog, QSizePolicy,
    QCheckBox,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QDate
from PyQt5.QtGui import QPixmap
from ui.styles import default_theme
from ui.date_picker import EctoDateEdit
from .models import Task, CARD, BORDER, TEXT, MUTED, ACCENT
from i18n import t

_BTN_DELETE = f"""
    QPushButton {{
        background-color: #fee2e2; color: #ef4444;
        border: 1px solid #fca5a5; border-radius: 6px;
        font-size: 14px; padding: 4px 12px;
    }}
    QPushButton:hover {{ background-color: #ef4444; color: white; border-color: #ef4444; }}
    QPushButton:disabled {{ color: #9ca3af; background-color: #f1f3f5; border-color: {BORDER}; }}
"""

_FIELD_STYLE = f"""
    QLineEdit {{
        background-color: #f5f6f8; color: {TEXT};
        border: 1px solid {BORDER}; border-radius: 5px;
        padding: 2px 6px; font-size: 12px;
    }}
    QLineEdit:focus    {{ border-color: {ACCENT}; }}
    QLineEdit:disabled {{ background-color: #f1f3f5; color: #9ca3af; }}
"""

_TEXTAREA_STYLE = f"""
    QTextEdit {{
        background-color: #eef2f7; color: {TEXT};
        border: 1px solid #c8d4e0; border-radius: 5px;
        font-size: 13px; padding: 4px;
    }}
    QTextEdit:focus {{ border-color: {ACCENT}; }}
"""

_PRIORITY_COLORS = {
    'Low':      ('#16a34a', '#dcfce7'),
    'Normal':   ('#2563eb', '#dbeafe'),
    'High':     ('#d97706', '#fef3c7'),
    'Critical': ('#dc2626', '#fee2e2'),
}

_PANEL_W = 180
_PHOTO_H = 160                              # photo height (half-width column)
_PROG_W  = _PANEL_W - 24                    # usable width for progress bar fill (12px col margins each side)


class TaskDetailPanel(QWidget):
    """Right-side inspector: task details, comments, and PM meta fields."""

    edit_requested   = pyqtSignal(object)
    delete_requested = pyqtSignal(object)
    task_changed     = pyqtSignal()   # emitted when a field mutates the task visually

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_task: Optional[Task] = None
        self._global_pm: str = ''
        self._last_auto_pm: str = ''
        self.setFixedWidth(_PANEL_W)
        self.setStyleSheet(f"""
            QWidget  {{ background-color: {CARD}; border-left: 1px solid {BORDER}; }}
            QLabel   {{ color: {TEXT}; font-size: 14px; background: transparent; border: none; }}
        """)
        self._build_ui()

    # ── layout ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Keep scroll area as safety net but hide the scrollbar
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"QScrollArea {{ background: {CARD}; border: none; }}")

        container = QWidget()
        container.setStyleSheet(f'background: {CARD}; border: none;')
        lay = QVBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        lay.addWidget(self._build_info_section())
        lay.addWidget(self._hline())
        lay.addWidget(self._build_photo_meta_section())    # PM / contributor details
        lay.addWidget(self._hline())
        lay.addWidget(self._build_comment_components_section())  # comments | components
        lay.addWidget(self._hline())
        lay.addWidget(self._build_priority_status_section())
        lay.addStretch()

        scroll.setWidget(container)
        outer.addWidget(scroll)

    def _hline(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f'color: {BORDER}; background: {BORDER}; max-height: 1px; border: none;')
        return sep

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text.upper())
        lbl.setStyleSheet(
            f'color: {MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.7px;'
            f' background: transparent; border: none;'
        )
        return lbl

    def _muted_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f'color: {MUTED}; font-size: 11px; background: transparent; border: none;'
        )
        return lbl

    # ── sections ──────────────────────────────────────────────────────────────

    def _build_info_section(self) -> QWidget:
        w = QWidget(); w.setStyleSheet(f'background: {CARD}; border: none;')
        col = QVBoxLayout(w)
        col.setContentsMargins(12, 10, 12, 8)
        col.setSpacing(2)

        self._lbl_task = QLabel(t('project.timeline.detail_click_task'))
        self._lbl_task.setWordWrap(True)
        self._lbl_task.setStyleSheet(
            f'color: {TEXT}; font-size: 15px; font-weight: bold; '
            f'background: transparent; border: none;'
        )
        col.addWidget(self._lbl_task)

        self._lbl_dates    = QLabel('')
        self._lbl_type     = QLabel('')
        self._lbl_duration = QLabel('')
        for lbl in (self._lbl_dates, self._lbl_type, self._lbl_duration):
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f'color: {MUTED}; font-size: 12px; background: transparent; border: none;')
            col.addWidget(lbl)

        col.addSpacing(4)

        btn_row = QVBoxLayout(); btn_row.setSpacing(6); btn_row.setContentsMargins(0, 0, 0, 0)

        self._edit_btn = QPushButton(t('project.timeline.detail_edit'))
        self._edit_btn.setFixedHeight(28)
        self._edit_btn.setEnabled(False)
        self._edit_btn.setCursor(Qt.PointingHandCursor)
        self._edit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #e5e7eb; color: {MUTED};
                border: 1px solid {BORDER}; border-radius: 4px;
                font-size: 13px; padding: 2px 8px;
            }}
            QPushButton:enabled {{ color: {TEXT}; border-color: #9ca3af; }}
            QPushButton:enabled:hover {{
                background-color: {ACCENT}; color: white; border-color: {ACCENT};
            }}
            QPushButton:disabled {{ color: #9ca3af; background-color: #f1f3f5; }}
        """)
        self._edit_btn.clicked.connect(
            lambda: self._current_task and self.edit_requested.emit(self._current_task)
        )

        self._delete_btn = QPushButton(t('project.timeline.detail_remove'))
        self._delete_btn.setFixedHeight(28)
        self._delete_btn.setEnabled(False)
        self._delete_btn.setCursor(Qt.PointingHandCursor)
        self._delete_btn.setStyleSheet(_BTN_DELETE)
        self._delete_btn.clicked.connect(
            lambda: self._current_task and self.delete_requested.emit(self._current_task)
        )

        btn_row.addWidget(self._edit_btn, 1)
        btn_row.addWidget(self._delete_btn, 1)
        col.addLayout(btn_row)
        return w

    def _build_photo_meta_section(self) -> QWidget:
        """Project manager fields (photo removed — redundant with the project photo)."""
        w = QWidget(); w.setStyleSheet(f'background: {CARD}; border: none;')
        row = QVBoxLayout(w)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(3)
        row.addWidget(self._section_label(t('project.timeline.detail_details')))

        def _stacked_field(label_text: str) -> QLineEdit:
            lbl = self._muted_label(label_text)
            inp = QLineEdit()
            inp.setPlaceholderText('—')
            inp.setFixedHeight(22)
            inp.setStyleSheet(_FIELD_STYLE)
            inp.setEnabled(False)
            row.addWidget(lbl)
            row.addWidget(inp)
            return inp

        self._f_pm      = _stacked_field(t('project.timeline.detail_pm'))
        self._f_tm      = _stacked_field(t('project.timeline.detail_tm'))
        self._f_contrib = _stacked_field(t('project.timeline.detail_contrib'))
        return w

    def _build_comment_components_section(self) -> QWidget:
        """Comments full-width, then components impacted full-width below, save at bottom-right."""
        w = QWidget(); w.setStyleSheet(f'background: {CARD}; border: none;')
        col = QVBoxLayout(w)
        col.setContentsMargins(12, 8, 12, 8)
        col.setSpacing(6)

        # ── Comments (full width) ─────────────────────────────────────────
        col.addWidget(self._section_label(t('project.timeline.detail_comments')))

        self._comment_box = QTextEdit()
        self._comment_box.setPlaceholderText(t('project.timeline.detail_comment_ph'))
        self._comment_box.setFixedHeight(90)
        self._comment_box.setStyleSheet(_TEXTAREA_STYLE)
        self._comment_box.textChanged.connect(self._on_comment_changed)
        col.addWidget(self._comment_box)

        # ── Components Impacted (full width) ──────────────────────────────
        col.addWidget(self._section_label(t('project.timeline.detail_components')))

        self._components_box = QTextEdit()
        self._components_box.setPlaceholderText(t('project.timeline.detail_comp_ph'))
        self._components_box.setFixedHeight(90)
        self._components_box.setStyleSheet(_TEXTAREA_STYLE)
        self._components_box.setEnabled(False)
        self._components_box.textChanged.connect(self._on_components_changed)
        col.addWidget(self._components_box)

        return w

    def _build_priority_status_section(self) -> QWidget:
        """Priority (full width) then execution status | progress side by side."""
        w = QWidget(); w.setStyleSheet(f'background: {CARD}; border: none;')
        col = QVBoxLayout(w)
        col.setContentsMargins(12, 8, 12, 10)
        col.setSpacing(6)

        # ── Priority (2×2 grid — 4-across no longer fits the halved panel width) ──
        col.addWidget(self._section_label(t('project.timeline.detail_priority')))
        priority_grid = QVBoxLayout(); priority_grid.setSpacing(4); priority_grid.setContentsMargins(0, 0, 0, 0)
        priority_row1 = QHBoxLayout(); priority_row1.setSpacing(4); priority_row1.setContentsMargins(0, 0, 0, 0)
        priority_row2 = QHBoxLayout(); priority_row2.setSpacing(4); priority_row2.setContentsMargins(0, 0, 0, 0)
        self._priority_btns: dict[str, QPushButton] = {}
        for i, level in enumerate(('Low', 'Normal', 'High', 'Critical')):
            fg, bg = _PRIORITY_COLORS[level]
            btn = QPushButton(t(f'project.timeline.priority_{level.lower()}'))
            btn.setFixedHeight(24)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setCheckable(True)
            btn.setEnabled(False)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: #f1f5f9; color: {MUTED};
                    border: 1px solid {BORDER}; border-radius: 4px;
                    font-size: 11px; font-weight: 600; padding: 1px 4px;
                }}
                QPushButton:checked {{
                    background: {bg}; color: {fg};
                    border-color: {fg};
                }}
                QPushButton:hover:!checked {{ background: #e5e7eb; }}
                QPushButton:disabled {{ color: #d1d5db; }}
            """)
            btn.clicked.connect(lambda _, l=level: self._set_priority(l))
            self._priority_btns[level] = btn
            (priority_row1 if i < 2 else priority_row2).addWidget(btn)
        priority_grid.addLayout(priority_row1)
        priority_grid.addLayout(priority_row2)
        col.addLayout(priority_grid)

        col.addWidget(self._hline())

        # ── Execution status + delay (full width, single column) ──────────
        col.addWidget(self._section_label(t('project.timeline.detail_exec_status')))
        status_row = QHBoxLayout(); status_row.setSpacing(6); status_row.setContentsMargins(0, 0, 0, 0)
        self._exec_status_dot = QLabel('●')
        self._exec_status_dot.setStyleSheet('font-size: 9px; background: transparent; border: none;')
        self._exec_status_lbl = QLabel('—')
        self._exec_status_lbl.setStyleSheet(f'color: {MUTED}; font-size: 12px; font-weight: 600; background: transparent; border: none;')
        status_row.addWidget(self._exec_status_dot)
        status_row.addWidget(self._exec_status_lbl)
        status_row.addStretch()
        col.addLayout(status_row)

        delay_row = QHBoxLayout(); delay_row.setSpacing(4); delay_row.setContentsMargins(0, 0, 0, 0)
        delay_prefix = QLabel(t('project.timeline.detail_delay'))
        delay_prefix.setStyleSheet(f'color: {MUTED}; font-size: 12px; background: transparent; border: none;')
        self._delay_lbl = QLabel('—')
        self._delay_lbl.setStyleSheet(f'color: {TEXT}; font-size: 12px; font-weight: 600; background: transparent; border: none;')
        delay_row.addWidget(delay_prefix)
        delay_row.addWidget(self._delay_lbl)
        delay_row.addStretch()
        col.addLayout(delay_row)

        # ── Delay extension ───────────────────────────────────────────────
        col.addWidget(self._hline())

        self._delay_ext_cb = QCheckBox(t('project.timeline.detail_delay_ext_check'))
        self._delay_ext_cb.setStyleSheet(f"""
            QCheckBox {{ color: {TEXT}; font-size: 11px; font-weight: 600;
                background: transparent; border: none; }}
            QCheckBox::indicator {{ width: 13px; height: 13px; border-radius: 3px;
                border: 1.5px solid {BORDER}; background: white; }}
            QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
            QCheckBox:disabled {{ color: #9ca3af; }}
        """)
        self._delay_ext_cb.setEnabled(False)
        self._delay_ext_cb.toggled.connect(self._on_delay_ext_toggled)
        col.addWidget(self._delay_ext_cb)

        ext_row = QHBoxLayout()
        ext_row.setSpacing(4)
        ext_row.setContentsMargins(0, 0, 0, 0)

        # Use the app's own calendar widget (EctoDateEdit) — the stock QDateEdit
        # popup wasn't letting users actually pick the extended date reliably.
        self._delay_ext_edit = EctoDateEdit(QDate.currentDate())
        self._delay_ext_edit.setFixedHeight(24)
        self._delay_ext_edit.setEnabled(False)
        self._delay_ext_edit.dateChanged.connect(self._on_delay_ext_date_changed)

        self._delay_ext_clear = QPushButton('✕')
        self._delay_ext_clear.setFixedSize(20, 24)
        self._delay_ext_clear.setCursor(Qt.PointingHandCursor)
        self._delay_ext_clear.setEnabled(False)
        self._delay_ext_clear.setStyleSheet(f"""
            QPushButton {{ background: #fee2e2; color: #ef4444; border: 1px solid #fca5a5;
                border-radius: 4px; font-size: 12px; font-weight: bold; padding: 0; }}
            QPushButton:hover {{ background: #ef4444; color: white; border-color: #ef4444; }}
            QPushButton:disabled {{ background: #f1f3f5; color: #9ca3af; border-color: {BORDER}; }}
        """)
        self._delay_ext_clear.clicked.connect(self._clear_delay_ext)

        ext_row.addWidget(self._delay_ext_edit, 1)
        ext_row.addWidget(self._delay_ext_clear)
        col.addLayout(ext_row)

        # ── Progress (full width, stacked below status instead of beside it) ──
        col.addWidget(self._hline())
        col.addWidget(self._section_label(t('project.timeline.detail_progress')))
        self._progress_pct_lbl = QLabel('0 %')
        self._progress_pct_lbl.setStyleSheet(f'color: {TEXT}; font-size: 13px; font-weight: 700; background: transparent; border: none;')
        col.addWidget(self._progress_pct_lbl)

        self._progress_bar_bg = QFrame()
        self._progress_bar_bg.setFixedHeight(8)
        self._progress_bar_bg.setStyleSheet('background: #e5e7eb; border-radius: 4px; border: none;')
        self._progress_bar_fill = QFrame(self._progress_bar_bg)
        self._progress_bar_fill.setFixedHeight(8)
        self._progress_bar_fill.setStyleSheet(f'background: {ACCENT}; border-radius: 4px; border: none;')
        self._progress_bar_fill.setFixedWidth(0)
        col.addWidget(self._progress_bar_bg)

        return w

    # ── priority / extra helpers ──────────────────────────────────────────────

    def _set_priority(self, level: str):
        if self._current_task:
            self._current_task.priority = level
        for lv, btn in self._priority_btns.items():
            btn.setChecked(lv == level)

    def _on_components_changed(self):
        if self._current_task:
            self._current_task.components_impacted = self._components_box.toPlainText()

    def _update_auto_fields(self, task: Task):
        """Recompute execution status, delay, and progress from task dates."""
        today = QDate.currentDate()
        total   = task.start.daysTo(task.end)
        elapsed = task.start.daysTo(today)
        pct = max(0, min(100, int(elapsed * 100 / total))) if total > 0 else 0

        if today > task.end:
            delay_days = task.end.daysTo(today)
            day_word = t('project.timeline.day_plural') if delay_days != 1 else t('project.timeline.day_singular')
            self._exec_status_dot.setStyleSheet('color: #ef4444; font-size: 9px; background: transparent; border: none;')
            self._exec_status_lbl.setText(t('project.timeline.status_late'))
            self._exec_status_lbl.setStyleSheet('color: #ef4444; font-size: 12px; font-weight: 600; background: transparent; border: none;')
            self._delay_lbl.setText(f'{delay_days} {day_word}')
            self._delay_lbl.setStyleSheet('color: #ef4444; font-size: 12px; font-weight: 600; background: transparent; border: none;')
        else:
            self._exec_status_dot.setStyleSheet('color: #16a34a; font-size: 9px; background: transparent; border: none;')
            self._exec_status_lbl.setText(t('project.timeline.status_in_progress'))
            self._exec_status_lbl.setStyleSheet('color: #16a34a; font-size: 12px; font-weight: 600; background: transparent; border: none;')
            self._delay_lbl.setText(t('project.timeline.detail_no_delay'))
            self._delay_lbl.setStyleSheet(f'color: {MUTED}; font-size: 12px; font-weight: 600; background: transparent; border: none;')

        self._progress_pct_lbl.setText(f'{pct} %')
        fill_w = max(0, int(_PROG_W * pct / 100))
        self._progress_bar_fill.setFixedWidth(fill_w)
        bar_color = '#ef4444' if today > task.end else ACCENT
        self._progress_bar_fill.setStyleSheet(f'background: {bar_color}; border-radius: 4px; border: none;')

    # ── public API ────────────────────────────────────────────────────────────

    def set_global_pm(self, pm: str):
        self._global_pm = (pm or '').strip()
        if self._current_task is not None:
            current = self._f_pm.text().strip()
            if not current or current == self._last_auto_pm:
                self._f_pm.blockSignals(True)
                self._f_pm.setText(self._global_pm)
                self._f_pm.blockSignals(False)
                if self._current_task:
                    self._current_task.project_manager = self._global_pm
                self._last_auto_pm = self._global_pm

    def show_task(self, task: Task):
        self._current_task = task
        self._lbl_task.setText(task.name)
        self._lbl_dates.setText(
            f"{task.start.toString('d MMM yyyy')}  →  {task.end.toString('d MMM yyyy')}"
        )
        self._lbl_type.setText(
            f"{t('project.timeline.label_type')} {task.task_type}"
            + (f"  {t('project.timeline.label_urgent')}" if task.is_urgent else '')
        )
        days = task.start.daysTo(task.end)
        day_word = t('project.timeline.day_plural') if days != 1 else t('project.timeline.day_singular')
        self._lbl_duration.setText(f"{t('project.timeline.label_duration')} {days} {day_word}")
        self._edit_btn.setEnabled(True)
        self._delete_btn.setEnabled(True)

        # Comments — persist live as you type, no save step needed
        self._comment_box.blockSignals(True)
        self._comment_box.setPlainText('\n'.join(task.comments))
        self._comment_box.blockSignals(False)

        # PM fields
        if not task.project_manager and self._global_pm:
            task.project_manager = self._global_pm
            self._last_auto_pm = self._global_pm
        for f, value in (
            (self._f_pm,      task.project_manager),
            (self._f_tm,      task.technical_manager),
            (self._f_contrib, task.contributors),
        ):
            f.blockSignals(True)
            f.setText(value)
            f.setEnabled(True)
            f.blockSignals(False)
        self._f_pm.textChanged.connect(lambda v: setattr(task, 'project_manager', v))
        self._f_tm.textChanged.connect(lambda v: setattr(task, 'technical_manager', v))
        self._f_contrib.textChanged.connect(lambda v: setattr(task, 'contributors', v))

        # Components impacted
        self._components_box.blockSignals(True)
        self._components_box.setPlainText(task.components_impacted)
        self._components_box.setEnabled(True)
        self._components_box.blockSignals(False)

        # Priority
        for btn in self._priority_btns.values():
            btn.setEnabled(True)
        self._set_priority(task.priority or 'Normal')

        # Delay extension
        self._delay_ext_edit.blockSignals(True)
        self._delay_ext_cb.blockSignals(True)
        if task.delay_end and task.delay_end > task.end:
            self._delay_ext_cb.setChecked(True)
            self._delay_ext_edit.setDate(task.delay_end)
            self._delay_ext_edit.setEnabled(True)
            self._delay_ext_clear.setEnabled(True)
        else:
            self._delay_ext_cb.setChecked(False)
            self._delay_ext_edit.setDate(task.end.addDays(1))
            self._delay_ext_edit.setEnabled(False)
            self._delay_ext_clear.setEnabled(False)
        self._delay_ext_cb.setEnabled(True)
        self._delay_ext_cb.blockSignals(False)
        self._delay_ext_edit.blockSignals(False)

        # Auto-computed fields
        self._update_auto_fields(task)

    def clear(self):
        self._current_task = None
        self._edit_btn.setEnabled(False)
        self._delete_btn.setEnabled(False)
        self._lbl_task.setText(t('project.timeline.detail_click_task'))
        for lbl in (self._lbl_dates, self._lbl_type, self._lbl_duration):
            lbl.setText('')
        self._comment_box.clear()
        for f in (self._f_pm, self._f_tm, self._f_contrib):
            f.blockSignals(True)
            f.clear()
            f.setEnabled(False)
            f.blockSignals(False)
        self._components_box.clear()
        self._components_box.setEnabled(False)
        for btn in self._priority_btns.values():
            btn.setChecked(False)
            btn.setEnabled(False)
        self._exec_status_lbl.setText('—')
        self._delay_lbl.setText('—')
        self._progress_pct_lbl.setText('0 %')
        self._progress_bar_fill.setFixedWidth(0)
        self._delay_ext_cb.blockSignals(True)
        self._delay_ext_cb.setChecked(False)
        self._delay_ext_cb.setEnabled(False)
        self._delay_ext_cb.blockSignals(False)
        self._delay_ext_edit.setEnabled(False)
        self._delay_ext_clear.setEnabled(False)

    def _on_comment_changed(self):
        """Comments persist as you type — no explicit save step, same as the
        other project fields."""
        if not self._current_task:
            return
        self._current_task.comments = [
            c for c in self._comment_box.toPlainText().split('\n') if c.strip()
        ]

    # ── delay extension slots ─────────────────────────────────────────────────

    def _on_delay_ext_toggled(self, checked: bool):
        if not self._current_task:
            return
        if checked:
            date = self._delay_ext_edit.date()
            if not date.isValid() or date <= self._current_task.end:
                date = self._current_task.end.addDays(1)
            self._delay_ext_edit.blockSignals(True)
            self._delay_ext_edit.setDate(date)
            self._delay_ext_edit.blockSignals(False)
            self._delay_ext_edit.setEnabled(True)
            self._delay_ext_clear.setEnabled(True)
            self._current_task.delay_end = date
        else:
            self._current_task.delay_end = None
            self._delay_ext_edit.setEnabled(False)
            self._delay_ext_clear.setEnabled(False)
        self.task_changed.emit()

    def _on_delay_ext_date_changed(self, date: QDate):
        if self._current_task and self._delay_ext_cb.isChecked():
            if date <= self._current_task.end:
                date = self._current_task.end.addDays(1)
                self._delay_ext_edit.setDate(date)
            self._current_task.delay_end = date
            self.task_changed.emit()

    def _clear_delay_ext(self):
        if not self._current_task:
            return
        self._current_task.delay_end = None
        self._delay_ext_cb.blockSignals(True)
        self._delay_ext_cb.setChecked(False)
        self._delay_ext_cb.blockSignals(False)
        self._delay_ext_edit.setEnabled(False)
        self._delay_ext_clear.setEnabled(False)
        self.task_changed.emit()

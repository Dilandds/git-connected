"""
TaskDetailPanel — right-side inspector panel showing selected task info,
comments, and editable project-management fields.
"""
from typing import Optional
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QLineEdit, QTextEdit, QScrollArea, QFileDialog, QSizePolicy,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QDate
from PyQt5.QtGui import QPixmap
from ui.styles import default_theme
from .models import Task, CARD, BORDER, TEXT, MUTED, ACCENT

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
        padding: 4px 8px; font-size: 14px;
    }}
    QLineEdit:focus    {{ border-color: {ACCENT}; }}
    QLineEdit:disabled {{ background-color: #f1f3f5; color: #9ca3af; }}
"""

_TEXTAREA_STYLE = f"""
    QTextEdit {{
        background-color: #eef2f7; color: {TEXT};
        border: 1px solid #c8d4e0; border-radius: 5px;
        font-size: 14px; padding: 6px;
    }}
    QTextEdit:focus {{ border-color: {ACCENT}; }}
"""

_PRIORITY_COLORS = {
    'Low':      ('#16a34a', '#dcfce7'),
    'Normal':   ('#2563eb', '#dbeafe'),
    'High':     ('#d97706', '#fef3c7'),
    'Critical': ('#dc2626', '#fee2e2'),
}

_PANEL_W = 340
_PHOTO_H = 170


class TaskDetailPanel(QWidget):
    """Right-side inspector: task details, comments, and PM meta fields."""

    edit_requested   = pyqtSignal(object)
    delete_requested = pyqtSignal(object)

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

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: {CARD}; border: none; }}
            QScrollBar:vertical {{ background: {CARD}; width: 6px; border-radius: 3px; }}
            QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 3px; }}
        """)

        container = QWidget()
        container.setStyleSheet(f'background: {CARD}; border: none;')
        lay = QVBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        lay.addWidget(self._build_info_section())
        lay.addWidget(self._hline())
        lay.addWidget(self._build_photo_section())
        lay.addWidget(self._hline())
        lay.addWidget(self._build_meta_section())
        lay.addWidget(self._hline())
        lay.addWidget(self._build_comment_section())
        lay.addWidget(self._hline())
        lay.addWidget(self._build_extra_section())
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
            f'color: {MUTED}; font-size: 11px; font-weight: bold; letter-spacing: 0.8px;'
            f' background: transparent; border: none;'
        )
        return lbl

    # ── sections ──────────────────────────────────────────────────────────────

    def _build_info_section(self) -> QWidget:
        w = QWidget(); w.setStyleSheet(f'background: {CARD}; border: none;')
        col = QVBoxLayout(w)
        col.setContentsMargins(12, 12, 12, 10)
        col.setSpacing(4)

        self._lbl_task = QLabel('Click a task to see details')
        self._lbl_task.setWordWrap(True)
        self._lbl_task.setStyleSheet(
            f'color: {TEXT}; font-size: 16px; font-weight: bold; '
            f'background: transparent; border: none;'
        )
        col.addWidget(self._lbl_task)

        self._lbl_dates    = QLabel('')
        self._lbl_type     = QLabel('')
        self._lbl_status   = QLabel('')
        self._lbl_duration = QLabel('')
        for lbl in (self._lbl_dates, self._lbl_type, self._lbl_status, self._lbl_duration):
            lbl.setWordWrap(True)
            col.addWidget(lbl)

        col.addSpacing(6)

        btn_row = QHBoxLayout(); btn_row.setSpacing(6); btn_row.setContentsMargins(0, 0, 0, 0)

        self._edit_btn = QPushButton('✎  Edit Task')
        self._edit_btn.setFixedHeight(32)
        self._edit_btn.setEnabled(False)
        self._edit_btn.setCursor(Qt.PointingHandCursor)
        self._edit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #e5e7eb; color: {MUTED};
                border: 1px solid {BORDER}; border-radius: 4px;
                font-size: 14px; padding: 4px 10px;
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

        self._delete_btn = QPushButton('🗑  Remove')
        self._delete_btn.setFixedHeight(32)
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

    def _build_photo_section(self) -> QWidget:
        w = QWidget(); w.setStyleSheet(f'background: {CARD}; border: none;')
        col = QVBoxLayout(w)
        col.setContentsMargins(12, 10, 12, 10)
        col.setSpacing(6)

        # Photo display area
        self._photo_frame = QLabel()
        self._photo_frame.setFixedHeight(_PHOTO_H)
        self._photo_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._photo_frame.setAlignment(Qt.AlignCenter)
        self._photo_frame.setCursor(Qt.PointingHandCursor)
        self._photo_frame.setStyleSheet(f"""
            QLabel {{
                background: #f1f5f9;
                border: 2px dashed {BORDER};
                border-radius: 8px;
                color: {MUTED};
                font-size: 13px;
            }}
        """)
        self._photo_frame.setText('📷  Click to add photo')
        self._photo_frame.mousePressEvent = lambda _: self._pick_photo()
        col.addWidget(self._photo_frame)

        # Remove photo link (hidden until photo set)
        self._remove_photo_btn = QPushButton('✕  Remove photo')
        self._remove_photo_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {MUTED}; font-size: 11px; padding: 0;
            }}
            QPushButton:hover {{ color: #ef4444; }}
        """)
        self._remove_photo_btn.setCursor(Qt.PointingHandCursor)
        self._remove_photo_btn.clicked.connect(self._remove_photo)
        self._remove_photo_btn.hide()
        col.addWidget(self._remove_photo_btn, 0, Qt.AlignRight)

        return w

    def _build_meta_section(self) -> QWidget:
        w = QWidget(); w.setStyleSheet(f'background: {CARD}; border: none;')
        col = QVBoxLayout(w)
        col.setContentsMargins(12, 10, 12, 10)
        col.setSpacing(6)

        col.addWidget(self._section_label('Details'))
        col.addSpacing(2)

        def _field(label_text: str) -> QLineEdit:
            row = QHBoxLayout(); row.setSpacing(4)
            lbl = QLabel(label_text)
            lbl.setFixedWidth(148)
            lbl.setStyleSheet(
                f'color: {MUTED}; font-size: 14px; background: transparent; border: none;'
            )
            inp = QLineEdit()
            inp.setPlaceholderText('—')
            inp.setFixedHeight(22)
            inp.setStyleSheet(_FIELD_STYLE)
            inp.setEnabled(False)
            row.addWidget(lbl)
            row.addWidget(inp)
            col.addLayout(row)
            return inp

        self._f_pm      = _field('Project Manager:')
        self._f_tm      = _field('Technical Manager:')
        self._f_contrib = _field('Contributors:')
        return w

    def _build_comment_section(self) -> QWidget:
        w = QWidget(); w.setStyleSheet(f'background: {CARD}; border: none;')
        col = QVBoxLayout(w)
        col.setContentsMargins(12, 10, 12, 10)
        col.setSpacing(6)

        col.addWidget(self._section_label('Comments'))

        self._comment_box = QTextEdit()
        self._comment_box.setPlaceholderText('Add a comment...')
        self._comment_box.setMinimumHeight(100)
        self._comment_box.setStyleSheet(_TEXTAREA_STYLE)
        self._comment_box.textChanged.connect(
            lambda: self._save_btn.setEnabled(self._current_task is not None)
        )
        col.addWidget(self._comment_box)

        self._save_btn = QPushButton('Save')
        self._save_btn.setFixedHeight(32)
        self._save_btn.setEnabled(False)
        self._save_btn.setCursor(Qt.PointingHandCursor)
        self._save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {ACCENT}; color: white; border: none;
                border-radius: 4px; font-size: 12px; font-weight: bold;
                padding: 0 18px;
            }}
            QPushButton:hover {{ background-color: {default_theme.button_primary_hover}; }}
            QPushButton:disabled {{ background-color: #e5e7eb; color: #9ca3af; }}
        """)
        self._save_btn.clicked.connect(self._save_comment)
        save_row = QHBoxLayout(); save_row.setContentsMargins(0, 0, 0, 0)
        save_row.addStretch()
        save_row.addWidget(self._save_btn)
        col.addLayout(save_row)
        return w

    def _build_extra_section(self) -> QWidget:
        w = QWidget(); w.setStyleSheet(f'background: {CARD}; border: none;')
        col = QVBoxLayout(w)
        col.setContentsMargins(12, 10, 12, 14)
        col.setSpacing(12)

        # ── Components impacted ───────────────────────────────────────────
        col.addWidget(self._section_label('Component(s) impacted by this event'))
        self._components_box = QTextEdit()
        self._components_box.setPlaceholderText('List the components affected by this event...')
        self._components_box.setFixedHeight(90)
        self._components_box.setStyleSheet(_TEXTAREA_STYLE)
        self._components_box.setEnabled(False)
        self._components_box.textChanged.connect(self._on_components_changed)
        col.addWidget(self._components_box)

        # ── Priority ──────────────────────────────────────────────────────
        col.addWidget(self._section_label('Priority'))
        priority_row = QHBoxLayout(); priority_row.setSpacing(4); priority_row.setContentsMargins(0, 0, 0, 0)
        self._priority_btns: dict[str, QPushButton] = {}
        for level in ('Low', 'Normal', 'High', 'Critical'):
            fg, bg = _PRIORITY_COLORS[level]
            btn = QPushButton(level)
            btn.setFixedHeight(26)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setCheckable(True)
            btn.setEnabled(False)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: #f1f5f9; color: {MUTED};
                    border: 1px solid {BORDER}; border-radius: 4px;
                    font-size: 11px; font-weight: 600; padding: 2px 6px;
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
            priority_row.addWidget(btn)
        col.addLayout(priority_row)

        # ── Auto status ───────────────────────────────────────────────────
        col.addWidget(self._section_label('Execution Status'))
        status_row = QHBoxLayout(); status_row.setSpacing(8); status_row.setContentsMargins(0, 0, 0, 0)
        self._exec_status_dot = QLabel('●')
        self._exec_status_dot.setStyleSheet('font-size: 10px; background: transparent; border: none;')
        self._exec_status_lbl = QLabel('—')
        self._exec_status_lbl.setStyleSheet(f'color: {MUTED}; font-size: 13px; font-weight: 600; background: transparent; border: none;')
        status_row.addWidget(self._exec_status_dot)
        status_row.addWidget(self._exec_status_lbl)
        status_row.addStretch()
        col.addLayout(status_row)

        # ── Delay ─────────────────────────────────────────────────────────
        delay_row = QHBoxLayout(); delay_row.setSpacing(4); delay_row.setContentsMargins(0, 0, 0, 0)
        delay_prefix = QLabel('Delay of:')
        delay_prefix.setStyleSheet(f'color: {MUTED}; font-size: 13px; background: transparent; border: none;')
        self._delay_lbl = QLabel('—')
        self._delay_lbl.setStyleSheet(f'color: {TEXT}; font-size: 13px; font-weight: 600; background: transparent; border: none;')
        delay_row.addWidget(delay_prefix)
        delay_row.addWidget(self._delay_lbl)
        delay_row.addStretch()
        col.addLayout(delay_row)

        # ── Progress bar ──────────────────────────────────────────────────
        col.addWidget(self._section_label('Progress'))
        prog_header = QHBoxLayout(); prog_header.setContentsMargins(0, 0, 0, 0)
        self._progress_pct_lbl = QLabel('0 %')
        self._progress_pct_lbl.setStyleSheet(f'color: {TEXT}; font-size: 13px; font-weight: 700; background: transparent; border: none;')
        prog_header.addWidget(self._progress_pct_lbl)
        prog_header.addStretch()
        col.addLayout(prog_header)

        self._progress_bar_bg = QFrame()
        self._progress_bar_bg.setFixedHeight(8)
        self._progress_bar_bg.setStyleSheet(f'background: #e5e7eb; border-radius: 4px; border: none;')
        self._progress_bar_fill = QFrame(self._progress_bar_bg)
        self._progress_bar_fill.setFixedHeight(8)
        self._progress_bar_fill.setStyleSheet(f'background: {ACCENT}; border-radius: 4px; border: none;')
        self._progress_bar_fill.setFixedWidth(0)
        col.addWidget(self._progress_bar_bg)

        return w

    # ── photo helpers ─────────────────────────────────────────────────────────

    def _pick_photo(self):
        if not self._current_task:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select Photo', '',
            'Images (*.png *.jpg *.jpeg *.webp *.bmp)'
        )
        if path:
            self._current_task.photo_path = path
            self._show_photo(path)

    def _remove_photo(self):
        if self._current_task:
            self._current_task.photo_path = ''
        self._photo_frame.setText('📷  Click to add photo')
        self._photo_frame.setStyleSheet(f"""
            QLabel {{
                background: #f1f5f9;
                border: 2px dashed {BORDER};
                border-radius: 8px;
                color: {MUTED};
                font-size: 13px;
            }}
        """)
        self._remove_photo_btn.hide()

    def _show_photo(self, path: str):
        pix = QPixmap(path)
        if pix.isNull():
            return
        available_w = _PANEL_W - 24
        scaled = pix.scaled(available_w, _PHOTO_H, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        # Centre-crop to exact size
        x = (scaled.width() - available_w) // 2
        y = (scaled.height() - _PHOTO_H) // 2
        cropped = scaled.copy(max(x, 0), max(y, 0), available_w, _PHOTO_H)
        self._photo_frame.setPixmap(cropped)
        self._photo_frame.setStyleSheet('border-radius: 8px; border: none;')
        self._remove_photo_btn.show()

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
        total = task.start.daysTo(task.end)
        elapsed = task.start.daysTo(today)
        pct = max(0, min(100, int(elapsed * 100 / total))) if total > 0 else 0

        if today > task.end:
            delay_days = task.end.daysTo(today)
            self._exec_status_dot.setStyleSheet('color: #ef4444; font-size: 10px; background: transparent; border: none;')
            self._exec_status_lbl.setText('Late')
            self._exec_status_lbl.setStyleSheet('color: #ef4444; font-size: 13px; font-weight: 600; background: transparent; border: none;')
            self._delay_lbl.setText(f'{delay_days} day{"s" if delay_days != 1 else ""}')
            self._delay_lbl.setStyleSheet('color: #ef4444; font-size: 13px; font-weight: 600; background: transparent; border: none;')
        else:
            self._exec_status_dot.setStyleSheet('color: #16a34a; font-size: 10px; background: transparent; border: none;')
            self._exec_status_lbl.setText('In Progress')
            self._exec_status_lbl.setStyleSheet('color: #16a34a; font-size: 13px; font-weight: 600; background: transparent; border: none;')
            self._delay_lbl.setText('None')
            self._delay_lbl.setStyleSheet(f'color: {MUTED}; font-size: 13px; font-weight: 600; background: transparent; border: none;')

        self._progress_pct_lbl.setText(f'{pct} %')
        available_w = _PANEL_W - 24
        fill_w = max(0, int(available_w * pct / 100))
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
            f"Type: {task.task_type}" + ('  🔴 URGENT' if task.is_urgent else '')
        )
        self._lbl_status.setText(f'Status: {task.status}')
        days = task.start.daysTo(task.end)
        self._lbl_duration.setText(f"Duration: {days} day{'s' if days != 1 else ''}")
        self._edit_btn.setEnabled(True)
        self._delete_btn.setEnabled(True)
        self._save_btn.setEnabled(True)

        # Photo
        if task.photo_path:
            self._show_photo(task.photo_path)
        else:
            self._remove_photo()

        # Comments
        self._comment_box.setPlainText('\n'.join(task.comments))

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

        # Auto-computed fields
        self._update_auto_fields(task)

    def clear(self):
        self._current_task = None
        self._edit_btn.setEnabled(False)
        self._delete_btn.setEnabled(False)
        self._save_btn.setEnabled(False)
        self._lbl_task.setText('Click a task to see details')
        for lbl in (self._lbl_dates, self._lbl_type, self._lbl_status, self._lbl_duration):
            lbl.setText('')
        self._comment_box.clear()
        for f in (self._f_pm, self._f_tm, self._f_contrib):
            f.blockSignals(True)
            f.clear()
            f.setEnabled(False)
            f.blockSignals(False)
        self._remove_photo()
        self._components_box.clear()
        self._components_box.setEnabled(False)
        for btn in self._priority_btns.values():
            btn.setChecked(False)
            btn.setEnabled(False)
        self._exec_status_lbl.setText('—')
        self._delay_lbl.setText('—')
        self._progress_pct_lbl.setText('0 %')
        self._progress_bar_fill.setFixedWidth(0)

    def _save_comment(self):
        if not self._current_task:
            return
        self._current_task.comments = [
            c for c in self._comment_box.toPlainText().split('\n') if c.strip()
        ]
        self._save_btn.setText('✔')
        QTimer.singleShot(1000, lambda: self._save_btn.setText('Save'))

"""
TaskDetailPanel — right-side inspector panel showing selected task info,
comments, and editable project-management fields.
"""
from typing import Optional
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QLineEdit, QTextEdit, QScrollArea,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from ui.styles import default_theme
from .models import Task, CARD, BORDER, TEXT, MUTED, ACCENT

_BTN_DELETE = f"""
    QPushButton {{
        background-color: #fee2e2; color: #ef4444;
        border: 1px solid #fca5a5; border-radius: 4px;
        font-size: 10px; padding: 2px 10px;
    }}
    QPushButton:hover {{ background-color: #ef4444; color: white; border-color: #ef4444; }}
    QPushButton:disabled {{ color: #9ca3af; background-color: #f1f3f5; border-color: {BORDER}; }}
"""

_FIELD_STYLE = f"""
    QLineEdit {{
        background-color: #f5f6f8; color: {TEXT};
        border: 1px solid {BORDER}; border-radius: 4px;
        padding: 2px 6px; font-size: 10px;
    }}
    QLineEdit:focus    {{ border-color: {ACCENT}; }}
    QLineEdit:disabled {{ background-color: #f1f3f5; color: #9ca3af; }}
"""

_PANEL_W = 280


class TaskDetailPanel(QWidget):
    """Right-side inspector: task details, comments, and PM meta fields."""

    edit_requested   = pyqtSignal(object)   # emits Task
    delete_requested = pyqtSignal(object)   # emits Task

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_task: Optional[Task] = None
        self.setFixedWidth(_PANEL_W)
        self.setStyleSheet(f"""
            QWidget  {{ background-color: {CARD}; border-left: 1px solid {BORDER}; }}
            QLabel   {{ color: {TEXT}; font-size: 10px; background: transparent; border: none; }}
            QTextEdit {{
                background-color: #f5f6f8; color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 4px;
                font-size: 10px; padding: 4px;
            }}
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
        lay.addWidget(self._build_comment_section())
        lay.addWidget(self._hline())
        lay.addWidget(self._build_meta_section())
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
            f'color: {MUTED}; font-size: 9px; font-weight: bold; '
            f'background: transparent; border: none;'
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
            f'color: {TEXT}; font-size: 12px; font-weight: bold; '
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
        self._edit_btn.setFixedHeight(26)
        self._edit_btn.setEnabled(False)
        self._edit_btn.setCursor(Qt.PointingHandCursor)
        self._edit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #e5e7eb; color: {MUTED};
                border: 1px solid {BORDER}; border-radius: 4px;
                font-size: 10px; padding: 2px 10px;
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
        self._delete_btn.setFixedHeight(26)
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

    def _build_comment_section(self) -> QWidget:
        w = QWidget(); w.setStyleSheet(f'background: {CARD}; border: none;')
        col = QVBoxLayout(w)
        col.setContentsMargins(12, 10, 12, 10)
        col.setSpacing(6)

        header = QHBoxLayout()
        header.addWidget(self._section_label('Comments'))
        header.addStretch()

        self._save_btn = QPushButton('Save')
        self._save_btn.setFixedHeight(22)
        self._save_btn.setEnabled(False)
        self._save_btn.setCursor(Qt.PointingHandCursor)
        self._save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {ACCENT}; color: white; border: none;
                border-radius: 4px; font-size: 10px; font-weight: bold;
                padding: 0 14px;
            }}
            QPushButton:hover {{ background-color: {default_theme.button_primary_hover}; }}
            QPushButton:disabled {{ background-color: #e5e7eb; color: #9ca3af; }}
        """)
        self._save_btn.clicked.connect(self._save_comment)
        header.addWidget(self._save_btn)
        col.addLayout(header)

        self._comment_box = QTextEdit()
        self._comment_box.setPlaceholderText('Add a comment...')
        self._comment_box.setFixedHeight(90)
        self._comment_box.textChanged.connect(
            lambda: self._save_btn.setEnabled(self._current_task is not None)
        )
        col.addWidget(self._comment_box)
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
            lbl.setFixedWidth(108)
            lbl.setStyleSheet(
                f'color: {MUTED}; font-size: 10px; background: transparent; border: none;'
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

    # ── public API ────────────────────────────────────────────────────────────

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
        self._comment_box.setPlainText('\n'.join(task.comments))
        self._edit_btn.setEnabled(True)
        self._delete_btn.setEnabled(True)
        self._save_btn.setEnabled(True)

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

    def _save_comment(self):
        if not self._current_task:
            return
        self._current_task.comments = [
            c for c in self._comment_box.toPlainText().split('\n') if c.strip()
        ]
        self._save_btn.setText('✔')
        QTimer.singleShot(1000, lambda: self._save_btn.setText('Save'))

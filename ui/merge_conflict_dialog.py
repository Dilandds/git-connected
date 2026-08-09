"""
Merge Conflict Dialog — shown when saving a project collides with changes
someone else already saved to the same field(s).

One row per core.project_merge.Conflict, showing both values with a
pick-one-side choice — per the milestone's explicit design decision
("pick one side per field", no manual-merge editor for this version).
Delete-vs-edit conflicts never reach this dialog — the merge engine
resolves those safely on its own (see core/project_merge.py).
"""
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QWidget, QFrame, QButtonGroup
from PyQt5.QtCore import Qt

from ui.modal_utils import BaseModal
from i18n import t


class MergeConflictDialog(BaseModal):
    def __init__(self, parent, conflicts):
        super().__init__(parent, t('project.msg.conflict_title'), theme=BaseModal.LIGHT, min_width=560)
        self._conflicts = conflicts
        self._choices = []  # (mine_btn, theirs_btn) per conflict, same order as self._conflicts

        intro = QLabel(t('project.msg.conflict_intro'))
        intro.setWordWrap(True)
        intro.setStyleSheet(f'color: {self._muted}; font-size: 12px; background: transparent; border: none;')
        self._root.addWidget(intro)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMaximumHeight(360)
        container = QWidget()
        rows_layout = QVBoxLayout(container)
        rows_layout.setSpacing(10)
        for conflict in conflicts:
            rows_layout.addWidget(self._build_row(conflict))
        rows_layout.addStretch()
        scroll.setWidget(container)
        self._root.addWidget(scroll)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.cancel_btn = self._make_cancel_btn(t('common.cancel'))
        self.ok_btn = self._make_ok_btn(t('project.msg.conflict_apply'))
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.ok_btn)
        self._root.addLayout(btn_row)

    def _build_row(self, conflict) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            'QFrame { background-color: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; }'
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        label = QLabel(self._describe(conflict))
        label.setWordWrap(True)
        label.setStyleSheet(
            'font-size: 12px; font-weight: bold; color: #111827; background: transparent; border: none;'
        )
        layout.addWidget(label)

        mine_btn = QPushButton(t('project.msg.conflict_keep_mine').format(value=self._truncate(conflict.local_value)))
        theirs_btn = QPushButton(t('project.msg.conflict_keep_theirs').format(value=self._truncate(conflict.remote_value)))
        group = QButtonGroup(frame)
        for btn in (mine_btn, theirs_btn):
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(self._choice_btn_style())
            group.addButton(btn)
        group.setExclusive(True)
        mine_btn.setChecked(True)  # default to the saver's own change

        row = QHBoxLayout()
        row.addWidget(mine_btn)
        row.addWidget(theirs_btn)
        layout.addLayout(row)

        self._choices.append((mine_btn, theirs_btn))
        return frame

    @staticmethod
    def _choice_btn_style() -> str:
        return """
            QPushButton {
                background-color: white; color: #111827;
                border: 1px solid #d1d5db; border-radius: 6px;
                padding: 6px 10px; font-size: 12px; text-align: left;
            }
            QPushButton:checked {
                background-color: #eff6ff; border: 2px solid #2596BE; color: #1e3a5f;
                font-weight: bold;
            }
            QPushButton:hover { border-color: #2596BE; }
        """

    @staticmethod
    def _describe(conflict) -> str:
        path_str = ' / '.join(str(p) for p in conflict.path) if conflict.path else conflict.section
        return f'{conflict.section} — {path_str} — {conflict.field}'

    @staticmethod
    def _truncate(value, limit: int = 60) -> str:
        text = '' if value is None else str(value)
        return text if len(text) <= limit else text[: limit - 1] + '…'

    def apply_resolutions(self):
        """Write each conflict's chosen value via its resolve() callback.
        Call only after exec_() returns Accepted."""
        for conflict, (mine_btn, _theirs_btn) in zip(self._conflicts, self._choices):
            if conflict.resolve is None:
                continue
            chosen = conflict.local_value if mine_btn.isChecked() else conflict.remote_value
            conflict.resolve(chosen)

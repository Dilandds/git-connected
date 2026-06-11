"""Section 2 — Planned Techniques / Watch Points card."""
from PyQt5.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel
from .shared import _TEXT, _MUTED, card, section_label, separator
from .widgets import BulletListWidget
from i18n import t


class TechniquesCard(QFrame):
    """Section 2: Planned Techniques / Watch Points."""

    def __init__(self, parent=None):
        super().__init__(parent)
        c = card()
        layout = QVBoxLayout(c)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(section_label(t('project.brief.s2_title')))
        layout.addWidget(separator())

        cols = QHBoxLayout()
        cols.setSpacing(16)
        cols.addLayout(self._build_column(
            t('project.brief.s2_techniques'),
            t('project.brief.s2_tech_hint'),
            '_techniques_list',
        ))
        cols.addLayout(self._build_column(
            t('project.brief.s2_watchpoints'),
            t('project.brief.s2_watch_hint'),
            '_watchpoints_list',
        ))
        layout.addLayout(cols)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(c)

    def _build_column(self, title: str, hint: str, attr: str) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(6)

        lbl = QLabel(title)
        lbl.setStyleSheet(
            f'color: {_TEXT}; font-size: 10px; font-weight: bold; background: transparent; border: none;'
        )
        col.addWidget(lbl)

        bullet_list = BulletListWidget('...', 4)
        setattr(self, attr, bullet_list)
        col.addWidget(bullet_list)

        hint_lbl = QLabel(hint)
        hint_lbl.setStyleSheet(
            f'color: {_MUTED}; font-size: 9px; background: transparent; border: none;'
        )
        hint_lbl.setWordWrap(True)
        col.addWidget(hint_lbl)
        col.addStretch()
        return col

    def set_edit_mode(self, enabled: bool):
        self._techniques_list.set_edit_mode(enabled)
        self._watchpoints_list.set_edit_mode(enabled)

    def get_data(self) -> dict:
        return {
            'techniques':  self._techniques_list.get_values(),
            'watchpoints': self._watchpoints_list.get_values(),
        }

    def set_data(self, data: dict):
        if data.get('techniques'):
            self._techniques_list.set_values(data['techniques'])
        if data.get('watchpoints'):
            self._watchpoints_list.set_values(data['watchpoints'])

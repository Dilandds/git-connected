"""Section 3 — Target Points card."""
from PyQt5.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy, QTextEdit
from .shared import _MUTED, _INPUT_BG, _BORDER, _ACCENT, _TEXT, LABEL_STYLE, card, section_label, make_input, separator
from i18n import t

_TEXTAREA_STYLE = f"""
    QTextEdit {{
        background: {_INPUT_BG};
        border: 1px solid {_BORDER};
        border-radius: 8px;
        color: {_TEXT};
        font-size: 13px;
        padding: 8px 10px;
    }}
    QTextEdit:focus {{
        border-color: {_ACCENT};
        background: #ffffff;
    }}
"""


class TargetPointsCard(QFrame):
    """Section 3: Target Points (dimensions, weight, cost, constraints)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        c = card()
        layout = QVBoxLayout(c)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(section_label(t('project.brief.s3_title')))
        layout.addWidget(separator())

        hint = QLabel(t('project.brief.s3_hint'))
        hint.setStyleSheet(f'color: {_MUTED}; font-size: 13px; background: transparent; border: none;')
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # Fixed single-line fields
        for label_key, attr, unit in [
            (t('project.brief.s3_dimensions'), '_f_dimensions', ''),
            (t('project.brief.s3_weight'),     '_f_weight',     'g'),
            (t('project.brief.s3_cost'),       '_f_cost',       '€'),
        ]:
            row = QHBoxLayout()
            row.setSpacing(6)
            lbl = QLabel(label_key)
            lbl.setStyleSheet(LABEL_STYLE)
            row.addWidget(lbl, 1)
            inp = make_input('')
            inp.setMinimumHeight(36)
            setattr(self, attr, inp)
            row.addWidget(inp, 2)
            if unit:
                u = QLabel(unit)
                u.setStyleSheet(
                    f'color: {_MUTED}; font-size: 13px; background: transparent; border: none;'
                )
                u.setFixedWidth(14)
                row.addWidget(u)
            layout.addLayout(row)

        # Other constraints — expands to fill remaining height
        cons_lbl = QLabel(t('project.brief.s3_constraints'))
        cons_lbl.setStyleSheet(LABEL_STYLE)
        layout.addWidget(cons_lbl)

        self._f_constraints = QTextEdit()
        self._f_constraints.setPlaceholderText(t('project.brief.s3_constraints'))
        self._f_constraints.setStyleSheet(_TEXTAREA_STYLE)
        self._f_constraints.setMinimumHeight(60)
        self._f_constraints.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self._f_constraints, 1)   # stretch=1 fills remaining space

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(c)

    def set_edit_mode(self, enabled: bool):
        self._f_constraints.setReadOnly(not enabled)
        for attr in ('_f_dimensions', '_f_weight', '_f_cost'):
            getattr(self, attr).setReadOnly(not enabled)

    def get_data(self) -> dict:
        return {
            'dimensions':  self._f_dimensions.text(),
            'weight':      self._f_weight.text(),
            'cost':        self._f_cost.text(),
            'constraints': self._f_constraints.toPlainText(),
        }

    def set_data(self, data: dict):
        self._f_dimensions.setText(data.get('dimensions', ''))
        self._f_weight.setText(data.get('weight', ''))
        self._f_cost.setText(data.get('cost', ''))
        self._f_constraints.setPlainText(data.get('constraints', ''))

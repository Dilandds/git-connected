"""Section 3 — Target Points card."""
from PyQt5.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel
from .shared import _MUTED, LABEL_STYLE, card, section_label, make_input, separator


class TargetPointsCard(QFrame):
    """Section 3: Target Points (dimensions, weight, cost, constraints)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        c = card()
        layout = QVBoxLayout(c)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(section_label('3. Target Points'))
        layout.addWidget(separator())

        hint = QLabel('Preliminary indications — to be refined as the project progresses.')
        hint.setStyleSheet(f'color: {_MUTED}; font-size: 9px; background: transparent; border: none;')
        hint.setWordWrap(True)
        layout.addWidget(hint)

        fields = [
            ('Dimensions',        '_f_dimensions',  ''),
            ('Target weight',     '_f_weight',      'g'),
            ('Target total cost', '_f_cost',        '€'),
            ('Other constraints', '_f_constraints', ''),
        ]
        for label, attr, unit in fields:
            row = QHBoxLayout()
            row.setSpacing(6)
            lbl = QLabel(label)
            lbl.setStyleSheet(LABEL_STYLE)
            row.addWidget(lbl, 1)
            inp = make_input('')
            inp.setMinimumHeight(26)
            setattr(self, attr, inp)
            row.addWidget(inp, 2)
            if unit:
                u = QLabel(unit)
                u.setStyleSheet(
                    f'color: {_MUTED}; font-size: 10px; background: transparent; border: none;'
                )
                u.setFixedWidth(14)
                row.addWidget(u)
            layout.addLayout(row)

        layout.addStretch()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(c)

    def set_edit_mode(self, enabled: bool):
        for attr in ('_f_dimensions', '_f_weight', '_f_cost', '_f_constraints'):
            getattr(self, attr).setReadOnly(not enabled)

    def get_data(self) -> dict:
        return {
            'dimensions':  self._f_dimensions.text(),
            'weight':      self._f_weight.text(),
            'cost':        self._f_cost.text(),
            'constraints': self._f_constraints.text(),
        }

    def set_data(self, data: dict):
        self._f_dimensions.setText(data.get('dimensions', ''))
        self._f_weight.setText(data.get('weight', ''))
        self._f_cost.setText(data.get('cost', ''))
        self._f_constraints.setText(data.get('constraints', ''))

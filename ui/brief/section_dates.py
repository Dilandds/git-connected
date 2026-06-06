"""Section 4 — Target Dates card."""
from PyQt5.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel
from PyQt5.QtCore import QDate
from .shared import _MUTED, LABEL_STYLE, card, section_label, make_textarea, make_date_edit, separator


class TargetDatesCard(QFrame):
    """Section 4: Target Dates (delivery, prototype, production + notes)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        c = card()
        layout = QVBoxLayout(c)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(section_label('4. Target Dates'))
        layout.addWidget(separator())

        date_fields = [
            ('Expected delivery date',      '_d_delivery'),
            ('Expected mockup / prototype', '_d_prototype'),
            ('Expected production start',   '_d_production'),
        ]
        for label, attr in date_fields:
            row = QHBoxLayout()
            row.setSpacing(6)
            lbl = QLabel(label)
            lbl.setStyleSheet(LABEL_STYLE)
            lbl.setWordWrap(True)
            row.addWidget(lbl, 2)
            d = make_date_edit()
            setattr(self, attr, d)
            row.addWidget(d, 2)
            layout.addLayout(row)

        layout.addWidget(separator())
        notes_lbl = QLabel('Notes')
        notes_lbl.setStyleSheet(LABEL_STYLE)
        layout.addWidget(notes_lbl)
        self._f_date_notes = make_textarea('Notes and additional details...', 60)
        layout.addWidget(self._f_date_notes)
        layout.addStretch()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(c)

    def set_edit_mode(self, enabled: bool):
        for attr in ('_d_delivery', '_d_prototype', '_d_production'):
            getattr(self, attr).setEnabled(enabled)
        self._f_date_notes.setReadOnly(not enabled)

    def get_data(self) -> dict:
        return {
            'delivery_date':   self._d_delivery.date().toString('dd/MM/yyyy'),
            'prototype_date':  self._d_prototype.date().toString('dd/MM/yyyy'),
            'production_date': self._d_production.date().toString('dd/MM/yyyy'),
            'date_notes':      self._f_date_notes.toPlainText(),
        }

    def set_data(self, data: dict):
        for attr, key in [
            ('_d_delivery', 'delivery_date'),
            ('_d_prototype', 'prototype_date'),
            ('_d_production', 'production_date'),
        ]:
            val = data.get(key, '')
            if val:
                d = QDate.fromString(val, 'dd/MM/yyyy')
                if d.isValid():
                    getattr(self, attr).setDate(d)
        self._f_date_notes.setPlainText(data.get('date_notes', ''))

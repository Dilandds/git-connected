"""Section 6 — Components, Materials & Colours card."""
from PyQt5.QtWidgets import QFrame, QVBoxLayout
from .shared import card, section_label, separator
from .widgets import ComponentsTable
from i18n import t


class ComponentsCard(QFrame):
    """Section 6: Components, Materials & Colours."""

    def __init__(self, parent=None):
        super().__init__(parent)
        c = card()
        layout = QVBoxLayout(c)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(section_label(t('project.brief.s6_title')))
        layout.addWidget(separator())

        self._table = ComponentsTable()
        layout.addWidget(self._table, 1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(c, 1)

    def set_edit_mode(self, enabled: bool):
        self._table.set_edit_mode(enabled)

    def get_data(self) -> dict:
        return {'components': self._table.get_data()}

    def set_data(self, data: dict):
        if data.get('components'):
            self._table.set_data(data['components'])

    def get_components(self) -> list:
        """Convenience accessor used by TraceabilityWidget sync."""
        return self._table.get_data()

    def replace_components(self, rows: list):
        """Replace all component rows (used for traceability→brief sync)."""
        self._table.replace_data(rows)

"""Section 7 — Notes card."""
from PyQt5.QtWidgets import QFrame, QVBoxLayout, QLabel
from .shared import _MUTED, card, section_label, make_textarea, separator


class NotesCard(QFrame):
    """Section 7: Notes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        c = card()
        layout = QVBoxLayout(c)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(section_label('7. Notes'))
        layout.addWidget(separator())

        hint = QLabel('Any additional information, remarks, ideas...')
        hint.setStyleSheet(f'color: {_MUTED}; font-size: 10px; background: transparent; border: none;')
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._f_notes = make_textarea('Additional notes...', min_height=120)
        layout.addWidget(self._f_notes)
        layout.addStretch()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(c)

    def set_edit_mode(self, enabled: bool):
        self._f_notes.setReadOnly(not enabled)

    def get_data(self) -> dict:
        return {'notes': self._f_notes.toPlainText()}

    def set_data(self, data: dict):
        self._f_notes.setPlainText(data.get('notes', ''))

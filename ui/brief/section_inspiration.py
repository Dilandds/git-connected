"""Section 5 — Inspiration / Idea / Direction card."""
from PyQt5.QtWidgets import QFrame, QVBoxLayout, QLabel
from .shared import _MUTED, card, section_label, make_textarea, separator


class InspirationCard(QFrame):
    """Section 5: Inspiration / Idea / Direction."""

    def __init__(self, parent=None):
        super().__init__(parent)
        c = card()
        layout = QVBoxLayout(c)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(section_label('5. Inspiration / Idea / Direction'))
        layout.addWidget(separator())

        hint = QLabel('References, ideas, visual atmosphere, design direction.')
        hint.setStyleSheet(f'color: {_MUTED}; font-size: 10px; background: transparent; border: none;')
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._f_inspiration = make_textarea(
            'Describe the main idea, the inspiration and the design direction...',
            min_height=120,
        )
        layout.addWidget(self._f_inspiration)
        layout.addStretch()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(c)

    def set_edit_mode(self, enabled: bool):
        self._f_inspiration.setReadOnly(not enabled)

    def get_data(self) -> dict:
        return {'inspiration': self._f_inspiration.toPlainText()}

    def set_data(self, data: dict):
        self._f_inspiration.setPlainText(data.get('inspiration', ''))

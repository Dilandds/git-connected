"""
Color picker popup for the freehand drawing tool.
Displays a grid of preset color swatches and a custom color option.
"""
from PyQt5.QtWidgets import (
    QWidget, QGridLayout, QPushButton, QVBoxLayout, QColorDialog, QLabel
)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QColor
from ui.styles import default_theme


PRESET_COLORS = [
    '#FF0000', '#FF6600', '#FFCC00', '#33CC33',
    '#0099FF', '#6633FF', '#FF33CC', '#00CCCC',
    '#FFFFFF', '#000000', '#888888', '#8B4513',
]


class DrawColorPicker(QWidget):
    """Popup widget showing preset color swatches and a custom color button."""

    color_selected = pyqtSignal(str)  # hex color string

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {default_theme.card_background};
                border: 1px solid {default_theme.border_standard};
                border-radius: 8px;
            }}
        """)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        title = QLabel("Pen Color")
        title.setStyleSheet(f"color: {default_theme.text_primary}; font-size: 11px; font-weight: bold; border: none;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(4)
        for i, color in enumerate(PRESET_COLORS):
            btn = QPushButton()
            btn.setFixedSize(24, 24)
            border_color = '#aaa' if color.upper() == '#FFFFFF' else 'transparent'
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    border: 1px solid {border_color};
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    border: 2px solid {default_theme.button_primary};
                }}
            """)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(color)
            btn.clicked.connect(lambda checked, c=color: self._pick(c))
            grid.addWidget(btn, i // 4, i % 4)
        layout.addLayout(grid)

        custom_btn = QPushButton("Custom…")
        custom_btn.setFixedHeight(26)
        custom_btn.setCursor(Qt.PointingHandCursor)
        custom_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {default_theme.row_bg_standard};
                color: {default_theme.text_primary};
                border: 1px solid {default_theme.border_standard};
                border-radius: 6px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {default_theme.row_bg_hover};
            }}
        """)
        custom_btn.clicked.connect(self._pick_custom)
        layout.addWidget(custom_btn)

    def _pick(self, color: str):
        self.color_selected.emit(color)
        self.close()

    def _pick_custom(self):
        color = QColorDialog.getColor(QColor('#FF0000'), self.parent(), "Choose Pen Color")
        if color.isValid():
            self.color_selected.emit(color.name())
        self.close()

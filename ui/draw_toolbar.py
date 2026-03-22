"""
Floating toolbar shown when draw mode is active.
Provides: Color picker, Eraser toggle, Undo last stroke, Clear all.
"""
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QPushButton, QFrame
from PyQt5.QtCore import pyqtSignal, Qt
from ui.styles import default_theme


class DrawToolbar(QWidget):
    """Small floating toolbar for draw mode actions."""

    color_picker_requested = pyqtSignal()
    eraser_toggled = pyqtSignal(bool)  # True = eraser on
    undo_requested = pyqtSignal()
    clear_all_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._eraser_active = False
        self.setFixedHeight(36)
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {default_theme.card_background};
                border: 1px solid {default_theme.border_standard};
                border-radius: 8px;
            }}
        """)
        self._build_ui()
        self.hide()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(3)

        btn_style = f"""
            QPushButton {{
                background-color: {default_theme.row_bg_standard};
                color: {default_theme.text_primary};
                border: 1px solid {default_theme.border_standard};
                border-radius: 6px;
                font-size: 12px;
                padding: 2px 8px;
                min-width: 28px;
            }}
            QPushButton:hover {{
                background-color: {default_theme.row_bg_hover};
            }}
        """
        active_style = f"""
            QPushButton {{
                background-color: {default_theme.button_primary};
                color: #fff;
                border: 1px solid {default_theme.button_primary};
                border-radius: 6px;
                font-size: 12px;
                padding: 2px 8px;
                min-width: 28px;
            }}
            QPushButton:hover {{
                background-color: {default_theme.button_primary_hover};
            }}
        """

        self._color_btn = QPushButton("🎨")
        self._color_btn.setToolTip("Change pen color")
        self._color_btn.setFixedSize(32, 28)
        self._color_btn.setStyleSheet(btn_style)
        self._color_btn.setCursor(Qt.PointingHandCursor)
        self._color_btn.clicked.connect(self.color_picker_requested.emit)
        layout.addWidget(self._color_btn)

        self._eraser_btn = QPushButton("🧹")
        self._eraser_btn.setToolTip("Eraser — click on strokes to remove them")
        self._eraser_btn.setFixedSize(32, 28)
        self._eraser_btn.setStyleSheet(btn_style)
        self._eraser_btn.setCursor(Qt.PointingHandCursor)
        self._eraser_btn.clicked.connect(self._toggle_eraser)
        layout.addWidget(self._eraser_btn)
        self._btn_style = btn_style
        self._active_style = active_style

        self._undo_btn = QPushButton("↩")
        self._undo_btn.setToolTip("Undo last stroke")
        self._undo_btn.setFixedSize(32, 28)
        self._undo_btn.setStyleSheet(btn_style)
        self._undo_btn.setCursor(Qt.PointingHandCursor)
        self._undo_btn.clicked.connect(self.undo_requested.emit)
        layout.addWidget(self._undo_btn)

        self._clear_btn = QPushButton("🗑")
        self._clear_btn.setToolTip("Clear all drawings")
        self._clear_btn.setFixedSize(32, 28)
        self._clear_btn.setStyleSheet(btn_style)
        self._clear_btn.setCursor(Qt.PointingHandCursor)
        self._clear_btn.clicked.connect(self.clear_all_requested.emit)
        layout.addWidget(self._clear_btn)

    def _toggle_eraser(self):
        self._eraser_active = not self._eraser_active
        self._eraser_btn.setStyleSheet(self._active_style if self._eraser_active else self._btn_style)
        self.eraser_toggled.emit(self._eraser_active)

    @property
    def eraser_active(self):
        return self._eraser_active

    def reset(self):
        """Reset eraser state when draw mode is exited."""
        self._eraser_active = False
        self._eraser_btn.setStyleSheet(self._btn_style)
        self.hide()

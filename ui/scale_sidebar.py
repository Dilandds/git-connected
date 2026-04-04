"""
Scale Sidebar — controls for the Drawing Scale Calibration mode.
Upload, unit selection, scale ratio, ruler toggle, reset.
"""
import logging
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QFrame, QSizePolicy, QScrollArea, QTextEdit,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from ui.styles import default_theme, make_font, sidebar_section_card_stylesheet

logger = logging.getLogger(__name__)

SIDEBAR_WIDTH = 220


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(make_font(size=10, bold=True))
    lbl.setStyleSheet(f"color: {default_theme.text_title}; padding: 0; margin: 0;")
    return lbl


def _styled_combo() -> QComboBox:
    combo = QComboBox()
    combo.setFixedHeight(28)
    combo.setCursor(Qt.PointingHandCursor)
    combo.setStyleSheet(f"""
        QComboBox {{
            background: {default_theme.input_bg};
            border: 1px solid {default_theme.input_border};
            border-radius: 4px;
            padding: 2px 8px;
            color: {default_theme.text_primary};
            font-size: 11px;
        }}
        QComboBox:hover {{
            border-color: {default_theme.input_border_hover};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 20px;
        }}
        QComboBox QAbstractItemView {{
            background: {default_theme.card_background};
            color: {default_theme.text_primary};
            selection-background-color: {default_theme.button_primary};
            border: 1px solid {default_theme.border_light};
        }}
    """)
    return combo


class ScaleSidebar(QWidget):
    """Sidebar controls for Drawing Scale mode."""

    upload_requested = pyqtSignal()
    unit_changed = pyqtSignal(str)  # "cm" | "mm" | "inches"
    scale_changed = pyqtSignal(float)  # ratio value
    ruler_toggled = pyqtSignal(bool)
    reset_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(SIDEBAR_WIDTH)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self._ruler_active = False
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Title
        title = QLabel("📐 Drawing Scale")
        title.setFont(make_font(size=13, bold=True))
        title.setStyleSheet(f"color: {default_theme.text_title};")
        layout.addWidget(title)

        # Upload button
        self.upload_btn = QPushButton("📂  Upload Drawing")
        self.upload_btn.setFixedHeight(36)
        self.upload_btn.setCursor(Qt.PointingHandCursor)
        self.upload_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {default_theme.button_primary},
                    stop:1 {default_theme.button_primary_pressed});
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {default_theme.button_primary_hover};
            }}
        """)
        self.upload_btn.clicked.connect(self.upload_requested.emit)
        layout.addWidget(self.upload_btn)

        # Separator
        layout.addWidget(self._separator())

        # Unit selector
        layout.addWidget(_section_label("Unit"))
        self.unit_combo = _styled_combo()
        self.unit_combo.addItems(["Centimeters (cm)", "Millimeters (mm)", "Inches (in)"])
        self.unit_combo.currentIndexChanged.connect(self._on_unit_changed)
        layout.addWidget(self.unit_combo)

        # Scale ratio
        layout.addWidget(_section_label("Scale Ratio"))
        self.scale_combo = _styled_combo()
        self.scale_combo.addItems(["1:1", "1:2", "1:5", "1:10"])
        self.scale_combo.currentIndexChanged.connect(self._on_scale_changed)
        layout.addWidget(self.scale_combo)

        # Separator
        layout.addWidget(self._separator())

        # Ruler toggle
        self.ruler_btn = QPushButton("📏  Ruler Tool")
        self.ruler_btn.setFixedHeight(32)
        self.ruler_btn.setCheckable(True)
        self.ruler_btn.setCursor(Qt.PointingHandCursor)
        self._update_ruler_btn_style(False)
        self.ruler_btn.clicked.connect(self._on_ruler_toggled)
        layout.addWidget(self.ruler_btn)

        # Reset button
        self.reset_btn = QPushButton("🗑  Reset")
        self.reset_btn.setFixedHeight(30)
        self.reset_btn.setCursor(Qt.PointingHandCursor)
        self.reset_btn.setStyleSheet(f"""
            QPushButton {{
                background: {default_theme.button_default_bg};
                border: 1px solid {default_theme.button_default_border};
                border-radius: 5px;
                color: {default_theme.text_secondary};
                font-size: 11px;
            }}
            QPushButton:hover {{
                background: {default_theme.row_bg_hover};
                color: {default_theme.text_primary};
            }}
        """)
        self.reset_btn.clicked.connect(self.reset_requested.emit)
        layout.addWidget(self.reset_btn)

        # Separator
        layout.addWidget(self._separator())

        # Instructions
        layout.addWidget(_section_label("How to use"))
        instructions = QLabel(
            "1. Upload a drawing (PDF/image)\n"
            "2. Use scroll wheel to resize the\n"
            "   drawing proportionally\n"
            "3. Align the drawing's reference\n"
            "   dimension with the ruler frame\n"
            "4. Enable Ruler Tool to measure"
        )
        instructions.setWordWrap(True)
        instructions.setFont(make_font(size=9))
        instructions.setStyleSheet(f"color: {default_theme.text_subtext}; line-height: 1.4;")
        layout.addWidget(instructions)

        layout.addStretch()

    def _separator(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {default_theme.separator}; border: none;")
        return sep

    def _on_unit_changed(self, index: int):
        units = ["cm", "mm", "inches"]
        if 0 <= index < len(units):
            self.unit_changed.emit(units[index])

    def _on_scale_changed(self, index: int):
        ratios = [1.0, 2.0, 5.0, 10.0]
        if 0 <= index < len(ratios):
            self.scale_changed.emit(ratios[index])

    def _on_ruler_toggled(self):
        self._ruler_active = self.ruler_btn.isChecked()
        self._update_ruler_btn_style(self._ruler_active)
        self.ruler_toggled.emit(self._ruler_active)

    def _update_ruler_btn_style(self, active: bool):
        if active:
            self.ruler_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {default_theme.button_primary};
                    color: white;
                    border: none;
                    border-radius: 5px;
                    font-size: 11px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background: {default_theme.button_primary_hover};
                }}
            """)
        else:
            self.ruler_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {default_theme.button_default_bg};
                    border: 1px solid {default_theme.button_default_border};
                    border-radius: 5px;
                    color: {default_theme.text_secondary};
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    background: {default_theme.row_bg_hover};
                    color: {default_theme.text_primary};
                }}
            """)

    def reset(self):
        """Reset controls to defaults."""
        self.unit_combo.setCurrentIndex(0)
        self.scale_combo.setCurrentIndex(0)
        self.ruler_btn.setChecked(False)
        self._ruler_active = False
        self._update_ruler_btn_style(False)

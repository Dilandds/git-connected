"""
Scale Sidebar — controls for the Drawing Scale Calibration mode.
Upload, unit selection, scale ratio, ruler toggle, add reference line, reset, export.
White theme to match Technical Overview.
"""
import logging
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QFrame, QSizePolicy, QScrollArea, QTextEdit,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from ui.styles import make_font

logger = logging.getLogger(__name__)

SIDEBAR_WIDTH = 220

# White theme colors
_BG = "#FFFFFF"
_CARD_BG = "#F9F9F9"
_BORDER = "#E0E0E0"
_TEXT_TITLE = "#212121"
_TEXT_PRIMARY = "#424242"
_TEXT_SECONDARY = "#757575"
_TEXT_SUBTEXT = "#9E9E9E"
_INPUT_BG = "#FFFFFF"
_INPUT_BORDER = "#BDBDBD"
_INPUT_BORDER_HOVER = "#757575"
_BTN_PRIMARY = "#1976D2"
_BTN_PRIMARY_HOVER = "#1565C0"
_BTN_PRIMARY_PRESSED = "#0D47A1"
_BTN_DEFAULT_BG = "#FAFAFA"
_BTN_DEFAULT_BORDER = "#E0E0E0"
_ROW_HOVER = "#F5F5F5"
_SEPARATOR = "#EEEEEE"


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(make_font(size=10, bold=True))
    lbl.setStyleSheet(f"color: {_TEXT_TITLE}; padding: 0; margin: 0;")
    return lbl


def _styled_combo() -> QComboBox:
    combo = QComboBox()
    combo.setFixedHeight(28)
    combo.setCursor(Qt.PointingHandCursor)
    combo.setStyleSheet(f"""
        QComboBox {{
            background: {_INPUT_BG};
            border: 1px solid {_INPUT_BORDER};
            border-radius: 4px;
            padding: 2px 8px;
            color: {_TEXT_PRIMARY};
            font-size: 11px;
        }}
        QComboBox:hover {{
            border-color: {_INPUT_BORDER_HOVER};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 20px;
        }}
        QComboBox QAbstractItemView {{
            background: {_BG};
            color: {_TEXT_PRIMARY};
            selection-background-color: {_BTN_PRIMARY};
            border: 1px solid {_BORDER};
        }}
    """)
    return combo


class ScaleSidebar(QWidget):
    """Sidebar controls for Drawing Scale mode — white theme."""

    upload_requested = pyqtSignal()
    unit_changed = pyqtSignal(str)  # "cm" | "mm" | "inches" | "m"
    scale_changed = pyqtSignal(float)  # ratio value
    ruler_toggled = pyqtSignal(bool)
    reset_requested = pyqtSignal()
    export_requested = pyqtSignal()
    add_reference_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(SIDEBAR_WIDTH)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self._ruler_active = False
        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet(f"background-color: {_BG};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Title
        title = QLabel("📐 Drawing Scale")
        title.setFont(make_font(size=13, bold=True))
        title.setStyleSheet(f"color: {_TEXT_TITLE};")
        layout.addWidget(title)

        # Upload button
        self.upload_btn = QPushButton("📂  Upload Drawing")
        self.upload_btn.setFixedHeight(36)
        self.upload_btn.setCursor(Qt.PointingHandCursor)
        self.upload_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {_BTN_PRIMARY},
                    stop:1 {_BTN_PRIMARY_PRESSED});
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {_BTN_PRIMARY_HOVER};
            }}
        """)
        self.upload_btn.clicked.connect(self.upload_requested.emit)
        layout.addWidget(self.upload_btn)

        # Separator
        layout.addWidget(self._separator())

        # Unit selector
        layout.addWidget(_section_label("Unit"))
        self.unit_combo = _styled_combo()
        self.unit_combo.addItems([
            "Centimeters (cm)",
            "Millimeters (mm)",
            "Inches (in)",
            "Meters (m)",
        ])
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

        # Add reference line button
        self.add_ref_btn = QPushButton("➕  Add Reference Line")
        self.add_ref_btn.setFixedHeight(30)
        self.add_ref_btn.setCursor(Qt.PointingHandCursor)
        self.add_ref_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_BTN_DEFAULT_BG};
                border: 1px solid {_BTN_DEFAULT_BORDER};
                border-radius: 5px;
                color: {_TEXT_PRIMARY};
                font-size: 11px;
            }}
            QPushButton:hover {{
                background: {_ROW_HOVER};
                border-color: {_BTN_PRIMARY};
                color: {_BTN_PRIMARY};
            }}
        """)
        self.add_ref_btn.clicked.connect(self.add_reference_requested.emit)
        layout.addWidget(self.add_ref_btn)

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
                background: {_BTN_DEFAULT_BG};
                border: 1px solid {_BTN_DEFAULT_BORDER};
                border-radius: 5px;
                color: {_TEXT_SECONDARY};
                font-size: 11px;
            }}
            QPushButton:hover {{
                background: {_ROW_HOVER};
                color: {_TEXT_PRIMARY};
            }}
        """)
        self.reset_btn.clicked.connect(self.reset_requested.emit)
        layout.addWidget(self.reset_btn)

        # Export button
        self.export_btn = QPushButton("💾  Export Scaled")
        self.export_btn.setFixedHeight(32)
        self.export_btn.setCursor(Qt.PointingHandCursor)
        self.export_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #43A047, stop:1 #2E7D32);
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: #388E3C;
            }}
        """)
        self.export_btn.clicked.connect(self.export_requested.emit)
        layout.addWidget(self.export_btn)

        # Separator
        layout.addWidget(self._separator())

        # Instructions
        layout.addWidget(_section_label("How to use"))
        instructions = QLabel(
            "1. Upload a drawing (PDF/image)\n"
            "2. Use scroll wheel to resize the\n"
            "   drawing proportionally\n"
            "3. Align the reference line with\n"
            "   the ruler frame graduations\n"
            "4. Add more reference lines with ➕\n"
            "5. Enable Ruler Tool to measure\n\n"
            "Scale 1:2 → reference halved,\n"
            "graduations doubled (for big plans)"
        )
        instructions.setWordWrap(True)
        instructions.setFont(make_font(size=9))
        instructions.setStyleSheet(f"color: {_TEXT_SUBTEXT}; line-height: 1.4;")
        layout.addWidget(instructions)

        layout.addStretch()

    def _separator(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {_SEPARATOR}; border: none;")
        return sep

    def _on_unit_changed(self, index: int):
        units = ["cm", "mm", "inches", "m"]
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
                    background: {_BTN_PRIMARY};
                    color: white;
                    border: none;
                    border-radius: 5px;
                    font-size: 11px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background: {_BTN_PRIMARY_HOVER};
                }}
            """)
        else:
            self.ruler_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {_BTN_DEFAULT_BG};
                    border: 1px solid {_BTN_DEFAULT_BORDER};
                    border-radius: 5px;
                    color: {_TEXT_SECONDARY};
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    background: {_ROW_HOVER};
                    color: {_TEXT_PRIMARY};
                }}
            """)

    def reset(self):
        """Reset controls to defaults."""
        self.unit_combo.setCurrentIndex(0)
        self.scale_combo.setCurrentIndex(0)
        self.ruler_btn.setChecked(False)
        self._ruler_active = False
        self._update_ruler_btn_style(False)

"""
Scale Sidebar — controls for the Drawing Scale Calibration mode.
Upload, unit selection, scale ratio, ruler toggle, reset.
Styled to match Technical Overview sidebar (white fields, dark labels).
"""
import logging
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QFrame, QSizePolicy, QScrollArea,
)
from PyQt5.QtCore import Qt, pyqtSignal
from ui.styles import default_theme, make_font
from ui.technical_sidebar import (
    _FIELD_BG,
    _FIELD_TEXT,
    _FIELD_BORDER,
    _apply_field_palette,
    _section_label,
)

logger = logging.getLogger(__name__)

SIDEBAR_WIDTH = 260


def _styled_combo() -> QComboBox:
    """White surface combo matching Technical Overview line edits."""
    combo = QComboBox()
    combo.setFixedHeight(30)
    combo.setCursor(Qt.PointingHandCursor)
    combo.setStyleSheet(f"""
        QComboBox {{
            background-color: {_FIELD_BG};
            border: 1px solid {_FIELD_BORDER};
            border-radius: 6px;
            padding: 4px 8px;
            font-size: 11px;
            color: {_FIELD_TEXT};
        }}
        QComboBox:hover {{
            border: 1px solid {default_theme.input_border_hover};
        }}
        QComboBox:focus {{
            border: 2px solid {default_theme.button_primary};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 22px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {_FIELD_BG};
            color: {_FIELD_TEXT};
            selection-background-color: {default_theme.button_primary};
            selection-color: white;
            border: 1px solid {_FIELD_BORDER};
            border-radius: 4px;
            padding: 4px;
        }}
    """)
    _apply_field_palette(combo)
    return combo


class ScaleSidebar(QWidget):
    """Sidebar controls for Drawing Scale mode."""

    upload_requested = pyqtSignal()
    unit_changed = pyqtSignal(str)  # "cm" | "mm" | "inches"
    scale_changed = pyqtSignal(float)  # ratio value
    ruler_toggled = pyqtSignal(bool)
    reset_requested = pyqtSignal()
    export_requested = pyqtSignal()
    add_ref_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(SIDEBAR_WIDTH)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self._ruler_active = False
        self._init_ui()

    def _init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Title header
        title = QLabel("📐 Drawing Scale")
        title.setFont(make_font(size=13, bold=True))
        title.setStyleSheet(f"color: {default_theme.text_title};")
        layout.addWidget(title)

        # Upload button (same pattern as Technical Overview)
        self.upload_btn = QPushButton("📂 Upload Drawing")
        self.upload_btn.setFixedHeight(34)
        self.upload_btn.setCursor(Qt.PointingHandCursor)
        self.upload_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {default_theme.row_bg_standard};
                border: 1px solid {default_theme.border_light};
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: bold;
                color: {default_theme.text_primary};
            }}
            QPushButton:hover {{
                background-color: {default_theme.row_bg_hover};
            }}
        """)
        self.upload_btn.clicked.connect(self.upload_requested.emit)
        layout.addWidget(self.upload_btn)

        layout.addWidget(self._separator())

        layout.addWidget(_section_label("UNIT"))
        self.unit_combo = _styled_combo()
        self.unit_combo.addItems(["Centimeters (cm)", "Millimeters (mm)", "Inches (in)", "Meters (m)"])
        self.unit_combo.currentIndexChanged.connect(self._on_unit_changed)
        layout.addWidget(self.unit_combo)

        layout.addWidget(_section_label("SCALE RATIO"))
        self.scale_combo = _styled_combo()
        self.scale_combo.addItems(["1:1", "1:2", "1:5", "1:10"])
        self.scale_combo.currentIndexChanged.connect(self._on_scale_changed)
        layout.addWidget(self.scale_combo)

        layout.addWidget(self._separator())

        # Ruler toggle — same family as Technical "Annotate"
        self.ruler_btn = QPushButton("📏 Ruler Tool")
        self.ruler_btn.setFixedHeight(34)
        self.ruler_btn.setCheckable(True)
        self.ruler_btn.setCursor(Qt.PointingHandCursor)
        self._update_ruler_btn_style(False)
        self.ruler_btn.clicked.connect(self._on_ruler_toggled)
        layout.addWidget(self.ruler_btn)

        # Add Reference — outlined accent (dark-theme-safe hover)
        self.add_ref_btn = QPushButton("📌 Add Reference")
        self.add_ref_btn.setFixedHeight(34)
        self.add_ref_btn.setCursor(Qt.PointingHandCursor)
        self.add_ref_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {default_theme.row_bg_standard};
                border: 1px solid {default_theme.button_primary};
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: bold;
                color: {default_theme.button_primary};
            }}
            QPushButton:hover {{
                background-color: {default_theme.row_bg_hover};
                border-color: {default_theme.button_primary_hover};
                color: {default_theme.icon_blue};
            }}
        """)
        self.add_ref_btn.clicked.connect(self.add_ref_requested.emit)
        layout.addWidget(self.add_ref_btn)

        # Reset — red destructive (matches Technical "Reset Workspace")
        self.reset_btn = QPushButton("🗑 Reset")
        self.reset_btn.setFixedHeight(34)
        self.reset_btn.setCursor(Qt.PointingHandCursor)
        self.reset_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #B91C1C;
                border: none;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: bold;
                color: white;
            }}
            QPushButton:hover {{
                background-color: #991B1B;
            }}
        """)
        self.reset_btn.clicked.connect(self.reset_requested.emit)
        layout.addWidget(self.reset_btn)

        # Export — same green as Technical "Export .ecto"
        self.export_btn = QPushButton("💾 Export Scaled")
        self.export_btn.setFixedHeight(34)
        self.export_btn.setCursor(Qt.PointingHandCursor)
        self.export_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #10B981;
                border: none;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: bold;
                color: white;
            }}
            QPushButton:hover {{
                background-color: #059669;
            }}
        """)
        self.export_btn.clicked.connect(self.export_requested.emit)
        layout.addWidget(self.export_btn)

        layout.addWidget(self._separator())

        layout.addWidget(_section_label("HOW TO USE"))
        instructions = QLabel(
            "1. Upload a drawing (PDF/image)\n"
            "2. Use scroll wheel to resize the drawing proportionally\n"
            "3. Align the drawing's reference dimension with the ruler frame\n"
            "4. Enable Ruler Tool to measure"
        )
        instructions.setWordWrap(True)
        instructions.setFont(make_font(size=9))
        instructions.setStyleSheet(
            f"color: {default_theme.text_secondary}; line-height: 1.45; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(instructions)

        layout.addStretch()

        scroll.setWidget(container)
        outer.addWidget(scroll)

    def _separator(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {default_theme.separator}; border: none;")
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
                    background-color: {default_theme.row_bg_highlight};
                    border: 1px solid {default_theme.border_highlight};
                    border-radius: 6px;
                    padding: 6px 12px;
                    font-size: 11px;
                    font-weight: bold;
                    color: {default_theme.text_primary};
                }}
                QPushButton:hover {{
                    background-color: {default_theme.row_bg_highlight_hover};
                }}
            """)
        else:
            self.ruler_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {default_theme.row_bg_standard};
                    border: 1px solid {default_theme.border_light};
                    border-radius: 6px;
                    padding: 6px 12px;
                    font-size: 11px;
                    color: {default_theme.text_primary};
                }}
                QPushButton:hover {{
                    background-color: {default_theme.row_bg_hover};
                }}
            """)

    def reset(self):
        """Reset controls to defaults and notify listeners (ruler off, unit/ratio defaults)."""
        self.unit_combo.blockSignals(True)
        self.scale_combo.blockSignals(True)
        self.unit_combo.setCurrentIndex(0)
        self.scale_combo.setCurrentIndex(0)
        self.unit_combo.blockSignals(False)
        self.scale_combo.blockSignals(False)
        self.unit_changed.emit("cm")
        self.scale_changed.emit(1.0)
        self.ruler_btn.setChecked(False)
        self._ruler_active = False
        self._update_ruler_btn_style(False)
        self.ruler_toggled.emit(False)

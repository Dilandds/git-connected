"""
Scale Sidebar — controls for the Drawing Scale Calibration mode.
Upload, unit selection, scale ratio, ruler toggle, reset.
Styled to match Technical Overview sidebar (white fields, dark labels).
"""
import logging
from typing import Optional
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QFrame, QSizePolicy, QScrollArea, QColorDialog,
    QGraphicsDropShadowEffect
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize, QPointF
from PyQt5.QtGui import QColor, QIcon, QPixmap, QPainter, QPen, QPolygonF
from ui.styles import default_theme, make_font, sidebar_section_card_stylesheet
from i18n import t, on_language_changed
from ui.technical_sidebar import (
    _FIELD_BG,
    _FIELD_TEXT,
    _FIELD_BORDER,
    _apply_field_palette,
    _section_label,
)

logger = logging.getLogger(__name__)

SIDEBAR_WIDTH = 350


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
    static_border_toggled = pyqtSignal(bool)  # hide/show static border
    moving_border_toggled = pyqtSignal(bool)  # hide/show moving border
    ref_lines_toggled = pyqtSignal(bool)  # hide/show dotted reference lines
    pdf_locked = pyqtSignal(bool)  # lock/unlock PDF position
    drawing_mode_changed = pyqtSignal(str)  # "arrow" | "rectangle" | "circle" | "move" | "erase" | ""
    drawing_color_changed = pyqtSignal(QColor)  # color for drawing shapes

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(SIDEBAR_WIDTH)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self._ruler_active = False
        self._static_border_visible = True
        self._moving_border_visible = True
        self._ref_lines_visible = True
        self._pdf_locked = False
        self._drawing_color = QColor("#FFFF00")
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

        # Hide static border toggle
        self.static_border_btn = QPushButton("👁 Show Static Border")
        self.static_border_btn.setFixedHeight(34)
        self.static_border_btn.setCheckable(True)
        self.static_border_btn.setChecked(True)
        self.static_border_btn.setCursor(Qt.PointingHandCursor)
        self._update_static_border_btn_style(True)
        self.static_border_btn.clicked.connect(self._on_static_border_toggled)
        layout.addWidget(self.static_border_btn)

        # Hide moving border toggle
        self.moving_border_btn = QPushButton("👁 Show Moving Border")
        self.moving_border_btn.setFixedHeight(34)
        self.moving_border_btn.setCheckable(True)
        self.moving_border_btn.setChecked(True)
        self.moving_border_btn.setCursor(Qt.PointingHandCursor)
        self._update_moving_border_btn_style(True)
        self.moving_border_btn.clicked.connect(self._on_moving_border_toggled)
        layout.addWidget(self.moving_border_btn)

        # Hide dotted reference lines toggle
        self.ref_lines_btn = QPushButton("👁 Show References")
        self.ref_lines_btn.setFixedHeight(34)
        self.ref_lines_btn.setCheckable(True)
        self.ref_lines_btn.setChecked(True)
        self.ref_lines_btn.setCursor(Qt.PointingHandCursor)
        self._update_ref_lines_btn_style(True)
        self.ref_lines_btn.clicked.connect(self._on_ref_lines_toggled)
        layout.addWidget(self.ref_lines_btn)

        # Lock document position toggle
        self.lock_btn = QPushButton("🔓 Unlock Document")
        self.lock_btn.setFixedHeight(34)
        self.lock_btn.setCheckable(True)
        self.lock_btn.setChecked(False)
        self.lock_btn.setCursor(Qt.PointingHandCursor)
        self._update_lock_btn_style(False)
        self.lock_btn.clicked.connect(self._on_pdf_locked)
        layout.addWidget(self.lock_btn)

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

        # Drawing shapes section
        layout.addWidget(_section_label("DRAW SHAPES"))
        
        # Drawing mode buttons (scrollable so sidebar width stays fixed)
        button_row = QHBoxLayout()
        button_row.setSpacing(4)

        tools_widget = QWidget()
        tools_layout = QHBoxLayout(tools_widget)
        tools_layout.setContentsMargins(0, 0, 0, 0)
        tools_layout.setSpacing(4)
        
        self.arrow_btn = QPushButton("➜")
        self.arrow_btn.setFixedWidth(44)
        self.arrow_btn.setFixedHeight(32)
        self.arrow_btn.setCheckable(True)
        self.arrow_btn.setCursor(Qt.PointingHandCursor)
        self.arrow_btn.setToolTip("Draw arrow")
        self.arrow_btn.clicked.connect(lambda: self._on_drawing_mode_clicked("arrow"))
        tools_layout.addWidget(self.arrow_btn)
        
        self.rectangle_btn = QPushButton("▭")
        self.rectangle_btn.setFixedWidth(44)
        self.rectangle_btn.setFixedHeight(32)
        self.rectangle_btn.setCheckable(True)
        self.rectangle_btn.setCursor(Qt.PointingHandCursor)
        self.rectangle_btn.setToolTip("Draw rectangle")
        self.rectangle_btn.clicked.connect(lambda: self._on_drawing_mode_clicked("rectangle"))
        tools_layout.addWidget(self.rectangle_btn)
        
        self.circle_btn = QPushButton("◯")
        self.circle_btn.setFixedWidth(44)
        self.circle_btn.setFixedHeight(32)
        self.circle_btn.setCheckable(True)
        self.circle_btn.setCursor(Qt.PointingHandCursor)
        self.circle_btn.setToolTip("Draw circle")
        self.circle_btn.clicked.connect(lambda: self._on_drawing_mode_clicked("circle"))
        tools_layout.addWidget(self.circle_btn)

        self.move_btn = QPushButton("✋")
        self.move_btn.setFixedWidth(44)
        self.move_btn.setFixedHeight(32)
        self.move_btn.setCheckable(True)
        self.move_btn.setCursor(Qt.PointingHandCursor)
        self.move_btn.setToolTip("Move drawings")
        self.move_btn.clicked.connect(lambda: self._on_drawing_mode_clicked("move"))
        tools_layout.addWidget(self.move_btn)

        self.erase_btn = QPushButton("⌫")
        self.erase_btn.setFixedWidth(44)
        self.erase_btn.setFixedHeight(32)
        self.erase_btn.setCheckable(True)
        self.erase_btn.setCursor(Qt.PointingHandCursor)
        self.erase_btn.setToolTip("Erase one drawing")
        self.erase_btn.clicked.connect(lambda: self._on_drawing_mode_clicked("erase"))
        tools_layout.addWidget(self.erase_btn)
        
        self.clear_shapes_btn = QPushButton("🗑")
        self.clear_shapes_btn.setFixedWidth(44)
        self.clear_shapes_btn.setFixedHeight(32)
        self.clear_shapes_btn.setCursor(Qt.PointingHandCursor)
        self.clear_shapes_btn.setToolTip("Clear all shapes")
        self.clear_shapes_btn.clicked.connect(self._on_clear_shapes)
        tools_layout.addWidget(self.clear_shapes_btn)
        
        tools_layout.addStretch()

        tools_scroll = QScrollArea()
        tools_scroll.setWidgetResizable(False)
        tools_scroll.setFrameShape(QFrame.NoFrame)
        tools_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tools_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        tools_scroll.setFixedHeight(52)
        tools_scroll.setWidget(tools_widget)

        button_row.addWidget(tools_scroll)
        layout.addLayout(button_row)
        
        # Color picker button
        self.color_btn = QPushButton("🎨 Color: ")
        self.color_btn.setFixedHeight(32)
        self.color_btn.setCursor(Qt.PointingHandCursor)
        self.color_btn.clicked.connect(self._on_color_picker)
        self._update_color_btn_style()
        layout.addWidget(self.color_btn)
        
        self._drawing_mode_buttons = {
            "arrow": self.arrow_btn,
            "rectangle": self.rectangle_btn,
            "circle": self.circle_btn,
            "move": self.move_btn,
            "erase": self.erase_btn,
        }
        self._current_drawing_mode: Optional[str] = None

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

    def _update_static_border_btn_style(self, visible: bool):
        """Update button appearance based on static border visibility."""
        if visible:
            style = f"""
                QPushButton {{
                    background-color: {default_theme.button_primary};
                    border: none;
                    border-radius: 6px;
                    padding: 6px 12px;
                    font-size: 11px;
                    font-weight: bold;
                    color: white;
                }}
                QPushButton:hover {{
                    background-color: {default_theme.button_primary_hover};
                }}
            """
        else:
            style = f"""
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
            """
        self.static_border_btn.setStyleSheet(style)
        self.static_border_btn.setText("👁 Show Static Border" if not visible else "👁 Hide Static Border")

    def _update_moving_border_btn_style(self, visible: bool):
        """Update button appearance based on moving border visibility."""
        if visible:
            style = f"""
                QPushButton {{
                    background-color: {default_theme.button_primary};
                    border: none;
                    border-radius: 6px;
                    padding: 6px 12px;
                    font-size: 11px;
                    font-weight: bold;
                    color: white;
                }}
                QPushButton:hover {{
                    background-color: {default_theme.button_primary_hover};
                }}
            """
        else:
            style = f"""
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
            """
        self.moving_border_btn.setStyleSheet(style)
        self.moving_border_btn.setText("👁 Show Moving Border" if not visible else "👁 Hide Moving Border")

    def _update_ref_lines_btn_style(self, visible: bool):
        """Update button appearance based on reference lines visibility."""
        if visible:
            style = f"""
                QPushButton {{
                    background-color: {default_theme.button_primary};
                    border: none;
                    border-radius: 6px;
                    padding: 6px 12px;
                    font-size: 11px;
                    font-weight: bold;
                    color: white;
                }}
                QPushButton:hover {{
                    background-color: {default_theme.button_primary_hover};
                }}
            """
        else:
            style = f"""
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
            """
        self.ref_lines_btn.setStyleSheet(style)
        self.ref_lines_btn.setText("👁 Show References" if not visible else "👁 Hide References")

    def _on_static_border_toggled(self):
        """Handle static border visibility toggle."""
        self._static_border_visible = self.static_border_btn.isChecked()
        self._update_static_border_btn_style(self._static_border_visible)
        self.static_border_toggled.emit(self._static_border_visible)

    def _on_moving_border_toggled(self):
        """Handle moving border visibility toggle."""
        self._moving_border_visible = self.moving_border_btn.isChecked()
        self._update_moving_border_btn_style(self._moving_border_visible)
        self.moving_border_toggled.emit(self._moving_border_visible)

    def _on_ref_lines_toggled(self):
        """Handle reference lines visibility toggle."""
        self._ref_lines_visible = self.ref_lines_btn.isChecked()
        self._update_ref_lines_btn_style(self._ref_lines_visible)
        self.ref_lines_toggled.emit(self._ref_lines_visible)

    def _update_borders_btn_style(self, visible: bool):
        """Update button appearance based on border visibility."""
        if visible:
            style = f"""
                QPushButton {{
                    background-color: {default_theme.button_primary};
                    border: none;
                    border-radius: 6px;
                    padding: 6px 12px;
                    font-size: 11px;
                    font-weight: bold;
                    color: white;
                }}
                QPushButton:hover {{
                    background-color: {default_theme.button_primary_hover};
                }}
            """
        else:
            style = f"""
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
            """
        self.borders_btn.setStyleSheet(style)
        self.borders_btn.setText("👁 Show Borders" if not visible else "👁 Hide Borders")

    def _update_lock_btn_style(self, locked: bool):
        """Update button appearance based on lock state."""
        if locked:
            style = f"""
                QPushButton {{
                    background-color: #DC2626;
                    border: none;
                    border-radius: 6px;
                    padding: 6px 12px;
                    font-size: 11px;
                    font-weight: bold;
                    color: white;
                }}
                QPushButton:hover {{
                    background-color: #B91C1C;
                }}
            """
        else:
            style = f"""
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
            """
        self.lock_btn.setStyleSheet(style)
        self.lock_btn.setText("🔒 Lock Document" if not locked else "🔓 Unlock Document")

    def _on_pdf_locked(self):
        """Handle PDF lock/unlock toggle."""
        self._pdf_locked = self.lock_btn.isChecked()
        self._update_lock_btn_style(self._pdf_locked)
        self.pdf_locked.emit(self._pdf_locked)

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
    def _on_drawing_mode_clicked(self, mode: str):
        """Handle drawing mode button clicks."""
        # Toggle mode: if already active, turn off; otherwise activate
        if self._current_drawing_mode == mode and self._drawing_mode_buttons[mode].isChecked():
            # Turn off all buttons
            for btn in self._drawing_mode_buttons.values():
                btn.blockSignals(True)
                btn.setChecked(False)
                btn.blockSignals(False)
                self._update_drawing_btn_style(btn, False)
            self._current_drawing_mode = None
            self.drawing_mode_changed.emit("")
        else:
            # Turn off all other buttons, turn on this one
            for m, btn in self._drawing_mode_buttons.items():
                is_active = (m == mode)
                btn.blockSignals(True)
                btn.setChecked(is_active)
                btn.blockSignals(False)
                self._update_drawing_btn_style(btn, is_active)
            self._current_drawing_mode = mode
            self.drawing_mode_changed.emit(mode)

    def _update_drawing_btn_style(self, btn: QPushButton, active: bool):
        """Update button style for active/inactive state."""
        if active:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {default_theme.button_primary};
                    border: none;
                    border-radius: 6px;
                    padding: 6px 12px;
                    font-size: 14px;
                    font-weight: bold;
                    color: white;
                }}
                QPushButton:hover {{
                    background-color: {default_theme.button_primary_hover};
                }}
            """)
        else:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {default_theme.row_bg_standard};
                    border: 1px solid {default_theme.border_light};
                    border-radius: 6px;
                    padding: 6px 12px;
                    font-size: 14px;
                    color: {default_theme.text_primary};
                }}
                QPushButton:hover {{
                    background-color: {default_theme.row_bg_hover};
                }}
            """)

    def _on_color_picker(self):
        """Open color picker dialog."""
        color = QColorDialog.getColor(
            self._drawing_color,
            self,
            "Select Drawing Color"
        )
        if color.isValid():
            self._drawing_color = color
            self._update_color_btn_style()
            self.drawing_color_changed.emit(color)

    def _update_color_btn_style(self):
        """Update color button to show current color."""
        color_hex = self._drawing_color.name()
        self.color_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {color_hex}, stop:1 {color_hex});
                border: 1px solid {default_theme.border_light};
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: bold;
                color: white;
            }}
            QPushButton:hover {{
                border: 2px solid {default_theme.button_primary};
            }}
        """)

    def _on_clear_shapes(self):
        """Handle clear shapes button click - emit signal to clear drawing."""
        self.drawing_mode_changed.emit("clear")
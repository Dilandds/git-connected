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


def _shape_icon(kind: str, color: QColor = None) -> QIcon:
    """Create crisp toolbar icons for drawing tools without external assets."""
    color = color or QColor(default_theme.text_primary)
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(color, 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    if kind == "arrow":
        painter.drawLine(8, 24, 24, 8)
        painter.drawLine(24, 8, 24, 17)
        painter.drawLine(24, 8, 15, 8)
    elif kind == "rectangle":
        painter.drawRoundedRect(7, 9, 18, 14, 2, 2)
    elif kind == "circle":
        painter.drawEllipse(8, 8, 16, 16)
    elif kind == "move":
        painter.drawLine(16, 6, 16, 26)
        painter.drawLine(6, 16, 26, 16)
        painter.drawPolygon(QPolygonF([QPointF(16, 4), QPointF(12, 9), QPointF(20, 9)]))
        painter.drawPolygon(QPolygonF([QPointF(16, 28), QPointF(12, 23), QPointF(20, 23)]))
        painter.drawPolygon(QPolygonF([QPointF(4, 16), QPointF(9, 12), QPointF(9, 20)]))
        painter.drawPolygon(QPolygonF([QPointF(28, 16), QPointF(23, 12), QPointF(23, 20)]))
    elif kind == "erase":
        painter.drawRoundedRect(9, 12, 15, 9, 2, 2)
        painter.drawLine(12, 10, 25, 23)
        painter.drawLine(7, 24, 26, 24)
    elif kind == "clear":
        painter.drawLine(11, 12, 21, 12)
        painter.drawRoundedRect(10, 14, 12, 12, 2, 2)
        painter.drawLine(13, 17, 13, 23)
        painter.drawLine(16, 17, 16, 23)
        painter.drawLine(19, 17, 19, 23)
    painter.end()
    return QIcon(pixmap)


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

    def _add_card_shadow(self, widget, blur_radius=26, y_offset=8, alpha=110):
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(blur_radius)
        shadow.setXOffset(0)
        shadow.setYOffset(y_offset)
        shadow.setColor(QColor(0, 0, 0, alpha))
        widget.setGraphicsEffect(shadow)

    def _style_section_card(self, card: QFrame):
        name = card.objectName()
        if not name:
            return
        card.setStyleSheet(f"QFrame#{name} {{ {sidebar_section_card_stylesheet(default_theme)} }}")
        card.setAttribute(Qt.WA_StyledBackground, True)
        self._add_card_shadow(card)

    def _create_tool_button(self, kind: str, tooltip: str, checkable: bool = True) -> QPushButton:
        btn = QPushButton()
        btn.setFixedSize(42, 36)
        btn.setIcon(_shape_icon(kind))
        btn.setIconSize(QSize(24, 24))
        btn.setCheckable(checkable)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip(tooltip)
        self._update_drawing_btn_style(btn, False)
        return btn

    def _init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setObjectName("sidebarScrollArea")
        scroll.setMinimumWidth(SIDEBAR_WIDTH)
        scroll.setStyleSheet(f"""
            QScrollArea#sidebarScrollArea {{
                background-color: {default_theme.background};
                border: none;
            }}
            QScrollArea#sidebarScrollArea > QWidget > QWidget {{
                background-color: {default_theme.background};
            }}
        """)
        scroll.viewport().setStyleSheet(f"background-color: {default_theme.background};")

        container = QWidget()
        container.setObjectName("sidebarContent")
        container.setStyleSheet(f"background-color: {default_theme.background};")
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignTop)
        layout.setContentsMargins(10, 14, 20, 18)
        layout.setSpacing(15)

        upload_card = QFrame()
        upload_card.setObjectName("uploadCard")
        self._style_section_card(upload_card)
        upload_card_layout = QVBoxLayout(upload_card)
        upload_card_layout.setContentsMargins(16, 18, 16, 18)
        upload_card_layout.setSpacing(10)

        # Title header
        self.title = QLabel(t("scale.title"))
        self.title.setFont(make_font(size=16, bold=True))
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setStyleSheet(f"background: transparent; border: none; color: {default_theme.text_title};")
        upload_card_layout.addWidget(self.title)

        # Upload button (same pattern as Technical Overview)
        self.upload_btn = QPushButton(t("scale.upload_btn"))
        self.upload_btn.setMinimumHeight(50)
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
        self._add_card_shadow(self.upload_btn, blur_radius=34, y_offset=9, alpha=210)
        self.upload_btn.clicked.connect(self.upload_requested.emit)
        upload_card_layout.addWidget(self.upload_btn)

        layout.addWidget(upload_card)

        layout.addWidget(self._separator())

        self.unit_label = _section_label(t("scale.unit"))
        layout.addWidget(self.unit_label)
        self.unit_combo = _styled_combo()
        self.unit_combo.addItems(["Centimeters (cm)", "Millimeters (mm)", "Inches (in)", "Meters (m)"])
        self.unit_combo.currentIndexChanged.connect(self._on_unit_changed)
        layout.addWidget(self.unit_combo)

        self.scale_ratio_label = _section_label(t("scale.scale_ratio"))
        layout.addWidget(self.scale_ratio_label)
        self.scale_combo = _styled_combo()
        self.scale_combo.addItems(["1:1", "1:2", "1:5", "1:10"])
        self.scale_combo.currentIndexChanged.connect(self._on_scale_changed)
        layout.addWidget(self.scale_combo)

        layout.addWidget(self._separator())

        # Ruler toggle — same family as Technical "Annotate"
        self.ruler_btn = QPushButton(t("scale.ruler_tool"))
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
        self.add_ref_btn = QPushButton(t("scale.add_reference"))
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
        self.reset_btn = QPushButton(t("scale.reset"))
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
        self.export_btn = QPushButton(t("scale.export_scaled"))
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
        self.draw_shapes_label = _section_label(t("scale.draw_shapes"))
        layout.addWidget(self.draw_shapes_label)
        
        shape_card = QFrame()
        shape_card.setObjectName("drawShapesCard")
        self._style_section_card(shape_card)
        shape_layout = QVBoxLayout(shape_card)
        shape_layout.setContentsMargins(12, 12, 12, 12)
        shape_layout.setSpacing(10)

        tools_layout = QHBoxLayout()
        tools_layout.setContentsMargins(0, 0, 0, 0)
        tools_layout.setSpacing(6)

        self.arrow_btn = self._create_tool_button("arrow", "Draw arrow")
        self.arrow_btn.clicked.connect(lambda: self._on_drawing_mode_clicked("arrow"))
        tools_layout.addWidget(self.arrow_btn)
        
        self.rectangle_btn = self._create_tool_button("rectangle", "Draw rectangle")
        self.rectangle_btn.clicked.connect(lambda: self._on_drawing_mode_clicked("rectangle"))
        tools_layout.addWidget(self.rectangle_btn)
        
        self.circle_btn = self._create_tool_button("circle", "Draw circle")
        self.circle_btn.clicked.connect(lambda: self._on_drawing_mode_clicked("circle"))
        tools_layout.addWidget(self.circle_btn)

        self.move_btn = self._create_tool_button("move", "Move drawings")
        self.move_btn.clicked.connect(lambda: self._on_drawing_mode_clicked("move"))
        tools_layout.addWidget(self.move_btn)

        self.erase_btn = self._create_tool_button("erase", "Erase one drawing")
        self.erase_btn.clicked.connect(lambda: self._on_drawing_mode_clicked("erase"))
        tools_layout.addWidget(self.erase_btn)
        
        self.clear_shapes_btn = self._create_tool_button("clear", "Clear all shapes", checkable=False)
        self.clear_shapes_btn.clicked.connect(self._on_clear_shapes)
        tools_layout.addWidget(self.clear_shapes_btn)
        
        tools_layout.addStretch()
        shape_layout.addLayout(tools_layout)
        
        # Color picker button
        self.color_btn = QPushButton("🎨 Color: ")
        self.color_btn.setFixedHeight(32)
        self.color_btn.setCursor(Qt.PointingHandCursor)
        self.color_btn.clicked.connect(self._on_color_picker)
        self._update_color_btn_style()
        shape_layout.addWidget(self.color_btn)
        layout.addWidget(shape_card)
        
        self._drawing_mode_buttons = {
            "arrow": self.arrow_btn,
            "rectangle": self.rectangle_btn,
            "circle": self.circle_btn,
            "move": self.move_btn,
            "erase": self.erase_btn,
        }
        self._current_drawing_mode: Optional[str] = None

        layout.addWidget(self._separator())

        self.how_to_use_label = _section_label(t("scale.how_to_use"))
        layout.addWidget(self.how_to_use_label)
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
        self._update_texts()
        on_language_changed(self._update_texts)

    def _separator(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {default_theme.separator}; border: none;")
        return sep

    def _update_texts(self):
        self.title.setText(t("scale.title"))
        self.upload_btn.setText(t("scale.upload_btn"))
        self.unit_label.setText(t("scale.unit"))
        self.scale_ratio_label.setText(t("scale.scale_ratio"))
        self.ruler_btn.setText(t("scale.ruler_tool"))
        self.add_ref_btn.setText(t("scale.add_reference"))
        self.reset_btn.setText(t("scale.reset"))
        self.export_btn.setText(t("scale.export_scaled"))
        self.draw_shapes_label.setText(t("scale.draw_shapes"))
        self.how_to_use_label.setText(t("scale.how_to_use"))

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
                    border: 1px solid {default_theme.button_primary_hover};
                    border-radius: 8px;
                    padding: 6px;
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
                    border-radius: 8px;
                    padding: 6px;
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
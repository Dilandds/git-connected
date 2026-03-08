"""
Secondary toolbar for ruler/measurement mode with orthographic view presets.
"""
import logging
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QFrame, QComboBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QEvent
from PyQt5.QtGui import QFont
from ui.styles import default_theme

logger = logging.getLogger(__name__)


class RulerViewButton(QPushButton):
    """Styled button for ruler view selection."""
    
    def __init__(self, text, tooltip="", parent=None):
        super().__init__(text, parent)
        self._is_active = False
        self.setToolTip(tooltip)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(26)
        self.setMinimumWidth(60)
        self._apply_default_style()
        self.installEventFilter(self)
    
    def _apply_default_style(self):
        """Apply default button style."""
        if self._is_active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {default_theme.button_primary};
                    color: {default_theme.text_white};
                    border: none;
                    border-radius: 6px;
                    padding: 4px 12px;
                    font-size: 11px;
                    font-weight: 500;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {default_theme.row_bg_standard};
                    color: {default_theme.text_primary};
                    border: 1px solid transparent;
                    border-radius: 6px;
                    padding: 4px 12px;
                    font-size: 11px;
                }}
            """)
    
    def _apply_hover_style(self):
        """Apply hover style."""
        if not self._is_active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {default_theme.row_bg_hover};
                    color: {default_theme.text_primary};
                    border: 1px solid {default_theme.border_light};
                    border-radius: 6px;
                    padding: 4px 12px;
                    font-size: 11px;
                }}
            """)
    
    def set_active(self, active):
        """Set the active state of the button."""
        self._is_active = active
        self._apply_default_style()
    
    def eventFilter(self, obj, event):
        """Handle hover events."""
        if obj == self:
            if event.type() == QEvent.Enter:
                self._apply_hover_style()
            elif event.type() == QEvent.Leave:
                self._apply_default_style()
        return super().eventFilter(obj, event)


class RulerToolbar(QWidget):
    """
    Secondary toolbar displayed when ruler/measurement mode is active.
    Provides orthographic view presets for accurate measurement.
    """
    
    # Signals for view selection
    view_front = pyqtSignal()
    view_left = pyqtSignal()
    view_right = pyqtSignal()
    view_top = pyqtSignal()
    view_bottom = pyqtSignal()
    view_rear = pyqtSignal()
    clear_measurements = pyqtSignal()
    exit_ruler = pyqtSignal()
    unit_changed = pyqtSignal(str)  # Emits unit key: "mm", "cm", "m", "inch", "ft"
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_view = "front"
        self.init_ui()
    
    def init_ui(self):
        """Initialize the ruler toolbar UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)
        
        # Container frame for styling
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {default_theme.row_bg_highlight};
                border-bottom: 1px solid {default_theme.border_highlight};
            }}
        """)
        
        # Mode indicator
        mode_label = QLabel("📐 Measure Mode")
        mode_label.setStyleSheet(f"""
            color: {default_theme.text_primary};
            font-size: 11px;
            font-weight: bold;
            background: transparent;
        """)
        layout.addWidget(mode_label)
        
        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Plain)
        separator.setStyleSheet(f"color: {default_theme.border_highlight};")
        separator.setFixedWidth(1)
        layout.addWidget(separator)
        
        # Instruction label
        instruction_label = QLabel("Click two points to measure")
        instruction_label.setStyleSheet(f"""
            color: {default_theme.text_secondary};
            font-size: 10px;
            background: transparent;
        """)
        layout.addWidget(instruction_label)
        
        # Spacer
        layout.addStretch()
        
        # View buttons
        view_label = QLabel("View:")
        view_label.setStyleSheet(f"""
            color: {default_theme.text_secondary};
            font-size: 10px;
            background: transparent;
        """)
        layout.addWidget(view_label)
        
        self.view_combo = QComboBox()
        self.view_combo.addItems(["Front", "Rear", "Left", "Right", "Top", "Bottom"])
        self.view_combo.setCurrentIndex(0)
        self.view_combo.setFixedHeight(26)
        self.view_combo.setMinimumWidth(90)
        self.view_combo.setCursor(Qt.PointingHandCursor)
        self.view_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {default_theme.row_bg_standard};
                color: {default_theme.text_primary};
                border: 1px solid {default_theme.border_light};
                border-radius: 6px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 500;
            }}
            QComboBox:hover {{
                background-color: {default_theme.row_bg_hover};
                border: 1px solid {default_theme.border_medium};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 18px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid {default_theme.text_secondary};
                margin-right: 6px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {default_theme.row_bg_standard};
                color: {default_theme.text_primary};
                border: 1px solid {default_theme.border_medium};
                border-radius: 4px;
                selection-background-color: {default_theme.button_primary};
                selection-color: {default_theme.text_white};
                padding: 2px;
                outline: none;
            }}
        """)
        self.view_combo.currentIndexChanged.connect(self._on_view_combo_changed)
        layout.addWidget(self.view_combo)
        
        # Separator before units
        sep_units = QFrame()
        sep_units.setFrameShape(QFrame.VLine)
        sep_units.setFrameShadow(QFrame.Plain)
        sep_units.setStyleSheet(f"color: {default_theme.border_highlight};")
        sep_units.setFixedWidth(1)
        layout.addWidget(sep_units)
        
        # Unit selector dropdown
        unit_label = QLabel("Unit:")
        unit_label.setStyleSheet(f"""
            color: {default_theme.text_secondary};
            font-size: 10px;
            background: transparent;
        """)
        layout.addWidget(unit_label)
        
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["MM", "CM", "M", "INCH", "FT"])
        self.unit_combo.setCurrentIndex(0)
        self._current_unit = "mm"
        self.unit_combo.setFixedHeight(26)
        self.unit_combo.setMinimumWidth(70)
        self.unit_combo.setCursor(Qt.PointingHandCursor)
        self.unit_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {default_theme.row_bg_standard};
                color: {default_theme.text_primary};
                border: 1px solid {default_theme.border_light};
                border-radius: 6px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 500;
            }}
            QComboBox:hover {{
                background-color: {default_theme.row_bg_hover};
                border: 1px solid {default_theme.border_medium};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 18px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid {default_theme.text_secondary};
                margin-right: 6px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {default_theme.row_bg_standard};
                color: {default_theme.text_primary};
                border: 1px solid {default_theme.border_medium};
                border-radius: 4px;
                selection-background-color: {default_theme.button_primary};
                selection-color: {default_theme.text_white};
                padding: 2px;
                outline: none;
            }}
        """)
        self.unit_combo.currentTextChanged.connect(self._on_unit_combo_changed)
        layout.addWidget(self.unit_combo)
        
        # Separator
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.VLine)
        separator2.setFrameShadow(QFrame.Plain)
        separator2.setStyleSheet(f"color: {default_theme.border_light};")
        separator2.setFixedWidth(1)
        layout.addWidget(separator2)
        
        # Clear button
        self.clear_btn = RulerViewButton("Clear")
        self.clear_btn.clicked.connect(self._on_clear_clicked)
        layout.addWidget(self.clear_btn)
        
        # Exit button
        self.exit_btn = QPushButton("✕ Exit")
        self.exit_btn.setCursor(Qt.PointingHandCursor)
        self.exit_btn.setFixedHeight(26)
        self.exit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {default_theme.button_default_bg};
                color: {default_theme.text_primary};
                border: 1px solid {default_theme.border_light};
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {default_theme.row_bg_hover};
                border: 1px solid {default_theme.border_medium};
            }}
        """)
        self.exit_btn.clicked.connect(self._on_exit_clicked)
        layout.addWidget(self.exit_btn)
        
        self.setFixedHeight(38)
    
    def _update_view_buttons(self, active_view):
        """Update view dropdown selection (kept for reset_to_front compatibility)."""
        view_order = ["front", "rear", "left", "right", "top", "bottom"]
        if active_view in view_order:
            idx = view_order.index(active_view)
            self.view_combo.blockSignals(True)
            self.view_combo.setCurrentIndex(idx)
            self.view_combo.blockSignals(False)
            self._current_view = active_view
    
    def _on_view_combo_changed(self, index):
        """Handle view dropdown change."""
        view_order = ["front", "rear", "left", "right", "top", "bottom"]
        view_id = view_order[index]
        self._current_view = view_id
        if view_id == "front":
            self.view_front.emit()
        elif view_id == "rear":
            self.view_rear.emit()
        elif view_id == "left":
            self.view_left.emit()
        elif view_id == "right":
            self.view_right.emit()
        elif view_id == "top":
            self.view_top.emit()
        elif view_id == "bottom":
            self.view_bottom.emit()
    
    def _on_clear_clicked(self):
        """Handle clear measurements button click."""
        self.clear_measurements.emit()
    
    def _on_exit_clicked(self):
        """Handle exit ruler mode button click."""
        self.exit_ruler.emit()
    
    def _on_unit_combo_changed(self, text):
        """Handle unit dropdown change."""
        unit_map = {"MM": "mm", "CM": "cm", "M": "m", "INCH": "inch", "FT": "ft"}
        unit_key = unit_map.get(text, "mm")
        self._current_unit = unit_key
        self.unit_changed.emit(unit_key)
    
    def reset_to_front(self):
        """Reset view selection to front (called when entering ruler mode)."""
        self._update_view_buttons("front")

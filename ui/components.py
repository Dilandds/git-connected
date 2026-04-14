"""
Reusable UI components for the ECTOFORM application.
"""
from PyQt5.QtWidgets import (
    QFrame, QLabel, QHBoxLayout, QVBoxLayout,
    QSpacerItem, QSizePolicy, QCheckBox, QWidget,
    QDialog, QPushButton, QGraphicsDropShadowEffect, QLineEdit, QStyleFactory,
)
from PyQt5.QtCore import Qt, QEvent, pyqtSignal
from PyQt5.QtGui import QFont, QPainter, QColor, QDoubleValidator
from ui.styles import default_theme
from i18n import t


def confirm_dialog(parent, title: str, message: str) -> bool:
    """Show a confirmation dialog with visible Yes/No buttons. Returns True for Yes, False for No."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setModal(True)
    dlg.setStyleSheet(f"QDialog {{ background-color: {default_theme.background}; }}")
    layout = QVBoxLayout(dlg)
    layout.setSpacing(16)
    layout.setContentsMargins(20, 20, 20, 20)
    msg_label = QLabel(message)
    msg_label.setWordWrap(True)
    msg_label.setStyleSheet(f"color: {default_theme.text_primary}; font-size: 13px; background: transparent;")
    layout.addWidget(msg_label)
    btn_layout = QHBoxLayout()
    btn_layout.addStretch()
    no_btn = QPushButton("No")
    yes_btn = QPushButton("Yes")
    for btn in (no_btn, yes_btn):
        btn.setCursor(Qt.PointingHandCursor)
        btn.setMinimumWidth(80)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {default_theme.button_default_bg};
                color: {default_theme.text_primary};
                border: 1px solid {default_theme.button_default_border};
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {default_theme.row_bg_hover};
            }}
        """)
    yes_btn.setStyleSheet(f"""
        QPushButton {{
            background-color: {default_theme.button_primary};
            color: {default_theme.text_white};
            border: none;
            border-radius: 6px;
            padding: 8px 20px;
            font-size: 13px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: {default_theme.button_primary_hover};
        }}
    """)
    btn_layout.addWidget(no_btn)
    btn_layout.addWidget(yes_btn)
    layout.addLayout(btn_layout)
    result = [False]

    def on_yes():
        result[0] = True
        dlg.accept()

    def on_no():
        result[0] = False
        dlg.reject()

    yes_btn.clicked.connect(on_yes)
    no_btn.clicked.connect(on_no)
    dlg.exec_()
    return result[0]


class DimensionRow(QFrame):
    """A reusable dimension row component with hover effect."""
    
    def __init__(self, label_text, value_text="--", parent=None):
        super().__init__(parent)
        self.setObjectName("dimensionRow")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(44)
        self.setStyleSheet(f"""
            QFrame#dimensionRow {{
                background-color: #ffffff;
                border-radius: 8px;
                border: none;
            }}
        """)
        
        row_layout = QHBoxLayout(self)
        row_layout.setContentsMargins(14, 8, 14, 8)
        row_layout.setSpacing(0)
        
        # Label
        self._label = QLabel(label_text)
        self._label.setObjectName("dimensionLabel")
        self._label.setStyleSheet("background-color: transparent; color: #000000;")
        label_font = QFont()
        label_font.setPointSize(11)
        label_font.setBold(True)
        self._label.setFont(label_font)
        self._label.setMinimumWidth(self._label.fontMetrics().horizontalAdvance(label_text) + 8)
        
        # Spacer
        spacer = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        
        # Value
        self.value_label = QLabel(value_text)
        self.value_label.setObjectName("dimensionValue")
        self.value_label.setStyleSheet("background-color: transparent; color: #000000;")
        value_font = QFont()
        value_font.setPointSize(13)
        value_font.setBold(True)
        self.value_label.setFont(value_font)
        self.value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.value_label.setMinimumWidth(self.value_label.fontMetrics().horizontalAdvance(value_text) + 8)
        
        row_layout.addWidget(self._label)
        row_layout.addItem(spacer)
        row_layout.addWidget(self.value_label)
        
        # Install event filter for hover effect
        self.installEventFilter(self)
    
    def eventFilter(self, obj, event):
        """Handle hover events."""
        if obj == self:
            if event.type() == QEvent.Enter:
                self.setStyleSheet(f"""
                    QFrame#dimensionRow {{
                        background-color: #f0f0f0;
                        border-radius: 8px;
                    }}
                """)
            elif event.type() == QEvent.Leave:
                self.setStyleSheet(f"""
                    QFrame#dimensionRow {{
                        background-color: #ffffff;
                        border-radius: 8px;
                    }}
                """)
        return super().eventFilter(obj, event)
    
    def set_value(self, text):
        """Update the value label text."""
        self.value_label.setText(text)
        self.value_label.setMinimumWidth(self.value_label.fontMetrics().horizontalAdvance(text) + 8)

    def set_label(self, text):
        """Update the label text."""
        self._label.setText(text)
        self._label.setMinimumWidth(self._label.fontMetrics().horizontalAdvance(text) + 8)


class SurfaceAreaRow(QFrame):
    """A reusable surface area row component with hover effect."""
    
    def __init__(self, label_text, value_text="--", row_type="standard", parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(44)
        
        if row_type == "total_area":
            self.setObjectName("surfaceRowTotalArea")
            _st = default_theme.surface_total_area_bg
            self.setAttribute(Qt.WA_StyledBackground, True)
            self.setStyleSheet(f"""
                QFrame#surfaceRowTotalArea {{
                    background-color: {_st};
                    border-radius: 8px;
                    border: none;
                }}
            """)
            _shadow = QGraphicsDropShadowEffect()
            _shadow.setBlurRadius(32)
            _shadow.setXOffset(0)
            _shadow.setYOffset(8)
            _shadow.setColor(QColor(0, 0, 0, 200))
            self.setGraphicsEffect(_shadow)
        elif row_type == "standard":
            self.setObjectName("surfaceRowStandard")
            self.setStyleSheet(f"""
                QFrame#surfaceRowStandard {{
                    background-color: #ffffff;
                    border-radius: 8px;
                    border: none;
                }}
            """)
        elif row_type == "highlight":
            self.setObjectName("surfaceRowHighlight")
            self.setStyleSheet(f"""
                QFrame#surfaceRowHighlight {{
                    background-color: #ffffff;
                    border-left: 4px solid {default_theme.border_highlight};
                    border-top: none;
                    border-right: none;
                    border-bottom: none;
                    border-radius: 8px;
                }}
            """)
        else:
            self.setObjectName("surfaceRowStandard")
            self.setStyleSheet(f"""
                QFrame#surfaceRowStandard {{
                    background-color: #ffffff;
                    border-radius: 8px;
                    border: none;
                }}
            """)
        
        row_layout = QHBoxLayout(self)
        row_layout.setContentsMargins(14, 8, 14, 8)
        row_layout.setSpacing(0)
        
        # Label
        self._label = QLabel(label_text)
        if row_type == "total_area":
            self._label.setObjectName("surfaceTotalLabel")
            self._label.setStyleSheet(
                f"background-color: transparent; color: {default_theme.text_white};"
            )
        else:
            self._label.setObjectName("surfaceLabel")
            self._label.setStyleSheet("background-color: transparent; color: #000000;")
        label_font = QFont()
        label_font.setPointSize(11)
        label_font.setBold(True)
        self._label.setFont(label_font)
        self._label.setMinimumWidth(self._label.fontMetrics().horizontalAdvance(label_text) + 8)
        
        # Spacer
        spacer = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        
        # Value
        self.value_label = QLabel(value_text)
        if row_type == "total_area":
            self.value_label.setObjectName("surfaceTotalValue")
            self.value_label.setStyleSheet(
                f"background-color: transparent; color: {default_theme.text_white};"
            )
        else:
            self.value_label.setObjectName("surfaceValue")
            self.value_label.setStyleSheet("background-color: transparent; color: #000000;")
        value_font = QFont()
        value_font.setPointSize(13)
        value_font.setBold(True)
        self.value_label.setFont(value_font)
        self.value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.value_label.setMinimumWidth(self.value_label.fontMetrics().horizontalAdvance(value_text) + 8)
        
        row_layout.addWidget(self._label)
        row_layout.addItem(spacer)
        row_layout.addWidget(self.value_label)
        
        # Install event filter for hover effect
        self.installEventFilter(self)
    
    def eventFilter(self, obj, event):
        """Handle hover events."""
        if obj == self:
            obj_name = self.objectName()
            if obj_name == "surfaceRowTotalArea":
                _bg = default_theme.surface_total_area_bg
                _hov = default_theme.surface_total_area_hover
                if event.type() == QEvent.Enter:
                    self.setStyleSheet(f"""
                        QFrame#surfaceRowTotalArea {{
                            background-color: {_hov};
                            border-radius: 8px;
                            border: none;
                        }}
                    """)
                elif event.type() == QEvent.Leave:
                    self.setStyleSheet(f"""
                        QFrame#surfaceRowTotalArea {{
                            background-color: {_bg};
                            border-radius: 8px;
                            border: none;
                        }}
                    """)
            elif obj_name == "surfaceRowStandard":
                if event.type() == QEvent.Enter:
                    self.setStyleSheet(f"""
                        QFrame#surfaceRowStandard {{
                            background-color: #f0f0f0;
                            border-radius: 8px;
                        }}
                    """)
                elif event.type() == QEvent.Leave:
                    self.setStyleSheet(f"""
                        QFrame#surfaceRowStandard {{
                            background-color: #ffffff;
                            border-radius: 8px;
                        }}
                    """)
            elif obj_name == "surfaceRowHighlight":
                if event.type() == QEvent.Enter:
                    self.setStyleSheet(f"""
                        QFrame#surfaceRowHighlight {{
                            background-color: #f0f0f0;
                            border-left: 4px solid {default_theme.border_highlight};
                            border-top: none;
                            border-right: none;
                            border-bottom: none;
                            border-radius: 8px;
                        }}
                    """)
                elif event.type() == QEvent.Leave:
                    self.setStyleSheet(f"""
                        QFrame#surfaceRowHighlight {{
                            background-color: #ffffff;
                            border-left: 4px solid {default_theme.border_highlight};
                            border-top: none;
                            border-right: none;
                            border-bottom: none;
                            border-radius: 8px;
                        }}
                    """)
        return super().eventFilter(obj, event)
    
    def set_value(self, text):
        """Update the value label text."""
        self.value_label.setText(text)
        self.value_label.setMinimumWidth(self.value_label.fontMetrics().horizontalAdvance(text) + 8)

    def set_label(self, text):
        """Update the label text."""
        self._label.setText(text)
        self._label.setMinimumWidth(self._label.fontMetrics().horizontalAdvance(text) + 8)


class WeightRow(QFrame):
    """A reusable weight row component with hover effect."""
    
    def __init__(self, label_text, value_text="--", row_type="standard", parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(44)
        
        _wp = default_theme.weight_panel_bg
        if row_type == "standard":
            self.setObjectName("weightRowStandard")
            self.setStyleSheet(f"""
                QFrame#weightRowStandard {{
                    background-color: {_wp};
                    border-radius: 8px;
                    border: none;
                }}
            """)
        elif row_type == "highlight":
            self.setObjectName("weightRowHighlight")
            self.setStyleSheet(f"""
                QFrame#weightRowHighlight {{
                    background-color: {_wp};
                    border: 1px solid {default_theme.border_highlight};
                    border-radius: 8px;
                }}
            """)
        else:
            self.setObjectName("weightRowStandard")
            self.setStyleSheet(f"""
                QFrame#weightRowStandard {{
                    background-color: {_wp};
                    border-radius: 8px;
                    border: none;
                }}
            """)
        
        row_layout = QHBoxLayout(self)
        row_layout.setContentsMargins(14, 8, 14, 8)
        row_layout.setSpacing(0)
        
        # Label
        self._label = QLabel(label_text)
        self._label.setObjectName("weightLabel")
        self._label.setStyleSheet(
            f"background-color: transparent; color: {default_theme.text_white};"
        )
        label_font = QFont()
        label_font.setPointSize(11)
        label_font.setBold(True)
        self._label.setFont(label_font)
        self._label.setMinimumWidth(self._label.fontMetrics().horizontalAdvance(label_text) + 8)
        
        # Spacer
        spacer = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        
        # Value
        self.value_label = QLabel(value_text)
        self.value_label.setObjectName("weightValue")
        self.value_label.setStyleSheet(
            f"background-color: transparent; color: {default_theme.text_primary};"
        )
        value_font = QFont()
        value_font.setPointSize(13)
        value_font.setBold(True)
        self.value_label.setFont(value_font)
        self.value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.value_label.setMinimumWidth(self.value_label.fontMetrics().horizontalAdvance(value_text) + 8)
        
        row_layout.addWidget(self._label)
        row_layout.addItem(spacer)
        row_layout.addWidget(self.value_label)
        
        # Install event filter for hover effect
        self.installEventFilter(self)
    
    def eventFilter(self, obj, event):
        """Handle hover events."""
        if obj == self:
            obj_name = self.objectName()
            _wp = default_theme.weight_panel_bg
            _wph = default_theme.weight_panel_hover
            if obj_name == "weightRowStandard":
                if event.type() == QEvent.Enter:
                    self.setStyleSheet(f"""
                        QFrame#weightRowStandard {{
                            background-color: {_wph};
                            border-radius: 8px;
                        }}
                    """)
                elif event.type() == QEvent.Leave:
                    self.setStyleSheet(f"""
                        QFrame#weightRowStandard {{
                            background-color: {_wp};
                            border-radius: 8px;
                        }}
                    """)
            elif obj_name == "weightRowHighlight":
                if event.type() == QEvent.Enter:
                    self.setStyleSheet(f"""
                        QFrame#weightRowHighlight {{
                            background-color: {_wph};
                            border: 1px solid {default_theme.border_highlight};
                            border-radius: 8px;
                        }}
                    """)
                elif event.type() == QEvent.Leave:
                    self.setStyleSheet(f"""
                        QFrame#weightRowHighlight {{
                            background-color: {_wp};
                            border: 1px solid {default_theme.border_highlight};
                            border-radius: 8px;
                        }}
                    """)
        return super().eventFilter(obj, event)
    
    def set_value(self, text):
        """Update the value label text."""
        self.value_label.setText(text)
        self.value_label.setMinimumWidth(self.value_label.fontMetrics().horizontalAdvance(text) + 8)

    def set_label(self, text):
        """Update the label text."""
        self._label.setText(text)
        self._label.setMinimumWidth(self._label.fontMetrics().horizontalAdvance(text) + 8)


class WeightDensityInputRow(QFrame):
    """Density row with editable g/cm³ field (matches WeightRow card styling)."""

    densityChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(44)

        _wp = default_theme.weight_panel_bg
        self.setObjectName("weightRowStandard")
        self.setStyleSheet(f"""
            QFrame#weightRowStandard {{
                background-color: {_wp};
                border-radius: 8px;
                border: none;
            }}
        """)

        row_layout = QHBoxLayout(self)
        row_layout.setContentsMargins(14, 8, 14, 8)
        row_layout.setSpacing(8)

        label = QLabel("Density")
        label.setObjectName("weightLabel")
        label.setStyleSheet(
            f"background-color: transparent; color: {default_theme.text_white};"
        )
        label_font = QFont()
        label_font.setPointSize(11)
        label_font.setBold(True)
        label.setFont(label_font)
        label.setMinimumWidth(label.fontMetrics().horizontalAdvance("Density") + 8)

        self.density_input = QLineEdit()
        self.density_input.setObjectName("densityInput")
        self.density_input.setPlaceholderText("")
        self.density_input.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.density_input.setMinimumWidth(72)
        self.density_input.setMinimumHeight(28)
        _df = QStyleFactory.create("Fusion")
        if _df is not None:
            self.density_input.setStyle(_df)
        self.density_input.setAttribute(Qt.WA_StyledBackground, True)
        _bd = default_theme.border_medium
        _wph = default_theme.weight_panel_hover
        self.density_input.setStyleSheet(f"""
            QLineEdit#densityInput {{
                background-color: {_wph};
                border: 1px solid {_bd};
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 13px;
                font-weight: bold;
                color: {default_theme.text_primary};
            }}
            QLineEdit#densityInput:hover {{
                border: 1px solid {default_theme.input_border_hover};
            }}
            QLineEdit#densityInput:focus {{
                border: 1px solid {default_theme.border_highlight};
            }}
        """)
        validator = QDoubleValidator(0.0, 999.0, 6)
        validator.setNotation(QDoubleValidator.StandardNotation)
        self.density_input.setValidator(validator)
        self.density_input.textChanged.connect(self.densityChanged.emit)

        unit_label = QLabel("g/cm³")
        unit_label.setStyleSheet(
            f"color: {default_theme.text_secondary}; font-size: 11px; "
            f"background: transparent; border: none;"
        )
        unit_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        row_layout.addWidget(label)
        row_layout.addWidget(self.density_input, 1)
        row_layout.addWidget(unit_label)

        self.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj == self:
            _wp = default_theme.weight_panel_bg
            _wph = default_theme.weight_panel_hover
            if self.objectName() == "weightRowStandard":
                if event.type() == QEvent.Enter:
                    self.setStyleSheet(f"""
                        QFrame#weightRowStandard {{
                            background-color: {_wph};
                            border-radius: 8px;
                        }}
                    """)
                elif event.type() == QEvent.Leave:
                    self.setStyleSheet(f"""
                        QFrame#weightRowStandard {{
                            background-color: {_wp};
                            border-radius: 8px;
                        }}
                    """)
        return super().eventFilter(obj, event)

    def set_density_silent(self, density: float):
        """Set numeric density without emitting densityChanged."""
        self.density_input.blockSignals(True)
        self.density_input.setText(f"{density:g}")
        self.density_input.blockSignals(False)

    def clear_density_silent(self):
        self.density_input.blockSignals(True)
        self.density_input.clear()
        self.density_input.blockSignals(False)


class InfoCard(QFrame):
    """Base card component for info sections."""
    
    def __init__(self, title, object_name, parent=None):
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        
        self.card_layout = QVBoxLayout(self)
        self.card_layout.setContentsMargins(16, 16, 16, 16)
        self.card_layout.setSpacing(10)
        
        # Card title
        title_label = QLabel(title)
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet(f"color: {default_theme.text_title}; margin-bottom: 4px;")
        self.card_layout.addWidget(title_label)
    
    def add_separator(self):
        """Add a subtle separator line."""
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet(f"background-color: {default_theme.separator}; max-height: 1px; margin: 6px 0;")
        self.card_layout.addWidget(separator)


class Separator(QFrame):
    """Horizontal separator component."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.HLine)
        self.setStyleSheet(f"background-color: {default_theme.separator}; max-height: 1px; margin: 6px 0;")


class ScaleResultRow(QFrame):
    """A reusable scale result row component with hover effect."""
    
    def __init__(self, label_text, value_text="--", row_type="standard", parent=None):
        super().__init__(parent)
        self.row_type = row_type
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(44)
        
        if row_type == "standard":
            self.setObjectName("scaleRowStandard")
            _wp = default_theme.weight_panel_bg
            self.setStyleSheet(f"""
                QFrame#scaleRowStandard {{
                    background-color: {_wp};
                    border: 1px solid transparent;
                    border-radius: 8px;
                }}
            """)
        elif row_type == "highlight":
            self.setObjectName("scaleRowHighlight")
            self.setStyleSheet(f"""
                QFrame#scaleRowHighlight {{
                    background-color: {default_theme.row_bg_highlight};
                    border: 1px solid {default_theme.border_highlight};
                    border-radius: 8px;
                }}
            """)
        elif row_type == "comparison":
            self.setObjectName("scaleRowComparison")
            self.setStyleSheet(f"""
                QFrame#scaleRowComparison {{
                    background-color: {default_theme.row_bg_standard};
                    border: none;
                    border-left: 4px solid #FB923C;
                    border-radius: 8px;
                }}
            """)
        elif row_type == "volume":
            self.setObjectName("scaleRowVolume")
            _wp = default_theme.weight_panel_bg
            self.setStyleSheet(f"""
                QFrame#scaleRowVolume {{
                    background-color: {_wp};
                    border: 1px solid {default_theme.border_medium};
                    border-radius: 8px;
                }}
            """)
        else:
            self.setObjectName("scaleRowStandard")
            self.setStyleSheet(f"""
                QFrame#scaleRowStandard {{
                    background-color: {default_theme.row_bg_standard};
                    border: 1px solid transparent;
                    border-radius: 8px;
                }}
            """)
        
        _label_fg = (
            default_theme.text_white
            if row_type in ("standard", "volume")
            else default_theme.text_primary
        )
        
        row_layout = QHBoxLayout(self)
        row_layout.setContentsMargins(14, 8, 14, 8)
        row_layout.setSpacing(0)
        
        # Label
        self._label = QLabel(label_text)
        self._label.setObjectName("scaleLabel")
        self._label.setStyleSheet(
            f"background-color: transparent; color: {_label_fg};"
        )
        label_font = QFont()
        label_font.setPointSize(11)
        label_font.setBold(True)
        self._label.setFont(label_font)
        self._label.setMinimumWidth(self._label.fontMetrics().horizontalAdvance(label_text) + 8)
        
        # Spacer
        spacer = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        
        # Value
        self.value_label = QLabel(value_text)
        self.value_label.setObjectName("scaleValue")
        self.value_label.setStyleSheet(
            f"background-color: transparent; color: {_label_fg};"
        )
        value_font = QFont()
        value_font.setPointSize(13)
        value_font.setBold(True)
        self.value_label.setFont(value_font)
        self.value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.value_label.setMinimumWidth(self.value_label.fontMetrics().horizontalAdvance(value_text) + 8)
        
        row_layout.addWidget(self._label)
        row_layout.addItem(spacer)
        row_layout.addWidget(self.value_label)
        
        # Install event filter for hover effect
        self.installEventFilter(self)
    
    def eventFilter(self, obj, event):
        """Handle hover events."""
        if obj == self:
            obj_name = self.objectName()
            if obj_name == "scaleRowStandard":
                _wp = default_theme.weight_panel_bg
                _wph = default_theme.weight_panel_hover
                if event.type() == QEvent.Enter:
                    self.setStyleSheet(f"""
                        QFrame#scaleRowStandard {{
                            background-color: {_wph};
                            border: 1px solid transparent;
                            border-radius: 8px;
                        }}
                    """)
                elif event.type() == QEvent.Leave:
                    self.setStyleSheet(f"""
                        QFrame#scaleRowStandard {{
                            background-color: {_wp};
                            border: 1px solid transparent;
                            border-radius: 8px;
                        }}
                    """)
            elif obj_name == "scaleRowVolume":
                _wp = default_theme.weight_panel_bg
                _wph = default_theme.weight_panel_hover
                if event.type() == QEvent.Enter:
                    self.setStyleSheet(f"""
                        QFrame#scaleRowVolume {{
                            background-color: {_wph};
                            border: 1px solid {default_theme.border_medium};
                            border-radius: 8px;
                        }}
                    """)
                elif event.type() == QEvent.Leave:
                    self.setStyleSheet(f"""
                        QFrame#scaleRowVolume {{
                            background-color: {_wp};
                            border: 1px solid {default_theme.border_medium};
                            border-radius: 8px;
                        }}
                    """)
            elif obj_name == "scaleRowHighlight":
                if event.type() == QEvent.Enter:
                    self.setStyleSheet(f"""
                        QFrame#scaleRowHighlight {{
                            background-color: {default_theme.row_bg_highlight_hover};
                            border: 1px solid {default_theme.border_highlight};
                            border-radius: 8px;
                        }}
                    """)
                elif event.type() == QEvent.Leave:
                    self.setStyleSheet(f"""
                        QFrame#scaleRowHighlight {{
                            background-color: {default_theme.row_bg_highlight};
                            border: 1px solid {default_theme.border_highlight};
                            border-radius: 8px;
                        }}
                    """)
            elif obj_name == "scaleRowComparison":
                if event.type() == QEvent.Enter:
                    self.setStyleSheet(f"""
                        QFrame#scaleRowComparison {{
                            background-color: {default_theme.row_bg_hover};
                            border: none;
                            border-left: 4px solid #FB923C;
                            border-radius: 8px;
                        }}
                    """)
                elif event.type() == QEvent.Leave:
                    self.setStyleSheet(f"""
                        QFrame#scaleRowComparison {{
                            background-color: {default_theme.row_bg_standard};
                            border: none;
                            border-left: 4px solid #FB923C;
                            border-radius: 8px;
                        }}
                    """)
        return super().eventFilter(obj, event)
    
    def set_value(self, text):
        """Update the value label text."""
        self.value_label.setText(text)
        self.value_label.setMinimumWidth(self.value_label.fontMetrics().horizontalAdvance(text) + 8)

    def set_label(self, text):
        """Update the label text."""
        self._label.setText(text)
        self._label.setMinimumWidth(self._label.fontMetrics().horizontalAdvance(text) + 8)


class ReportCheckbox(QFrame):
    """A styled checkbox row for PDF report section selection."""
    
    def __init__(self, label_text, checked=False, enabled=True, always_checked=False, parent=None):
        super().__init__(parent)
        self.always_checked = always_checked
        self.setObjectName("reportCheckboxRow")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(40)
        
        self._enabled = enabled
        self._update_style()
        
        row_layout = QHBoxLayout(self)
        row_layout.setContentsMargins(12, 6, 12, 6)
        row_layout.setSpacing(10)
        
        # Custom checkbox indicator with checkmark
        class CheckboxIndicator(QWidget):
            def __init__(self, parent_checkbox, parent=None):
                super().__init__(parent)
                self.parent_checkbox = parent_checkbox
                self.setFixedSize(14, 14)
                self._checked = False
                self._disabled = False
            
            def set_checked(self, checked):
                self._checked = checked
                self.update()
            
            def set_disabled_state(self, disabled):
                self._disabled = disabled
                self.update()
            
            def mousePressEvent(self, event):
                if not self._disabled and event.button() == Qt.LeftButton:
                    self.parent_checkbox.toggle()
            
            def paintEvent(self, event):
                painter = QPainter(self)
                painter.setRenderHint(QPainter.Antialiasing)
                
                rect = self.rect()
                
                # Draw border and background
                if self._disabled:
                    bg_color = QColor(default_theme.button_default_bg)
                    border_color = QColor(default_theme.border_light)
                elif self._checked:
                    bg_color = QColor(default_theme.button_primary)
                    border_color = QColor(default_theme.button_primary)
                else:
                    bg_color = QColor(default_theme.input_bg)
                    border_color = QColor(default_theme.input_border)
                
                # Draw rounded rectangle
                painter.setBrush(bg_color)
                painter.setPen(border_color)
                painter.drawRoundedRect(rect.adjusted(0, 0, -1, -1), 3, 3)
                
                # Draw checkmark if checked
                if self._checked:
                    from PyQt5.QtGui import QPen
                    pen = QPen(QColor('white'), 1.5)
                    pen.setCapStyle(Qt.RoundCap)
                    pen.setJoinStyle(Qt.RoundJoin)
                    painter.setPen(pen)
                    # Draw checkmark lines (smaller checkmark)
                    painter.drawLine(3, 7, 6, 10)
                    painter.drawLine(6, 10, 11, 4)
        
        # Use invisible QCheckBox for state management
        self.checkbox = QCheckBox()
        self.checkbox.setChecked(checked or always_checked)
        self.checkbox.setEnabled(enabled and not always_checked)
        self.checkbox.setVisible(False)  # Hide the actual checkbox
        
        # Create custom checkbox indicator
        self.checkbox_indicator = CheckboxIndicator(self.checkbox, self)
        self.checkbox_indicator.set_checked(checked or always_checked)
        self.checkbox_indicator.set_disabled_state(not enabled or always_checked)
        
        # Connect checkbox state changes to update indicator
        self.checkbox.stateChanged.connect(lambda state: self.checkbox_indicator.set_checked(state == Qt.Checked))
        
        # Label
        self.label = QLabel(label_text)
        self.label.setObjectName("reportCheckboxLabel")
        label_color = default_theme.text_secondary if not enabled else default_theme.text_primary
        self.label.setStyleSheet(f"background-color: transparent; color: {label_color};")
        label_font = QFont()
        label_font.setPointSize(11)
        self.label.setFont(label_font)
        
        # Status indicator for disabled items
        self.status_label = QLabel()
        self.status_label.setObjectName("reportCheckboxStatus")
        self.status_label.setStyleSheet(f"background-color: transparent; color: {default_theme.text_subtext}; font-size: 10px;")
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        row_layout.addWidget(self.checkbox_indicator)
        row_layout.addWidget(self.label)
        row_layout.addStretch()
        row_layout.addWidget(self.status_label)
        
        # Install event filter for hover effect
        self.installEventFilter(self)
    
    def _update_style(self):
        """Update frame style based on enabled state."""
        if self._enabled:
            self.setStyleSheet(f"""
                QFrame#reportCheckboxRow {{
                    background-color: {default_theme.row_bg_standard};
                    border-radius: 6px;
                    border: none;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QFrame#reportCheckboxRow {{
                    background-color: {default_theme.button_default_bg};
                    border-radius: 6px;
                    border: none;
                }}
            """)
    
    def eventFilter(self, obj, event):
        """Handle hover events."""
        if obj == self and self._enabled:
            if event.type() == QEvent.Enter:
                self.setStyleSheet(f"""
                    QFrame#reportCheckboxRow {{
                        background-color: {default_theme.row_bg_hover};
                        border-radius: 6px;
                    }}
                """)
            elif event.type() == QEvent.Leave:
                self._update_style()
        return super().eventFilter(obj, event)
    
    def is_checked(self):
        """Return whether the checkbox is checked."""
        return self.checkbox.isChecked()
    
    def set_checked(self, checked):
        """Set checkbox state."""
        if not self.always_checked:
            self.checkbox.setChecked(checked)
            self.checkbox_indicator.set_checked(checked)
    
    def set_enabled(self, enabled):
        """Enable or disable the checkbox."""
        if self.always_checked:
            return
        self._enabled = enabled
        self.checkbox.setEnabled(enabled)
        self.checkbox_indicator.set_disabled_state(not enabled)
        label_color = default_theme.text_secondary if not enabled else default_theme.text_primary
        self.label.setStyleSheet(f"background-color: transparent; color: {label_color};")
        self._update_style()
    
    def set_status(self, text):
        """Set status text for the checkbox row."""
        self.status_label.setText(text)

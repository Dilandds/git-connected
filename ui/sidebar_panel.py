"""
Sidebar panel widget for the ECTOFORM application.
"""
import logging
import os
from datetime import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QFrame, QComboBox, QSizePolicy, QGraphicsDropShadowEffect,
    QLineEdit, QFileDialog, QMessageBox, QApplication
)
from PyQt5.QtCore import Qt, QEvent, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QDoubleValidator
from ui.components import DimensionRow, SurfaceAreaRow, WeightRow, Separator, ScaleResultRow, ReportCheckbox
from ui.styles import get_button_style, default_theme

logger = logging.getLogger(__name__)


class SidebarPanel(QWidget):
    """Left sidebar panel with upload controls and information sections."""
    
    # Signal emitted when export is requested (file_path, scale_factor)
    export_scaled_stl = pyqtSignal(str, float)
    
    # Material density data (g/cm³)
    MATERIALS = [
        ("24 carat gold (999)", 19.32),
        ("22 carat gold (916)", 17.7),
        ("18K yellow gold 3N", 15.5),
        ("18K rose gold", 15.0),
        ("18K white gold (Pd)", 15.0),
        ("18K white gold (Ag)", 14.7),
        ("14K yellow gold N2", 13.58),
        ("14K rose gold", 13.2),
        ("14K white gold", 13.0),
        ("10K gold", 11.6),
        ("9K gold", 10.8),
        ("Pure platinum (999)", 21.45),
        ("Platinum 950", 20.64),
        ("Platinum 900", 20.0),
        ("Pure palladium (999)", 12.02),
        ("Palladium 950", 11.5),
        ("Pure silver (999)", 10.49),
        ("Sterling Silver 925", 10.36),
        ("Copper Cu", 8.96),
        ("Brass UZ36", 8.5),
        ("Bronze", 8.8),
        ("316L Stainless Steel", 8.0),
        ("Grade 2 Titanium", 4.51),
        ("Aluminium", 2.7),
        ("Standard Resin", 1.2),
        ("Diamond", 3.52),
        ("Sapphire / Ruby", 4.0),
        ("Emerald", 2.75),
        ("Quartz", 2.65),
    ]
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_volume_mm3 = 0.0
        self.current_weight_grams = 0.0
        self.current_dimensions = {'width': 0.0, 'height': 0.0, 'depth': 0.0}
        self.calculated_scale_factor = 1.0
        self.current_surface_area_cm2 = 0.0
        self.current_stl_filename = ""
        self.has_stl_loaded = False
        self.has_scaled_data = False
        self.init_ui()
    
    def _add_card_shadow(self, card):
        """Add a subtle shadow effect to a card."""
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(12)
        shadow.setXOffset(0)
        shadow.setYOffset(2)
        shadow.setColor(QColor(0, 0, 0, 30))  # Semi-transparent black
        card.setGraphicsEffect(shadow)
    
    def init_ui(self):
        """Initialize the sidebar UI."""
        # Create scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setObjectName("sidebarScrollArea")
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setMinimumWidth(350)
        
        # Style scroll area
        scroll_area.setStyleSheet(f"""
            QScrollArea#sidebarScrollArea {{
                background-color: {default_theme.background};
                border: none;
            }}
            QScrollArea#sidebarScrollArea > QWidget > QWidget {{
                background-color: {default_theme.background};
            }}
        """)
        scroll_area.viewport().setStyleSheet(f"background-color: {default_theme.background};")
        
        # Create content widget
        content_widget = QWidget()
        content_widget.setObjectName("sidebarContent")
        content_widget.setStyleSheet(f"background-color: {default_theme.background};")
        content_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        
        layout = QVBoxLayout(content_widget)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(15)
        layout.setContentsMargins(10, 10, 20, 10)
        
        # Title label
        title_label = QLabel("ECTOFORM")
        title_label.setObjectName("titleLabel")
        title_font = QFont("Inter", 16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # Upload button
        self.upload_btn = QPushButton("Upload 3D File")
        self.upload_btn.setMinimumHeight(50)
        self.upload_btn.setObjectName("uploadBtn")
        self.upload_btn.setStyleSheet(get_button_style("uploadBtn"))
        self.upload_btn.setToolTip("Upload STL, STEP, 3DM, OBJ, or IGES file for 3D visualization")
        layout.addWidget(self.upload_btn)
        
        # Info label
        info_label = QLabel(
            "Click the button above\nto load a 3D file (STL, STEP, 3DM, OBJ, IGES)\nfor 3D visualization."
        )
        info_label.setObjectName("infoLabel")
        info_label.setAlignment(Qt.AlignCenter)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Create sections
        self.dimensions_group = self.create_dimensions_section()
        layout.addWidget(self.dimensions_group)
        
        self.surface_area_group = self.create_surface_area_section()
        layout.addWidget(self.surface_area_group)
        
        self.weight_group = self.create_weight_section()
        layout.addWidget(self.weight_group)
        
        # Create Adjust to Target Weight section
        self.adjust_weight_group = self.create_adjust_weight_section()
        layout.addWidget(self.adjust_weight_group)
        
        # Create PDF Report section
        self.pdf_report_group = self.create_pdf_report_section()
        layout.addWidget(self.pdf_report_group)
        
        # Create Export with Annotations section
        self.export_annotations_group = self.create_export_annotations_section()
        layout.addWidget(self.export_annotations_group)
        
        # Add stretch
        layout.addStretch()
        
        # Set content widget to scroll area
        scroll_area.setWidget(content_widget)
        
        # Store scroll area as main widget
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll_area)
    
    def create_dimensions_section(self):
        """Create the dimensions display section."""
        card = QFrame()
        card.setObjectName("dimensionsCard")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(10)
        
        # Card title
        title_label = QLabel("Dimensions")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet(f"color: {default_theme.text_title}; margin-bottom: 4px;")
        card_layout.addWidget(title_label)
        
        # Dimension rows using components
        self.width_row = DimensionRow("Length (X)", "--", self)
        self.height_row = DimensionRow("Width (Y)", "--", self)
        self.depth_row = DimensionRow("Height (Z)", "--", self)
        
        card_layout.addWidget(self.width_row)
        card_layout.addWidget(self.height_row)
        card_layout.addWidget(self.depth_row)
        
        # Separator
        separator = Separator(self)
        card_layout.addWidget(separator)
        
        # Volume row
        self.volume_row = DimensionRow("Volume", "--", self)
        card_layout.addWidget(self.volume_row)
        
        # Add shadow effect
        self._add_card_shadow(card)
        
        return card
    
    def create_surface_area_section(self):
        """Create the surface area section."""
        card = QFrame()
        card.setObjectName("surfaceAreaCard")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(10)
        
        # Header row with title and icon
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)
        
        title_label = QLabel("Total Surface Area")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet(f"color: {default_theme.text_title}; margin-bottom: 4px;")
        
        icon_label = QLabel("⬇")
        icon_label.setStyleSheet(f"color: {default_theme.icon_blue}; font-size: 16px;")
        icon_label.setAlignment(Qt.AlignCenter)
        
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(icon_label)
        card_layout.addLayout(header_layout)
        
        # Surface area rows using components
        self.surface_total_row = SurfaceAreaRow("Total area", "--", "standard", self)
        self.surface_cm_row = SurfaceAreaRow("Area (cm²)", "--", "highlight", self)
        
        card_layout.addWidget(self.surface_total_row)
        card_layout.addWidget(self.surface_cm_row)
        
        # Information footer
        footer_frame = QFrame()
        footer_frame.setObjectName("surfaceFooter")
        footer_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        footer_frame.setMinimumHeight(40)
        
        footer_layout = QHBoxLayout(footer_frame)
        footer_layout.setContentsMargins(10, 8, 10, 8)
        footer_layout.setSpacing(8)
        
        info_icon = QLabel("ℹ️")
        info_icon.setStyleSheet(f"color: {default_theme.icon_info_gray}; font-size: 12px;")
        info_icon.setFixedWidth(20)
        info_icon.setAlignment(Qt.AlignTop)
        
        disclaimer = QLabel("Calculated surface area: Sum of the areas of all triangles in the 3D mesh. Useful for estimating galvanizing or surface treatment costs.")
        disclaimer_font = QFont()
        disclaimer_font.setPointSize(9)
        disclaimer.setFont(disclaimer_font)
        disclaimer.setStyleSheet(f"color: {default_theme.icon_info_gray};")
        disclaimer.setWordWrap(True)
        
        footer_layout.addWidget(info_icon)
        footer_layout.addWidget(disclaimer)
        footer_layout.addStretch()
        
        card_layout.addWidget(footer_frame)
        
        # Add shadow effect
        self._add_card_shadow(card)
        
        return card
    
    def create_weight_section(self):
        """Create the estimated weight calculator section."""
        card = QFrame()
        card.setObjectName("weightCard")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(10)
        
        # Header row with title and icon
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)
        
        title_label = QLabel("Estimated Weight")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet(f"color: {default_theme.text_title}; margin-bottom: 4px;")
        
        icon_label = QLabel("⚖")
        icon_label.setStyleSheet(f"color: {default_theme.icon_blue}; font-size: 16px;")
        icon_label.setAlignment(Qt.AlignCenter)
        
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(icon_label)
        card_layout.addLayout(header_layout)
        
        # Material selector dropdown
        self.material_combo = QComboBox()
        self.material_combo.setObjectName("materialCombo")
        self.material_combo.setMinimumHeight(40)
        for material_name, density in self.MATERIALS:
            self.material_combo.addItem(f"{material_name} ({density} g/cm³)", density)
        self.material_combo.currentIndexChanged.connect(self.on_material_changed)
        card_layout.addWidget(self.material_combo)
        
        # Weight rows using components
        self.weight_volume_row = WeightRow("Volume", "--", "standard", self)
        self.weight_density_row = WeightRow("Density", "--", "standard", self)
        self.weight_result_row = WeightRow("Estimated weight", "--", "highlight", self)
        
        card_layout.addWidget(self.weight_volume_row)
        card_layout.addWidget(self.weight_density_row)
        card_layout.addWidget(self.weight_result_row)
        
        # Information footer
        footer_frame = QFrame()
        footer_frame.setObjectName("weightFooter")
        footer_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        footer_frame.setMinimumHeight(40)
        
        footer_layout = QHBoxLayout(footer_frame)
        footer_layout.setContentsMargins(10, 8, 10, 8)
        footer_layout.setSpacing(8)
        
        info_icon = QLabel("ℹ️")
        info_icon.setStyleSheet(f"color: {default_theme.icon_warning}; font-size: 12px;")
        info_icon.setFixedWidth(20)
        info_icon.setAlignment(Qt.AlignTop)
        
        disclaimer = QLabel("Actual Volume Calculated: Weight is estimated by multiplying volume (mm³ → cm³) by material density. Results may vary based on mesh accuracy and material purity.")
        disclaimer_font = QFont()
        disclaimer_font.setPointSize(9)
        disclaimer.setFont(disclaimer_font)
        disclaimer.setStyleSheet(f"color: {default_theme.icon_warning};")
        disclaimer.setWordWrap(True)
        
        footer_layout.addWidget(info_icon)
        footer_layout.addWidget(disclaimer)
        
        card_layout.addWidget(footer_frame)
        
        # Add shadow effect
        self._add_card_shadow(card)
        
        return card
    
    def create_adjust_weight_section(self):
        """Create the adjust to target weight section."""
        card = QFrame()
        card.setObjectName("adjustWeightCard")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(10)
        
        # Header row with title and icon
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)
        
        title_label = QLabel("Adjust to Target Weight")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet(f"color: {default_theme.text_title}; margin-bottom: 4px;")
        
        icon_label = QLabel("⚙")
        icon_label.setStyleSheet(f"color: {default_theme.icon_blue}; font-size: 16px;")
        icon_label.setAlignment(Qt.AlignCenter)
        
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(icon_label)
        card_layout.addLayout(header_layout)
        
        # Target weight input
        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)
        
        self.target_weight_input = QLineEdit()
        self.target_weight_input.setObjectName("targetWeightInput")
        self.target_weight_input.setPlaceholderText("Enter target weight")
        self.target_weight_input.setMinimumHeight(40)
        
        # Set validator for numeric input
        validator = QDoubleValidator(0.0, 999999.0, 4)
        validator.setNotation(QDoubleValidator.StandardNotation)
        self.target_weight_input.setValidator(validator)
        self.target_weight_input.returnPressed.connect(self.calculate_scale)
        
        unit_label = QLabel("g")
        unit_label.setStyleSheet(f"color: {default_theme.text_secondary}; font-weight: bold;")
        unit_label.setFixedWidth(20)
        
        input_layout.addWidget(self.target_weight_input)
        input_layout.addWidget(unit_label)
        card_layout.addLayout(input_layout)
        
        # Calculate button
        self.calculate_scale_btn = QPushButton("Calculate Scale")
        self.calculate_scale_btn.setObjectName("calculateScaleBtn")
        self.calculate_scale_btn.setMinimumHeight(40)
        self.calculate_scale_btn.setEnabled(False)
        self.calculate_scale_btn.setStyleSheet(f"""
            QPushButton#calculateScaleBtn {{
                background-color: {default_theme.button_primary};
                color: {default_theme.text_white};
                border: none;
                border-radius: 8px;
                padding: 10px 16px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton#calculateScaleBtn:hover {{
                background-color: {default_theme.button_primary_hover};
            }}
            QPushButton#calculateScaleBtn:pressed {{
                background-color: {default_theme.button_primary_pressed};
            }}
            QPushButton#calculateScaleBtn:disabled {{
                background-color: {default_theme.button_default_bg};
                color: {default_theme.text_primary};
            }}
        """)
        self.calculate_scale_btn.clicked.connect(self.calculate_scale)
        card_layout.addWidget(self.calculate_scale_btn)
        
        # Separator
        separator = Separator(self)
        card_layout.addWidget(separator)
        
        # Results section title
        results_label = QLabel("Scaled Results")
        results_font = QFont()
        results_font.setPointSize(11)
        results_font.setBold(True)
        results_label.setFont(results_font)
        results_label.setStyleSheet(f"color: {default_theme.text_secondary}; margin-top: 4px;")
        card_layout.addWidget(results_label)
        
        # Scale factor row
        self.scale_factor_row = ScaleResultRow("Scale factor", "--", "highlight", self)
        card_layout.addWidget(self.scale_factor_row)
        
        # New dimensions rows
        self.new_x_row = ScaleResultRow("New X (Length)", "--", "standard", self)
        self.new_y_row = ScaleResultRow("New Y (Width)", "--", "standard", self)
        self.new_z_row = ScaleResultRow("New Z (Height)", "--", "standard", self)
        card_layout.addWidget(self.new_x_row)
        card_layout.addWidget(self.new_y_row)
        card_layout.addWidget(self.new_z_row)
        
        # New volume row (with subtle border to differentiate from dimensions)
        self.new_volume_row = ScaleResultRow("New Volume", "--", "volume", self)
        card_layout.addWidget(self.new_volume_row)
        
        # Weight comparison separator
        separator2 = Separator(self)
        card_layout.addWidget(separator2)
        
        # Weight comparison title
        comparison_label = QLabel("Weight Comparison")
        comparison_label.setFont(results_font)
        comparison_label.setStyleSheet(f"color: {default_theme.text_secondary}; margin-top: 4px;")
        card_layout.addWidget(comparison_label)
        
        # Weight comparison rows
        self.original_weight_row = ScaleResultRow("Original weight", "--", "comparison", self)
        self.target_weight_row = ScaleResultRow("Target weight", "--", "highlight", self)
        card_layout.addWidget(self.original_weight_row)
        card_layout.addWidget(self.target_weight_row)
        
        # Export button
        self.export_scaled_btn = QPushButton("Export Scaled STL")
        self.export_scaled_btn.setObjectName("exportScaledBtn")
        self.export_scaled_btn.setMinimumHeight(44)
        self.export_scaled_btn.setEnabled(False)
        self.export_scaled_btn.setStyleSheet(f"""
            QPushButton#exportScaledBtn {{
                background-color: #10B981;
                color: {default_theme.text_white};
                border: none;
                border-radius: 8px;
                padding: 10px 16px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton#exportScaledBtn:hover {{
                background-color: #059669;
            }}
            QPushButton#exportScaledBtn:pressed {{
                background-color: #047857;
            }}
            QPushButton#exportScaledBtn:disabled {{
                background-color: {default_theme.button_default_bg};
                color: {default_theme.text_primary};
            }}
        """)
        self.export_scaled_btn.clicked.connect(self.export_scaled_stl_file)
        card_layout.addWidget(self.export_scaled_btn)
        
        # Add shadow effect
        self._add_card_shadow(card)
        
        return card
    
    def create_pdf_report_section(self):
        """Create the 3D PDF export section."""
        card = QFrame()
        card.setObjectName("pdfReportCard")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(10)
        
        # Header row with title and icon
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)
        
        title_label = QLabel("Export 3D PDF")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet(f"color: {default_theme.text_title}; margin-bottom: 4px;")
        
        icon_label = QLabel("📐")
        icon_label.setStyleSheet(f"color: {default_theme.icon_blue}; font-size: 16px;")
        icon_label.setAlignment(Qt.AlignCenter)
        
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(icon_label)
        card_layout.addLayout(header_layout)
        
        # Description
        desc_label = QLabel("Export interactive 3D PDF for Adobe Acrobat Reader.\nRotate, pan, and zoom the model inside the PDF.")
        desc_font = QFont()
        desc_font.setPointSize(11)
        desc_label.setFont(desc_font)
        desc_label.setStyleSheet(f"color: {default_theme.text_secondary};")
        desc_label.setWordWrap(True)
        card_layout.addWidget(desc_label)
        
        # Export button
        self.export_pdf_btn = QPushButton("Export 3D PDF")
        self.export_pdf_btn.setObjectName("exportPdfBtn")
        self.export_pdf_btn.setMinimumHeight(44)
        self.export_pdf_btn.setEnabled(False)
        self.export_pdf_btn.setStyleSheet(f"""
            QPushButton#exportPdfBtn {{
                background-color: {default_theme.button_primary};
                color: {default_theme.text_white};
                border: none;
                border-radius: 8px;
                padding: 10px 16px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton#exportPdfBtn:hover {{
                background-color: {default_theme.button_primary_hover};
            }}
            QPushButton#exportPdfBtn:pressed {{
                background-color: {default_theme.button_primary_pressed};
            }}
            QPushButton#exportPdfBtn:disabled {{
                background-color: {default_theme.button_default_bg};
                color: {default_theme.text_primary};
            }}
        """)
        self.export_pdf_btn.clicked.connect(self.export_pdf_report)
        card_layout.addWidget(self.export_pdf_btn)
        
        # Information footer
        footer_frame = QFrame()
        footer_frame.setObjectName("pdfReportFooter")
        footer_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        footer_frame.setMinimumHeight(36)
        footer_frame.setStyleSheet(f"""
            QFrame#pdfReportFooter {{
                background-color: {default_theme.background};
                border: 1px solid {default_theme.border_standard};
                border-radius: 6px;
            }}
        """)
        
        footer_layout = QHBoxLayout(footer_frame)
        footer_layout.setContentsMargins(10, 6, 10, 6)
        footer_layout.setSpacing(8)
        
        info_icon = QLabel("ℹ️")
        info_icon.setStyleSheet(f"color: {default_theme.icon_info_gray}; font-size: 11px;")
        info_icon.setFixedWidth(18)
        info_icon.setAlignment(Qt.AlignTop)
        
        disclaimer = QLabel("Requires Adobe Acrobat Reader for interactive 3D. Ensure VTK provides vtkU3DExporter (usually via 'pip install -U vtk').")
        disclaimer_font = QFont()
        disclaimer_font.setPointSize(9)
        disclaimer.setFont(disclaimer_font)
        disclaimer.setStyleSheet(f"color: {default_theme.icon_info_gray};")
        disclaimer.setWordWrap(True)
        
        footer_layout.addWidget(info_icon)
        footer_layout.addWidget(disclaimer)
        footer_layout.addStretch()
        
        card_layout.addWidget(footer_frame)
        
        # Add shadow effect
        self._add_card_shadow(card)
        
        return card
    
    def eventFilter(self, obj, event):
        """Handle hover events for rows."""
        # Rows handle their own events, but we need to ensure they're installed
        # The event filter is already installed on each row in create_*_section methods
        return super().eventFilter(obj, event)
    
    def on_material_changed(self, index):
        """Handle material selection change."""
        if index < 0 or index >= len(self.MATERIALS):
            return
        
        material_name, density = self.MATERIALS[index]
        self.weight_density_row.set_value(f"{density} g/cm³")
        self.calculate_weight()
    
    def calculate_weight(self, volume_mm3=None, density_g_per_cm3=None):
        """Calculate and update the estimated weight."""
        from core.mesh_calculator import MeshCalculator
        
        if volume_mm3 is None:
            volume_mm3 = self.current_volume_mm3
        
        if density_g_per_cm3 is None:
            index = self.material_combo.currentIndex()
            if index < 0 or index >= len(self.MATERIALS):
                return
            _, density_g_per_cm3 = self.MATERIALS[index]
        
        result = MeshCalculator.estimate_weight(volume_mm3, density_g_per_cm3)
        self.weight_result_row.set_value(result['display'])
        
        # Store current weight for scaling calculations
        self.current_weight_grams = result['grams']
        
        # Enable/disable calculate button based on whether we have valid data
        has_valid_weight = self.current_weight_grams > 0
        self.calculate_scale_btn.setEnabled(has_valid_weight)
        
        # Reset scale results if weight changed
        self.reset_scale_results()
    
    def calculate_scale(self):
        """Calculate the scale factor for target weight."""
        from core.mesh_calculator import MeshCalculator
        
        # Get target weight from input
        target_text = self.target_weight_input.text().strip()
        if not target_text:
            return
        
        try:
            target_weight = float(target_text)
        except ValueError:
            return
        
        if target_weight <= 0 or self.current_weight_grams <= 0:
            return
        
        # Calculate scale factor
        scale_result = MeshCalculator.calculate_scale_for_target_weight(
            self.current_weight_grams, target_weight
        )
        
        if not scale_result['valid']:
            return
        
        scale_factor = scale_result['scale_factor']
        self.calculated_scale_factor = scale_factor
        
        # Update scale factor display
        self.scale_factor_row.set_value(f"{scale_factor:.6f}")
        
        # Calculate new dimensions
        new_dims = MeshCalculator.apply_scale_to_dimensions(
            self.current_dimensions['width'],
            self.current_dimensions['height'],
            self.current_dimensions['depth'],
            scale_factor
        )
        
        self.new_x_row.set_value(f"{new_dims['width']:.2f} mm")
        self.new_y_row.set_value(f"{new_dims['height']:.2f} mm")
        self.new_z_row.set_value(f"{new_dims['depth']:.2f} mm")
        
        # Calculate new volume
        new_volume = MeshCalculator.apply_scale_to_volume(self.current_volume_mm3, scale_factor)
        self.new_volume_row.set_value(f"{new_volume['volume_cm3']:.4f} cm³")
        
        # Update weight comparison
        if self.current_weight_grams >= 1000:
            original_display = f"{self.current_weight_grams / 1000:.3f} kg"
        else:
            original_display = f"{self.current_weight_grams:.2f} g"
        
        if target_weight >= 1000:
            target_display = f"{target_weight / 1000:.3f} kg"
        else:
            target_display = f"{target_weight:.2f} g"
        
        self.original_weight_row.set_value(original_display)
        self.target_weight_row.set_value(target_display)
        
        # Enable export button
        self.export_scaled_btn.setEnabled(True)
        
        # Update state - scaled data now available
        self.has_scaled_data = True
        self.update_pdf_button_state()
    
    def reset_scale_results(self):
        """Reset all scale result displays."""
        self.scale_factor_row.set_value("--")
        self.new_x_row.set_value("--")
        self.new_y_row.set_value("--")
        self.new_z_row.set_value("--")
        self.new_volume_row.set_value("--")
        self.original_weight_row.set_value("--")
        self.target_weight_row.set_value("--")
        self.export_scaled_btn.setEnabled(False)
        self.calculated_scale_factor = 1.0
        
        # Update state - scaled data no longer available
        self.has_scaled_data = False
        self.update_pdf_button_state()
    
    def export_scaled_stl_file(self):
        """Handle export of scaled STL file."""
        if self.calculated_scale_factor == 1.0:
            return
        
        # Open save dialog
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Scaled STL File",
            "",
            "STL Files (*.stl);;All Files (*)"
        )
        
        if file_path:
            # Ensure .stl extension
            if not file_path.lower().endswith('.stl'):
                file_path += '.stl'
            
            # Emit signal with file path and scale factor
            self.export_scaled_stl.emit(file_path, self.calculated_scale_factor)
    
    def update_dimensions(self, mesh_data, filename=None):
        """Update all dimension displays with mesh data."""
        from core.mesh_calculator import MeshCalculator
        
        if mesh_data is None:
            self.width_row.set_value("--")
            self.height_row.set_value("--")
            self.depth_row.set_value("--")
            self.volume_row.set_value("--")
            self.surface_total_row.set_value("--")
            self.surface_cm_row.set_value("--")
            self.weight_volume_row.set_value("--")
            self.current_volume_mm3 = 0.0
            self.current_dimensions = {'width': 0.0, 'height': 0.0, 'depth': 0.0}
            self.current_surface_area_cm2 = 0.0
            self.current_stl_filename = ""
            self.has_stl_loaded = False
            self.calculate_weight()
            self.reset_scale_results()
            self.calculate_scale_btn.setEnabled(False)
            self.update_pdf_button_state()
            return
        
        # Store filename
        if filename:
            self.current_stl_filename = os.path.basename(filename)
        
        # Update dimensions
        self.width_row.set_value(f"{mesh_data['width']:.2f} mm")
        self.height_row.set_value(f"{mesh_data['height']:.2f} mm")
        self.depth_row.set_value(f"{mesh_data['depth']:.2f} mm")
        self.volume_row.set_value(f"{mesh_data['volume_mm3']:.2f} mm³")
        
        # Store current dimensions
        self.current_dimensions = {
            'width': mesh_data['width'],
            'height': mesh_data['height'],
            'depth': mesh_data['depth']
        }
        
        # Update surface area
        self.surface_total_row.set_value(f"{mesh_data['surface_area_mm2']:.2f} mm²")
        self.surface_cm_row.set_value(f"{mesh_data['surface_area_cm2']:.2f} cm²")
        self.current_surface_area_cm2 = mesh_data['surface_area_cm2']
        self.has_stl_loaded = True
        
        # Update weight calculator
        self.current_volume_mm3 = mesh_data['volume_mm3']
        self.weight_volume_row.set_value(f"{mesh_data['volume_cm3']:.4f} cm³")
        
        # Update density display
        index = self.material_combo.currentIndex()
        if index >= 0 and index < len(self.MATERIALS):
            _, density = self.MATERIALS[index]
            self.weight_density_row.set_value(f"{density} g/cm³")
        
        # Calculate weight
        self.calculate_weight()
        
        # Update PDF button state
        self.update_pdf_button_state()
    
    def update_pdf_button_state(self):
        """Update the PDF export button based on available data."""
        self.export_pdf_btn.setEnabled(self.has_stl_loaded)
    
    def export_pdf_report(self):
        """Generate and export 3D PDF with multiple views."""
        if not self.has_stl_loaded:
            return
        
        # We need access to the current mesh - emit a signal to get it
        # For now, we'll need to get mesh from parent
        mesh = self._get_current_mesh()
        if mesh is None:
            QMessageBox.warning(
                self,
                "Export Error",
                "No 3D model loaded. Please load a model first."
            )
            return
        
        # Open save dialog
        default_name = f"3D_Model_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save 3D PDF",
            default_name,
            "PDF Files (*.pdf);;All Files (*)"
        )
        
        if not file_path:
            return
        
        # Ensure .pdf extension
        if not file_path.lower().endswith('.pdf'):
            file_path += '.pdf'
        
        try:
            from core.pdf3d_exporter import PDF3DExporter
            
            # Show progress message
            self.export_pdf_btn.setEnabled(False)
            self.export_pdf_btn.setText("Exporting...")
            QApplication.processEvents()
            
            success, result = PDF3DExporter.export_interactive_3d_pdf(
                mesh, 
                file_path, 
                title=self.current_stl_filename,
                allow_static_fallback=False,
            )
            
            # Restore button
            self.export_pdf_btn.setEnabled(True)
            self.export_pdf_btn.setText("Export 3D PDF")
            
            if success:
                QMessageBox.information(
                    self,
                    "Export Complete",
                    f"3D PDF exported successfully:\n{file_path}"
                )
            else:
                # Help the user quickly find detailed exporter logs
                try:
                    app_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
                    log_path = os.path.join(app_root, "app_debug.log")
                except Exception:
                    log_path = "app_debug.log"

                QMessageBox.critical(
                    self,
                    "Export Error",
                    f"Failed to export interactive 3D PDF:\n{result}\n\n"
                    f"Detailed logs: {log_path}"
                )
        except Exception as e:
            logger.error(f"Error exporting 3D PDF: {e}")
            self.export_pdf_btn.setEnabled(True)
            self.export_pdf_btn.setText("Export 3D PDF")

            try:
                app_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
                log_path = os.path.join(app_root, "app_debug.log")
            except Exception:
                log_path = "app_debug.log"

            QMessageBox.critical(
                self,
                "Export Error",
                f"Failed to export interactive 3D PDF:\n{str(e)}\n\nDetailed logs: {log_path}"
            )
    
    def _get_current_mesh(self):
        """Get the current mesh from the viewer widget."""
        # Navigate up to find the main window and get mesh from viewer
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, 'viewer_widget') and hasattr(parent.viewer_widget, 'current_mesh'):
                return parent.viewer_widget.current_mesh
            parent = parent.parent()
        return None
    
    def create_export_annotations_section(self):
        """Create the Export as .ecto section."""
        card = QFrame()
        card.setObjectName("exportAnnotationsCard")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(10)
        
        # Header row with title and icon
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)
        
        title_label = QLabel("Export as .ecto")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet(f"color: {default_theme.text_title}; margin-bottom: 4px;")
        
        icon_label = QLabel("📦")
        icon_label.setStyleSheet(f"color: {default_theme.icon_blue}; font-size: 16px;")
        icon_label.setAlignment(Qt.AlignCenter)
        
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(icon_label)
        card_layout.addLayout(header_layout)
        
        # Description
        desc_label = QLabel("Export a single .ecto file with model, annotations, and photos bundled together.\nOnly ECTOFORM can open .ecto files.")
        desc_font = QFont()
        desc_font.setPointSize(11)
        desc_label.setFont(desc_font)
        desc_label.setStyleSheet(f"color: {default_theme.text_secondary};")
        desc_label.setWordWrap(True)
        card_layout.addWidget(desc_label)
        
        # Annotation count label
        self.annotation_count_label = QLabel("No annotations to export")
        self.annotation_count_label.setStyleSheet(f"color: {default_theme.text_secondary}; font-style: italic;")
        card_layout.addWidget(self.annotation_count_label)
        
        # Export button
        self.export_annotations_btn = QPushButton("Export as .ecto")
        self.export_annotations_btn.setObjectName("exportAnnotationsBtn")
        self.export_annotations_btn.setMinimumHeight(44)
        self.export_annotations_btn.setEnabled(False)
        self.export_annotations_btn.setStyleSheet(f"""
            QPushButton#exportAnnotationsBtn {{
                background-color: #8B5CF6;
                color: {default_theme.text_white};
                border: none;
                border-radius: 8px;
                padding: 10px 16px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton#exportAnnotationsBtn:hover {{
                background-color: #7C3AED;
            }}
            QPushButton#exportAnnotationsBtn:pressed {{
                background-color: #6D28D9;
            }}
            QPushButton#exportAnnotationsBtn:disabled {{
                background-color: {default_theme.button_default_bg};
                color: {default_theme.text_primary};
            }}
        """)
        self.export_annotations_btn.clicked.connect(self.export_as_ecto)
        card_layout.addWidget(self.export_annotations_btn)
        
        # Information footer
        footer_frame = QFrame()
        footer_frame.setObjectName("exportAnnotationsFooter")
        footer_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        footer_frame.setMinimumHeight(36)
        footer_frame.setStyleSheet(f"""
            QFrame#exportAnnotationsFooter {{
                background-color: {default_theme.background};
                border: 1px solid {default_theme.border_standard};
                border-radius: 6px;
            }}
        """)
        
        footer_layout = QHBoxLayout(footer_frame)
        footer_layout.setContentsMargins(10, 6, 10, 6)
        footer_layout.setSpacing(8)
        
        info_icon = QLabel("ℹ️")
        info_icon.setStyleSheet(f"color: {default_theme.icon_info_gray}; font-size: 11px;")
        info_icon.setFixedWidth(18)
        info_icon.setAlignment(Qt.AlignTop)
        
        disclaimer = QLabel("Single file contains: model + annotations + photos. Recipients open it directly in ECTOFORM.")
        disclaimer_font = QFont()
        disclaimer_font.setPointSize(9)
        disclaimer.setFont(disclaimer_font)
        disclaimer.setStyleSheet(f"color: {default_theme.icon_info_gray};")
        disclaimer.setWordWrap(True)
        
        footer_layout.addWidget(info_icon)
        footer_layout.addWidget(disclaimer)
        footer_layout.addStretch()
        
        card_layout.addWidget(footer_frame)
        
        # Add shadow effect
        self._add_card_shadow(card)
        
        return card
    
    def update_annotation_count(self, count: int):
        """Update the annotation count label and button state."""
        if count == 0:
            self.annotation_count_label.setText("No annotations to export")
            self.export_annotations_btn.setEnabled(self.has_stl_loaded)
        else:
            self.annotation_count_label.setText(f"📌 {count} annotation{'s' if count != 1 else ''} ready to export")
            self.export_annotations_btn.setEnabled(self.has_stl_loaded)
    
    def export_as_ecto(self):
        """Export the current model as an .ecto bundle file."""
        if not self.has_stl_loaded:
            QMessageBox.warning(
                self,
                "Export Error",
                "No 3D model loaded. Please load a model first."
            )
            return
        
        # Get current mesh
        mesh = self._get_current_mesh()
        if mesh is None:
            QMessageBox.warning(
                self,
                "Export Error",
                "No 3D model available for export."
            )
            return
        
        # Get annotations from annotation panel
        annotations = self._get_annotations()
        
        if not annotations:
            reply = QMessageBox.question(
                self,
                "No Annotations",
                "There are no annotations to include.\nDo you want to export the model as .ecto without annotations?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
        
        # Open save dialog
        default_name = f"{os.path.splitext(self.current_stl_filename)[0]}.ecto"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export as ECTOFORM Bundle",
            default_name,
            "ECTOFORM Bundle (*.ecto);;All Files (*)"
        )
        
        if not file_path:
            return
        
        # Ensure .ecto extension
        if not file_path.lower().endswith('.ecto'):
            file_path += '.ecto'
        
        try:
            from core.ecto_format import EctoFormat
            
            # Show progress
            self.export_annotations_btn.setEnabled(False)
            self.export_annotations_btn.setText("Exporting...")
            QApplication.processEvents()
            
            # Export as .ecto bundle
            success, result = EctoFormat.export(
                mesh=mesh,
                annotations=annotations,
                output_path=file_path,
                source_format='stl',
                original_filename=self.current_stl_filename
            )
            
            # Restore button
            self.export_annotations_btn.setEnabled(True)
            self.export_annotations_btn.setText("Export as .ecto")
            
            if success:
                # Build success message
                msg = f"Export complete!\n\nCreated: {os.path.basename(file_path)}"
                if annotations:
                    msg += f"\n\n📦 Bundle contains:"
                    msg += f"\n• 3D Model (STL)"
                    msg += f"\n• {len(annotations)} annotation{'s' if len(annotations) != 1 else ''}"
                    # Count images
                    image_count = sum(len(ann.get('image_paths', [])) for ann in annotations)
                    if image_count > 0:
                        msg += f"\n• {image_count} attached photo{'s' if image_count != 1 else ''}"
                else:
                    msg += f"\n\n📦 Bundle contains: 3D Model only"
                
                msg += "\n\nRecipients can open this file in ECTOFORM."
                
                QMessageBox.information(self, "Export Complete", msg)
            else:
                QMessageBox.critical(
                    self,
                    "Export Error",
                    f"Failed to create .ecto bundle:\n{result}"
                )
        except Exception as e:
            logger.error(f"Error exporting as .ecto: {e}")
            self.export_annotations_btn.setEnabled(True)
            self.export_annotations_btn.setText("Export as .ecto")
            QMessageBox.critical(
                self,
                "Export Error",
                f"Failed to create .ecto bundle:\n{str(e)}"
            )
    
    def _get_annotations(self):
        """Get annotations from the annotation panel."""
        # Navigate up to find the main window and get annotations
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, 'annotation_panel') and hasattr(parent.annotation_panel, 'export_annotations'):
                return parent.annotation_panel.export_annotations()
            parent = parent.parent()
        return []

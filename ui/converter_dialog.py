"""
File format converter dialog.
Standalone modal dialog for converting between 3D file formats (3DM, STEP, STL).
"""
import os
import logging

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton, QComboBox,
    QFileDialog, QMessageBox, QApplication, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal

from ui.styles import default_theme, make_font, sidebar_section_card_stylesheet
from i18n import t, on_language_changed

logger = logging.getLogger(__name__)


class ConverterDialog(QDialog):
    """Modal dialog for file format conversion."""

    conversion_complete = pyqtSignal(str)

    # Conversion map: source_ext -> list of (label, output_ext, conversion_type)
    _CONVERSION_MAP = {
        '.3dm': [
            ("3DM → STEP", ".step", "3dm_to_step"),
            ("3DM → STL", ".stl", "3dm_to_stl"),
        ],
        '.step': [
            ("STEP → STL", ".stl", "step_to_stl"),
        ],
        '.stp': [
            ("STEP → STL", ".stl", "step_to_stl"),
        ],
    }

    def __init__(self, parent=None, preset_file: str = None):
        super().__init__(parent)
        self.setWindowTitle("Convert File")
        self.setMinimumWidth(420)
        self.setModal(True)
        self._source_path = None

        self._init_ui()
        self._apply_theme()

        if preset_file:
            self._set_source(preset_file)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        # Title
        title = QLabel("🔄  Convert File")
        title.setFont(make_font(size=16, bold=True))
        title.setStyleSheet(f"color: {default_theme.text_title}; background: transparent; border: none;")
        layout.addWidget(title)

        # Subtitle
        subtitle = QLabel("Select a STEP or 3DM file to see available conversions")
        subtitle.setStyleSheet(
            f"color: {default_theme.text_secondary}; font-size: 12px; background: transparent; border: none;"
        )
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # Select file button
        self._select_btn = QPushButton("Select Source File…")
        self._select_btn.setObjectName("converterSelectBtn")
        self._select_btn.setMinimumHeight(42)
        self._select_btn.setCursor(Qt.PointingHandCursor)
        self._select_btn.setStyleSheet(f"""
            QPushButton#converterSelectBtn {{
                background-color: {default_theme.button_default_bg};
                color: {default_theme.text_primary};
                border: 1px solid {default_theme.border_light};
                border-radius: 8px;
                padding: 10px 16px;
                font-size: 13px;
                font-weight: 600;
                text-align: left;
            }}
            QPushButton#converterSelectBtn:hover {{
                background-color: {default_theme.row_bg_hover};
                border-color: {default_theme.border_highlight};
            }}
        """)
        self._select_btn.clicked.connect(self._select_source)
        layout.addWidget(self._select_btn)

        # File label
        self._file_label = QLabel("")
        self._file_label.setStyleSheet(
            f"color: {default_theme.text_secondary}; font-size: 11px; background: transparent; border: none;"
        )
        self._file_label.setWordWrap(True)
        self._file_label.hide()
        layout.addWidget(self._file_label)

        # Combo
        self._combo = QComboBox()
        self._combo.setObjectName("converterCombo")
        self._combo.setMinimumHeight(42)
        self._combo.setPlaceholderText("Select conversion…")
        self._combo.setStyleSheet(f"""
            QComboBox#converterCombo {{
                background-color: {default_theme.input_bg};
                color: {default_theme.text_primary};
                border: 1px solid {default_theme.input_border};
                border-radius: 8px;
                padding: 10px 12px;
                font-size: 13px;
            }}
            QComboBox#converterCombo:hover {{
                border: 1px solid {default_theme.input_border_hover};
            }}
            QComboBox#converterCombo::drop-down {{
                border: none;
                border-left: 1px solid {default_theme.input_border};
                width: 32px;
            }}
            QComboBox#converterCombo QAbstractItemView {{
                background-color: {default_theme.input_bg};
                color: {default_theme.text_primary};
                border: 1px solid {default_theme.input_border};
                border-radius: 6px;
                selection-background-color: {default_theme.row_bg_standard};
                selection-color: {default_theme.text_primary};
                padding: 8px 12px;
                outline: none;
            }}
        """)
        self._combo.hide()
        layout.addWidget(self._combo)

        # Convert button
        self._run_btn = QPushButton("Convert")
        self._run_btn.setObjectName("converterRunBtn")
        self._run_btn.setMinimumHeight(42)
        self._run_btn.setCursor(Qt.PointingHandCursor)
        self._run_btn.setStyleSheet(f"""
            QPushButton#converterRunBtn {{
                background-color: {default_theme.button_primary};
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 10px 16px;
                font-size: 13px;
                font-weight: 700;
            }}
            QPushButton#converterRunBtn:hover {{
                background-color: {default_theme.button_primary_hover};
            }}
            QPushButton#converterRunBtn:disabled {{
                background-color: {default_theme.border_standard};
                color: {default_theme.text_secondary};
            }}
        """)
        self._run_btn.clicked.connect(self._run_conversion)
        self._run_btn.hide()
        layout.addWidget(self._run_btn)

        layout.addStretch()

    def _apply_theme(self):
        self.setStyleSheet(f"""
            QDialog {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {default_theme.gradient_start},
                    stop:1 {default_theme.gradient_end});
            }}
        """)

    def _select_source(self):
        input_path, _ = QFileDialog.getOpenFileName(
            self, "Select File to Convert", "",
            "Supported Files (*.3dm *.step *.stp);;Rhino 3DM (*.3dm);;STEP Files (*.step *.stp)"
        )
        if input_path:
            self._set_source(input_path)

    def _set_source(self, file_path: str):
        ext = os.path.splitext(file_path)[1].lower()
        options = self._CONVERSION_MAP.get(ext, [])

        self._source_path = file_path
        self._file_label.setText(f"📄 {os.path.basename(file_path)}")
        self._file_label.show()

        self._combo.clear()
        if options:
            for label, output_ext, conv_type in options:
                self._combo.addItem(label, (output_ext, conv_type))
            self._combo.setCurrentIndex(0)
            self._combo.show()
            self._run_btn.show()
            self._run_btn.setEnabled(True)
        else:
            self._combo.hide()
            self._run_btn.hide()
            QMessageBox.warning(
                self, "Unsupported Format",
                f"No conversions available for '{ext}' files.\n\nSupported: .3dm, .step, .stp"
            )

    def _run_conversion(self):
        if not self._source_path or self._combo.currentIndex() < 0:
            return
        data = self._combo.currentData()
        if not data:
            return

        output_ext, conversion_type = data
        label = self._combo.currentText()
        default_output = os.path.splitext(self._source_path)[0] + output_ext

        ext_filters = {
            ".step": "STEP Files (*.step *.stp)",
            ".stl": "STL Files (*.stl)",
        }

        output_path, _ = QFileDialog.getSaveFileName(
            self, f"Save {label} Output", default_output,
            ext_filters.get(output_ext, "All Files (*)")
        )
        if not output_path:
            return

        from core.file_converter import FileConverter

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if conversion_type == "3dm_to_step":
                FileConverter.convert_3dm_to_step(self._source_path, output_path)
            elif conversion_type == "3dm_to_stl":
                FileConverter.convert_3dm_to_stl(self._source_path, output_path)
            elif conversion_type == "step_to_stl":
                FileConverter.convert_step_to_stl(self._source_path, output_path)

            QApplication.restoreOverrideCursor()
            QMessageBox.information(
                self, "Conversion Complete",
                f"{label} conversion successful!\n\nSaved to:\n{output_path}"
            )
            self.conversion_complete.emit(output_path)
            self.accept()
        except Exception as e:
            QApplication.restoreOverrideCursor()
            logger.error(f"Conversion failed ({label}): {e}", exc_info=True)
            QMessageBox.critical(
                self, "Conversion Failed",
                f"{label} conversion failed:\n\n{str(e)}"
            )

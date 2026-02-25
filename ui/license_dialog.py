"""
License Key Entry Dialog

PyQt5 dialog for entering and validating license keys.
"""

import sys
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QProgressBar
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
from typing import Optional

from core.license_validator import check_license_validity, store_license_key


class LicenseValidationThread(QThread):
    """Background thread for license validation to prevent UI freezing."""
    
    validation_complete = pyqtSignal(bool, str)  # is_valid, error_message
    
    def __init__(self, license_key: str):
        super().__init__()
        self.license_key = license_key
    
    def run(self):
        """Run license validation in background thread."""
        is_valid, error = check_license_validity(self.license_key, use_cache=True)
        self.validation_complete.emit(is_valid, error or "")


class LicenseDialog(QDialog):
    """Dialog for entering and validating license keys."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)  # Remove ? help button on Windows
        self.license_key = None
        self.validation_thread = None
        self.init_ui()
    
    def init_ui(self):
        """Initialize the dialog UI."""
        self.setWindowTitle("License Activation")
        self.setMinimumWidth(500)
        self.setMinimumHeight(250)
        self.setModal(True)
        from ui.annotation_icon import get_app_window_icon
        icon = get_app_window_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)
        
        # Apply styling to match application theme
        from ui.styles import default_theme
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {default_theme.background};
            }}
            QLabel {{
                color: {default_theme.text_primary};
            }}
            QLineEdit {{
                background-color: {default_theme.input_bg};
                border: 1px solid {default_theme.input_border};
                border-radius: 8px;
                padding: 10px 14px;
                font-size: 13px;
                color: {default_theme.text_primary};
            }}
            QLineEdit:focus {{
                border: 2px solid {default_theme.button_primary};
            }}
            QPushButton {{
                background-color: {default_theme.button_primary};
                color: {default_theme.text_white};
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {default_theme.button_primary_hover};
            }}
            QPushButton:pressed {{
                background-color: {default_theme.button_primary_pressed};
            }}
            QPushButton:disabled {{
                background-color: {default_theme.button_default_bg};
                color: {default_theme.text_secondary};
            }}
        """)
        
        # Main layout
        layout = QVBoxLayout()
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # Title
        title_label = QLabel("ECTOFORM")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # Instructions
        instructions = QLabel(
            "Please enter your license key to activate the application.\n"
            "You can obtain a license key from the software vendor."
        )
        instructions.setAlignment(Qt.AlignCenter)
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        
        # License key input
        key_layout = QVBoxLayout()
        key_label = QLabel("License Key:")
        key_layout.addWidget(key_label)
        
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("Enter your license key (e.g., STL-XXXX-XXXX-XXXX-XXXX)")
        self.key_input.returnPressed.connect(self.validate_license)
        key_layout.addWidget(self.key_input)
        layout.addLayout(key_layout)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(f"color: {default_theme.text_secondary};")
        layout.addWidget(self.status_label)
        
        # Progress bar (hidden initially)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        self.validate_button = QPushButton("Validate")
        self.validate_button.setDefault(True)
        self.validate_button.clicked.connect(self.validate_license)
        button_layout.addWidget(self.validate_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # Set focus on input
        self.key_input.setFocus()
    
    def validate_license(self):
        """Validate the entered license key."""
        license_key = self.key_input.text().strip()
        
        if not license_key:
            from ui.styles import default_theme
            self.status_label.setText("Please enter a license key")
            self.status_label.setStyleSheet("color: #FF0000;")
            return
        
        # Disable UI during validation
        self.key_input.setEnabled(False)
        self.validate_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.status_label.setText("Validating license key...")
        from ui.styles import default_theme
        self.status_label.setStyleSheet(f"color: {default_theme.text_secondary};")
        
        # Create and start validation thread
        self.validation_thread = LicenseValidationThread(license_key)
        self.validation_thread.validation_complete.connect(self.on_validation_complete)
        self.validation_thread.start()
    
    def on_validation_complete(self, is_valid: bool, error_message: str):
        """Handle validation completion."""
        # Re-enable UI
        self.key_input.setEnabled(True)
        self.validate_button.setEnabled(True)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        if is_valid:
            # Valid key
            self.license_key = self.key_input.text().strip()
            self.status_label.setText("License key validated successfully!")
            self.status_label.setStyleSheet("color: #00AA00;")
            
            # Close dialog after a brief delay
            self.validate_button.setText("Success!")
            self.validate_button.setEnabled(False)
            
            # Accept dialog (returns QDialog.Accepted)
            QMessageBox.information(
                self,
                "License Activated",
                "Your license has been activated successfully!\n"
                "You can now use the application."
            )
            self.accept()
        else:
            # Invalid key
            error_msg = error_message or "Invalid license key"
            self.status_label.setText(f"Validation failed: {error_msg}")
            self.status_label.setStyleSheet("color: #FF0000;")
            
            # Show error message
            QMessageBox.warning(
                self,
                "Invalid License Key",
                f"The license key you entered is invalid.\n\n"
                f"Error: {error_msg}\n\n"
                f"Please check your license key and try again."
            )
    
    def get_license_key(self) -> Optional[str]:
        """Get the validated license key."""
        return self.license_key


# For testing/development
if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    dialog = LicenseDialog()
    
    if dialog.exec() == QDialog.Accepted:
        print(f"License key accepted: {dialog.get_license_key()}")
    else:
        print("Dialog cancelled")
    
    sys.exit(app.exec())

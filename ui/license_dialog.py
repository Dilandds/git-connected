"""
License activation dialog for subscription-based commercial seats.
"""

import sys
from typing import Optional

from PyQt5.QtCore import QSize, QThread, Qt, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices, QFont
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.license_validator import (
    activate_subscription,
    get_buy_url,
    get_machine_fingerprint,
    get_support_url,
)


class LicenseValidationThread(QThread):
    """Background thread for license validation to prevent UI freezing."""
    
    validation_complete = pyqtSignal(bool, str, object)  # is_valid, error_message, response
    
    def __init__(self, license_key: str, user_identifier: str):
        super().__init__()
        self.license_key = license_key
        self.user_identifier = user_identifier
    
    def run(self):
        """Run license validation in background thread."""
        is_valid, response, error = activate_subscription(
            self.license_key,
            self.user_identifier,
            machine_fingerprint=get_machine_fingerprint(),
        )
        self.validation_complete.emit(is_valid, error or "", response or {})


class LicenseDialog(QDialog):
    """Dialog for entering and validating license keys."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)  # Remove ? help button on Windows
        self.license_key = None
        self.activation_response = None
        self.validation_thread = None
        self.init_ui()
    
    def init_ui(self):
        """Initialize the dialog UI."""
        self.setWindowTitle("License Activation")
        self.setMinimumWidth(560)
        self.setMinimumHeight(360)
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
            "Enter your commercial subscription key and work email to activate this device.\n"
            "Each company seat is tied to a user identity."
        )
        instructions.setAlignment(Qt.AlignCenter)
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        
        # Activation inputs
        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignTop)
        
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("Enter your subscription key")
        self.key_input.returnPressed.connect(self.validate_license)
        form_layout.addRow("Subscription Key:", self.key_input)

        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("name@company.com")
        self.user_input.returnPressed.connect(self.validate_license)
        form_layout.addRow("Work Email / User ID:", self.user_input)

        layout.addLayout(form_layout)

        helper_label = QLabel(
            "Buy the subscription if you do not have a key yet, or contact your company admin to assign a seat."
        )
        helper_label.setAlignment(Qt.AlignCenter)
        helper_label.setWordWrap(True)
        layout.addWidget(helper_label)

        # Link buttons
        link_layout = QHBoxLayout()
        link_layout.setSpacing(10)
        link_layout.addStretch()

        self.buy_button = QPushButton("Buy Subscription")
        self.buy_button.clicked.connect(lambda: self.open_external_url(get_buy_url(), "Buy Subscription"))
        link_layout.addWidget(self.buy_button)

        self.manage_button = QPushButton("Manage Seats")
        self.manage_button.clicked.connect(lambda: self.open_external_url(self.resolve_manage_url(), "Manage Seats"))
        link_layout.addWidget(self.manage_button)

        self.support_button = QPushButton("Support")
        self.support_button.clicked.connect(lambda: self.open_external_url(get_support_url(), "Support"))
        link_layout.addWidget(self.support_button)

        link_layout.addStretch()
        layout.addLayout(link_layout)
        
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

    def resolve_manage_url(self) -> str:
        """Resolve the current manage-seats URL from the backend response or config."""
        if isinstance(self.activation_response, dict):
            subscription = self.activation_response.get("subscription")
            if isinstance(subscription, dict):
                manage_url = subscription.get("management_url")
                if manage_url:
                    return str(manage_url)
        return get_manage_url()

    def open_external_url(self, url: str, label: str) -> None:
        """Open a URL in the system browser if configured."""
        if not url:
            QMessageBox.information(
                self,
                f"{label} Unavailable",
                f"{label} is not configured yet.",
            )
            return

        QDesktopServices.openUrl(QUrl(url))
    
    def validate_license(self):
        """Validate the entered license key."""
        license_key = self.key_input.text().strip()
        user_identifier = self.user_input.text().strip()
        
        if not license_key:
            self.status_label.setText("Please enter a license key")
            self.status_label.setStyleSheet("color: #FF0000;")
            return

        if not user_identifier:
            self.status_label.setText("Please enter your work email or user ID")
            self.status_label.setStyleSheet("color: #FF0000;")
            return
        
        # Disable UI during validation
        self.key_input.setEnabled(False)
        self.user_input.setEnabled(False)
        self.validate_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.status_label.setText("Validating license key...")
        from ui.styles import default_theme
        self.status_label.setStyleSheet(f"color: {default_theme.text_secondary};")
        
        # Create and start validation thread
        self.validation_thread = LicenseValidationThread(license_key, user_identifier)
        self.validation_thread.validation_complete.connect(self.on_validation_complete)
        self.validation_thread.start()
    
    def on_validation_complete(self, is_valid: bool, error_message: str, activation_response: object):
        """Handle validation completion."""
        # Re-enable UI
        self.key_input.setEnabled(True)
        self.user_input.setEnabled(True)
        self.validate_button.setEnabled(True)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        if is_valid:
            # Valid key
            self.license_key = self.key_input.text().strip()
            self.activation_response = activation_response if isinstance(activation_response, dict) else None

            subscription = {}
            if isinstance(self.activation_response, dict):
                subscription = self.activation_response.get("subscription") if isinstance(self.activation_response.get("subscription"), dict) else {}

            status = str(subscription.get("status", "active")).strip().lower()
            seat_limit = subscription.get("seat_limit")
            seats_used = subscription.get("seats_used")
            expires_at = subscription.get("expires_at")

            success_message = "Subscription activated successfully!"
            if status != "active":
                success_message = f"Subscription activated with status: {status}"

            if seat_limit is not None and seats_used is not None:
                success_message += f"\nSeats: {seats_used}/{seat_limit}"

            if expires_at:
                success_message += f"\nRenews/Expires: {expires_at}"

            self.status_label.setText(success_message)
            self.status_label.setStyleSheet("color: #00AA00;")
            
            # Close dialog after a brief delay
            self.validate_button.setText("Success!")
            self.validate_button.setEnabled(False)
            
            # Accept dialog (returns QDialog.Accepted)
            QMessageBox.information(
                self,
                "Subscription Activated",
                "Your subscription has been activated successfully!\n"
                "You can now use the application."
            )
            self.accept()
        else:
            # Invalid key or subscription issue
            error_msg = error_message or "Invalid license key"
            self.status_label.setText(f"Validation failed: {error_msg}")
            self.status_label.setStyleSheet("color: #FF0000;")
            
            # Show error message
            QMessageBox.warning(
                self,
                "Subscription Activation Failed",
                f"The subscription key could not be activated.\n\n"
                f"Error: {error_msg}\n\n"
                f"Please verify your subscription status or contact your company admin."
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

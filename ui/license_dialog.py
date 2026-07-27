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
        self.setWindowTitle("Activate LYNS360")
        self.setFixedSize(460, 440)
        self.setModal(True)
        from ui.annotation_icon import get_app_window_icon
        icon = get_app_window_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)

        # Apply styling to match application theme
        from ui.styles import default_theme
        self._theme = default_theme
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
                border-radius: 10px;
                padding: 10px 14px;
                font-size: 14px;
                color: {default_theme.text_primary};
            }}
            QLineEdit:focus {{
                border: 2px solid {default_theme.button_primary};
            }}
            QPushButton#primary {{
                background-color: {default_theme.button_primary};
                color: {default_theme.text_white};
                border: none;
                border-radius: 10px;
                padding: 12px 20px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton#primary:hover {{
                background-color: {default_theme.button_primary_hover};
            }}
            QPushButton#primary:pressed {{
                background-color: {default_theme.button_primary_pressed};
            }}
            QPushButton#primary:disabled {{
                background-color: {default_theme.button_default_bg};
                color: {default_theme.text_secondary};
            }}
            QPushButton#link {{
                background: transparent;
                border: none;
                color: {default_theme.button_primary};
                padding: 2px 4px;
                font-size: 12px;
                text-align: left;
            }}
            QPushButton#link:hover {{
                color: {default_theme.button_primary_hover};
                text-decoration: underline;
            }}
            QPushButton#cancel {{
                background: transparent;
                border: none;
                color: {default_theme.text_secondary};
                padding: 4px 10px;
                font-size: 12px;
            }}
            QPushButton#cancel:hover {{
                color: {default_theme.text_primary};
            }}
        """)

        layout = QVBoxLayout()
        layout.setSpacing(14)
        layout.setContentsMargins(36, 32, 36, 24)

        # Header icon
        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignCenter)
        if not icon.isNull():
            icon_label.setPixmap(icon.pixmap(QSize(56, 56)))
            icon_label.setFixedHeight(60)
        layout.addWidget(icon_label)

        # Title
        title_label = QLabel("Activate LYNS360")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # Subtitle
        subtitle = QLabel("Enter your license key to activate this device.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 12px;")
        layout.addWidget(subtitle)

        layout.addSpacing(8)

        # License key field
        key_label = QLabel("License key")
        key_label.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 11px; font-weight: bold;")
        layout.addWidget(key_label)

        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX")
        self.key_input.setFixedHeight(44)
        mono_font = QFont("Menlo, Consolas, monospace")
        mono_font.setStyleHint(QFont.Monospace)
        self.key_input.setFont(mono_font)
        self.key_input.textChanged.connect(self._on_key_changed)
        self.key_input.returnPressed.connect(self.validate_license)
        layout.addWidget(self.key_input)

        layout.addSpacing(4)

        # Primary action button
        self.activate_button = QPushButton("Activate this device")
        self.activate_button.setObjectName("primary")
        self.activate_button.setFixedHeight(44)
        self.activate_button.setDefault(True)
        self.activate_button.clicked.connect(self.validate_license)
        layout.addWidget(self.activate_button)

        # Inline status
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(32)
        self.status_label.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 12px;")
        layout.addWidget(self.status_label)

        layout.addStretch()

        # Footer links
        footer_layout = QHBoxLayout()
        footer_layout.setSpacing(6)

        buy_link = QPushButton("Don't have a key? Buy a subscription")
        buy_link.setObjectName("link")
        buy_link.setCursor(Qt.PointingHandCursor)
        buy_link.setFlat(True)
        buy_link.clicked.connect(lambda: self.open_external_url(get_buy_url(), "Buy Subscription"))
        footer_layout.addWidget(buy_link)

        footer_layout.addStretch()

        support_link = QPushButton("Contact support")
        support_link.setObjectName("link")
        support_link.setCursor(Qt.PointingHandCursor)
        support_link.setFlat(True)
        support_link.clicked.connect(lambda: self.open_external_url(get_support_url(), "Support"))
        footer_layout.addWidget(support_link)

        layout.addLayout(footer_layout)

        # Cancel
        cancel_layout = QHBoxLayout()
        cancel_layout.addStretch()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("cancel")
        self.cancel_button.setCursor(Qt.PointingHandCursor)
        self.cancel_button.clicked.connect(self.reject)
        cancel_layout.addWidget(self.cancel_button)
        layout.addLayout(cancel_layout)

        self.setLayout(layout)
        self.key_input.setFocus()

    def _on_key_changed(self, text: str) -> None:
        """Auto-uppercase license key input without breaking the cursor."""
        upper = text.upper()
        if upper != text:
            cursor_pos = self.key_input.cursorPosition()
            self.key_input.blockSignals(True)
            self.key_input.setText(upper)
            self.key_input.setCursorPosition(cursor_pos)
            self.key_input.blockSignals(False)

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

        if not license_key:
            self.status_label.setText("Please enter a license key.")
            self.status_label.setStyleSheet("color: #FF4444; font-size: 12px;")
            return

        # Disable UI during validation
        self.key_input.setEnabled(False)
        self.activate_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.activate_button.setText("Activating…")
        self.status_label.setText("")

        # Use the machine fingerprint as the identity (no separate user field).
        self.validation_thread = LicenseValidationThread(license_key, "")
        self.validation_thread.validation_complete.connect(self.on_validation_complete)
        self.validation_thread.start()

    def on_validation_complete(self, is_valid: bool, error_message: str, activation_response: object):
        """Handle validation completion."""
        self.key_input.setEnabled(True)
        self.activate_button.setEnabled(True)
        self.cancel_button.setEnabled(True)
        self.activate_button.setText("Activate this device")

        if is_valid:
            self.license_key = self.key_input.text().strip()
            self.activation_response = activation_response if isinstance(activation_response, dict) else None

            self.status_label.setText("✓ Device activated.")
            self.status_label.setStyleSheet("color: #00AA55; font-size: 12px; font-weight: bold;")
            self.activate_button.setText("Activated")
            self.activate_button.setEnabled(False)

            # Brief delay so the user sees the confirmation, then close.
            QTimer.singleShot(800, self.accept)
        else:
            error_msg = error_message or "Invalid license key"
            self.status_label.setText(error_msg)
            self.status_label.setStyleSheet("color: #FF4444; font-size: 12px;")

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

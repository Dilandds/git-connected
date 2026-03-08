"""
Passcode Dialog - Set or Enter a passcode for .ecto file edit protection.
Uses SHA-256 hashing; no plaintext passcodes are stored.
"""
import hashlib
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from ui.styles import default_theme


def hash_passcode(passcode: str) -> str:
    """Return SHA-256 hex digest of a passcode string."""
    return hashlib.sha256(passcode.encode('utf-8')).hexdigest()


def verify_passcode(passcode: str, stored_hash: str) -> bool:
    """Check if a passcode matches a stored SHA-256 hash."""
    return hash_passcode(passcode) == stored_hash


class PasscodeDialog(QDialog):
    """Dialog for setting or entering a passcode.

    Modes:
      - 'set':   Two fields (passcode + confirm). Returns the hash on accept.
      - 'enter': One field. Returns True on accept if hash matches.
    """

    def __init__(self, mode: str = 'set', stored_hash: str = None, parent=None):
        super().__init__(parent)
        assert mode in ('set', 'enter')
        self._mode = mode
        self._stored_hash = stored_hash
        self._result_hash: str | None = None
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("Set Passcode" if self._mode == 'set' else "Enter Passcode")
        self.setMinimumWidth(400)
        self.setModal(True)
        from ui.annotation_icon import get_app_window_icon
        icon = get_app_window_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)

        self.setStyleSheet(f"""
            QDialog {{ background-color: {default_theme.background}; }}
            QLabel {{ color: {default_theme.text_primary}; }}
            QLineEdit {{
                background-color: {default_theme.input_bg};
                border: 1px solid {default_theme.input_border};
                border-radius: 8px; padding: 10px 14px; font-size: 13px;
                color: {default_theme.text_primary};
            }}
            QLineEdit:focus {{ border: 2px solid {default_theme.button_primary}; }}
            QPushButton {{
                background-color: {default_theme.button_primary};
                color: white; border: none; border-radius: 8px;
                padding: 10px 20px; font-size: 13px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {default_theme.button_primary_hover}; }}
            QPushButton:pressed {{ background-color: {default_theme.button_primary_pressed}; }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(30, 30, 30, 30)

        title = QLabel("Set Passcode" if self._mode == 'set' else "Enter Passcode")
        tf = QFont(); tf.setPointSize(14); tf.setBold(True)
        title.setFont(tf)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        if self._mode == 'set':
            hint = QLabel("This passcode will be required to edit the .ecto file.\nAnyone can still view the file without a passcode.")
        else:
            hint = QLabel("Enter the passcode to unlock editing.")
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 11px;")
        layout.addWidget(hint)

        layout.addWidget(QLabel("Passcode:"))
        self._passcode_input = QLineEdit()
        self._passcode_input.setEchoMode(QLineEdit.Password)
        self._passcode_input.setPlaceholderText("Enter passcode")
        layout.addWidget(self._passcode_input)

        if self._mode == 'set':
            layout.addWidget(QLabel("Confirm Passcode:"))
            self._confirm_input = QLineEdit()
            self._confirm_input.setEchoMode(QLineEdit.Password)
            self._confirm_input.setPlaceholderText("Re-enter passcode")
            layout.addWidget(self._confirm_input)

        self._status = QLabel("")
        self._status.setAlignment(Qt.AlignCenter)
        self._status.setStyleSheet("color: #DC2626; font-size: 11px;")
        layout.addWidget(self._status)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.setStyleSheet(f"""
            QPushButton {{
                background-color: {default_theme.button_default_bg};
                color: {default_theme.text_primary}; border: 1px solid {default_theme.button_default_border};
                border-radius: 8px; padding: 10px 20px; font-size: 13px;
            }}
            QPushButton:hover {{ background-color: {default_theme.row_bg_hover}; }}
        """)
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)

        ok = QPushButton("Set Passcode" if self._mode == 'set' else "Unlock")
        ok.setDefault(True)
        ok.clicked.connect(self._on_ok)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)

        self._passcode_input.setFocus()
        self._passcode_input.returnPressed.connect(self._on_ok)

    def _on_ok(self):
        pw = self._passcode_input.text()
        if not pw:
            self._status.setText("Passcode cannot be empty.")
            return

        if self._mode == 'set':
            if pw != self._confirm_input.text():
                self._status.setText("Passcodes do not match.")
                return
            if len(pw) < 4:
                self._status.setText("Passcode must be at least 4 characters.")
                return
            self._result_hash = hash_passcode(pw)
            self.accept()
        else:
            if verify_passcode(pw, self._stored_hash):
                self.accept()
            else:
                self._status.setText("Incorrect passcode. Try again.")

    def get_passcode_hash(self) -> str | None:
        """Return the SHA-256 hash (set mode only)."""
        return self._result_hash

"""
Login dialog for ECTOFORM — Supabase authentication.
"""
import sys
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QInputDialog,
)

from ui.styles import default_theme
import session


class _AuthThread(QThread):
    done = pyqtSignal(bool, dict, str)  # success, profile, error

    def __init__(self, email: str, password: str):
        super().__init__()
        self._email = email
        self._password = password

    def run(self):
        try:
            from supabase_client import get_client
            client = get_client()
            resp = client.auth.sign_in_with_password({
                "email": self._email,
                "password": self._password,
            })
            uid = resp.user.id
            profile_resp = (
                client.table('profiles')
                .select('*')
                .eq('id', uid)
                .single()
                .execute()
            )
            profile = profile_resp.data or {}
            profile['email'] = resp.user.email
            self.done.emit(True, profile, "")
        except Exception as exc:
            self.done.emit(False, {}, str(exc))


class _ResetThread(QThread):
    done = pyqtSignal(bool, str)

    def __init__(self, email: str):
        super().__init__()
        self._email = email

    def run(self):
        try:
            from supabase_client import get_client
            client = get_client()
            client.auth.reset_password_for_email(self._email)
            self.done.emit(True, "")
        except Exception as exc:
            self.done.emit(False, str(exc))


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setWindowTitle("Sign In — ECTOFORM")
        self.setFixedSize(420, 500)
        self.setModal(True)
        self._auth_thread = None
        self._reset_thread = None
        self._build_ui()

    def _build_ui(self):
        t = default_theme
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {t.background};
            }}
            QLabel {{
                color: {t.text_primary};
            }}
            QLineEdit {{
                background-color: {t.input_bg};
                border: 1px solid {t.input_border};
                border-radius: 10px;
                padding: 10px 14px;
                font-size: 14px;
                color: {t.text_primary};
            }}
            QLineEdit:focus {{
                border: 2px solid {t.button_primary};
            }}
            QPushButton#primary {{
                background-color: {t.button_primary};
                color: {t.text_white};
                border: none;
                border-radius: 10px;
                padding: 12px 20px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton#primary:hover {{
                background-color: {t.button_primary_hover};
            }}
            QPushButton#primary:pressed {{
                background-color: {t.button_primary_pressed};
            }}
            QPushButton#primary:disabled {{
                background-color: {t.button_default_bg};
                color: {t.text_secondary};
            }}
            QPushButton#link {{
                background: transparent;
                border: none;
                color: {t.button_primary};
                padding: 2px 4px;
                font-size: 12px;
            }}
            QPushButton#link:hover {{
                color: {t.button_primary_hover};
                text-decoration: underline;
            }}
        """)

        layout = QVBoxLayout()
        layout.setSpacing(14)
        layout.setContentsMargins(36, 32, 36, 28)

        # App icon
        from ui.annotation_icon import get_app_window_icon
        icon = get_app_window_icon()
        if not icon.isNull():
            icon_label = QLabel()
            icon_label.setAlignment(Qt.AlignCenter)
            icon_label.setPixmap(icon.pixmap(QSize(52, 52)))
            icon_label.setFixedHeight(58)
            layout.addWidget(icon_label)
            self.setWindowIcon(icon)

        # Title
        title = QLabel("Sign in to ECTOFORM")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Subtitle
        subtitle = QLabel("Enter your credentials to continue.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {t.text_secondary}; font-size: 12px;")
        layout.addWidget(subtitle)

        layout.addSpacing(8)

        # Email
        email_label = QLabel("Email")
        email_label.setStyleSheet(f"color: {t.text_secondary}; font-size: 11px; font-weight: bold;")
        layout.addWidget(email_label)

        self._email_input = QLineEdit()
        self._email_input.setPlaceholderText("you@company.com")
        self._email_input.setFixedHeight(44)
        self._email_input.returnPressed.connect(self._on_login)
        layout.addWidget(self._email_input)

        # Password
        pw_label = QLabel("Password")
        pw_label.setStyleSheet(f"color: {t.text_secondary}; font-size: 11px; font-weight: bold;")
        layout.addWidget(pw_label)

        pw_row = QHBoxLayout()
        pw_row.setSpacing(6)
        self._pw_input = QLineEdit()
        self._pw_input.setPlaceholderText("••••••••")
        self._pw_input.setEchoMode(QLineEdit.Password)
        self._pw_input.setFixedHeight(44)
        self._pw_input.returnPressed.connect(self._on_login)
        pw_row.addWidget(self._pw_input)

        self._show_pw_btn = QPushButton("Show")
        self._show_pw_btn.setObjectName("link")
        self._show_pw_btn.setFixedSize(46, 44)
        self._show_pw_btn.setCursor(Qt.PointingHandCursor)
        self._show_pw_btn.clicked.connect(self._toggle_password)
        pw_row.addWidget(self._show_pw_btn)
        layout.addLayout(pw_row)

        # Status label — errors in red, success in green
        self._status_label = QLabel("")
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("color: #FF4444; font-size: 12px;")
        self._status_label.setMinimumHeight(20)
        layout.addWidget(self._status_label)

        # Sign In button
        self._login_btn = QPushButton("Sign In")
        self._login_btn.setObjectName("primary")
        self._login_btn.setFixedHeight(44)
        self._login_btn.setDefault(True)
        self._login_btn.clicked.connect(self._on_login)
        layout.addWidget(self._login_btn)

        # Forgot password
        forgot_row = QHBoxLayout()
        forgot_row.addStretch()
        self._forgot_btn = QPushButton("Forgot your password?")
        self._forgot_btn.setObjectName("link")
        self._forgot_btn.setCursor(Qt.PointingHandCursor)
        self._forgot_btn.clicked.connect(self._on_forgot_password)
        forgot_row.addWidget(self._forgot_btn)
        forgot_row.addStretch()
        layout.addLayout(forgot_row)

        layout.addStretch()
        self.setLayout(layout)
        self._email_input.setFocus()

    def _toggle_password(self):
        if self._pw_input.echoMode() == QLineEdit.Password:
            self._pw_input.setEchoMode(QLineEdit.Normal)
            self._show_pw_btn.setText("Hide")
        else:
            self._pw_input.setEchoMode(QLineEdit.Password)
            self._show_pw_btn.setText("Show")

    def _set_loading(self, loading: bool):
        self._login_btn.setEnabled(not loading)
        self._email_input.setEnabled(not loading)
        self._pw_input.setEnabled(not loading)
        self._forgot_btn.setEnabled(not loading)
        self._login_btn.setText("Signing in…" if loading else "Sign In")

    def _on_login(self):
        email = self._email_input.text().strip()
        password = self._pw_input.text()

        if not email or not password:
            self._status_label.setStyleSheet("color: #FF4444; font-size: 12px;")
            self._status_label.setText("Please enter your email and password.")
            return

        self._status_label.setText("")
        self._set_loading(True)

        self._auth_thread = _AuthThread(email, password)
        self._auth_thread.done.connect(self._on_auth_done)
        self._auth_thread.start()

    def _on_auth_done(self, success: bool, profile: dict, error: str):
        self._set_loading(False)
        if success:
            session.set_user(profile)
            self.accept()
        else:
            msg = "Invalid email or password."
            if "Email not confirmed" in error:
                msg = "Please confirm your email before signing in."
            elif "Invalid login credentials" not in error and error:
                msg = f"Sign in failed. Please try again."
            self._status_label.setStyleSheet("color: #FF4444; font-size: 12px;")
            self._status_label.setText(msg)

    def _on_forgot_password(self):
        email = self._email_input.text().strip()
        if not email:
            email, ok = QInputDialog.getText(
                self, "Reset Password", "Enter your email address:"
            )
            if not ok or not email.strip():
                return
            email = email.strip()

        self._forgot_btn.setEnabled(False)
        self._forgot_btn.setText("Sending…")

        self._reset_thread = _ResetThread(email)
        self._reset_thread.done.connect(self._on_reset_done)
        self._reset_thread.start()

    def _on_reset_done(self, success: bool, error: str):
        self._forgot_btn.setEnabled(True)
        self._forgot_btn.setText("Forgot your password?")
        if success:
            self._status_label.setStyleSheet("color: #00AA55; font-size: 12px;")
            self._status_label.setText("Password reset email sent. Check your inbox.")
            QTimer.singleShot(5000, lambda: (
                self._status_label.setStyleSheet("color: #FF4444; font-size: 12px;"),
                self._status_label.setText(""),
            ))
        else:
            self._status_label.setStyleSheet("color: #FF4444; font-size: 12px;")
            self._status_label.setText("Could not send reset email. Please try again.")

"""
Activation dialog for ECTOFORM — license key entry + first admin setup.
Shown once on first launch per device. Bypassed in DEV_MODE.
"""
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QStackedWidget, QWidget,
)

from ui.styles import default_theme

try:
    from config import TEST_LICENSE_KEY
except ImportError:
    TEST_LICENSE_KEY = None


def _stylesheet(t):
    return f"""
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
        QPushButton#back {{
            background: transparent;
            border: none;
            color: {t.text_secondary};
            padding: 2px 4px;
            font-size: 12px;
        }}
        QPushButton#back:hover {{
            color: {t.text_primary};
        }}
    """


class _LookupThread(QThread):
    """Query Supabase to check if a company already exists for this license key."""
    done = pyqtSignal(bool, str, str)  # found, company_name, error

    def __init__(self, license_key: str):
        super().__init__()
        self._license_key = license_key

    def run(self):
        import logging
        logger = logging.getLogger(__name__)
        try:
            from supabase_client import get_client
            client = get_client()
            logger.info("_LookupThread: querying companies for license key %s", self._license_key)
            resp = (
                client.table('companies')
                .select('name')
                .eq('license_key', self._license_key)
                .execute()
            )
            logger.info("_LookupThread: result data=%s", resp.data)
            if resp.data:
                self.done.emit(True, resp.data[0]['name'], "")
            else:
                self.done.emit(False, "", "")
        except Exception as exc:
            logger.error("_LookupThread: exception: %s", exc, exc_info=True)
            self.done.emit(False, "", str(exc))


class _SetupThread(QThread):
    done = pyqtSignal(bool, str)  # success, error

    def __init__(self, company_name: str, full_name: str,
                 email: str, password: str, license_key: str):
        super().__init__()
        self._company = company_name
        self._full_name = full_name
        self._email = email
        self._password = password
        self._license_key = license_key

    def run(self):
        import logging
        logger = logging.getLogger(__name__)
        try:
            from supabase_client import get_client
            client = get_client()

            # Try to create the auth user. If the email already exists from a
            # previous failed attempt, sign in instead so we can finish setup.
            resp = client.auth.sign_up({
                "email": self._email,
                "password": self._password,
            })

            if resp.user is None:
                self.done.emit(False, "Could not create user account.")
                return

            if resp.session is None:
                self.done.emit(
                    False,
                    "Email confirmation is required. Disable it in Supabase → "
                    "Authentication → Settings → Email → Confirm email OFF."
                )
                return

            session = resp.session
            user_id = resp.user.id
            logger.info("_SetupThread: auth user ready %s", user_id)

        except Exception as exc:
            error_str = str(exc)
            if "already registered" not in error_str and "already exists" not in error_str:
                logger.error("_SetupThread: sign_up failed: %s", exc, exc_info=True)
                self.done.emit(False, error_str)
                return

            # Auth user exists from a prior failed attempt — sign in to recover
            logger.info("_SetupThread: user exists, attempting recovery sign-in")
            try:
                from supabase_client import get_client
                client = get_client()
                resp = client.auth.sign_in_with_password({
                    "email": self._email,
                    "password": self._password,
                })
                session = resp.session
                user_id = resp.user.id
                logger.info("_SetupThread: recovery sign-in OK, user %s", user_id)
            except Exception as sign_in_exc:
                logger.error("_SetupThread: recovery sign-in failed: %s", sign_in_exc)
                self.done.emit(
                    False,
                    "An account with this email already exists. "
                    "If you previously tried to activate and it failed, "
                    "use the same password to retry — or use a different email."
                )
                return

        try:
            # Set the session so subsequent requests use the user's JWT
            client.auth.set_session(session.access_token, session.refresh_token)

            # Check if this user already has a profile (setup already complete)
            existing = (
                client.table('profiles')
                .select('id')
                .eq('id', user_id)
                .execute()
            )
            if existing.data:
                logger.info("_SetupThread: profile already exists, setup was already complete")
                self.done.emit(True, "")
                return

            # Check if a company already exists for this license key
            existing_company = (
                client.table('companies')
                .select('id')
                .eq('license_key', self._license_key)
                .execute()
            )

            if existing_company.data:
                company_id = existing_company.data[0]['id']
                logger.info("_SetupThread: company already exists %s, creating profile", company_id)
            else:
                company_resp = client.table('companies').insert({
                    "name": self._company,
                    "license_key": self._license_key,
                }).execute()
                company_id = company_resp.data[0]['id']
                logger.info("_SetupThread: company created %s", company_id)

            client.table('profiles').insert({
                "id": user_id,
                "full_name": self._full_name,
                "role": "admin",
                "company_id": company_id,
            }).execute()

            logger.info("_SetupThread: profile created, setup complete")
            self.done.emit(True, "")
        except Exception as exc:
            logger.error("_SetupThread: setup failed: %s", exc, exc_info=True)
            self.done.emit(False, str(exc))


class ActivationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setWindowTitle("Activate ECTOFORM")
        self.setFixedSize(440, 540)
        self.setModal(True)
        self._license_key = None
        self._lookup_thread = None
        self._setup_thread = None
        self._build_ui()

    def _build_ui(self):
        from ui.annotation_icon import get_app_window_icon
        self._icon = get_app_window_icon()
        if not self._icon.isNull():
            self.setWindowIcon(self._icon)

        self.setStyleSheet(_stylesheet(default_theme))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_license_page())   # 0 — key entry
        self._stack.addWidget(self._build_setup_page())     # 1 — first admin setup
        self._stack.addWidget(self._build_welcome_page())   # 2 — company already exists
        outer.addWidget(self._stack)

    # ── Page 0: License key ──────────────────────────────────────────────────

    def _build_license_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(14)
        layout.setContentsMargins(36, 32, 36, 28)
        t = default_theme

        if not self._icon.isNull():
            icon_label = QLabel()
            icon_label.setAlignment(Qt.AlignCenter)
            icon_label.setPixmap(self._icon.pixmap(QSize(52, 52)))
            icon_label.setFixedHeight(58)
            layout.addWidget(icon_label)

        title = QLabel("Activate ECTOFORM")
        f = QFont(); f.setPointSize(16); f.setBold(True)
        title.setFont(f)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        sub = QLabel("Enter your license key to get started.")
        sub.setAlignment(Qt.AlignCenter)
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color: {t.text_secondary}; font-size: 12px;")
        layout.addWidget(sub)

        layout.addSpacing(8)

        key_lbl = QLabel("License Key")
        key_lbl.setStyleSheet(f"color: {t.text_secondary}; font-size: 11px; font-weight: bold;")
        layout.addWidget(key_lbl)

        self._key_input = QLineEdit()
        self._key_input.setPlaceholderText("ECTO-XXXX-XXXX-XXXX")
        self._key_input.setFixedHeight(44)
        self._key_input.returnPressed.connect(self._on_validate_key)
        layout.addWidget(self._key_input)

        self._key_status = QLabel("")
        self._key_status.setAlignment(Qt.AlignCenter)
        self._key_status.setWordWrap(True)
        self._key_status.setStyleSheet("color: #FF4444; font-size: 12px;")
        self._key_status.setMinimumHeight(20)
        layout.addWidget(self._key_status)

        self._activate_btn = QPushButton("Continue")
        self._activate_btn.setObjectName("primary")
        self._activate_btn.setFixedHeight(44)
        self._activate_btn.setDefault(True)
        self._activate_btn.clicked.connect(self._on_validate_key)
        layout.addWidget(self._activate_btn)

        if TEST_LICENSE_KEY:
            hint = QLabel(f"Dev bypass key: {TEST_LICENSE_KEY}")
            hint.setAlignment(Qt.AlignCenter)
            hint.setStyleSheet(f"color: {t.text_secondary}; font-size: 10px;")
            layout.addWidget(hint)

        layout.addStretch()
        return page

    def _on_validate_key(self):
        key = self._key_input.text().strip().upper()
        if not key:
            self._key_status.setText("Please enter your license key.")
            return

        if TEST_LICENSE_KEY and key == TEST_LICENSE_KEY.upper():
            pass  # test key accepted — fall through to Supabase lookup
        else:
            # TODO: validate against Polar.sh
            self._key_status.setText("Live license validation coming soon. Use the dev key for now.")
            return

        self._license_key = key
        self._key_status.setText("")
        self._set_key_loading(True)

        self._lookup_thread = _LookupThread(key)
        self._lookup_thread.done.connect(self._on_lookup_done)
        self._lookup_thread.start()

    def _set_key_loading(self, loading: bool):
        self._activate_btn.setEnabled(not loading)
        self._activate_btn.setText("Checking…" if loading else "Continue")
        self._key_input.setEnabled(not loading)

    def _on_lookup_done(self, found: bool, company_name: str, error: str):
        self._set_key_loading(False)
        if error:
            self._key_status.setText("Could not connect to server. Check your internet and try again.")
            return

        if found:
            # Company already set up — this is a team member joining
            self._welcome_label.setText(
                f"Welcome to <b>{company_name}</b>.<br><br>"
                f"Your company account is already set up.<br>"
                f"Sign in to continue."
            )
            self._stack.setCurrentIndex(2)
        else:
            # First use of this key — admin setup
            self._stack.setCurrentIndex(1)

    # ── Page 1: First admin setup ────────────────────────────────────────────

    def _build_setup_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)
        layout.setContentsMargins(36, 28, 36, 28)
        t = default_theme

        title = QLabel("Set up your account")
        f = QFont(); f.setPointSize(16); f.setBold(True)
        title.setFont(f)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        sub = QLabel("You'll be the admin for your company workspace.")
        sub.setAlignment(Qt.AlignCenter)
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color: {t.text_secondary}; font-size: 12px;")
        layout.addWidget(sub)

        layout.addSpacing(4)

        def _field(label_text, placeholder, echo=QLineEdit.Normal):
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"color: {t.text_secondary}; font-size: 11px; font-weight: bold;")
            layout.addWidget(lbl)
            inp = QLineEdit()
            inp.setPlaceholderText(placeholder)
            inp.setFixedHeight(42)
            inp.setEchoMode(echo)
            inp.returnPressed.connect(self._on_create_account)
            layout.addWidget(inp)
            return inp

        self._company_input = _field("Company Name",     "Acme Corp")
        self._name_input    = _field("Your Full Name",   "John Smith")
        self._email_input   = _field("Email",            "you@company.com")
        self._pw_input      = _field("Password",         "••••••••", QLineEdit.Password)
        self._pw2_input     = _field("Confirm Password", "••••••••", QLineEdit.Password)

        self._setup_status = QLabel("")
        self._setup_status.setAlignment(Qt.AlignCenter)
        self._setup_status.setWordWrap(True)
        self._setup_status.setStyleSheet("color: #FF4444; font-size: 12px;")
        self._setup_status.setMinimumHeight(20)
        layout.addWidget(self._setup_status)

        self._create_btn = QPushButton("Create Account")
        self._create_btn.setObjectName("primary")
        self._create_btn.setFixedHeight(44)
        self._create_btn.setDefault(True)
        self._create_btn.clicked.connect(self._on_create_account)
        layout.addWidget(self._create_btn)

        back_row = QHBoxLayout()
        back_row.addStretch()
        back_btn = QPushButton("← Back")
        back_btn.setObjectName("back")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        back_row.addWidget(back_btn)
        back_row.addStretch()
        layout.addLayout(back_row)

        layout.addStretch()
        return page

    def _on_create_account(self):
        company = self._company_input.text().strip()
        name    = self._name_input.text().strip()
        email   = self._email_input.text().strip()
        pw      = self._pw_input.text()
        pw2     = self._pw2_input.text()

        if not all([company, name, email, pw, pw2]):
            self._setup_status.setText("Please fill in all fields.")
            return
        if pw != pw2:
            self._setup_status.setText("Passwords do not match.")
            return
        if len(pw) < 8:
            self._setup_status.setText("Password must be at least 8 characters.")
            return

        self._setup_status.setText("")
        self._set_setup_loading(True)

        self._setup_thread = _SetupThread(company, name, email, pw, self._license_key)
        self._setup_thread.done.connect(self._on_setup_done)
        self._setup_thread.start()

    def _set_setup_loading(self, loading: bool):
        self._create_btn.setEnabled(not loading)
        self._create_btn.setText("Creating account…" if loading else "Create Account")
        for w in [self._company_input, self._name_input,
                  self._email_input, self._pw_input, self._pw2_input]:
            w.setEnabled(not loading)

    def _on_setup_done(self, success: bool, error: str):
        self._set_setup_loading(False)
        if success:
            self._setup_status.setStyleSheet("color: #00AA55; font-size: 12px;")
            self._setup_status.setText("Account created! You can now sign in.")
            QTimer.singleShot(1200, self.accept)
        else:
            self._setup_status.setStyleSheet("color: #FF4444; font-size: 12px;")
            msg = "Could not create account. Please try again."
            if "already registered" in error or "already exists" in error:
                msg = "This email is already registered."
            self._setup_status.setText(msg)

    # ── Page 2: Welcome — company already exists (team member) ──────────────

    def _build_welcome_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(16)
        layout.setContentsMargins(36, 60, 36, 28)
        t = default_theme

        if not self._icon.isNull():
            icon_label = QLabel()
            icon_label.setAlignment(Qt.AlignCenter)
            icon_label.setPixmap(self._icon.pixmap(QSize(52, 52)))
            icon_label.setFixedHeight(58)
            layout.addWidget(icon_label)

        self._welcome_label = QLabel("")
        self._welcome_label.setAlignment(Qt.AlignCenter)
        self._welcome_label.setWordWrap(True)
        self._welcome_label.setStyleSheet(f"color: {t.text_primary}; font-size: 14px;")
        layout.addWidget(self._welcome_label)

        layout.addSpacing(8)

        signin_btn = QPushButton("Sign In")
        signin_btn.setObjectName("primary")
        signin_btn.setFixedHeight(44)
        signin_btn.setDefault(True)
        signin_btn.clicked.connect(self.accept)
        layout.addWidget(signin_btn)

        back_row = QHBoxLayout()
        back_row.addStretch()
        back_btn = QPushButton("← Back")
        back_btn.setObjectName("back")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        back_row.addWidget(back_btn)
        back_row.addStretch()
        layout.addLayout(back_row)

        layout.addStretch()
        return page

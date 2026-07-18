"""
User Management dialog — admin-only.
Lists team members, lets admin invite new users and remove existing ones.
"""
import logging
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QScrollArea, QWidget, QFrame,
    QSizePolicy,
)

from ui.styles import default_theme
import session

logger = logging.getLogger(__name__)

ROLE_LABELS = {"admin": "Admin", "manager": "Manager", "member": "Member", "supplier": "Supplier"}


# ─── Background threads ──────────────────────────────────────────────────────

class _LoadUsersThread(QThread):
    done = pyqtSignal(list, str)  # users, error

    def run(self):
        try:
            from supabase_client import get_client
            client = get_client()
            resp = (
                client.table("profiles")
                .select("id, full_name, role")
                .execute()
            )
            self.done.emit(resp.data or [], "")
        except Exception as exc:
            logger.error("LoadUsersThread: %s", exc, exc_info=True)
            self.done.emit([], str(exc))


class _InviteThread(QThread):
    done = pyqtSignal(bool, str, str)  # success, error, temp_password

    def __init__(self, email: str, full_name: str, role: str):
        super().__init__()
        self._email = email
        self._full_name = full_name
        self._role = role

    def run(self):
        try:
            from supabase_client import get_client
            import json, urllib.request, urllib.error
            client = get_client()
            sess = client.auth.get_session()
            if not sess or not sess.access_token:
                self.done.emit(False, "Session expired — please sign in again.")
                return

            from config import SUPABASE_URL, SUPABASE_KEY
            url = f"{SUPABASE_URL}/functions/v1/invite-user"
            payload = json.dumps({
                "email": self._email,
                "full_name": self._full_name,
                "role": self._role,
            }).encode()
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {sess.access_token}",
                    "apikey": SUPABASE_KEY,
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = json.loads(resp.read())
            if body.get("success"):
                self.done.emit(True, "", body.get("temp_password", ""))
            else:
                self.done.emit(False, body.get("error", "Unknown error"), "")
        except urllib.error.HTTPError as exc:
            try:
                import json
                body = json.loads(exc.read())
                self.done.emit(False, body.get("error", exc.reason), "")
            except Exception:
                self.done.emit(False, str(exc), "")
        except Exception as exc:
            logger.error("InviteThread: %s", exc, exc_info=True)
            self.done.emit(False, str(exc), "")


class _RemoveThread(QThread):
    done = pyqtSignal(bool, str)  # success, error

    def __init__(self, user_id: str):
        super().__init__()
        self._user_id = user_id

    def run(self):
        try:
            from supabase_client import get_client
            import json, urllib.request, urllib.error
            client = get_client()
            sess = client.auth.get_session()
            if not sess or not sess.access_token:
                self.done.emit(False, "Session expired — please sign in again.")
                return

            from config import SUPABASE_URL, SUPABASE_KEY
            url = f"{SUPABASE_URL}/functions/v1/remove-user"
            payload = json.dumps({"user_id": self._user_id}).encode()
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {sess.access_token}",
                    "apikey": SUPABASE_KEY,
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = json.loads(resp.read())
            if body.get("success"):
                self.done.emit(True, "")
            else:
                self.done.emit(False, body.get("error", "Unknown error"))
        except urllib.error.HTTPError as exc:
            try:
                import json
                body = json.loads(exc.read())
                self.done.emit(False, body.get("error", exc.reason))
            except Exception:
                self.done.emit(False, str(exc))
        except Exception as exc:
            logger.error("RemoveThread: %s", exc, exc_info=True)
            self.done.emit(False, str(exc))


# ─── Dialog ──────────────────────────────────────────────────────────────────

class UserManagementDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setWindowTitle("Manage Team — ECTOFORM")
        self.setMinimumSize(520, 480)
        self.resize(520, 540)
        self.setModal(True)
        self._threads = []
        self._current_user_id = session.get_user().get("id", "") if session.get_user() else ""
        self._build_ui()
        self._load_users()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        t = default_theme
        self.setStyleSheet(f"""
            QDialog {{ background-color: {t.background}; }}
            QLabel {{ color: {t.text_primary}; }}
            QLineEdit {{
                background-color: {t.input_bg};
                border: 1px solid {t.input_border};
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
                color: {t.text_primary};
            }}
            QLineEdit:focus {{ border: 2px solid {t.button_primary}; }}
            QComboBox {{
                background-color: {t.input_bg};
                border: 1px solid {t.input_border};
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
                color: {t.text_primary};
            }}
            QPushButton#primary {{
                background-color: {t.button_primary};
                color: {t.text_white};
                border: none;
                border-radius: 8px;
                padding: 10px 18px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton#primary:hover {{ background-color: {t.button_primary_hover}; }}
            QPushButton#primary:disabled {{
                background-color: {t.button_default_bg};
                color: {t.text_secondary};
            }}
            QPushButton#danger {{
                background-color: transparent;
                color: #e05252;
                border: 1px solid #e05252;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 11px;
            }}
            QPushButton#danger:hover {{ background-color: #e05252; color: white; }}
            QPushButton#danger:disabled {{ color: {t.text_secondary}; border-color: {t.border_light}; }}
        """)

        outer = QVBoxLayout(self)
        outer.setSpacing(16)
        outer.setContentsMargins(28, 24, 28, 20)

        # Title
        title = QLabel("Team Members")
        f = QFont(); f.setPointSize(15); f.setBold(True)
        title.setFont(f)
        outer.addWidget(title)

        # ── Member list ───────────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        self._list_widget = QWidget()
        self._list_widget.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setSpacing(6)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.addStretch()

        scroll.setWidget(self._list_widget)
        outer.addWidget(scroll, 1)

        self._list_status = QLabel("Loading…")
        self._list_status.setAlignment(Qt.AlignCenter)
        self._list_status.setStyleSheet(f"color: {t.text_secondary}; font-size: 12px;")
        outer.addWidget(self._list_status)

        # ── Divider ───────────────────────────────────────────────────────────
        div = QFrame(); div.setFrameShape(QFrame.HLine)
        div.setStyleSheet(f"color: {t.border_light};")
        outer.addWidget(div)

        # ── Invite form ───────────────────────────────────────────────────────
        invite_title = QLabel("Invite New Member")
        f2 = QFont(); f2.setPointSize(12); f2.setBold(True)
        invite_title.setFont(f2)
        outer.addWidget(invite_title)

        form_row = QHBoxLayout()
        form_row.setSpacing(8)

        self._inv_email = QLineEdit()
        self._inv_email.setPlaceholderText("Email address")
        self._inv_email.setFixedHeight(40)
        form_row.addWidget(self._inv_email, 3)

        self._inv_name = QLineEdit()
        self._inv_name.setPlaceholderText("Full name")
        self._inv_name.setFixedHeight(40)
        form_row.addWidget(self._inv_name, 3)

        self._inv_role = QComboBox()
        self._inv_role.setFixedHeight(40)
        for key, label in ROLE_LABELS.items():
            self._inv_role.addItem(label, key)
        self._inv_role.setCurrentIndex(2)  # default: member
        form_row.addWidget(self._inv_role, 2)

        outer.addLayout(form_row)

        self._inv_status = QLabel("")
        self._inv_status.setAlignment(Qt.AlignCenter)
        self._inv_status.setWordWrap(True)
        self._inv_status.setStyleSheet("color: #FF4444; font-size: 12px;")
        self._inv_status.setMinimumHeight(20)
        outer.addWidget(self._inv_status)

        self._invite_btn = QPushButton("Send Invite")
        self._invite_btn.setObjectName("primary")
        self._invite_btn.setFixedHeight(42)
        self._invite_btn.clicked.connect(self._on_invite)
        outer.addWidget(self._invite_btn)

    # ── Load users ────────────────────────────────────────────────────────────

    def _load_users(self):
        self._list_status.setText("Loading…")
        t = _LoadUsersThread()
        t.done.connect(self._on_users_loaded)
        self._threads.append(t)
        t.start()

    def _on_users_loaded(self, users: list, error: str):
        # Clear existing rows (keep the trailing stretch)
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if error:
            self._list_status.setText(f"Could not load team: {error}")
            return

        self._list_status.setText("")

        if not users:
            self._list_status.setText("No team members yet.")
            return

        for user in users:
            self._list_layout.insertWidget(self._list_layout.count() - 1, self._make_row(user))

    def _make_row(self, user: dict) -> QWidget:
        t = default_theme
        uid = user.get("id", "")
        name = user.get("full_name") or "Unknown"
        role = user.get("role") or "member"
        role_label = ROLE_LABELS.get(role, role.capitalize())
        is_self = uid == self._current_user_id

        row = QWidget()
        row.setStyleSheet(f"""
            QWidget {{
                background-color: {t.input_bg};
                border: 1px solid {t.input_border};
                border-radius: 8px;
            }}
        """)
        row.setFixedHeight(52)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(14, 0, 10, 0)
        rl.setSpacing(10)

        # Initials badge
        initials = "".join(p[0].upper() for p in name.split()[:2]) or "?"
        badge = QLabel(initials)
        badge.setFixedSize(28, 28)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(f"""
            QLabel {{
                background-color: {t.button_primary};
                color: white;
                border-radius: 14px;
                font-size: 10px;
                font-weight: bold;
                border: none;
            }}
        """)
        rl.addWidget(badge)

        name_lbl = QLabel(name + (" (you)" if is_self else ""))
        name_lbl.setStyleSheet(f"background: transparent; border: none; font-size: 13px; color: {t.text_primary};")
        rl.addWidget(name_lbl, 1)

        role_lbl = QLabel(role_label)
        role_lbl.setStyleSheet(f"background: transparent; border: none; font-size: 11px; color: {t.text_secondary};")
        rl.addWidget(role_lbl)

        remove_btn = QPushButton("Remove")
        remove_btn.setObjectName("danger")
        remove_btn.setFixedSize(72, 28)
        remove_btn.setEnabled(not is_self)
        remove_btn.clicked.connect(lambda _, u=uid, n=name: self._on_remove(u, n))
        rl.addWidget(remove_btn)

        return row

    # ── Invite ────────────────────────────────────────────────────────────────

    def _on_invite(self):
        email = self._inv_email.text().strip()
        full_name = self._inv_name.text().strip()
        role = self._inv_role.currentData()

        if not email or not full_name:
            self._inv_status.setStyleSheet("color: #FF4444; font-size: 12px;")
            self._inv_status.setText("Email and name are required.")
            return

        self._inv_status.setText("")
        self._invite_btn.setEnabled(False)
        self._invite_btn.setText("Sending…")

        t = _InviteThread(email, full_name, role)
        t.done.connect(self._on_invite_done)
        self._threads.append(t)
        t.start()

    def _on_invite_done(self, success: bool, error: str, temp_password: str):
        self._invite_btn.setEnabled(True)
        self._invite_btn.setText("Send Invite")
        if success:
            email = self._inv_email.text().strip()
            self._inv_email.clear()
            self._inv_name.clear()
            self._inv_role.setCurrentIndex(2)
            self._load_users()
            self._show_temp_password(email, temp_password)
        else:
            self._inv_status.setStyleSheet("color: #FF4444; font-size: 12px;")
            self._inv_status.setText(error or "Could not add user. Try again.")

    def _show_temp_password(self, email: str, temp_password: str):
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
        from PyQt5.QtGui import QFont
        t = default_theme
        dlg = QDialog(self)
        dlg.setWindowTitle("User Created")
        dlg.setFixedSize(400, 260)
        dlg.setStyleSheet(f"QDialog {{ background-color: {t.background}; }} QLabel {{ color: {t.text_primary}; }}")

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(12)

        title = QLabel("Account Created")
        f = QFont(); f.setPointSize(14); f.setBold(True)
        title.setFont(f)
        layout.addWidget(title)

        desc = QLabel(
            f"Share these credentials with <b>{email}</b>.<br>"
            "They can change their password after signing in."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {t.text_secondary}; font-size: 12px;")
        layout.addWidget(desc)

        pw_label = QLabel("Temporary Password")
        pw_label.setStyleSheet(f"color: {t.text_secondary}; font-size: 11px; font-weight: bold;")
        layout.addWidget(pw_label)

        pw_box = QLabel(temp_password)
        pw_box.setAlignment(Qt.AlignCenter)
        pw_box.setStyleSheet(f"""
            QLabel {{
                background-color: {t.input_bg};
                border: 1px solid {t.input_border};
                border-radius: 8px;
                padding: 10px;
                font-size: 18px;
                font-weight: bold;
                letter-spacing: 2px;
                color: {t.text_primary};
            }}
        """)
        layout.addWidget(pw_box)

        btn_row = QHBoxLayout()
        copy_btn = QPushButton("Copy Password")
        copy_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t.button_primary};
                color: white; border: none; border-radius: 8px;
                padding: 10px 18px; font-size: 13px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {t.button_primary_hover}; }}
        """)
        copy_btn.clicked.connect(lambda: (
            __import__('PyQt5.QtWidgets', fromlist=['QApplication']).QApplication.clipboard().setText(temp_password),
            copy_btn.setText("Copied!"),
        ))
        btn_row.addWidget(copy_btn)

        close_btn = QPushButton("Done")
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent; color: {t.text_secondary};
                border: 1px solid {t.border_light}; border-radius: 8px;
                padding: 10px 18px; font-size: 13px;
            }}
        """)
        close_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        dlg.exec_()

    # ── Remove ────────────────────────────────────────────────────────────────

    def _on_remove(self, user_id: str, name: str):
        from PyQt5.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self,
            "Remove Team Member",
            f"Remove <b>{name}</b> from your team?<br><br>"
            "They will lose access immediately and their account will be deleted.",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if reply != QMessageBox.Yes:
            return

        t = _RemoveThread(user_id)
        t.done.connect(lambda ok, err: self._on_remove_done(ok, err, name))
        self._threads.append(t)
        t.start()

    def _on_remove_done(self, success: bool, error: str, name: str):
        if success:
            self._inv_status.setStyleSheet("color: #00AA55; font-size: 12px;")
            self._inv_status.setText(f"{name} has been removed.")
            self._load_users()
        else:
            self._inv_status.setStyleSheet("color: #FF4444; font-size: 12px;")
            self._inv_status.setText(error or "Could not remove user. Try again.")

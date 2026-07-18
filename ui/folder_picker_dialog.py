"""
Folder picker dialog — shown after login when no project folder is set.
Handles first-time setup (admin writes workspace marker) and team member
joining an existing folder (reads and validates the marker file).
"""
import json
import logging
import os
from pathlib import Path

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog,
)

from ui.styles import default_theme
import session

logger = logging.getLogger(__name__)

WORKSPACE_MARKER = ".ectoform-workspace"


class _ValidateFolderThread(QThread):
    """Validate the selected folder and write/check the workspace marker."""
    done = pyqtSignal(bool, str)  # success, error

    def __init__(self, folder: str, company_id: str, role: str):
        super().__init__()
        self._folder = folder
        self._company_id = company_id
        self._role = role

    def run(self):
        try:
            folder_path = Path(self._folder)

            if not folder_path.exists():
                self.done.emit(False, "Folder does not exist.")
                return

            marker_path = folder_path / WORKSPACE_MARKER

            if marker_path.exists():
                # Folder already set up — validate it belongs to this company
                try:
                    with open(marker_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    stored_company_id = data.get("company_id", "")
                    if stored_company_id != self._company_id:
                        self.done.emit(
                            False,
                            "This folder belongs to a different company.\n"
                            "Please select the correct shared folder for your team."
                        )
                        return
                    # Matched — done
                    self.done.emit(True, "")
                    return
                except (json.JSONDecodeError, OSError):
                    # Corrupted marker — treat as missing
                    pass

            # No (valid) marker — only admin can initialise the folder
            if self._role not in ("admin", "manager"):
                self.done.emit(
                    False,
                    "This folder has not been set up for your team yet.\n"
                    "Ask your administrator to set up the shared folder first,\n"
                    "then select the same folder here."
                )
                return

            # Admin: check we can write to the folder
            test_file = folder_path / ".ectoform-write-check"
            try:
                test_file.write_text("ok")
                test_file.unlink()
            except OSError:
                self.done.emit(
                    False,
                    "Cannot write to this folder. Check permissions and try again."
                )
                return

            # Write the workspace marker
            marker_data = {
                "company_id": self._company_id,
                "created_by": session.get_full_name() or "admin",
            }
            with open(marker_path, "w", encoding="utf-8") as f:
                json.dump(marker_data, f, indent=2)

            logger.info("Workspace marker written to %s", marker_path)
            self.done.emit(True, "")

        except Exception as exc:
            logger.error("Folder validation error: %s", exc, exc_info=True)
            self.done.emit(False, f"Unexpected error: {exc}")


class FolderPickerDialog(QDialog):
    """
    Shown after login when QSettings has no project_folder, or when the
    stored folder is missing. Lets the user browse to the shared project
    folder and validates it against the workspace marker file.
    """

    def __init__(self, missing: bool = False, parent=None):
        """
        missing=True  → folder was previously saved but no longer exists (re-pick)
        missing=False → first time on this device
        """
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setWindowTitle("Select Project Folder — ECTOFORM")
        self.setFixedSize(480, 340)
        self.setModal(True)
        self._missing = missing
        self._validate_thread = None
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
                font-size: 13px;
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
            QPushButton#secondary {{
                background-color: transparent;
                color: {t.button_primary};
                border: 1px solid {t.button_primary};
                border-radius: 10px;
                padding: 10px 16px;
                font-size: 13px;
            }}
            QPushButton#secondary:hover {{
                background-color: {t.button_primary};
                color: {t.text_white};
            }}
        """)

        layout = QVBoxLayout()
        layout.setSpacing(14)
        layout.setContentsMargins(36, 28, 36, 24)

        # Title
        title = QLabel("Select Shared Project Folder")
        title_font = QFont()
        title_font.setPointSize(15)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Description
        if self._missing:
            desc_text = (
                "Your previously saved project folder could not be found.\n"
                "Please select the correct shared folder for your team."
            )
        else:
            role = session.get_role() or "member"
            if role in ("admin", "manager"):
                desc_text = (
                    "Select or create the shared folder where your team's\n"
                    "project files will be stored. Other team members will\n"
                    "need access to this same folder."
                )
            else:
                desc_text = (
                    "Select the shared folder your administrator has set up\n"
                    "for your team. Make sure you have access to it."
                )

        desc = QLabel(desc_text)
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {t.text_secondary}; font-size: 12px;")
        layout.addWidget(desc)

        layout.addSpacing(6)

        # Folder path row
        path_row = QHBoxLayout()
        path_row.setSpacing(8)

        self._path_input = QLineEdit()
        self._path_input.setPlaceholderText("No folder selected…")
        self._path_input.setReadOnly(True)
        self._path_input.setFixedHeight(44)
        path_row.addWidget(self._path_input)

        browse_btn = QPushButton("Browse…")
        browse_btn.setObjectName("secondary")
        browse_btn.setFixedHeight(44)
        browse_btn.setCursor(Qt.PointingHandCursor)
        browse_btn.clicked.connect(self._on_browse)
        path_row.addWidget(browse_btn)

        layout.addLayout(path_row)

        # Status label
        self._status_label = QLabel("")
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("color: #FF4444; font-size: 12px;")
        self._status_label.setMinimumHeight(32)
        layout.addWidget(self._status_label)

        # Confirm button
        self._confirm_btn = QPushButton("Confirm Folder")
        self._confirm_btn.setObjectName("primary")
        self._confirm_btn.setFixedHeight(44)
        self._confirm_btn.setEnabled(False)
        self._confirm_btn.clicked.connect(self._on_confirm)
        layout.addWidget(self._confirm_btn)

        layout.addStretch()
        self.setLayout(layout)

    def _on_browse(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Project Folder",
            str(Path.home()),
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
        )
        if folder:
            self._path_input.setText(folder)
            self._confirm_btn.setEnabled(True)
            self._status_label.setText("")

    def _set_loading(self, loading: bool):
        self._confirm_btn.setEnabled(not loading)
        self._confirm_btn.setText("Validating…" if loading else "Confirm Folder")

    def _on_confirm(self):
        folder = self._path_input.text().strip()
        if not folder:
            return

        company_id = session.get_company_id()
        role = session.get_role() or "member"

        if not company_id:
            self._status_label.setText("Session error — please sign in again.")
            return

        self._status_label.setText("")
        self._set_loading(True)

        self._validate_thread = _ValidateFolderThread(folder, company_id, role)
        self._validate_thread.done.connect(self._on_validate_done)
        self._validate_thread.start()

    def _on_validate_done(self, success: bool, error: str):
        self._set_loading(False)
        if success:
            from PyQt5.QtCore import QSettings
            settings = QSettings("ECTOFORM", "ECTOFORM")
            settings.setValue("project_folder", self._path_input.text().strip())
            settings.sync()
            logger.info("Project folder saved: %s", self._path_input.text().strip())
            self.accept()
        else:
            self._status_label.setText(error)
            self._confirm_btn.setEnabled(True)

    def selected_folder(self) -> str:
        return self._path_input.text().strip()

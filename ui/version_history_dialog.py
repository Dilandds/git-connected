"""
Version History Dialog — browse and manually restore local snapshots of the
current project file (see core/version_history.py). Purely on-demand: this
dialog is the only place these snapshots ever get surfaced or acted on.
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton,
)
from PyQt5.QtCore import Qt

from ui.styles import default_theme
from ui.components import confirm_dialog
from core.version_history import list_snapshots, restore_snapshot
from i18n import t


def _format_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size < 1024 or unit == 'GB':
            return f'{size:.0f} {unit}' if unit == 'B' else f'{size:.1f} {unit}'
        size /= 1024
    return f'{size:.1f} GB'


class VersionHistoryDialog(QDialog):
    """Lists local snapshots for `project_path`, newest first, with a
    Restore action. Restoring always archives the current file first (see
    restore_snapshot), so it's itself never a way to lose data."""

    def __init__(self, parent, project_path: str):
        super().__init__(parent)
        self._project_path = project_path
        self.restored = False
        self.setWindowTitle(t('project.version_history.title'))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumSize(480, 420)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {default_theme.card_background}; }}
            QLabel {{ color: {default_theme.text_primary}; }}
        """)
        self._init_ui()
        self._populate()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel(t('project.version_history.title'))
        title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {default_theme.text_primary};")
        layout.addWidget(title)

        subtitle = QLabel(t('project.version_history.subtitle'))
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 11px;")
        layout.addWidget(subtitle)

        self._list = QListWidget()
        self._list.setStyleSheet(f"""
            QListWidget {{
                background-color: {default_theme.background};
                border: 1px solid {default_theme.border_standard};
                border-radius: 6px;
                color: {default_theme.text_primary};
                font-size: 12px;
            }}
            QListWidget::item {{ padding: 8px; }}
            QListWidget::item:selected {{ background-color: {default_theme.button_primary}; color: #ffffff; }}
        """)
        layout.addWidget(self._list, 1)

        self._empty_label = QLabel(t('project.version_history.empty'))
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setStyleSheet(f"color: {default_theme.text_secondary}; font-size: 12px; padding: 24px;")
        self._empty_label.hide()
        layout.addWidget(self._empty_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._close_btn = QPushButton(t('project.version_history.close'))
        self._close_btn.setCursor(Qt.PointingHandCursor)
        self._close_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._close_btn)

        self._restore_btn = QPushButton(t('project.version_history.restore'))
        self._restore_btn.setCursor(Qt.PointingHandCursor)
        self._restore_btn.setEnabled(False)
        self._restore_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {default_theme.button_primary};
                color: #ffffff;
                border-radius: 6px;
                padding: 6px 16px;
                font-weight: bold;
            }}
            QPushButton:disabled {{ background-color: {default_theme.border_standard}; color: {default_theme.text_secondary}; }}
        """)
        self._restore_btn.clicked.connect(self._on_restore)
        btn_row.addWidget(self._restore_btn)
        layout.addLayout(btn_row)

        self._list.itemSelectionChanged.connect(
            lambda: self._restore_btn.setEnabled(bool(self._list.selectedItems()))
        )

    def _populate(self):
        snapshots = list_snapshots(self._project_path)
        if not snapshots:
            self._list.hide()
            self._empty_label.show()
            return
        for snap in snapshots:
            local_time = snap['timestamp'].astimezone()
            label = f"{local_time.strftime('%b %d, %Y · %H:%M')} — {_format_size(snap['size'])}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, snap['path'])
            self._list.addItem(item)

    def _on_restore(self):
        items = self._list.selectedItems()
        if not items:
            return
        snapshot_path = items[0].data(Qt.UserRole)
        if not confirm_dialog(
            self,
            t('project.version_history.confirm_title'),
            t('project.version_history.confirm_body'),
        ):
            return
        if restore_snapshot(snapshot_path, self._project_path):
            self.restored = True
            self.accept()
        else:
            from ui.modal_utils import show_error_dialog
            show_error_dialog(self, t('project.version_history.confirm_title'),
                               t('project.version_history.restore_failed'))

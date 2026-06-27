"""
Prototype tab — manage prototype versions with photos, files, status and comments.
"""
import uuid
import os
from dataclasses import dataclass, field, asdict
from typing import List, Dict

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QComboBox, QTextEdit, QFileDialog,
    QSizePolicy, QLineEdit,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap

from ui.styles import default_theme
from i18n import t

# ── Theme ────────────────────────────────────────────────────────────────────
_CARD     = '#ffffff'
_TEXT     = '#1a2033'
_MUTED    = '#6b7280'
_ACCENT   = default_theme.button_primary
_ACCENT_H = default_theme.button_primary_hover
_BORDER   = '#e2e8f0'
_HDR_BG   = '#f8fafc'

_STATUS = {
    'in_progress':     ('#3b82f6', '#eff6ff'),
    'to_be_modified':  ('#f59e0b', '#fffbeb'),
    'to_be_validated': ('#8b5cf6', '#f5f3ff'),
    'validated':       ('#22c55e', '#f0fdf4'),
}
_STATUS_KEYS = [
    ('proto.status_in_progress',    'in_progress'),
    ('proto.status_to_be_modified', 'to_be_modified'),
    ('proto.status_to_validate',    'to_be_validated'),
    ('proto.status_validated',      'validated'),
]

_LBL_CSS = f'color: {_MUTED}; font-size: 11px; font-weight: 600; letter-spacing: 0.5px;'


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class PrototypeVersion:
    id: str
    version_number: int
    date: str = ''
    status: str = 'in_progress'
    comments: str = ''
    image_path: str = ''
    file_paths: List[str] = field(default_factory=list)


# ── Photo area ────────────────────────────────────────────────────────────────

class _PhotoArea(QFrame):
    """Clickable area showing a photo thumbnail or an upload placeholder."""
    changed = pyqtSignal(str)

    def __init__(self, path: str = '', parent=None):
        super().__init__(parent)
        self._path = path
        self._build()

    def _build(self):
        self.setMinimumHeight(200)
        self.setMaximumHeight(240)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
            QFrame {{
                background: #f8fafc;
                border: 2px dashed {_BORDER};
                border-radius: 10px;
            }}
            QFrame:hover {{
                border-color: {_ACCENT};
                background: #eff6ff;
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(6)

        self._icon_lbl = QLabel('📷')
        self._icon_lbl.setAlignment(Qt.AlignCenter)
        self._icon_lbl.setStyleSheet('background: transparent; font-size: 32px; border: none;')
        lay.addWidget(self._icon_lbl)

        self._img_lbl = QLabel()
        self._img_lbl.setAlignment(Qt.AlignCenter)
        self._img_lbl.setStyleSheet('background: transparent; border: none;')
        lay.addWidget(self._img_lbl)

        self._hint_lbl = QLabel()
        self._hint_lbl.setAlignment(Qt.AlignCenter)
        self._hint_lbl.setStyleSheet(
            f'background: transparent; color: {_MUTED}; font-size: 12px; border: none;'
        )
        lay.addWidget(self._hint_lbl)

        self._refresh()

    def _refresh(self):
        has_img = bool(self._path and os.path.exists(self._path))
        if has_img:
            pix = QPixmap(self._path).scaled(
                self.width() - 24 if self.width() > 24 else 260, 180,
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
            self._img_lbl.setPixmap(pix)
            self._icon_lbl.hide()
            self._hint_lbl.setText(t('proto.click_to_change'))
        else:
            self._img_lbl.clear()
            self._icon_lbl.show()
            self._hint_lbl.setText(t('proto.click_to_add_photo'))

    def set_path(self, path: str):
        self._path = path
        self._refresh()

    def get_path(self) -> str:
        return self._path

    def mousePressEvent(self, _event):
        path, _ = QFileDialog.getOpenFileName(
            self, t('proto.select_photo'), '',
            'Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tiff)',
        )
        if path:
            self._path = path
            self._refresh()
            self.changed.emit(path)


# ── File chip ─────────────────────────────────────────────────────────────────

class _FileChip(QFrame):
    """Inline chip for an attached file with a remove ×."""
    remove_requested = pyqtSignal(str)

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self._path = path
        name = os.path.basename(path)
        self.setStyleSheet(f"""
            QFrame {{ background: #f1f5f9; border: 1px solid {_BORDER}; border-radius: 5px; }}
        """)
        row = QHBoxLayout(self)
        row.setContentsMargins(6, 3, 4, 3)
        row.setSpacing(4)

        icon = QLabel('📎')
        icon.setStyleSheet('background: transparent; font-size: 11px;')
        row.addWidget(icon)

        display = name if len(name) <= 30 else name[:27] + '…'
        lbl = QLabel(display)
        lbl.setToolTip(path)
        lbl.setStyleSheet(f'background: transparent; color: {_TEXT}; font-size: 11px;')
        row.addWidget(lbl, 1)

        btn = QPushButton('×')
        btn.setFixedSize(16, 16)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #94a3b8;
                border: none; font-size: 14px; font-weight: bold; padding: 0;
            }
            QPushButton:hover { color: #ef4444; }
        """)
        btn.clicked.connect(lambda: self.remove_requested.emit(self._path))
        row.addWidget(btn)


# ── Version panel ─────────────────────────────────────────────────────────────

class _VersionPanel(QFrame):
    changed = pyqtSignal()
    remove_requested = pyqtSignal(str)

    def __init__(self, version: PrototypeVersion, parent=None):
        super().__init__(parent)
        self._v = version
        self._build()

    def _build(self):
        self.setObjectName('version_panel')
        self.setStyleSheet("""
            QFrame#version_panel {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Panel header ─────────────────────────────────────────────
        hdr = QFrame()
        hdr.setObjectName('proto_hdr')
        hdr.setStyleSheet(f"""
            QFrame#proto_hdr {{
                background: {_HDR_BG};
                border-radius: 12px 12px 0 0;
                border-bottom: 1px solid {_BORDER};
            }}
        """)
        hdr_row = QHBoxLayout(hdr)
        hdr_row.setContentsMargins(18, 12, 14, 12)
        hdr_row.setSpacing(10)

        s_color, _ = _STATUS.get(self._v.status, ('#6b7280', '#f9fafb'))
        self._v_badge = QLabel(f'V{self._v.version_number}')
        self._v_badge.setStyleSheet(
            f'background: {s_color}; color: white; border-radius: 5px;'
            f' padding: 2px 9px; font-size: 12px; font-weight: bold;'
        )
        hdr_row.addWidget(self._v_badge)

        lbl_ver = QLabel(f'{t("proto.version")} {self._v.version_number}')
        lbl_ver.setStyleSheet(
            f'background: transparent; color: {_TEXT}; font-size: 14px; font-weight: bold;'
        )
        hdr_row.addWidget(lbl_ver)
        hdr_row.addStretch()

        btn_remove = QPushButton(t('proto.remove_version'))
        btn_remove.setCursor(Qt.PointingHandCursor)
        btn_remove.setStyleSheet("""
            QPushButton {
                background: #fff5f5; color: #dc2626;
                border: 1px solid #fecaca; border-radius: 5px;
                font-size: 11px; font-weight: 600; padding: 4px 12px;
            }
            QPushButton:hover { background: #fee2e2; }
        """)
        btn_remove.clicked.connect(lambda: self.remove_requested.emit(self._v.id))
        hdr_row.addWidget(btn_remove)
        root.addWidget(hdr)

        # ── Panel body ───────────────────────────────────────────────
        body = QWidget()
        body.setStyleSheet('background: transparent;')
        body_row = QHBoxLayout(body)
        body_row.setContentsMargins(18, 16, 18, 18)
        body_row.setSpacing(24)

        # Left column — photo + attached files
        left = QVBoxLayout()
        left.setSpacing(10)

        self._photo = _PhotoArea(self._v.image_path)
        self._photo.changed.connect(self._on_photo_changed)
        left.addWidget(self._photo)

        files_hdr = QHBoxLayout()
        lbl_files = QLabel(t('proto.attached_files'))
        lbl_files.setStyleSheet(_LBL_CSS)
        files_hdr.addWidget(lbl_files)
        files_hdr.addStretch()

        btn_attach = QPushButton(f'+ {t("proto.attach_file")}')
        btn_attach.setCursor(Qt.PointingHandCursor)
        btn_attach.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {_ACCENT};
                border: none; font-size: 11px; font-weight: 600; padding: 0;
            }}
            QPushButton:hover {{ color: {_ACCENT_H}; }}
        """)
        btn_attach.clicked.connect(self._attach_file)
        files_hdr.addWidget(btn_attach)
        left.addLayout(files_hdr)

        self._file_container = QWidget()
        self._file_container.setStyleSheet('background: transparent;')
        self._file_lay = QVBoxLayout(self._file_container)
        self._file_lay.setContentsMargins(0, 0, 0, 0)
        self._file_lay.setSpacing(4)
        left.addWidget(self._file_container)
        self._refresh_files()

        left.addStretch()
        body_row.addLayout(left, 4)

        # Right column — status, date, comments
        right = QVBoxLayout()
        right.setSpacing(6)

        # Status
        lbl_status = QLabel(t('proto.status'))
        lbl_status.setStyleSheet(_LBL_CSS)
        right.addWidget(lbl_status)

        self._status_combo = QComboBox()
        for key, val in _STATUS_KEYS:
            self._status_combo.addItem(t(key), val)
        for i in range(self._status_combo.count()):
            if self._status_combo.itemData(i) == self._v.status:
                self._status_combo.setCurrentIndex(i)
                break
        self._status_combo.currentIndexChanged.connect(self._on_status_changed)
        self._apply_status_style()
        right.addWidget(self._status_combo)

        # Date
        lbl_date = QLabel(t('proto.date'))
        lbl_date.setStyleSheet(_LBL_CSS + ' margin-top: 8px;')
        right.addWidget(lbl_date)

        self._date_edit = QLineEdit(self._v.date)
        self._date_edit.setPlaceholderText('YYYY-MM-DD')
        self._date_edit.setStyleSheet(f"""
            QLineEdit {{
                background: {_CARD}; color: {_TEXT};
                border: 1px solid {_BORDER}; border-radius: 6px;
                padding: 7px 10px; font-size: 13px;
            }}
            QLineEdit:focus {{ border-color: {_ACCENT}; }}
        """)
        self._date_edit.textChanged.connect(self._on_date_changed)
        right.addWidget(self._date_edit)

        # Comments
        lbl_comments = QLabel(t('proto.comments'))
        lbl_comments.setStyleSheet(_LBL_CSS + ' margin-top: 8px;')
        right.addWidget(lbl_comments)

        self._comments_edit = QTextEdit(self._v.comments)
        self._comments_edit.setPlaceholderText(t('proto.comments_ph'))
        self._comments_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {_CARD}; color: {_TEXT};
                border: 1px solid {_BORDER}; border-radius: 6px;
                padding: 8px; font-size: 13px;
            }}
            QTextEdit:focus {{ border-color: {_ACCENT}; }}
        """)
        self._comments_edit.setMinimumHeight(120)
        self._comments_edit.textChanged.connect(self._on_comments_changed)
        right.addWidget(self._comments_edit, 1)

        body_row.addLayout(right, 6)
        root.addWidget(body)

    # ── Style helpers ─────────────────────────────────────────────────────────

    def _apply_status_style(self):
        val = self._status_combo.currentData() or 'in_progress'
        s_color, s_bg = _STATUS.get(val, ('#6b7280', '#f9fafb'))
        self._status_combo.setStyleSheet(f"""
            QComboBox {{
                background: {s_bg}; color: {s_color};
                border: 1px solid {s_color}55; border-radius: 6px;
                padding: 7px 10px; font-size: 13px; font-weight: 600;
            }}
            QComboBox::drop-down {{ border: none; padding-right: 8px; }}
            QComboBox QAbstractItemView {{
                background: white; color: {_TEXT};
                border: 1px solid {_BORDER}; border-radius: 4px;
                selection-background-color: {s_color}; selection-color: white;
                font-size: 13px;
            }}
        """)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_photo_changed(self, path: str):
        self._v.image_path = path
        self.changed.emit()

    def _on_status_changed(self):
        self._v.status = self._status_combo.currentData() or 'in_progress'
        s_color, _ = _STATUS.get(self._v.status, ('#6b7280', '#f9fafb'))
        self._v_badge.setStyleSheet(
            f'background: {s_color}; color: white; border-radius: 5px;'
            f' padding: 2px 9px; font-size: 12px; font-weight: bold;'
        )
        self._apply_status_style()
        self.changed.emit()

    def _on_date_changed(self):
        self._v.date = self._date_edit.text().strip()
        self.changed.emit()

    def _on_comments_changed(self):
        self._v.comments = self._comments_edit.toPlainText()
        self.changed.emit()

    def _attach_file(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, t('proto.select_files'), '', 'All Files (*.*)'
        )
        for p in paths:
            if p and p not in self._v.file_paths:
                self._v.file_paths.append(p)
        self._refresh_files()
        self.changed.emit()

    def _remove_file(self, path: str):
        if path in self._v.file_paths:
            self._v.file_paths.remove(path)
        self._refresh_files()
        self.changed.emit()

    def _refresh_files(self):
        while self._file_lay.count():
            item = self._file_lay.takeAt(0)
            if w := item.widget():
                w.setParent(None)

        if self._v.file_paths:
            for p in self._v.file_paths:
                chip = _FileChip(p)
                chip.remove_requested.connect(self._remove_file)
                self._file_lay.addWidget(chip)
        else:
            lbl = QLabel(t('proto.no_files'))
            lbl.setStyleSheet(f'color: {_MUTED}; font-size: 11px;')
            self._file_lay.addWidget(lbl)


# ── Main widget ───────────────────────────────────────────────────────────────

class PrototypeWidget(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._versions: List[PrototypeVersion] = []
        self._next_number = 1
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(12)

        # Header
        hdr_row = QHBoxLayout()
        lbl_title = QLabel(t('proto.title'))
        lbl_title.setStyleSheet(
            f'color: {_TEXT}; font-size: 22px; font-weight: bold; letter-spacing: 0.3px;'
        )
        hdr_row.addWidget(lbl_title)
        hdr_row.addStretch()

        btn_add = QPushButton(f'+ {t("proto.add_version")}')
        btn_add.setCursor(Qt.PointingHandCursor)
        btn_add.setStyleSheet(f"""
            QPushButton {{
                background: {_ACCENT}; color: white; border: none;
                border-radius: 6px; padding: 7px 16px;
                font-size: 13px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {_ACCENT_H}; }}
        """)
        btn_add.clicked.connect(self._add_version)
        hdr_row.addWidget(btn_add)
        root.addLayout(hdr_row)

        lbl_sub = QLabel(t('proto.subtitle'))
        lbl_sub.setStyleSheet(f'color: {_MUTED}; font-size: 13px;')
        root.addWidget(lbl_sub)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setMaximumHeight(1)
        sep.setStyleSheet(f'background: {_BORDER}; border: none;')
        root.addWidget(sep)

        # Scroll area for version panels
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet('background: transparent; border: none;')
        scroll.viewport().setStyleSheet('background: transparent;')

        self._container = QWidget()
        self._container.setStyleSheet('background: transparent;')
        self._lay = QVBoxLayout(self._container)
        self._lay.setContentsMargins(0, 4, 4, 16)
        self._lay.setSpacing(16)

        self._empty_lbl = QLabel(t('proto.no_versions'))
        self._empty_lbl.setAlignment(Qt.AlignCenter)
        self._empty_lbl.setWordWrap(True)
        self._empty_lbl.setStyleSheet(
            f'color: {_MUTED}; font-size: 14px; padding: 60px;'
        )
        self._lay.addWidget(self._empty_lbl)
        self._lay.addStretch()

        scroll.setWidget(self._container)
        root.addWidget(scroll, 1)

    # ── Version management ────────────────────────────────────────────────────

    def _add_version(self):
        v = PrototypeVersion(
            id=str(uuid.uuid4()),
            version_number=self._next_number,
        )
        self._versions.append(v)
        self._next_number += 1
        self._rebuild()
        self.changed.emit()

    def _remove_version(self, vid: str):
        self._versions = [v for v in self._versions if v.id != vid]
        self._rebuild()
        self.changed.emit()

    def _rebuild(self):
        while self._lay.count():
            item = self._lay.takeAt(0)
            if w := item.widget():
                if w is not self._empty_lbl:
                    w.setParent(None)

        if not self._versions:
            self._lay.addWidget(self._empty_lbl)
            self._empty_lbl.show()
        else:
            self._empty_lbl.hide()
            for v in self._versions:
                panel = _VersionPanel(v)
                panel.changed.connect(self.changed.emit)
                panel.remove_requested.connect(self._remove_version)
                self._lay.addWidget(panel)

        self._lay.addStretch()

    # ── Persistence ───────────────────────────────────────────────────────────

    def get_data(self) -> dict:
        return {
            'versions': [asdict(v) for v in self._versions],
            'next_number': self._next_number,
        }

    def set_data(self, data: dict):
        self._versions = []
        for d in data.get('versions', []):
            try:
                v = PrototypeVersion(**d)
                self._versions.append(v)
            except TypeError:
                pass
        self._next_number = data.get('next_number', len(self._versions) + 1)
        self._rebuild()

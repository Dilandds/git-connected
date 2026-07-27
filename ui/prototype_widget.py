"""
Prototype tab — manage prototype versions with photos, files, status and comments.
"""
import uuid
import os
from dataclasses import dataclass, field, asdict
from typing import List

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QComboBox, QTextEdit, QFileDialog,
    QSizePolicy, QLineEdit, QStackedWidget,
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QPixmap

from ui.styles import default_theme
from i18n import t

# ── Theme ─────────────────────────────────────────────────────────────────────
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

_THUMB_W = 150
_THUMB_H = 120


# ── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class PrototypeVersion:
    id: str
    version_number: int
    date: str = ''
    status: str = 'in_progress'
    comments: str = ''
    image_paths: List[str] = field(default_factory=list)
    file_paths: List[str] = field(default_factory=list)


# ── Main photo area ────────────────────────────────────────────────────────────

class _MainPhotoArea(QFrame):
    """Large clickable main photo area."""
    changed = pyqtSignal(str)

    def __init__(self, path: str = '', parent=None):
        super().__init__(parent)
        self._path = path
        self._build()

    def _build(self):
        self.setMinimumHeight(380)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet(f"""
            QFrame {{
                background: #f8fafc;
                border: 2px dashed {_BORDER};
                border-radius: 12px;
            }}
            QFrame:hover {{
                border-color: {_ACCENT};
                background: #eff6ff;
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(8)

        self._icon_lbl = QLabel('📷')
        self._icon_lbl.setAlignment(Qt.AlignCenter)
        self._icon_lbl.setStyleSheet('background: transparent; font-size: 48px; border: none;')
        lay.addWidget(self._icon_lbl)

        self._img_lbl = QLabel()
        self._img_lbl.setAlignment(Qt.AlignCenter)
        self._img_lbl.setStyleSheet('background: transparent; border: none;')
        self._img_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay.addWidget(self._img_lbl, 1)

        self._hint_lbl = QLabel()
        self._hint_lbl.setAlignment(Qt.AlignCenter)
        self._hint_lbl.setStyleSheet(
            f'background: transparent; color: {_MUTED}; font-size: 13px; border: none;'
        )
        lay.addWidget(self._hint_lbl)

        self._refresh()

    def _refresh(self):
        has_img = bool(self._path and os.path.exists(self._path))
        if has_img:
            pix = QPixmap(self._path).scaled(
                max(self.width() - 32, 300), max(self.height() - 60, 300),
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
            self._img_lbl.setPixmap(pix)
            self._icon_lbl.hide()
            self._hint_lbl.setText(t('proto.click_to_change'))
        else:
            self._img_lbl.clear()
            self._icon_lbl.show()
            self._hint_lbl.setText(t('proto.click_to_add_photo'))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh()

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


# ── Thumbnail photo slot ───────────────────────────────────────────────────────

class _ThumbPhoto(QFrame):
    """Small clickable photo thumbnail for the gallery row."""
    changed = pyqtSignal(int, str)       # index, path
    remove_requested = pyqtSignal(int)   # index

    def __init__(self, index: int, path: str = '', parent=None):
        super().__init__(parent)
        self._index = index
        self._path = path
        self._build()

    def _build(self):
        self.setFixedSize(_THUMB_W, _THUMB_H)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
            QFrame {{
                background: #f8fafc;
                border: 2px dashed {_BORDER};
                border-radius: 8px;
            }}
            QFrame:hover {{
                border-color: {_ACCENT};
                background: #eff6ff;
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(4)

        # Remove button (top-right corner overlay) — must be parented to self,
        # otherwise it's a parentless top-level widget: .move()/.show() then
        # position and pop an independent floating OS window at absolute
        # screen coordinates instead of overlaying this thumbnail, visually
        # landing on top of (and obscuring) whatever's underneath — including
        # a just-uploaded photo, which then looks like it got deleted.
        self._remove_btn = QPushButton('×', self)
        self._remove_btn.setFixedSize(18, 18)
        self._remove_btn.setCursor(Qt.PointingHandCursor)
        self._remove_btn.hide()
        self._remove_btn.setStyleSheet("""
            QPushButton {
                background: #ef4444; color: white; border: none;
                border-radius: 9px; font-size: 12px; font-weight: bold; padding: 0;
            }
            QPushButton:hover { background: #dc2626; }
        """)
        self._remove_btn.clicked.connect(lambda: self.remove_requested.emit(self._index))

        self._icon_lbl = QLabel('📷')
        self._icon_lbl.setAlignment(Qt.AlignCenter)
        self._icon_lbl.setStyleSheet('background: transparent; font-size: 22px; border: none;')
        lay.addWidget(self._icon_lbl)

        self._img_lbl = QLabel()
        self._img_lbl.setAlignment(Qt.AlignCenter)
        self._img_lbl.setStyleSheet('background: transparent; border: none;')
        self._img_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay.addWidget(self._img_lbl, 1)

        self._hint_lbl = QLabel(t('proto.click_to_add_photo'))
        self._hint_lbl.setAlignment(Qt.AlignCenter)
        self._hint_lbl.setWordWrap(True)
        self._hint_lbl.setStyleSheet(
            f'background: transparent; color: {_MUTED}; font-size: 10px; border: none;'
        )
        lay.addWidget(self._hint_lbl)

        self._refresh()

    def _refresh(self):
        has_img = bool(self._path and os.path.exists(self._path))
        if has_img:
            pix = QPixmap(self._path).scaled(
                _THUMB_W - 8, _THUMB_H - 8,
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
            self._img_lbl.setPixmap(pix)
            self._icon_lbl.hide()
            self._hint_lbl.hide()
            self._remove_btn.show()
        else:
            self._img_lbl.clear()
            self._icon_lbl.show()
            self._hint_lbl.show()
            self._remove_btn.hide()

    def set_path(self, path: str):
        self._path = path
        self._refresh()

    def get_path(self) -> str:
        return self._path

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Position remove button at top-right
        self._remove_btn.move(self.width() - 22, 4)
        self._remove_btn.raise_()

    def showEvent(self, event):
        super().showEvent(event)
        self._remove_btn.move(self.width() - 22, 4)
        self._remove_btn.raise_()

    def mousePressEvent(self, _event):
        path, _ = QFileDialog.getOpenFileName(
            self, t('proto.select_photo'), '',
            'Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tiff)',
        )
        if path:
            self._path = path
            self._refresh()
            self.changed.emit(self._index, path)


# ── File chip ──────────────────────────────────────────────────────────────────

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


# ── Version panel ──────────────────────────────────────────────────────────────

class _VersionPanel(QFrame):
    changed = pyqtSignal()
    remove_requested = pyqtSignal(str)   # emits version id

    def __init__(self, version: PrototypeVersion, parent=None):
        super().__init__(parent)
        self._v = version
        self._thumb_widgets: List[_ThumbPhoto] = []
        self._build()

    def _build(self):
        self.setObjectName('version_panel')
        self.setStyleSheet("""
            QFrame#version_panel {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 0 12px 12px 12px;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 20)
        root.setSpacing(16)

        # ── Panel header: badge + name + Remove Version ───────────────
        panel_hdr = QHBoxLayout()
        panel_hdr.setSpacing(10)

        badge = QLabel(f'V{self._v.version_number}')
        badge.setFixedSize(32, 22)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(f"""
            QLabel {{
                background: {_ACCENT}; color: #ffffff;
                border-radius: 6px; font-size: 11px; font-weight: bold;
            }}
        """)
        panel_hdr.addWidget(badge)

        name_lbl = QLabel(f'{t("proto.version")} {self._v.version_number}')
        name_lbl.setStyleSheet(f'color: {_TEXT}; font-size: 14px; font-weight: 600;')
        panel_hdr.addWidget(name_lbl)
        panel_hdr.addStretch()

        btn_remove = QPushButton(t('proto.remove_version'))
        btn_remove.setCursor(Qt.PointingHandCursor)
        btn_remove.setFixedHeight(26)
        btn_remove.setStyleSheet(f"""
            QPushButton {{
                background: #f1f5f9; color: {_MUTED};
                border: 1px solid {_BORDER}; border-radius: 5px;
                font-size: 12px; padding: 0 12px;
            }}
            QPushButton:hover {{ background: #fee2e2; color: #ef4444; border-color: #fca5a5; }}
        """)
        btn_remove.clicked.connect(lambda: self.remove_requested.emit(self._v.id))
        panel_hdr.addWidget(btn_remove)

        root.addLayout(panel_hdr)

        # Thin separator under header
        hdr_sep = QFrame()
        hdr_sep.setFixedHeight(1)
        hdr_sep.setStyleSheet(f'background: {_BORDER}; border: none;')
        root.addWidget(hdr_sep)

        # ── Main content row ──────────────────────────────────────────
        content_row = QHBoxLayout()
        content_row.setSpacing(24)

        # Left column — large photo + gallery + files
        left = QVBoxLayout()
        left.setSpacing(12)

        self._main_photo = _MainPhotoArea(
            self._v.image_paths[0] if self._v.image_paths else ''
        )
        self._main_photo.changed.connect(self._on_main_photo_changed)
        left.addWidget(self._main_photo, 1)

        # Gallery row label + add button
        gallery_hdr = QHBoxLayout()
        lbl_views = QLabel('PHOTO VIEWS')
        lbl_views.setStyleSheet(_LBL_CSS)
        gallery_hdr.addWidget(lbl_views)
        gallery_hdr.addStretch()

        btn_add_photo = QPushButton(f'+ {t("proto.click_to_add_photo").replace("Click to add a ", "Add ")}')
        btn_add_photo.setToolTip('Add another photo view')
        btn_add_photo.setCursor(Qt.PointingHandCursor)
        btn_add_photo.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {_ACCENT};
                border: none; font-size: 11px; font-weight: 600; padding: 0;
            }}
            QPushButton:hover {{ color: {_ACCENT_H}; }}
        """)
        btn_add_photo.clicked.connect(self._add_photo_slot)
        gallery_hdr.addWidget(btn_add_photo)
        left.addLayout(gallery_hdr)

        # Gallery scroll area
        gallery_scroll = QScrollArea()
        gallery_scroll.setFixedHeight(_THUMB_H + 20)
        gallery_scroll.setWidgetResizable(True)
        gallery_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        gallery_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        gallery_scroll.setFrameShape(QFrame.NoFrame)
        gallery_scroll.setStyleSheet('background: transparent; border: none;')

        self._gallery_widget = QWidget()
        self._gallery_widget.setStyleSheet('background: transparent;')
        self._gallery_lay = QHBoxLayout(self._gallery_widget)
        self._gallery_lay.setContentsMargins(0, 4, 0, 4)
        self._gallery_lay.setSpacing(10)
        self._gallery_lay.addStretch()

        gallery_scroll.setWidget(self._gallery_widget)
        left.addWidget(gallery_scroll)

        # Attached files
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

        content_row.addLayout(left, 6)

        # Right column — status, date, comments
        right = QVBoxLayout()
        right.setSpacing(6)

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
        self._comments_edit.setMinimumHeight(150)
        self._comments_edit.textChanged.connect(self._on_comments_changed)
        right.addWidget(self._comments_edit, 1)

        right.addStretch()
        content_row.addLayout(right, 4)
        root.addLayout(content_row, 1)

        # Populate existing gallery photos (index 1+)
        for i, path in enumerate(self._v.image_paths[1:], start=1):
            self._add_thumb(i, path)

    # ── Helpers ──────────────────────────────────────────────────────────────

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

    def _add_thumb(self, index: int, path: str = ''):
        thumb = _ThumbPhoto(index, path)
        thumb.changed.connect(self._on_thumb_changed)
        thumb.remove_requested.connect(self._on_thumb_removed)
        self._thumb_widgets.append(thumb)
        # Insert before the stretch
        pos = self._gallery_lay.count() - 1
        self._gallery_lay.insertWidget(pos, thumb)

    def _add_photo_slot(self):
        index = len(self._v.image_paths)
        self._v.image_paths.append('')
        self._add_thumb(index, '')
        self.changed.emit()

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_main_photo_changed(self, path: str):
        if self._v.image_paths:
            self._v.image_paths[0] = path
        else:
            self._v.image_paths.append(path)
        self.changed.emit()

    def _on_thumb_changed(self, index: int, path: str):
        while len(self._v.image_paths) <= index:
            self._v.image_paths.append('')
        self._v.image_paths[index] = path
        self.changed.emit()

    def _on_thumb_removed(self, index: int):
        # Remove from data
        if 0 < index < len(self._v.image_paths):
            self._v.image_paths.pop(index)

        # Remove from UI
        widget_to_remove = None
        for w in self._thumb_widgets:
            if w._index == index:
                widget_to_remove = w
                break
        if widget_to_remove:
            self._thumb_widgets.remove(widget_to_remove)
            widget_to_remove.setParent(None)

        # Re-index remaining thumbs
        for i, w in enumerate(self._thumb_widgets):
            w._index = i + 1

        self.changed.emit()

    def _on_status_changed(self):
        self._v.status = self._status_combo.currentData() or 'in_progress'
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


# ── Tab button ─────────────────────────────────────────────────────────────────

class _VersionTabBtn(QWidget):
    """A single tab button: label only (no × — remove is done via the panel header)."""
    clicked = pyqtSignal(str)

    def __init__(self, version_id: str, label: str, active: bool = False, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._id = version_id
        self._label = label
        self._active = active
        self._build()
        self._apply_style()

    def _build(self):
        self.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.setSpacing(0)

        self._lbl = QLabel(self._label)
        self._lbl.setStyleSheet('background: transparent; border: none; font-size: 13px; font-weight: 600;')
        lay.addWidget(self._lbl)

    def _apply_style(self):
        if self._active:
            bg = _ACCENT
            fg = '#ffffff'
            border = f'border: 1px solid {_ACCENT}; border-bottom: none;'
        else:
            bg = '#e9eef5'
            fg = '#374151'
            border = f'border: 1px solid {_BORDER}; border-bottom: none;'

        self.setStyleSheet(f"""
            QWidget {{
                background: {bg};
                {border}
                border-radius: 8px 8px 0 0;
            }}
        """)
        self._lbl.setStyleSheet(
            f'background: transparent; border: none; color: {fg};'
            f' font-size: 13px; font-weight: 600;'
        )

    def set_active(self, active: bool):
        self._active = active
        self._apply_style()

    def mousePressEvent(self, _event):
        self.clicked.emit(self._id)


# ── Main widget ────────────────────────────────────────────────────────────────

class PrototypeWidget(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._versions: List[PrototypeVersion] = []
        self._next_number = 1
        self._active_id: str = ''
        self._tab_buttons: dict = {}   # id -> _VersionTabBtn
        self._panels: dict = {}        # id -> _VersionPanel
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────
        hdr_row = QHBoxLayout()
        hdr_row.setContentsMargins(0, 0, 0, 10)
        lbl_title = QLabel(t('proto.title'))
        lbl_title.setStyleSheet(
            f'color: {_TEXT}; font-size: 22px; font-weight: bold; letter-spacing: 0.3px;'
        )
        hdr_row.addWidget(lbl_title)

        lbl_sub = QLabel(f'  —  {t("proto.subtitle")}')
        lbl_sub.setStyleSheet(f'color: {_MUTED}; font-size: 13px;')
        hdr_row.addWidget(lbl_sub)
        hdr_row.addStretch()
        root.addLayout(hdr_row)

        # ── Tab bar row ───────────────────────────────────────────────
        tab_row = QHBoxLayout()
        tab_row.setContentsMargins(0, 0, 0, 0)
        tab_row.setSpacing(4)

        self._tab_scroll = QScrollArea()
        self._tab_scroll.setFixedHeight(44)
        self._tab_scroll.setWidgetResizable(True)
        self._tab_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._tab_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._tab_scroll.setFrameShape(QFrame.NoFrame)
        self._tab_scroll.setStyleSheet('background: transparent; border: none;')

        self._tab_container = QWidget()
        self._tab_container.setStyleSheet('background: transparent;')
        self._tab_lay = QHBoxLayout(self._tab_container)
        self._tab_lay.setContentsMargins(0, 0, 0, 0)
        self._tab_lay.setSpacing(4)
        self._tab_lay.addStretch()
        self._tab_scroll.setWidget(self._tab_container)
        tab_row.addWidget(self._tab_scroll, 1)

        btn_add = QPushButton(f'+ {t("proto.add_version")}')
        btn_add.setCursor(Qt.PointingHandCursor)
        btn_add.setFixedHeight(34)
        btn_add.setStyleSheet(f"""
            QPushButton {{
                background: {_ACCENT}; color: white; border: none;
                border-radius: 6px; padding: 0 16px;
                font-size: 13px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {_ACCENT_H}; }}
        """)
        btn_add.clicked.connect(self._add_version)
        tab_row.addWidget(btn_add)
        root.addLayout(tab_row)

        # ── Separator under tabs ──────────────────────────────────────
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f'background: {_BORDER}; border: none;')
        root.addWidget(sep)

        # ── Stacked content area ──────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet('background: transparent; border: none;')
        scroll.viewport().setStyleSheet('background: transparent;')

        self._stack_container = QWidget()
        self._stack_container.setStyleSheet('background: transparent;')
        self._stack_lay = QVBoxLayout(self._stack_container)
        self._stack_lay.setContentsMargins(0, 16, 0, 16)
        self._stack_lay.setSpacing(0)

        self._empty_lbl = QLabel(t('proto.no_versions'))
        self._empty_lbl.setAlignment(Qt.AlignCenter)
        self._empty_lbl.setWordWrap(True)
        self._empty_lbl.setStyleSheet(
            f'color: {_MUTED}; font-size: 14px; padding: 80px;'
        )
        self._stack_lay.addWidget(self._empty_lbl)
        self._stack_lay.addStretch()

        scroll.setWidget(self._stack_container)
        root.addWidget(scroll, 1)

    # ── Version management ─────────────────────────────────────────────────────

    def _add_version(self):
        v = PrototypeVersion(
            id=str(uuid.uuid4()),
            version_number=self._next_number,
        )
        self._versions.append(v)
        self._next_number += 1
        self._create_tab(v)
        self._create_panel(v)
        self._switch_to(v.id)
        self.changed.emit()

    def _remove_version(self, vid: str):
        # Remove data
        self._versions = [v for v in self._versions if v.id != vid]

        # Remove tab
        if tab := self._tab_buttons.pop(vid, None):
            tab.setParent(None)

        # Remove panel
        if panel := self._panels.pop(vid, None):
            panel.setParent(None)

        # Switch to last available version
        if self._active_id == vid:
            self._active_id = ''
            if self._versions:
                self._switch_to(self._versions[-1].id)
            else:
                self._show_empty()

        self.changed.emit()

    def _create_tab(self, v: PrototypeVersion):
        label = f'{t("proto.version")} {v.version_number}'
        tab = _VersionTabBtn(v.id, label, active=False)
        tab.clicked.connect(self._switch_to)
        self._tab_buttons[v.id] = tab

        # Insert before the stretch
        pos = self._tab_lay.count() - 1
        self._tab_lay.insertWidget(pos, tab)

    def _create_panel(self, v: PrototypeVersion):
        panel = _VersionPanel(v)
        panel.changed.connect(self.changed.emit)
        panel.remove_requested.connect(self._remove_version)
        panel.hide()
        self._panels[v.id] = panel
        self._stack_lay.insertWidget(self._stack_lay.count() - 1, panel)

    def _switch_to(self, vid: str):
        # Deactivate current
        if self._active_id and self._active_id in self._tab_buttons:
            self._tab_buttons[self._active_id].set_active(False)
        if self._active_id and self._active_id in self._panels:
            self._panels[self._active_id].hide()

        self._active_id = vid

        if vid in self._tab_buttons:
            self._tab_buttons[vid].set_active(True)
        if vid in self._panels:
            self._panels[vid].show()
            self._empty_lbl.hide()

    def _show_empty(self):
        self._empty_lbl.show()

    # ── Persistence ────────────────────────────────────────────────────────────

    def get_data(self) -> dict:
        return {
            'versions': [asdict(v) for v in self._versions],
            'next_number': self._next_number,
        }

    def set_data(self, data: dict):
        # Clear existing
        for tab in self._tab_buttons.values():
            tab.setParent(None)
        for panel in self._panels.values():
            panel.setParent(None)
        self._tab_buttons.clear()
        self._panels.clear()
        self._active_id = ''
        self._versions = []

        for d in data.get('versions', []):
            try:
                # Migrate legacy single image_path -> image_paths
                if 'image_path' in d and d['image_path'] and 'image_paths' not in d:
                    d = dict(d)
                    d['image_paths'] = [d.pop('image_path')]
                elif 'image_path' in d:
                    d = {k: v for k, v in d.items() if k != 'image_path'}

                v = PrototypeVersion(**d)
                self._versions.append(v)
            except TypeError:
                pass

        self._next_number = data.get('next_number', len(self._versions) + 1)

        if self._versions:
            for v in self._versions:
                self._create_tab(v)
                self._create_panel(v)
            self._switch_to(self._versions[-1].id)
        else:
            self._show_empty()

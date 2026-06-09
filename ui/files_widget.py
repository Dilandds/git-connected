"""
Files & Versions screen — folder tree, versioned file list, search/filter,
status management, bulk download, trash, and 3D viewer launch.
"""
import logging
import os
import zipfile
import tempfile
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QLineEdit, QSizePolicy, QFileDialog,
    QMenu, QAction, QDialog, QComboBox,
    QStackedWidget, QApplication, QAbstractItemView,
)
from ui.modal_utils import FormModal, BaseModal
from PyQt5.QtCore import Qt, pyqtSignal, QSize, QPoint
from PyQt5.QtGui import QColor, QPainter, QBrush, QPen, QFont, QPixmap, QIcon, QCursor

from ui.styles import default_theme, make_font, dropdown_arrow_url as _get_arrow, TOOLTIP_STYLE
from ui.modal_utils import ask_yes_no_dialog, ask_text_input_dialog, show_message_dialog

logger = logging.getLogger(__name__)
_ARROW_URL = _get_arrow()

# ── palette ───────────────────────────────────────────────────────────────────
_BG      = '#f8f9fa'
_CARD    = '#ffffff'
_BORDER  = '#e5e7eb'
_TEXT    = '#1e2430'
_MUTED   = '#6b7280'
_ACCENT  = default_theme.button_primary
_ACCENT_H = default_theme.button_primary_hover
_SIDEBAR = '#f1f3f5'

_STATUS_COLORS = {
    "Approved":   "#22c55e",
    "In review":  "#f59e0b",
    "In progress":"#3b82f6",
}
_EXT_COLORS = {
    '.stl':  '#3b82f6', '.step': '#8b5cf6', '.stp': '#8b5cf6',
    '.3dm':  '#06b6d4', '.obj':  '#10b981', '.dxf': '#f97316',
    '.iges': '#14b8a6', '.igs':  '#14b8a6',
    '.pdf':  '#ef4444',
    '.jpg':  '#6b7280', '.jpeg': '#6b7280', '.png': '#6b7280', '.heic': '#6b7280',
}
_3D_EXTS = {'.stl', '.step', '.stp', '.3dm', '.obj', '.dxf', '.iges', '.igs'}

# ── styles ────────────────────────────────────────────────────────────────────
_INPUT = f"""
    QLineEdit, QComboBox {{
        background: {_CARD}; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 4px;
        padding: 3px 8px; font-size: 14px;
    }}
    QLineEdit:focus {{ border-color: {_ACCENT}; }}
    QComboBox::drop-down {{ border: none; width: 18px; }}
    QComboBox::down-arrow {{ image: url({_ARROW_URL}); width: 9px; height: 9px; }}
    QComboBox QAbstractItemView {{
        background: {_CARD}; color: {_TEXT}; border: 1px solid {_BORDER};
        selection-background-color: {_ACCENT}; selection-color: white;
    }}
"""
_BTN_PRIMARY = f"""
    QPushButton {{
        background: {_ACCENT}; color: white; border: none;
        border-radius: 5px; padding: 5px 14px; font-size: 15px; font-weight: bold;
    }}
    QPushButton:hover {{ background: {_ACCENT_H}; }}
"""
_BTN_SMALL = f"""
    QPushButton {{
        background: {_CARD}; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 4px;
        padding: 4px 10px; font-size: 14px;
    }}
    QPushButton:hover {{ background: #f1f3f5; border-color: {_ACCENT}; color: {_ACCENT}; }}
"""
_BTN_ICON = f"""
    QPushButton {{
        background: transparent; border: none;
        color: {_MUTED}; font-size: 16px; padding: 2px 5px;
    }}
    QPushButton:hover {{ color: {_ACCENT}; background: #e8f0fe; border-radius: 4px; }}
""" + TOOLTIP_STYLE
_FOLDER_ITEM_ACTIVE = f"""
    QPushButton {{
        background: {_ACCENT}22; color: {_ACCENT};
        border: none; border-radius: 4px;
        text-align: left; padding: 5px 8px; font-size: 14px; font-weight: bold;
    }}
"""
_FOLDER_ITEM = f"""
    QPushButton {{
        background: transparent; color: {_TEXT};
        border: none; border-radius: 4px;
        text-align: left; padding: 5px 8px; font-size: 14px;
    }}
    QPushButton:hover {{ background: #e5e7eb; }}
"""


# ── data model ────────────────────────────────────────────────────────────────

@dataclass
class FileVersion:
    version_str: str       # "v1.0", "v1.1", etc.
    file_path:   str       # full path on disk
    uploaded_at: str       # "dd/MM/yyyy HH:mm"
    size_bytes:  int = 0


@dataclass
class ProjectFile:
    id:        int
    name:      str         # display name (renameable)
    folder_id: int
    status:    str         = "In progress"
    trashed:   bool        = False
    versions:  List[FileVersion] = field(default_factory=list)

    @property
    def extension(self) -> str:
        if self.versions:
            return Path(self.versions[-1].file_path).suffix.lower()
        return ""

    @property
    def latest_version(self) -> Optional[FileVersion]:
        return self.versions[-1] if self.versions else None

    def next_version_str(self) -> str:
        if not self.versions:
            return "v1.0"
        last = self.versions[-1].version_str
        try:
            parts = last.lstrip("v").split(".")
            minor = int(parts[1]) + 1
            return f"v{parts[0]}.{minor}"
        except Exception:
            return f"v1.{len(self.versions)}"


@dataclass
class Folder:
    id:        int
    name:      str
    parent_id: Optional[int] = None
    is_trash:  bool = False


def _fmt_size(b: int) -> str:
    if b <= 0:     return "—"
    if b < 1024:   return f"{b} B"
    if b < 1<<20:  return f"{b/1024:.1f} KB"
    if b < 1<<30:  return f"{b/(1<<20):.1f} MB"
    return f"{b/(1<<30):.1f} GB"


def _fmt_date(s: str) -> str:
    try:
        dt = datetime.strptime(s, "%d/%m/%Y %H:%M")
        return dt.strftime("%b %d, %Y\n%H:%M")
    except Exception:
        return s


# ── Extension thumbnail ───────────────────────────────────────────────────────

class _ExtThumb(QWidget):
    """Colored block with extension text — lightweight thumbnail placeholder."""

    def __init__(self, ext: str, w=40, h=40, parent=None):
        super().__init__(parent)
        self._color = QColor(_EXT_COLORS.get(ext, '#9ca3af'))
        self._text  = ext.lstrip('.').upper()
        self.setFixedSize(w, h)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QBrush(self._color))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(self.rect(), 4, 4)
        p.setPen(QColor("white"))
        f = QFont("Arial", max(6, self.width() // 4), QFont.Bold)
        p.setFont(f)
        p.drawText(self.rect(), Qt.AlignCenter, self._text)
        p.end()


# ── Status / Version badges ───────────────────────────────────────────────────

def _status_chip(status: str) -> QLabel:
    color = _STATUS_COLORS.get(status, _MUTED)
    l = QLabel(status)
    l.setStyleSheet(f"""
        QLabel {{
            background: {color}22; color: {color};
            border: 1px solid {color}66; border-radius: 4px;
            padding: 1px 8px; font-size: 16px; font-weight: bold;
        }}
    """)
    l.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    return l


def _version_chip(ver: str) -> QLabel:
    l = QLabel(ver)
    l.setStyleSheet(f"""
        QLabel {{
            background: {_ACCENT}22; color: {_ACCENT};
            border: 1px solid {_ACCENT}55; border-radius: 4px;
            padding: 1px 8px; font-size: 16px; font-weight: bold;
        }}
    """)
    return l


# ── File row (list view) ──────────────────────────────────────────────────────

class _FileRow(QFrame):
    open_viewer    = pyqtSignal(str)    # emits file path
    upload_version = pyqtSignal(object) # emits ProjectFile
    rename         = pyqtSignal(object)
    move           = pyqtSignal(object)
    trash          = pyqtSignal(object)
    restore        = pyqtSignal(object)
    delete_perm    = pyqtSignal(object)
    status_changed = pyqtSignal(object, str)

    def __init__(self, pf: ProjectFile, in_trash: bool = False, parent=None):
        super().__init__(parent)
        self._pf       = pf
        self._in_trash = in_trash
        self.setStyleSheet(f"""
            QFrame {{ background: {_CARD}; border: none;
                      border-bottom: 1px solid {_BORDER}; }}
            QFrame:hover {{ background: #f9fafb; }}
        """)
        self._build()

    def _build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 8, 10, 8)
        lay.setSpacing(12)

        # Thumbnail
        thumb = _ExtThumb(self._pf.extension, 36, 36)
        lay.addWidget(thumb)

        # Name + extension
        name_col = QVBoxLayout(); name_col.setSpacing(1)
        nl = QLabel(self._pf.name)
        nl.setStyleSheet(f"color: {_TEXT}; font-size: 15px; font-weight: bold; background: transparent; border: none;")
        el = QLabel(self._pf.extension)
        el.setStyleSheet(f"color: {_MUTED}; font-size: 16px; background: transparent; border: none;")
        name_col.addWidget(nl)
        name_col.addWidget(el)
        lay.addLayout(name_col, 2)

        # Latest version
        lv = self._pf.latest_version
        if lv:
            lay.addWidget(_version_chip(lv.version_str))
        else:
            lay.addWidget(QLabel("—"))

        # Updated date
        date_str = lv.uploaded_at if lv else "—"
        dl = QLabel(_fmt_date(date_str))
        dl.setAlignment(Qt.AlignCenter)
        dl.setStyleSheet(f"color: {_MUTED}; font-size: 16px; background: transparent; border: none;")
        lay.addWidget(dl, 1)

        # Status
        lay.addWidget(_status_chip(self._pf.status))

        # Size
        size_bytes = lv.size_bytes if lv else 0
        sl = QLabel(_fmt_size(size_bytes))
        sl.setFixedWidth(58)
        sl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        sl.setStyleSheet(f"color: {_MUTED}; font-size: 14px; background: transparent; border: none;")
        lay.addWidget(sl)

        # Actions
        dl_btn = QPushButton("↓")
        dl_btn.setFixedSize(26, 26)
        dl_btn.setToolTip("Download latest version")
        dl_btn.setStyleSheet(_BTN_ICON)
        dl_btn.setCursor(Qt.PointingHandCursor)
        dl_btn.clicked.connect(self._download)

        more_btn = QPushButton("⋮")
        more_btn.setFixedSize(26, 26)
        more_btn.setToolTip("More actions")
        more_btn.setStyleSheet(_BTN_ICON)
        more_btn.setCursor(Qt.PointingHandCursor)
        more_btn.clicked.connect(self._show_menu)

        lay.addWidget(dl_btn)
        lay.addWidget(more_btn)

    def _download(self):
        lv = self._pf.latest_version
        if not lv or not os.path.exists(lv.file_path):
            show_message_dialog(self, "File Not Found",
                                "The file could not be found on disk.")
            return
        dest, _ = QFileDialog.getSaveFileName(
            self, "Save File", self._pf.name + self._pf.extension
        )
        if dest:
            import shutil
            shutil.copy2(lv.file_path, dest)

    def _show_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background: {_CARD}; color: {_TEXT}; border: 1px solid {_BORDER};
                     border-radius: 6px; padding: 4px; font-size: 15px; }}
            QMenu::item {{ padding: 6px 16px; border-radius: 4px; }}
            QMenu::item:selected {{ background: {_ACCENT}; color: white; }}
        """)

        if self._in_trash:
            menu.addAction("↩  Restore").triggered.connect(lambda: self.restore.emit(self._pf))
            menu.addSeparator()
            menu.addAction("🗑  Delete permanently").triggered.connect(lambda: self.delete_perm.emit(self._pf))
        else:
            ext = self._pf.extension
            if ext in _3D_EXTS:
                lv = self._pf.latest_version
                if lv:
                    menu.addAction("📐  Open in 3D Viewer").triggered.connect(
                        lambda: self.open_viewer.emit(lv.file_path)
                    )
                    menu.addSeparator()

            menu.addAction("↑  Upload new version").triggered.connect(
                lambda: self.upload_version.emit(self._pf)
            )
            menu.addAction("🕐  Version history").triggered.connect(self._show_history)
            menu.addSeparator()

            status_menu = menu.addMenu("Status")
            status_menu.setStyleSheet(menu.styleSheet())
            for s in ("Approved", "In review", "In progress"):
                a = status_menu.addAction(s)
                a.triggered.connect(lambda _, st=s: self.status_changed.emit(self._pf, st))

            menu.addAction("✎  Rename").triggered.connect(lambda: self.rename.emit(self._pf))
            menu.addAction("📁  Move to folder").triggered.connect(lambda: self.move.emit(self._pf))
            menu.addSeparator()
            menu.addAction("↓  Download").triggered.connect(self._download)
            menu.addSeparator()
            menu.addAction("🗑  Move to Trash").triggered.connect(lambda: self.trash.emit(self._pf))

        menu.exec_(QCursor.pos())

    def _show_history(self):
        dlg = BaseModal(self, f"Version History — {self._pf.name}",
                        theme=BaseModal.LIGHT, min_width=420)
        lay = dlg._root
        lay.setSpacing(6)

        hdr = QLabel(f"Version history for  {self._pf.name}{self._pf.extension}")
        hdr.setStyleSheet(f"color: {_TEXT}; font-size: 15px; font-weight: bold; background: transparent; border: none;")
        lay.addWidget(hdr)

        for v in reversed(self._pf.versions):
            row = QFrame()
            row.setStyleSheet(f"QFrame {{ background: #f5f6f8; border-radius: 6px; }}")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(10, 6, 10, 6)
            vl = QLabel(v.version_str)
            vl.setStyleSheet(f"color: {_ACCENT}; font-size: 15px; font-weight: bold; background: transparent; border: none;")
            vl.setFixedWidth(40)
            dl = QLabel(v.uploaded_at)
            dl.setStyleSheet(f"color: {_MUTED}; font-size: 14px; background: transparent; border: none;")
            sl = QLabel(_fmt_size(v.size_bytes))
            sl.setStyleSheet(f"color: {_MUTED}; font-size: 14px; background: transparent; border: none;")
            rl.addWidget(vl)
            rl.addWidget(dl, 1)
            rl.addWidget(sl)
            lay.addWidget(row)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(_BTN_PRIMARY)
        close_btn.setFixedHeight(30)
        close_btn.clicked.connect(dlg.accept)
        lay.addWidget(close_btn, alignment=Qt.AlignRight)
        dlg.exec_()


# ── Folder tree ───────────────────────────────────────────────────────────────

class _FolderTree(QWidget):
    folder_selected = pyqtSignal(object)   # emits Folder or None
    folder_renamed  = pyqtSignal(object, str)
    folder_deleted  = pyqtSignal(object)
    folder_created  = pyqtSignal(object, object)  # (parent_folder_or_None, name)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._folders: List[Folder] = []
        self._selected_id: Optional[int] = None
        self.setFixedWidth(230)
        self.setStyleSheet(f"background: {_SIDEBAR};")
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hdr = QWidget()
        hdr.setFixedHeight(36)
        hdr.setStyleSheet(f"background: {_SIDEBAR}; border-bottom: 1px solid {_BORDER};")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(12, 0, 8, 0)
        lbl = QLabel("PROJECT FOLDERS")
        lbl.setStyleSheet(f"color: {_MUTED}; font-size: 16px; font-weight: bold; background: transparent; border: none;")
        add_btn = QPushButton("＋")
        add_btn.setFixedSize(22, 22)
        add_btn.setToolTip("New root folder")
        add_btn.setStyleSheet(_BTN_ICON)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(lambda: self._create_folder(None))
        hl.addWidget(lbl)
        hl.addStretch()
        hl.addWidget(add_btn)
        root.addWidget(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background: {_SIDEBAR}; border: none; }}")
        self._list = QWidget()
        self._list.setStyleSheet(f"background: {_SIDEBAR};")
        self._list_layout = QVBoxLayout(self._list)
        self._list_layout.setContentsMargins(8, 8, 8, 8)
        self._list_layout.setSpacing(2)
        self._list_layout.addStretch()
        scroll.setWidget(self._list)
        root.addWidget(scroll, 1)

    def set_folders(self, folders: List[Folder]):
        self._folders = folders
        self._rebuild()

    def _rebuild(self):
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        non_trash = [f for f in self._folders if not f.is_trash]
        trash     = [f for f in self._folders if f.is_trash]

        idx = 0
        idx = self._add_items(non_trash, None, 0, idx)

        if non_trash:
            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setStyleSheet(f"color: {_BORDER}; background: {_BORDER}; max-height: 1px; border: none; margin: 4px 0;")
            self._list_layout.insertWidget(idx, sep)
            idx += 1

        for f in trash:
            self._list_layout.insertWidget(idx, self._make_item(f, 0))
            idx += 1

    def _add_items(self, folders, parent_id, depth, idx):
        children = [f for f in folders if f.parent_id == parent_id]
        for f in children:
            self._list_layout.insertWidget(idx, self._make_item(f, depth))
            idx += 1
            idx = self._add_items(folders, f.id, depth + 1, idx)
        return idx

    def _make_item(self, folder: Folder, depth: int) -> QWidget:
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        cl = QHBoxLayout(container)
        cl.setContentsMargins(depth * 14, 0, 0, 0)
        cl.setSpacing(0)

        icon = "🗑" if folder.is_trash else "📁"
        is_active = (folder.id == self._selected_id)

        btn = QPushButton(f"{icon}  {folder.name}")
        btn.setStyleSheet(_FOLDER_ITEM_ACTIVE if is_active else _FOLDER_ITEM)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFlat(True)
        btn.clicked.connect(lambda _, f=folder: self._select(f))
        btn.setContextMenuPolicy(Qt.CustomContextMenu)
        btn.customContextMenuRequested.connect(lambda _, f=folder: self._folder_menu(f))
        cl.addWidget(btn)
        return container

    def _select(self, folder: Folder):
        self._selected_id = folder.id
        self._rebuild()
        self.folder_selected.emit(folder)

    def _folder_menu(self, folder: Folder):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background: {_CARD}; color: {_TEXT}; border: 1px solid {_BORDER};
                     border-radius: 6px; padding: 4px; font-size: 15px; }}
            QMenu::item {{ padding: 6px 16px; border-radius: 4px; }}
            QMenu::item:selected {{ background: {_ACCENT}; color: white; }}
        """)
        if not folder.is_trash:
            menu.addAction("📁  New subfolder").triggered.connect(
                lambda: self._create_folder(folder)
            )
            menu.addAction("✎  Rename").triggered.connect(
                lambda: self._rename_folder(folder)
            )
            menu.addSeparator()
            menu.addAction("🗑  Delete folder").triggered.connect(
                lambda: self.folder_deleted.emit(folder)
            )
        menu.exec_(QCursor.pos())

    def _rename_folder(self, folder: Folder):
        name, ok = ask_text_input_dialog(
            self, "Rename Folder", "Folder name", placeholder=folder.name
        )
        if ok and name:
            self.folder_renamed.emit(folder, name)

    def _create_folder(self, parent: Optional[Folder]):
        name, ok = ask_text_input_dialog(
            self, "New Folder", "Folder name", placeholder="New Folder"
        )
        if ok and name:
            self.folder_created.emit(parent, name)

    def select_none(self):
        self._selected_id = None
        self._rebuild()


# ── Column header row ─────────────────────────────────────────────────────────

class _ColHeader(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setStyleSheet(f"background: #f1f3f5; border-bottom: 1px solid {_BORDER};")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 10, 0)
        lay.setSpacing(12)

        def _h(text, stretch=0, w=None):
            l = QLabel(text)
            l.setStyleSheet(f"color: {_MUTED}; font-size: 16px; font-weight: bold; background: transparent; border: none;")
            if w:
                l.setFixedWidth(w)
            return l, stretch

        items = [
            (_h("NAME"),                2),
            (_h("LATEST VERSION"),      0),
            (_h("UPDATED",   w=110),    0),
            (_h("STATUS",    w=90),     0),
            (_h("SIZE",      w=58),     0),
            (_h("ACTIONS",   w=64),     0),
        ]
        # thumbnail spacer
        lay.addSpacing(48)
        for (lbl, _), stretch in items:
            if stretch:
                lay.addWidget(lbl, stretch)
            else:
                lay.addWidget(lbl)


# ── Main widget ───────────────────────────────────────────────────────────────

class FilesVersionsWidget(QWidget):
    """Top-level Files & Versions screen."""

    changed        = pyqtSignal()
    open_in_viewer = pyqtSignal(str)   # propagated up to main window

    def __init__(self, parent=None):
        super().__init__(parent)
        self._folders:   List[Folder]      = []
        self._files:     List[ProjectFile] = []
        self._next_folder_id = 1
        self._next_file_id   = 1
        self._selected_folder: Optional[Folder] = None
        self._search_text  = ""
        self._filter_type  = ""
        self._filter_status = ""
        self._grid_view    = False
        self.setStyleSheet(f"background: {_BG};")
        self._ensure_trash()
        self._build_ui()
        self._refresh()

    # ── init ──────────────────────────────────────────────────────────────────

    def _ensure_trash(self):
        if not any(f.is_trash for f in self._folders):
            self._folders.append(Folder(id=self._next_folder_id, name="Trash", is_trash=True))
            self._next_folder_id += 1

    def _trash_folder(self) -> Optional[Folder]:
        return next((f for f in self._folders if f.is_trash), None)

    # ── build ──────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top bar ──
        top = QWidget()
        top.setFixedHeight(50)
        top.setStyleSheet(f"background: {_BG}; border-bottom: 1px solid {_BORDER};")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(16, 0, 16, 0)
        tl.setSpacing(10)

        t_col = QVBoxLayout(); t_col.setSpacing(1)
        title = QLabel("Files and versions")
        title.setFont(make_font(size=19, bold=True))
        title.setStyleSheet(f"color: {_TEXT}; background: transparent; border: none;")
        sub = QLabel("All your 3D files and their versions, organised and easy to find.")
        sub.setStyleSheet(f"color: {_MUTED}; font-size: 14px; background: transparent; border: none;")
        t_col.addWidget(title); t_col.addWidget(sub)
        tl.addLayout(t_col)
        tl.addStretch()

        new_folder_btn = QPushButton("📁  New folder")
        new_folder_btn.setStyleSheet(_BTN_SMALL)
        new_folder_btn.setFixedHeight(30)
        new_folder_btn.setCursor(Qt.PointingHandCursor)
        new_folder_btn.clicked.connect(lambda: self._create_folder(self._selected_folder))

        upload_btn = QPushButton("↑  Upload file")
        upload_btn.setStyleSheet(_BTN_PRIMARY)
        upload_btn.setFixedHeight(30)
        upload_btn.setCursor(Qt.PointingHandCursor)
        upload_btn.clicked.connect(self._upload_files)

        tl.addWidget(new_folder_btn)
        tl.addWidget(upload_btn)
        root.addWidget(top)

        # ── Main horizontal split ──
        main = QWidget()
        ml = QHBoxLayout(main)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)

        # Left: folder tree
        self._tree = _FolderTree()
        self._tree.folder_selected.connect(self._on_folder_selected)
        self._tree.folder_renamed.connect(self._on_folder_renamed)
        self._tree.folder_deleted.connect(self._on_folder_deleted)
        self._tree.folder_created.connect(self._on_folder_created)
        ml.addWidget(self._tree)

        vdiv = QFrame()
        vdiv.setFrameShape(QFrame.VLine)
        vdiv.setStyleSheet(f"color: {_BORDER}; background: {_BORDER}; max-width: 1px; border: none;")
        ml.addWidget(vdiv)

        # Right: file list area
        right = QWidget()
        right.setStyleSheet(f"background: {_BG};")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)

        # Search + filters toolbar
        toolbar = QWidget()
        toolbar.setFixedHeight(44)
        toolbar.setStyleSheet(f"background: {_CARD}; border-bottom: 1px solid {_BORDER};")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(16, 6, 16, 6)
        tb.setSpacing(8)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search files and versions…")
        self._search.setFixedWidth(220)
        self._search.setFixedHeight(28)
        self._search.setStyleSheet(_INPUT)
        self._search.textChanged.connect(self._on_search)
        tb.addWidget(self._search)

        self._type_combo = QComboBox()
        self._type_combo.setFixedHeight(28)
        self._type_combo.setStyleSheet(_INPUT)
        self._type_combo.addItems([
            "All file types",
            ".stl", ".step", ".3dm", ".obj", ".dxf",   # 3D formats
            ".pdf",                                      # Documents
            ".jpg", ".jpeg", ".png",                     # Images
        ])
        self._type_combo.currentTextChanged.connect(self._on_filter_type)
        tb.addWidget(self._type_combo)

        self._status_combo = QComboBox()
        self._status_combo.setFixedHeight(28)
        self._status_combo.setStyleSheet(_INPUT)
        self._status_combo.addItems(["All statuses", "Approved", "In review", "In progress"])
        self._status_combo.currentTextChanged.connect(self._on_filter_status)
        tb.addWidget(self._status_combo)

        tb.addStretch()

        # List / Grid toggle
        self._list_btn = QPushButton("☰")
        self._list_btn.setFixedSize(28, 28)
        self._list_btn.setCheckable(True)
        self._list_btn.setChecked(True)
        self._list_btn.setStyleSheet(f"""
            QPushButton {{ background: {_ACCENT}; color: white; border: none;
                           border-radius: 4px 0 0 4px; font-size: 16px; }}
            QPushButton:!checked {{ background: {_CARD}; color: {_MUTED};
                                    border: 1px solid {_BORDER}; }}
        """)
        self._list_btn.clicked.connect(lambda: self._set_grid_view(False))

        self._grid_btn = QPushButton("⊞")
        self._grid_btn.setFixedSize(28, 28)
        self._grid_btn.setCheckable(True)
        self._grid_btn.setStyleSheet(f"""
            QPushButton {{ background: {_CARD}; color: {_MUTED};
                           border: 1px solid {_BORDER}; border-radius: 0 4px 4px 0; font-size: 16px; }}
            QPushButton:checked {{ background: {_ACCENT}; color: white; border: none; }}
        """)
        self._grid_btn.clicked.connect(lambda: self._set_grid_view(True))

        tb.addWidget(self._list_btn)
        tb.addWidget(self._grid_btn)
        rl.addWidget(toolbar)

        # Column headers (list view only)
        self._col_hdr = _ColHeader()
        rl.addWidget(self._col_hdr)

        # Scrollable file list
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ background: {_BG}; border: none; }}
            QScrollBar:vertical {{ background: {_BG}; width: 8px; border-radius: 4px; }}
            QScrollBar::handle:vertical {{ background: {_BORDER}; border-radius: 4px; min-height: 30px; }}
        """)
        self._content = QWidget()
        self._content.setStyleSheet(f"background: {_BG};")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        self._content_layout.addStretch()
        self._scroll.setWidget(self._content)
        rl.addWidget(self._scroll, 1)

        ml.addWidget(right, 1)
        root.addWidget(main, 1)

    # ── filtering / display ────────────────────────────────────────────────────

    def _visible_files(self) -> List[ProjectFile]:
        in_trash = (self._selected_folder and self._selected_folder.is_trash)

        files = [f for f in self._files if f.trashed == bool(in_trash)]

        if self._selected_folder and not self._selected_folder.is_trash:
            files = [f for f in files if f.folder_id == self._selected_folder.id]

        if self._search_text:
            q = self._search_text.lower()
            files = [f for f in files
                     if q in f.name.lower() or q in f.extension.lower()]

        if self._filter_type and self._filter_type != "All file types":
            files = [f for f in files if f.extension == self._filter_type]

        if self._filter_status and self._filter_status != "All statuses":
            files = [f for f in files if f.status == self._filter_status]

        return files

    def _refresh(self):
        self._tree.set_folders(self._folders)

        while self._content_layout.count() > 1:
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        files = self._visible_files()
        in_trash = bool(self._selected_folder and self._selected_folder.is_trash)
        self._col_hdr.setVisible(not self._grid_view)

        if not files:
            empty = QLabel("No files here yet. Click ↑ Upload file to add one." if not in_trash
                           else "Trash is empty.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(f"color: {_MUTED}; font-size: 15px; background: transparent; border: none;")
            empty.setContentsMargins(0, 40, 0, 0)
            self._content_layout.insertWidget(0, empty)
            return

        if self._grid_view:
            self._render_grid(files, in_trash)
        else:
            self._render_list(files, in_trash)

    def _render_list(self, files: List[ProjectFile], in_trash: bool):
        # Group by extension category
        groups = {}
        for f in files:
            cat = f.extension.upper().lstrip('.') + " FILES" if f.extension else "OTHER FILES"
            groups.setdefault(cat, []).append(f)

        idx = 0
        for cat, cat_files in groups.items():
            # Section header
            hdr = QWidget()
            hdr.setFixedHeight(32)
            hdr.setStyleSheet(f"background: {_BG};")
            hl = QHBoxLayout(hdr)
            hl.setContentsMargins(16, 0, 16, 0)
            cat_lbl = QLabel(cat)
            cat_lbl.setStyleSheet(f"color: {_TEXT}; font-size: 15px; font-weight: bold; background: transparent; border: none;")
            count_lbl = QLabel(f"{len(cat_files)} file{'s' if len(cat_files) != 1 else ''}")
            count_lbl.setStyleSheet(f"""
                QLabel {{ background: {_ACCENT}22; color: {_ACCENT};
                          border: 1px solid {_ACCENT}55; border-radius: 10px;
                          padding: 1px 8px; font-size: 16px; font-weight: bold; }}
            """)
            hl.addWidget(cat_lbl)
            hl.addWidget(count_lbl)
            hl.addStretch()
            self._content_layout.insertWidget(idx, hdr)
            idx += 1

            for pf in cat_files:
                row = _FileRow(pf, in_trash=in_trash)
                self._connect_file_row(row)
                self._content_layout.insertWidget(idx, row)
                idx += 1

    def _render_grid(self, files: List[ProjectFile], in_trash: bool):
        wrap = QWidget()
        wrap.setStyleSheet(f"background: {_BG};")
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(16, 16, 16, 16)
        wl.setSpacing(8)

        row_w = None
        cols = 0
        for i, pf in enumerate(files):
            if cols == 0:
                row_w = QWidget(); row_w.setStyleSheet("background: transparent;")
                rl = QHBoxLayout(row_w); rl.setContentsMargins(0,0,0,0); rl.setSpacing(12)
                wl.addWidget(row_w)

            card = self._make_card(pf, in_trash)
            row_w.layout().addWidget(card)
            cols += 1
            if cols == 4:
                row_w.layout().addStretch()
                cols = 0

        if row_w and cols > 0:
            row_w.layout().addStretch()

        self._content_layout.insertWidget(0, wrap)

    def _make_card(self, pf: ProjectFile, in_trash: bool) -> QFrame:
        card = QFrame()
        card.setFixedWidth(160)
        card.setStyleSheet(f"""
            QFrame {{ background: {_CARD}; border: 1px solid {_BORDER};
                      border-radius: 8px; }}
            QFrame:hover {{ border-color: {_ACCENT}; }}
        """)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(10, 10, 10, 10)
        cl.setSpacing(6)

        thumb = _ExtThumb(pf.extension, 140, 80)
        cl.addWidget(thumb)

        nl = QLabel(pf.name)
        nl.setWordWrap(True)
        nl.setStyleSheet(f"color: {_TEXT}; font-size: 14px; font-weight: bold; background: transparent; border: none;")
        cl.addWidget(nl)

        lv = pf.latest_version
        if lv:
            cl.addWidget(_version_chip(lv.version_str))
        cl.addWidget(_status_chip(pf.status))

        btn_row = QHBoxLayout(); btn_row.setSpacing(4)
        dl_btn = QPushButton("↓")
        dl_btn.setFixedSize(24, 24)
        dl_btn.setStyleSheet(_BTN_ICON)
        dl_btn.setCursor(Qt.PointingHandCursor)

        more_btn = QPushButton("⋮")
        more_btn.setFixedSize(24, 24)
        more_btn.setStyleSheet(_BTN_ICON)
        more_btn.setCursor(Qt.PointingHandCursor)

        row_widget = _FileRow(pf, in_trash=in_trash)
        row_widget.setVisible(False)
        dl_btn.clicked.connect(row_widget._download)
        more_btn.clicked.connect(row_widget._show_menu)
        self._connect_file_row(row_widget)
        card.layout().addWidget(row_widget)

        btn_row.addStretch()
        btn_row.addWidget(dl_btn)
        btn_row.addWidget(more_btn)
        cl.addLayout(btn_row)
        return card

    def _connect_file_row(self, row: _FileRow):
        row.open_viewer.connect(self.open_in_viewer)
        row.upload_version.connect(self._upload_new_version)
        row.rename.connect(self._rename_file)
        row.move.connect(self._move_file)
        row.trash.connect(self._trash_file)
        row.restore.connect(self._restore_file)
        row.delete_perm.connect(self._delete_file_perm)
        row.status_changed.connect(self._change_status)

    # ── event handlers ─────────────────────────────────────────────────────────

    def _on_folder_selected(self, folder: Folder):
        self._selected_folder = folder
        self._refresh()

    def _on_folder_renamed(self, folder: Folder, name: str):
        folder.name = name
        self._refresh()
        self.changed.emit()

    def _on_folder_deleted(self, folder: Folder):
        child_files = [f for f in self._files if f.folder_id == folder.id]
        if child_files:
            if not ask_yes_no_dialog(
                self, "Delete Folder",
                f"Delete '{folder.name}'?\n{len(child_files)} file(s) will be moved to Trash."
            ):
                return
            trash = self._trash_folder()
            if trash:
                for f in child_files:
                    f.folder_id = trash.id
                    f.trashed = True
        else:
            if not ask_yes_no_dialog(self, "Delete Folder", f"Delete folder '{folder.name}'?"):
                return

        self._folders = [f for f in self._folders if f.id != folder.id]
        if self._selected_folder and self._selected_folder.id == folder.id:
            self._selected_folder = None
        self._refresh()
        self.changed.emit()

    def _on_folder_created(self, parent: Optional[Folder], name: str):
        self._create_folder(parent, name)

    def _create_folder(self, parent: Optional[Folder], name: str = ""):
        if not name:
            root_count = len([f for f in self._folders if f.parent_id is None and not f.is_trash])
            num = f"{root_count + 1:02d}_"
            name, ok = ask_text_input_dialog(
                self, "New Folder", "Folder name", placeholder=f"{num}New Folder"
            )
            if not ok or not name:
                return

        folder = Folder(
            id=self._next_folder_id,
            name=name,
            parent_id=parent.id if parent else None,
        )
        self._next_folder_id += 1
        trash = self._trash_folder()
        insert_before = self._folders.index(trash) if trash else len(self._folders)
        self._folders.insert(insert_before, folder)
        self._refresh()
        self.changed.emit()

    def _upload_files(self):
        target_folder = self._selected_folder
        if target_folder and target_folder.is_trash:
            show_message_dialog(self, "Cannot Upload", "Cannot upload files to Trash.")
            return
        if target_folder is None:
            non_trash = [f for f in self._folders if not f.is_trash]
            if not non_trash:
                show_message_dialog(self, "No Folder", "Please create a folder first.")
                return

        paths, _ = QFileDialog.getOpenFileNames(
            self, "Upload Files", "",
            "Supported Files (*.stl *.step *.stp *.3dm *.obj *.dxf *.pdf *.jpg *.jpeg *.png *.heic);;All Files (*)"
        )
        if not paths:
            return

        folder_id = target_folder.id if target_folder else self._folders[0].id
        now = datetime.now().strftime("%d/%m/%Y %H:%M")

        for path in paths:
            size = os.path.getsize(path) if os.path.exists(path) else 0
            name = Path(path).stem
            pf = ProjectFile(
                id=self._next_file_id,
                name=name,
                folder_id=folder_id,
                versions=[FileVersion(version_str="v1.0", file_path=path,
                                      uploaded_at=now, size_bytes=size)]
            )
            self._next_file_id += 1
            self._files.append(pf)

        self._refresh()
        self.changed.emit()

    def _upload_new_version(self, pf: ProjectFile):
        path, _ = QFileDialog.getOpenFileName(
            self, "Upload New Version", "",
            "All Files (*)"
        )
        if not path:
            return
        size = os.path.getsize(path) if os.path.exists(path) else 0
        now = datetime.now().strftime("%d/%m/%Y %H:%M")
        pf.versions.append(FileVersion(
            version_str=pf.next_version_str(),
            file_path=path,
            uploaded_at=now,
            size_bytes=size,
        ))
        self._refresh()
        self.changed.emit()

    def _rename_file(self, pf: ProjectFile):
        name, ok = ask_text_input_dialog(self, "Rename File", "File name", placeholder=pf.name)
        if ok and name:
            pf.name = name
            self._refresh()
            self.changed.emit()

    def _move_file(self, pf: ProjectFile):
        non_trash = [f for f in self._folders if not f.is_trash]
        if not non_trash:
            return
        dlg = FormModal(self, "Move to Folder",
                        theme=FormModal.LIGHT, min_width=300)
        combo = dlg.add_field("DESTINATION FOLDER", QComboBox())
        for f in non_trash:
            combo.addItem(f.name, f.id)
        dlg.finish()
        if dlg.exec_() == QDialog.Accepted:
            pf.folder_id = combo.currentData()
            self._refresh()
            self.changed.emit()

    def _trash_file(self, pf: ProjectFile):
        trash = self._trash_folder()
        if trash:
            pf.folder_id = trash.id
            pf.trashed = True
            self._refresh()
            self.changed.emit()

    def _restore_file(self, pf: ProjectFile):
        non_trash = [f for f in self._folders if not f.is_trash]
        target = non_trash[0] if non_trash else None
        if target:
            pf.folder_id = target.id
            pf.trashed = False
            self._refresh()
            self.changed.emit()

    def _delete_file_perm(self, pf: ProjectFile):
        if ask_yes_no_dialog(self, "Delete Permanently",
                             f"Permanently delete '{pf.name}'?\nThis cannot be undone."):
            self._files.remove(pf)
            self._refresh()
            self.changed.emit()

    def _change_status(self, pf: ProjectFile, status: str):
        pf.status = status
        self._refresh()
        self.changed.emit()

    def _on_search(self, text: str):
        self._search_text = text
        self._refresh()

    def _on_filter_type(self, text: str):
        self._filter_type = text
        self._refresh()

    def _on_filter_status(self, text: str):
        self._filter_status = text
        self._refresh()

    def _set_grid_view(self, grid: bool):
        self._grid_view = grid
        self._list_btn.setChecked(not grid)
        self._grid_btn.setChecked(grid)
        self._refresh()

    # ── serialisation ──────────────────────────────────────────────────────────

    def get_data(self) -> dict:
        def _ver(v: FileVersion) -> dict:
            return {"version_str": v.version_str, "file_path": v.file_path,
                    "uploaded_at": v.uploaded_at, "size_bytes": v.size_bytes}
        def _file(f: ProjectFile) -> dict:
            return {"id": f.id, "name": f.name, "folder_id": f.folder_id,
                    "status": f.status, "trashed": f.trashed,
                    "versions": [_ver(v) for v in f.versions]}
        def _folder(f: Folder) -> dict:
            return {"id": f.id, "name": f.name, "parent_id": f.parent_id, "is_trash": f.is_trash}
        return {
            "next_folder_id": self._next_folder_id,
            "next_file_id":   self._next_file_id,
            "folders": [_folder(f) for f in self._folders],
            "files":   [_file(f) for f in self._files],
        }

    def set_data(self, data: dict):
        self._next_folder_id = data.get("next_folder_id", 1)
        self._next_file_id   = data.get("next_file_id", 1)
        self._folders = [
            Folder(id=d["id"], name=d["name"], parent_id=d.get("parent_id"),
                   is_trash=d.get("is_trash", False))
            for d in data.get("folders", [])
        ]
        self._files = []
        for fd in data.get("files", []):
            pf = ProjectFile(
                id=fd["id"], name=fd["name"], folder_id=fd["folder_id"],
                status=fd.get("status", "In progress"), trashed=fd.get("trashed", False),
                versions=[FileVersion(**v) for v in fd.get("versions", [])],
            )
            self._files.append(pf)
        self._ensure_trash()
        self._selected_folder = None
        self._refresh()

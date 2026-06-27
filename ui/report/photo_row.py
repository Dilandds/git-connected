"""Row of 4 photo slots with captions — one repeating unit inside a page's photo section."""
from typing import List

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QFileDialog,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap, QIcon

from .models import PhotoRow
from .shared import _BORDER, _MUTED, _ACCENT, _field


class PhotoRowWidget(QWidget):
    """4 photo slots with captions — one row in the Components section."""

    changed = pyqtSignal()

    def __init__(self, row_data: PhotoRow, parent=None):
        super().__init__(parent)
        self._row = row_data
        self.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        photo_row   = QHBoxLayout()
        caption_row = QHBoxLayout()
        photo_row.setSpacing(8)
        caption_row.setSpacing(8)

        self._photo_btns:    List[QPushButton] = []
        self._caption_edits: List[QLineEdit]   = []

        for i, cell in enumerate(self._row.photos):
            btn = QPushButton("＋\nAdd photo")
            btn.setFixedSize(130, 100)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: #f1f3f5; border: 1px dashed {_BORDER};
                    border-radius: 6px; color: {_MUTED}; font-size: 10px;
                }}
                QPushButton:hover {{ border-color: {_ACCENT}; color: {_ACCENT}; }}
            """)
            btn.clicked.connect(lambda _, idx=i: self._upload(idx))
            if cell.image_path:
                self._apply_image(btn, cell.image_path)

            cap = _field("text here")
            cap.setText(cell.caption)
            cap.setFixedWidth(130)
            cap.textChanged.connect(lambda t, idx=i: self._on_caption(idx, t))

            photo_row.addWidget(btn)
            caption_row.addWidget(cap)
            self._photo_btns.append(btn)
            self._caption_edits.append(cap)

        photo_row.addStretch()
        caption_row.addStretch()
        layout.addLayout(photo_row)
        layout.addLayout(caption_row)

    def _upload(self, idx: int):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Photo", "", "Images (*.png *.jpg *.jpeg *.webp)"
        )
        if path:
            self._row.photos[idx].image_path = path
            self._apply_image(self._photo_btns[idx], path)
            self.changed.emit()

    def _apply_image(self, btn: QPushButton, path: str):
        pix = QPixmap(path)
        if not pix.isNull():
            btn.setIcon(QIcon(
                pix.scaled(btn.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            ))
            btn.setIconSize(btn.size())
            btn.setText("")

    def _on_caption(self, idx: int, text: str):
        self._row.photos[idx].caption = text
        self.changed.emit()

    def first_empty_slot(self) -> int:
        """Return the index of the first slot with no image, or -1 if all full."""
        for i, cell in enumerate(self._row.photos):
            if not cell.image_path:
                return i
        return -1

    def set_image_from_pixmap(self, idx: int, pixmap: "QPixmap") -> bool:
        """Write a QPixmap directly into slot idx. Saves to a temp PNG on disk."""
        import tempfile, os
        if not (0 <= idx < len(self._photo_btns)):
            return False
        tmp_dir = os.path.join(tempfile.gettempdir(), "ectoform_report_photos")
        os.makedirs(tmp_dir, exist_ok=True)
        import time
        path = os.path.join(tmp_dir, f"screenshot_{int(time.time()*1000)}_{idx}.png")
        if not pixmap.save(path, "PNG"):
            return False
        self._row.photos[idx].image_path = path
        self._apply_image(self._photo_btns[idx], path)
        self.changed.emit()
        return True

    def lock(self):
        for btn in self._photo_btns:
            btn.setEnabled(False)
        for cap in self._caption_edits:
            cap.setReadOnly(True)

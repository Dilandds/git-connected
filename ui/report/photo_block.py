"""
Photo block flow for the report page.
Each block = one large photo + caption + Comments textarea + remove button.
Blocks flow left-to-right, wrapping to the next row when full.
"""
import math
import os
import tempfile
import time
from typing import List, Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLineEdit, QTextEdit, QLabel,
    QFileDialog, QSizePolicy, QFrame, QApplication,
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize, QPoint
from PyQt5.QtGui import QPixmap, QIcon, QCursor

from .models import PhotoCell, PhotoBlock, ReportPage
from .shared import _BORDER, _MUTED, _ACCENT, _BG as _INPUT_BG

# ── dimensions ────────────────────────────────────────────────────────────────
_INNER_PAD  = 10
_BLOCK_W    = 310
_CAPTION_H  = 28
_PHOTO_W    = _BLOCK_W - 2 * _INNER_PAD          # 290
_PHOTO_H    = 260                                 # tall single image slot
_BLOCK_GAP  = 14

_BLOCK_H = (
    _INNER_PAD      # top
    + _PHOTO_H      # photo
    + 10            # gap
    + 18            # "Comments" label
    + 4             # gap
    + 68            # comment textarea
    + _INNER_PAD    # bottom
)

# ── styles ────────────────────────────────────────────────────────────────────
_SLOT_EMPTY = f"""
    QPushButton {{
        background: {_INPUT_BG};
        border: 1.5px dashed {_BORDER};
        border-radius: 8px;
        color: {_MUTED}; font-size: 16px;
    }}
    QPushButton:hover {{ border-color: {_ACCENT}; color: {_ACCENT}; background: #eff6ff; }}
"""
_SLOT_FILLED = f"""
    QPushButton {{
        background: {_INPUT_BG};
        border: 1.5px solid {_BORDER};
        border-radius: 8px;
    }}
    QPushButton:hover {{ border-color: {_ACCENT}; }}
"""
_CAPTION_STYLE = f"""
    QLineEdit {{
        background: {_INPUT_BG}; border: 1px solid {_BORDER};
        border-radius: 6px; color: #374151; font-size: 12px; padding: 2px 8px;
    }}
    QLineEdit:focus {{ border-color: {_ACCENT}; background: #ffffff; }}
"""
_COMMENT_STYLE = f"""
    QTextEdit {{
        background: {_INPUT_BG}; border: 1px solid {_BORDER};
        border-radius: 6px; color: #374151; font-size: 12px; padding: 4px 8px;
    }}
    QTextEdit:focus {{ border-color: {_ACCENT}; background: #ffffff; }}
"""
_LBL_STYLE = f"color: {_MUTED}; font-size: 11px; font-weight: 600; background: transparent; border: none;"
_REMOVE_STYLE = f"""
    QPushButton {{
        background: #ef4444; color: #ffffff;
        border: none; border-radius: 9px;
        font-size: 13px; font-weight: bold; padding: 0;
    }}
    QPushButton:hover {{ background: #dc2626; }}
"""


# ── Floating hover-zoom preview ───────────────────────────────────────────────

class _HoverPreview(QWidget):
    """Frameless floating widget showing an enlarged photo on hover."""

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._lbl = QLabel(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addWidget(self._lbl)
        self._lbl.setStyleSheet(
            'border: 2px solid #d0d0d0; border-radius: 10px; background: #ffffff;'
        )

    def show_for(self, pixmap: QPixmap, global_pos: QPoint):
        if pixmap.isNull():
            return
        preview = pixmap.scaled(720, 540, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._lbl.setPixmap(preview)
        self._lbl.setFixedSize(preview.size())
        self.adjustSize()
        screen = QApplication.screenAt(global_pos)
        x = global_pos.x() + 20
        y = global_pos.y() - self.height() // 2
        if screen:
            sr = screen.availableGeometry()
            if x + self.width() > sr.right():
                x = global_pos.x() - self.width() - 20
            y = max(sr.top() + 4, min(y, sr.bottom() - self.height() - 4))
        self.move(x, y)
        self.show()
        self.raise_()


# ── Photo button with hover-zoom ──────────────────────────────────────────────

class _PhotoBtn(QPushButton):
    """Photo slot button that shows an enlarged floating preview on hover."""

    def __init__(self, preview: _HoverPreview, parent=None):
        super().__init__(parent)
        self._preview = preview
        self._orig_pix: Optional[QPixmap] = None

    def set_orig_pixmap(self, pix: Optional[QPixmap]):
        self._orig_pix = pix

    def enterEvent(self, event):
        if self._orig_pix and not self._orig_pix.isNull():
            self._preview.show_for(self._orig_pix, QCursor.pos())
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._preview.hide()
        super().leaveEvent(event)


# ── One block: large photo + caption + comments + remove ──────────────────────

class PhotoBlockWidget(QFrame):
    changed          = pyqtSignal()
    delete_requested = pyqtSignal()

    def __init__(self, block: PhotoBlock, preview: _HoverPreview, parent=None):
        super().__init__(parent)
        self._block = block
        cell = block.photos[0]
        self._cell = cell
        self._locked = False
        self._orig_pix: Optional[QPixmap] = None

        self.setFixedSize(_BLOCK_W, _BLOCK_H)
        self.setStyleSheet(f"""
            QFrame {{
                background: #ffffff;
                border: 1.5px solid {_BORDER};
                border-radius: 10px;
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(_INNER_PAD, _INNER_PAD, _INNER_PAD, _INNER_PAD)
        lay.setSpacing(0)

        # Large photo slot with hover preview
        self._photo_btn = _PhotoBtn(preview)
        self._photo_btn.setFixedSize(_PHOTO_W, _PHOTO_H)
        self._photo_btn.setCursor(Qt.PointingHandCursor)
        self._photo_btn.setStyleSheet(_SLOT_EMPTY)
        self._photo_btn.setText('📷\nAdd photo')
        self._photo_btn.clicked.connect(self._upload)
        if cell.image_path:
            pix = QPixmap(cell.image_path)
            if not pix.isNull():
                self._apply_photo(pix)
        lay.addWidget(self._photo_btn)

        lay.addSpacing(10)

        # Comments label
        lbl = QLabel('Comments')
        lbl.setStyleSheet(_LBL_STYLE)
        lay.addWidget(lbl)

        lay.addSpacing(4)

        # Comments textarea
        self._comment = QTextEdit()
        self._comment.setPlaceholderText('Comments...')
        self._comment.setStyleSheet(_COMMENT_STYLE)
        self._comment.setPlainText(block.comment)
        self._comment.textChanged.connect(self._on_comment)
        lay.addWidget(self._comment, 1)

        # Remove button (pinned to top-right corner)
        self._remove_btn = QPushButton('×')
        self._remove_btn.setParent(self)
        self._remove_btn.setFixedSize(18, 18)
        self._remove_btn.setCursor(Qt.PointingHandCursor)
        self._remove_btn.setStyleSheet(_REMOVE_STYLE)
        self._remove_btn.clicked.connect(self.delete_requested)
        self._remove_btn.move(_BLOCK_W - 22, 4)

    def _upload(self):
        if self._locked:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select Photo', '', 'Images (*.png *.jpg *.jpeg *.webp *.heic)')
        if path:
            pix = QPixmap(path)
            if not pix.isNull():
                self._cell.image_path = path
                self._apply_photo(pix)
                self.changed.emit()

    def _apply_photo(self, pix: QPixmap):
        self._orig_pix = pix
        self._photo_btn.set_orig_pixmap(pix)
        scaled = pix.scaled(QSize(_PHOTO_W, _PHOTO_H),
                            Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        self._photo_btn.setIcon(QIcon(scaled))
        self._photo_btn.setIconSize(QSize(_PHOTO_W, _PHOTO_H))
        self._photo_btn.setText('')
        self._photo_btn.setStyleSheet(_SLOT_FILLED)

    def _on_comment(self):
        self._block.comment = self._comment.toPlainText()
        self.changed.emit()

    def has_image(self) -> bool:
        return bool(self._cell.image_path)

    def set_pixmap(self, pixmap: QPixmap) -> bool:
        """Save pixmap to a temp file and display it. Used for screenshot drops."""
        tmp_dir = os.path.join(tempfile.gettempdir(), "ectoform_report_photos")
        os.makedirs(tmp_dir, exist_ok=True)
        path = os.path.join(tmp_dir, f"photo_{int(time.time() * 1000)}.png")
        if not pixmap.save(path, "PNG"):
            return False
        self._cell.image_path = path
        self._apply_photo(pixmap)
        self.changed.emit()
        return True

    def lock(self):
        self._locked = True
        self._photo_btn.setEnabled(False)
        self._comment.setReadOnly(True)
        self._remove_btn.hide()


# ── Flow of blocks ─────────────────────────────────────────────────────────────

class PhotoBlockFlow(QWidget):
    """Horizontally-wrapping flow of PhotoBlockWidget units + an add button."""

    changed = pyqtSignal()

    def __init__(self, page: ReportPage, parent=None):
        super().__init__(parent)
        self._page = page
        self._block_widgets: List[PhotoBlockWidget] = []
        self._locked = False
        self._preview = _HoverPreview()   # shared across all blocks

        self._add_btn = QPushButton('+\nAdd block')
        self._add_btn.setParent(self)
        self._add_btn.setFixedSize(_BLOCK_W, _BLOCK_H)
        self._add_btn.setCursor(Qt.PointingHandCursor)
        self._add_btn.setStyleSheet(f"""
            QPushButton {{
                background: #ffffff; border: 2px dashed {_ACCENT};
                border-radius: 10px; color: {_ACCENT};
                font-size: 14px; font-weight: bold;
            }}
            QPushButton:hover {{ background: #eff6ff; }}
        """)
        self._add_btn.clicked.connect(self._on_add)

        if not page.photo_blocks:
            page.photo_blocks.append(PhotoBlock())

        for blk in page.photo_blocks:
            self._make_widget(blk)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    # ── layout ────────────────────────────────────────────────────────────────

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self):
        w = self.width()
        if w <= 0:
            return
        cols = max(1, (w + _BLOCK_GAP) // (_BLOCK_W + _BLOCK_GAP))
        all_items = list(self._block_widgets) + ([] if self._locked else [self._add_btn])

        for idx, item in enumerate(all_items):
            r, c = divmod(idx, cols)
            item.setGeometry(
                c * (_BLOCK_W + _BLOCK_GAP),
                r * (_BLOCK_H + _BLOCK_GAP),
                _BLOCK_W, _BLOCK_H,
            )
            item.show()

        total_rows = math.ceil(len(all_items) / cols) if all_items else 1
        self.setFixedHeight(total_rows * (_BLOCK_H + _BLOCK_GAP) + _BLOCK_GAP)

    def sizeHint(self) -> QSize:
        return QSize(_BLOCK_W * 2 + _BLOCK_GAP, _BLOCK_H + _BLOCK_GAP * 2)

    # ── actions ───────────────────────────────────────────────────────────────

    def _on_add(self):
        blk = PhotoBlock()
        self._page.photo_blocks.append(blk)
        self._make_widget(blk)
        self._relayout()
        self.changed.emit()

    def _on_delete(self, widget: PhotoBlockWidget, block: PhotoBlock):
        if block in self._page.photo_blocks:
            self._page.photo_blocks.remove(block)
        self._block_widgets.remove(widget)
        widget.hide()
        widget.deleteLater()
        self._relayout()
        self.changed.emit()

    def _make_widget(self, blk: PhotoBlock) -> PhotoBlockWidget:
        w = PhotoBlockWidget(blk, self._preview, parent=self)
        w.changed.connect(self.changed)
        w.delete_requested.connect(lambda b=blk, bw=w: self._on_delete(bw, b))
        self._block_widgets.append(w)
        w.show()
        return w

    # ── public API ────────────────────────────────────────────────────────────

    def add_screenshot(self, pixmap: QPixmap) -> bool:
        """Fill the first empty block slot, or add a new block if all are full."""
        for bw in self._block_widgets:
            if not bw.has_image():
                return bw.set_pixmap(pixmap)
        self._on_add()
        if self._block_widgets:
            return self._block_widgets[-1].set_pixmap(pixmap)
        return False

    def lock(self):
        self._locked = True
        self._add_btn.hide()
        for bw in self._block_widgets:
            bw.lock()
        self._relayout()

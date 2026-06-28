"""
Photo grid for report pages.
Each photo is a card (image + comment field).
Cards flow left-to-right, wrapping to the next line when the row is full.
The "+" button always appears at the end of the last card.
"""
import math
import os
import tempfile
import time
from typing import List, Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLineEdit, QFileDialog,
    QLabel, QApplication, QSizePolicy,
)
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QSize
from PyQt5.QtGui import QPixmap, QIcon, QCursor, QColor

from .models import PhotoCell, PhotoRow, ReportPage
from .shared import _BORDER, _MUTED, _ACCENT, _field


# ── Hover preview ─────────────────────────────────────────────────────────────

class _HoverPreview(QWidget):
    """Frameless floating widget that shows an enlarged image on hover."""

    def __init__(self, parent=None):
        super().__init__(parent,
                         Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._label = QLabel(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addWidget(self._label)
        self._label.setStyleSheet(
            "border: 2px solid #d0d0d0; border-radius: 10px; background: #ffffff;"
        )

    def show_for(self, pixmap: QPixmap, global_pos: QPoint):
        if pixmap.isNull():
            return
        preview = pixmap.scaled(680, 520, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._label.setPixmap(preview)
        self._label.setFixedSize(preview.size())
        self.adjustSize()
        screen = QApplication.screenAt(global_pos)
        x = global_pos.x() + 16
        y = global_pos.y() - self.height() // 2
        if screen:
            sr = screen.availableGeometry()
            if x + self.width() > sr.right():
                x = global_pos.x() - self.width() - 16
            y = max(sr.top() + 4, min(y, sr.bottom() - self.height() - 4))
        self.move(x, y)
        self.show()
        self.raise_()


# ── Photo cell button ─────────────────────────────────────────────────────────

class _PhotoCellButton(QPushButton):
    """Photo slot button that shows a floating enlarged preview on hover."""

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


# ── Single photo card ─────────────────────────────────────────────────────────

class PhotoCardWidget(QWidget):
    """One photo + comment field — the basic unit of the flow grid."""

    changed          = pyqtSignal()
    delete_requested = pyqtSignal()   # emitted when the user clicks ×

    PHOTO_H   = 120
    COMMENT_H = 28

    def __init__(self, cell: PhotoCell, hover: _HoverPreview, parent=None):
        super().__init__(parent)
        self._cell  = cell
        self._hover = hover
        self.setStyleSheet("background: transparent;")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        # Photo button (fills all horizontal space)
        self._btn = _PhotoCellButton(self._hover)
        self._btn.setFixedHeight(self.PHOTO_H)
        self._btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn.setCursor(Qt.PointingHandCursor)
        self._btn.setStyleSheet(f"""
            QPushButton {{
                background: #f1f3f5; border: 1px dashed {_BORDER};
                border-radius: 6px; color: {_MUTED}; font-size: 10px;
            }}
            QPushButton:hover {{ border-color: {_ACCENT}; color: {_ACCENT}; }}
        """)
        self._btn.setText('+\nAdd photo')
        self._btn.clicked.connect(self._upload)
        if cell.image_path:
            self._apply_image(cell.image_path)
        lay.addWidget(self._btn)

        # Delete overlay — top-right corner of the photo button, always on top
        self._del_btn = QPushButton('×', self._btn)
        self._del_btn.setFixedSize(20, 20)
        self._del_btn.setCursor(Qt.PointingHandCursor)
        self._del_btn.setStyleSheet("""
            QPushButton {
                background: rgba(239,68,68,0.85); color: white;
                border: none; border-radius: 10px;
                font-size: 13px; font-weight: bold; padding: 0;
            }
            QPushButton:hover { background: #dc2626; }
        """)
        self._del_btn.clicked.connect(self.delete_requested)
        self._del_btn.hide()

        # Comment field
        self._comment = _field('text here')
        self._comment.setFixedHeight(self.COMMENT_H)
        self._comment.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._comment.setText(cell.caption)
        self._comment.textChanged.connect(self._on_comment)
        lay.addWidget(self._comment)

    # ── Hover: show/hide delete button ────────────────────────────────────────

    def enterEvent(self, event):
        self._del_btn.show()
        self._del_btn.raise_()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._del_btn.hide()
        super().leaveEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Keep delete button pinned to top-right of the photo area
        self._del_btn.move(self._btn.width() - self._del_btn.width() - 4, 4)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _upload(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Photo", "", "Images (*.png *.jpg *.jpeg *.webp *.heic)")
        if path:
            self._cell.image_path = path
            self._apply_image(path)
            self.changed.emit()

    def _apply_image(self, path: str):
        pix = QPixmap(path)
        if not pix.isNull():
            self._btn.setIcon(QIcon(
                pix.scaled(self._btn.size(),
                           Qt.KeepAspectRatioByExpanding,
                           Qt.SmoothTransformation)
            ))
            self._btn.setIconSize(self._btn.size())
            self._btn.setText("")
            self._btn.set_orig_pixmap(pix)

    def _on_comment(self, text: str):
        self._cell.caption = text
        self.changed.emit()

    # ── Public API ────────────────────────────────────────────────────────────

    def has_image(self) -> bool:
        return bool(self._cell.image_path)

    def cell(self) -> PhotoCell:
        return self._cell

    def set_pixmap(self, pixmap: QPixmap) -> bool:
        tmp_dir = os.path.join(tempfile.gettempdir(), "ectoform_report_photos")
        os.makedirs(tmp_dir, exist_ok=True)
        path = os.path.join(tmp_dir, f"photo_{int(time.time() * 1000)}.png")
        if not pixmap.save(path, "PNG"):
            return False
        self._cell.image_path = path
        self._apply_image(path)
        self.changed.emit()
        return True

    def lock(self):
        self._btn.setEnabled(False)
        self._del_btn.hide()
        self._comment.setReadOnly(True)


# ── Flow grid ─────────────────────────────────────────────────────────────────

class PhotoFlowWidget(QWidget):
    """
    Displays PhotoCardWidgets in a wrapping grid.
    A '+' add-card button always appears after the last card.
    When a row fills up, the next card wraps to the line below.
    """

    changed = pyqtSignal()

    CARD_W  = 150
    CARD_H  = PhotoCardWidget.PHOTO_H + PhotoCardWidget.COMMENT_H + 4 + 8  # total card height
    GAP     = 10

    def __init__(self, page: ReportPage, parent=None):
        super().__init__(parent)
        self._page  = page
        self._cards: List[PhotoCardWidget] = []
        self._locked = False

        self._hover = _HoverPreview()

        # "+" add button — same visual size as a card
        self._add_btn = QPushButton('+\nAdd photo')
        self._add_btn.setParent(self)
        self._add_btn.setCursor(Qt.PointingHandCursor)
        self._add_btn.setStyleSheet(f"""
            QPushButton {{
                background: #ffffff; border: 2px dashed {_ACCENT};
                border-radius: 6px; color: {_ACCENT}; font-size: 12px; font-weight: bold;
            }}
            QPushButton:hover {{ background: #eaf5fb; }}
        """)
        self._add_btn.clicked.connect(self._on_add)

        # Populate from model (flatten all photo_rows)
        cells = [cell for row in page.photo_rows for cell in row.photos]
        for cell in cells:
            self._make_card(cell, save=False)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    # ── Layout ────────────────────────────────────────────────────────────────

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self):
        w = self.width()
        if w <= 0:
            return
        cols = max(1, (w + self.GAP) // (self.CARD_W + self.GAP))
        all_items = list(self._cards) + ([self._add_btn] if not self._locked else [])

        for i, item in enumerate(all_items):
            r, c = divmod(i, cols)
            item.setGeometry(
                c * (self.CARD_W + self.GAP),
                r * (self.CARD_H + self.GAP),
                self.CARD_W,
                self.CARD_H,
            )
            item.show()

        rows = math.ceil(len(all_items) / cols) if all_items else 1
        self.setFixedHeight(rows * (self.CARD_H + self.GAP) + self.GAP)

    def sizeHint(self) -> QSize:
        return QSize(self.CARD_W * 4 + self.GAP * 3, self.CARD_H + self.GAP * 2)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _on_add(self):
        cell = PhotoCell()
        # Store as a new single-photo row in the model
        self._page.photo_rows.append(PhotoRow(photos=[cell]))
        self._make_card(cell, save=False)
        self._relayout()
        self.changed.emit()

    def _make_card(self, cell: PhotoCell, save: bool = True) -> PhotoCardWidget:
        card = PhotoCardWidget(cell, self._hover, parent=self)
        card.changed.connect(self.changed)
        card.delete_requested.connect(lambda c=card: self._remove_card(c))
        self._cards.append(card)
        if save:
            self._page.photo_rows.append(PhotoRow(photos=[cell]))
        card.show()
        return card

    def _remove_card(self, card: PhotoCardWidget):
        if card not in self._cards:
            return
        target_cell = card.cell()
        # Remove the cell from the model
        self._page.photo_rows = [
            row for row in self._page.photo_rows
            if not (len(row.photos) == 1 and row.photos[0] is target_cell)
        ]
        for row in self._page.photo_rows:
            if target_cell in row.photos:
                row.photos.remove(target_cell)
        self._cards.remove(card)
        card.hide()
        card.setParent(None)
        self._relayout()
        self.changed.emit()

    # ── Public API ────────────────────────────────────────────────────────────

    def add_screenshot(self, pixmap: QPixmap) -> bool:
        """Fill the first empty card, or add a new card if all are full."""
        # Find first card without an image
        for card in self._cards:
            if not card.has_image():
                return card.set_pixmap(pixmap)
        # All full — add a new card
        self._on_add()
        if self._cards:
            return self._cards[-1].set_pixmap(pixmap)
        return False

    def lock(self):
        self._locked = True
        self._add_btn.hide()
        for card in self._cards:
            card.lock()
        self._relayout()


# ── Backward-compat alias (used by page_widget import) ───────────────────────

PhotoRowWidget = PhotoFlowWidget  # keep old import working during transition

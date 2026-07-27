"""Section 5 — Inspiration / Idea / Direction card."""
import base64
from typing import List, Optional

from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QApplication,
)
from PyQt5.QtCore import Qt, QSize, QPoint, QBuffer, QIODevice
from PyQt5.QtGui import QPixmap, QIcon, QCursor


def _pixmap_to_b64(pix: QPixmap) -> str:
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    pix.save(buf, 'PNG')
    return base64.b64encode(bytes(buf.data())).decode()


def _b64_to_pixmap(b64: str) -> QPixmap:
    pix = QPixmap()
    pix.loadFromData(base64.b64decode(b64))
    return pix

from .shared import (
    _MUTED, _BORDER, _BORDER_L, _ACCENT, _ACCENT_H, _INPUT_BG,
    card, section_label, make_textarea, separator,
)
from i18n import t

_PHOTO_W = 160
_PHOTO_H = 130
_NUM_PHOTOS = 8   # 2 rows × 4 columns


_PHOTO_BTN_STYLE = f"""
    QPushButton {{
        background-color: {_INPUT_BG};
        border: 1.5px dashed {_BORDER_L};
        border-radius: 8px;
        color: {_MUTED}; font-size: 13px; font-weight: bold;
    }}
    QPushButton:hover {{
        border-color: {_ACCENT}; color: {_ACCENT};
        background-color: #eff6ff;
    }}
"""

_PHOTO_BTN_STYLE_FILLED = f"""
    QPushButton {{
        background-color: {_INPUT_BG};
        border: 1.5px solid {_BORDER};
        border-radius: 8px;
    }}
    QPushButton:hover {{
        border-color: {_ACCENT};
    }}
"""


class _HoverPreview(QFrame):
    """Frameless floating widget that shows an enlarged photo on hover."""

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
        preview = pixmap.scaled(680, 520, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._lbl.setPixmap(preview)
        self._lbl.setFixedSize(preview.size())
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


class _PhotoBtn(QPushButton):
    """Photo slot with hover-zoom preview."""

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


class InspirationCard(QFrame):
    """Section 5: Inspiration — textarea + 8 photo slots (2 rows × 4)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._photo_b64s: List[str] = [''] * _NUM_PHOTOS
        self._photo_btns:  List[_PhotoBtn] = []
        self._edit_enabled = True
        self._preview = _HoverPreview()

        c = card()
        layout = QVBoxLayout(c)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(section_label(t('project.brief.s5_title')))
        layout.addWidget(separator())

        hint = QLabel(t('project.brief.s5_hint'))
        hint.setStyleSheet(
            f'color: {_MUTED}; font-size: 13px; background: transparent; border: none;'
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # ── Compact text area ──────────────────────────────────────────────
        self._f_inspiration = make_textarea(t('project.brief.s5_ph'), min_height=70)
        self._f_inspiration.setMaximumHeight(100)
        layout.addWidget(self._f_inspiration)

        # ── 2 rows × 4 photo slots ─────────────────────────────────────────
        for row_start in (0, 4):
            photos_row = QHBoxLayout()
            photos_row.setSpacing(10)
            photos_row.setContentsMargins(0, 4 if row_start == 0 else 0, 0, 0)
            for i in range(row_start, row_start + 4):
                btn = _PhotoBtn(self._preview)
                btn.setText(f'＋\n{t("project.brief.s5_add_photo")}')
                btn.setFixedSize(_PHOTO_W, _PHOTO_H)
                btn.setCursor(Qt.PointingHandCursor)
                btn.setStyleSheet(_PHOTO_BTN_STYLE)
                btn.clicked.connect(lambda _, idx=i: self._upload_photo(idx))
                photos_row.addWidget(btn)
                self._photo_btns.append(btn)
            layout.addLayout(photos_row)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(c)

    # ── photo handling ─────────────────────────────────────────────────────

    def _upload_photo(self, idx: int):
        if not self._edit_enabled:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, t('project.brief.s5_select_photo'), '',
            'Images (*.png *.jpg *.jpeg *.webp)'
        )
        if path:
            pix = QPixmap(path)
            if not pix.isNull():
                self._photo_b64s[idx] = _pixmap_to_b64(pix)
                self._apply_photo(idx, pix)

    def _apply_photo(self, idx: int, pix: QPixmap):
        btn = self._photo_btns[idx]
        scaled = pix.scaled(
            QSize(_PHOTO_W, _PHOTO_H), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
        )
        btn.setIcon(QIcon(scaled))
        btn.setIconSize(QSize(_PHOTO_W, _PHOTO_H))
        btn.setText('')
        btn.setStyleSheet(_PHOTO_BTN_STYLE_FILLED)
        btn.set_orig_pixmap(pix)

    def _clear_photo(self, idx: int):
        btn = self._photo_btns[idx]
        btn.setIcon(QIcon())
        btn.setText(f'＋\n{t("project.brief.s5_add_photo")}')
        btn.setStyleSheet(_PHOTO_BTN_STYLE)
        btn.set_orig_pixmap(None)

    # ── public API ─────────────────────────────────────────────────────────

    def set_edit_mode(self, enabled: bool):
        self._edit_enabled = enabled
        self._f_inspiration.setReadOnly(not enabled)
        for btn in self._photo_btns:
            btn.setEnabled(enabled)

    def get_data(self) -> dict:
        return {
            'inspiration': self._f_inspiration.toPlainText(),
            'photo_b64s':  list(self._photo_b64s),
        }

    def set_data(self, data: dict):
        self._f_inspiration.setPlainText(data.get('inspiration', ''))
        b64s = data.get('photo_b64s', [])
        if not b64s:
            # backward compat: old files stored file paths
            old_paths = data.get('photo_paths', [])
            for i in range(_NUM_PHOTOS):
                path = old_paths[i] if i < len(old_paths) else ''
                self._photo_b64s[i] = ''
                if path:
                    pix = QPixmap(path)
                    if not pix.isNull():
                        self._photo_b64s[i] = _pixmap_to_b64(pix)
                        self._apply_photo(i, pix)
                        continue
                # Every branch above either fills a slot or falls through to
                # here — without this, a slot that had a photo in the
                # previous project (e.g. New Project resetting to none)
                # kept showing it, since _apply_photo was only ever called,
                # never its inverse.
                self._clear_photo(i)
            return
        for i in range(_NUM_PHOTOS):
            b64 = b64s[i] if i < len(b64s) else ''
            self._photo_b64s[i] = b64
            if b64:
                pix = _b64_to_pixmap(b64)
                if not pix.isNull():
                    self._apply_photo(i, pix)
                    continue
            self._clear_photo(i)

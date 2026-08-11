"""Section 1 — Product Overview card."""
from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QSizePolicy, QTextEdit,
)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPixmap, QIcon

from core.image_utils import path_to_b64, b64_to_pixmap
from .shared import (
    _MUTED, _INPUT_BG, _BORDER_L, _BORDER, _ACCENT, _TEXT,
    card, section_label, make_input, separator,
)
from i18n import t

_IMG_W = 290

_IMG_BTN_STYLE = f"""
    QPushButton {{
        background-color: {_INPUT_BG};
        border: 1.5px dashed {_BORDER_L};
        border-radius: 8px;
        color: {_MUTED}; font-size: 11px; font-weight: bold;
    }}
    QPushButton:hover {{
        border-color: {_ACCENT}; color: {_ACCENT};
        background-color: #eff6ff;
    }}
"""

_TEXTAREA_STYLE = f"""
    QTextEdit {{
        background: {_INPUT_BG};
        border: 1px solid {_BORDER};
        border-radius: 8px;
        color: {_TEXT};
        font-size: 13px;
        padding: 8px 10px;
    }}
    QTextEdit:focus {{
        border-color: {_ACCENT};
        background: #ffffff;
    }}
"""


class ProductOverviewCard(QFrame):
    """Section 1: Product Overview — image left, fields right (4 fields)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image_b64: str = ''
        c = card()
        layout = QVBoxLayout(c)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(section_label(t('project.brief.s1_title')))
        layout.addWidget(separator())
        layout.addLayout(self._build_body())

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(c)

    def _build_body(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(20)
        row.setContentsMargins(0, 0, 0, 0)

        # ── Left: image upload — fixed width, stretches to match right column ──
        self._img_btn = QPushButton(t('project.brief.s1_add_image'))
        self._img_btn.setFixedWidth(_IMG_W)
        self._img_btn.setMinimumHeight(280)
        self._img_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self._img_btn.setCursor(Qt.PointingHandCursor)
        self._img_btn.setStyleSheet(_IMG_BTN_STYLE)
        self._img_btn.clicked.connect(self._upload_image)
        row.addWidget(self._img_btn)

        # ── Right: 4 fields ────────────────────────────────────────────────
        fields_col = QVBoxLayout()
        fields_col.setSpacing(6)
        fields_col.setContentsMargins(0, 0, 0, 0)

        for label_key, attr in [
            ('project.brief.s1_product_name', '_f_product_name'),
            ('project.brief.s1_reference',    '_f_reference'),
        ]:
            lbl = QLabel(t(label_key))
            lbl.setStyleSheet(
                f'color: {_MUTED}; font-size: 13px; background: transparent; border: none;'
            )
            inp = make_input(t(label_key))
            inp.setMinimumHeight(36)
            setattr(self, attr, inp)
            fields_col.addWidget(lbl)
            fields_col.addWidget(inp)

        # Description — expanding textarea (takes up remaining height)
        desc_lbl = QLabel(t('project.brief.s1_description'))
        desc_lbl.setStyleSheet(
            f'color: {_MUTED}; font-size: 13px; background: transparent; border: none;'
        )
        self._f_description = QTextEdit()
        self._f_description.setPlaceholderText(t('project.brief.s1_description'))
        self._f_description.setStyleSheet(_TEXTAREA_STYLE)
        self._f_description.setMinimumHeight(120)
        self._f_description.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        fields_col.addWidget(desc_lbl)
        fields_col.addWidget(self._f_description, 1)

        # Visual links
        vis_lbl = QLabel(t('project.brief.s1_visual_links'))
        vis_lbl.setStyleSheet(
            f'color: {_MUTED}; font-size: 13px; background: transparent; border: none;'
        )
        self._f_visual_links = make_input(t('project.brief.s1_visual_links'))
        self._f_visual_links.setMinimumHeight(36)
        fields_col.addWidget(vis_lbl)
        fields_col.addWidget(self._f_visual_links)

        row.addLayout(fields_col, 1)
        return row

    # ── image ──────────────────────────────────────────────────────────────

    def _upload_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, t('project.brief.s1_select_image'), '',
            'Images (*.png *.jpg *.jpeg *.webp)'
        )
        if path:
            self.set_image_from_path(path)

    def _apply_image(self, pix: QPixmap):
        w = self._img_btn.width() or _IMG_W
        h = self._img_btn.height() or 280
        scaled = pix.scaled(QSize(w, h), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._img_btn.setIcon(QIcon(scaled))
        self._img_btn.setIconSize(QSize(w, h))
        self._img_btn.setText('')

    # ── public API ─────────────────────────────────────────────────────────

    def set_edit_mode(self, enabled: bool):
        self._img_btn.setEnabled(enabled)
        self._f_description.setReadOnly(not enabled)
        for attr in ('_f_product_name', '_f_reference', '_f_visual_links'):
            getattr(self, attr).setReadOnly(not enabled)

    def set_image_from_path(self, path: str):
        """Load image from disk, embed as base64. Used for direct uploads
        and as a backward-compat fallback for pre-embedding saves."""
        b64 = path_to_b64(path)
        if b64:
            self.set_image_from_b64(b64)

    def set_image_from_b64(self, b64: str):
        """Adopt an already-base64-encoded image directly — used by the
        sidebar photo auto-fill, which stores base64 too now, so no
        path/re-encode round-trip is needed."""
        pix = b64_to_pixmap(b64)
        if pix is not None:
            self._image_b64 = b64
            self._apply_image(pix)

    def clear_image(self):
        self._image_b64 = ''
        self._img_btn.setIcon(QIcon())
        self._img_btn.setText(t('project.brief.s1_add_image'))

    def get_data(self) -> dict:
        return {
            'product_name': self._f_product_name.text(),
            'reference':    self._f_reference.text(),
            'description':  self._f_description.toPlainText(),
            'intended_use': '',
            'visual_links': self._f_visual_links.text(),
            'image_b64':    self._image_b64,
        }

    def set_data(self, data: dict):
        self._f_product_name.setText(data.get('product_name', ''))
        self._f_reference.setText(data.get('reference', ''))
        self._f_description.setPlainText(data.get('description', ''))
        self._f_visual_links.setText(data.get('visual_links', ''))
        b64 = data.get('image_b64', '')
        if not b64:
            # backward compat: old files stored a file path
            old_path = data.get('image_path', '')
            if old_path:
                self.set_image_from_path(old_path)
            else:
                # Without this, loading/new-project data with no image left
                # the *previous* project's image still showing — the icon
                # on _img_btn was never cleared, only re-set when truthy.
                self.clear_image()
            return
        pix = b64_to_pixmap(b64)
        if pix is not None:
            self._image_b64 = b64
            self._apply_image(pix)

"""Section 1 — Product Overview card."""
from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog, QSizePolicy,
)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPixmap, QIcon
from .shared import (
    _MUTED, _INPUT_BG, _BORDER_L, _BORDER, _ACCENT, _ACCENT_H, _TEXT,
    ADD_BTN_STYLE, card, section_label, field_label, make_input, separator,
)

_IMG_W = 280
_IMG_H = 360

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


class ProductOverviewCard(QFrame):
    """Section 1: Product Overview — image left, fields right."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image_path: str = ''
        c = card()
        layout = QVBoxLayout(c)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(section_label('1. Product Overview'))
        layout.addWidget(separator())
        layout.addLayout(self._build_body())

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(c)

    def _build_body(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(16)
        row.setContentsMargins(0, 0, 0, 0)

        # ── Left: image upload button ──────────────────────────────────────
        self._img_btn = QPushButton('+ Add Image')
        self._img_btn.setFixedSize(_IMG_W, _IMG_H)
        self._img_btn.setCursor(Qt.PointingHandCursor)
        self._img_btn.setStyleSheet(_IMG_BTN_STYLE)
        self._img_btn.clicked.connect(self._upload_image)
        row.addWidget(self._img_btn, 0, Qt.AlignTop)

        # ── Right: fields stacked vertically ──────────────────────────────
        fields_col = QVBoxLayout()
        fields_col.setSpacing(8)
        fields_col.setContentsMargins(0, 0, 0, 0)

        defs = [
            ('Product name',           '_f_product_name'),
            ('Reference / Version',    '_f_reference'),
            ('Short description',      '_f_description'),
            ('Intended use',           '_f_intended_use'),
            ('Image / Visual (links)', '_f_visual_links'),
        ]
        for label, attr in defs:
            lbl = QLabel(label)
            lbl.setStyleSheet(
                f'color: {_MUTED}; font-size: 10px; background: transparent; border: none;'
            )
            inp = make_input(label)
            setattr(self, attr, inp)
            fields_col.addWidget(lbl)
            fields_col.addWidget(inp)

        fields_col.addStretch()
        row.addLayout(fields_col, 1)
        return row

    # ── image ──────────────────────────────────────────────────────────────

    def _upload_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select Product Image', '',
            'Images (*.png *.jpg *.jpeg *.webp)'
        )
        if path:
            pix = QPixmap(path)
            if not pix.isNull():
                self._image_path = path
                self._apply_image(pix)

    def _apply_image(self, pix: QPixmap):
        scaled = pix.scaled(
            QSize(_IMG_W, _IMG_H), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self._img_btn.setIcon(QIcon(scaled))
        self._img_btn.setIconSize(QSize(_IMG_W, _IMG_H))
        self._img_btn.setText('')

    # ── public API ─────────────────────────────────────────────────────────

    def set_edit_mode(self, enabled: bool):
        self._img_btn.setEnabled(enabled)
        for attr in ('_f_product_name', '_f_reference', '_f_description',
                     '_f_intended_use', '_f_visual_links'):
            getattr(self, attr).setReadOnly(not enabled)

    def get_data(self) -> dict:
        return {
            'product_name': self._f_product_name.text(),
            'reference':    self._f_reference.text(),
            'description':  self._f_description.text(),
            'intended_use': self._f_intended_use.text(),
            'visual_links': self._f_visual_links.text(),
            'image_path':   self._image_path,
        }

    def set_data(self, data: dict):
        self._f_product_name.setText(data.get('product_name', ''))
        self._f_reference.setText(data.get('reference', ''))
        self._f_description.setText(data.get('description', ''))
        self._f_intended_use.setText(data.get('intended_use', ''))
        self._f_visual_links.setText(data.get('visual_links', ''))
        path = data.get('image_path', '')
        if path:
            pix = QPixmap(path)
            if not pix.isNull():
                self._image_path = path
                self._apply_image(pix)

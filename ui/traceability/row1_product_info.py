"""Row 1: Main product info bar (auto-filled from global project data)."""
from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFileDialog, QInputDialog,
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QPixmap, QIcon
from ui.styles import make_font
from .shared import _CARD, _BORDER, _TEXT, _MUTED, _ACCENT, _STATUS_COLORS
from .shared import _ProgressBar


class _ProductInfoRow(QFrame):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._planned_launch     = ''
        self._overall_progress   = 0
        self._product_image_path = ''
        self.setFixedHeight(108)
        self.setStyleSheet(f'background: {_CARD}; border-bottom: 1px solid {_BORDER};')
        self._build()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 8, 16, 8)
        root.setSpacing(14)

        # Photo button
        self._img_btn = QPushButton('＋\nPhoto')
        self._img_btn.setFixedSize(72, 72)
        self._img_btn.setStyleSheet(f"""
            QPushButton {{
                background: #f1f3f5; border: 2px dashed {_BORDER};
                border-radius: 8px; color: {_MUTED}; font-size: 9px;
            }}
            QPushButton:hover {{ border-color: {_ACCENT}; background: #e8f0fe; }}
        """)
        self._img_btn.setCursor(Qt.PointingHandCursor)
        self._img_btn.clicked.connect(self._upload_image)
        root.addWidget(self._img_btn)

        # Name / reference / PM / launch block
        left = QVBoxLayout(); left.setSpacing(1)
        mp = QLabel('Main Product')
        mp.setStyleSheet(f'color: {_MUTED}; font-size: 9px; background: transparent; border: none;')
        left.addWidget(mp)

        self._name_lbl = QLabel('—')
        self._name_lbl.setFont(make_font(size=14, bold=True))
        self._name_lbl.setStyleSheet(f'color: {_TEXT}; background: transparent; border: none;')
        left.addWidget(self._name_lbl)

        meta_row = QHBoxLayout(); meta_row.setSpacing(14)
        self._ref_lbl    = self._meta_lbl('Reference  —')
        self._pm_lbl     = self._meta_lbl('Project Manager  —')
        self._launch_lbl = self._meta_lbl('Planned Launch  —')
        self._launch_lbl.setCursor(Qt.PointingHandCursor)
        self._launch_lbl.setToolTip('Click to edit')
        self._launch_lbl.mousePressEvent = lambda _: self._edit('planned_launch')
        for lbl in (self._ref_lbl, self._pm_lbl, self._launch_lbl):
            meta_row.addWidget(lbl)
        meta_row.addStretch()
        left.addLayout(meta_row)
        root.addLayout(left, 2)

        root.addWidget(self._vdiv())

        self._start_lbl = self._info_col_val('—')
        root.addLayout(self._info_col('Start Date', self._start_lbl))
        root.addWidget(self._vdiv())

        self._dd_lbl = self._info_col_val('—')
        root.addLayout(self._info_col('Due Date', self._dd_lbl))
        root.addWidget(self._vdiv())

        self._status_lbl = self._info_col_val('—')
        root.addLayout(self._info_col('Global Status', self._status_lbl))
        root.addWidget(self._vdiv())

        # Overall progress (editable)
        pc = QVBoxLayout(); pc.setSpacing(3); pc.setAlignment(Qt.AlignVCenter)
        pt = QLabel('Overall Progress')
        pt.setStyleSheet(f'color: {_MUTED}; font-size: 8px; background: transparent; border: none;')
        pc.addWidget(pt)
        self._prog_lbl = QLabel('0 %')
        self._prog_lbl.setFont(make_font(size=15, bold=True))
        self._prog_lbl.setStyleSheet(f'color: {_TEXT}; background: transparent; border: none;')
        self._prog_lbl.setCursor(Qt.PointingHandCursor)
        self._prog_lbl.setToolTip('Click to edit progress')
        self._prog_lbl.mousePressEvent = lambda _: self._edit('progress')
        pc.addWidget(self._prog_lbl)
        self._prog_bar = _ProgressBar(0); self._prog_bar.setFixedSize(80, 6)
        pc.addWidget(self._prog_bar)
        root.addLayout(pc)

    @staticmethod
    def _meta_lbl(text: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet(f'color: {_MUTED}; font-size: 9px; background: transparent; border: none;')
        return l

    @staticmethod
    def _info_col_val(value: str) -> QLabel:
        l = QLabel(value)
        l.setFont(make_font(size=10, bold=True))
        l.setStyleSheet(f'color: {_TEXT}; background: transparent; border: none;')
        return l

    @staticmethod
    def _info_col(title: str, val_lbl: QLabel) -> QVBoxLayout:
        lay = QVBoxLayout(); lay.setSpacing(3); lay.setAlignment(Qt.AlignVCenter)
        t = QLabel(title)
        t.setStyleSheet(f'color: {_MUTED}; font-size: 8px; background: transparent; border: none;')
        lay.addWidget(t); lay.addWidget(val_lbl)
        return lay

    @staticmethod
    def _vdiv() -> QFrame:
        v = QFrame(); v.setFrameShape(QFrame.VLine); v.setFixedHeight(58)
        v.setStyleSheet(f'color: {_BORDER}; background: {_BORDER}; max-width: 1px; border: none;')
        return v

    def _upload_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select Product Image', '', 'Images (*.png *.jpg *.jpeg *.webp)'
        )
        if path:
            self._product_image_path = path
            pix = QPixmap(path)
            if not pix.isNull():
                self._img_btn.setIcon(QIcon(pix.scaled(68, 68, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
                self._img_btn.setIconSize(QSize(68, 68))
                self._img_btn.setText('')
            self.changed.emit()

    def _edit(self, field: str):
        if field == 'planned_launch':
            val, ok = QInputDialog.getText(
                self, 'Edit Planned Launch', 'Planned Launch:', text=self._planned_launch
            )
            if ok:
                self._planned_launch = val.strip()
                self._launch_lbl.setText(f'Planned Launch  {val.strip() or "—"}')
                self.changed.emit()
        elif field == 'progress':
            val, ok = QInputDialog.getText(
                self, 'Edit Overall Progress', 'Overall Progress (0–100):',
                text=str(self._overall_progress)
            )
            if ok:
                try:
                    v = max(0, min(100, int(val)))
                    self._overall_progress = v
                    self._prog_lbl.setText(f'{v} %')
                    self._prog_bar.set_value(v)
                    self.changed.emit()
                except ValueError:
                    pass

    def update_project_info(self, info: dict):
        self._name_lbl.setText(info.get('title') or '—')
        self._ref_lbl.setText(f"Reference  {info.get('number') or '—'}")
        self._pm_lbl.setText(f"Project Manager  {info.get('company') or '—'}")
        self._start_lbl.setText(info.get('start_date') or '—')
        self._dd_lbl.setText(info.get('due_date') or '—')
        status = info.get('status', '')
        self._status_lbl.setText(status or '—')
        color = _STATUS_COLORS.get(status, _MUTED)
        self._status_lbl.setStyleSheet(
            f'color: {color}; font-size: 10px; font-weight: bold; background: transparent; border: none;'
        )
        photo = info.get('photo_path', '')
        if photo and photo != self._product_image_path:
            pix = QPixmap(photo)
            if not pix.isNull():
                self._product_image_path = photo
                self._img_btn.setIcon(QIcon(pix.scaled(68, 68, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
                self._img_btn.setIconSize(QSize(68, 68))
                self._img_btn.setText('')

    def get_extra_data(self) -> dict:
        return {
            'planned_launch':     self._planned_launch,
            'overall_progress':   self._overall_progress,
            'product_image_path': self._product_image_path,
        }

    def set_extra_data(self, data: dict):
        self._planned_launch   = data.get('planned_launch', '')
        self._overall_progress = data.get('overall_progress', 0)
        self._product_image_path = data.get('product_image_path', '')
        self._launch_lbl.setText(f'Planned Launch  {self._planned_launch or "—"}')
        self._prog_lbl.setText(f'{self._overall_progress} %')
        self._prog_bar.set_value(self._overall_progress)
        if self._product_image_path:
            pix = QPixmap(self._product_image_path)
            if not pix.isNull():
                self._img_btn.setIcon(QIcon(pix.scaled(68, 68, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
                self._img_btn.setIconSize(QSize(68, 68))
                self._img_btn.setText('')

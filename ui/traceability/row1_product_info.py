"""Row 1: Main product info bar (auto-filled from global project data)."""
from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFileDialog, QInputDialog,
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QPixmap, QIcon
from ui.styles import make_font
from .shared import _CARD, _BORDER, _TEXT, _MUTED, _ACCENT, _STATUS_COLORS, _TOOLTIP_STYLE
from .shared import _ProgressBar

_LAUNCH_TOOLTIP = f"""
    QLabel {{
        background: transparent;
        border: none;
    }}
""" + _TOOLTIP_STYLE

_PROG_LABEL_STYLE = f"""
    QLabel {{
        color: {_ACCENT};
        background: transparent;
        border: none;
    }}
""" + _TOOLTIP_STYLE

_IMG_SIZE = 130


class _ProductInfoRow(QFrame):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._planned_launch     = ''
        self._overall_progress   = 0
        self._product_image_path = ''
        self.setFixedHeight(152)
        self.setStyleSheet(f'background: {_CARD}; border-bottom: 1px solid {_BORDER};')
        self._build()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 10, 0, 10)
        root.setSpacing(16)

        root.addSpacing(60)   # left free space

        # Photo button — large, rounded
        self._img_btn = QPushButton('＋\nPhoto')
        self._img_btn.setFixedSize(_IMG_SIZE, _IMG_SIZE)
        self._img_btn.setStyleSheet(f"""
            QPushButton {{
                background: #f1f3f5; border: 2px dashed {_BORDER};
                border-radius: 12px; color: {_MUTED}; font-size: 9px;
            }}
            QPushButton:hover {{ border-color: {_ACCENT}; background: #e8f0fe; }}
        """)
        self._img_btn.setCursor(Qt.PointingHandCursor)
        self._img_btn.clicked.connect(self._upload_image)
        root.addWidget(self._img_btn)

        # Name / reference / PM / launch — each on its own line
        left = QVBoxLayout()
        left.setSpacing(3)
        left.setContentsMargins(4, 0, 0, 0)

        mp = QLabel('Main Product')
        mp.setStyleSheet(f'color: {_MUTED}; font-size: 9px; background: transparent; border: none;')
        left.addWidget(mp)

        self._name_lbl = QLabel('—')
        self._name_lbl.setFont(make_font(size=15, bold=True))
        self._name_lbl.setStyleSheet(f'color: {_TEXT}; background: transparent; border: none;')
        left.addWidget(self._name_lbl)

        self._ref_lbl    = self._meta_field('Reference', '—')
        self._pm_lbl     = self._meta_field('Project Manager', '—')
        self._launch_lbl = self._meta_field('Planned Launch', '—')
        self._launch_lbl.setStyleSheet(_LAUNCH_TOOLTIP)
        self._launch_lbl.setCursor(Qt.PointingHandCursor)
        self._launch_lbl.setToolTip('Click to edit')
        self._launch_lbl.mousePressEvent = lambda _: self._edit('planned_launch')

        left.addWidget(self._ref_lbl)
        left.addWidget(self._pm_lbl)
        left.addWidget(self._launch_lbl)
        left.addStretch()
        root.addLayout(left)

        root.addWidget(self._vdiv())

        # Start Date with calendar icon
        self._start_lbl = self._date_val('—')
        root.addLayout(self._info_col('📅  Start Date', self._start_lbl))
        root.addWidget(self._vdiv())

        # Due Date with calendar icon
        self._dd_lbl = self._date_val('—')
        root.addLayout(self._info_col('📅  Due Date', self._dd_lbl))
        root.addWidget(self._vdiv())

        # Global Status — pill badge
        sc = QVBoxLayout(); sc.setSpacing(6); sc.setAlignment(Qt.AlignVCenter)
        st_title = QLabel('Global Status')
        st_title.setStyleSheet(f'color: {_MUTED}; font-size: 8px; background: transparent; border: none;')
        sc.addWidget(st_title)
        self._status_lbl = QLabel('—')
        self._status_lbl.setFont(make_font(size=9, bold=True))
        self._status_lbl.setStyleSheet(
            f'color: {_MUTED}; background: transparent; border: none; padding: 0px;'
        )
        sc.addWidget(self._status_lbl)
        root.addLayout(sc)
        root.addWidget(self._vdiv())

        # Overall progress (editable)
        pc = QVBoxLayout(); pc.setSpacing(4); pc.setAlignment(Qt.AlignVCenter)
        pt = QLabel('Overall Progress')
        pt.setStyleSheet(f'color: {_MUTED}; font-size: 8px; background: transparent; border: none;')
        pc.addWidget(pt)
        self._prog_lbl = QLabel('0 %')
        self._prog_lbl.setFont(make_font(size=20, bold=True))
        self._prog_lbl.setStyleSheet(_PROG_LABEL_STYLE)
        self._prog_lbl.setCursor(Qt.PointingHandCursor)
        self._prog_lbl.setToolTip('Click to edit progress')
        self._prog_lbl.mousePressEvent = lambda _: self._edit('progress')
        pc.addWidget(self._prog_lbl)
        self._prog_bar = _ProgressBar(0)
        self._prog_bar.setFixedSize(100, 7)
        pc.addWidget(self._prog_bar)
        root.addLayout(pc)

        root.addSpacing(60)   # right free space

    @staticmethod
    def _meta_field(label: str, value: str) -> QLabel:
        lbl = QLabel()
        lbl.setTextFormat(Qt.RichText)
        lbl.setText(
            f'<span style="color:{_MUTED}; font-size:10px;">{label}</span>'
            f'&nbsp;&nbsp;<b style="color:{_TEXT}; font-size:10px;">{value}</b>'
        )
        lbl.setStyleSheet('background: transparent; border: none;')
        return lbl

    @staticmethod
    def _date_val(value: str) -> QLabel:
        l = QLabel(value)
        l.setFont(make_font(size=11, bold=True))
        l.setStyleSheet(f'color: {_TEXT}; background: transparent; border: none;')
        return l

    @staticmethod
    def _info_col(title: str, val_lbl: QLabel) -> QVBoxLayout:
        lay = QVBoxLayout(); lay.setSpacing(5); lay.setAlignment(Qt.AlignVCenter)
        t = QLabel(title)
        t.setStyleSheet(f'color: {_MUTED}; font-size: 8px; background: transparent; border: none;')
        lay.addWidget(t)
        lay.addWidget(val_lbl)
        return lay

    @staticmethod
    def _vdiv() -> QFrame:
        v = QFrame(); v.setFrameShape(QFrame.VLine); v.setFixedHeight(90)
        v.setStyleSheet(f'color: {_BORDER}; background: {_BORDER}; max-width: 1px; border: none;')
        return v

    def _apply_image(self, path: str):
        pix = QPixmap(path)
        if not pix.isNull():
            scaled = pix.scaled(_IMG_SIZE, _IMG_SIZE, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            self._img_btn.setIcon(QIcon(scaled))
            self._img_btn.setIconSize(QSize(_IMG_SIZE, _IMG_SIZE))
            self._img_btn.setText('')
            self._img_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; border: none;
                    border-radius: 12px;
                }}
                QPushButton:hover {{ border: 2px solid {_ACCENT}; }}
            """)

    def _upload_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select Product Image', '', 'Images (*.png *.jpg *.jpeg *.webp)'
        )
        if path:
            self._product_image_path = path
            self._apply_image(path)
            self.changed.emit()

    def _edit(self, field: str):
        if field == 'planned_launch':
            val, ok = QInputDialog.getText(
                self, 'Edit Planned Launch', 'Planned Launch:', text=self._planned_launch
            )
            if ok:
                self._planned_launch = val.strip()
                self._set_launch_text(self._planned_launch or '—')
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

    def _set_launch_text(self, value: str):
        self._launch_lbl.setText(
            f'<span style="color:{_MUTED}; font-size:10px;">Planned Launch</span>'
            f'&nbsp;&nbsp;<b style="color:{_TEXT}; font-size:10px;">{value}</b>'
        )

    def _set_status_pill(self, status: str):
        if status and status != '—':
            color = _STATUS_COLORS.get(status, _MUTED)
            bg = color + '22'
            self._status_lbl.setText(status)
            self._status_lbl.setStyleSheet(
                f'color: {color}; background: {bg}; border: 1px solid {color}44;'
                f'border-radius: 9px; padding: 2px 10px; font-size: 9px; font-weight: bold;'
            )
        else:
            self._status_lbl.setText('—')
            self._status_lbl.setStyleSheet(
                f'color: {_MUTED}; background: transparent; border: none; padding: 0px;'
            )

    def update_project_info(self, info: dict):
        self._name_lbl.setText(info.get('title') or '—')

        ref = info.get('number') or '—'
        self._ref_lbl.setText(
            f'<span style="color:{_MUTED}; font-size:10px;">Reference</span>'
            f'&nbsp;&nbsp;<b style="color:{_TEXT}; font-size:10px;">{ref}</b>'
        )

        pm = info.get('company') or '—'
        self._pm_lbl.setText(
            f'<span style="color:{_MUTED}; font-size:10px;">Project Manager</span>'
            f'&nbsp;&nbsp;<b style="color:{_TEXT}; font-size:10px;">{pm}</b>'
        )

        self._start_lbl.setText(info.get('start_date') or '—')
        self._dd_lbl.setText(info.get('due_date') or '—')

        status = info.get('status', '')
        self._set_status_pill(status or '—')

        photo = info.get('photo_path', '')
        if photo and photo != self._product_image_path:
            self._product_image_path = photo
            self._apply_image(photo)

    def get_extra_data(self) -> dict:
        return {
            'planned_launch':     self._planned_launch,
            'overall_progress':   self._overall_progress,
            'product_image_path': self._product_image_path,
        }

    def set_extra_data(self, data: dict):
        self._planned_launch     = data.get('planned_launch', '')
        self._overall_progress   = data.get('overall_progress', 0)
        self._product_image_path = data.get('product_image_path', '')
        self._set_launch_text(self._planned_launch or '—')
        self._prog_lbl.setText(f'{self._overall_progress} %')
        self._prog_bar.set_value(self._overall_progress)
        if self._product_image_path:
            self._apply_image(self._product_image_path)

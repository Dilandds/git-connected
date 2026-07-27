"""Row 1: Main product info bar (auto-filled from global project data)."""
from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFileDialog, QLineEdit, QDialog,
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize, QEvent, QPoint
from PyQt5.QtGui import QPixmap, QIcon
from ui.styles import make_font
from .shared import _CARD, _BORDER, _TEXT, _MUTED, _ACCENT, _TOOLTIP_STYLE
from .shared import _ProgressBar
from i18n import t
# "Statut global" mirrors the project sidebar's own status field (info['status']
# is 'in_progress'/'awaiting'/'completed'/'cancelled'), not a traceability
# stage's status ('Upcoming'/'In Progress'/'Completed') — translate/color it
# against the project's own vocabulary instead of traceability/shared.py's.
from ui.project_widget import _STATUS_COLORS as _GLOBAL_STATUS_COLORS
from ui.project_widget import _STATUS_I18N as _GLOBAL_STATUS_I18N

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
        self._zoom_lbl = None   # lazily-created floating hover-zoom preview
        self.setFixedHeight(152)
        self.setStyleSheet(f'background: {_CARD}; border-bottom: 1px solid {_BORDER};')
        self._build()
        self._img_btn.installEventFilter(self)

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 10, 0, 10)
        root.setSpacing(16)

        root.addSpacing(60)   # left free space

        # Photo button — large, rounded
        self._img_btn = QPushButton(t('project.traceability.photo_btn'))
        self._img_btn.setFixedSize(_IMG_SIZE, _IMG_SIZE)
        self._img_btn.setStyleSheet(f"""
            QPushButton {{
                background: #f1f3f5; border: 2px dashed {_BORDER};
                border-radius: 12px; color: {_MUTED}; font-size: 11px;
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

        mp = QLabel(t('project.traceability.main_product'))
        mp.setStyleSheet(f'color: {_MUTED}; font-size: 11px; background: transparent; border: none;')
        left.addWidget(mp)

        self._name_lbl = QLabel('—')
        self._name_lbl.setFont(make_font(size=17, bold=True))
        self._name_lbl.setStyleSheet(f'color: {_TEXT}; background: transparent; border: none;')
        left.addWidget(self._name_lbl)

        self._ref_lbl    = self._meta_field(t('project.traceability.reference'), '—')
        self._pm_lbl     = self._meta_field(t('project.traceability.manager'), '—')
        self._launch_lbl = self._meta_field(t('project.traceability.planned_launch'), '—')
        self._launch_lbl.setStyleSheet(_LAUNCH_TOOLTIP)
        self._launch_lbl.setCursor(Qt.PointingHandCursor)
        self._launch_lbl.setToolTip(t('project.traceability.click_to_edit'))
        self._launch_lbl.mousePressEvent = lambda _: self._edit('planned_launch')

        left.addWidget(self._ref_lbl)
        left.addWidget(self._pm_lbl)
        left.addWidget(self._launch_lbl)
        left.addStretch()
        root.addLayout(left)

        root.addWidget(self._vdiv())

        # Start Date with calendar icon
        self._start_lbl = self._date_val('—')
        root.addLayout(self._info_col(t('project.traceability.start_date'), self._start_lbl))
        root.addWidget(self._vdiv())

        # Due Date with calendar icon
        self._dd_lbl = self._date_val('—')
        root.addLayout(self._info_col(t('project.traceability.due_date'), self._dd_lbl))
        root.addWidget(self._vdiv())

        # Global Status — pill badge
        sc = QVBoxLayout(); sc.setSpacing(6); sc.setAlignment(Qt.AlignVCenter)
        st_title = QLabel(t('project.traceability.global_status'))
        st_title.setStyleSheet(f'color: {_MUTED}; font-size: 10px; background: transparent; border: none;')
        sc.addWidget(st_title)
        self._status_lbl = QLabel('—')
        self._status_lbl.setFont(make_font(size=11, bold=True))
        self._status_lbl.setStyleSheet(
            f'color: {_MUTED}; background: transparent; border: none; padding: 0px;'
        )
        sc.addWidget(self._status_lbl)
        root.addLayout(sc)
        root.addWidget(self._vdiv())

        # Overall progress (editable)
        pc = QVBoxLayout(); pc.setSpacing(4); pc.setAlignment(Qt.AlignVCenter)
        pt = QLabel(t('project.traceability.overall_progress'))
        pt.setStyleSheet(f'color: {_MUTED}; font-size: 10px; background: transparent; border: none;')
        pc.addWidget(pt)
        self._prog_lbl = QLabel('0 %')
        self._prog_lbl.setFont(make_font(size=22, bold=True))
        self._prog_lbl.setStyleSheet(_PROG_LABEL_STYLE)
        self._prog_lbl.setCursor(Qt.PointingHandCursor)
        self._prog_lbl.setToolTip(t('project.traceability.click_edit_progress'))
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
            f'<span style="color:{_MUTED}; font-size: 12px;">{label}</span>'
            f'&nbsp;&nbsp;<b style="color:{_TEXT}; font-size: 12px;">{value}</b>'
        )
        lbl.setStyleSheet('background: transparent; border: none;')
        return lbl

    @staticmethod
    def _date_val(value: str) -> QLabel:
        l = QLabel(value)
        l.setFont(make_font(size=13, bold=True))
        l.setStyleSheet(f'color: {_TEXT}; background: transparent; border: none;')
        return l

    @staticmethod
    def _info_col(title: str, val_lbl: QLabel) -> QVBoxLayout:
        lay = QVBoxLayout(); lay.setSpacing(5); lay.setAlignment(Qt.AlignVCenter)
        t = QLabel(title)
        t.setStyleSheet(f'color: {_MUTED}; font-size: 10px; background: transparent; border: none;')
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

    def _clear_image(self):
        self._img_btn.setIcon(QIcon())
        self._img_btn.setText(t('project.traceability.photo_btn'))
        self._img_btn.setStyleSheet(f"""
            QPushButton {{
                background: #f1f3f5; border: 2px dashed {_BORDER};
                border-radius: 12px; color: {_MUTED}; font-size: 11px;
            }}
            QPushButton:hover {{ border-color: {_ACCENT}; background: #e8f0fe; }}
        """)

    def _upload_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select Product Image', '', 'Images (*.png *.jpg *.jpeg *.webp)'
        )
        if path:
            self._product_image_path = path
            self._apply_image(path)
            self.changed.emit()

    # ── hover-zoom preview ───────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        if obj is self._img_btn:
            if event.type() == QEvent.Enter and self._product_image_path:
                self._show_zoom_preview()
            elif event.type() == QEvent.Leave:
                self._hide_zoom_preview()
        return super().eventFilter(obj, event)

    def _show_zoom_preview(self):
        """Float an enlarged copy of the product photo next to the thumbnail
        while the mouse hovers over it."""
        pix = QPixmap(self._product_image_path)
        if pix.isNull():
            return
        scaled = pix.scaled(320, 320, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if self._zoom_lbl is None:
            self._zoom_lbl = QLabel(None, Qt.ToolTip | Qt.FramelessWindowHint)
            self._zoom_lbl.setStyleSheet(f"""
                QLabel {{
                    background: {_CARD};
                    border: 2px solid {_ACCENT};
                    border-radius: 8px;
                    padding: 4px;
                }}
            """)
        self._zoom_lbl.setPixmap(scaled)
        self._zoom_lbl.adjustSize()
        pos = self._img_btn.mapToGlobal(QPoint(self._img_btn.width() + 14, 0))
        self._zoom_lbl.move(pos)
        self._zoom_lbl.show()
        self._zoom_lbl.raise_()

    def _hide_zoom_preview(self):
        if self._zoom_lbl is not None:
            self._zoom_lbl.hide()

    def _edit(self, field: str):
        from ui.modal_utils import FormModal
        if field == 'planned_launch':
            dlg = FormModal(self, t('project.traceability.edit_launch_title'), min_width=340)
            f = dlg.add_hfield(t('project.traceability.planned_launch'), QLineEdit(self._planned_launch))
            f.setPlaceholderText(t('project.traceability.launch_ph'))
            dlg.finish()
            f.setFocus()
            if dlg.exec_() == QDialog.Accepted and f.text().strip() is not None:
                self._planned_launch = f.text().strip()
                self._set_launch_text(self._planned_launch or '—')
                self.changed.emit()
        elif field == 'progress':
            dlg = FormModal(self, t('project.traceability.edit_progress_title'), min_width=300)
            f = dlg.add_hfield(t('project.traceability.progress_field'), QLineEdit(str(self._overall_progress)))
            f.setPlaceholderText('0 – 100')
            dlg.finish()
            f.setFocus()
            if dlg.exec_() == QDialog.Accepted:
                try:
                    v = max(0, min(100, int(f.text())))
                    self._overall_progress = v
                    self._prog_lbl.setText(f'{v} %')
                    self._prog_bar.set_value(v)
                    self.changed.emit()
                except ValueError:
                    pass

    def _set_launch_text(self, value: str):
        self._launch_lbl.setText(
            f'<span style="color:{_MUTED}; font-size: 12px;">{t("project.traceability.planned_launch")}</span>'
            f'&nbsp;&nbsp;<b style="color:{_TEXT}; font-size: 12px;">{value}</b>'
        )

    def _set_status_pill(self, status: str):
        if status and status != '—':
            color = _GLOBAL_STATUS_COLORS.get(status, _MUTED)
            bg = color + '22'
            i18n_key = _GLOBAL_STATUS_I18N.get(status)
            self._status_lbl.setText(t(i18n_key) if i18n_key else status)
            self._status_lbl.setStyleSheet(
                f'color: {color}; background: {bg}; border: 1px solid {color}44;'
                f'border-radius: 9px; padding: 2px 10px; font-size: 11px; font-weight: bold;'
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
            f'<span style="color:{_MUTED}; font-size: 12px;">{t("project.traceability.reference")}</span>'
            f'&nbsp;&nbsp;<b style="color:{_TEXT}; font-size: 12px;">{ref}</b>'
        )

        pm = info.get('project_manager') or '—'
        self._pm_lbl.setText(
            f'<span style="color:{_MUTED}; font-size: 12px;">{t("project.traceability.manager")}</span>'
            f'&nbsp;&nbsp;<b style="color:{_TEXT}; font-size: 12px;">{pm}</b>'
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
        else:
            # _apply_image was only ever called when truthy — without this,
            # New Project / opening a project with no image left the
            # previous project's photo still showing on the button.
            self._clear_image()

"""
R&D — Textures & Materials tab
Three-panel layout: component list | proposal card grid | selection + brief
"""
import uuid
import os
import tempfile
from dataclasses import dataclass, field, asdict
from datetime import date as _date_cls
from typing import List, Optional, Tuple

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QComboBox, QTextEdit, QFileDialog,
    QLineEdit, QGridLayout, QSizePolicy, QDialog, QMenu,
    QAction, QTabWidget, QApplication,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap, QColor, QPainter, QBrush, QPen, QPalette

from ui.styles import default_theme
from ui.modal_utils import FormModal
from i18n import t

# ── Palette ───────────────────────────────────────────────────────────────────
_CARD     = '#ffffff'
_BG       = '#f4f6f9'
_TEXT     = '#1a2033'
_MUTED    = '#6b7280'
_ACCENT   = default_theme.button_primary
_ACCENT_H = default_theme.button_primary_hover
_BORDER   = '#e2e8f0'
_PANEL    = '#f8fafc'

_STATUS_CLR = {
    'in_evaluation': '#3b82f6',
    'selected':      '#22c55e',
    'rejected':      '#94a3b8',
}
_STATUS_BG = {
    'in_evaluation': '#eff6ff',
    'selected':      '#f0fdf4',
    'rejected':      '#f8fafc',
}
_BADGE_COLORS = [
    '#f97316','#3b82f6','#f59e0b','#14b8a6',
    '#ef4444','#22c55e','#6366f1','#8b5cf6',
    '#06b6d4','#ec4899',
]
_COLS = 3

_LBL = f'color: {_MUTED}; font-size: 10px; font-weight: 700; letter-spacing: 0.7px; background: transparent;'
_INPUT_CSS = f"""
    QLineEdit, QTextEdit, QComboBox {{
        background: {_CARD}; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 6px;
        padding: 6px 10px; font-size: 13px;
    }}
    QLineEdit:focus, QTextEdit:focus {{ border-color: {_ACCENT}; }}
"""


def _make_check_icon() -> str:
    """Write a white checkmark SVG to a temp file; return its path for use in stylesheets."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<polyline points="2.5,8.5 6.5,12.5 13.5,3.5" '
        'stroke="white" stroke-width="2.5" fill="none" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
        '</svg>'
    )
    path = os.path.join(tempfile.gettempdir(), 'ectoform_rd_check.svg')
    with open(path, 'w') as f:
        f.write(svg)
    return path

_CHECK_ICON = _make_check_icon()


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class BriefNote:
    id: str
    text: str
    author: str
    date: str  # 'YYYY-MM-DD'


@dataclass
class ComponentBrief:
    objective: str = ''
    constraints: str = ''
    budget_min: float = 0.0
    budget_max: float = 0.0
    quantity: int = 1
    quantity_unit: str = 'piece'
    notes: List[dict] = field(default_factory=list)  # BriefNote as dict


@dataclass
class MaterialProposal:
    id: str
    name: str
    category: str = ''
    treatment: str = ''
    origin: str = ''
    supplier: str = ''
    status: str = 'in_evaluation'
    image_path: str = ''
    notes: str = ''


@dataclass
class TechniqueProposal:
    id: str
    name: str
    process_type: str = ''
    equipment: str = ''
    parameters: str = ''
    lead_time: str = ''
    complexity: str = ''
    supplier: str = ''
    notes: str = ''
    status: str = 'in_evaluation'
    image_path: str = ''


@dataclass
class RdComponent:
    id: str
    name: str
    supplier: str = ''
    color: str = ''
    brief: dict = field(default_factory=dict)
    proposals: list = field(default_factory=list)             # MaterialProposal as dict
    technique_proposals: list = field(default_factory=list)   # TechniqueProposal as dict


# ── Helpers ───────────────────────────────────────────────────────────────────

def _brief_from_dict(d: dict) -> ComponentBrief:
    d2 = {k: v for k, v in d.items() if k in ComponentBrief.__dataclass_fields__}
    return ComponentBrief(**d2)


def _proposal_from_dict(d: dict) -> MaterialProposal:
    d2 = {k: v for k, v in d.items() if k in MaterialProposal.__dataclass_fields__}
    return MaterialProposal(**d2)


def _technique_from_dict(d: dict) -> TechniqueProposal:
    d2 = {k: v for k, v in d.items() if k in TechniqueProposal.__dataclass_fields__}
    return TechniqueProposal(**d2)


def _comp_from_dict(d: dict) -> RdComponent:
    return RdComponent(
        id=d.get('id', str(uuid.uuid4())),
        name=d.get('name', ''),
        supplier=d.get('supplier', ''),
        color=d.get('color', ''),
        brief=d.get('brief', {}),
        proposals=d.get('proposals', []),
        technique_proposals=d.get('technique_proposals', []),
    )


# ── Inline photo widget ───────────────────────────────────────────────────────

class _MiniPhoto(QLabel):
    """Clickable square that shows a photo thumbnail or placeholder."""
    changed = pyqtSignal(str)

    def __init__(self, path: str = '', w: int = 150, h: int = 110, parent=None):
        super().__init__(parent)
        self._path = path
        self._w, self._h = w, h
        self.setFixedSize(w, h)
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
            QLabel {{
                background: #f8fafc; border: 2px dashed {_BORDER};
                border-radius: 8px; color: {_MUTED}; font-size: 11px;
            }}
            QLabel:hover {{ border-color: {_ACCENT}; background: #eff6ff; }}
        """)
        self._refresh()

    def _refresh(self):
        if self._path and os.path.exists(self._path):
            pix = QPixmap(self._path).scaled(
                self._w - 4, self._h - 4,
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
            self.setPixmap(pix)
            self.setText('')
            self.setStyleSheet(
                f'QLabel {{ background: #f8fafc; border: 1px solid {_BORDER}; border-radius: 8px; }}'
            )
        else:
            self.clear()
            self.setText('📷\n' + t('rd.click_to_add_photo'))

    def set_path(self, path: str):
        self._path = path
        self._refresh()

    def get_path(self) -> str:
        return self._path

    def mousePressEvent(self, _e):
        path, _ = QFileDialog.getOpenFileName(
            self, t('rd.select_photo'), '',
            'Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tiff)',
        )
        if path:
            self._path = path
            self._refresh()
            self.changed.emit(path)


# ── Dialogs ───────────────────────────────────────────────────────────────────

class _ComponentDialog(FormModal):
    def __init__(self, comp: RdComponent = None, parent=None):
        label = t('rd.edit_component') if comp else t('rd.add_component')
        super().__init__(parent, label, theme=FormModal.LIGHT)
        self._f_name = self.add_field(t('rd.comp_name'), QLineEdit(comp.name if comp else ''))
        self._f_sup  = self.add_field(t('rd.comp_supplier'), QLineEdit(comp.supplier if comp else ''))
        self.finish(ok=t('common.save'), cancel=t('common.cancel'))

    def get_result(self) -> dict:
        return {
            'name':     self._f_name.text().strip(),
            'supplier': self._f_sup.text().strip(),
        }


class _ProposalDialog(FormModal):
    def __init__(self, prop: MaterialProposal = None, parent=None):
        label = t('rd.edit_proposal') if prop else t('rd.add_proposal_dlg')
        super().__init__(parent, label, theme=FormModal.LIGHT, min_width=440)
        self._photo = _MiniPhoto(prop.image_path if prop else '', 200, 140)
        self.add_widget(self._photo)
        self._f_name  = self.add_field(t('rd.prop_name'),      QLineEdit(prop.name if prop else ''))
        self._f_cat   = self.add_field(t('rd.prop_category'),  QLineEdit(prop.category if prop else ''))
        self._f_treat = self.add_field(t('rd.prop_treatment'), QLineEdit(prop.treatment if prop else ''))
        self._f_orig  = self.add_field(t('rd.prop_origin'),    QLineEdit(prop.origin if prop else ''))
        self._f_sup   = self.add_field(t('rd.prop_supplier'),  QLineEdit(prop.supplier if prop else ''))
        notes_edit = QTextEdit(prop.notes if prop else '')
        notes_edit.setFixedHeight(60)
        self._f_notes = self.add_field(t('rd.prop_notes'), notes_edit, height_override=60)
        self.finish(ok=t('common.save'), cancel=t('common.cancel'))

    def get_result(self) -> dict:
        return {
            'name':      self._f_name.text().strip(),
            'category':  self._f_cat.text().strip(),
            'treatment': self._f_treat.text().strip(),
            'origin':    self._f_orig.text().strip(),
            'supplier':  self._f_sup.text().strip(),
            'image_path': self._photo.get_path(),
            'notes':     self._f_notes.toPlainText().strip(),
        }


class _TechniqueDialog(FormModal):
    def __init__(self, prop: TechniqueProposal = None, parent=None):
        label = t('rd.edit_technique') if prop else t('rd.add_technique_dlg')
        super().__init__(parent, label, theme=FormModal.LIGHT, min_width=440)
        self._photo = _MiniPhoto(prop.image_path if prop else '', 200, 140)
        self.add_widget(self._photo)
        self._f_name     = self.add_field(t('rd.tech_name'),       QLineEdit(prop.name if prop else ''))
        self._f_process  = self.add_field(t('rd.tech_process'),    QLineEdit(prop.process_type if prop else ''))
        self._f_equip    = self.add_field(t('rd.tech_equipment'),  QLineEdit(prop.equipment if prop else ''))
        self._f_params   = self.add_field(t('rd.tech_parameters'), QLineEdit(prop.parameters if prop else ''))
        self._f_lead     = self.add_field(t('rd.tech_lead_time'),  QLineEdit(prop.lead_time if prop else ''))
        self._f_complex  = self.add_field(t('rd.tech_complexity'), QLineEdit(prop.complexity if prop else ''))
        self._f_sup      = self.add_field(t('rd.tech_supplier'),   QLineEdit(prop.supplier if prop else ''))
        notes_edit = QTextEdit(prop.notes if prop else '')
        notes_edit.setFixedHeight(60)
        self._f_notes = self.add_field(t('rd.tech_notes'), notes_edit, height_override=60)
        self.finish(ok=t('common.save'), cancel=t('common.cancel'))

    def get_result(self) -> dict:
        return {
            'name':         self._f_name.text().strip(),
            'process_type': self._f_process.text().strip(),
            'equipment':    self._f_equip.text().strip(),
            'parameters':   self._f_params.text().strip(),
            'lead_time':    self._f_lead.text().strip(),
            'complexity':   self._f_complex.text().strip(),
            'supplier':     self._f_sup.text().strip(),
            'image_path':   self._photo.get_path(),
            'notes':        self._f_notes.toPlainText().strip(),
        }


class _BriefDialog(FormModal):
    def __init__(self, brief: ComponentBrief, parent=None):
        super().__init__(parent, t('rd.edit_brief'), theme=FormModal.LIGHT, min_width=420)
        obj_edit = QTextEdit(brief.objective)
        obj_edit.setFixedHeight(60)
        self._f_obj = self.add_field(t('rd.brief_objective'), obj_edit, height_override=60)
        con_edit = QTextEdit(brief.constraints)
        con_edit.setFixedHeight(60)
        self._f_con = self.add_field(t('rd.brief_constraints'), con_edit, height_override=60)
        row = self.add_row_fields(
            (t('rd.brief_budget_min'), QLineEdit(str(brief.budget_min or ''))),
            (t('rd.brief_budget_max'), QLineEdit(str(brief.budget_max or ''))),
        )
        self._f_bmin, self._f_bmax = row[0], row[1]
        row2 = self.add_row_fields(
            (t('rd.brief_quantity'), QLineEdit(str(brief.quantity or 1))),
            (t('rd.brief_unit'), QLineEdit(brief.quantity_unit or 'piece')),
        )
        self._f_qty, self._f_unit = row2[0], row2[1]
        self.finish(ok=t('common.save'), cancel=t('common.cancel'))

    def get_result(self) -> dict:
        def _f(s):
            try:
                return float(s.strip())
            except (ValueError, AttributeError):
                return 0.0
        return {
            'objective':     self._f_obj.toPlainText().strip(),
            'constraints':   self._f_con.toPlainText().strip(),
            'budget_min':    _f(self._f_bmin.text()),
            'budget_max':    _f(self._f_bmax.text()),
            'quantity':      int(self._f_qty.text().strip() or 1),
            'quantity_unit': self._f_unit.text().strip() or 'piece',
        }


class _NoteDialog(FormModal):
    def __init__(self, parent=None):
        super().__init__(parent, t('rd.add_note'), theme=FormModal.LIGHT, min_width=380)
        self._f_text   = self.add_field(t('rd.note_text'),   QLineEdit())
        self._f_author = self.add_field(t('rd.note_author'), QLineEdit())
        self.finish(ok=t('common.save'), cancel=t('common.cancel'))

    def get_result(self) -> dict:
        return {
            'text':   self._f_text.text().strip(),
            'author': self._f_author.text().strip(),
        }


class _CompareDialog(QDialog):
    def __init__(self, proposals: List[Tuple[MaterialProposal, str]], parent=None):
        super().__init__(parent)
        self.setWindowTitle(t('rd.compare_title'))
        self.setMinimumSize(600, 480)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        container = QWidget()
        row = QHBoxLayout(container)
        row.setSpacing(16)
        row.setContentsMargins(0, 0, 0, 0)

        for prop, comp_name in proposals:
            card = self._make_card(prop, comp_name)
            row.addWidget(card)
        row.addStretch()
        scroll.setWidget(container)
        root.addWidget(scroll, 1)

        btn_close = QPushButton(t('common.close') if t('common.close') != 'common.close' else 'Close')
        btn_close.setFixedHeight(34)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet(f"""
            QPushButton {{ background: {_ACCENT}; color: white; border: none;
                border-radius: 6px; font-size: 13px; font-weight: 600; }}
            QPushButton:hover {{ background: {_ACCENT_H}; }}
        """)
        btn_close.clicked.connect(self.accept)
        root.addWidget(btn_close)

    @staticmethod
    def _make_card(prop: MaterialProposal, comp_name: str) -> QFrame:
        c = QFrame()
        c.setFixedWidth(200)
        c.setStyleSheet(f"""
            QFrame {{ background: {_CARD}; border: 1px solid {_BORDER};
                border-radius: 10px; }}
        """)
        lay = QVBoxLayout(c)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(6)

        img = QLabel()
        img.setFixedSize(176, 130)
        img.setAlignment(Qt.AlignCenter)
        img.setStyleSheet(f'background: {_PANEL}; border-radius: 6px;')
        if prop.image_path and os.path.exists(prop.image_path):
            pix = QPixmap(prop.image_path).scaled(176, 130, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            img.setPixmap(pix)
        else:
            img.setText('📷')
            img.setStyleSheet(img.styleSheet() + f' color: {_MUTED}; font-size: 24px;')
        lay.addWidget(img)

        name_lbl = QLabel(prop.name)
        name_lbl.setWordWrap(True)
        name_lbl.setStyleSheet(f'color: {_TEXT}; font-size: 13px; font-weight: bold; background: transparent;')
        lay.addWidget(name_lbl)

        comp_lbl = QLabel(comp_name)
        comp_lbl.setStyleSheet(f'color: {_ACCENT}; font-size: 11px; background: transparent;')
        lay.addWidget(comp_lbl)

        for label, value in [
            (t('rd.prop_category'),  prop.category),
            (t('rd.prop_treatment'), prop.treatment),
            (t('rd.prop_origin'),    prop.origin),
            (t('rd.prop_supplier'),  prop.supplier),
        ]:
            if value:
                lbl = QLabel(f'<span style="color:{_MUTED};">{label}</span>  {value}')
                lbl.setStyleSheet(f'color: {_TEXT}; font-size: 11px; background: transparent;')
                lay.addWidget(lbl)

        lay.addStretch()
        return c


# ── Left panel — component list ───────────────────────────────────────────────

class _BadgePainter(QWidget):
    """Coloured circle with a number inside."""
    def __init__(self, number: int, color: str, parent=None):
        super().__init__(parent)
        self._n = number
        self._color = color
        self.setFixedSize(26, 26)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QBrush(QColor(self._color)))
        p.setPen(Qt.NoPen)
        p.drawEllipse(1, 1, 24, 24)
        p.setPen(QPen(QColor('white')))
        f = p.font()
        f.setPixelSize(11)
        f.setBold(True)
        p.setFont(f)
        p.drawText(self.rect(), Qt.AlignCenter, str(self._n))


class _ComponentRow(QFrame):
    clicked    = pyqtSignal(str)   # comp id
    edit_req   = pyqtSignal(str)
    delete_req = pyqtSignal(str)

    def __init__(self, comp: RdComponent, number: int, active: bool, parent=None):
        super().__init__(parent)
        self._id = comp.id
        color = comp.color or _BADGE_COLORS[(number - 1) % len(_BADGE_COLORS)]
        self._set_style(active)
        self.setCursor(Qt.PointingHandCursor)

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 8, 8, 8)
        row.setSpacing(8)

        row.addWidget(_BadgePainter(number, color))

        info = QVBoxLayout()
        info.setSpacing(1)
        lbl_name = QLabel(comp.name)
        lbl_name.setStyleSheet(f'background: transparent; color: {_TEXT}; font-size: 12px; font-weight: 600;')
        info.addWidget(lbl_name)
        if comp.supplier:
            lbl_sup = QLabel(comp.supplier)
            lbl_sup.setStyleSheet(f'background: transparent; color: {_MUTED}; font-size: 11px;')
            info.addWidget(lbl_sup)
        row.addLayout(info, 1)

        btn_menu = QPushButton('⋮')
        btn_menu.setFixedSize(22, 22)
        btn_menu.setCursor(Qt.PointingHandCursor)
        btn_menu.setStyleSheet('QPushButton { background: transparent; border: none; color: #94a3b8; font-size: 15px; }')
        btn_menu.clicked.connect(self._show_menu)
        row.addWidget(btn_menu)

    def _set_style(self, active: bool):
        if active:
            self.setStyleSheet(f"""
                QFrame {{ background: #eff6ff; border-radius: 8px;
                    border-left: 3px solid {_ACCENT}; }}
            """)
        else:
            self.setStyleSheet(f"""
                QFrame {{ background: transparent; border-radius: 8px; border: none; }}
                QFrame:hover {{ background: #f1f5f9; }}
            """)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self._id)

    def _show_menu(self):
        menu = QMenu(self)
        menu.addAction(t('rd.rename_component'), lambda: self.edit_req.emit(self._id))
        menu.addSeparator()
        menu.addAction(t('rd.remove_component'), lambda: self.delete_req.emit(self._id))
        menu.exec_(self.cursor().pos())


# ── Proposal card ─────────────────────────────────────────────────────────────

class _ProposalCard(QFrame):
    toggled        = pyqtSignal(str, bool)   # (prop_id, selected)
    edit_req       = pyqtSignal(str)
    reject_req     = pyqtSignal(str)
    delete_req     = pyqtSignal(str)

    def __init__(self, prop: MaterialProposal, parent=None):
        super().__init__(parent)
        self._prop = prop
        self._build()

    def _build(self):
        from PyQt5.QtWidgets import QCheckBox
        s = self._prop.status
        is_selected = (s == 'selected')
        border_color = '#22c55e' if is_selected else _BORDER
        border_w = '2px' if is_selected else '1px'

        self.setFixedWidth(280)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)
        self.setStyleSheet(f"""
            QFrame {{
                background: {_CARD}; border-radius: 12px;
                border: {border_w} solid {border_color};
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(0)

        # ── Top row: checkbox + menu ─────────────────────────────────────────
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 6)
        self._cb = QCheckBox()
        self._cb.setChecked(is_selected)
        self._cb.setStyleSheet(f"""
            QCheckBox {{ background: transparent; }}
            QCheckBox::indicator {{
                width: 20px; height: 20px; border-radius: 6px;
                border: 2px solid {_BORDER}; background: white;
            }}
            QCheckBox::indicator:checked {{
                background: #22c55e; border-color: #22c55e;
                image: url({_CHECK_ICON});
            }}
        """)
        self._cb.toggled.connect(lambda v: self.toggled.emit(self._prop.id, v))
        top_row.addWidget(self._cb)
        top_row.addStretch()

        btn_menu = QPushButton('⋮')
        btn_menu.setFixedSize(24, 24)
        btn_menu.setCursor(Qt.PointingHandCursor)
        btn_menu.setStyleSheet(
            'QPushButton { background: transparent; border: none; color: #94a3b8; font-size: 16px; }'
            'QPushButton:hover { color: #475569; }'
        )
        btn_menu.clicked.connect(self._show_menu)
        top_row.addWidget(btn_menu)
        root.addLayout(top_row)

        # ── Photo ─────────────────────────────────────────────────────────────
        IMG_W, IMG_H = 256, 160
        self._img = QLabel()
        self._img.setFixedSize(IMG_W, IMG_H)
        self._img.setAlignment(Qt.AlignCenter)
        self._img.setStyleSheet(
            f'background: {_PANEL}; border-radius: 8px; color: {_MUTED}; font-size: 28px; border: none;'
        )
        self._load_image()
        root.addWidget(self._img)
        root.addSpacing(10)

        # ── Name ──────────────────────────────────────────────────────────────
        lbl_name = QLabel(self._prop.name or '—')
        lbl_name.setWordWrap(True)
        lbl_name.setStyleSheet(
            f'background: transparent; color: {_TEXT}; font-size: 13px; font-weight: 700; border: none;'
        )
        root.addWidget(lbl_name)
        root.addSpacing(6)

        # ── Separator ─────────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f'background: {_BORDER}; border: none; max-height: 1px;')
        root.addWidget(sep)
        root.addSpacing(8)

        # ── Metadata rows (label | value) ─────────────────────────────────────
        meta_rows = [
            (t('rd.supplier'), self._prop.supplier),
            (t('rd.type'),     self._prop.category),
            (t('rd.treat'),    self._prop.treatment),
            (t('rd.origin'),   self._prop.origin),
        ]
        for label, value in meta_rows:
            if not value:
                continue
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            lbl = QLabel(label)
            lbl.setFixedWidth(72)
            lbl.setStyleSheet(f'color: {_MUTED}; font-size: 11px; background: transparent; border: none;')
            val = QLabel(value)
            val.setStyleSheet(f'color: {_TEXT}; font-size: 11px; font-weight: 600; background: transparent; border: none;')
            val.setWordWrap(True)
            row.addWidget(lbl)
            row.addWidget(val, 1)
            root.addLayout(row)
            root.addSpacing(3)

        # ── Notes / comment box ───────────────────────────────────────────────
        if self._prop.notes:
            root.addSpacing(6)
            comment_lbl = QLabel('Comment')
            comment_lbl.setStyleSheet(
                f'color: {_MUTED}; font-size: 11px; background: transparent; border: none;'
            )
            root.addWidget(comment_lbl)
            root.addSpacing(3)
            note_box = QLabel(self._prop.notes)
            note_box.setWordWrap(True)
            note_box.setStyleSheet("""
                QLabel {
                    background: #e0f2fe; color: #0369a1;
                    border-radius: 6px; padding: 6px 8px;
                    font-size: 11px; border: none;
                }
            """)
            root.addWidget(note_box)

    def _load_image(self):
        if self._prop.image_path and os.path.exists(self._prop.image_path):
            pix = QPixmap(self._prop.image_path).scaled(
                256, 160, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            self._img.setPixmap(pix)
            self._img.setScaledContents(False)
        else:
            self._img.setText('📷')

    def _show_menu(self):
        menu = QMenu(self)
        menu.addAction(t('rd.edit_proposal'), lambda: self.edit_req.emit(self._prop.id))
        menu.addAction(t('rd.reject_proposal'), lambda: self.reject_req.emit(self._prop.id))
        menu.addSeparator()
        menu.addAction(t('rd.remove_proposal'), lambda: self.delete_req.emit(self._prop.id))
        menu.exec_(self.cursor().pos())


# ── Technique card ───────────────────────────────────────────────────────────

class _TechniqueCard(QFrame):
    toggled    = pyqtSignal(str, bool)
    edit_req   = pyqtSignal(str)
    reject_req = pyqtSignal(str)
    delete_req = pyqtSignal(str)

    def __init__(self, prop: TechniqueProposal, parent=None):
        super().__init__(parent)
        self._prop = prop
        self._build()

    def _build(self):
        from PyQt5.QtWidgets import QCheckBox
        s = self._prop.status
        is_selected = (s == 'selected')
        border_color = '#22c55e' if is_selected else _BORDER
        border_w = '2px' if is_selected else '1px'

        self.setFixedWidth(280)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)
        self.setStyleSheet(f"""
            QFrame {{
                background: {_CARD}; border-radius: 12px;
                border: {border_w} solid {border_color};
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(0)

        # Top row: checkbox + menu
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 6)
        self._cb = QCheckBox()
        self._cb.setChecked(is_selected)
        self._cb.setStyleSheet(f"""
            QCheckBox {{ background: transparent; }}
            QCheckBox::indicator {{
                width: 20px; height: 20px; border-radius: 6px;
                border: 2px solid {_BORDER}; background: white;
            }}
            QCheckBox::indicator:checked {{
                background: #22c55e; border-color: #22c55e;
                image: url({_CHECK_ICON});
            }}
        """)
        self._cb.toggled.connect(lambda v: self.toggled.emit(self._prop.id, v))
        top_row.addWidget(self._cb)
        top_row.addStretch()

        btn_menu = QPushButton('⋮')
        btn_menu.setFixedSize(24, 24)
        btn_menu.setCursor(Qt.PointingHandCursor)
        btn_menu.setStyleSheet(
            'QPushButton { background: transparent; border: none; color: #94a3b8; font-size: 16px; }'
            'QPushButton:hover { color: #475569; }'
        )
        btn_menu.clicked.connect(self._show_menu)
        top_row.addWidget(btn_menu)
        root.addLayout(top_row)

        # Optional image
        if self._prop.image_path and os.path.exists(self._prop.image_path):
            IMG_W, IMG_H = 256, 140
            img_lbl = QLabel()
            img_lbl.setFixedSize(IMG_W, IMG_H)
            img_lbl.setAlignment(Qt.AlignCenter)
            img_lbl.setStyleSheet(f'background: {_PANEL}; border-radius: 8px; border: none;')
            pix = QPixmap(self._prop.image_path).scaled(
                IMG_W, IMG_H, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            img_lbl.setPixmap(pix)
            root.addWidget(img_lbl)
            root.addSpacing(10)

        # Name
        lbl_name = QLabel(self._prop.name or '—')
        lbl_name.setWordWrap(True)
        lbl_name.setStyleSheet(
            f'background: transparent; color: {_TEXT}; font-size: 13px; font-weight: 700; border: none;'
        )
        root.addWidget(lbl_name)
        root.addSpacing(6)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f'background: {_BORDER}; border: none; max-height: 1px;')
        root.addWidget(sep)
        root.addSpacing(8)

        # Technique-specific metadata rows
        meta_rows = [
            (t('rd.process_type'), self._prop.process_type),
            (t('rd.equipment'),    self._prop.equipment),
            (t('rd.parameters'),   self._prop.parameters),
            (t('rd.lead_time'),    self._prop.lead_time),
            (t('rd.complexity'),   self._prop.complexity),
            (t('rd.supplier'),     self._prop.supplier),
        ]
        for label, value in meta_rows:
            if not value:
                continue
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            lbl = QLabel(label)
            lbl.setFixedWidth(72)
            lbl.setStyleSheet(f'color: {_MUTED}; font-size: 11px; background: transparent; border: none;')
            val = QLabel(value)
            val.setStyleSheet(f'color: {_TEXT}; font-size: 11px; font-weight: 600; background: transparent; border: none;')
            val.setWordWrap(True)
            row.addWidget(lbl)
            row.addWidget(val, 1)
            root.addLayout(row)
            root.addSpacing(3)

        # Notes
        if self._prop.notes:
            root.addSpacing(6)
            comment_lbl = QLabel('Notes')
            comment_lbl.setStyleSheet(
                f'color: {_MUTED}; font-size: 11px; background: transparent; border: none;'
            )
            root.addWidget(comment_lbl)
            root.addSpacing(3)
            note_box = QLabel(self._prop.notes)
            note_box.setWordWrap(True)
            note_box.setStyleSheet("""
                QLabel {
                    background: #e0f2fe; color: #0369a1;
                    border-radius: 6px; padding: 6px 8px;
                    font-size: 11px; border: none;
                }
            """)
            root.addWidget(note_box)

    def _show_menu(self):
        menu = QMenu(self)
        menu.addAction(t('rd.edit_technique'),   lambda: self.edit_req.emit(self._prop.id))
        menu.addAction(t('rd.reject_technique'), lambda: self.reject_req.emit(self._prop.id))
        menu.addSeparator()
        menu.addAction(t('rd.remove_technique'), lambda: self.delete_req.emit(self._prop.id))
        menu.exec_(self.cursor().pos())


# ── Selection row (right panel) ───────────────────────────────────────────────

class _SelectionRow(QFrame):
    deselect = pyqtSignal(str)  # prop id

    def __init__(self, prop: MaterialProposal, comp_name: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{ background: {_CARD}; border: 1px solid {_BORDER};
                border-radius: 8px; }}
        """)
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 6, 6, 6)
        row.setSpacing(8)

        thumb = QLabel()
        thumb.setFixedSize(44, 44)
        thumb.setAlignment(Qt.AlignCenter)
        thumb.setStyleSheet(f'background: {_PANEL}; border-radius: 6px; color: {_MUTED}; font-size: 18px;')
        if prop.image_path and os.path.exists(prop.image_path):
            pix = QPixmap(prop.image_path).scaled(44, 44, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            thumb.setPixmap(pix)
        else:
            thumb.setText('📷')
        row.addWidget(thumb)

        info = QVBoxLayout()
        info.setSpacing(1)
        lbl_n = QLabel(prop.name)
        lbl_n.setStyleSheet(f'background: transparent; color: {_TEXT}; font-size: 12px; font-weight: 600;')
        info.addWidget(lbl_n)
        lbl_s = QLabel(f'{prop.supplier}  ·  {comp_name}')
        lbl_s.setStyleSheet(f'background: transparent; color: {_MUTED}; font-size: 10px;')
        info.addWidget(lbl_s)
        row.addLayout(info, 1)

        btn_x = QPushButton('×')
        btn_x.setFixedSize(20, 20)
        btn_x.setCursor(Qt.PointingHandCursor)
        btn_x.setStyleSheet("""
            QPushButton { background: transparent; border: none; color: #94a3b8;
                font-size: 16px; font-weight: bold; padding: 0; }
            QPushButton:hover { color: #ef4444; }
        """)
        btn_x.clicked.connect(lambda: self.deselect.emit(prop.id))
        row.addWidget(btn_x)


# ── Main widget ───────────────────────────────────────────────────────────────

class RdWidget(QWidget):
    changed     = pyqtSignal()
    tab_changed = pyqtSignal(int)   # emitted when the user switches tabs

    def __init__(self, parent=None):
        super().__init__(parent)
        self._components: List[RdComponent] = []
        self._active_id: Optional[str] = None   # None = show all
        self._active_tab_idx: int = 0            # 0 = Textures, 1 = Techniques
        self._cat_filter  = ''
        self._sup_filter  = ''
        self._search_text = ''
        self._build_ui()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Left panel
        self._left = self._build_left()
        outer.addWidget(self._left)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.VLine)
        div.setMaximumWidth(1)
        div.setStyleSheet(f'background: {_BORDER}; border: none;')
        outer.addWidget(div)

        # Centre
        self._centre = QWidget()
        self._centre.setStyleSheet(f'background: #f7f9fc;')
        centre_lay = QVBoxLayout(self._centre)
        centre_lay.setContentsMargins(20, 18, 20, 18)
        centre_lay.setSpacing(12)
        self._centre_lay = centre_lay
        self._build_centre(centre_lay)
        outer.addWidget(self._centre, 1)

        # Divider
        div2 = QFrame()
        div2.setFrameShape(QFrame.VLine)
        div2.setMaximumWidth(1)
        div2.setStyleSheet(f'background: {_BORDER}; border: none;')
        outer.addWidget(div2)

        # Right panel
        self._right = self._build_right()
        outer.addWidget(self._right)

    # ── Left: component list ──────────────────────────────────────────────────

    def _build_left(self) -> QFrame:
        panel = QFrame()
        panel.setFixedWidth(200)
        panel.setStyleSheet(f'QFrame {{ background: {_PANEL}; }}')
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(10, 16, 10, 12)
        lay.setSpacing(6)

        lbl = QLabel(t('rd.components'))
        lbl.setStyleSheet(_LBL)
        lay.addWidget(lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet('background: transparent; border: none;')
        scroll.viewport().setStyleSheet('background: transparent;')
        self._comp_container = QWidget()
        self._comp_container.setStyleSheet('background: transparent;')
        self._comp_lay = QVBoxLayout(self._comp_container)
        self._comp_lay.setContentsMargins(0, 0, 0, 0)
        self._comp_lay.setSpacing(2)
        self._comp_lay.addStretch()
        scroll.setWidget(self._comp_container)
        lay.addWidget(scroll, 1)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setMaximumHeight(1)
        sep.setStyleSheet(f'background: {_BORDER}; border: none;')
        lay.addWidget(sep)

        btn_add = QPushButton(f'+ {t("rd.add_component")}')
        btn_add.setCursor(Qt.PointingHandCursor)
        btn_add.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {_ACCENT};
                border: 1px solid {_ACCENT}; border-radius: 6px;
                font-size: 12px; font-weight: 600; padding: 6px; }}
            QPushButton:hover {{ background: #eff6ff; }}
        """)
        btn_add.clicked.connect(self._add_component)
        lay.addWidget(btn_add)

        hint = QLabel(t('rd.how_it_works'))
        hint.setWordWrap(True)
        hint.setStyleSheet(f'background: transparent; color: {_MUTED}; font-size: 10px; padding: 4px 0;')
        lay.addWidget(hint)

        return panel

    # ── Centre: filter + tab area ─────────────────────────────────────────────

    def _build_centre(self, lay: QVBoxLayout):
        # Header
        hdr = QHBoxLayout()
        lbl_title = QLabel(t('rd.title'))
        lbl_title.setStyleSheet(f'color: {_TEXT}; font-size: 20px; font-weight: bold;')
        hdr.addWidget(lbl_title)
        hdr.addStretch()
        lay.addLayout(hdr)

        lbl_sub = QLabel(t('rd.subtitle'))
        lbl_sub.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')
        lay.addWidget(lbl_sub)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setMaximumHeight(1)
        sep.setStyleSheet(f'background: {_BORDER}; border: none;')
        lay.addWidget(sep)

        # Filter bar
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        self._combo_comp = self._make_filter_combo()
        self._combo_comp.currentIndexChanged.connect(self._on_comp_combo)
        filter_row.addWidget(self._combo_comp)

        self._combo_cat = self._make_filter_combo()
        self._combo_cat.currentIndexChanged.connect(lambda _: self._apply_filters())
        filter_row.addWidget(self._combo_cat)

        self._combo_sup = self._make_filter_combo()
        self._combo_sup.currentIndexChanged.connect(lambda _: self._apply_filters())
        filter_row.addWidget(self._combo_sup)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText(t('rd.search_ph'))
        self._search_edit.setFixedHeight(32)
        self._search_edit.setStyleSheet(f"""
            QLineEdit {{ background: {_CARD}; color: {_TEXT}; border: 1px solid {_BORDER};
                border-radius: 6px; padding: 0 10px; font-size: 12px; }}
            QLineEdit:focus {{ border-color: {_ACCENT}; }}
        """)
        self._search_edit.textChanged.connect(self._apply_filters)
        filter_row.addWidget(self._search_edit, 1)

        self._btn_compare = QPushButton(t('rd.compare'))
        self._btn_compare.setFixedHeight(32)
        self._btn_compare.setCursor(Qt.PointingHandCursor)
        self._btn_compare.setStyleSheet(f"""
            QPushButton {{ background: #f1f5f9; color: {_TEXT}; border: 1px solid {_BORDER};
                border-radius: 6px; font-size: 12px; font-weight: 600; padding: 0 14px; }}
            QPushButton:hover {{ background: #e2e8f0; }}
            QPushButton:disabled {{ color: #c4cdd8; }}
        """)
        self._btn_compare.clicked.connect(self._open_compare)
        filter_row.addWidget(self._btn_compare)

        self._btn_add_prop = QPushButton(t('rd.add_texture'))
        self._btn_add_prop.setFixedHeight(32)
        self._btn_add_prop.setCursor(Qt.PointingHandCursor)
        self._btn_add_prop.setStyleSheet(f"""
            QPushButton {{ background: {_ACCENT}; color: white; border: none;
                border-radius: 6px; font-size: 12px; font-weight: 600; padding: 0 14px; }}
            QPushButton:hover {{ background: {_ACCENT_H}; }}
            QPushButton:disabled {{ background: {_BORDER}; color: {_MUTED}; }}
        """)
        self._btn_add_prop.setEnabled(False)
        self._btn_add_prop.setToolTip(t('rd.select_component_first'))
        self._btn_add_prop.clicked.connect(self._add_proposal)
        filter_row.addWidget(self._btn_add_prop)
        lay.addLayout(filter_row)

        # Component header (shown when a component is active)
        self._comp_hdr = QWidget()
        self._comp_hdr.setStyleSheet(f"""
            QWidget {{ background: {_CARD}; border: 1px solid {_BORDER}; border-radius: 10px; }}
        """)
        chdr_lay = QHBoxLayout(self._comp_hdr)
        chdr_lay.setContentsMargins(14, 10, 14, 10)
        chdr_lay.setSpacing(12)
        self._comp_hdr_name = QLabel('')
        self._comp_hdr_name.setStyleSheet(f'background: transparent; color: {_TEXT}; font-size: 15px; font-weight: bold;')
        chdr_lay.addWidget(self._comp_hdr_name)
        self._comp_hdr_sup = QLabel('')
        self._comp_hdr_sup.setStyleSheet(f'background: transparent; color: {_MUTED}; font-size: 13px;')
        chdr_lay.addWidget(self._comp_hdr_sup)
        chdr_lay.addStretch()
        self._stat_labels = {}
        for key in ('proposals', 'in_evaluation', 'selected', 'rejected'):
            pill = QLabel('')
            pill.setStyleSheet(f'background: transparent; color: {_MUTED}; font-size: 11px;')
            chdr_lay.addWidget(pill)
            self._stat_labels[key] = pill
        self._comp_hdr.hide()
        lay.addWidget(self._comp_hdr)

        # Sub-tabs
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(False)

        # Force a light palette on both the tab widget and its tab bar so the
        # dark app palette doesn't bleed through (CSS alone can't beat palette).
        _light_bg = QColor(_BG)
        for w in (self._tabs, self._tabs.tabBar()):
            w.setAutoFillBackground(True)
            pal = QPalette()
            pal.setColor(QPalette.Window, _light_bg)
            pal.setColor(QPalette.Base, _light_bg)
            pal.setColor(QPalette.Button, _light_bg)
            w.setPalette(pal)

        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; background: transparent; }}
            QTabWidget::tab-bar {{ alignment: left; }}
            QTabBar {{ background: {_BG}; border: none; }}
            QTabBar::tab {{
                background: transparent; color: {_MUTED};
                padding: 8px 16px; font-size: 12px; border: none;
                border-bottom: 2px solid transparent;
            }}
            QTabBar::tab:selected {{
                color: {_ACCENT}; border-bottom: 2px solid {_ACCENT};
                font-weight: 600;
            }}
            QTabBar::tab:hover:!selected {{ color: {_TEXT}; }}
        """)

        # Tab 0: Textures & Materials — proposal grid
        tab0 = QWidget()
        tab0.setStyleSheet('background: transparent;')
        tab0_lay = QVBoxLayout(tab0)
        tab0_lay.setContentsMargins(0, 10, 0, 0)
        tab0_lay.setSpacing(8)

        lbl_proposed = QLabel(t('rd.proposed_textures'))
        lbl_proposed.setStyleSheet(f'background: transparent; color: {_TEXT}; font-size: 13px; font-weight: 600;')
        tab0_lay.addWidget(lbl_proposed)

        grid_scroll = QScrollArea()
        grid_scroll.setWidgetResizable(True)
        grid_scroll.setFrameShape(QFrame.NoFrame)
        grid_scroll.setStyleSheet('background: transparent; border: none;')
        grid_scroll.viewport().setStyleSheet('background: transparent;')
        self._grid_container = QWidget()
        self._grid_container.setStyleSheet('background: transparent;')
        self._grid_lay = QGridLayout(self._grid_container)
        self._grid_lay.setSpacing(16)
        self._grid_lay.setContentsMargins(0, 0, 0, 0)
        self._grid_lay.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._empty_grid_lbl = QLabel(t('rd.no_proposals'))
        self._empty_grid_lbl.setAlignment(Qt.AlignCenter)
        self._empty_grid_lbl.setStyleSheet(f'color: {_MUTED}; font-size: 13px; padding: 40px;')
        self._grid_lay.addWidget(self._empty_grid_lbl, 0, 0, 1, _COLS)
        grid_scroll.setWidget(self._grid_container)
        tab0_lay.addWidget(grid_scroll, 1)
        self._tabs.addTab(tab0, t('rd.tab_textures').replace('&', '&&'))

        tab1 = QWidget()
        tab1.setStyleSheet('background: transparent;')
        tab1_lay = QVBoxLayout(tab1)
        tab1_lay.setContentsMargins(0, 10, 0, 0)
        tab1_lay.setSpacing(8)

        lbl_techniques = QLabel(t('rd.proposed_techniques'))
        lbl_techniques.setStyleSheet(f'background: transparent; color: {_TEXT}; font-size: 13px; font-weight: 600;')
        tab1_lay.addWidget(lbl_techniques)

        tech_scroll = QScrollArea()
        tech_scroll.setWidgetResizable(True)
        tech_scroll.setFrameShape(QFrame.NoFrame)
        tech_scroll.setStyleSheet('background: transparent; border: none;')
        tech_scroll.viewport().setStyleSheet('background: transparent;')
        self._tech_container = QWidget()
        self._tech_container.setStyleSheet('background: transparent;')
        self._tech_grid_lay = QGridLayout(self._tech_container)
        self._tech_grid_lay.setSpacing(16)
        self._tech_grid_lay.setContentsMargins(0, 0, 0, 0)
        self._tech_grid_lay.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._tech_empty_lbl = QLabel(t('rd.no_techniques'))
        self._tech_empty_lbl.setAlignment(Qt.AlignCenter)
        self._tech_empty_lbl.setStyleSheet(f'color: {_MUTED}; font-size: 13px; padding: 40px;')
        self._tech_grid_lay.addWidget(self._tech_empty_lbl, 0, 0, 1, _COLS)
        tech_scroll.setWidget(self._tech_container)
        tab1_lay.addWidget(tech_scroll, 1)
        self._tabs.addTab(tab1, t('rd.tab_techniques'))

        self._tabs.tabBar().setExpanding(False)
        self._tabs.currentChanged.connect(self._on_tab_changed)
        lay.addWidget(self._tabs, 1)

    @staticmethod
    def _make_filter_combo() -> QComboBox:
        cb = QComboBox()
        cb.setFixedHeight(32)
        cb.setStyleSheet(f"""
            QComboBox {{ background: {_CARD}; color: {_TEXT}; border: 1px solid {_BORDER};
                border-radius: 6px; padding: 0 10px; font-size: 12px; min-width: 130px; }}
            QComboBox::drop-down {{ border: none; padding-right: 6px; }}
            QComboBox QAbstractItemView {{ background: {_CARD}; color: {_TEXT};
                border: 1px solid {_BORDER}; border-radius: 4px;
                selection-background-color: {_ACCENT}; selection-color: white; }}
        """)
        return cb

    # ── Right: selection + brief ──────────────────────────────────────────────

    def _build_right(self) -> QFrame:
        panel = QFrame()
        panel.setFixedWidth(270)
        panel.setStyleSheet(f'QFrame {{ background: {_PANEL}; }}')
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(12, 16, 12, 12)
        lay.setSpacing(10)

        # Selection header
        sel_hdr = QHBoxLayout()
        self._sel_title = QLabel(t('rd.selection') + ' (0)')
        self._sel_title.setStyleSheet(f'background: transparent; color: {_TEXT}; font-size: 13px; font-weight: bold;')
        sel_hdr.addWidget(self._sel_title)
        sel_hdr.addStretch()
        btn_clear = QPushButton(t('rd.clear_all'))
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.setStyleSheet(f'QPushButton {{ background: transparent; color: {_MUTED}; border: none; font-size: 11px; }}')
        btn_clear.clicked.connect(self._clear_selection)
        sel_hdr.addWidget(btn_clear)
        lay.addLayout(sel_hdr)

        sel_scroll = QScrollArea()
        sel_scroll.setWidgetResizable(True)
        sel_scroll.setFrameShape(QFrame.NoFrame)
        sel_scroll.setStyleSheet('background: transparent; border: none;')
        sel_scroll.viewport().setStyleSheet('background: transparent;')
        sel_scroll.setMaximumHeight(240)
        self._sel_container = QWidget()
        self._sel_container.setStyleSheet('background: transparent;')
        self._sel_lay = QVBoxLayout(self._sel_container)
        self._sel_lay.setContentsMargins(0, 0, 0, 0)
        self._sel_lay.setSpacing(6)
        self._sel_lay.addStretch()
        self._sel_empty = QLabel(t('rd.no_selection'))
        self._sel_empty.setAlignment(Qt.AlignCenter)
        self._sel_empty.setStyleSheet(f'color: {_MUTED}; font-size: 11px; padding: 12px;')
        self._sel_lay.insertWidget(0, self._sel_empty)
        sel_scroll.setWidget(self._sel_container)
        lay.addWidget(sel_scroll)

        btn_req = QPushButton(t('rd.request_samples'))
        btn_req.setFixedHeight(34)
        btn_req.setCursor(Qt.PointingHandCursor)
        btn_req.setStyleSheet(f"""
            QPushButton {{ background: {_ACCENT}; color: white; border: none;
                border-radius: 6px; font-size: 12px; font-weight: 600; }}
            QPushButton:hover {{ background: {_ACCENT_H}; }}
        """)
        lay.addWidget(btn_req)

        btn_cmp = QPushButton(t('rd.compare_selected'))
        btn_cmp.setFixedHeight(34)
        btn_cmp.setCursor(Qt.PointingHandCursor)
        btn_cmp.setStyleSheet(f"""
            QPushButton {{ background: #f1f5f9; color: {_TEXT}; border: 1px solid {_BORDER};
                border-radius: 6px; font-size: 12px; font-weight: 600; }}
            QPushButton:hover {{ background: #e2e8f0; }}
        """)
        btn_cmp.clicked.connect(self._open_compare)
        lay.addWidget(btn_cmp)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setMaximumHeight(1)
        sep.setStyleSheet(f'background: {_BORDER}; border: none;')
        lay.addWidget(sep)

        # Component brief section
        brief_hdr = QHBoxLayout()
        lbl_brief = QLabel(t('rd.component_brief'))
        lbl_brief.setStyleSheet(f'background: transparent; color: {_TEXT}; font-size: 12px; font-weight: bold;')
        brief_hdr.addWidget(lbl_brief)
        lay.addLayout(brief_hdr)

        self._brief_widget = QWidget()
        self._brief_widget.setStyleSheet('background: transparent;')
        brief_scroll = QScrollArea()
        brief_scroll.setWidgetResizable(True)
        brief_scroll.setFrameShape(QFrame.NoFrame)
        brief_scroll.setStyleSheet('background: transparent; border: none;')
        brief_scroll.viewport().setStyleSheet('background: transparent;')
        self._brief_lay = QVBoxLayout(self._brief_widget)
        self._brief_lay.setContentsMargins(0, 0, 0, 0)
        self._brief_lay.setSpacing(6)
        self._no_brief_lbl = QLabel(t('rd.no_component'))
        self._no_brief_lbl.setWordWrap(True)
        self._no_brief_lbl.setStyleSheet(f'color: {_MUTED}; font-size: 11px;')
        self._brief_lay.addWidget(self._no_brief_lbl)
        self._brief_lay.addStretch()
        brief_scroll.setWidget(self._brief_widget)
        lay.addWidget(brief_scroll, 1)

        # Notes section
        notes_hdr = QHBoxLayout()
        lbl_notes = QLabel(t('rd.brief_notes'))
        lbl_notes.setStyleSheet(_LBL)
        notes_hdr.addWidget(lbl_notes)
        notes_hdr.addStretch()
        self._btn_note = QPushButton(t('rd.add_note'))
        self._btn_note.setCursor(Qt.PointingHandCursor)
        self._btn_note.setStyleSheet(f'QPushButton {{ background: transparent; color: {_ACCENT}; border: none; font-size: 11px; font-weight: 600; }}'
                                     f'QPushButton:disabled {{ color: {_MUTED}; }}')
        self._btn_note.clicked.connect(self._add_note)
        self._btn_note.setEnabled(False)
        notes_hdr.addWidget(self._btn_note)
        lay.addLayout(notes_hdr)

        self._notes_container = QWidget()
        self._notes_container.setStyleSheet('background: transparent;')
        self._notes_lay = QVBoxLayout(self._notes_container)
        self._notes_lay.setContentsMargins(0, 0, 0, 0)
        self._notes_lay.setSpacing(4)
        self._notes_lay.addStretch()
        lay.addWidget(self._notes_container)

        return panel

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_comp_combo(self, idx: int):
        val = self._combo_comp.itemData(idx)
        # None → all components
        if val != self._active_id:
            self._active_id = val
            self._rebuild_comp_rows()
            self._update_comp_header()
            self._rebuild_grid()
            self._rebuild_technique_grid()
            self._rebuild_brief()
            self._btn_add_prop.setEnabled(self._active_id is not None)
            self._btn_add_prop.setToolTip(
                '' if self._active_id else t('rd.select_component_first')
            )

    def _apply_filters(self):
        self._cat_filter  = self._combo_cat.currentData() or ''
        self._sup_filter  = self._combo_sup.currentData() or ''
        self._search_text = self._search_edit.text().strip().lower()
        self._rebuild_grid()

    def _on_proposal_toggled(self, prop_id: str, selected: bool):
        for comp in self._components:
            for i, pd in enumerate(comp.proposals):
                prop = _proposal_from_dict(pd)
                if prop.id == prop_id:
                    prop.status = 'selected' if selected else 'in_evaluation'
                    comp.proposals[i] = asdict(prop)
                    break
        self._rebuild_grid()
        self._rebuild_selection()
        self._update_comp_header()
        self.changed.emit()

    def _on_deselect(self, prop_id: str):
        self._on_proposal_toggled(prop_id, False)

    def _on_reject(self, prop_id: str):
        for comp in self._components:
            for i, pd in enumerate(comp.proposals):
                prop = _proposal_from_dict(pd)
                if prop.id == prop_id:
                    prop.status = 'rejected'
                    comp.proposals[i] = asdict(prop)
                    break
        self._rebuild_grid()
        self._rebuild_selection()
        self._update_comp_header()
        self.changed.emit()

    def _on_delete_proposal(self, prop_id: str):
        for comp in self._components:
            comp.proposals = [p for p in comp.proposals if p.get('id') != prop_id]
        self._rebuild_grid()
        self._rebuild_selection()
        self._update_comp_header()
        self.changed.emit()

    def _on_edit_proposal(self, prop_id: str):
        for comp in self._components:
            for i, pd in enumerate(comp.proposals):
                prop = _proposal_from_dict(pd)
                if prop.id == prop_id:
                    dlg = _ProposalDialog(prop, parent=self)
                    if dlg.exec_():
                        data = dlg.get_result()
                        if data['name']:
                            for key, val in data.items():
                                setattr(prop, key, val)
                            comp.proposals[i] = asdict(prop)
                            self._rebuild_grid()
                            self._rebuild_selection()
                            self.changed.emit()
                    return

    # ── Tab switching ─────────────────────────────────────────────────────────

    def _on_tab_changed(self, idx: int):
        self._active_tab_idx = idx
        if idx == 0:
            self._btn_add_prop.setText(t('rd.add_texture'))
        else:
            self._btn_add_prop.setText(t('rd.add_technique'))
        self.tab_changed.emit(idx)

    # ── Technique actions ─────────────────────────────────────────────────────

    def _on_technique_toggled(self, tech_id: str, selected: bool):
        for comp in self._components:
            for i, td in enumerate(comp.technique_proposals):
                tech = _technique_from_dict(td)
                if tech.id == tech_id:
                    tech.status = 'selected' if selected else 'in_evaluation'
                    comp.technique_proposals[i] = asdict(tech)
                    break
        self._rebuild_technique_grid()
        self.changed.emit()

    def _on_reject_technique(self, tech_id: str):
        for comp in self._components:
            for i, td in enumerate(comp.technique_proposals):
                tech = _technique_from_dict(td)
                if tech.id == tech_id:
                    tech.status = 'rejected'
                    comp.technique_proposals[i] = asdict(tech)
                    break
        self._rebuild_technique_grid()
        self.changed.emit()

    def _on_delete_technique(self, tech_id: str):
        for comp in self._components:
            comp.technique_proposals = [
                t for t in comp.technique_proposals if t.get('id') != tech_id
            ]
        self._rebuild_technique_grid()
        self.changed.emit()

    def _on_edit_technique(self, tech_id: str):
        for comp in self._components:
            for i, td in enumerate(comp.technique_proposals):
                tech = _technique_from_dict(td)
                if tech.id == tech_id:
                    dlg = _TechniqueDialog(tech, parent=self)
                    if dlg.exec_():
                        data = dlg.get_result()
                        if data['name']:
                            for key, val in data.items():
                                setattr(tech, key, val)
                            comp.technique_proposals[i] = asdict(tech)
                            self._rebuild_technique_grid()
                            self.changed.emit()
                    return

    # ── Component actions ─────────────────────────────────────────────────────

    def _add_component(self):
        dlg = _ComponentDialog(parent=self)
        if dlg.exec_():
            data = dlg.get_result()
            if not data['name']:
                return
            idx = len(self._components)
            comp = RdComponent(
                id=str(uuid.uuid4()),
                name=data['name'],
                supplier=data['supplier'],
                color=_BADGE_COLORS[idx % len(_BADGE_COLORS)],
            )
            self._components.append(comp)
            self._rebuild_comp_rows()
            self._repopulate_combos()
            self.changed.emit()

    def _edit_component(self, comp_id: str):
        comp = self._get_comp(comp_id)
        if not comp:
            return
        dlg = _ComponentDialog(comp, parent=self)
        if dlg.exec_():
            data = dlg.get_result()
            if data['name']:
                comp.name     = data['name']
                comp.supplier = data['supplier']
                self._rebuild_comp_rows()
                self._repopulate_combos()
                self._update_comp_header()
                self.changed.emit()

    def _delete_component(self, comp_id: str):
        self._components = [c for c in self._components if c.id != comp_id]
        if self._active_id == comp_id:
            self._active_id = None
        self._rebuild_comp_rows()
        self._repopulate_combos()
        self._update_comp_header()
        self._rebuild_grid()
        self._rebuild_brief()
        self._rebuild_selection()
        self.changed.emit()

    def _add_proposal(self):
        comp = self._get_comp(self._active_id)
        if not comp:
            return
        if self._active_tab_idx == 1:
            dlg = _TechniqueDialog(parent=self)
            if dlg.exec_():
                data = dlg.get_result()
                if not data['name']:
                    return
                tech = TechniqueProposal(id=str(uuid.uuid4()), **data)
                comp.technique_proposals.append(asdict(tech))
                self._rebuild_technique_grid()
                self.changed.emit()
        else:
            dlg = _ProposalDialog(parent=self)
            if dlg.exec_():
                data = dlg.get_result()
                if not data['name']:
                    return
                prop = MaterialProposal(id=str(uuid.uuid4()), **data)
                comp.proposals.append(asdict(prop))
                self._rebuild_grid()
                self._update_comp_header()
                self._repopulate_combos()
                self.changed.emit()

    # ── Brief & notes ─────────────────────────────────────────────────────────

    def _save_brief_field(self, comp_id: str, field: str, value):
        comp = self._get_comp(comp_id)
        if not comp:
            return
        comp.brief[field] = value
        self.changed.emit()

    def _save_note(self, comp_id: str, note_id: str, field: str, value: str):
        comp = self._get_comp(comp_id)
        if not comp:
            return
        for nd in comp.brief.get('notes', []):
            if nd.get('id') == note_id:
                nd[field] = value
                break
        self.changed.emit()

    def _delete_note(self, comp_id: str, note_id: str):
        comp = self._get_comp(comp_id)
        if not comp:
            return
        notes = comp.brief.get('notes', [])
        comp.brief['notes'] = [n for n in notes if n.get('id') != note_id]
        self._rebuild_notes()
        self.changed.emit()

    def _add_note(self):
        comp = self._get_comp(self._active_id)
        if not comp:
            return
        dlg = _NoteDialog(parent=self)
        if dlg.exec_():
            data = dlg.get_result()
            if not data['text']:
                return
            note = BriefNote(
                id=str(uuid.uuid4()),
                text=data['text'],
                author=data['author'],
                date=str(_date_cls.today()),
            )
            comp.brief.setdefault('notes', []).append(asdict(note))
            self._rebuild_notes()
            self.changed.emit()

    def _clear_selection(self):
        for comp in self._components:
            for i, pd in enumerate(comp.proposals):
                prop = _proposal_from_dict(pd)
                if prop.status == 'selected':
                    prop.status = 'in_evaluation'
                    comp.proposals[i] = asdict(prop)
        self._rebuild_grid()
        self._rebuild_selection()
        self._update_comp_header()
        self.changed.emit()

    def _open_compare(self):
        selected = self._get_selected_proposals()
        if len(selected) < 2:
            return
        dlg = _CompareDialog(selected, parent=self)
        dlg.exec_()

    # ── Rebuild helpers ───────────────────────────────────────────────────────

    def _rebuild_comp_rows(self):
        while self._comp_lay.count():
            item = self._comp_lay.takeAt(0)
            if w := item.widget():
                w.setParent(None)

        for i, comp in enumerate(self._components):
            row = _ComponentRow(comp, i + 1, comp.id == self._active_id)
            row.clicked.connect(self._on_comp_row_clicked)
            row.edit_req.connect(self._edit_component)
            row.delete_req.connect(self._delete_component)
            self._comp_lay.addWidget(row)

        self._comp_lay.addStretch()

    def _on_comp_row_clicked(self, comp_id: str):
        self._active_id = comp_id if self._active_id != comp_id else None
        self._rebuild_comp_rows()
        self._update_comp_header()
        self._repopulate_combos()
        self._rebuild_grid()
        self._rebuild_technique_grid()
        self._rebuild_brief()
        self._btn_add_prop.setEnabled(self._active_id is not None)
        self._btn_add_prop.setToolTip(
            '' if self._active_id else t('rd.select_component_first')
        )

    def _repopulate_combos(self):
        # "All components" combo
        self._combo_comp.blockSignals(True)
        self._combo_comp.clear()
        self._combo_comp.addItem(t('rd.all_components'), None)
        for comp in self._components:
            self._combo_comp.addItem(comp.name, comp.id)
        # Sync to active_id
        for i in range(self._combo_comp.count()):
            if self._combo_comp.itemData(i) == self._active_id:
                self._combo_comp.setCurrentIndex(i)
                break
        else:
            self._combo_comp.setCurrentIndex(0)
        self._combo_comp.blockSignals(False)

        # Gather all unique categories and suppliers from visible proposals
        proposals = self._get_visible_proposals()
        cats = sorted({p.category for p in proposals if p.category})
        sups = sorted({p.supplier for p in proposals if p.supplier})

        self._combo_cat.blockSignals(True)
        self._combo_cat.clear()
        self._combo_cat.addItem(t('rd.all_categories'), '')
        for c in cats:
            self._combo_cat.addItem(c, c)
        self._combo_cat.blockSignals(False)

        self._combo_sup.blockSignals(True)
        self._combo_sup.clear()
        self._combo_sup.addItem(t('rd.all_suppliers'), '')
        for s in sups:
            self._combo_sup.addItem(s, s)
        self._combo_sup.blockSignals(False)

    def _update_comp_header(self):
        comp = self._get_comp(self._active_id)
        if not comp:
            self._comp_hdr.hide()
            return
        self._comp_hdr.show()
        self._comp_hdr_name.setText(comp.name)
        self._comp_hdr_sup.setText(comp.supplier)
        props = [_proposal_from_dict(pd) for pd in comp.proposals]
        counts = {
            'proposals':     len(props),
            'in_evaluation': sum(1 for p in props if p.status == 'in_evaluation'),
            'selected':      sum(1 for p in props if p.status == 'selected'),
            'rejected':      sum(1 for p in props if p.status == 'rejected'),
        }
        for key, lbl_w in self._stat_labels.items():
            lbl_w.setText(f'{t("rd." + key)}  {counts[key]}')

        n_sel = counts['selected']
        self._btn_compare.setText(f'{t("rd.compare")} ({n_sel})')
        self._btn_compare.setEnabled(n_sel >= 2)

    def _rebuild_grid(self):
        while self._grid_lay.count():
            item = self._grid_lay.takeAt(0)
            if (w := item.widget()) and w is not self._empty_grid_lbl:
                w.setParent(None)

        proposals = self._get_filtered_proposals()
        n_sel = sum(1 for p, _ in self._get_selected_proposals())
        self._btn_compare.setText(f'{t("rd.compare")} ({n_sel})')
        self._btn_compare.setEnabled(n_sel >= 2)

        if not proposals:
            self._grid_lay.addWidget(self._empty_grid_lbl, 0, 0, 1, _COLS)
            self._empty_grid_lbl.show()
            return

        self._empty_grid_lbl.hide()
        for idx, prop in enumerate(proposals):
            card = _ProposalCard(prop)
            card.toggled.connect(self._on_proposal_toggled)
            card.edit_req.connect(self._on_edit_proposal)
            card.reject_req.connect(self._on_reject)
            card.delete_req.connect(self._on_delete_proposal)
            self._grid_lay.addWidget(card, idx // _COLS, idx % _COLS)

        # Fill remaining columns in last row with spacers
        last_row_count = len(proposals) % _COLS
        if last_row_count:
            last_row = len(proposals) // _COLS
            for col in range(last_row_count, _COLS):
                spacer = QWidget()
                spacer.setFixedWidth(168)
                self._grid_lay.addWidget(spacer, last_row, col)

    def _rebuild_technique_grid(self):
        while self._tech_grid_lay.count():
            item = self._tech_grid_lay.takeAt(0)
            if (w := item.widget()) and w is not self._tech_empty_lbl:
                w.setParent(None)

        techniques = self._get_visible_techniques()
        if not techniques:
            self._tech_grid_lay.addWidget(self._tech_empty_lbl, 0, 0, 1, _COLS)
            self._tech_empty_lbl.show()
            return

        self._tech_empty_lbl.hide()
        for idx, tech in enumerate(techniques):
            card = _TechniqueCard(tech)
            card.toggled.connect(self._on_technique_toggled)
            card.edit_req.connect(self._on_edit_technique)
            card.reject_req.connect(self._on_reject_technique)
            card.delete_req.connect(self._on_delete_technique)
            self._tech_grid_lay.addWidget(card, idx // _COLS, idx % _COLS)

        last_row_count = len(techniques) % _COLS
        if last_row_count:
            last_row = len(techniques) // _COLS
            for col in range(last_row_count, _COLS):
                spacer = QWidget()
                spacer.setFixedWidth(168)
                self._tech_grid_lay.addWidget(spacer, last_row, col)

    def _rebuild_selection(self):
        while self._sel_lay.count():
            item = self._sel_lay.takeAt(0)
            if w := item.widget():
                w.setParent(None)

        selected = self._get_selected_proposals()
        self._sel_title.setText(f'{t("rd.selection")} ({len(selected)})')

        if not selected:
            self._sel_lay.addWidget(self._sel_empty)
            self._sel_empty.show()
            self._sel_lay.addStretch()
            return

        self._sel_empty.hide()
        for prop, comp_name in selected:
            row = _SelectionRow(prop, comp_name)
            row.deselect.connect(self._on_deselect)
            self._sel_lay.addWidget(row)
        self._sel_lay.addStretch()

    def _rebuild_brief(self):
        while self._brief_lay.count():
            item = self._brief_lay.takeAt(0)
            if (w := item.widget()) and w is not self._no_brief_lbl:
                w.setParent(None)

        comp = self._get_comp(self._active_id)
        if not comp:
            self._brief_lay.addWidget(self._no_brief_lbl)
            self._no_brief_lbl.show()
            self._brief_lay.addStretch()
            self._btn_note.setEnabled(False)
            self._rebuild_notes()
            return

        self._no_brief_lbl.hide()
        self._btn_note.setEnabled(True)
        brief = _brief_from_dict(comp.brief)
        comp_id = comp.id

        # ── Component identity header ─────────────────────────────────────────
        comp_name_lbl = QLabel(comp.name)
        comp_name_lbl.setStyleSheet(
            f'background: transparent; color: {_TEXT}; font-size: 13px; font-weight: 700;'
        )
        self._brief_lay.addWidget(comp_name_lbl)
        if comp.supplier:
            sup_lbl = QLabel(comp.supplier)
            sup_lbl.setStyleSheet(
                f'background: transparent; color: {_MUTED}; font-size: 11px;'
            )
            self._brief_lay.addWidget(sup_lbl)

        n_props = len(comp.proposals)
        n_sel   = sum(1 for p in comp.proposals
                      if _proposal_from_dict(p).status == 'selected')
        stats_lbl = QLabel(f'{n_props} proposal{"s" if n_props != 1 else ""}  ·  {n_sel} selected')
        stats_lbl.setStyleSheet(
            f'background: transparent; color: {_ACCENT}; font-size: 10px; font-weight: 600;'
        )
        self._brief_lay.addWidget(stats_lbl)

        sep_comp = QFrame()
        sep_comp.setFrameShape(QFrame.HLine)
        sep_comp.setMaximumHeight(1)
        sep_comp.setStyleSheet(f'background: {_BORDER}; border: none; margin: 4px 0;')
        self._brief_lay.addWidget(sep_comp)

        _field_css = f"""
            QTextEdit, QLineEdit {{
                background: {_CARD}; color: {_TEXT};
                border: 1px solid {_BORDER}; border-radius: 5px;
                padding: 4px 6px; font-size: 11px;
            }}
            QTextEdit:focus, QLineEdit:focus {{ border-color: {_ACCENT}; }}
        """

        def _lbl(text: str) -> QLabel:
            l = QLabel(text)
            l.setStyleSheet(_LBL + ' background: transparent;')
            return l

        # Objective
        self._brief_lay.addWidget(_lbl(t('rd.brief_objective')))
        obj_edit = QTextEdit()
        obj_edit.setFixedHeight(52)
        obj_edit.setStyleSheet(_field_css)
        obj_edit.setPlainText(brief.objective)
        obj_edit.textChanged.connect(
            lambda: self._save_brief_field(comp_id, 'objective', obj_edit.toPlainText())
        )
        self._brief_lay.addWidget(obj_edit)

        # Constraints
        self._brief_lay.addWidget(_lbl(t('rd.brief_constraints')))
        con_edit = QTextEdit()
        con_edit.setFixedHeight(52)
        con_edit.setStyleSheet(_field_css)
        con_edit.setPlainText(brief.constraints)
        con_edit.textChanged.connect(
            lambda: self._save_brief_field(comp_id, 'constraints', con_edit.toPlainText())
        )
        self._brief_lay.addWidget(con_edit)

        # Budget min / max
        self._brief_lay.addWidget(_lbl(t('rd.brief_budget')))
        bud_row = QHBoxLayout()
        bud_row.setSpacing(6)
        bmin = QLineEdit(str(brief.budget_min or ''))
        bmin.setPlaceholderText('min €')
        bmin.setFixedHeight(26)
        bmin.setStyleSheet(_field_css)
        bmin.editingFinished.connect(
            lambda: self._save_brief_field(comp_id, 'budget_min', float(bmin.text().strip() or 0))
        )
        dash = QLabel('–')
        dash.setStyleSheet(f'background: transparent; color: {_MUTED}; font-size: 12px;')
        bmax = QLineEdit(str(brief.budget_max or ''))
        bmax.setPlaceholderText('max €')
        bmax.setFixedHeight(26)
        bmax.setStyleSheet(_field_css)
        bmax.editingFinished.connect(
            lambda: self._save_brief_field(comp_id, 'budget_max', float(bmax.text().strip() or 0))
        )
        bud_row.addWidget(bmin)
        bud_row.addWidget(dash)
        bud_row.addWidget(bmax)
        self._brief_lay.addLayout(bud_row)

        # Quantity + unit
        self._brief_lay.addWidget(_lbl(t('rd.brief_quantity')))
        qty_row = QHBoxLayout()
        qty_row.setSpacing(6)
        qty_edit = QLineEdit(str(brief.quantity or 1))
        qty_edit.setFixedHeight(26)
        qty_edit.setFixedWidth(52)
        qty_edit.setStyleSheet(_field_css)
        qty_edit.editingFinished.connect(
            lambda: self._save_brief_field(
                comp_id, 'quantity', int(qty_edit.text().strip() or 1)
            )
        )
        unit_edit = QLineEdit(brief.quantity_unit or 'piece')
        unit_edit.setFixedHeight(26)
        unit_edit.setStyleSheet(_field_css)
        unit_edit.editingFinished.connect(
            lambda: self._save_brief_field(
                comp_id, 'quantity_unit', unit_edit.text().strip() or 'piece'
            )
        )
        qty_row.addWidget(qty_edit)
        qty_row.addWidget(unit_edit, 1)
        self._brief_lay.addLayout(qty_row)

        self._brief_lay.addStretch()
        self._rebuild_notes()

    def _rebuild_notes(self):
        while self._notes_lay.count():
            item = self._notes_lay.takeAt(0)
            if w := item.widget():
                w.setParent(None)

        comp = self._get_comp(self._active_id)
        notes = comp.brief.get('notes', []) if comp else []
        comp_id = comp.id if comp else None

        _note_field_css = f"""
            QLineEdit {{
                background: {_CARD}; color: {_TEXT};
                border: 1px solid {_BORDER}; border-radius: 4px;
                padding: 2px 5px; font-size: 11px;
            }}
            QLineEdit:focus {{ border-color: {_ACCENT}; }}
        """

        for nd in notes:
            note = BriefNote(**nd) if isinstance(nd, dict) else nd
            note_id = note.id

            w = QFrame()
            w.setStyleSheet(f"""
                QFrame {{ background: {_CARD}; border: 1px solid {_BORDER};
                    border-radius: 6px; }}
            """)
            nl = QVBoxLayout(w)
            nl.setContentsMargins(8, 6, 8, 6)
            nl.setSpacing(4)

            # Editable note text
            txt_edit = QLineEdit(note.text)
            txt_edit.setPlaceholderText('Note text…')
            txt_edit.setFixedHeight(26)
            txt_edit.setStyleSheet(_note_field_css)
            txt_edit.editingFinished.connect(
                lambda nid=note_id, e=txt_edit:
                    self._save_note(comp_id, nid, 'text', e.text())
            )
            nl.addWidget(txt_edit)

            # Author + date row
            meta_row = QHBoxLayout()
            meta_row.setSpacing(4)
            meta_row.setContentsMargins(0, 0, 0, 0)

            auth_edit = QLineEdit(note.author)
            auth_edit.setPlaceholderText('author')
            auth_edit.setFixedHeight(20)
            auth_edit.setStyleSheet(f"""
                QLineEdit {{
                    background: transparent; color: {_MUTED};
                    border: none; border-bottom: 1px solid {_BORDER};
                    font-size: 10px; padding: 0 2px;
                }}
                QLineEdit:focus {{ border-bottom-color: {_ACCENT}; }}
            """)
            auth_edit.editingFinished.connect(
                lambda nid=note_id, e=auth_edit:
                    self._save_note(comp_id, nid, 'author', e.text())
            )

            date_lbl = QLabel(f'· {note.date}')
            date_lbl.setStyleSheet(f'background: transparent; color: {_MUTED}; font-size: 10px;')

            btn_del = QPushButton('×')
            btn_del.setFixedSize(18, 18)
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.setStyleSheet("""
                QPushButton { background: transparent; border: none;
                    color: #94a3b8; font-size: 14px; font-weight: bold; padding: 0; }
                QPushButton:hover { color: #ef4444; }
            """)
            btn_del.clicked.connect(
                lambda _, nid=note_id: self._delete_note(comp_id, nid)
            )

            meta_row.addWidget(auth_edit, 1)
            meta_row.addWidget(date_lbl)
            meta_row.addWidget(btn_del)
            nl.addLayout(meta_row)

            self._notes_lay.addWidget(w)

        self._notes_lay.addStretch()

    # ── Data helpers ──────────────────────────────────────────────────────────

    def _get_comp(self, comp_id: Optional[str]) -> Optional[RdComponent]:
        if not comp_id:
            return None
        return next((c for c in self._components if c.id == comp_id), None)

    def _get_visible_techniques(self) -> List[TechniqueProposal]:
        """All technique proposals for the active component (or all if none selected)."""
        comps = ([self._get_comp(self._active_id)] if self._active_id
                 else self._components)
        result = []
        for comp in comps:
            if comp:
                result.extend(_technique_from_dict(td) for td in comp.technique_proposals)
        return result

    def _get_visible_proposals(self) -> List[MaterialProposal]:
        """All proposals for the active component (or all if none selected)."""
        comps = ([self._get_comp(self._active_id)] if self._active_id
                 else self._components)
        result = []
        for comp in comps:
            if comp:
                result.extend(_proposal_from_dict(pd) for pd in comp.proposals)
        return result

    def _get_filtered_proposals(self) -> List[MaterialProposal]:
        proposals = self._get_visible_proposals()
        cat = self._cat_filter
        sup = self._sup_filter
        q   = self._search_text
        return [
            p for p in proposals
            if (not cat or p.category == cat)
            and (not sup or p.supplier == sup)
            and (not q or q in p.name.lower() or q in p.category.lower()
                 or q in p.origin.lower() or q in p.supplier.lower())
        ]

    def _get_selected_proposals(self) -> List[Tuple[MaterialProposal, str]]:
        result = []
        for comp in self._components:
            for pd in comp.proposals:
                prop = _proposal_from_dict(pd)
                if prop.status == 'selected':
                    result.append((prop, comp.name))
        return result

    # ── Persistence ───────────────────────────────────────────────────────────

    def switch_tab(self, idx: int):
        """Switch the active R&D tab (called from the sidebar sub-nav)."""
        if 0 <= idx < self._tabs.count():
            self._tabs.setCurrentIndex(idx)

    def get_data(self) -> dict:
        return {'components': [asdict(c) for c in self._components]}

    def set_data(self, data: dict):
        self._components = [_comp_from_dict(d) for d in data.get('components', [])]
        self._active_id = None
        self._rebuild_comp_rows()
        self._repopulate_combos()
        self._update_comp_header()
        self._rebuild_grid()
        self._rebuild_technique_grid()
        self._rebuild_selection()
        self._rebuild_brief()

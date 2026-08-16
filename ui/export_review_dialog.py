"""
Export Supplier Review dialog — the PM picks exactly what goes into a
.lyns.review file before it's written: which open 3D viewer tabs (one or
more), which Quality Control images (control points travel with their
image automatically — see QualityControlWidget.get_data()), and which
Supplier it's going to (existing, from the project's registry, or a new
one created on the spot). See core/supplier_registry.py for the Supplier
shape and core/review_format.py for how these choices become a
.lyns.review file.

Inherits BaseModal (light theme) — every dialog in the app is expected to,
per ui/modal_utils.py's own docstring, so this gets a white background and
the same input styling as the rest of the app for free. Section headers are
plain QLabels above plain QListWidgets rather than QGroupBox — QGroupBox's
native title chrome clips against custom borders/margins in this Qt/macOS
combo. Checkable rows are ui/checkable_list.py's shared CheckRow.
"""
from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QListWidget, QAbstractItemView,
)
from PyQt5.QtGui import QFont
from ui.modal_utils import BaseModal, MODAL_BTN_PRIMARY, show_warning_dialog
from ui.checkable_list import LIST_STYLE, add_checkable_row, checked_values, section_label
from core.supplier_registry import Supplier
from i18n import t

_NEW_SUPPLIER_SENTINEL = '__new__'


class ExportReviewDialog(BaseModal):
    """Modal picker for exporting a .lyns.review supplier package.

    Args:
        tabs: [(tab_id, tab_name), ...] — open 3D viewer tabs with a loaded mesh.
        qc_images: [{'id': int, 'image_b64': str}, ...] — QC inspection images.
        suppliers: [dict, ...] — existing Supplier.to_dict() entries for this project.
    """

    def __init__(self, tabs: list, qc_images: list, suppliers: list, parent=None):
        super().__init__(parent, t('export_review.dialog_title'), theme=BaseModal.LIGHT, min_width=460)
        self._tabs = tabs
        self._qc_images = qc_images
        self._suppliers = suppliers
        self._result: dict | None = None

        from ui.annotation_icon import get_app_window_icon
        icon = get_app_window_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)

        title = QLabel(t('export_review.dialog_title'))
        tf = QFont(); tf.setPointSize(14); tf.setBold(True)
        title.setFont(tf)
        title.setStyleSheet('color: #111827; background: transparent; border: none;')
        self._root.addWidget(title)

        # ── 3D tabs picker (multi-select — a supplier review can include
        # more than one open model at once) ────────────────────────────────
        self._root.addWidget(section_label(t('export_review.tab_group')))
        self._tab_list = QListWidget()
        self._tab_list.setStyleSheet(LIST_STYLE)
        self._tab_list.setSelectionMode(QAbstractItemView.NoSelection)
        self._tab_list.setMinimumHeight(90)
        for tab_id, tab_name in tabs:
            add_checkable_row(self._tab_list, tab_id, tab_name or tab_id, checked=True)
        self._root.addWidget(self._tab_list)
        if not tabs:
            self._tab_list.setEnabled(False)
            self._root.addWidget(QLabel(t('export_review.no_tabs')))

        # ── QC image picker ───────────────────────────────────────────────
        self._root.addWidget(section_label(t('export_review.qc_group')))
        self._qc_list = QListWidget()
        self._qc_list.setStyleSheet(LIST_STYLE)
        self._qc_list.setSelectionMode(QAbstractItemView.NoSelection)
        self._qc_list.setMinimumHeight(110)
        from core.image_utils import b64_to_pixmap
        for img in qc_images:
            label = t('export_review.qc_image_label').format(id=img.get('id'))
            pix = b64_to_pixmap(img.get('image_b64', ''))
            add_checkable_row(self._qc_list, img.get('id'), label, icon=pix, checked=True)
        self._root.addWidget(self._qc_list)
        if not qc_images:
            self._qc_list.setEnabled(False)
            self._root.addWidget(QLabel(t('export_review.no_qc_images')))

        # ── Supplier picker ───────────────────────────────────────────────
        self._root.addWidget(section_label(t('export_review.supplier_group')))
        self._supplier_combo = QComboBox()
        for s in suppliers:
            sup = Supplier.from_dict(s)
            self._supplier_combo.addItem(sup.display_name, sup.id)
        self._supplier_combo.addItem(t('export_review.new_supplier'), _NEW_SUPPLIER_SENTINEL)
        self._supplier_combo.currentIndexChanged.connect(self._on_supplier_choice_changed)
        self._root.addWidget(self._supplier_combo)

        self._new_supplier_box = QVBoxLayout()
        self._new_supplier_box.setSpacing(8)
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText(t('export_review.supplier_name_placeholder'))
        self._company_input = QLineEdit()
        self._company_input.setPlaceholderText(t('export_review.supplier_company_placeholder'))
        self._contact_input = QLineEdit()
        self._contact_input.setPlaceholderText(t('export_review.supplier_contact_placeholder'))
        self._new_supplier_box.addWidget(self._name_input)
        self._new_supplier_box.addWidget(self._company_input)
        self._new_supplier_box.addWidget(self._contact_input)
        self._root.addLayout(self._new_supplier_box)
        self._new_supplier_widgets = [self._name_input, self._company_input, self._contact_input]

        self._set_new_supplier_visible(not suppliers)

        # ── buttons ────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._export_btn = self._make_btn(t('export_review.export_btn'), MODAL_BTN_PRIMARY, connect=self._on_export)
        self._export_btn.setEnabled(bool(tabs))
        btn_row.addWidget(self._export_btn)
        btn_row.addWidget(self._make_cancel_btn(t('export_review.cancel')))
        self._root.addLayout(btn_row)

    def _set_new_supplier_visible(self, visible: bool):
        for w in self._new_supplier_widgets:
            w.setVisible(visible)

    def _on_supplier_choice_changed(self, _index):
        is_new = self._supplier_combo.currentData() == _NEW_SUPPLIER_SENTINEL
        self._set_new_supplier_visible(is_new)

    def _on_export(self):
        if not self._tabs:
            return

        tab_ids = checked_values(self._tab_list)
        if not tab_ids:
            show_warning_dialog(self, t('export_review.dialog_title'), t('export_review.tabs_required'))
            return

        image_ids = checked_values(self._qc_list)

        if self._supplier_combo.currentData() == _NEW_SUPPLIER_SENTINEL:
            name = self._name_input.text().strip()
            company = self._company_input.text().strip()
            if not name and not company:
                show_warning_dialog(self, t('export_review.dialog_title'), t('export_review.supplier_required'))
                return
            supplier = Supplier(name=name, company=company, contact=self._contact_input.text().strip())
            is_new_supplier = True
        else:
            supplier_id = self._supplier_combo.currentData()
            match = next((s for s in self._suppliers if s.get('id') == supplier_id), None)
            supplier = Supplier.from_dict(match) if match else Supplier()
            is_new_supplier = False

        self._result = {
            'tab_ids': tab_ids,
            'image_ids': image_ids,
            'supplier': supplier.to_dict(),
            'is_new_supplier': is_new_supplier,
        }
        self.accept()

    def get_result(self) -> dict | None:
        return self._result

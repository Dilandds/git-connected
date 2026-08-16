"""
Annotation merge dialog — shown during "Import Supplier Review"
(ui/project_widget.py's _import_supplier_review) for each open 3D tab
where the returned file has new/updated annotations, new drawing strokes,
new screenshots, or a changed render/material (see core/annotation_merge.py:
diff_annotations/diff_drawings/diff_screenshots/render_changed), once more
for the Drawing Scale workspace if it has new shapes (diff_drawing_scale),
once more for Technical Overview if it has new/updated arrow annotations
(diff_annotations again — same id shape), and once more for Quality
Control if it has new inspection images or new control points
(diff_quality_control). The PM picks, per item, whether to Add it in or
Ignore it; nothing is merged in silently. Every kind of change here
except annotations is new-or-not-changed only — no per-field merge (see
core/annotation_merge.py's docstrings for why).
"""
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QAbstractItemView
from PyQt5.QtGui import QFont, QPixmap
from ui.modal_utils import BaseModal, MODAL_BTN_PRIMARY
from ui.checkable_list import LIST_STYLE, add_checkable_row, checked_values, section_label
from i18n import t


class AnnotationMergeDialog(BaseModal):
    """Args:
        tab_name: display name of the 3D tab this diff belongs to — or,
            for the one Drawing Scale invocation (that workspace isn't
            per-tab), a literal display name like "Drawing Scale" passed
            by the caller.
        supplier_name: display name of the supplier this review came from.
        diff: {'new': [...], 'updated': [...]} from
            core.annotation_merge.diff_annotations(), plus 'drawings'
            (diff_drawings), 'screenshots' (diff_screenshots), 'render'
            (the whole remote texture_data dict, or None/falsy if
            unchanged — render_changed), 'drawing_scale'
            (diff_drawing_scale), and 'qc_images'/'qc_points'
            (diff_quality_control's 'new_images'/'new_points') — all
            merged into one dict by the caller (ui/project_widget.py's
            _merge_supplier_annotations / _merge_supplier_technical_overview
            / _merge_supplier_drawing_scale / _merge_supplier_quality_control).
            Any key can be omitted/empty if that kind of change doesn't
            apply to this invocation.
    """

    def __init__(self, tab_name: str, supplier_name: str, diff: dict, parent=None):
        title = t('annotation_merge.dialog_title').format(tab=tab_name)
        super().__init__(parent, title, theme=BaseModal.LIGHT, min_width=440)
        self._diff = diff
        self._result: dict | None = None

        from ui.annotation_icon import get_app_window_icon
        icon = get_app_window_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)

        title_lbl = QLabel(title)
        tf = QFont(); tf.setPointSize(14); tf.setBold(True)
        title_lbl.setFont(tf)
        title_lbl.setStyleSheet('color: #111827; background: transparent; border: none;')
        self._root.addWidget(title_lbl)

        subtitle = QLabel(t('annotation_merge.subtitle').format(supplier=supplier_name))
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet('color: #6b7280; background: transparent; border: none; font-size: 11px;')
        self._root.addWidget(subtitle)

        self._new_list = None
        new_items = diff.get('new', [])
        if new_items:
            self._root.addWidget(section_label(t('annotation_merge.new_group')))
            self._new_list = QListWidget()
            self._new_list.setStyleSheet(LIST_STYLE)
            self._new_list.setSelectionMode(QAbstractItemView.NoSelection)
            self._new_list.setMinimumHeight(min(200, 44 * len(new_items) + 8))
            for i, entry in enumerate(new_items):
                remote = entry['remote']
                label_text = f"{remote.get('label', 'Point')} — {t('annotation_merge.new_pin_subtitle')}"
                add_checkable_row(self._new_list, i, label_text, checked=True)
            self._root.addWidget(self._new_list)

        self._updated_list = None
        updated_items = diff.get('updated', [])
        if updated_items:
            self._root.addWidget(section_label(t('annotation_merge.updated_group')))
            self._updated_list = QListWidget()
            self._updated_list.setStyleSheet(LIST_STYLE)
            self._updated_list.setSelectionMode(QAbstractItemView.NoSelection)
            self._updated_list.setMinimumHeight(min(200, 44 * len(updated_items) + 8))
            for i, entry in enumerate(updated_items):
                count = len(entry['new_notes'])
                subtitle_text = t('annotation_merge.updated_subtitle').format(count=count)
                add_checkable_row(self._updated_list, i, entry['label'], checked=True, subtitle=subtitle_text)
            self._root.addWidget(self._updated_list)

        self._drawings_list = None
        drawing_items = diff.get('drawings', [])
        if drawing_items:
            self._root.addWidget(section_label(t('annotation_merge.new_drawings_group')))
            self._drawings_list = QListWidget()
            self._drawings_list.setStyleSheet(LIST_STYLE)
            self._drawings_list.setSelectionMode(QAbstractItemView.NoSelection)
            self._drawings_list.setMinimumHeight(min(200, 44 * len(drawing_items) + 8))
            for i, stroke in enumerate(drawing_items):
                point_count = len(stroke.get('points', []))
                label_text = f"Drawing {i + 1} — {t('annotation_merge.new_drawing_subtitle')}"
                subtitle_text = f"{point_count} pts" if point_count else ''
                add_checkable_row(self._drawings_list, i, label_text, checked=True, subtitle=subtitle_text)
            self._root.addWidget(self._drawings_list)

        self._screenshots_list = None
        screenshot_items = diff.get('screenshots', [])
        if screenshot_items:
            self._root.addWidget(section_label(t('annotation_merge.new_screenshots_group')))
            self._screenshots_list = QListWidget()
            self._screenshots_list.setStyleSheet(LIST_STYLE)
            self._screenshots_list.setSelectionMode(QAbstractItemView.NoSelection)
            self._screenshots_list.setMinimumHeight(min(240, 52 * len(screenshot_items) + 8))
            for i, shot in enumerate(screenshot_items):
                thumb = QPixmap(shot.get('image_path', ''))
                label_text = shot.get('note') or f"Screenshot — {shot.get('timestamp', '')}".strip(' —')
                add_checkable_row(
                    self._screenshots_list, i, label_text,
                    icon=thumb if not thumb.isNull() else None,
                    checked=True, subtitle=t('annotation_merge.new_screenshot_subtitle'),
                )
            self._root.addWidget(self._screenshots_list)

        self._render_list = None
        if diff.get('render'):
            self._root.addWidget(section_label(t('annotation_merge.render_group')))
            self._render_list = QListWidget()
            self._render_list.setStyleSheet(LIST_STYLE)
            self._render_list.setSelectionMode(QAbstractItemView.NoSelection)
            self._render_list.setMinimumHeight(52)
            add_checkable_row(
                self._render_list, 0, t('annotation_merge.render_item_label'),
                checked=True, subtitle=t('annotation_merge.render_subtitle'),
            )
            self._root.addWidget(self._render_list)

        # Drawing Scale shapes — one all-or-nothing row for however many new
        # shapes came back (see core/annotation_merge.py's diff_drawing_scale),
        # not itemized per shape: this workspace isn't per-tab like the
        # sections above, and per-shape picking wasn't worth the extra UI
        # for how rarely this has more than a couple of new shapes at once.
        self._drawing_scale_list = None
        from core.annotation_merge import drawing_scale_new_count
        ds_count = drawing_scale_new_count(diff.get('drawing_scale') or {})
        if ds_count:
            self._root.addWidget(section_label(t('annotation_merge.drawing_scale_group')))
            self._drawing_scale_list = QListWidget()
            self._drawing_scale_list.setStyleSheet(LIST_STYLE)
            self._drawing_scale_list.setSelectionMode(QAbstractItemView.NoSelection)
            self._drawing_scale_list.setMinimumHeight(52)
            add_checkable_row(
                self._drawing_scale_list, 0,
                t('annotation_merge.drawing_scale_item_label').format(count=ds_count),
                checked=True, subtitle=t('annotation_merge.new_drawing_subtitle'),
            )
            self._root.addWidget(self._drawing_scale_list)

        self._qc_images_list = None
        qc_images = diff.get('qc_images', [])
        if qc_images:
            from core.image_utils import b64_to_pixmap
            self._root.addWidget(section_label(t('annotation_merge.new_qc_images_group')))
            self._qc_images_list = QListWidget()
            self._qc_images_list.setStyleSheet(LIST_STYLE)
            self._qc_images_list.setSelectionMode(QAbstractItemView.NoSelection)
            self._qc_images_list.setMinimumHeight(min(240, 52 * len(qc_images) + 8))
            for i, img in enumerate(qc_images):
                thumb = b64_to_pixmap(img.get('image_b64', ''))
                point_count = len(img.get('control_points', []))
                label_text = f"Inspection Image {i + 1} — {point_count} point(s)"
                add_checkable_row(
                    self._qc_images_list, i, label_text,
                    icon=thumb if thumb is not None and not thumb.isNull() else None,
                    checked=True, subtitle=t('annotation_merge.new_qc_image_subtitle'),
                )
            self._root.addWidget(self._qc_images_list)

        # New control points on images that already existed on both sides —
        # one all-or-nothing row for however many came back (see
        # core/annotation_merge.py's diff_quality_control), same
        # not-worth-itemizing reasoning as Drawing Scale above.
        self._qc_points_list = None
        qc_points = diff.get('qc_points', [])
        if qc_points:
            self._root.addWidget(section_label(t('annotation_merge.new_qc_points_group')))
            self._qc_points_list = QListWidget()
            self._qc_points_list.setStyleSheet(LIST_STYLE)
            self._qc_points_list.setSelectionMode(QAbstractItemView.NoSelection)
            self._qc_points_list.setMinimumHeight(52)
            add_checkable_row(
                self._qc_points_list, 0,
                t('annotation_merge.new_qc_points_item_label').format(count=len(qc_points)),
                checked=True, subtitle=t('annotation_merge.new_qc_image_subtitle'),
            )
            self._root.addWidget(self._qc_points_list)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        apply_btn = self._make_btn(t('annotation_merge.apply_btn'), MODAL_BTN_PRIMARY, connect=self._on_apply)
        btn_row.addWidget(apply_btn)
        btn_row.addWidget(self._make_cancel_btn(t('annotation_merge.skip_all')))
        self._root.addLayout(btn_row)

    def _on_apply(self):
        new_indices = checked_values(self._new_list) if self._new_list else []
        updated_indices = checked_values(self._updated_list) if self._updated_list else []
        drawing_indices = checked_values(self._drawings_list) if self._drawings_list else []
        screenshot_indices = checked_values(self._screenshots_list) if self._screenshots_list else []
        render_checked = bool(checked_values(self._render_list)) if self._render_list else False
        drawing_scale_checked = bool(checked_values(self._drawing_scale_list)) if self._drawing_scale_list else False
        qc_image_indices = checked_values(self._qc_images_list) if self._qc_images_list else []
        qc_points_checked = bool(checked_values(self._qc_points_list)) if self._qc_points_list else False
        self._result = {
            'new': [self._diff['new'][i] for i in new_indices],
            'updated': [self._diff['updated'][i] for i in updated_indices],
            'drawings': [self._diff['drawings'][i] for i in drawing_indices],
            'screenshots': [self._diff['screenshots'][i] for i in screenshot_indices],
            'render': self._diff['render'] if render_checked else None,
            'drawing_scale': self._diff.get('drawing_scale') if drawing_scale_checked else {},
            'qc_images': [self._diff['qc_images'][i] for i in qc_image_indices],
            'qc_points': self._diff.get('qc_points', []) if qc_points_checked else [],
        }
        self.accept()

    def get_result(self) -> dict | None:
        """None if the dialog was cancelled/rejected (Skip All) — caller
        should treat that as "merge nothing" for this tab."""
        return self._result

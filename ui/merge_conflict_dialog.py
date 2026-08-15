"""
Merge Conflict Dialog — shown when saving a project collides with changes
someone else already saved to the same field(s).

One row per core.project_merge.Conflict, showing both values with a
pick-one-side choice — per the milestone's explicit design decision
("pick one side per field", no manual-merge editor for this version).
Delete-vs-edit conflicts never reach this dialog — the merge engine
resolves those safely on its own (see core/project_merge.py). Conflicts
folded together by core.project_merge.fold_linked_conflicts (mirrored
copies of the same field across sections, e.g. the sidebar Title auto-
copied into Report/Brief/Quality Control) show as a single row with a
note about what else it affects, instead of one row per copy.
"""
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QWidget, QFrame, QButtonGroup
from PyQt5.QtCore import Qt

from ui.modal_utils import BaseModal
from i18n import t

# (section, field) -> friendly display name. Not exhaustive by design —
# anything missing falls back to a humanized version of the raw key
# (see _humanize), so an unmapped field still reads reasonably instead of
# needing every single field pre-registered here.
_SECTION_LABELS = {
    'project_info': 'Project Info',
    'todo': 'To-Do',
    'timeline': 'Timeline',
    'traceability': 'Traceability',
    'report': 'Report',
    'quality_control': 'Quality Control',
    'brief': 'Project Brief',
    'drawing_scale': 'Drawing Scale',
    'technical_overview': 'Technical Overview',
    'viewer_tabs': '3D Viewer',
    'assignment': 'Assignment',
    'rd': 'R&D',
    'estimated_cost': 'Estimated Cost',
    'files': 'Files',
    'validation': 'Validation',
    'prototype': 'Prototype',
    'version_comparison': 'Version Comparison',
    'glossary': 'Glossary',
}

_FIELD_LABELS = {
    ('project_info', 'title'): 'Project Title',
    ('project_info', 'company'): 'Company',
    ('project_info', 'number'): 'Project Number',
    ('project_info', 'project_manager'): 'Project Manager',
    ('project_info', 'status'): 'Status',
    ('project_info', 'photo_b64'): 'Project Photo',
    ('report', 'project_name'): 'Project Name',
    ('report', 'project_reference'): 'Project Reference',
    ('report', 'project_manager'): 'Project Manager',
    ('report', 'project_photo_b64'): 'Project Photo',
    ('report', 'logo_b64'): 'Logo',
    ('report', 'followup'): 'Follow-up',
    ('report', 'comments'): 'Comments',
    ('report', 'photo_blocks'): 'Photos',
    ('report', 'company_extras'): 'Company Info',
    ('report', 'partner_extras'): 'Partner Info',
    ('report', 'attendees'): 'Attendees',
    ('brief', 'product_name'): 'Product Name',
    ('brief', 'reference'): 'Reference / Version',
    ('quality_control', 'designation'): 'Designation',
    ('quality_control', 'inspected_by'): 'Inspected By',
    ('quality_control', 'inspection_date'): 'Inspection Date',
    ('quality_control', 'overall_status'): 'Overall Status',
    ('quality_control', 'image_b64'): 'Photo',
    ('quality_control', 'annotations'): 'Marked Points',
    ('quality_control', 'name'): 'Name',
    ('quality_control', 'status'): 'Status',
    ('quality_control', 'comment'): 'Comment',
    ('quality_control', 'color'): 'Color',
    ('todo', 'title'): 'Task Title',
    ('todo', 'date'): 'Due Date',
    ('todo', 'notes'): 'Notes',
    ('todo', 'priority'): 'Priority',
    ('timeline', 'name'): 'Name',
    ('timeline', 'project_manager'): 'Project Manager',
    ('traceability', 'name'): 'Name',
    ('traceability', 'status'): 'Status',
    ('traceability', 'image_b64'): 'Image',
    ('traceability', 'product_image_b64'): 'Product Image',
    ('drawing_scale', 'unit'): 'Unit',
    ('drawing_scale', 'scale_ratio'): 'Scale Ratio',
    ('technical_overview', 'document'): 'Document',
    ('viewer_tabs', 'content'): 'Model Tab',
    ('assignment', 'title'): 'Card Title',
    ('assignment', 'supplier'): 'Supplier',
    ('assignment', 'status'): 'Status',
    ('assignment', 'image_name'): 'Image',
    ('assignment', 'image_b64'): 'Image',
    ('assignment', 'orientation'): 'Orientation',
    ('rd', 'name'): 'Name',
    ('rd', 'supplier'): 'Supplier',
    ('rd', 'status'): 'Status',
    ('rd', 'image_b64'): 'Image',
    ('rd', 'text'): 'Note',
    ('estimated_cost', 'name'): 'Name',
    ('estimated_cost', 'tasks'): 'Tasks',
    ('files', 'name'): 'Name',
    ('files', 'versions'): 'Versions',
    ('validation', 'signature'): 'Signature',
    ('validation', 'modifications'): 'Modifications',
    ('validation', 'action_plan'): 'Action Plan',
    ('validation', 'schedule_dates'): 'Schedule Dates',
    ('prototype', 'comments'): 'Comments',
    ('prototype', 'status'): 'Status',
    ('prototype', 'image_b64s'): 'Photos',
    ('prototype', 'files'): 'Files',
    ('version_comparison', 'comments'): 'Comments',
    ('version_comparison', 'photo_b64s'): 'Photos',
    ('glossary', 'term'): 'Term',
    ('glossary', 'definition'): 'Definition',
}


def _humanize(key: str) -> str:
    return key.replace('_', ' ').strip().title() if key else ''


def _section_label(section: str) -> str:
    return _SECTION_LABELS.get(section) or _humanize(section)


def _field_label(section: str, field_key: str) -> str:
    return _FIELD_LABELS.get((section, field_key)) or _humanize(field_key)


class MergeConflictDialog(BaseModal):
    def __init__(self, parent, conflicts):
        super().__init__(parent, t('project.msg.conflict_title'), theme=BaseModal.LIGHT, min_width=800)
        self._conflicts = conflicts
        self._choices = []  # (mine_btn, theirs_btn) per conflict, same order as self._conflicts

        intro = QLabel(t('project.msg.conflict_intro'))
        intro.setWordWrap(True)
        intro.setStyleSheet(f'color: {self._muted}; font-size: 12px; background: transparent; border: none;')
        self._root.addWidget(intro)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMaximumHeight(500)
        container = QWidget()
        rows_layout = QVBoxLayout(container)
        rows_layout.setSpacing(10)
        for conflict in conflicts:
            rows_layout.addWidget(self._build_row(conflict))
        rows_layout.addStretch()
        scroll.setWidget(container)
        self._root.addWidget(scroll)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.cancel_btn = self._make_cancel_btn(t('common.cancel'))
        self.ok_btn = self._make_ok_btn(t('project.msg.conflict_apply'))
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.ok_btn)
        self._root.addLayout(btn_row)

    def _build_row(self, conflict) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            'QFrame { background-color: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; }'
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        needs_generic = self._needs_generic_buttons(conflict)

        label = QLabel(self._describe(conflict))
        label.setWordWrap(True)
        label.setStyleSheet(
            'font-size: 13px; font-weight: bold; color: #111827; background: transparent; border: none;'
        )
        layout.addWidget(label)

        also_affects = getattr(conflict, 'also_affects', None)
        if also_affects:
            names = ', '.join(dict.fromkeys(_section_label(c.section) for c in also_affects))
            note = QLabel(t('project.msg.conflict_also_affects').format(sections=names))
            note.setWordWrap(True)
            note.setStyleSheet(f'color: {self._muted}; font-size: 11px; font-style: italic; '
                                f'background: transparent; border: none;')
            layout.addWidget(note)

        if needs_generic:
            mine_text = t('project.msg.conflict_keep_mine_generic')
            theirs_text = t('project.msg.conflict_keep_theirs_generic')
        else:
            mine_text = t('project.msg.conflict_keep_mine').format(value=self._truncate(conflict.local_value))
            theirs_text = t('project.msg.conflict_keep_theirs').format(value=self._truncate(conflict.remote_value))

        mine_btn = QPushButton(mine_text)
        theirs_btn = QPushButton(theirs_text)
        group = QButtonGroup(frame)
        for btn in (mine_btn, theirs_btn):
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(self._choice_btn_style())
            group.addButton(btn)
        group.setExclusive(True)
        mine_btn.setChecked(True)  # default to the saver's own change

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(mine_btn, 1)
        row.addWidget(theirs_btn, 1)
        layout.addLayout(row)

        self._choices.append((mine_btn, theirs_btn))
        return frame

    @staticmethod
    def _choice_btn_style() -> str:
        return """
            QPushButton {
                background-color: white; color: #111827;
                border: 1px solid #d1d5db; border-radius: 6px;
                padding: 8px 12px; font-size: 12px; text-align: left;
            }
            QPushButton:checked {
                background-color: #eff6ff; border: 2px solid #2596BE; color: #1e3a5f;
                font-weight: bold;
            }
            QPushButton:hover { border-color: #2596BE; }
        """

    @staticmethod
    def _is_whole_section(conflict) -> bool:
        # merge_whole_section() always creates its Conflict with field ==
        # section (see core/project_merge.py) — the tell-tale that this is
        # an entire opaque section, not a specific named field, so there's
        # no meaningful single "value" to preview.
        return conflict.field == conflict.section

    @classmethod
    def _needs_generic_buttons(cls, conflict) -> bool:
        """True whenever a value isn't sensible to preview as short text —
        a whole opaque section, any conflict whose local_value/remote_value
        is itself a list/dict/bytes/etc rather than a simple scalar (e.g.
        technical_overview's document+annotations conflict, or report's
        photo_blocks/attendees), or a base64-embedded image/file (every
        such field across the app is named with a `_b64`/`_b64s` suffix —
        see core/image_utils.py — a base64 string IS technically a `str`,
        so without this explicit name check it would slip past the
        type-based test below and get dumped as raw button text). Deliberately
        broader than _is_whole_section (which still drives _describe's
        message wording below) — this only controls whether the buttons
        try to preview the raw value."""
        if cls._is_whole_section(conflict):
            return True
        if conflict.field.endswith('_b64') or conflict.field.endswith('_b64s'):
            return True
        for value in (conflict.local_value, conflict.remote_value):
            if value is not None and not isinstance(value, (str, int, float, bool)):
                return True
        return False

    @classmethod
    def _describe(cls, conflict) -> str:
        section_label = _section_label(conflict.section)
        if cls._is_whole_section(conflict):
            return t('project.msg.conflict_whole_section').format(section=section_label)
        field_label = _field_label(conflict.section, conflict.field)
        path_labels = getattr(conflict, 'path_labels', None)
        if path_labels:
            return ' › '.join((section_label, *path_labels, field_label))
        return f'{section_label} › {field_label}'

    @staticmethod
    def _truncate(value, limit: int = 80) -> str:
        text = '' if value is None else str(value)
        return text if len(text) <= limit else text[: limit - 1] + '…'

    def apply_resolutions(self):
        """Write each conflict's chosen value via its resolve() callback,
        including every conflict it was folded together with (also_affects)
        — each follower gets its OWN local/remote value, picked by the same
        side the user chose for the primary (they're equal by construction,
        folding only happens when they already match, but resolving this
        way is robust regardless). Call only after exec_() returns Accepted."""
        for conflict, (mine_btn, _theirs_btn) in zip(self._conflicts, self._choices):
            keep_mine = mine_btn.isChecked()
            if conflict.resolve is not None:
                conflict.resolve(conflict.local_value if keep_mine else conflict.remote_value)
            for follower in getattr(conflict, 'also_affects', None) or []:
                if follower.resolve is not None:
                    follower.resolve(follower.local_value if keep_mine else follower.remote_value)

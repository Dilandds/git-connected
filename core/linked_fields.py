"""
Linked Fields - declares which fields across different sections are meant
to always mirror the same underlying value.

Several screens auto-copy the Project sidebar's fields into their own data
(an "auto-fill unless the user already customized it" pattern used
throughout the app — see e.g. ui/report/header_section.py's
update_project_info, ui/brief/widget.py's update_project_info,
ui/quality_control_widget.py's update_project_info). Because each copy is
stored separately, a single edit to the sidebar can independently conflict
in several sections at once — core.project_merge.fold_linked_conflicts uses
this table to collapse those into one prompt instead of asking the same
question 3-4 times for what's really one edit.

Each entry: source (section, field) -> list of destination (section, field)
pairs. Deliberately NOT exhaustive — see the omissions below.

Omitted on purpose:
- technical_overview's own copy of title/property (inside its bundle's
  sidebar metadata) is merged field-by-field but never interactively
  conflicted at all (core.project_merge._merge_technical_overview uses
  merge_dict_fields_prefer_local, which silently auto-resolves a dual-edit
  instead of producing a Conflict) — there's simply never a Conflict on
  this side to fold into, so it stays out of this table.
- photo_b64 (the sidebar's project photo, embedded as base64 like every
  other image field in the app) is omitted entirely: two of its known
  destinations (traceability's main-component image and row1's
  product_image_b64) have no auto-fill guard at all
  (ui/traceability/widget.py's update_project_info,
  ui/traceability/row1_product_info.py's update_project_info) — they
  always overwrite, which is a pre-existing traceability-specific bug,
  not something this table should paper over by folding a field whose
  "customized independently" signal can't be trusted for every
  destination.
"""
from typing import Dict, List, Tuple

LINKED_FIELDS: Dict[Tuple[str, str], List[Tuple[str, str]]] = {
    ('project_info', 'title'): [
        ('report', 'project_name'),
        ('brief', 'product_name'),
        ('quality_control', 'designation'),
    ],
    ('project_info', 'number'): [
        ('report', 'project_reference'),
        ('brief', 'reference'),
    ],
    ('project_info', 'project_manager'): [
        ('report', 'project_manager'),
        ('timeline', 'project_manager'),
    ],
}

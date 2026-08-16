"""
Diffs a supplier's returned 3D-tab annotations and drawings against what's
currently live in LYNS360, for the Supplier Review Workflow's import step
(see ui/project_widget.py's _import_supplier_review and
ui/annotation_merge_dialog.py for the PM-facing Add/Ignore prompt).

Two kinds of annotation change a supplier's LYNS Lite session can produce
(see ui/annotation_panel.py's Annotation.added_by / supplier_notes):
  - a brand new annotation (added_by='supplier', id not seen locally)
  - feedback (text/photos) attached to one of the PM's own existing
    annotations, without touching its original content (supplier_notes)

Matching is by annotation id — stable within one tab's lifetime (see
Annotation/AnnotationPanel._next_id) — and by note id for supplier_notes
entries, so re-importing the same file twice (or two suppliers reviewing
overlapping content) doesn't duplicate anything already merged in.

Drawing strokes (on-model markup — see viewer_widget_pygfx.py) are a
simpler, third kind of change: diff_drawings below.
"""
from typing import List, Dict, Optional


def diff_annotations(local_annotations: List[dict], remote_annotations: List[dict]) -> Dict[str, list]:
    """Compare a tab's live annotations against a supplier's returned copy.

    Returns:
        {
            'new': [{'remote': <annotation dict>}, ...],
            'updated': [{'annotation_id': int, 'label': str, 'new_notes': [<note dict>, ...]}, ...],
        }
    Both lists are empty if there's nothing to merge (e.g. re-importing a
    file whose changes were already applied).
    """
    local_by_id = {a['id']: a for a in local_annotations}
    new_items = []
    updated_items = []

    for remote in remote_annotations:
        rid = remote.get('id')
        local = local_by_id.get(rid)
        if local is None:
            new_items.append({'remote': remote})
            continue

        local_note_ids = {n.get('id') for n in local.get('supplier_notes', [])}
        new_notes = [n for n in remote.get('supplier_notes', []) if n.get('id') not in local_note_ids]
        if new_notes:
            updated_items.append({
                'annotation_id': rid,
                'label': local.get('label') or remote.get('label') or 'Point',
                'new_notes': new_notes,
            })

    return {'new': new_items, 'updated': updated_items}


def diff_drawings(local_drawings: List[dict], remote_drawings: List[dict]) -> List[dict]:
    """Compare a tab's live on-model drawing strokes (see
    viewer_widget_pygfx.py's get_draw_strokes/restore_draw_strokes) against
    a supplier's returned copy.

    Strokes have no id — each is just {'points': [[x,y,z],...], 'color':
    '#RRGGBB'} — so unlike diff_annotations, matching is by exact content
    instead. A remote stroke counts as new if no local stroke has the same
    points+color, so re-importing the same file twice (or two suppliers
    drawing on the same tab) doesn't duplicate anything already merged in.

    Returns the list of new stroke dicts, empty if there's nothing to add.
    """
    def _key(stroke):
        return (
            tuple(tuple(p) for p in stroke.get('points', [])),
            stroke.get('color'),
        )
    local_keys = {_key(s) for s in local_drawings}
    return [s for s in remote_drawings if _key(s) not in local_keys]


def diff_screenshots(local_screenshots: List[dict], remote_screenshots: List[dict]) -> List[dict]:
    """Compare a tab's live screenshots against a supplier's returned copy,
    matched by id (assigned once at capture — see ui/screenshot_panel.py).
    Like diff_drawings, this is new-items-only: a screenshot present on
    both sides is never compared or offered as an "update" here — only
    ones the supplier added that aren't already present locally.

    local_screenshots: [{'id': ...}, ...] — only 'id' is read, so callers
    can pass their own tuples/dicts as long as each has that key.
    remote_screenshots: [{'id', 'image_path', 'timestamp', 'note'}, ...],
    the shape core.ecto_format.EctoFormat.import_ecto returns.
    """
    local_ids = {s.get('id') for s in local_screenshots}
    return [s for s in remote_screenshots if s.get('id') not in local_ids]


def render_changed(local_texture: Optional[dict], remote_texture: Optional[dict]) -> bool:
    """Whether a supplier's returned render/material data (texture_data —
    see viewer_widget_pygfx.py's get_texture_data) differs from what's
    live locally. Reuses core/project_merge.py's own path normalization
    (import_ecto resolves texture-map paths to a fresh temp-extraction
    directory on every decode, so comparing raw paths would call an
    untouched material "changed" every time) so this one whole-field
    yes/no question is judged the same way the project-level merge
    already judges the identical field — never merged piece by piece,
    only ever "take the whole updated one or don't" (see
    AnnotationMergeDialog and _merge_viewer_tab_content's own docstring
    for why: no natural per-item identity inside a material blob worth
    tracking, e.g. which slider changed)."""
    from core.project_merge import _normalize_texture_for_compare
    return _normalize_texture_for_compare(local_texture) != _normalize_texture_for_compare(remote_texture)


_DRAWING_SCALE_SHAPE_KEYS = ('measurements', 'arrows', 'rectangles', 'circles', 'texts', 'extra_ref_lines')


def diff_drawing_scale(local_state: Optional[dict], remote_state: Optional[dict]) -> Dict[str, list]:
    """Compare the Drawing Scale workspace's live shapes (see
    ui/scale_canvas.py's ScaleCanvas.get_state/set_state) against a
    supplier's returned copy. Unlike on-model drawing strokes, every shape
    type here already has a stable per-item id, so — like
    diff_screenshots — this is matched by id and new-items-only: a shape
    present on both sides is never compared or offered as an "update",
    only ones the supplier added that aren't already present locally.

    Returns {shape_type: [new_item, ...], ...} — only shape types with at
    least one new item are included, so an empty dict means nothing new."""
    local_state = local_state or {}
    remote_state = remote_state or {}
    result = {}
    for key in _DRAWING_SCALE_SHAPE_KEYS:
        local_ids = {item.get('id') for item in (local_state.get(key) or [])}
        new_items = [item for item in (remote_state.get(key) or []) if item.get('id') not in local_ids]
        if new_items:
            result[key] = new_items
    return result


def drawing_scale_new_count(diff: Dict[str, list]) -> int:
    return sum(len(v) for v in diff.values())


def diff_quality_control(local_images: List[dict], remote_images: List[dict]) -> Dict[str, list]:
    """Compare a project's live Quality Control inspection images (see
    ui/quality_control_widget.py's _QCLeftPanel.get_data/set_data) against
    a supplier's returned copy. Two kinds of change a supplier's LYNS Lite
    session can produce:
      - a brand new inspection image (matched by the image's own stable
        id — assigned once at capture/upload, same idea as
        diff_screenshots)
      - a new control point added onto an image that already existed —
        points have no stable id of their own (ControlPoint.id gets
        renumbered to a photo-scoped 1..N position on every UI rebuild,
        see ControlPoint's own docstring), so, like diff_drawings,
        matching is by exact content: the owning image's id plus the
        point's placement coordinates (its paired entry in that image's
        'annotations' list — the two lists are index-aligned, see
        _on_image_point_added).

    Returns:
        {
            'new_images': [<image dict>, ...],
            'new_points': [{'image_id': ..., 'annotation': [x,y,x,y],
                             'control_point': <control point dict>}, ...],
        }
    Both lists are empty if there's nothing to merge (e.g. re-importing a
    file whose changes were already applied)."""
    local_by_id = {img.get('id'): img for img in local_images}
    new_images = [img for img in remote_images if img.get('id') not in local_by_id]

    local_point_keys = {
        (img.get('id'), tuple(ann))
        for img in local_images
        for ann in img.get('annotations', [])
    }

    new_points = []
    for img in remote_images:
        img_id = img.get('id')
        if img_id not in local_by_id:
            continue  # whole image already covered by new_images above
        for ann, cp in zip(img.get('annotations', []), img.get('control_points', [])):
            if (img_id, tuple(ann)) not in local_point_keys:
                new_points.append({'image_id': img_id, 'annotation': list(ann), 'control_point': cp})

    return {'new_images': new_images, 'new_points': new_points}


def qc_new_count(diff: Dict[str, list]) -> int:
    return len(diff.get('new_images') or []) + len(diff.get('new_points') or [])


def has_changes(diff: Dict[str, list]) -> bool:
    return bool(
        diff.get('new') or diff.get('updated') or diff.get('drawings')
        or diff.get('screenshots') or diff.get('render')
    )

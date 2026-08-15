"""
Project Merge - Three-way merge for concurrently-edited .lyns.pjt saves.

Pure functions only — no PyQt import anywhere in this file, no file I/O.
The caller (ui/project_widget.py) is responsible for reading the on-disk
file and handing this module three already-parsed dicts:

    base   — the project data as it was when this session last loaded/saved it
    local  — this session's current in-memory data, about to be saved
    remote — what's actually on disk right now (someone else may have saved
             since this session's `base` was captured)

If `remote == base`, nobody else touched the file — the caller should just
overwrite, no merge needed (that's the caller's decision, not this module's).
Otherwise `merge_project()` combines `local` and `remote` section by
section, returning the merged data plus a flat list of field-level
Conflicts for anything that was changed differently on both sides — the
caller shows those to whoever is saving and lets them pick a side, then
calls each Conflict's `resolve(value)` to write the chosen value into the
already-merged result (each Conflict's resolver closes over the exact
dict/key it came from, so there's no need to re-locate it by walking
`path` again — `path` is purely informational, for display).

Delete-vs-edit conflicts (an item deleted on one side, edited on the
other) are NOT included in the interactive conflict list — the merge
already resolves them safely on its own (favoring "don't lose data": the
edited version survives). Only "the same field was changed differently on
both sides" produces a Conflict a person needs to look at, per the brief.

Metadata bookkeeping fields on the save envelope itself (created_by,
last_saved_by/at, password_hash, file_type, version) are NOT part of what
this module merges — the caller stamps those directly, since "who saved
last and when" is always this save, not something to three-way-merge.
"""
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

_SENTINEL = object()  # distinguishes "key absent" from "key present with value None"


@dataclass
class Conflict:
    """One field that was changed differently on both sides since `base`.
    `resolve(value)` writes the caller's chosen value into the merged
    result — always attached by this module, never left None for a
    genuine field conflict (delete-vs-edit conflicts don't produce
    Conflict objects at all; see module docstring)."""
    section: str
    path: Tuple[Any, ...]   # id path to the item, e.g. ('operators', 3, 'operations', 1) — display only
    field: str
    local_value: Any
    remote_value: Any
    resolve: Optional[Callable[[Any], None]] = field(default=None, compare=False, repr=False)
    # Human-readable version of `path` (item names instead of raw ids), where
    # cheaply available — e.g. a to-do task's own title instead of its uuid.
    # Falls back to '#<id>' per segment when no obvious name field exists.
    path_labels: Tuple[str, ...] = field(default_factory=tuple, compare=False)
    # Other Conflicts that are just mirrored copies of THIS one (see
    # core.linked_fields / fold_linked_conflicts) — populated by
    # fold_linked_conflicts, empty otherwise. The caller resolves these
    # together with their parent instead of asking about each separately.
    also_affects: List['Conflict'] = field(default_factory=list, compare=False, repr=False)


# ── generic three-way scalar merge ──────────────────────────────────────────

def _merge_scalar(base_v, local_v, remote_v, section: str, path: tuple, field_name: str,
                   *, target: Optional[dict] = None, target_key: Optional[str] = None,
                   path_labels: tuple = ()):
    """Three-way merge of a single value. Returns (value, [Conflict]).
    If target/target_key are given, a resulting Conflict's resolve()
    writes the chosen value straight into target[target_key]."""
    if local_v == remote_v:
        return local_v, []
    if local_v == base_v:
        return remote_v, []            # only remote changed it
    if remote_v == base_v:
        return local_v, []             # only local changed it
    # changed differently on both sides
    conflict = Conflict(section, path, field_name, local_value=local_v, remote_value=remote_v,
                         path_labels=path_labels)
    if target is not None and target_key is not None:
        conflict.resolve = lambda v, _t=target, _k=target_key: _t.__setitem__(_k, v)
    return remote_v, [conflict]


def merge_whole_section(base, local, remote, section: str,
                         target: Optional[dict] = None, target_key: Optional[str] = None) -> Tuple[Any, List[Conflict]]:
    """Treat an entire section as one opaque value — used for sections that
    aren't structured as id-keyed lists (technical_overview, drawing_scale,
    and any not-yet-audited section). No pretense of solving item-level
    merging inside them; if both sides touched it, that's a single
    section-wide conflict."""
    return _merge_scalar(base, local, remote, section, (), section, target=target, target_key=target_key)


# ── field-based dict merge ──────────────────────────────────────────────────

def merge_dict_fields(base: Optional[dict], local: Optional[dict], remote: Optional[dict],
                       section: str = '', path: tuple = (), path_labels: tuple = (),
                       skip_keys: Sequence[str] = ()) -> Tuple[dict, List[Conflict]]:
    """Three-way merge of a flat dict, field by field. `skip_keys` lets a
    caller exclude keys it's merging separately (e.g. a nested id-keyed
    list that needs merge_nested_by_path instead of naive field merging).
    A value that's itself a list/dict (and not in skip_keys) is still
    merged as one opaque scalar here — compared by equality, replaced
    wholesale if only one side changed it, flagged as a conflict only if
    both sides changed it differently. That's the correct "no clean
    per-item merge available" fallback for exactly this reason wherever
    it's used (e.g. a report page's photo_blocks)."""
    base = base or {}
    local = local or {}
    remote = remote or {}
    conflicts: List[Conflict] = []
    merged: Dict[str, Any] = {}
    all_keys = set(base) | set(local) | set(remote)
    for key in all_keys:
        if key in skip_keys:
            continue
        value, key_conflicts = _merge_scalar(
            base.get(key, _SENTINEL), local.get(key, _SENTINEL), remote.get(key, _SENTINEL),
            section, path, key, target=merged, target_key=key, path_labels=path_labels,
        )
        if value is not _SENTINEL:
            merged[key] = value
        conflicts.extend(key_conflicts)
    return merged, conflicts


def merge_dict_fields_prefer_local(base: Optional[dict], local: Optional[dict], remote: Optional[dict],
                                    skip_keys: Sequence[str] = ()) -> dict:
    """Same three-way field logic as merge_dict_fields, but a genuine
    dual-edit on the same key is silently resolved in favor of `local`
    instead of producing a Conflict. For low-stakes fields where asking is
    worse than occasionally picking the "wrong" side (e.g.
    technical_overview's sidebar metadata, which mostly just mirrors
    project_info and is explicitly not worth interrupting a save over)."""
    base = base or {}
    local = local or {}
    remote = remote or {}
    merged: Dict[str, Any] = {}
    for key in set(base) | set(local) | set(remote):
        if key in skip_keys:
            continue
        b, l, r = base.get(key, _SENTINEL), local.get(key, _SENTINEL), remote.get(key, _SENTINEL)
        if l == r:
            value = l
        elif l == b:
            value = r        # only remote changed it
        elif r == b:
            value = l        # only local changed it
        else:
            value = l        # changed differently on both sides — never ask, prefer local
        if value is not _SENTINEL:
            merged[key] = value
    return merged


# ── id-collision detection ───────────────────────────────────────────────────

def detect_id_collision(local_new_ids: set, remote_new_ids: set) -> set:
    """Ids that were independently minted for NEW items on both sides since
    `base` — a collision, not the same item edited twice. Locally-scoped
    sequential-integer ids (timeline, traceability) make this a real
    scenario: two people each add a new sibling under the same parent and
    each mints the same "next id" for genuinely different content."""
    return local_new_ids & remote_new_ids


def _renumber_collisions(remote_items: List[dict], colliding_ids: set,
                          all_known_ids: set, id_key: str) -> List[dict]:
    """Give remote's colliding new items fresh ids so they survive the merge
    as distinct items instead of being conflated with local's same-id item."""
    if not colliding_ids:
        return remote_items
    next_id = (max(all_known_ids) + 1) if all_known_ids else 1
    renumbered = []
    for item in remote_items:
        if item.get(id_key) in colliding_ids:
            item = dict(item)
            item[id_key] = next_id
            next_id += 1
        renumbered.append(item)
    return renumbered


# ── id-based list merge (flat and nested) ────────────────────────────────────

def _index_by_id(items: List[dict], id_key: str) -> Dict[Any, dict]:
    return {item[id_key]: item for item in items if id_key in item}


def _item_label(item_id, *dicts: dict) -> str:
    """Best-effort human label for an item, tried across whichever of
    base/local/remote dicts have it (in that preference order) — 'name'
    covers timeline/traceability/quality_control items, 'title' covers
    to-do tasks, 'project_name' covers report entries. Falls back to the
    raw id (formatted, not bare) when none of those exist, e.g. report
    pages have no name field at all."""
    for d in dicts:
        for key in ('name', 'title', 'project_name'):
            val = (d or {}).get(key)
            if val:
                return str(val)
    return f'#{item_id}'


def merge_nested_by_path(base: List[dict], local: List[dict], remote: List[dict],
                          id_key: str = 'id', child_keys: Sequence[str] = (),
                          section: str = '', path: tuple = (),
                          path_labels: tuple = (),
                          item_merger: Optional[Callable[..., Tuple[dict, List[Conflict]]]] = None,
                          ) -> Tuple[List[dict], List[Conflict]]:
    """Three-way merge of a list of id-keyed dicts. If child_keys is given,
    child_keys[0] names a nested id-keyed list inside each item that gets
    recursively merged the same way (using child_keys[1:] at that level) —
    e.g. child_keys=('operations', 'tasks') merges timeline's
    operators -> operations -> tasks, three levels deep, each level's id
    comparisons scoped to their own parent (ids here are locally-scoped
    sequential counters, not globally unique, so a bare-id comparison
    across different parents would be wrong).

    merge_list_by_id() is just this function with child_keys=().

    An item with MULTIPLE sibling nested lists to merge (not just one
    linear child_keys chain), or a mix of id-keyed and non-id-keyed nested
    lists, doesn't fit the child_keys shape — pass `item_merger(b, l, r,
    item_path, item_path_labels) -> (merged_item, conflicts)` instead;
    it takes full responsibility for that item's own fields and any
    nesting (child_keys is ignored when item_merger is given). See
    core.project_merge's _merge_report_item / _merge_rd_component /
    _merge_validation_session for examples.
    """
    base, local, remote = base or [], local or [], remote or []
    base_by_id = _index_by_id(base, id_key)
    local_by_id = _index_by_id(local, id_key)
    remote_by_id = _index_by_id(remote, id_key)

    # New-on-both-sides id collisions must be resolved before anything else
    # treats "same id" as "same item".
    local_new = set(local_by_id) - set(base_by_id)
    remote_new = set(remote_by_id) - set(base_by_id)
    colliding = detect_id_collision(local_new, remote_new)
    if colliding:
        all_ids = set(base_by_id) | set(local_by_id) | set(remote_by_id)
        remote = _renumber_collisions(remote, colliding, all_ids, id_key)
        remote_by_id = _index_by_id(remote, id_key)

    conflicts: List[Conflict] = []
    merged: List[dict] = []
    seen = set()

    def _order():
        # Deterministic: local's own order first (covers base+local ids),
        # then any purely-remote additions in remote's order.
        for item in local:
            iid = item.get(id_key)
            if iid is not None and iid not in seen:
                seen.add(iid)
                yield iid
        for item in remote:
            iid = item.get(id_key)
            if iid is not None and iid not in seen:
                seen.add(iid)
                yield iid

    child_key = child_keys[0] if child_keys else None
    grandchild_keys = child_keys[1:] if child_keys else ()

    for item_id in _order():
        in_base, in_local, in_remote = item_id in base_by_id, item_id in local_by_id, item_id in remote_by_id
        item_path = path + (item_id,)

        if in_base and not in_local and not in_remote:
            continue  # deleted on both sides

        if in_base and not in_local and in_remote:
            if remote_by_id[item_id] != base_by_id[item_id]:
                # deleted locally, but edited remotely — not an interactive
                # conflict (see module docstring): favor not losing the edit.
                conflicts_for_log = Conflict(section, item_path, '__deleted__',
                                              local_value=None, remote_value=remote_by_id[item_id])
                conflicts.append(conflicts_for_log)
                merged.append(remote_by_id[item_id])
            continue  # cleanly deleted (remote unchanged) — drop it

        if in_base and in_local and not in_remote:
            if local_by_id[item_id] != base_by_id[item_id]:
                conflicts.append(Conflict(section, item_path, '__deleted__',
                                           local_value=local_by_id[item_id], remote_value=None))
                merged.append(local_by_id[item_id])
            continue  # cleanly deleted remotely — drop it

        if not in_base and in_local and not in_remote:
            merged.append(local_by_id[item_id])
            continue

        if not in_base and not in_local and in_remote:
            merged.append(remote_by_id[item_id])
            continue

        # Present on at least local + remote (possibly base too) — field-merge,
        # recursing into the nested child list separately if this level has one.
        b, l, r = base_by_id.get(item_id, {}), local_by_id[item_id], remote_by_id[item_id]
        item_path_labels = path_labels + (_item_label(item_id, l, r, b),)

        if item_merger is not None:
            merged_item, field_conflicts = item_merger(b, l, r, item_path, item_path_labels)
            conflicts.extend(field_conflicts)
            merged.append(merged_item)
            continue

        skip = (child_key,) if child_key else ()
        merged_item, field_conflicts = merge_dict_fields(
            b, l, r, section=section, path=item_path, path_labels=item_path_labels, skip_keys=skip,
        )
        conflicts.extend(field_conflicts)

        if child_key:
            nested_merged, nested_conflicts = merge_nested_by_path(
                b.get(child_key, []), l.get(child_key, []), r.get(child_key, []),
                id_key=id_key, child_keys=grandchild_keys,
                section=section, path=item_path + (child_key,), path_labels=item_path_labels,
            )
            merged_item[child_key] = nested_merged
            conflicts.extend(nested_conflicts)

        merged.append(merged_item)

    return merged, conflicts


def merge_list_by_id(base: List[dict], local: List[dict], remote: List[dict],
                      id_key: str = 'id', section: str = '', path: tuple = (),
                      path_labels: tuple = ()) -> Tuple[List[dict], List[Conflict]]:
    """Three-way merge of a flat list of id-keyed dicts (no nesting)."""
    return merge_nested_by_path(base, local, remote, id_key=id_key, child_keys=(), section=section,
                                 path=path, path_labels=path_labels)


def merge_list_add_only(local: List[Any], remote: List[Any]) -> List[Any]:
    """No id, no conflict possible: union both sides, keeping local's items
    plus anything from remote not already present (exact match). Used for
    sections like viewer_tabs where items are added, not field-merged."""
    local = local or []
    remote = remote or []
    merged = list(local)
    for item in remote:
        if item not in merged:
            merged.append(item)
    return merged


# ── section dispatch ─────────────────────────────────────────────────────────

def _merge_todo(base, local, remote):
    base, local, remote = base or {}, local or {}, remote or {}
    tasks, conflicts = merge_list_by_id(
        base.get('tasks', []), local.get('tasks', []), remote.get('tasks', []),
        id_key='id', section='todo', path=('tasks',),
    )
    return {'tasks': tasks}, conflicts


def _merge_timeline(base, local, remote):
    base, local, remote = base or {}, local or {}, remote or {}
    operators, conflicts = merge_nested_by_path(
        base.get('operators', []), local.get('operators', []), remote.get('operators', []),
        id_key='id', child_keys=('operations', 'tasks'),
        section='timeline', path=('operators',),
    )
    return {'operators': operators}, conflicts


def _merge_project_info(base, local, remote):
    return merge_dict_fields(base, local, remote, section='project_info', path=())


def _merge_traceability(base, local, remote):
    base, local, remote = base or {}, local or {}, remote or {}
    components, conflicts = merge_nested_by_path(
        base.get('components', []), local.get('components', []), remote.get('components', []),
        id_key='id', child_keys=('stages', 'sub_stages', 'parts', 'tasks', 'steps'),
        section='traceability', path=('components',),
    )
    extra, extra_conflicts = merge_dict_fields(
        base.get('extra', {}), local.get('extra', {}), remote.get('extra', {}),
        section='traceability', path=('extra',),
    )
    conflicts += extra_conflicts

    # current_component is a raw list INDEX, not an id — resolve post-merge
    # by looking up whichever id it pointed to before, never merge it as a
    # literal scalar (local's index and remote's index refer to different
    # items once the lists diverge).
    local_components = local.get('components', [])
    idx = local.get('current_component', 0)
    target_id = local_components[idx]['id'] if 0 <= idx < len(local_components) else None
    current_component = 0
    if target_id is not None:
        for i, c in enumerate(components):
            if c.get('id') == target_id:
                current_component = i
                break

    result = {
        'version': local.get('version'),
        'current_component': current_component,
        'extra': extra,
        'components': components,
    }
    result['version'], version_conflicts = _merge_scalar(
        base.get('version'), local.get('version'), remote.get('version'),
        'traceability', (), 'version', target=result, target_key='version',
    )
    conflicts += version_conflicts

    return result, conflicts


def _merge_report(base, local, remote):
    base, local, remote = base or {}, local or {}, remote or {}

    def _merge_report_item(b, l, r, path, path_labels=()):
        # pages need id-based merging; company_extras/partner_extras/attendees
        # have no id field at all, so they're merged as opaque values below
        # (same reasoning as photo_blocks inside pages — handled for free by
        # merge_dict_fields treating an un-skipped list value as one opaque
        # field, replaced wholesale if only one side changed it).
        skip = ('pages', 'company_extras', 'partner_extras', 'attendees')
        merged, conflicts = merge_dict_fields(b, l, r, section='report', path=path,
                                               path_labels=path_labels, skip_keys=skip)

        pages, page_conflicts = merge_list_by_id(
            b.get('pages', []), l.get('pages', []), r.get('pages', []),
            id_key='id', section='report', path=path + ('pages',), path_labels=path_labels,
        )
        merged['pages'] = pages
        conflicts += page_conflicts

        for key in ('company_extras', 'partner_extras', 'attendees'):
            value, key_conflicts = _merge_scalar(
                b.get(key), l.get(key), r.get(key), 'report', path, key,
                target=merged, target_key=key, path_labels=path_labels,
            )
            merged[key] = value
            conflicts += key_conflicts

        return merged, conflicts

    reports, conflicts = merge_nested_by_path(
        base.get('reports', []), local.get('reports', []), remote.get('reports', []),
        id_key='id', section='report', path=('reports',), item_merger=_merge_report_item,
    )

    result = {'logo_path': local.get('logo_path'), 'reports': reports}
    result['logo_path'], logo_conflicts = _merge_scalar(
        base.get('logo_path'), local.get('logo_path'), remote.get('logo_path'),
        'report', (), 'logo_path', target=result, target_key='logo_path',
    )
    conflicts += logo_conflicts

    return result, conflicts


def _normalize_viewer_tab_for_compare(item: Optional[dict]) -> Optional[dict]:
    """Comparison-only view of a decoded viewer-tab entry: annotation
    image_paths and any texture-map path reduced to their bare filename.
    import_ecto() resolves both to absolute paths under a fresh temp-
    extraction directory on every decode (see core/ecto_format.py), so
    comparing them directly would make an untouched tab look "different"
    on every single merge — same class of non-determinism as
    technical_overview's annotations, one level deeper. Pure string
    manipulation, not I/O. Excludes `id` and `bundle_b64` — a tab's
    identity and its non-deterministic raw zip bytes are never part of
    "did this tab's content actually change"."""
    if not item:
        return item
    out = {k: v for k, v in item.items() if k not in ('id', 'bundle_b64')}
    annotations = []
    for ann in out.get('annotations') or []:
        a = dict(ann)
        a['image_paths'] = [os.path.basename(p) for p in a.get('image_paths', [])]
        annotations.append(a)
    out['annotations'] = annotations
    texture = out.get('texture_data')
    if texture:
        texture = dict(texture)
        albedo = texture.get('albedo_map_path')
        if albedo:
            texture['albedo_map_path'] = os.path.basename(albedo)
        parts = texture.get('parts_textures')
        if parts:
            new_parts = []
            for pt in parts:
                pt = dict(pt)
                p = pt.get('albedo_map_path')
                if p:
                    pt['albedo_map_path'] = os.path.basename(p)
                new_parts.append(pt)
            texture['parts_textures'] = new_parts
        out['texture_data'] = texture
    return out


def _merge_viewer_tabs(base, local, remote):
    """3D model tabs are atomic — no sub-merging. A tab's annotations,
    drawings, render/texture state and model itself are never compared or
    merged field by field; the whole tab is one opaque unit, per explicit
    product decision. Unlike every other id-keyed list in this module,
    delete-vs-edit on the SAME tab id is deliberately NOT auto-resolved in
    favor of the edit — it surfaces the same interactive conflict as a
    genuine dual edit, since a 3D model carrying new annotations/drawings
    is exactly the kind of work an abandoned-lock scenario shouldn't
    silently decide about on the user's behalf. A brand-new tab on either
    side (non-colliding id) just gets added; a tab deleted on one side and
    left untouched on the other since `base` is still a clean, silent
    delete — only a real divergence on the same id ever prompts.

    Expects entries already decoded to a comparison-friendly structural
    shape by the caller (ui/project_widget.py's _decode_viewer_tab) —
    each dict carries 'id' + 'bundle_b64' (kept verbatim, reused wholesale
    by whichever side wins — never itself compared) plus the decoded
    'tab_name'/'annotations'/'drawings'/'texture_data'/model fields. This
    module stays I/O-free, same reasoning as _merge_technical_overview."""
    base = base or []
    local = local or []
    remote = remote or []
    base_by_id = _index_by_id(base, 'id')
    local_by_id = _index_by_id(local, 'id')
    remote_by_id = _index_by_id(remote, 'id')

    local_new = set(local_by_id) - set(base_by_id)
    remote_new = set(remote_by_id) - set(base_by_id)
    colliding = detect_id_collision(local_new, remote_new)
    if colliding:
        all_ids = set(base_by_id) | set(local_by_id) | set(remote_by_id)
        remote = _renumber_collisions(remote, colliding, all_ids, 'id')
        remote_by_id = _index_by_id(remote, 'id')

    def _make_conflict(path, path_labels, local_value, remote_value, target_list, item):
        conflict = Conflict('viewer_tabs', path, 'content', local_value=local_value,
                             remote_value=remote_value, path_labels=path_labels)

        def _resolve(v, _item=item, _out=target_list):
            if v is None:
                for i, x in enumerate(_out):
                    if x is _item:
                        _out.pop(i)
                        break
            else:
                _item.clear()
                _item.update(v)
        conflict.resolve = _resolve
        return conflict

    conflicts: List[Conflict] = []
    merged: List[dict] = []
    seen = set()

    def _order():
        for item in local:
            iid = item.get('id')
            if iid is not None and iid not in seen:
                seen.add(iid)
                yield iid
        for item in remote:
            iid = item.get('id')
            if iid is not None and iid not in seen:
                seen.add(iid)
                yield iid

    for tab_id in _order():
        in_base, in_local, in_remote = tab_id in base_by_id, tab_id in local_by_id, tab_id in remote_by_id
        item_path = ('viewer_tabs', tab_id)

        if in_base and not in_local and not in_remote:
            continue  # deleted on both sides

        if not in_base and in_local and not in_remote:
            merged.append(local_by_id[tab_id])
            continue

        if not in_base and not in_local and in_remote:
            merged.append(remote_by_id[tab_id])
            continue

        b_item = base_by_id.get(tab_id)
        b_content = _normalize_viewer_tab_for_compare(b_item)

        if in_base and not in_local and in_remote:
            r_item = remote_by_id[tab_id]
            if _normalize_viewer_tab_for_compare(r_item) == b_content:
                continue  # remote never touched it since base -> clean delete
            label = r_item.get('tab_name') or f'#{tab_id}'
            item = dict(r_item)
            conflicts.append(_make_conflict(item_path, (label,), None, r_item, merged, item))
            merged.append(item)
            continue

        if in_base and in_local and not in_remote:
            l_item = local_by_id[tab_id]
            if _normalize_viewer_tab_for_compare(l_item) == b_content:
                continue  # local never touched it since base -> clean delete
            label = l_item.get('tab_name') or f'#{tab_id}'
            item = dict(l_item)
            conflicts.append(_make_conflict(item_path, (label,), l_item, None, merged, item))
            merged.append(item)
            continue

        # present on both local and remote (possibly base too)
        l_item, r_item = local_by_id[tab_id], remote_by_id[tab_id]
        l_content = _normalize_viewer_tab_for_compare(l_item)
        r_content = _normalize_viewer_tab_for_compare(r_item)
        if l_content == r_content:
            merged.append(l_item)
            continue
        if l_content == b_content:
            merged.append(r_item)  # only remote changed it
            continue
        if r_content == b_content:
            merged.append(l_item)  # only local changed it
            continue
        label = l_item.get('tab_name') or r_item.get('tab_name') or f'#{tab_id}'
        item = dict(l_item)
        conflicts.append(_make_conflict(item_path, (label,), l_item, r_item, merged, item))
        merged.append(item)

    return merged, conflicts


def _merge_quality_control(base, local, remote):
    base, local, remote = base or {}, local or {}, remote or {}
    # `images` used to be two parallel id-less lists (inspection_images +
    # image_annotations) merged as one opaque whole-list value — so a
    # genuine simultaneous edit (one side takes a new photo, the other
    # deletes a different one) produced a single conflict on the *entire*
    # list, and picking either side threw away the other side's change
    # completely: a newly-taken photo could vanish, or a deleted photo
    # could come back. Each photo now carries a stable `id` (assigned once,
    # never reassigned — unlike a control point's own `id`, which is a
    # pure display position), so it merges per-item like every other
    # id-keyed section instead of as one opaque blob.
    def _merge_image_item(b, l, r, path, path_labels=()):
        skip = ('control_points',)
        merged, conflicts = merge_dict_fields(b, l, r, section='quality_control', path=path,
                                               path_labels=path_labels, skip_keys=skip)
        points, point_conflicts = merge_list_by_id(
            b.get('control_points', []), l.get('control_points', []), r.get('control_points', []),
            id_key='id', section='quality_control', path=path + ('control_points',), path_labels=path_labels,
        )
        merged['control_points'] = points
        conflicts += point_conflicts
        return merged, conflicts

    images, image_conflicts = merge_nested_by_path(
        base.get('images', []), local.get('images', []), remote.get('images', []),
        id_key='id', section='quality_control', path=('images',), item_merger=_merge_image_item,
    )

    # general_control_points has no id field of its own scope beyond the
    # same locally-scoped display-position ids as per-image ones — merge
    # the same way.
    general_points, general_conflicts = merge_list_by_id(
        base.get('general_control_points', []), local.get('general_control_points', []),
        remote.get('general_control_points', []),
        id_key='id', section='quality_control', path=('general_control_points',),
    )

    skip = ('images', 'general_control_points')
    merged, conflicts = merge_dict_fields(base, local, remote, section='quality_control', path=(), skip_keys=skip)
    merged['images'] = images
    merged['general_control_points'] = general_points
    conflicts += image_conflicts + general_conflicts
    return merged, conflicts


def _merge_brief(base, local, remote):
    # Brief.get_data() is already one flat dict (every sub-card's fields
    # merged together with dict.update()) with no id-keyed nested lists —
    # techniques/watchpoints/photo_b64s/components are all id-less lists
    # that correctly fall through to the same opaque whole-value handling
    # used for report's company_extras/attendees. Plain field merge covers
    # the whole section, no skip_keys needed.
    return merge_dict_fields(base, local, remote, section='brief', path=())


def _merge_drawing_scale(base, local, remote):
    base, local, remote = base or {}, local or {}, remote or {}
    # The file itself (file_name/file_ext/file_b64) is a real document, not
    # metadata — opaque is the honest treatment, same as technical_overview.
    # `state` (calibration/borders/shapes — see ui/scale_canvas.py's
    # ScaleCanvas.get_state()) is field-merged separately so a conflict
    # there isolates to "the calibration" instead of the whole workspace.
    merged, conflicts = merge_dict_fields(base, local, remote, section='drawing_scale', path=(),
                                           skip_keys=('state',))
    state, state_conflicts = merge_dict_fields(
        base.get('state', {}), local.get('state', {}), remote.get('state', {}),
        section='drawing_scale', path=('state',),
    )
    merged['state'] = state
    conflicts += state_conflicts
    return merged, conflicts


def _normalize_annotations_for_compare(annotations: List[dict]) -> List[dict]:
    """Comparison-only view of a technical_overview annotations list: each
    annotation's image_paths reduced to their bare filename. The real
    values are absolute paths under a fresh temp-extraction directory
    every time the bundle is decoded (see ui/project_widget.py's
    _decode_technical_overview), so comparing them directly would make an
    unchanged attached image look "different" on every single merge —
    the same class of non-determinism as the outer zip blob, one level
    deeper. os.path.basename is pure string manipulation, not I/O."""
    normalized = []
    for ann in annotations or []:
        a = dict(ann)
        a['image_paths'] = [os.path.basename(p) for p in a.get('image_paths', [])]
        normalized.append(a)
    return normalized


def _merge_technical_overview(base, local, remote):
    """technical_overview is decoded to this structural shape by
    ui/project_widget.py before merge_project() runs (and re-encoded back
    to {'bundle_b64': ...} afterward) — this function never touches the
    zip/base64 form itself, keeping this module I/O-free:
        {'metadata': {...}, 'document_bytes': bytes|None,
         'document_ext': '.pdf', 'annotations': [...]}

    Two different policies, per explicit product decision: the sidebar
    metadata (title/property/dates/comments) mostly just mirrors
    project_info and is low-stakes — merged field by field but never
    interactively conflicted. The document + annotations are the actual
    content; a genuine simultaneous edit there IS worth a (rare) prompt."""
    base, local, remote = base or {}, local or {}, remote or {}
    metadata = merge_dict_fields_prefer_local(
        base.get('metadata', {}), local.get('metadata', {}), remote.get('metadata', {}),
    )
    merged: Dict[str, Any] = {'metadata': metadata}
    conflicts: List[Conflict] = []

    def _content(d: dict):
        return d.get('document_bytes'), _normalize_annotations_for_compare(d.get('annotations', []))

    local_c, remote_c, base_c = _content(local), _content(remote), _content(base)
    if local_c == remote_c:
        winner = local
    elif local_c == base_c:
        winner = remote           # only remote changed the document/annotations
    elif remote_c == base_c:
        winner = local            # only local changed the document/annotations
    else:
        winner = local            # placeholder — resolve() overwrites once the user picks

        def _resolve(value, _m=merged):
            _m['document_bytes'] = value.get('document_bytes')
            _m['document_ext'] = value.get('document_ext', '')
            _m['annotations'] = value.get('annotations', [])

        conflicts.append(Conflict(
            'technical_overview', (), 'document',
            local_value=local, remote_value=remote, resolve=_resolve,
        ))

    merged['document_bytes'] = winner.get('document_bytes')
    merged['document_ext'] = winner.get('document_ext', '')
    merged['annotations'] = winner.get('annotations', [])
    return merged, conflicts


def _merge_assignment(base, local, remote):
    base, local, remote = base or {}, local or {}, remote or {}
    tabs, conflicts = merge_nested_by_path(
        base.get('tabs', []), local.get('tabs', []), remote.get('tabs', []),
        id_key='id', child_keys=('cards',),
        section='assignment', path=('tabs',),
    )

    # current_tab is a raw list INDEX, not an id — resolve post-merge by
    # looking up whichever tab id it pointed to before merging, same
    # reasoning as traceability's current_component (local's index and
    # remote's index refer to different tabs once the lists diverge, e.g.
    # a tab got deleted or a new one inserted ahead of it on either side).
    local_tabs = local.get('tabs', [])
    idx = local.get('current_tab', 0)
    target_id = local_tabs[idx].get('id') if 0 <= idx < len(local_tabs) else None
    current_tab = 0
    if target_id is not None:
        for i, tb in enumerate(tabs):
            if tb.get('id') == target_id:
                current_tab = i
                break

    return {'tabs': tabs, 'current_tab': current_tab}, conflicts


def _merge_rd(base, local, remote):
    """R&D components. Each component has THREE sibling nested lists
    (brief.notes, proposals, technique_proposals) rather than one linear
    child_keys chain, so it needs a custom item_merger — same shape as
    _merge_report_item. proposals/technique_proposals each carry their own
    image_path (ui/rd_widget.py's MaterialProposal/TechniqueProposal) —
    id-based merging keeps an unrelated proposal's image intact when only
    a different proposal/component was actually edited."""
    base, local, remote = base or {}, local or {}, remote or {}

    def _merge_component(b, l, r, path, path_labels=()):
        skip = ('brief', 'proposals', 'technique_proposals')
        merged, conflicts = merge_dict_fields(b, l, r, section='rd', path=path,
                                               path_labels=path_labels, skip_keys=skip)

        b_brief, l_brief, r_brief = b.get('brief') or {}, l.get('brief') or {}, r.get('brief') or {}
        brief, brief_conflicts = merge_dict_fields(
            b_brief, l_brief, r_brief, section='rd', path=path + ('brief',),
            path_labels=path_labels, skip_keys=('notes',),
        )
        notes, notes_conflicts = merge_list_by_id(
            b_brief.get('notes', []), l_brief.get('notes', []), r_brief.get('notes', []),
            id_key='id', section='rd', path=path + ('brief', 'notes'), path_labels=path_labels,
        )
        brief['notes'] = notes
        merged['brief'] = brief
        conflicts += brief_conflicts + notes_conflicts

        for key in ('proposals', 'technique_proposals'):
            items, item_conflicts = merge_list_by_id(
                b.get(key, []), l.get(key, []), r.get(key, []),
                id_key='id', section='rd', path=path + (key,), path_labels=path_labels,
            )
            merged[key] = items
            conflicts += item_conflicts

        return merged, conflicts

    components, conflicts = merge_nested_by_path(
        base.get('components', []), local.get('components', []), remote.get('components', []),
        id_key='id', section='rd', path=('components',), item_merger=_merge_component,
    )
    return {'components': components}, conflicts


def _merge_estimated_cost(base, local, remote):
    """trades -> partners are id-keyed (ui/estimated_cost.py's CostTrade/
    CostPartner), but a partner's own `tasks` have no id at all (CostTask),
    so the nesting stops at partners — `tasks` is then just a normal list
    field of the partner dict, handled by merge_dict_fields' existing
    opaque-whole-list-if-differs fallback (same treatment as report's
    photo_blocks), which is the correct/safe behavior for an unkeyed list."""
    base, local, remote = base or {}, local or {}, remote or {}
    merged, conflicts = merge_dict_fields(base, local, remote, section='estimated_cost', path=(),
                                           skip_keys=('trades',))
    trades, trade_conflicts = merge_nested_by_path(
        base.get('trades', []), local.get('trades', []), remote.get('trades', []),
        id_key='id', child_keys=('partners',), section='estimated_cost', path=('trades',),
    )
    merged['trades'] = trades
    conflicts += trade_conflicts
    return merged, conflicts


def _merge_files(base, local, remote):
    """folders/files (ui/files_widget.py) are id-keyed; a file's own
    `versions` have no id (only a display version_str), so they're left as
    one opaque list field per file — same reasoning as estimated_cost's
    tasks. `file_data_b64` (the actual uploaded content) lives inside those
    versions, so this still isolates a conflict to "this one file's
    versions", not the entire files+folders tree, unlike the previous
    whole-section fallback. next_folder_id/next_file_id are bumped past
    whatever ids actually survived the merge (from either side) so a
    future add on either machine can't mint a colliding id."""
    base, local, remote = base or {}, local or {}, remote or {}
    folders, folder_conflicts = merge_list_by_id(
        base.get('folders', []), local.get('folders', []), remote.get('folders', []),
        id_key='id', section='files', path=('folders',),
    )
    files, file_conflicts = merge_list_by_id(
        base.get('files', []), local.get('files', []), remote.get('files', []),
        id_key='id', section='files', path=('files',),
    )
    next_folder_id = max(
        [f.get('id', 0) + 1 for f in folders] + [local.get('next_folder_id', 1), remote.get('next_folder_id', 1)]
    )
    next_file_id = max(
        [f.get('id', 0) + 1 for f in files] + [local.get('next_file_id', 1), remote.get('next_file_id', 1)]
    )
    return {
        'folders': folders, 'files': files,
        'next_folder_id': next_folder_id, 'next_file_id': next_file_id,
    }, folder_conflicts + file_conflicts


def _merge_validation(base, local, remote):
    """Validation sessions (ui/validation/models.py's ValidationSession)
    each have a mix of an id-keyed nested list (stakeholders) and two that
    aren't (modifications, action_plan — ModificationRow/ActionRow have no
    id field), plus a fixed-length positional schedule_dates list — a
    custom item_merger, same shape as _merge_report_item/_merge_component:
    stakeholders merged by id, the rest fall through as opaque list
    fields (safe fallback for the id-less ones, and schedule_dates is
    positional by nature anyway)."""
    base, local, remote = base or {}, local or {}, remote or {}

    def _merge_session(b, l, r, path, path_labels=()):
        skip = ('stakeholders',)
        merged, conflicts = merge_dict_fields(b, l, r, section='validation', path=path,
                                               path_labels=path_labels, skip_keys=skip)
        stakeholders, sh_conflicts = merge_list_by_id(
            b.get('stakeholders', []), l.get('stakeholders', []), r.get('stakeholders', []),
            id_key='id', section='validation', path=path + ('stakeholders',), path_labels=path_labels,
        )
        merged['stakeholders'] = stakeholders
        conflicts += sh_conflicts
        return merged, conflicts

    sessions, conflicts = merge_nested_by_path(
        base.get('sessions', []), local.get('sessions', []), remote.get('sessions', []),
        id_key='id', section='validation', path=('sessions',), item_merger=_merge_session,
    )
    return {'sessions': sessions}, conflicts


def _merge_prototype(base, local, remote):
    """Prototype versions (ui/prototype_widget.py's PrototypeVersion) are
    id-keyed (a uuid — no collision-counter concern); each version's own
    image_paths/file_paths are plain list fields with no per-item id, so
    they fall through to merge_dict_fields' opaque-whole-list treatment —
    id-based versioning is what actually matters here, since that's what
    previously let editing one version's comments wipe out a DIFFERENT
    version's photos entirely. next_number is a display counter (not an
    id) — bumped past the highest version_number that survived the merge
    so the next new version doesn't duplicate a number."""
    base, local, remote = base or {}, local or {}, remote or {}
    versions, conflicts = merge_list_by_id(
        base.get('versions', []), local.get('versions', []), remote.get('versions', []),
        id_key='id', section='prototype', path=('versions',),
    )
    next_number = max(
        [v.get('version_number', 0) + 1 for v in versions]
        + [local.get('next_number', 1), remote.get('next_number', 1)]
    )
    return {'versions': versions, 'next_number': next_number}, conflicts


def _merge_version_comparison(base, local, remote):
    """Cards (ui/version_comparison.py's VersionCard) are id-keyed by a
    persisted sequential next_id counter (unlike prototype's uuids) —
    each card's own photo_paths (up to 3 per card) fall through to
    merge_dict_fields' opaque-list treatment. next_id is bumped past every
    surviving card id so a future add on either machine can't mint an id
    that collides with one the other machine already saved."""
    base, local, remote = base or {}, local or {}, remote or {}
    cards, conflicts = merge_list_by_id(
        base.get('cards', []), local.get('cards', []), remote.get('cards', []),
        id_key='id', section='version_comparison', path=('cards',),
    )
    next_id = max(
        [c.get('id', 0) + 1 for c in cards] + [local.get('next_id', 1), remote.get('next_id', 1)]
    )
    return {'cards': cards, 'next_id': next_id}, conflicts


def _merge_glossary(base, local, remote):
    """Terms (ui/glossary_widget.py's GlossaryTerm) are id-keyed by a
    persisted sequential next_id counter, same reasoning as
    version_comparison's cards — no images here, but still a plain id-keyed
    list vulnerable to "concurrent edits to different terms wipe each
    other" under the old whole-section fallback."""
    base, local, remote = base or {}, local or {}, remote or {}
    terms, conflicts = merge_list_by_id(
        base.get('terms', []), local.get('terms', []), remote.get('terms', []),
        id_key='id', section='glossary', path=('terms',),
    )
    next_id = max(
        [t.get('id', 0) + 1 for t in terms] + [local.get('next_id', 1), remote.get('next_id', 1)]
    )
    return {'terms': terms, 'next_id': next_id}, conflicts


_SECTION_MERGERS = {
    'todo': _merge_todo,
    'timeline': _merge_timeline,
    'project_info': _merge_project_info,
    'traceability': _merge_traceability,
    'report': _merge_report,
    'viewer_tabs': _merge_viewer_tabs,
    'quality_control': _merge_quality_control,
    'brief': _merge_brief,
    'drawing_scale': _merge_drawing_scale,
    'technical_overview': _merge_technical_overview,
    'assignment': _merge_assignment,
    'rd': _merge_rd,
    'estimated_cost': _merge_estimated_cost,
    'files': _merge_files,
    'validation': _merge_validation,
    'prototype': _merge_prototype,
    'version_comparison': _merge_version_comparison,
    'glossary': _merge_glossary,
}

# Every top-level save section (all of _NAV_KEYS in ui/project_widget.py,
# plus project_info/viewer_tabs/technical_overview/drawing_scale) has a real
# entry above as of the "assignment" image-loss bug audit — none are left on
# the whole-section fallback below. merge_section still falls back to it for
# any genuinely new section added later, so wiring one up is a
# _SECTION_MERGERS entry, not new engine code. technical_overview used to
# live here too (as an opaque zip blob), but the blob got regenerated with
# non-deterministic bytes (a fresh created_at + zip-entry mtimes) on every
# single save, so it looked "conflicting" almost every time regardless of
# whether anyone actually touched it — ui/project_widget.py now decodes it
# to real parts before merging (see _merge_technical_overview above) so
# equality is judged on content, not incidental re-encoding noise.


def merge_section(section_name: str, base, local, remote,
                   target: Optional[dict] = None, target_key: Optional[str] = None) -> Tuple[Any, List[Conflict]]:
    """Merge one top-level save key using whichever strategy fits its shape."""
    merger = _SECTION_MERGERS.get(section_name)
    if merger is not None:
        return merger(base, local, remote)
    return merge_whole_section(base, local, remote, section_name, target=target, target_key=target_key)


def merge_project(base: dict, local: dict, remote: dict) -> Tuple[dict, List[Conflict]]:
    """Top-level entry point. Merges every data section present in local
    and/or remote; envelope metadata (created_by, last_saved_by/at,
    password_hash, file_type, version) is left untouched here — the caller
    stamps those directly after merging."""
    base = base or {}
    metadata_keys = {'file_type', 'version', 'created_by', 'created_at',
                      'last_saved_by', 'last_saved_at', 'password_hash'}
    section_keys = (set(local) | set(remote)) - metadata_keys

    merged: Dict[str, Any] = dict(local)  # start from local so untouched keys survive
    all_conflicts: List[Conflict] = []
    for key in section_keys:
        value, conflicts = merge_section(key, base.get(key), local.get(key), remote.get(key),
                                          target=merged, target_key=key)
        merged[key] = value
        all_conflicts.extend(conflicts)

    return merged, all_conflicts


def fold_linked_conflicts(conflicts: List[Conflict]) -> List[Conflict]:
    """Collapse conflicts on fields that are just auto-filled mirrors of an
    already-conflicting source field (see core.linked_fields.LINKED_FIELDS)
    into the source conflict's `also_affects` list, so the caller shows one
    prompt instead of several for what's really a single edit.

    A destination conflict only folds in when its local_value/remote_value
    EXACTLY match the source conflict's — i.e. it's still a straight
    mirror, nobody customized it independently. A destination that doesn't
    match is left as its own separate conflict; this function never
    silently overwrites or hides a genuinely independent edit.

    Safe to call on any conflict list, including ones with no linked
    fields present — it's a no-op fold in that case."""
    from core.linked_fields import LINKED_FIELDS

    # First pass: decide which conflicts fold into which source, without
    # touching the output list yet — `conflicts` comes from merge_project's
    # set-keyed iteration over section names, so its order isn't
    # guaranteed; building the result incrementally in a single pass would
    # make the outcome depend on whether a destination happens to be
    # visited before or after its source.
    folded_into: Dict[int, Conflict] = {}  # id(destination conflict) -> its source conflict
    for source in conflicts:
        destinations = LINKED_FIELDS.get((source.section, source.field))
        if not destinations:
            continue
        for other in conflicts:
            if other is source or id(other) in folded_into:
                continue
            if (other.section, other.field) in destinations \
                    and other.local_value == source.local_value \
                    and other.remote_value == source.remote_value:
                folded_into[id(other)] = source

    result = []
    for c in conflicts:
        source = folded_into.get(id(c))
        if source is not None:
            source.also_affects.append(c)
        else:
            result.append(c)
    return result


def field_conflicts_only(conflicts: List[Conflict]) -> List[Conflict]:
    """Filter out delete-vs-edit conflicts (field == '__deleted__') — those
    are already safely auto-resolved by the merge itself and shouldn't be
    shown in an interactive per-field picker. What's left is exactly "the
    same field was changed differently on both sides", per the brief."""
    return [c for c in conflicts if c.field != '__deleted__']

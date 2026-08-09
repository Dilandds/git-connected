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


# ── generic three-way scalar merge ──────────────────────────────────────────

def _merge_scalar(base_v, local_v, remote_v, section: str, path: tuple, field_name: str,
                   *, target: Optional[dict] = None, target_key: Optional[str] = None):
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
    conflict = Conflict(section, path, field_name, local_value=local_v, remote_value=remote_v)
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
                       section: str = '', path: tuple = (),
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
            section, path, key, target=merged, target_key=key,
        )
        if value is not _SENTINEL:
            merged[key] = value
        conflicts.extend(key_conflicts)
    return merged, conflicts


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


def merge_nested_by_path(base: List[dict], local: List[dict], remote: List[dict],
                          id_key: str = 'id', child_keys: Sequence[str] = (),
                          section: str = '', path: tuple = ()) -> Tuple[List[dict], List[Conflict]]:
    """Three-way merge of a list of id-keyed dicts. If child_keys is given,
    child_keys[0] names a nested id-keyed list inside each item that gets
    recursively merged the same way (using child_keys[1:] at that level) —
    e.g. child_keys=('operations', 'tasks') merges timeline's
    operators -> operations -> tasks, three levels deep, each level's id
    comparisons scoped to their own parent (ids here are locally-scoped
    sequential counters, not globally unique, so a bare-id comparison
    across different parents would be wrong).

    merge_list_by_id() is just this function with child_keys=().
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
        skip = (child_key,) if child_key else ()
        merged_item, field_conflicts = merge_dict_fields(b, l, r, section=section, path=item_path, skip_keys=skip)
        conflicts.extend(field_conflicts)

        if child_key:
            nested_merged, nested_conflicts = merge_nested_by_path(
                b.get(child_key, []), l.get(child_key, []), r.get(child_key, []),
                id_key=id_key, child_keys=grandchild_keys,
                section=section, path=item_path + (child_key,),
            )
            merged_item[child_key] = nested_merged
            conflicts.extend(nested_conflicts)

        merged.append(merged_item)

    return merged, conflicts


def merge_list_by_id(base: List[dict], local: List[dict], remote: List[dict],
                      id_key: str = 'id', section: str = '', path: tuple = ()) -> Tuple[List[dict], List[Conflict]]:
    """Three-way merge of a flat list of id-keyed dicts (no nesting)."""
    return merge_nested_by_path(base, local, remote, id_key=id_key, child_keys=(), section=section, path=path)


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

    def _merge_report_item(b, l, r, path):
        # pages need id-based merging; company_extras/partner_extras/attendees
        # have no id field at all, so they're merged as opaque values below
        # (same reasoning as photo_blocks inside pages — handled for free by
        # merge_dict_fields treating an un-skipped list value as one opaque
        # field, replaced wholesale if only one side changed it).
        skip = ('pages', 'company_extras', 'partner_extras', 'attendees')
        merged, conflicts = merge_dict_fields(b, l, r, section='report', path=path, skip_keys=skip)

        pages, page_conflicts = merge_list_by_id(
            b.get('pages', []), l.get('pages', []), r.get('pages', []),
            id_key='id', section='report', path=path + ('pages',),
        )
        merged['pages'] = pages
        conflicts += page_conflicts

        for key in ('company_extras', 'partner_extras', 'attendees'):
            value, key_conflicts = _merge_scalar(
                b.get(key), l.get(key), r.get(key), 'report', path, key,
                target=merged, target_key=key,
            )
            merged[key] = value
            conflicts += key_conflicts

        return merged, conflicts

    base_by_id = _index_by_id(base.get('reports', []), 'id')
    local_by_id = _index_by_id(local.get('reports', []), 'id')
    remote_by_id = _index_by_id(remote.get('reports', []), 'id')

    # Resolve id collisions on brand-new reports the same way
    # merge_nested_by_path would, before deciding which reports survive.
    local_new = set(local_by_id) - set(base_by_id)
    remote_new = set(remote_by_id) - set(base_by_id)
    colliding = detect_id_collision(local_new, remote_new)
    if colliding:
        all_ids = set(base_by_id) | set(local_by_id) | set(remote_by_id)
        remote_reports = _renumber_collisions(remote.get('reports', []), colliding, all_ids, 'id')
        remote_by_id = _index_by_id(remote_reports, 'id')

    conflicts: List[Conflict] = []
    reports: List[dict] = []
    seen = set()

    def _order():
        for r_item in local.get('reports', []):
            rid = r_item.get('id')
            if rid is not None and rid not in seen:
                seen.add(rid)
                yield rid
        for r_item in remote_by_id.values():
            rid = r_item.get('id')
            if rid is not None and rid not in seen:
                seen.add(rid)
                yield rid

    for rid in _order():
        in_base, in_local, in_remote = rid in base_by_id, rid in local_by_id, rid in remote_by_id
        r_path = ('reports', rid)

        if in_base and not in_local and not in_remote:
            continue
        if in_base and not in_local and in_remote:
            if remote_by_id[rid] != base_by_id[rid]:
                conflicts.append(Conflict('report', r_path, '__deleted__', None, remote_by_id[rid]))
                reports.append(remote_by_id[rid])
            continue
        if in_base and in_local and not in_remote:
            if local_by_id[rid] != base_by_id[rid]:
                conflicts.append(Conflict('report', r_path, '__deleted__', local_by_id[rid], None))
                reports.append(local_by_id[rid])
            continue
        if not in_base and in_local and not in_remote:
            reports.append(local_by_id[rid])
            continue
        if not in_base and not in_local and in_remote:
            reports.append(remote_by_id[rid])
            continue

        b, l, r = base_by_id.get(rid, {}), local_by_id[rid], remote_by_id[rid]
        merged_report, item_conflicts = _merge_report_item(b, l, r, r_path)
        conflicts += item_conflicts
        reports.append(merged_report)

    result = {'logo_path': local.get('logo_path'), 'reports': reports}
    result['logo_path'], logo_conflicts = _merge_scalar(
        base.get('logo_path'), local.get('logo_path'), remote.get('logo_path'),
        'report', (), 'logo_path', target=result, target_key='logo_path',
    )
    conflicts += logo_conflicts

    return result, conflicts


def _merge_viewer_tabs(base, local, remote):
    return merge_list_add_only(local, remote), []


_SECTION_MERGERS = {
    'todo': _merge_todo,
    'timeline': _merge_timeline,
    'project_info': _merge_project_info,
    'traceability': _merge_traceability,
    'report': _merge_report,
    'viewer_tabs': _merge_viewer_tabs,
}

# Sections that are single opaque blobs (not lists) — whole-section
# replace-if-differs. technical_overview/drawing_scale by explicit design
# decision; everything else not yet audited defaults here too, so adding
# real support for one later is a _SECTION_MERGERS entry, not new engine code.


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


def field_conflicts_only(conflicts: List[Conflict]) -> List[Conflict]:
    """Filter out delete-vs-edit conflicts (field == '__deleted__') — those
    are already safely auto-resolved by the merge itself and shouldn't be
    shown in an interactive per-field picker. What's left is exactly "the
    same field was changed differently on both sides", per the brief."""
    return [c for c in conflicts if c.field != '__deleted__']

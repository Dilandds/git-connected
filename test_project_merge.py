#!/usr/bin/env python3
"""
Standalone tests for core/project_merge.py's pure merge functions.
No Qt, no file I/O, no pytest dependency (none is installed in this repo) —
just plain asserts, matching the style of the other test_*.py scripts here.

Usage:
    python test_project_merge.py
"""
from core.project_merge import (
    Conflict, merge_dict_fields, merge_list_by_id, merge_nested_by_path,
    merge_list_add_only, detect_id_collision, merge_section, merge_project,
    field_conflicts_only,
)

_passed = 0
_failed = 0


def check(name, condition):
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  PASS: {name}")
    else:
        _failed += 1
        print(f"  FAIL: {name}")


def test_no_conflict_both_sides_add():
    print("test_no_conflict_both_sides_add")
    base = {'tasks': [{'id': 'a', 'title': 'Existing'}]}
    local = {'tasks': [{'id': 'a', 'title': 'Existing'}, {'id': 'b', 'title': 'Local new'}]}
    remote = {'tasks': [{'id': 'a', 'title': 'Existing'}, {'id': 'c', 'title': 'Remote new'}]}
    merged, conflicts = merge_section('todo', base, local, remote)
    ids = {t['id'] for t in merged['tasks']}
    check("no conflicts", conflicts == [])
    check("both additions present", ids == {'a', 'b', 'c'})


def test_same_field_conflict():
    print("test_same_field_conflict")
    base = {'tasks': [{'id': 'a', 'title': 'Original', 'status': 'todo'}]}
    local = {'tasks': [{'id': 'a', 'title': 'Local title', 'status': 'todo'}]}
    remote = {'tasks': [{'id': 'a', 'title': 'Remote title', 'status': 'todo'}]}
    merged, conflicts = merge_section('todo', base, local, remote)
    check("exactly one conflict", len(conflicts) == 1)
    check("conflict is on 'title'", conflicts[0].field == 'title')
    check("conflict has both values", conflicts[0].local_value == 'Local title' and conflicts[0].remote_value == 'Remote title')
    check("status unaffected (only one field conflicts)", merged['tasks'][0]['status'] == 'todo')


def test_delete_vs_edit_conflict():
    print("test_delete_vs_edit_conflict")
    base = {'tasks': [{'id': 'a', 'title': 'Original'}]}
    local = {'tasks': []}  # local deleted it
    remote = {'tasks': [{'id': 'a', 'title': 'Remote edited it'}]}  # remote edited it
    merged, conflicts = merge_section('todo', base, local, remote)
    check("deletion-vs-edit produces a conflict", len(conflicts) == 1)
    check("conflict field is __deleted__", conflicts[0].field == '__deleted__')
    check("item survives (undelete)", any(t['id'] == 'a' for t in merged['tasks']))

    # clean delete (remote didn't touch it) should NOT conflict
    base2 = {'tasks': [{'id': 'a', 'title': 'Original'}]}
    local2 = {'tasks': []}
    remote2 = {'tasks': [{'id': 'a', 'title': 'Original'}]}
    merged2, conflicts2 = merge_section('todo', base2, local2, remote2)
    check("clean delete has no conflict", conflicts2 == [])
    check("clean delete actually removes item", merged2['tasks'] == [])


def test_id_collision_on_new_items():
    print("test_id_collision_on_new_items")
    # timeline: one operator, base has no operations; local and remote each
    # independently add a NEW operation with the same locally-scoped id=1,
    # but genuinely different content.
    base = {'operators': [{'id': 1, 'name': 'Op A', 'operations': []}]}
    local = {'operators': [{'id': 1, 'name': 'Op A', 'operations': [
        {'id': 1, 'name': 'Local operation', 'tasks': []},
    ]}]}
    remote = {'operators': [{'id': 1, 'name': 'Op A', 'operations': [
        {'id': 1, 'name': 'Remote operation', 'tasks': []},
    ]}]}
    merged, conflicts = merge_section('timeline', base, local, remote)
    ops = merged['operators'][0]['operations']
    check("both new operations survive distinctly", len(ops) == 2)
    names = {op['name'] for op in ops}
    check("no data loss from collision", names == {'Local operation', 'Remote operation'})
    ids = [op['id'] for op in ops]
    check("collision was resolved to distinct ids", len(set(ids)) == 2)


def test_nested_path_scoping_not_bare_id():
    print("test_nested_path_scoping_not_bare_id")
    # Two different operators each already have an operation with id=1 from
    # base (legitimately, since ids are only unique per-parent) — editing
    # one must not affect the other.
    base = {'operators': [
        {'id': 1, 'name': 'Op A', 'operations': [{'id': 1, 'name': 'Task under A', 'tasks': []}]},
        {'id': 2, 'name': 'Op B', 'operations': [{'id': 1, 'name': 'Task under B', 'tasks': []}]},
    ]}
    local = {'operators': [
        {'id': 1, 'name': 'Op A', 'operations': [{'id': 1, 'name': 'Task under A EDITED', 'tasks': []}]},
        {'id': 2, 'name': 'Op B', 'operations': [{'id': 1, 'name': 'Task under B', 'tasks': []}]},
    ]}
    remote = base
    merged, conflicts = merge_section('timeline', base, local, remote)
    a_op = next(o for o in merged['operators'] if o['id'] == 1)
    b_op = next(o for o in merged['operators'] if o['id'] == 2)
    check("no conflicts", conflicts == [])
    check("operator A's operation edited", a_op['operations'][0]['name'] == 'Task under A EDITED')
    check("operator B's same-id operation untouched", b_op['operations'][0]['name'] == 'Task under B')


def test_traceability_current_component_index_repair():
    print("test_traceability_current_component_index_repair")
    base = {
        'version': 3, 'extra': {}, 'current_component': 0,
        'components': [
            {'id': 1, 'name': 'Comp 1', 'image_path': '', 'is_main': True, 'stages': []},
            {'id': 2, 'name': 'Comp 2', 'image_path': '', 'is_main': False, 'stages': []},
        ],
    }
    # local is looking at component id=2 (index 1)
    local = dict(base)
    local['current_component'] = 1
    # remote added a new component at the FRONT conceptually (doesn't matter,
    # what matters is component id=2 might land at a different index post-merge)
    remote = {
        'version': 3, 'extra': {}, 'current_component': 0,
        'components': [
            {'id': 1, 'name': 'Comp 1', 'image_path': '', 'is_main': True, 'stages': []},
            {'id': 2, 'name': 'Comp 2', 'image_path': '', 'is_main': False, 'stages': []},
            {'id': 3, 'name': 'Comp 3 (new)', 'image_path': '', 'is_main': False, 'stages': []},
        ],
    }
    merged, conflicts = merge_section('traceability', base, local, remote)
    resolved_id = merged['components'][merged['current_component']]['id']
    check("current_component still points at id=2 after merge", resolved_id == 2)


def test_project_info_field_merge():
    print("test_project_info_field_merge")
    base = {'company': 'Acme', 'title': 'Ring', 'status': 'in_progress'}
    local = {'company': 'Acme', 'title': 'Ring V2', 'status': 'in_progress'}
    remote = {'company': 'Acme Corp', 'title': 'Ring', 'status': 'in_progress'}
    merged, conflicts = merge_section('project_info', base, local, remote)
    check("no conflicts (different fields changed)", conflicts == [])
    check("local's title kept", merged['title'] == 'Ring V2')
    check("remote's company kept", merged['company'] == 'Acme Corp')


def test_viewer_tabs_add_only():
    print("test_viewer_tabs_add_only")
    local = [{'tab_name': 'a.stl', 'bundle_b64': 'AAA'}]
    remote = [{'tab_name': 'a.stl', 'bundle_b64': 'AAA'}, {'tab_name': 'b.stl', 'bundle_b64': 'BBB'}]
    merged = merge_list_add_only(local, remote)
    check("no duplicate of identical tab", len(merged) == 2)
    check("both tab names present", {t['tab_name'] for t in merged} == {'a.stl', 'b.stl'})


def test_whole_section_replace_if_differs():
    print("test_whole_section_replace_if_differs")
    base = {'file_name': 'doc.pdf', 'state': {'unit': 'cm'}}
    local = {'file_name': 'doc.pdf', 'state': {'unit': 'mm'}}
    remote = base  # remote never touched it
    merged, conflicts = merge_section('drawing_scale', base, local, remote)
    check("no conflict, local's change kept", conflicts == [] and merged['state']['unit'] == 'mm')

    remote2 = {'file_name': 'doc.pdf', 'state': {'unit': 'inches'}}
    merged2, conflicts2 = merge_section('drawing_scale', base, local, remote2)
    check("both changed differently -> one whole-section conflict", len(conflicts2) == 1)
    check("conflict section name", conflicts2[0].section == 'drawing_scale')


def test_report_id_less_sublists():
    print("test_report_id_less_sublists")
    base = {'logo_path': '', 'reports': [{
        'id': 1, 'date': '', 'locked': False, 'launch_deadline': '',
        'project_name': '', 'project_reference': '', 'project_manager': '',
        'technical_manager': '', 'quality_lead': '', 'company_extras': [],
        'partner_1': '', 'partner_2': '', 'partner_3': '', 'partner_extras': [],
        'attendees': [{'header': 'PM', 'name': 'Alice'}],
        'pages': [{'id': 1, 'followup': '', 'comments': '', 'photo_blocks': []}],
        'project_photo_path': '',
    }]}
    local = {'logo_path': '', 'reports': [dict(base['reports'][0])]}
    local['reports'][0] = dict(local['reports'][0])
    local['reports'][0]['attendees'] = [{'header': 'PM', 'name': 'Bob'}]  # local changed attendees
    remote = base  # remote untouched
    merged, conflicts = merge_section('report', base, local, remote)
    check("no conflict (only local changed attendees)", conflicts == [])
    check("local's attendees change kept", merged['reports'][0]['attendees'] == [{'header': 'PM', 'name': 'Bob'}])


def test_resolve_callback_writes_into_merged_result():
    print("test_resolve_callback_writes_into_merged_result")
    base = {'tasks': [{'id': 'a', 'title': 'Original'}]}
    local = {'tasks': [{'id': 'a', 'title': 'Local title'}]}
    remote = {'tasks': [{'id': 'a', 'title': 'Remote title'}]}
    merged, conflicts = merge_section('todo', base, local, remote)
    check("one conflict with a resolve callback", len(conflicts) == 1 and conflicts[0].resolve is not None)
    conflicts[0].resolve('User-picked value')
    check("resolve() writes straight into the already-merged result",
          merged['tasks'][0]['title'] == 'User-picked value')


def test_deleted_conflicts_excluded_from_interactive_list():
    print("test_deleted_conflicts_excluded_from_interactive_list")
    base = {'tasks': [{'id': 'a', 'title': 'Original'}]}
    local = {'tasks': []}
    remote = {'tasks': [{'id': 'a', 'title': 'Remote edited it'}]}
    merged, conflicts = merge_section('todo', base, local, remote)
    check("raw conflicts include the __deleted__ one", any(c.field == '__deleted__' for c in conflicts))
    check("field_conflicts_only filters it out", field_conflicts_only(conflicts) == [])


def test_report_page_photo_blocks_opaque_merge():
    print("test_report_page_photo_blocks_opaque_merge")
    base_page = {'id': 1, 'followup': '', 'comments': '', 'photo_blocks': [{'photos': [], 'comment': 'orig'}]}
    base = {'logo_path': '', 'reports': [{
        'id': 1, 'date': '', 'locked': False, 'launch_deadline': '',
        'project_name': '', 'project_reference': '', 'project_manager': '',
        'technical_manager': '', 'quality_lead': '', 'company_extras': [],
        'partner_1': '', 'partner_2': '', 'partner_3': '', 'partner_extras': [],
        'attendees': [], 'pages': [base_page], 'project_photo_path': '',
    }]}
    local = {'logo_path': '', 'reports': [dict(base['reports'][0])]}
    local_page = dict(base_page)
    local_page['photo_blocks'] = [{'photos': [], 'comment': 'local changed it'}]
    local['reports'][0] = dict(local['reports'][0])
    local['reports'][0]['pages'] = [local_page]
    remote = base  # remote untouched -> no conflict, local's photo_blocks change should win

    merged, conflicts = merge_section('report', base, local, remote)
    check("no conflict (only local touched photo_blocks)", conflicts == [])
    check("local's photo_blocks change kept",
          merged['reports'][0]['pages'][0]['photo_blocks'][0]['comment'] == 'local changed it')

    # now make BOTH sides change it differently -> must conflict
    remote_page = dict(base_page)
    remote_page['photo_blocks'] = [{'photos': [], 'comment': 'remote changed it'}]
    remote2 = {'logo_path': '', 'reports': [dict(base['reports'][0])]}
    remote2['reports'][0] = dict(remote2['reports'][0])
    remote2['reports'][0]['pages'] = [remote_page]
    merged2, conflicts2 = merge_section('report', base, local, remote2)
    check("both sides changed photo_blocks differently -> one conflict",
          len(conflicts2) == 1 and conflicts2[0].field == 'photo_blocks')


def test_merge_project_end_to_end():
    print("test_merge_project_end_to_end")
    base = {
        'file_type': 'lyns.pjt', 'version': '1.0',
        'created_by': 'Alice', 'created_at': 'T0',
        'last_saved_by': 'Alice', 'last_saved_at': 'T0',
        'todo': {'tasks': [{'id': 'x', 'title': 'Existing'}]},
        'project_info': {'company': 'Acme', 'title': 'Ring'},
    }
    local = dict(base)
    local['todo'] = {'tasks': [{'id': 'x', 'title': 'Existing'}, {'id': 'y', 'title': 'Local new'}]}
    local['last_saved_by'] = 'Alice'
    remote = dict(base)
    remote['project_info'] = {'company': 'Acme Corp', 'title': 'Ring'}
    remote['last_saved_by'] = 'Bob'

    merged, conflicts = merge_project(base, local, remote)
    check("no conflicts", conflicts == [])
    check("local's new task present", any(t['id'] == 'y' for t in merged['todo']['tasks']))
    check("remote's project_info change present", merged['project_info']['company'] == 'Acme Corp')
    check("metadata not merged by merge_project (caller's job)", 'last_saved_by' in merged)


def main():
    tests = [
        test_no_conflict_both_sides_add,
        test_same_field_conflict,
        test_delete_vs_edit_conflict,
        test_id_collision_on_new_items,
        test_nested_path_scoping_not_bare_id,
        test_traceability_current_component_index_repair,
        test_project_info_field_merge,
        test_viewer_tabs_add_only,
        test_whole_section_replace_if_differs,
        test_report_id_less_sublists,
        test_resolve_callback_writes_into_merged_result,
        test_deleted_conflicts_excluded_from_interactive_list,
        test_report_page_photo_blocks_opaque_merge,
        test_merge_project_end_to_end,
    ]
    for t in tests:
        t()
    print()
    print(f"{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == '__main__':
    import sys
    sys.exit(main())

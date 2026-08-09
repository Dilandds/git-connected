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
    field_conflicts_only, fold_linked_conflicts,
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


def test_quality_control_merge():
    print("test_quality_control_merge")
    base = {
        'inspection_date': '2026-01-01', 'inspected_by': '', 'comments': '',
        'inspection_images': [], 'image_annotations': [],
        'logo_data': '', 'designation': 'Original', 'reference_number': '',
        'manufacturer': '', 'inspection_due_date': '', 'overall_status': '',
        'waived_by': '', 'control_points': [{'id': 1, 'name': 'CP1', 'status': 'to_check',
                                              'comment': '', 'annotation_id': None, 'color': ''}],
    }
    local = dict(base)
    local['inspected_by'] = 'Alice'
    local['control_points'] = base['control_points'] + [
        {'id': 2, 'name': 'CP2 local', 'status': 'to_check', 'comment': '', 'annotation_id': None, 'color': ''}
    ]
    remote = dict(base)
    remote['reference_number'] = 'REF-99'

    merged, conflicts = merge_section('quality_control', base, local, remote)
    check("no conflicts (different fields changed)", conflicts == [])
    check("local's inspected_by kept", merged['inspected_by'] == 'Alice')
    check("remote's reference_number kept", merged['reference_number'] == 'REF-99')
    check("both control points present", {cp['id'] for cp in merged['control_points']} == {1, 2})

    # same field, different values -> real conflict
    remote2 = dict(base)
    remote2['designation'] = 'Remote designation'
    local2 = dict(base)
    local2['designation'] = 'Local designation'
    merged2, conflicts2 = merge_section('quality_control', base, local2, remote2)
    check("designation conflict detected", len(conflicts2) == 1 and conflicts2[0].field == 'designation')


def test_brief_merge():
    print("test_brief_merge")
    base = {'product_name': 'Ring', 'reference': 'R1', 'techniques': ['Casting'], 'notes': ''}
    local = dict(base)
    local['notes'] = 'Local note'
    remote = dict(base)
    remote['techniques'] = ['Casting', 'Polishing']

    merged, conflicts = merge_section('brief', base, local, remote)
    check("no conflicts (different fields changed)", conflicts == [])
    check("local's notes kept", merged['notes'] == 'Local note')
    check("remote's techniques list kept", merged['techniques'] == ['Casting', 'Polishing'])

    # same id-less list changed differently on both sides -> conflict, whole list
    local2 = dict(base)
    local2['techniques'] = ['Casting', 'Local addition']
    remote2 = dict(base)
    remote2['techniques'] = ['Casting', 'Remote addition']
    merged2, conflicts2 = merge_section('brief', base, local2, remote2)
    check("techniques conflict detected", len(conflicts2) == 1 and conflicts2[0].field == 'techniques')


def test_drawing_scale_merge():
    print("test_drawing_scale_merge")
    base = {
        'file_name': 'doc.pdf', 'file_ext': '.pdf', 'file_b64': 'AAA',
        'state': {'unit': 'cm', 'scale_ratio': 1.0, 'arrows': []},
    }
    local = dict(base)
    local['state'] = dict(base['state']); local['state']['unit'] = 'mm'
    remote = dict(base)
    remote['state'] = dict(base['state']); remote['state']['scale_ratio'] = 2.0

    merged, conflicts = merge_section('drawing_scale', base, local, remote)
    check("no conflicts (different state fields changed)", conflicts == [])
    check("local's unit kept", merged['state']['unit'] == 'mm')
    check("remote's scale_ratio kept", merged['state']['scale_ratio'] == 2.0)

    # both change 'unit' differently -> isolated conflict, not the whole workspace
    local2 = dict(base); local2['state'] = dict(base['state']); local2['state']['unit'] = 'mm'
    remote2 = dict(base); remote2['state'] = dict(base['state']); remote2['state']['unit'] = 'inches'
    merged2, conflicts2 = merge_section('drawing_scale', base, local2, remote2)
    check("unit conflict isolated to state.unit, not whole section",
          len(conflicts2) == 1 and conflicts2[0].field == 'unit' and conflicts2[0].section == 'drawing_scale')


def test_path_labels_resolve_item_names():
    print("test_path_labels_resolve_item_names")
    base = {'tasks': [{'id': 'a', 'title': 'Buy fabric', 'notes': ''}]}
    local = {'tasks': [{'id': 'a', 'title': 'Buy fabric', 'notes': 'Local note'}]}
    remote = {'tasks': [{'id': 'a', 'title': 'Buy fabric', 'notes': 'Remote note'}]}
    merged, conflicts = merge_section('todo', base, local, remote)
    check("one conflict", len(conflicts) == 1)
    check("path_labels resolves to the task's own title, not its id",
          conflicts[0].path_labels == ('Buy fabric',))

    # item with no name/title field at all falls back to a formatted id
    base2 = {'reports': [{'id': 7, 'followup': ''}]}  # report page shape has no name field
    # (use merge_list_by_id directly since this isn't a full report section)
    merged2, conflicts2 = merge_list_by_id(
        base2['reports'], [{'id': 7, 'followup': 'local'}], [{'id': 7, 'followup': 'remote'}],
        id_key='id', section='report', path=('pages',),
    )
    check("no-name item falls back to formatted id", conflicts2[0].path_labels == ('#7',))


def test_fold_linked_conflicts():
    print("test_fold_linked_conflicts")
    base = {
        'project_info': {'title': 'Original Title'},
        'report': {'reports': [{'id': 1, 'project_name': 'Original Title'}]},
        'quality_control': {'designation': 'Original Title'},
    }
    # Both sides change the title the same way everywhere EXCEPT quality_control,
    # which only diverged locally (still equals the source's local value, so it
    # should still fold — the fold criterion is "matches the source conflict's
    # local/remote", not "differs from base").
    local = {
        'project_info': {'title': 'Local Title'},
        'report': {'reports': [{'id': 1, 'project_name': 'Local Title'}]},
        'quality_control': {'designation': 'Local Title'},
    }
    remote = {
        'project_info': {'title': 'Remote Title'},
        'report': {'reports': [{'id': 1, 'project_name': 'Remote Title'}]},
        'quality_control': {'designation': 'Someone Customized This'},  # diverged independently
    }
    merged, conflicts = merge_project(base, local, remote)
    folded = fold_linked_conflicts(conflicts)
    interactive = field_conflicts_only(folded)

    title_conflict = next(c for c in interactive if c.section == 'project_info' and c.field == 'title')
    check("title conflict folds in report's project_name (still a straight mirror)",
          any(f.section == 'report' and f.field == 'project_name' for f in title_conflict.also_affects))
    check("quality_control's independently-diverged designation is NOT folded in",
          not any(f.section == 'quality_control' for f in title_conflict.also_affects))
    check("quality_control's designation conflict still shown on its own",
          any(c.section == 'quality_control' and c.field == 'designation' for c in interactive))
    check("folded conflicts don't ALSO appear as their own top-level rows",
          not any(c.section == 'report' and c.field == 'project_name' for c in interactive))

    # Resolving the primary should resolve its folded followers too
    report_follower = next(f for f in title_conflict.also_affects if f.section == 'report')
    title_conflict.resolve('Chosen Title')
    report_follower.resolve('Chosen Title')
    check("primary resolution applied", merged['project_info']['title'] == 'Chosen Title')
    check("folded follower resolution applied", merged['report']['reports'][0]['project_name'] == 'Chosen Title')


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
        test_quality_control_merge,
        test_brief_merge,
        test_drawing_scale_merge,
        test_path_labels_resolve_item_names,
        test_fold_linked_conflicts,
    ]
    for t in tests:
        t()
    print()
    print(f"{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == '__main__':
    import sys
    sys.exit(main())

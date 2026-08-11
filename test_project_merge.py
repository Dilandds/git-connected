#!/usr/bin/env python3
"""
Standalone tests for core/project_merge.py's pure merge functions.
No Qt, no file I/O, no pytest dependency (none is installed in this repo) —
just plain asserts, matching the style of the other test_*.py scripts here.

Usage:
    python test_project_merge.py
"""
import json

from core.project_merge import (
    Conflict, merge_dict_fields, merge_dict_fields_prefer_local, merge_list_by_id,
    merge_nested_by_path, merge_list_add_only, detect_id_collision, merge_section,
    merge_project, field_conflicts_only, fold_linked_conflicts,
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


def test_merge_dict_fields_prefer_local():
    print("test_merge_dict_fields_prefer_local")
    base = {'title': 'Orig', 'comments': 'Orig comment', 'unused': 'x'}
    local = {'title': 'Orig', 'comments': 'Local comment', 'unused': 'x'}
    remote = {'title': 'Orig', 'comments': 'Remote comment', 'unused': 'x'}
    merged = merge_dict_fields_prefer_local(base, local, remote)
    check("dual-edit on the same field auto-resolved to local (no Conflict object involved)",
          merged['comments'] == 'Local comment')
    check("untouched field passes through unchanged", merged['title'] == 'Orig')

    # only one side changed -> that side's value wins, same as merge_dict_fields
    local2 = dict(base)
    local2['title'] = 'Local title'
    merged2 = merge_dict_fields_prefer_local(base, local2, remote)
    check("only-local change kept when remote didn't touch the field", merged2['title'] == 'Local title')


def test_technical_overview_merge():
    print("test_technical_overview_merge")
    base = {
        'metadata': {'title': 'Widget', 'comments': ''},
        'document_bytes': b'PDF-BYTES-V1', 'document_ext': '.pdf',
        'annotations': [{'id': 1, 'text': 'note', 'image_paths': ['/tmp/x1/images/ann_1_img_0.png']}],
    }

    # Side-panel metadata edited differently on both sides; content
    # identical (annotations' image_paths point into two different temp
    # dirs, exactly like two independent _decode_technical_overview calls
    # of the same underlying image would produce) -> must NOT produce an
    # interactive conflict, and metadata must not just be dropped.
    local = {
        'metadata': {'title': 'Widget', 'comments': 'Local comment'},
        'document_bytes': b'PDF-BYTES-V1', 'document_ext': '.pdf',
        'annotations': [{'id': 1, 'text': 'note', 'image_paths': ['/tmp/local_xyz/images/ann_1_img_0.png']}],
    }
    remote = {
        'metadata': {'title': 'Widget', 'comments': 'Remote comment'},
        'document_bytes': b'PDF-BYTES-V1', 'document_ext': '.pdf',
        'annotations': [{'id': 1, 'text': 'note', 'image_paths': ['/tmp/remote_abc/images/ann_1_img_0.png']}],
    }
    merged, conflicts = merge_section('technical_overview', base, local, remote)
    check("metadata dual-edit never surfaces as an interactive conflict", conflicts == [])
    check("metadata dual-edit auto-resolved to local", merged['metadata']['comments'] == 'Local comment')
    check("identical content (different temp-dir image_paths) treated as unchanged",
          merged['document_bytes'] == b'PDF-BYTES-V1' and len(merged['annotations']) == 1)

    # Only local touched the document; remote never touched Technical
    # Overview at all -> silent, no conflict, local's document kept. This
    # is the exact scenario behind the reported bug: two sessions that
    # never touched Technical Overview must not conflict just because the
    # bundle gets re-zipped with fresh timestamps on every save.
    local_doc_change = dict(base)
    local_doc_change['metadata'] = dict(base['metadata'])
    local_doc_change['document_bytes'] = b'PDF-BYTES-V2'
    local_doc_change['annotations'] = list(base['annotations'])
    merged2, conflicts2 = merge_section('technical_overview', base, local_doc_change, base)
    check("only-local document change kept silently, no conflict",
          merged2['document_bytes'] == b'PDF-BYTES-V2' and conflicts2 == [])

    # Both sides genuinely changed the document differently -> one real,
    # rare conflict, not a whole-section dump.
    local3 = dict(base)
    local3['metadata'] = dict(base['metadata'])
    local3['document_bytes'] = b'PDF-BYTES-LOCAL'
    local3['annotations'] = list(base['annotations'])
    remote3 = dict(base)
    remote3['metadata'] = dict(base['metadata'])
    remote3['document_bytes'] = b'PDF-BYTES-REMOTE'
    remote3['annotations'] = list(base['annotations'])
    merged3, conflicts3 = merge_section('technical_overview', base, local3, remote3)
    check("genuine document divergence produces exactly one conflict",
          len(conflicts3) == 1 and conflicts3[0].field == 'document'
          and conflicts3[0].section == 'technical_overview')
    conflicts3[0].resolve(conflicts3[0].remote_value)
    check("resolve() writes the chosen side's document bytes into the merged result",
          merged3['document_bytes'] == b'PDF-BYTES-REMOTE')


def test_assignment_merge():
    print("test_assignment_merge")
    base = {
        'tabs': [{
            'id': 'tab-1', 'image_name': 'plan.png', 'image_path': '/x/plan.png',
            'orientation': 'portrait', 'font_family': '', 'font_size': 13,
            'cards': [{'id': 'c1', 'title': 'Handle', 'supplier': '', 'status': 'In progress',
                       'number': 1, 'x': 0.0, 'y': 0.0, 'color': '#3b82f6', 'arrows': []}],
        }],
        'current_tab': 0,
    }

    # local edits one card's status; remote's own tab (independently
    # untouched, still identical to base) must survive fully intact,
    # including its image — the exact bug reported: a card-only edit must
    # not wholesale-clobber the rest of the section.
    local = json.loads(json.dumps(base))
    local['tabs'][0]['cards'][0]['status'] = 'Done'
    remote = json.loads(json.dumps(base))

    merged, conflicts = merge_section('assignment', base, local, remote)
    check("no conflicts (only local touched anything)", conflicts == [])
    check("card status change kept", merged['tabs'][0]['cards'][0]['status'] == 'Done')
    check("tab's image untouched by an unrelated card edit",
          merged['tabs'][0]['image_path'] == '/x/plan.png')

    # remote adds a second tab with its own image; local only edited a
    # card in tab 1 -> both survive, tab 2's image is not lost.
    remote2 = json.loads(json.dumps(base))
    remote2['tabs'].append({
        'id': 'tab-2', 'image_name': 'back.png', 'image_path': '/x/back.png',
        'orientation': 'portrait', 'font_family': '', 'font_size': 13, 'cards': [],
    })
    merged2, conflicts2 = merge_section('assignment', base, local, remote2)
    check("no conflicts (different things changed)", conflicts2 == [])
    check("both tabs present after merge", {tb['id'] for tb in merged2['tabs']} == {'tab-1', 'tab-2'})
    check("remote's new tab image kept",
          next(tb for tb in merged2['tabs'] if tb['id'] == 'tab-2')['image_path'] == '/x/back.png')
    check("local's card edit on tab 1 also kept",
          next(tb for tb in merged2['tabs'] if tb['id'] == 'tab-1')['cards'][0]['status'] == 'Done')

    # same card field changed differently on both sides -> real, isolated
    # conflict, not a whole-tab or whole-section one.
    local3 = json.loads(json.dumps(base))
    local3['tabs'][0]['cards'][0]['status'] = 'Done'
    remote3 = json.loads(json.dumps(base))
    remote3['tabs'][0]['cards'][0]['status'] = 'Blocked'
    merged3, conflicts3 = merge_section('assignment', base, local3, remote3)
    check("isolated card-field conflict, not a whole-section one",
          len(conflicts3) == 1 and conflicts3[0].field == 'status' and conflicts3[0].section == 'assignment')

    # current_tab re-resolved by id, not raw index, when tabs shift
    local4 = json.loads(json.dumps(base))
    local4['tabs'].insert(0, {
        'id': 'tab-0', 'image_name': '', 'image_path': '', 'orientation': 'portrait',
        'font_family': '', 'font_size': 13, 'cards': [],
    })
    local4['current_tab'] = 1  # still pointing at tab-1, now at index 1
    merged4, _ = merge_section('assignment', base, local4, base)
    check("current_tab re-resolved to tab-1's new index after a tab was inserted ahead of it",
          merged4['tabs'][merged4['current_tab']]['id'] == 'tab-1')


def test_rd_merge():
    print("test_rd_merge")
    base = {'components': [{
        'id': 'c1', 'name': 'Handle', 'supplier': '', 'color': '',
        'brief': {'objective': '', 'constraints': '', 'budget_min': 0.0, 'budget_max': 0.0,
                  'quantity': 1, 'quantity_unit': 'piece',
                  'notes': [{'id': 'n1', 'text': 'first note', 'author': 'A', 'date': '2026-01-01'}]},
        'proposals': [{'id': 'p1', 'name': 'Brass', 'image_path': '/x/brass.png', 'status': 'in_evaluation'}],
        'technique_proposals': [],
    }]}

    # local edits a brief note; remote independently edits a proposal's
    # status in the SAME component -> both survive, proposal's image intact.
    local = json.loads(json.dumps(base))
    local['components'][0]['brief']['notes'][0]['text'] = 'edited note'
    remote = json.loads(json.dumps(base))
    remote['components'][0]['proposals'][0]['status'] = 'selected'

    merged, conflicts = merge_section('rd', base, local, remote)
    check("no conflicts (different things changed)", conflicts == [])
    check("local's note edit kept", merged['components'][0]['brief']['notes'][0]['text'] == 'edited note')
    check("remote's proposal status change kept",
          merged['components'][0]['proposals'][0]['status'] == 'selected')
    check("unrelated proposal's image untouched by a note edit elsewhere in the same component",
          merged['components'][0]['proposals'][0]['image_path'] == '/x/brass.png')


def test_estimated_cost_merge():
    print("test_estimated_cost_merge")
    base = {'currency': 'EUR', 'trades': [{'id': 1, 'name': 'Trade', 'partners': [
        {'id': 1, 'name': 'Partner', 'activity': '', 'start_date': '', 'delivery_date': '',
         'is_best': False, 'tax_rate': 0,
         'tasks': [{'component': 'a', 'task': 'b', 'hours': 1, 'hourly_rate': 10}]},
    ]}]}
    local = json.loads(json.dumps(base))
    local['trades'][0]['name'] = 'Renamed Trade'
    remote = json.loads(json.dumps(base))
    remote['trades'][0]['partners'][0]['tasks'][0]['hours'] = 8

    merged, conflicts = merge_section('estimated_cost', base, local, remote)
    check("no conflicts (different fields changed)", conflicts == [])
    check("local's trade rename kept", merged['trades'][0]['name'] == 'Renamed Trade')
    check("remote's task hours change kept (id-less tasks list replaced wholesale, safely)",
          merged['trades'][0]['partners'][0]['tasks'][0]['hours'] == 8)


def test_files_merge():
    print("test_files_merge")
    base = {
        'next_folder_id': 2, 'next_file_id': 2,
        'folders': [{'id': 1, 'name': 'Docs'}],
        'files': [{'id': 1, 'folder_id': 1, 'name': 'a.txt',
                   'versions': [{'version_str': 'v1', 'file_data_b64': 'QQQQ'}]}],
    }
    # local renames folder; remote independently uploads a brand new file
    # with real content -> both survive, remote's file content intact.
    local = json.loads(json.dumps(base))
    local['folders'][0]['name'] = 'Documents'
    remote = json.loads(json.dumps(base))
    remote['files'].append({'id': 2, 'folder_id': 1, 'name': 'b.txt',
                             'versions': [{'version_str': 'v1', 'file_data_b64': 'QkJCQg=='}]})
    remote['next_file_id'] = 3

    merged, conflicts = merge_section('files', base, local, remote)
    check("no conflicts (different things changed)", conflicts == [])
    check("local's folder rename kept", merged['folders'][0]['name'] == 'Documents')
    check("both files present", {f['id'] for f in merged['files']} == {1, 2})
    new_file = next(f for f in merged['files'] if f['id'] == 2)
    check("remote's new file content survived the merge (not dropped)",
          new_file['versions'][0]['file_data_b64'] == 'QkJCQg==')
    check("next_file_id bumped past the highest surviving id", merged['next_file_id'] == 3)


def test_validation_merge():
    print("test_validation_merge")
    base = {'sessions': [{
        'id': 's1', 'signature': '', 'schedule_dates': [''] * 7,
        'stakeholders': [{'id': 'st1', 'name': 'Alice', 'role': ''}],
        'modifications': [], 'action_plan': [],
    }]}
    local = json.loads(json.dumps(base))
    local['sessions'][0]['stakeholders'][0]['name'] = 'Alice Renamed'
    remote = json.loads(json.dumps(base))
    remote['sessions'][0]['signature'] = 'Approved'

    merged, conflicts = merge_section('validation', base, local, remote)
    check("no conflicts (different fields changed)", conflicts == [])
    check("local's stakeholder rename kept", merged['sessions'][0]['stakeholders'][0]['name'] == 'Alice Renamed')
    check("remote's signature change kept", merged['sessions'][0]['signature'] == 'Approved')


def test_prototype_merge():
    print("test_prototype_merge")
    base = {'next_number': 3, 'versions': [
        {'id': 'v1', 'version_number': 1, 'date': '', 'status': '', 'comments': '',
         'image_paths': ['/x/v1_main.png'], 'file_paths': []},
        {'id': 'v2', 'version_number': 2, 'date': '', 'status': '', 'comments': '',
         'image_paths': ['/x/v2_main.png'], 'file_paths': []},
    ]}
    # local edits v1's comments; remote independently edits v2's status ->
    # both survive, neither version's photos are touched by the other's edit.
    local = json.loads(json.dumps(base))
    local['versions'][0]['comments'] = 'looks good'
    remote = json.loads(json.dumps(base))
    remote['versions'][1]['status'] = 'approved'

    merged, conflicts = merge_section('prototype', base, local, remote)
    check("no conflicts (different versions/fields changed)", conflicts == [])
    by_id = {v['id']: v for v in merged['versions']}
    check("local's v1 comment kept", by_id['v1']['comments'] == 'looks good')
    check("remote's v2 status kept", by_id['v2']['status'] == 'approved')
    check("v1's own photo untouched by a comment edit", by_id['v1']['image_paths'] == ['/x/v1_main.png'])
    check("v2's own photo untouched by a status edit elsewhere", by_id['v2']['image_paths'] == ['/x/v2_main.png'])


def test_version_comparison_merge():
    print("test_version_comparison_merge")
    base = {'next_id': 2, 'cards': [
        {'id': 1, 'star_number': 1, 'version': 'v1', 'comments': '', 'cost': '',
         'positive_points': '', 'negative_points': '', 'photo_paths': ['/x/card1.png']},
    ]}
    local = json.loads(json.dumps(base))
    local['cards'][0]['comments'] = 'note from local'
    remote = json.loads(json.dumps(base))
    remote['cards'].append({'id': 2, 'star_number': 2, 'version': 'v2', 'comments': '', 'cost': '',
                             'positive_points': '', 'negative_points': '', 'photo_paths': ['/x/card2.png']})
    remote['next_id'] = 3

    merged, conflicts = merge_section('version_comparison', base, local, remote)
    check("no conflicts (different things changed)", conflicts == [])
    by_id = {c['id']: c for c in merged['cards']}
    check("local's comment kept", by_id[1]['comments'] == 'note from local')
    check("card 1's own photo untouched by remote adding a different card",
          by_id[1]['photo_paths'] == ['/x/card1.png'])
    check("remote's new card 2 (and its photo) survived", by_id[2]['photo_paths'] == ['/x/card2.png'])
    check("next_id bumped past the highest surviving id", merged['next_id'] == 3)


def test_glossary_merge():
    print("test_glossary_merge")
    base = {'next_id': 2, 'terms': [{'id': 1, 'term': 'Anodizing', 'definition': 'Old def'}]}
    local = json.loads(json.dumps(base))
    local['terms'][0]['definition'] = 'Updated def'
    remote = json.loads(json.dumps(base))
    remote['terms'].append({'id': 2, 'term': 'Casting', 'definition': 'New term'})
    remote['next_id'] = 3

    merged, conflicts = merge_section('glossary', base, local, remote)
    check("no conflicts (different things changed)", conflicts == [])
    check("both terms present", {t['id'] for t in merged['terms']} == {1, 2})
    check("next_id bumped past the highest surviving id", merged['next_id'] == 3)


def test_assignment_ensure_tab_ids():
    print("test_assignment_ensure_tab_ids")
    from ui.assignment_widget import ensure_tab_ids

    # Real ids are preserved untouched.
    tabs = [{'id': 'real-id', 'image_name': 'a.png'}]
    check("existing id kept as-is", ensure_tab_ids(tabs)[0]['id'] == 'real-id')

    # A save from before tabs had ids (none present at all) gets a
    # deterministic positional fallback...
    legacy = [{'image_name': 'a.png'}, {'image_name': 'b.png'}]
    result1 = ensure_tab_ids(legacy)
    check("missing id gets a positional fallback", [t['id'] for t in result1] == ['tab-0', 'tab-1'])

    # ...and, critically, two INDEPENDENT calls on the same legacy data
    # (standing in for two separate machines loading the same unmigrated
    # file) must derive the IDENTICAL fallback ids — this is exactly what
    # keeps core.project_merge from mistaking "the same untouched tab" for
    # a brand-new id collision between local and remote (which crashed
    # trying to renumber a string id as if it were numeric).
    result2 = ensure_tab_ids(legacy)
    check("two independent calls derive identical fallback ids",
          [t['id'] for t in result1] == [t['id'] for t in result2])

    # merge_section itself must not choke on an all-legacy scenario once
    # normalized (this is what ui/project_widget.py's _resolve_save_conflicts
    # now does to base/local/remote before calling merge_project).
    base = {'current_tab': 0, 'tabs': ensure_tab_ids(legacy)}
    local = json.loads(json.dumps(base))
    local['tabs'][0]['image_name'] = 'renamed.png'
    remote = json.loads(json.dumps(base))
    merged, conflicts = merge_section('assignment', base, local, remote)
    check("no crash and no spurious collision merging an all-legacy assignment section", conflicts == [])
    check("local's rename kept, legacy tab correctly recognized as the same tab",
          merged['tabs'][0]['image_name'] == 'renamed.png' and len(merged['tabs']) == 2)


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
        test_merge_dict_fields_prefer_local,
        test_technical_overview_merge,
        test_assignment_merge,
        test_rd_merge,
        test_estimated_cost_merge,
        test_files_merge,
        test_validation_merge,
        test_prototype_merge,
        test_version_comparison_merge,
        test_glossary_merge,
        test_assignment_ensure_tab_ids,
    ]
    for t in tests:
        t()
    print()
    print(f"{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == '__main__':
    import sys
    sys.exit(main())

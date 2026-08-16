"""
.lyns.review envelope — the file LYNS360 exports for one supplier and LYNS
Lite opens. Unlike .ecto/.lyns (a ZIP), this is a single flat JSON file
(base64 blobs embedded directly), matching the original disabled export
stub's format — simpler to read/patch by hand and consistent with how
project_widget.py already embeds .lyns/.ecto bundles as base64 strings
inside the project JSON.

Contains only the sections the PM chose to share:
  - viewer_tabs:        one or more entries shaped like TheProjectWidget.
                         _bundle_viewer_tabs()'s per-tab body ({id, tab_name,
                         bundle_b64}) — a review can include multiple open
                         3D models at once, not just one.
  - technical_overview: TheProjectWidget._bundle_technical_overview() output, or None.
  - drawing_scale:      TheProjectWidget._bundle_drawing_scale() output, or None.
  - quality_control:    QualityControlWidget.get_data() output, with 'images'
                         filtered to the PM-selected subset (control points
                         travel with their image automatically).
  - report:             ReportWidget.get_data() output (ui/report/widget.py) —
                         included whole, no per-page filtering (unlike QC's
                         image subset). Always opened read-only in LYNS Lite
                         (see ReportWidget.set_read_only) — a supplier can
                         view the PM's report but never edit it.
  - project_info:       ProjectNavPanel.get_info_data() output — read-only on
                         the Lite side, not baked into the data itself.

See ui/export_review_dialog.py for where the PM's choices come from and
core/supplier_registry.py for the Supplier shape.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

REVIEW_FILE_TYPE = 'lyns.review'
REVIEW_FORMAT_VERSION = '2.2'


def build_review_envelope(
    exported_by: str,
    original_filename: str,
    supplier: dict,
    viewer_tabs: Optional[list],
    technical_overview: Optional[dict],
    drawing_scale: Optional[dict],
    quality_control: Optional[dict],
    project_info: Optional[dict],
    report: Optional[dict] = None,
) -> dict:
    return {
        'file_type': REVIEW_FILE_TYPE,
        'version': REVIEW_FORMAT_VERSION,
        'exported_by': exported_by,
        'exported_at': datetime.now(timezone.utc).isoformat(),
        'original_filename': original_filename,
        'supplier': supplier,
        'viewer_tabs': viewer_tabs or [],
        'technical_overview': technical_overview,
        'drawing_scale': drawing_scale,
        'quality_control': quality_control,
        'project_info': project_info,
        'report': report,
    }


def save_review_file(envelope: dict, file_path: str) -> None:
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(envelope, f, indent=2, ensure_ascii=False)


def load_review_file(file_path: str) -> dict:
    """Read and validate a .lyns.review file. Raises ValueError if it isn't one."""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if data.get('file_type') != REVIEW_FILE_TYPE:
        raise ValueError('Not a valid .lyns.review file')
    return data


def ensure_review_extension(file_path: str) -> str:
    """Normalize a save-dialog result onto exactly one trailing
    '.lyns.review'. Windows' native Save dialog only reasons about the
    text after the LAST dot when deciding whether a typed/pre-filled name
    already carries the current filter's extension — for a compound
    extension like '.lyns.review' it doesn't recognize
    "supplier.lyns.review" as already complete, and appends its own
    (sometimes partial: just ".review") extension on top, producing
    "supplier.lyns.review.lyns.review" or "supplier.lyns.review.review".
    Strip whichever known variant is present — longest first, so the
    fully-doubled case doesn't only get half-stripped — then apply
    exactly one canonical suffix. Safe to call regardless of what
    Windows already did (or didn't) append; callers should also avoid
    pre-filling the dialog's default filename with the extension already
    on it (see _export_supplier_review / _lite_save_review) since an
    already-dotted default name is what triggers this Windows behavior
    in the first place."""
    for suffix in ('.lyns.review.lyns.review', '.lyns.review.review', '.lyns.review', '.review'):
        if file_path.endswith(suffix):
            file_path = file_path[:-len(suffix)]
            break
    return file_path + '.lyns.review'


def is_review_file(file_path: str) -> bool:
    try:
        load_review_file(file_path)
        return True
    except Exception:
        return False


def filter_quality_control(qc_data: dict, image_ids: list) -> dict:
    """Return a copy of QualityControlWidget.get_data() output with 'images'
    narrowed to the PM-selected subset. Everything else (inspection_date,
    inspected_by, comments, general_control_points, company info fields)
    passes through unchanged — only per-image data is scoped per supplier."""
    if not qc_data:
        return qc_data
    filtered = dict(qc_data)
    id_set = set(image_ids)
    filtered['images'] = [img for img in qc_data.get('images', []) if img.get('id') in id_set]
    return filtered

"""
ECTOFORM Edition Detection.

Set the environment variable ECTOFORM_EDITION to "education" or "lite"
before launching to run that edition. The default is 'commercial'.

Education edition restrictions:
  - PDF export disabled (3D PDF + Technical PDF)
  - Passcode protection disabled for .ecto files
  - Watermark banner at top of window, below 3D viewer, and embedded in .ecto files

Lite edition ("LYNS Lite") is the supplier-facing companion app — opens
only .lyns.review files, shows a reduced set of screens. It carries none
of the Education restrictions above (no watermark, no feature blocks);
see main_lite.py / core/file_association.py for what's actually different.

Core edition ("LYNS Core") is full-featured commercial minus "The
Project" section — no Brief/Assignment/Timeline/R&D/Estimated Cost/
Traceability/Report/Files/Validation/Prototype/Version Comparison/
Quality Control/To-Do/Glossary nav, and no "📁 The Project" mode button
at all (see stl_viewer.py's mode-bar construction). It still opens/saves
a normal .lyns.pjt project file — New/Open/Save/Save As/Version History/
Password all work exactly like Commercial — since TheProjectWidget's
save/load already tolerates nav screens that are never constructed (see
_gather_live_data's per-key None handling); Core just never builds or
shows any of them. 3D Viewer, Technical Overview, and Drawing Scale are
fully editable, same as Commercial. No watermark, no feature blocks.
"""
import os
import logging

logger = logging.getLogger(__name__)

_EDITION = os.environ.get("ECTOFORM_EDITION", "commercial").strip().lower()
logger.info(f"ECTOFORM edition: {_EDITION}")

WATERMARK_TEXT = "This version is exclusively for Education and not professional use"


def is_education() -> bool:
    """Return True when running the Education edition."""
    return _EDITION == "education"


def is_lite() -> bool:
    """Return True when running the Lite edition (LYNS Lite, supplier-facing)."""
    return _EDITION == "lite"


def is_core() -> bool:
    """Return True when running the Core edition (LYNS Core — full editor
    minus "The Project" section, see module docstring)."""
    return _EDITION == "core"


def is_commercial() -> bool:
    """Return True when running the Commercial edition."""
    return _EDITION == "commercial"

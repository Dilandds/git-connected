"""
ECTOFORM Edition Detection.

Set the environment variable ECTOFORM_EDITION=education before launching
to run the Education edition.  The default is 'commercial'.

Education edition restrictions:
  - PDF export disabled (3D PDF + Technical PDF)
  - Passcode protection disabled for .ecto files
  - Watermark banner at top of window, below 3D viewer, and embedded in .ecto files
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


def is_commercial() -> bool:
    """Return True when running the Commercial edition."""
    return not is_education()

# Re-export shim — kept for any direct imports.
# Dialog now lives in ui/traceability/dialogs.py
from .dialogs import _PartDialog

__all__ = ['_PartDialog']

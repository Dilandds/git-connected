"""
Image utilities for ECTOFORM, including HEIC (iPhone) to JPEG conversion and
base64 embedding — every image field in a saved project is embedded as base64
(not a bare filesystem path) so it actually travels with the project file
across machines instead of only resolving on whichever machine originally
picked the file.
"""
import base64
import os
import logging
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QBuffer, QIODevice
from PyQt5.QtGui import QPixmap

logger = logging.getLogger(__name__)


def convert_heic_to_jpeg(heic_path: str, output_path: Optional[str] = None) -> Optional[str]:
    """
    Convert a HEIC image to JPEG.
    
    Args:
        heic_path: Path to the HEIC file.
        output_path: Optional path for the output JPEG. If None, saves next to
            the HEIC file with the same base name and .jpg extension.
    
    Returns:
        Path to the converted JPEG file, or None if conversion failed.
    """
    if not os.path.exists(heic_path):
        logger.warning(f"convert_heic_to_jpeg: File not found: {heic_path}")
        return None
    
    try:
        import pillow_heif
        from PIL import Image
        
        pillow_heif.register_heif_opener()
        
        if output_path is None:
            base, _ = os.path.splitext(heic_path)
            output_path = base + ".jpg"
        
        img = Image.open(heic_path)
        # Convert to RGB if necessary (HEIC may have alpha or different mode)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        elif img.mode != "RGB":
            img = img.convert("RGB")
        
        img.save(output_path, "JPEG", quality=92)
        logger.info(f"Converted HEIC to JPEG: {heic_path} -> {output_path}")
        return output_path
        
    except ImportError as e:
        logger.warning(f"HEIC conversion requires pillow-heif: {e}")
        return None
    except Exception as e:
        logger.warning(f"Failed to convert HEIC {heic_path}: {e}")
        return None


def ensure_image_readable(path: str) -> Optional[str]:
    """
    If the path points to a HEIC file, convert it to JPEG and return the new path.
    Otherwise return the original path.
    
    Returns:
        Path to a readable image (JPEG/PNG/etc or converted HEIC), or None if
        conversion failed for a HEIC file (caller should skip adding it).
    """
    if not path or not os.path.exists(path):
        return path
    
    ext = os.path.splitext(path)[1].lower()
    if ext in (".heic", ".heif"):
        converted = convert_heic_to_jpeg(path)
        if converted:
            return converted
        # Conversion failed - return None so caller skips (QPixmap can't display HEIC)
        return None

    return path


# ── base64 embedding ─────────────────────────────────────────────────────────
# The shared pattern every image-carrying section uses: encode to PNG bytes,
# base64 that, store the string in the project JSON. Consolidates what used
# to be near-identical _pixmap_to_b64/_b64_to_pixmap pairs duplicated in
# ui/quality_control_widget.py and ui/brief's section_inspiration.py/
# section_overview.py.

def pixmap_to_b64(pix: QPixmap) -> Optional[str]:
    """PNG-encode a QPixmap and base64 it. None for a null/invalid pixmap."""
    if pix is None or pix.isNull():
        return None
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    pix.save(buf, 'PNG')
    buf.close()
    return base64.b64encode(bytes(buf.data())).decode()


def b64_to_pixmap(data: Optional[str]) -> Optional[QPixmap]:
    """Reverse of pixmap_to_b64. None for empty/invalid/corrupt input —
    never raises, callers can treat None the same as "no image saved"."""
    if not data:
        return None
    try:
        raw = base64.b64decode(data)
        pix = QPixmap()
        pix.loadFromData(raw, 'PNG')
        return pix if not pix.isNull() else None
    except Exception:
        return None


def path_to_b64(path: str) -> Optional[str]:
    """Load an image file from disk (any Qt-supported format, plus HEIC/HEIF
    via ensure_image_readable) and return it as PNG base64. None if the path
    is empty, the file is missing, or it isn't a readable image — the single
    entry point every "user picked a file, embed it" upload handler should
    call instead of storing the raw path."""
    if not path:
        return None
    resolved = ensure_image_readable(path)
    if not resolved:
        return None
    return pixmap_to_b64(QPixmap(resolved))


def migrate_path_to_b64(d: dict, path_key: str, b64_key: str) -> dict:
    """Return a copy of dict `d` with a legacy path field folded into its
    replacement base64 field: if `b64_key` is already present (a save from
    after this conversion), it's kept as-is; otherwise, if `path_key` is
    present (a save from before it), best-effort convert that file to
    base64 if it still exists on THIS machine. Always drops `path_key` from
    the result — the path itself is never portable and isn't worth keeping
    around once we've tried to migrate it. Used at every load site that
    used to read a bare path field, so an already-uploaded photo isn't
    silently lost the next time an old project is opened and re-saved."""
    d = dict(d)
    old_path = d.pop(path_key, None)
    if not d.get(b64_key) and old_path:
        d[b64_key] = path_to_b64(old_path) or ''
    d.setdefault(b64_key, '')
    return d


def file_to_b64(path: str) -> Optional[str]:
    """Read a file's raw bytes (any type, not just images — e.g. Prototype's
    arbitrary attachments) and base64 them. None if missing/unreadable."""
    try:
        return base64.b64encode(Path(path).read_bytes()).decode()
    except OSError as e:
        logger.warning(f'file_to_b64: could not read {path}: {e}')
        return None

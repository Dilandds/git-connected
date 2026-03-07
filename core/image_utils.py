"""
Image utilities for ECTOFORM, including HEIC (iPhone) to JPEG conversion.
"""
import os
import logging
from typing import Optional

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

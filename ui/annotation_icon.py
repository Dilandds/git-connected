"""Shared annotation icon helper for crisp rendering across different sizes."""
import os
import sys
from pathlib import Path
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QApplication


def _get_assets_base():
    """Return base path for assets (handles PyInstaller frozen bundle)."""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


_ICON_PATH = str(_get_assets_base() / 'assets' / 'annotation_icon.png')


def get_annotation_icon_path():
    """Return the path to the annotation icon, or None if not found."""
    return _ICON_PATH if os.path.exists(_ICON_PATH) else None


def get_annotation_icon_pixmap(size: int = 24, path: str = None):
    """Load and scale the annotation icon for crisp display (handles high-DPI).
    
    Args:
        size: Logical size in pixels (e.g., 24 for toolbar)
        path: Optional path to icon file (defaults to assets/annotation_icon.png)
    
    Returns:
        QPixmap scaled for sharp display, or empty QPixmap if not found
    """
    path = path or get_annotation_icon_path()
    if not path or not os.path.exists(path):
        return QPixmap()
    pixmap = QPixmap(path)
    if pixmap.isNull():
        return QPixmap()
    # Scale at 2x for retina/high-DPI - provides crisper rendering
    dpr = 2
    if QApplication.instance():
        try:
            dpr = int(QApplication.instance().devicePixelRatio()) or 2
        except Exception:
            dpr = 2
    target = size * dpr
    scaled = pixmap.scaled(target, target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    scaled.setDevicePixelRatio(dpr)
    return scaled

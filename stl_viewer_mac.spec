# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for ECTOFORM macOS build.
"""

import sys
import os
from pathlib import Path

block_cipher = None

# Get project root directory (where spec file is located)
# Build script changes to project directory, so use CWD for reliability
# This is more reliable than SPECPATH which may have path resolution issues
project_root = Path(os.getcwd())

# Debug: Print what we're checking
print(f"[PyInstaller] Project root: {project_root}")
print(f"[PyInstaller] Checking for assets/splash.png: {(project_root / 'assets' / 'splash.png').exists()}")
print(f"[PyInstaller] Checking for assets/icon.icns: {(project_root / 'assets' / 'icon.icns').exists()}")

# Build datas list with assets
datas = [
    ('ui', 'ui'),
    ('core', 'core'),
]

# Add splash screen images if they exist
splash_image_paths = [
    ('assets/splash.png', 'assets'),
    ('assets/splash.jpg', 'assets'),
    ('assets/logo.png', 'assets'),
    ('assets/logo.jpg', 'assets'),
    ('assets/annotation_icon.png', 'assets'),
    ('assets/xyz_gizmo.png', 'assets'),
    ('assets/dropdown_arrow.png', 'assets'),
]

for src_path, dst_path in splash_image_paths:
    full_path = project_root / src_path
    if full_path.exists():
        print(f"[PyInstaller] [OK] Adding to bundle: {src_path}")
        datas.append((src_path, dst_path))
    else:
        print(f"[PyInstaller] [X] NOT found: {full_path}")

print(f"[PyInstaller] Final datas list has {len(datas)} items")

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # PyQt5 modules
        'PyQt5',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        'PyQt5.sip',
        # PyVista and VTK
        'pyvista',
        'pyvistaqt',
        'vtkmodules',
        'vtkmodules.all',
        'vtkmodules.qt.QVTKRenderWindowInteractor',
        # Pygfx and deps (WebGPU viewer, avoids Windows black screen)
        'pygfx',
        'wgpu',
        'trimesh',
        'rendercanvas',
        'rendercanvas.qt',
        'scipy',
        'viewer_widget_pygfx',
        # NumPy
        'numpy',
        'numpy.core._methods',
        'numpy.lib.format',
        # ReportLab for PDF export
        'reportlab',
        'reportlab.pdfgen',
        'reportlab.lib',
        'reportlab.platypus',
        # Requests for license validation
        'requests',
        'urllib3',
        # Custom modules
        'stl_viewer',
        'viewer_widget',
        'viewer_widget_offscreen',
        'ui.sidebar_panel',
        'ui.toolbar',
        'ui.styles',
        'ui.components',
        'ui.license_dialog',
        'core.mesh_calculator',
        'core.license_validator',
        'core.image_utils',
        # HEIC (iPhone) to JPEG conversion in annotation mode
        'PIL',
        'PIL.Image',
        'pillow_heif',
        # Standard library modules that might be missed
        'logging',
        'pathlib',
        'datetime',
        'io',
        'json',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # PyQt6 (not used)
        'PyQt6', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets',
        # Unused PyQt5 modules
        'PyQt5.QtWebEngine', 'PyQt5.QtWebEngineWidgets', 'PyQt5.QtWebEngineCore',
        'PyQt5.QtBluetooth', 'PyQt5.QtNfc',
        'PyQt5.QtLocation', 'PyQt5.QtPositioning',
        'PyQt5.QtMultimedia', 'PyQt5.QtMultimediaWidgets', 'PyQt5.QtMultimediaQuick',
        'PyQt5.QtQuick', 'PyQt5.QtQml', 'PyQt5.QtQuickWidgets',
        'PyQt5.QtSql',
        'PyQt5.QtXml', 'PyQt5.QtXmlPatterns',
        'PyQt5.QtNetwork',
        'PyQt5.QtSvg',
        'PyQt5.QtDesigner', 'PyQt5.QtHelp',
        # Test files
        'test_minimal_pyqt6', 'test_pyvista_qt', 'test_pyvista_simple', 'test_volume_methods',
        'check_results',
        # VTK web modules (not needed)
        'vtkmodules.web', 'vtkmodules.qt.web',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ECTOFORM',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,  # Enable stripping for size reduction
    upx=True,
    console=False,  # Windowed app, no console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=True,  # Enable stripping for size reduction
    upx=True,
    upx_exclude=[],
    name='ECTOFORM',
)

# Debug icon for BUNDLE
bundle_icon_path = project_root / 'assets' / 'icon.icns'
bundle_icon = str(bundle_icon_path) if bundle_icon_path.exists() else None
if bundle_icon:
    print(f"[PyInstaller] [OK] Icon will be used for BUNDLE: {bundle_icon}")
else:
    print(f"[PyInstaller] [X] Icon NOT found for BUNDLE: {bundle_icon_path}")

app = BUNDLE(
    coll,
    name='ECTOFORM.app',
    icon=bundle_icon,
        bundle_identifier='com.ectoform.app',
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSHighResolutionCapable': 'True',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleVersion': '1.0.0',
        'NSHumanReadableCopyright': 'Copyright © 2024',
        'LSMinimumSystemVersion': '10.13',
    },
)

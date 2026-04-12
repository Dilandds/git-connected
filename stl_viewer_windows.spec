# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for ECTOFORM Windows build.
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
print(f"[PyInstaller] Checking for assets/icon.ico: {(project_root / 'assets' / 'icon.ico').exists()}")

# Build datas list with assets
datas = [
    ('ui', 'ui'),
    ('core', 'core'),
]

# Add splash screen and icon assets if they exist
splash_image_paths = [
    ('assets/splash.png', 'assets'),
    ('assets/splash.jpg', 'assets'),
    ('assets/logo.png', 'assets'),
    ('assets/logo.jpg', 'assets'),
    ('assets/annotation_icon.png', 'assets'),
    ('assets/xyz_gizmo.png', 'assets'),
    ('assets/dropdown_arrow.png', 'assets'),
    ('assets/icon.ico', 'assets'),
]

for src_path, dst_path in splash_image_paths:
    full_path = project_root / src_path
    if full_path.exists():
        print(f"[PyInstaller] [OK] Adding to bundle: {src_path}")
        datas.append((src_path, dst_path))
    else:
        print(f"[PyInstaller] [X] NOT found: {full_path}")

print(f"[PyInstaller] Final datas list has {len(datas)} items")

# Collect casadi DLLs for Windows
binaries_list = []
try:
    import site
    import casadi
    casadi_path = Path(casadi.__file__).parent if hasattr(casadi, '__file__') else None
    if casadi_path and casadi_path.exists():
        # Collect all DLL files from casadi directory
        dll_files = list(casadi_path.glob('*.dll'))
        for dll_file in dll_files:
            binaries_list.append((str(dll_file), 'casadi'))
        print(f"[PyInstaller] Found {len(dll_files)} casadi DLL files to bundle")
except Exception as e:
    print(f"[PyInstaller] Warning: Could not collect casadi DLLs: {e}")
    print("[PyInstaller] casadi DLLs may need to be manually added")

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries_list,
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
        # cadquery and dependencies
        'cadquery',
        'casadi',
        'casadi._casadi',
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
        'core.procedural_textures',
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
    noarchive=True,  # Faster imports - files extracted individually instead of from archive
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ECTOFORM',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,  # Disable stripping to prevent DLL loading issues
    upx=False,  # Disable UPX compression - decompression adds startup time and can corrupt DLLs
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Windowed app, no console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_root / 'assets' / 'icon.ico') if (project_root / 'assets' / 'icon.ico').exists() else None,
    version_file=None,
)

# Debug icon file
icon_path = project_root / 'assets' / 'icon.ico'
if icon_path.exists():
    print(f"[PyInstaller] [OK] Icon file found: {icon_path}")
    print(f"[PyInstaller] Icon will be used for EXE")
else:
    print(f"[PyInstaller] [X] Icon file NOT found: {icon_path}")
    print(f"[PyInstaller] App will use default Windows icon")

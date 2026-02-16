"""
Main entry point for the ECTOFORM application.
"""
import sys
import logging
import os
from pathlib import Path

# Set OpenGL environment variables for macOS compatibility
# These help with PyVista/VTK rendering issues on macOS
os.environ.setdefault('MESA_GL_VERSION_OVERRIDE', '3.3')
os.environ.setdefault('VTK_USE_OSMESA', '0')  # Try hardware rendering first
# Windows: VTK MSAA can conflict with Qt format and cause black screen on resize/maximize
if sys.platform == 'win32':
    os.environ.setdefault('VTK_FORCE_MSAA', '0')
# Uncomment below if hardware rendering fails:
# os.environ['VTK_USE_OSMESA'] = '1'  # Force software rendering

# Configure logging FIRST, before any other imports
log_file = os.path.join(os.path.dirname(__file__), 'app_debug.log')
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ],
    force=True  # Override any existing configuration
)

logger = logging.getLogger(__name__)


def safe_flush(stream):
    """Safely flush a stream, handling None (common in PyInstaller Windows builds)."""
    if stream is not None:
        try:
            stream.flush()
        except (AttributeError, OSError):
            pass  # Stream may not support flush or may be closed


# Print immediately to stdout (before Qt might interfere)
print("=" * 50, file=sys.stderr)
print("ECTOFORM: Starting application...", file=sys.stderr)
print(f"Log file: {log_file}", file=sys.stderr)
print("=" * 50, file=sys.stderr)
safe_flush(sys.stderr)

from PyQt5.QtWidgets import QApplication, QMessageBox, QDialog, QSplashScreen
from PyQt5.QtCore import QTimer, Qt as QtCore, Qt
from PyQt5.QtGui import QPixmap, QColor
from stl_viewer import STLViewerWindow
from core.license_validator import is_license_valid_stored
from ui.license_dialog import LicenseDialog
from ui.styles import get_global_stylesheet


def main():
    """Initialize and run the ECTOFORM application."""
    print("=" * 50, file=sys.stderr)
    print("Starting ECTOFORM Application", file=sys.stderr)
    print("=" * 50, file=sys.stderr)
    safe_flush(sys.stderr)
    
    logger.info("=" * 50)
    logger.info("Starting ECTOFORM Application")
    logger.info(f"Platform: {sys.platform}, Python: {sys.version.split()[0]}")
    logger.info(f"App log file: {log_file}")
    logger.info("=" * 50)
    
    try:
        # Request multi-sampling for OpenGL on Windows (improves 3D rendering quality)
        # Use 4x MSAA - 8x can cause framebuffer reallocation issues on resize/maximize (black screen)
        if sys.platform == 'win32':
            from PyQt5.QtGui import QSurfaceFormat
            fmt = QSurfaceFormat()
            fmt.setSamples(4)
            QSurfaceFormat.setDefaultFormat(fmt)
        print("Step 1: Creating QApplication...", file=sys.stderr)
        safe_flush(sys.stderr)
        logger.info("Step 1: Creating QApplication...")
        app = QApplication(sys.argv)
        print("✓ QApplication created successfully", file=sys.stderr)
        safe_flush(sys.stderr)
        logger.info("✓ QApplication created successfully")
        
        # Set app icon for all windows (removes Windows '?' placeholder in title bars)
        from ui.annotation_icon import get_app_window_icon
        app_icon = get_app_window_icon()
        if not app_icon.isNull():
            app.setWindowIcon(app_icon)
        
        # Apply global stylesheet early to ensure QMessageBox dialogs are styled
        app.setStyleSheet(get_global_stylesheet())
        print("✓ Global stylesheet applied", file=sys.stderr)
        safe_flush(sys.stderr)
        logger.info("✓ Global stylesheet applied")
        
        print("Step 2: Setting application properties...", file=sys.stderr)
        safe_flush(sys.stderr)
        logger.info("Step 2: Setting application properties...")
        app.setApplicationName("ECTOFORM")
        app.setOrganizationName("ECTOFORM")
        print("✓ Application properties set", file=sys.stderr)
        safe_flush(sys.stderr)
        logger.info("✓ Application properties set")
        
        # Create splash screen
        splash_pixmap = None
        
        # Try to load splash screen image
        if getattr(sys, 'frozen', False):
            # PyInstaller bundle
            base_path = Path(sys._MEIPASS)
        else:
            # Development mode
            base_path = Path(__file__).parent
        
        splash_image_paths = [
            base_path / 'assets' / 'splash.png',
            base_path / 'assets' / 'splash.jpg',
            base_path / 'assets' / 'logo.png',
            base_path / 'assets' / 'logo.jpg',
        ]
        
        for img_path in splash_image_paths:
            if img_path.exists():
                splash_pixmap = QPixmap(str(img_path))
                if not splash_pixmap.isNull():
                    # Scale if too large
                    if splash_pixmap.width() > 800 or splash_pixmap.height() > 600:
                        splash_pixmap = splash_pixmap.scaled(800, 600, QtCore.KeepAspectRatio, QtCore.SmoothTransformation)
                    break
        
        # Create default splash if image not found
        if splash_pixmap is None or splash_pixmap.isNull():
            splash_pixmap = QPixmap(600, 450)
            splash_pixmap.fill(QColor("#F8FAFC"))
        
        splash = QSplashScreen(splash_pixmap, QtCore.WindowStaysOnTopHint)
        splash.setStyleSheet("""
            QSplashScreen {
                background-color: #F8FAFC;
                color: #1E293B;
                font-size: 14px;
                font-weight: 500;
            }
        """)
        
        splash.showMessage("Loading ECTOFORM...", 
                          QtCore.AlignCenter | QtCore.AlignBottom, 
                          QColor("#5294E2"))
        splash.show()
        app.processEvents()
        
        # Step 2.5: Check license
        print("Step 2.5: Checking license...", file=sys.stderr)
        safe_flush(sys.stderr)
        logger.info("Step 2.5: Checking license...")
        
        if not is_license_valid_stored():
            splash.showMessage("License validation required...", 
                              QtCore.AlignCenter | QtCore.AlignBottom, 
                              QColor("#5294E2"))
            app.processEvents()
            
            print("License not valid, showing license dialog...", file=sys.stderr)
            safe_flush(sys.stderr)
            logger.info("License not valid, showing license dialog...")
            
            # Temporarily remove WindowStaysOnTopHint from splash so license dialog appears on top
            # Store original flags
            original_flags = splash.windowFlags()
            # Remove WindowStaysOnTopHint
            splash.setWindowFlags(splash.windowFlags() & ~Qt.WindowStaysOnTopHint)
            splash.show()  # Re-show with new flags
            app.processEvents()
            
            # Create and show license dialog (it will appear on top now)
            license_dialog = LicenseDialog()
            license_dialog.setWindowFlags(license_dialog.windowFlags() | Qt.WindowStaysOnTopHint)
            license_dialog.raise_()
            license_dialog.activateWindow()
            
            if license_dialog.exec() != QDialog.Accepted:
                # Restore splash flags before exiting
                splash.setWindowFlags(original_flags)
                splash.show()
                app.processEvents()
                print("License dialog cancelled, exiting application", file=sys.stderr)
                safe_flush(sys.stderr)
                logger.info("License dialog cancelled, exiting application")
                splash.finish(None)
                QMessageBox.information(
                    None,
                    "License Required",
                    "A valid license key is required to use this application.\n"
                    "The application will now exit."
                )
                return 0  # Exit application
            
            # Restore splash window flags to keep it on top again
            splash.setWindowFlags(original_flags)
            splash.show()
            app.processEvents()
            
            splash.showMessage("License validated. Starting application...", 
                              QtCore.AlignCenter | QtCore.AlignBottom, 
                              QColor("#5294E2"))
            app.processEvents()
            
            print("✓ License validated successfully", file=sys.stderr)
            safe_flush(sys.stderr)
            logger.info("✓ License validated successfully")
        else:
            print("✓ Valid license found in cache", file=sys.stderr)
            safe_flush(sys.stderr)
            logger.info("✓ Valid license found in cache")
        
        splash.showMessage("Loading application...", 
                          QtCore.AlignCenter | QtCore.AlignBottom, 
                          QColor("#5294E2"))
        app.processEvents()
        
        print("Step 3: Creating main window...", file=sys.stderr)
        safe_flush(sys.stderr)
        logger.info("Step 3: Creating main window...")
        window = STLViewerWindow()
        print("✓ Main window created successfully", file=sys.stderr)
        safe_flush(sys.stderr)
        logger.info("✓ Main window created successfully")
        
        print("Step 4: Showing window...", file=sys.stderr)
        safe_flush(sys.stderr)
        logger.info("Step 4: Showing window...")
        window.show()
        
        # Process events to ensure window renders before QtInteractor initialization
        app.processEvents()
        
        # Ensure window is raised and activated (especially important on macOS)
        window.raise_()
        window.activateWindow()
        app.processEvents()
        
        print(f"✓ Window shown - Position: {window.pos()}, Size: {window.size()}, Visible: {window.isVisible()}", file=sys.stderr)
        safe_flush(sys.stderr)
        logger.info(f"✓ Window shown - Position: {window.pos()}, Size: {window.size()}, Visible: {window.isVisible()}")
        
        # Give QtInteractor time to initialize (it will be triggered by showEvent)
        app.processEvents()
        
        # Finish splash screen
        splash.finish(window)
        
        print("Step 5: Starting event loop...", file=sys.stderr)
        safe_flush(sys.stderr)
        logger.info("Step 5: Starting event loop...")
        # Run application event loop
        sys.exit(app.exec())
    except Exception as e:
        print(f"FATAL ERROR: {e}", file=sys.stderr)
        safe_flush(sys.stderr)
        logger.error(f"Fatal error in main: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()

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

from PyQt5.QtWidgets import QApplication, QDialog, QSplashScreen
from PyQt5.QtCore import QTimer, Qt as QtCore, Qt
from PyQt5.QtGui import QPixmap, QColor
from stl_viewer import STLViewerWindow, USE_PYGFX
from core.license_validator import is_license_valid_stored
from ui.license_dialog import LicenseDialog
from ui.styles import get_global_stylesheet
from ui.modal_utils import show_message_dialog


def _parse_screenshot_mode_args(argv):
    """Return (enabled: bool, outdir: str) parsed from sys.argv."""
    enabled = "--screenshot-mode" in argv
    outdir = "screenshots"
    if "--screenshot-outdir" in argv:
        idx = argv.index("--screenshot-outdir")
        if idx + 1 < len(argv):
            outdir = argv[idx + 1]
    return enabled, outdir


def _pump_events(app, ms=400, step=50):
    """Process the Qt event loop for `ms` milliseconds so async paints
    (e.g. the pygfx canvas's deferred QTimer.singleShot(100, ...) init in
    viewer_widget_pygfx.py) have a chance to complete before .grab()."""
    import time
    elapsed = 0
    while elapsed < ms:
        app.processEvents()
        time.sleep(step / 1000.0)
        elapsed += step
    app.processEvents()


def run_screenshot_mode(app, window, outdir):
    """Walk SCREENSHOT_TARGETS, grab() each state, save as PNG, then return.
    Each target is isolated in its own try/except so one failure doesn't
    abort the remaining captures."""
    os.makedirs(outdir, exist_ok=True)

    def _capture(name):
        _pump_events(app)
        pixmap = window.grab()
        path = os.path.join(outdir, f"{name}.png")
        ok = pixmap.save(path)
        logger.info(f"screenshot-mode: saved {path} ({'ok' if ok else 'FAILED'})")

    def _load_sample_model(win):
        """Load the bundled sample STL into the current tab so the 3D
        viewport has real rendered geometry instead of the empty
        drag-and-drop state. Idempotent — safe to call more than once."""
        sample_stl = Path(__file__).parent / "test.stl"
        if sample_stl.exists():
            win._load_file_into_current_tab(str(sample_stl))
            _pump_events(app)

    def _view_3d_with_model(win):
        win._switch_mode("3d")
        _load_sample_model(win)

    # A maximized capture window (e.g. 1920x1050) is wide/tall enough that the
    # toolbar and sidebar don't overflow, so there'd be nothing to scroll to.
    # Shrink to a common laptop-ish size for the two "scrolled" targets below
    # to reliably reproduce the overflow, then restore it for every target
    # after (_restore_window_size, wired into 02_technical_overview).
    _original_size = window.size()
    _SMALL_SIZE = (1280, 800)

    def _toolbar_scrolled(win):
        # The top toolbar overflows and scrolls horizontally
        # (ui/toolbar.py's self.toolbar_scroll, a QScrollArea) — scroll it
        # all the way right so icons past the fold (Fullscreen, folder,
        # refresh, etc.) are visible too.
        win._switch_mode("3d")
        _load_sample_model(win)
        win.resize(*_SMALL_SIZE)
        _pump_events(app)
        hbar = win.toolbar.toolbar_scroll.horizontalScrollBar()
        hbar.setValue(hbar.maximum())

    def _sidebar_scrolled(win):
        # The left sidebar (Dimensions/Weight/Surface Area/Export) is inside
        # a QScrollArea (ui/sidebar_panel.py, objectName "sidebarScrollArea")
        # taller than the viewport — scroll it to the bottom so the Export
        # section is visible too.
        from PyQt5.QtWidgets import QScrollArea
        win._switch_mode("3d")
        _load_sample_model(win)
        win.resize(*_SMALL_SIZE)
        _pump_events(app)
        scroll = win.sidebar_panel.findChild(QScrollArea, "sidebarScrollArea")
        if scroll is not None:
            vbar = scroll.verticalScrollBar()
            vbar.setValue(vbar.maximum())

    def _restore_window_size(win):
        win.resize(_original_size)
        _pump_events(app)

    def _enable_screenshot_panel(win):
        # The screenshot side panel only lives inside the 3D Viewer workspace —
        # switch there first or the toggle has nothing visible to attach to.
        win._switch_mode("3d")
        # enable_screenshot_mode() (viewer_widget_pygfx.py) requires a loaded
        # model and silently no-ops on an empty viewport — load the bundled
        # sample STL first so the panel actually has something to show.
        _load_sample_model(win)
        win.toolbar.screenshot_mode_enabled = True
        win._toggle_screenshot_mode()

    # "The Project" mode has its own sidebar with 14 sub-screens (ui/project_widget.py's
    # TheProjectWidget). Capture each one individually via project_widget._nav.select(key) —
    # confirmed to work against a fresh/blank project with no login gate or data requirement.
    PROJECT_SECTIONS = [
        "brief", "assignment", "timeline", "validation", "quality_control", "report",
        "estimated_cost", "files", "rd", "prototype", "version_comparison",
        "traceability", "todo", "glossary",
    ]

    def _project_section(key):
        def _go(win):
            win._switch_mode("project")
            win.project_widget._nav.select(key)
        return _go

    def _rd_sub_tab(idx):
        def _go(win):
            win._switch_mode("project")
            win.project_widget._nav.select("rd")
            win.project_widget._screen_widgets["rd"].switch_tab(idx)
        return _go

    def _seed_project_data(win):
        """Populate each Project sidebar section with representative sample
        data via each widget's own set_data(dict) API (the same schema used
        for save/load), so screenshots show real content instead of blank
        forms. Each section is isolated in its own try/except — a schema
        mismatch in one section just leaves it blank, same as before,
        rather than aborting the whole run."""
        assets = Path(__file__).parent / "assets"
        img_blue = str(assets / "color_blue.jpg")
        img_green = str(assets / "color_green.jpg")
        metal = str(assets / "brushed_metal.jpg")

        pw = win.project_widget
        win._switch_mode("project")

        def _seed(key, fn):
            try:
                pw._nav.select(key)  # lazily instantiates the section widget
                _pump_events(app, ms=100)
                widget = pw._screen_widgets.get(key)
                if widget is not None:
                    fn(widget)
                    _pump_events(app, ms=100)
            except Exception as e:
                logger.warning(f"screenshot-mode: seed '{key}' failed: {e}")

        _seed("brief", lambda w: w.update_project_info({
            "title": "LYNS Sample Ring", "number": "LYNS-2026-001",
            "photo_path": img_blue,
        }) if hasattr(w, "update_project_info") else None)

        # AreaCard.x/.y are absolute pixel coordinates on the canvas (not
        # fractions) — A4 portrait area is 560x793, card size is 148x88
        # (ui/assignment_widget.py _A4_W_PORTRAIT/_CARD_W constants).
        _seed("assignment", lambda w: w.set_data({
            "cards": [
                {"id": "c1", "title": "Body", "supplier": "Acme Casting", "status": "In progress",
                 "number": 1, "x": 150, "y": 180, "color": "#3b82f6", "arrows": []},
                {"id": "c2", "title": "Setting", "supplier": "Precision Stones", "status": "Done",
                 "number": 2, "x": 260, "y": 420, "color": "#22c55e", "arrows": []},
            ],
            "image_name": "test.stl", "image_path": "",
            "orientation": "portrait", "font_family": "Arial", "font_size": 10,
        }))

        def _seed_timeline(w):
            # sample_data() returns real Operator/Operation/Task dataclass
            # instances (the widget's own demo-data generator); set_data()
            # expects plain dicts (the get_data()/save-load schema) — convert
            # using the exact same shape TimelineWidget.get_data() produces.
            from ui.timeline.models import sample_data
            def _task_d(t):
                return {
                    'id': t.id, 'name': t.name,
                    'start': t.start.toString('yyyy-MM-dd'),
                    'end': t.end.toString('yyyy-MM-dd'),
                    'task_type': t.task_type, 'is_urgent': t.is_urgent,
                    'status': t.status, 'comments': t.comments,
                    'project_manager': t.project_manager,
                    'technical_manager': t.technical_manager,
                    'contributors': t.contributors,
                }
            def _op_d(o):
                return {'id': o.id, 'name': o.name, 'tasks': [_task_d(t) for t in o.tasks]}
            def _operator_d(op):
                return {'id': op.id, 'name': op.name, 'operations': [_op_d(o) for o in op.operations]}
            w.set_data({'operators': [_operator_d(op) for op in sample_data()]})
        _seed("timeline", _seed_timeline)

        _seed("validation", lambda w: w.set_data({
            "sessions": [{
                "id": 1, "date": "2026-07-20",
                "stakeholders": [{"id": 1, "name": "Client Co.", "role": "Client"}],
                "modifications": [], "action_plan": [],
                "ceo_feedback": "Looks great, proceed.",
                "risks": "None identified.",
            }],
        }))

        def _seed_report(w):
            # _default_report() returns a real Report dataclass instance, not
            # the dict shape set_data() parses — assign directly and replicate
            # set_data()'s own post-assignment refresh calls.
            # NOTE: the Project sidebar's "report" section imports ReportWidget
            # from the ui/report package (ui/project_widget.py:194), not the
            # separate legacy ui/report_widget.py module — its Report dataclass
            # is structurally different (has project_photo_path etc.).
            from ui.report.models import _default_report
            w._reports = [_default_report(1)]
            w._rebuild_all()
            w._switch_report(0)
        _seed("report", _seed_report)

        _seed("quality_control", lambda w: w.set_data({
            "inspection_date": "2026-07-20", "inspected_by": "QC Team",
            "comments": "All checks passed within tolerance.",
            "inspection_images": [], "image_annotations": [], "logo_data": "",
            "designation": "LYNS Ring Batch 1", "reference_number": "QC-2026-001",
            "manufacturer": "Acme Casting", "inspection_due_date": "2026-08-01",
            "overall_status": "approved", "waived_by": "",
            "control_points": [
                {"id": 1, "name": "Diameter", "status": "ok", "comment": "Within spec",
                 "annotation_id": None, "color": "#22c55e"},
                {"id": 2, "name": "Surface finish", "status": "ok", "comment": "Smooth",
                 "annotation_id": None, "color": "#22c55e"},
                {"id": 3, "name": "Weight", "status": "to_check", "comment": "",
                 "annotation_id": None, "color": "#f59e0b"},
            ],
        }))

        _seed("estimated_cost", lambda w: w.set_data({
            "currency": "EUR",
            "trades": [{"id": 1, "name": "Casting", "partners": [
                {"id": 1, "name": "Acme Casting", "activity": "Casting",
                 "start_date": "2026-07-01", "delivery_date": "2026-07-10",
                 "is_best": True, "tax_rate": 20.0, "tasks": [
                     {"component": "Body", "task": "Cast", "hours": 4.0, "hourly_rate": 35.0},
                 ]},
            ]}],
        }))

        def _seed_files(w):
            import base64
            sample_path = Path(__file__).parent / "test.stl"
            if not sample_path.exists():
                return
            data_b64 = base64.b64encode(sample_path.read_bytes()).decode("ascii")
            w.set_data({
                "next_folder_id": 1, "next_file_id": 2, "folders": [],
                "files": [{
                    "id": 1, "name": "test.stl", "folder_id": None,
                    "status": "In progress", "trashed": False,
                    "versions": [{
                        "version_str": "v1.0", "original_filename": "test.stl",
                        "uploaded_at": "20/07/2026 10:00",
                        "size_bytes": sample_path.stat().st_size,
                        "file_data_b64": data_b64,
                    }],
                }],
            })
        _seed("files", _seed_files)

        _seed("rd", lambda w: w.set_data({"components": [{
            "id": "c1", "name": "Body", "supplier": "Acme", "color": "#3b82f6",
            "brief": {"objective": "Durable finish", "constraints": "Budget-friendly",
                      "budget_min": 5.0, "budget_max": 20.0, "quantity": 100,
                      "quantity_unit": "pcs", "notes": []},
            "proposals": [
                {"id": "p1", "name": "Blue anodized", "category": "Metal", "treatment": "Anodizing",
                 "origin": "EU", "supplier": "Acme", "status": "selected",
                 "image_path": img_blue, "notes": "Preferred"},
                {"id": "p2", "name": "Green anodized", "category": "Metal", "treatment": "Anodizing",
                 "origin": "EU", "supplier": "Acme", "status": "in_evaluation",
                 "image_path": img_green, "notes": ""},
            ],
            "technique_proposals": [
                {"id": "t1", "name": "CNC Machining", "process_type": "Subtractive",
                 "equipment": "5-axis CNC", "parameters": "1000 RPM", "lead_time": "3 days",
                 "complexity": "Medium", "supplier": "Acme", "notes": "",
                 "status": "selected", "image_path": metal},
            ],
        }]}))

        _seed("prototype", lambda w: w.set_data({
            "versions": [
                {"id": "v1", "version_number": 1, "date": "2026-07-01", "status": "in_progress",
                 "comments": "First iteration", "image_paths": [img_blue], "file_paths": []},
                {"id": "v2", "version_number": 2, "date": "2026-07-15", "status": "approved",
                 "comments": "Final adjustments made", "image_paths": [img_green], "file_paths": []},
            ],
            "next_number": 3,
        }))

        _seed("version_comparison", lambda w: w.set_data({
            "next_id": 3,
            "cards": [
                {"id": 1, "star_number": 1, "photo_paths": [img_blue], "version": "v1.0",
                 "positive_points": "Good fit", "negative_points": "Finish too dull",
                 "comments": "", "cost": "120"},
                {"id": 2, "star_number": 2, "photo_paths": [img_green], "version": "v2.0",
                 "positive_points": "Improved finish", "negative_points": "",
                 "comments": "Client favorite", "cost": "135"},
            ],
        }))

        _seed("traceability", lambda w: w.set_data({
            "version": 3,
            # TraceComponent.id must be an int — the widget does
            # max(c.id for c in components) + 1 arithmetic on it internally
            # (ui/traceability/widget.py's update_components_from_brief).
            "components": [{"id": 1, "name": "Body", "image_path": img_blue, "is_main": True,
                             "stages": []}],
        }))

        _seed("todo", lambda w: w.set_data({"tasks": [
            {"id": "t1", "title": "Confirm supplier quote", "date": "2026-07-26", "time": "10:00",
             "reminder": 30, "done": False, "notes": "", "priority": "high"},
            {"id": "t2", "title": "Review QC report", "date": "2026-07-28", "time": "",
             "reminder": 0, "done": True, "notes": "Completed early", "priority": "medium"},
        ]}))

        _seed("glossary", lambda w: w.set_data({"next_id": 3, "terms": [
            {"id": 1, "term": "Casting", "definition": "Process of pouring molten metal into a mold."},
            {"id": 2, "term": "Anodizing", "definition": "Electrochemical process that increases corrosion resistance."},
        ]}))

    _NATIVE_DIALOG_TARGET = "99_save_project_as_dialog"

    def _save_as_native_dialog(win):
        """Trigger the OS-native "Save Project As" file dialog, screen-grab
        it, then dismiss it with a synthetic Escape keypress.

        Unlike every other target above, this dialog is a real Windows
        window, not part of our own Qt widget tree, so window.grab() can't
        see it — a full-screen grab is the only way to capture it. And
        QFileDialog.getSaveFileName() blocks the calling thread until the
        dialog closes, so the grab + dismiss must be scheduled on a timer
        *before* making the call, timed for after the dialog has had a
        moment to actually paint. Escape is the OS's own universal cancel
        for this dialog, so dismissal doesn't depend on window titles or
        locale (the dialog title is translated; the Escape key isn't).
        Windows-only — there's no native-dialog quirk to check on
        macOS/Linux, and keybd_event doesn't exist there anyway.

        A failed auto-dismiss would hang this call — and therefore the rest
        of the capture run — rather than merely failing this one
        screenshot, so this target MUST stay last in SCREENSHOT_TARGETS:
        every capture before it is already saved to disk, and the "Run app
        in screenshot mode" step's own timeout plus the upload step's
        `if: always()` mean a hang here still ships every other screenshot
        instead of losing the whole run.
        """
        if sys.platform != 'win32':
            return
        import ctypes

        path = os.path.join(outdir, f"{_NATIVE_DIALOG_TARGET}.png")

        def _snap_and_dismiss():
            try:
                pix = app.primaryScreen().grabWindow(0)
                ok = pix.save(path)
                logger.info(f"screenshot-mode: saved {path} (native dialog, {'ok' if ok else 'FAILED'})")
            except Exception as e:
                logger.error(f"screenshot-mode: native dialog capture failed: {e}")
            finally:
                user32 = ctypes.windll.user32
                VK_ESCAPE, KEYEVENTF_KEYUP = 0x1B, 0x0002
                user32.keybd_event(VK_ESCAPE, 0, 0, 0)
                user32.keybd_event(VK_ESCAPE, 0, KEYEVENTF_KEYUP, 0)

        win._switch_mode("project")
        QTimer.singleShot(700, _snap_and_dismiss)
        win.project_widget._on_save_project_as()  # blocks until Escape lands

    SCREENSHOT_TARGETS = {
        "01_3d_viewer":            lambda win: win._switch_mode("3d"),
        "01b_3d_viewer_with_model": _view_3d_with_model,
        "01c_3d_viewer_toolbar_scrolled": _toolbar_scrolled,
        "01d_3d_viewer_sidebar_scrolled": _sidebar_scrolled,
        "02_technical_overview": lambda win: (_restore_window_size(win), win._switch_mode("technical")),
        "03_drawing_scale":      lambda win: win._switch_mode("scale"),
        "05_help":               lambda win: win._switch_mode("help"),
        "06_screenshot_panel":   _enable_screenshot_panel,
    }
    # Insert one target per Project sidebar section: 04_project_<key>.
    # "rd" is captured here first, in its fresh/default tab state — the two
    # explicit sub-tab targets below run afterward and deliberately force
    # each state (RdWidget's internal tab selection persists across
    # _nav.select() calls, so forcing them first would leak into this one).
    for _key in PROJECT_SECTIONS:
        SCREENSHOT_TARGETS[f"04_project_{_key}"] = _project_section(_key)
    SCREENSHOT_TARGETS["04_project_rd_0_textures"] = _rd_sub_tab(0)
    SCREENSHOT_TARGETS["04_project_rd_1_techniques"] = _rd_sub_tab(1)
    # Must be inserted last — see _save_as_native_dialog's docstring.
    SCREENSHOT_TARGETS[_NATIVE_DIALOG_TARGET] = _save_as_native_dialog

    print("screenshot-mode: seeding Project sections with sample data...", file=sys.stderr)
    safe_flush(sys.stderr)
    try:
        _seed_project_data(window)
    except Exception as e:
        print(f"screenshot-mode: seeding failed (non-fatal): {e}", file=sys.stderr)
        safe_flush(sys.stderr)
        logger.error("screenshot-mode: seeding failed", exc_info=True)

    print(f"screenshot-mode: capturing {len(SCREENSHOT_TARGETS)} UI states to '{outdir}'...",
          file=sys.stderr)
    safe_flush(sys.stderr)
    logger.info(f"screenshot-mode: capturing {len(SCREENSHOT_TARGETS)} targets to {outdir}")

    for name, action in SCREENSHOT_TARGETS.items():
        try:
            action(window)
            # _save_as_native_dialog captures itself (a full-screen grab
            # while the native dialog is up) — window.grab() here would
            # just overwrite that with a shot of the app after the dialog
            # already closed.
            if name != _NATIVE_DIALOG_TARGET:
                _capture(name)
        except Exception as e:
            print(f"screenshot-mode: target '{name}' FAILED: {e}", file=sys.stderr)
            safe_flush(sys.stderr)
            logger.error(f"screenshot-mode: target '{name}' failed", exc_info=True)

    print(f"✓ screenshot-mode complete — output in '{outdir}'", file=sys.stderr)
    safe_flush(sys.stderr)
    logger.info("screenshot-mode: complete")


def main():
    """Initialize and run the ECTOFORM application."""
    print("=" * 50, file=sys.stderr)
    print("Starting ECTOFORM Application", file=sys.stderr)
    print("=" * 50, file=sys.stderr)
    safe_flush(sys.stderr)
    
    logger.info("=" * 50)
    logger.info("Starting ECTOFORM Application")
    logger.info(f"Platform: {sys.platform}, Python: {sys.version.split()[0]}")
    logger.info(f"parts_debug: USE_PYGFX={USE_PYGFX} (pygfx=WebGPU viewer, False=PyVista viewer)")
    logger.info(f"App log file: {log_file}")
    logger.info("=" * 50)
    
    try:
        # Windows: OpenGL setup before QApplication (no env vars required for exe)
        if sys.platform == 'win32':
            from PyQt5.QtGui import QSurfaceFormat
            fmt = QSurfaceFormat()
            fmt.setSamples(0)
            QSurfaceFormat.setDefaultFormat(fmt)
        # Windows: pre-initialize VTK only when using PyVista (pygfx uses WebGPU, no VTK)
        if sys.platform == 'win32' and not USE_PYGFX:
            try:
                import pyvista as pv
                _preinit = pv.Plotter()
                _preinit.close()
                logger.info("VTK pre-initialized (PyVista fallback)")
            except Exception as e:
                logger.debug(f"VTK pre-init skipped: {e}")
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
        app.setApplicationName("LYNS360")
        app.setOrganizationName("LYNS360")
        print("✓ Application properties set", file=sys.stderr)
        safe_flush(sys.stderr)
        logger.info("✓ Application properties set")

        # Windows only, no-op in dev mode — registers .lyns.pjt with File
        # Explorer so project files show the app's icon instead of a blank
        # generic one. Self-registering since there's no installer step.
        from core.file_association import register_file_association
        register_file_association()
        
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
            splash_pixmap.fill(QColor("#22262c"))
        
        splash = QSplashScreen(splash_pixmap, QtCore.WindowStaysOnTopHint)
        splash.setStyleSheet("""
            QSplashScreen {
                background-color: #22262c;
                color: #E0ECF4;
                font-size: 14px;
                font-weight: 500;
            }
        """)
        
        splash.showMessage("Loading LYNS360...",
                          QtCore.AlignCenter | QtCore.AlignBottom, 
                          QColor("#5294E2"))
        splash.show()
        app.processEvents()
        
        # Step 2.5: Check license
        print("Step 2.5: Checking license...", file=sys.stderr)
        safe_flush(sys.stderr)
        logger.info("Step 2.5: Checking license...")
        
        # License validation skipped per user request
        if False:  # is_license_valid_stored():
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
                show_message_dialog(
                    None,
                    "Subscription Required",
                    "An active commercial subscription is required to use this application.\n"
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
        # Log VTK/PyVista versions (vtk>=9.1 recommended for Windows resize fixes)
        try:
            import vtk
            import pyvista as pv
            logger.info(f"VTK: {vtk.vtkVersion.GetVTKVersion()}, PyVista: {pv.__version__}")
        except Exception as e:
            logger.debug(f"Could not log VTK/PyVista versions: {e}")
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

        # --- Hidden screenshot-mode: capture UI states and exit (no event loop) ---
        screenshot_mode, screenshot_outdir = _parse_screenshot_mode_args(sys.argv)
        if screenshot_mode:
            splash.close()
            run_screenshot_mode(app, window, screenshot_outdir)
            return 0

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

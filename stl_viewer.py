"""
Main ECTOFORM Window with minimalistic UI and multi-tab support.
"""
import os
import sys
import uuid
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Any
from pathlib import Path
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QFileDialog,
    QSplitter, QFrame, QApplication, QStackedWidget, QTabBar,
    QPushButton, QLabel, QMenu
)
from ui.modal_utils import (
    show_message_dialog, show_warning_dialog, show_error_dialog,
    ask_yes_no_dialog, ask_yes_no_cancel_dialog
)
# Use native QFileDialog for file upload/save flows to preserve OS-native behavior.
# Backwards-compatible small shims so existing call sites keep working.
def get_open_file_name(parent, title: str, directory: str = "", filter: str = "All Files (*)"):
    return QFileDialog.getOpenFileName(parent, title, directory, filter)


def get_save_file_name(parent, title: str, directory: str = "", filter: str = "All Files (*)"):
    return QFileDialog.getSaveFileName(parent, title, directory, filter)
from PyQt5.QtCore import Qt, QEvent, QTimer, QThread, pyqtSignal, QSize

# Force PyInstaller to bundle pygfx and deps (imported lazily in viewer_widget_pygfx._init_pygfx)
try:
    import pygfx  # noqa: F401
    import wgpu  # noqa: F401
    import trimesh  # noqa: F401
    import rendercanvas  # noqa: F401
except ImportError:
    pass

# Always use pygfx (WebGPU) - no env vars. Fixes Windows black screen, works in exe.
# Fall back to PyVista only if pygfx import fails (e.g. missing wgpu/rendercanvas).
USE_PYGFX = False
USE_OFFSCREEN = False
try:
    from viewer_widget_pygfx import STLViewerWidget
    USE_PYGFX = True
except Exception as e:
    print(f"Warning: Could not import pygfx viewer: {e}, falling back to PyVista", file=sys.stderr)
    try:
        from viewer_widget import STLViewerWidget
    except Exception as e2:
        print(f"Warning: Could not import QtInteractor viewer, using offscreen fallback: {e2}", file=sys.stderr)
        from viewer_widget_offscreen import STLViewerWidgetOffscreen as STLViewerWidget
        USE_OFFSCREEN = True

from ui.sidebar_panel import SidebarPanel
from ui.toolbar import ViewControlsToolbar
from ui.ruler_toolbar import RulerToolbar
from ui.annotation_panel import AnnotationPanel, VALIDATED_COLOR, PENDING_COLOR
from ui.arrow_panel import ArrowPanel
from ui.parts_panel import PartsPanel
from ui.styles import get_global_stylesheet, default_theme
from core.mesh_calculator import MeshCalculator
from ui.screenshot_panel import ScreenshotPanel
from ui.texture_panel import TexturePanel
from ui.components import confirm_dialog
from ui.technical_overview import TechnicalOverviewWidget
from ui.technical_sidebar import TechnicalSidebar
from ui.scale_canvas import ScaleCanvas
from ui.scale_sidebar import ScaleSidebar
from ui.help_panel import HelpWidget
from ui.project_widget import TheProjectWidget
from ui.overview_widget import OverviewWidget
from ui.record_panel import RecordPanel
from i18n import t, set_language, get_language, on_language_changed
from core.edition import is_education, WATERMARK_TEXT

logger = logging.getLogger(__name__)

# QTabBar + QSS can still clip the first glyph on macOS; leading en spaces reserve real width.
_TAB_CAPTION_LEAD = "\u2002\u2002\u2002"


def _ecto_tab_caption(visible_name: str) -> str:
    """Tab strip label with left inset so the first character is not clipped."""
    if not visible_name or visible_name == "+":
        return visible_name
    return _TAB_CAPTION_LEAD + visible_name


def safe_flush(stream):
    """Safely flush a stream, handling None (common in PyInstaller Windows builds)."""
    if stream is not None:
        try:
            stream.flush()
        except (AttributeError, OSError):
            pass  # Stream may not support flush or may be closed


# Print to stderr for immediate visibility
def debug_print(msg):
    print(f"[DEBUG] {msg}", file=sys.stderr)
    safe_flush(sys.stderr)


# ======================== Tab State ========================

@dataclass
class TabState:
    """Holds all per-tab state: viewer, annotations, arrows, sidebar cache, mode flags."""
    file_path: Optional[str] = None
    viewer_widget: Any = None  # STLViewerWidget instance
    annotation_panel: Any = None  # AnnotationPanel instance
    arrow_panel: Any = None  # ArrowPanel instance
    parts_panel: Any = None  # PartsPanel instance
    sidebar_data: Optional[dict] = None  # cached mesh_data dict for sidebar
    mesh: Any = None  # current_mesh reference
    ruler_active: bool = False
    annotation_mode_active: bool = False
    arrow_mode_active: bool = False
    parts_mode_active: bool = False
    screenshot_mode_active: bool = False
    texture_mode_active: bool = False
    draw_mode_active: bool = False
    annotations_exported: bool = False
    ecto_temp_dir: Optional[str] = None
    filename: Optional[str] = None  # display name for tab
    loaded_via_conversion: bool = False  # True when file was loaded via Convert File flow
    is_2d_model: bool = False  # True when current model is 2D geometry
    thumbnail: Any = None  # QPixmap thumbnail for the Overview tab
    reader_mode: bool = False  # True when this tab's annotations are view-only (see _load_ecto_file)
    tab_id: Optional[str] = None  # stable identity across save/restore — see core/project_merge.py's viewer_tabs merger
    screenshots: list = field(default_factory=list)  # [(QPixmap, timestamp_str, id, note), ...] — screenshot_panel is one shared widget, swapped per tab on switch (see _save_current_tab_state / _on_tab_changed)


# ── Background thread: runs screencapture -i and emits result ─────────────────

class _ScreenshotThread(QThread):
    captured  = pyqtSignal(str)   # path to the saved PNG
    cancelled = pyqtSignal()

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self._path = path

    def run(self):
        import platform
        if platform.system() == 'Windows':
            self._run_windows()
        else:
            self._run_macos()

    def _run_macos(self):
        import subprocess, os
        result = subprocess.run(
            ['screencapture', '-i', self._path],
            capture_output=True,
        )
        if result.returncode == 0 and os.path.exists(self._path):
            self.captured.emit(self._path)
        else:
            self.cancelled.emit()

    def _run_windows(self):
        import os, time, ctypes
        # Clear clipboard so we can detect a new image being placed
        try:
            ctypes.windll.user32.OpenClipboard(0)
            ctypes.windll.user32.EmptyClipboard()
            ctypes.windll.user32.CloseClipboard()
        except Exception:
            pass
        # Open the built-in Windows Snip & Sketch overlay (Win 10 1809+)
        os.startfile('ms-screenclip:')
        # Poll for a new clipboard image (CF_DIB = 8), max 120 s
        for _ in range(240):
            time.sleep(0.5)
            try:
                ctypes.windll.user32.OpenClipboard(0)
                has_image = bool(ctypes.windll.user32.IsClipboardFormatAvailable(8))
                ctypes.windll.user32.CloseClipboard()
            except Exception:
                has_image = False
            if has_image:
                try:
                    from PIL import ImageGrab
                    img = ImageGrab.grabclipboard()
                    if img is not None:
                        img.save(self._path, 'PNG')
                        self.captured.emit(self._path)
                        return
                except Exception:
                    pass
        self.cancelled.emit()


# ── Tab bar that auto-sizes each tab to fit its text on any platform/DPI ─────

class _EctoTabBar(QTabBar):
    """QTabBar subclass whose tabSizeHint guarantees the full label is visible.

    Qt's QSS min-width is a hard minimum that clips text when the content area
    (min-width minus padding) is narrower than the text — especially on Windows
    where font metrics produce wider glyphs.  Overriding tabSizeHint() forces
    the size to be at least (text_width + padding + safety), so Qt never clips.
    """

    # Total horizontal padding (left+right) mirroring the QSS values:
    #   :first  → padding-left:14 + padding-right:14 = 28
    #   :last   → padding-left:12 + padding-right:12 = 24
    #   middle  → padding-left:28 + padding-right:14 = 42  (+2 for 1px borders)
    _PAD_FIRST  = 28
    _PAD_LAST   = 24
    _PAD_MIDDLE = 44
    _SAFETY     = 12  # extra pixels so the last character is never shaved off

    def tabSizeHint(self, index: int) -> QSize:
        sz   = super().tabSizeHint(index)
        n    = self.count()
        pad  = (self._PAD_FIRST  if index == 0 else
                self._PAD_LAST   if index == n - 1 else
                self._PAD_MIDDLE)
        needed = self.fontMetrics().horizontalAdvance(self.tabText(index)) + pad + self._SAFETY
        return QSize(max(sz.width(), needed), sz.height())


# ======================== Main Window ========================

class STLViewerWindow(QMainWindow):
    """Main window for STL file viewer application with multi-tab support."""
    
    def __init__(self):
        debug_print("STLViewerWindow: Initializing...")
        logger.info("STLViewerWindow: Initializing...")
        super().__init__()
        debug_print("STLViewerWindow: Parent initialized")
        logger.info("STLViewerWindow: Parent initialized")
        
        # Tab management
        self.tabs: List[TabState] = []
        self.current_tab_index: int = -1

        # Mirrors project_widget's read-only state (see
        # ui.project_widget.TheProjectWidget.read_only_changed) — set True
        # while someone else's lock is active/took over.
        self._read_only = False

        # Desktop snip state
        self._snip_thread  = None
        self._snip_trigger = None   # floating "Snip" button shown while in screenshot mode

        self.init_ui()
        debug_print("STLViewerWindow: Initialization complete")
        logger.info("STLViewerWindow: Initialization complete")
    
    # ---- helpers to access current tab ----
    
    @property
    def _current_tab(self) -> Optional[TabState]:
        if 0 <= self.current_tab_index < len(self.tabs):
            return self.tabs[self.current_tab_index]
        return None

    @property
    def viewer_widget(self):
        tab = self._current_tab
        return tab.viewer_widget if tab else None

    @property
    def annotation_panel(self):
        tab = self._current_tab
        return tab.annotation_panel if tab else None

    def _ensure_texture_panel_ready(self):
        panel = getattr(self, 'texture_panel', None)
        if panel and hasattr(panel, 'prepare_for_show'):
            panel.prepare_for_show()

    @property
    def _annotations_exported(self):
        tab = self._current_tab
        return tab.annotations_exported if tab else False

    @_annotations_exported.setter
    def _annotations_exported(self, value):
        tab = self._current_tab
        if tab:
            tab.annotations_exported = value

    def init_ui(self):
        """Initialize the user interface."""
        logger.info("init_ui: Starting UI initialization...")
        
        logger.info("init_ui: Setting window title and size...")
        _title = "LYNS — Education" if is_education() else "LYNS"
        self.setWindowTitle(_title)
        if sys.platform == 'win32':
            min_w, min_h = 900, 600
        else:
            min_w, min_h = 900, 600
        self.setMinimumSize(min_w, min_h)
        from ui.annotation_icon import get_app_window_icon
        icon = get_app_window_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)
        # macOS: true fullscreen hides the Dock; Windows: maximized keeps taskbar
        if sys.platform == 'darwin':
            self.showFullScreen()
        else:
            self.showMaximized()
        
        logger.info("init_ui: Creating central widget...")
        central_widget = QWidget()
        central_widget.setStyleSheet(f"background-color: {default_theme.background};")
        self.setCentralWidget(central_widget)
        
        logger.info("init_ui: Creating main layout...")
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        
        # ---- Education watermark banner (top) ----
        if is_education():
            self._edu_top_banner = QLabel(WATERMARK_TEXT)
            self._edu_top_banner.setAlignment(Qt.AlignCenter)
            self._edu_top_banner.setFixedHeight(28)
            self._edu_top_banner.setStyleSheet(
                "background-color: #B91C1C; color: #ffffff; font-size: 11px; "
                "font-weight: bold; padding: 4px 0; letter-spacing: 0.5px;"
            )
            root_layout.addWidget(self._edu_top_banner)
        
        # ---- Mode Switcher Bar ----
        mode_bar = QWidget()
        mode_bar.setFixedHeight(40)
        mode_bar.setStyleSheet(f"""
            QWidget {{
                background-color: #2a2e38;
                border-bottom: 1px solid {default_theme.border_standard};
            }}
        """)
        mode_bar_layout = QHBoxLayout(mode_bar)
        mode_bar_layout.setContentsMargins(12, 4, 12, 4)
        mode_bar_layout.setSpacing(8)
        
        # File menu button — quick access to New/Open/Save/Save As/Password
        # without having to first switch into "The Project" workspace.
        # Wired to ui.project_widget.ProjectWidget's existing file-operation
        # methods via self.project_widget, which is created further below;
        # the lambdas below only resolve that attribute at click time.
        _mode_font_size = '14px' if sys.platform == 'win32' else '13px'
        self._mode_file_btn = QPushButton(t("mode_bar.file"))
        self._mode_file_btn.setFixedHeight(30)
        self._mode_file_btn.setCursor(Qt.PointingHandCursor)
        self._mode_file_btn.setAttribute(Qt.WA_StyledBackground, True)
        self._mode_file_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {default_theme.button_primary};
                color: #ffffff;
                border: 1px solid {default_theme.button_primary};
                border-radius: 6px;
                padding: 5px 14px;
                font-size: {_mode_font_size};
                font-weight: normal;
            }}
            QPushButton:hover {{
                background-color: #ffffff;
                color: #000000;
                border-color: #8090a8;
                font-weight: bold;
            }}
            QPushButton::menu-indicator {{ subcontrol-position: right center; }}
        """)
        _file_menu = QMenu(self._mode_file_btn)
        _file_menu.setStyleSheet(f"""
            QMenu {{
                background-color: {default_theme.card_background};
                color: {default_theme.text_primary};
                border: 1px solid {default_theme.border_standard};
            }}
            QMenu::item {{ padding: 6px 22px; }}
            QMenu::item:selected {{ background-color: {default_theme.button_primary}; color: #ffffff; }}
            QMenu::separator {{ height: 1px; background: {default_theme.border_standard}; margin: 4px 0; }}
        """)
        from core.edition import is_lite
        if is_lite():
            # LYNS Lite never manages a .lyns.pjt project — it only ever
            # opens/saves the one .lyns.review file a supplier was sent.
            # See _lite_new_project/_lite_open_review/_lite_save_review below.
            _file_menu.addAction(t('mode_bar.lite_new_review'), lambda: self._lite_new_project())
            _file_menu.addAction(t('mode_bar.lite_open_review'), lambda: self._lite_open_review())
            _file_menu.addAction(t('mode_bar.lite_save_review'), lambda: self._lite_save_review())
            _file_menu.addAction(t('mode_bar.lite_save_review_as'), lambda: self._lite_save_review_as())
        else:
            _file_menu.addAction(t('project.topbar.new'), lambda: self.project_widget._on_new_project())
            _file_menu.addAction(t('project.topbar.open'), lambda: self.project_widget._on_open_project())
            _file_menu.addAction(t('project.topbar.save'), lambda: self.project_widget._on_save_project())
            _file_menu.addAction(t('project.topbar.save_as'), lambda: self.project_widget._on_save_project_as())
            _file_menu.addAction(t('project.topbar.version_history'), lambda: self.project_widget._show_version_history())
            _file_menu.addSeparator()
            # Supplier Review Workflow — see core/review_format.py.
            _file_menu.addAction(t('project.topbar.export_review'), lambda: self.project_widget._export_supplier_review())
            _file_menu.addAction(t('project.topbar.import_review'), lambda: self.project_widget._import_supplier_review())
            _file_menu.addSeparator()
            _file_menu.addAction(t('project.topbar.password'), lambda: self.project_widget._on_password_btn())
        self._mode_file_btn.setMenu(_file_menu)

        self._mode_3d_btn = QPushButton(t("mode_bar.viewer_3d"))
        self._mode_tech_btn = QPushButton(t("mode_bar.technical"))
        self._mode_scale_btn = QPushButton(t("mode_bar.drawing_scale"))
        self._mode_project_btn = QPushButton(t("mode_bar.project"))
        self._mode_help_btn = QPushButton(t("mode_bar.help"))
        for btn in (self._mode_3d_btn, self._mode_tech_btn, self._mode_scale_btn, self._mode_project_btn, self._mode_help_btn):
            btn.setFixedHeight(30)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setCheckable(True)
            btn.setAttribute(Qt.WA_StyledBackground, True)
        self._mode_3d_btn.setChecked(True)
        self._current_mode = "3d"

        self._update_mode_btn_styles()
        self._mode_3d_btn.clicked.connect(lambda: self._switch_mode("3d"))
        self._mode_tech_btn.clicked.connect(lambda: self._switch_mode("technical"))
        self._mode_scale_btn.clicked.connect(lambda: self._switch_mode("scale"))
        self._mode_project_btn.clicked.connect(lambda: self._switch_mode("project"))
        self._mode_help_btn.clicked.connect(lambda: self._switch_mode("help"))

        mode_bar_layout.addWidget(self._mode_file_btn)
        mode_bar_layout.addWidget(self._mode_3d_btn)
        mode_bar_layout.addWidget(self._mode_tech_btn)
        mode_bar_layout.addWidget(self._mode_scale_btn)
        mode_bar_layout.addWidget(self._mode_project_btn)
        mode_bar_layout.addStretch()

        # Language toggle button (EN/FR)
        self._lang_btn = QPushButton("FR" if get_language() == "en" else "EN")
        self._lang_btn.setFixedSize(42, 26)
        self._lang_btn.setCursor(Qt.PointingHandCursor)
        self._lang_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(255, 255, 255, 0.12);
                color: {default_theme.text_white};
                border: 1px solid rgba(255, 255, 255, 0.25);
                border-radius: 6px;
                font-size: 11px;
                font-weight: bold;
                padding: 2px 6px;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.22);
                border-color: rgba(255, 255, 255, 0.40);
            }}
        """)
        self._lang_btn.clicked.connect(self._toggle_language)
        mode_bar_layout.addWidget(self._lang_btn)

        mode_bar_layout.addWidget(self._mode_help_btn)
        root_layout.addWidget(mode_bar)
        
        # ---- Workspace stack (3D vs Technical) ----
        self._workspace_stack = QStackedWidget()
        root_layout.addWidget(self._workspace_stack, 1)
        
        # ==== 3D Viewer Workspace ====
        viewer_workspace = QWidget()
        main_layout = QHBoxLayout(viewer_workspace)
        main_layout.setContentsMargins(0, 10, 10, 10)
        main_layout.setSpacing(10)
        
        logger.info("init_ui: Creating splitter...")
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet(f"background-color: {default_theme.background};")
        splitter.setOpaqueResize(False)
        main_layout.addWidget(splitter)
        
        logger.info("init_ui: Creating sidebar panel...")
        self.sidebar_panel = SidebarPanel()
        self.sidebar_panel._main_window = self  # Direct reference for texture data access
        self.sidebar_panel.upload_btn.clicked.connect(self.upload_stl_file)
        self.sidebar_panel.export_scaled_stl.connect(self.export_scaled_stl)
        self.sidebar_panel.annotations_exported.connect(self._on_annotations_exported)
        
        splitter.addWidget(self.sidebar_panel)
        logger.info("init_ui: Sidebar panel created")
        
        # Create right panel container (tab bar + toolbar + viewer stack)
        right_container = QWidget()
        self.right_layout = QVBoxLayout(right_container)
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        self.right_layout.setSpacing(0)
        
        # ---- Tab Bar (left-aligned so "Untitled" starts at left edge) ----
        self.tab_bar = _EctoTabBar()
        self.tab_bar.setObjectName("ectoTabBar")
        self.tab_bar.setAttribute(Qt.WA_StyledBackground, True)
        self.tab_bar.setMinimumHeight(30)
        self.tab_bar.setTabsClosable(True)
        self.tab_bar.setMovable(False)
        self.tab_bar.setExpanding(False)
        self.tab_bar.setDrawBase(False)
        self.tab_bar.setElideMode(Qt.ElideNone)
        self.tab_bar.tabCloseRequested.connect(self._on_tab_close_requested)
        # Add Overview pinned tab, then "+" button (before connecting currentChanged)
        self._overview_tab_index = self.tab_bar.addTab("⊞  Overview")
        self._plus_tab_index = self.tab_bar.addTab("+")
        self.tab_bar.currentChanged.connect(self._on_tab_changed)
        # Overview: no close button
        self.tab_bar.setTabButton(self._overview_tab_index, QTabBar.RightSide, None)
        self.tab_bar.setTabButton(self._overview_tab_index, QTabBar.LeftSide, None)
        # "+": no close button
        self.tab_bar.setTabButton(self._plus_tab_index, QTabBar.RightSide, None)
        self.tab_bar.setTabButton(self._plus_tab_index, QTabBar.LeftSide, None)
        tab_bar_container = QWidget()
        tab_bar_layout = QHBoxLayout(tab_bar_container)
        # Left inset so first tab label (bold) is not flush against the splitter edge / clipped
        tab_bar_layout.setContentsMargins(14, 0, 0, 0)
        tab_bar_layout.setSpacing(0)
        tab_bar_layout.addWidget(self.tab_bar, 0, Qt.AlignLeft)
        tab_bar_layout.addStretch(1)
        self.right_layout.addWidget(tab_bar_container)
        
        # Create toolbar
        logger.info("init_ui: Creating toolbar...")
        self.toolbar = ViewControlsToolbar()
        self._connect_toolbar_signals()
        self.right_layout.addWidget(self.toolbar)
        logger.info("init_ui: Toolbar created")
        
        # Create ruler toolbar (hidden by default)
        logger.info("init_ui: Creating ruler toolbar...")
        self.ruler_toolbar = RulerToolbar()
        self.ruler_toolbar.hide()
        self._connect_ruler_toolbar_signals()
        self.right_layout.addWidget(self.ruler_toolbar)
        logger.info("init_ui: Ruler toolbar created")
        
        # ---- Overview widget (lives in viewer_stack, shown when Overview tab is active) ----
        self.overview_widget = OverviewWidget()
        self.overview_widget.tab_requested.connect(self._on_overview_tab_requested)
        self.overview_widget.set_refresh_callback(self._capture_all_thumbnails)
        self.overview_widget.set_rotate_callback(self._on_overview_rotate)
        self.overview_widget.set_drag_released_callback(self._on_overview_drag_released)

        # ---- Stacked widgets for viewers and annotation/screenshot/arrow/texture panels ----
        self.viewer_stack = QStackedWidget()
        self.viewer_stack.addWidget(self.overview_widget)   # index 0 = overview
        self.annotation_stack = QStackedWidget()
        self.screenshot_stack = QStackedWidget()
        self.arrow_stack = QStackedWidget()
        self.parts_stack = QStackedWidget()
        self.texture_stack = QStackedWidget()
        
        # Shared screenshot panel (one per window, not per tab)
        self.screenshot_panel = ScreenshotPanel()
        self.screenshot_panel.exit_screenshot_mode.connect(self._exit_screenshot_mode)
        self.screenshot_panel.save_to_report.connect(self._save_screenshot_to_report)
        self.screenshot_panel.capture_desktop_requested.connect(self._on_capture_desktop)
        self.screenshot_stack.addWidget(self.screenshot_panel)
        
        # Shared texture panel (one per window, not per tab)
        self.texture_panel = TexturePanel()
        self.texture_panel.exit_texture_mode.connect(self._exit_texture_mode_from_panel)
        self.texture_panel.texture_settings_changed.connect(self._on_texture_settings_changed)
        self.texture_panel.reset_textures_requested.connect(self._on_reset_textures_requested)
        self.texture_stack.addWidget(self.texture_panel)
        
        # Shared record panel
        self.record_panel = RecordPanel()
        self.record_panel.start_recording_clicked.connect(self._on_panel_start_recording)
        self.record_panel.stop_recording_clicked.connect(self._on_panel_stop_recording)
        self.record_panel.save_recording_clicked.connect(self._on_panel_save_recording)
        self.record_panel.discard_recording_clicked.connect(self._on_panel_discard_recording)
        self.record_panel.exit_record_mode.connect(self._exit_record_mode)
        self.record_panel.rotate_toggled.connect(self._on_record_panel_rotate_toggled)
        self.record_panel.speed_changed.connect(self._on_record_panel_speed_changed)
        self.record_panel.direction_changed.connect(self._on_record_panel_direction_changed)
        self._record_stopped_tmp_path = ""   # held between Stop and Save/Discard
        self.record_stack = QStackedWidget()
        self.record_stack.addWidget(self.record_panel)

        # Single right panel: only annotation OR screenshot OR arrow OR parts OR texture OR record visible at a time
        self.right_panel_stack = QStackedWidget()
        self._right_panel_placeholder = QWidget()
        self._right_panel_placeholder.setFixedWidth(0)  # No space when neither mode active
        self.right_panel_stack.addWidget(self._right_panel_placeholder)
        self.right_panel_stack.addWidget(self.annotation_stack)
        self.right_panel_stack.addWidget(self.screenshot_stack)
        self.right_panel_stack.addWidget(self.arrow_stack)
        self.right_panel_stack.addWidget(self.parts_stack)
        self.right_panel_stack.addWidget(self.texture_stack)
        self.right_panel_stack.addWidget(self.record_stack)
        self.right_panel_stack.setCurrentWidget(self._right_panel_placeholder)
        self.right_panel_stack.hide()  # No blank space when neither mode active
        
        # Use an inner splitter so the right-side panels are draggable/resizable
        self._viewer_splitter = QSplitter(Qt.Horizontal)
        self._viewer_splitter.setOpaqueResize(False)
        self._viewer_splitter.addWidget(self.viewer_stack)
        self._viewer_splitter.addWidget(self.right_panel_stack)
        # Make the right panel collapsible so when hidden it uses zero width
        try:
            self._viewer_splitter.setCollapsible(0, False)
            self._viewer_splitter.setCollapsible(1, True)
        except Exception:
            pass
        # Favor the viewer taking available space
        self._viewer_splitter.setStretchFactor(0, 1)
        self._viewer_splitter.setStretchFactor(1, 0)
        self._right_panel_default_width = 320
        self._right_panel_last_width = self._right_panel_default_width
        self._viewer_splitter.setSizes([1000, self._right_panel_default_width])
        self._viewer_splitter.splitterMoved.connect(self._on_viewer_splitter_moved)
        self.right_layout.addWidget(self._viewer_splitter, 1)
        
        # ---- Education watermark below 3D viewer ----
        if is_education():
            self._edu_viewer_watermark = QLabel(WATERMARK_TEXT)
            self._edu_viewer_watermark.setAlignment(Qt.AlignCenter)
            self._edu_viewer_watermark.setFixedHeight(24)
            self._edu_viewer_watermark.setStyleSheet(
                f"background-color: {default_theme.background}; color: #B91C1C; "
                "font-size: 10px; font-weight: bold; font-style: italic; padding: 2px 0;"
            )
            self.right_layout.addWidget(self._edu_viewer_watermark)
        
        # Add right container to splitter
        splitter.addWidget(right_container)
        
        logger.info("init_ui: Configuring splitter...")
        splitter.setSizes([200, 1000])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        
        self._workspace_stack.addWidget(viewer_workspace)
        
        # ==== Technical Overview Workspace ====
        tech_workspace = QWidget()
        _tech_outer = QHBoxLayout(tech_workspace)
        _tech_outer.setContentsMargins(0, 0, 0, 0)
        _tech_outer.setSpacing(0)

        self._tech_splitter = QSplitter(Qt.Horizontal)
        self._tech_splitter.setOpaqueResize(False)
        self._tech_splitter.setStyleSheet(f"background-color: {default_theme.background};")

        self.technical_sidebar = TechnicalSidebar()
        self.technical_sidebar.upload_requested.connect(self._tech_upload_image)
        self.technical_sidebar.annotate_toggled.connect(self._tech_toggle_annotation)
        self.technical_sidebar.export_requested.connect(self._tech_export_ecto)
        self.technical_sidebar.export_pdf_requested.connect(self._tech_export_pdf)
        self.technical_sidebar.reset_requested.connect(self._tech_reset)
        from core.edition import is_lite
        if is_lite():
            # LYNS Lite never edits the technical document's own metadata
            # (property/title/manufacturer/dates/comments) or uploads a new
            # one — only annotate + the two export buttons stay usable (see
            # TechnicalSidebar.set_read_only's is_lite() bypass). Set once,
            # unconditionally, here rather than per load-path, since Lite
            # stays Lite for its whole session regardless of how a document
            # got loaded (a fresh review, or one reopened via file
            # association — see main.py).
            self.technical_sidebar.set_read_only(True)
        self._tech_ecto_exported = False
        self._tech_splitter.addWidget(self.technical_sidebar)

        self.technical_overview = TechnicalOverviewWidget()
        self._tech_splitter.addWidget(self.technical_overview)
        self._tech_splitter.setStretchFactor(0, 0)
        self._tech_splitter.setStretchFactor(1, 1)
        self._tech_splitter.setSizes([420, 1000])
        self._tech_splitter.setCollapsible(0, False)

        _tech_outer.addWidget(self._tech_splitter)
        self._workspace_stack.addWidget(tech_workspace)
        
        # ==== Drawing Scale Workspace ====
        scale_workspace = QWidget()
        _scale_outer = QHBoxLayout(scale_workspace)
        _scale_outer.setContentsMargins(0, 0, 0, 0)
        _scale_outer.setSpacing(0)

        self._scale_splitter = QSplitter(Qt.Horizontal)
        self._scale_splitter.setOpaqueResize(False)
        self._scale_splitter.setStyleSheet(f"background-color: {default_theme.background};")

        self.scale_sidebar = ScaleSidebar()
        self.scale_sidebar.upload_requested.connect(self._scale_upload)
        self.scale_sidebar.unit_changed.connect(self._scale_unit_changed)
        self.scale_sidebar.scale_changed.connect(self._scale_ratio_changed)
        self.scale_sidebar.ruler_toggled.connect(self._scale_ruler_toggled)
        self.scale_sidebar.export_requested.connect(self._scale_export)
        self.scale_sidebar.add_ref_requested.connect(self._scale_add_ref)
        self.scale_sidebar.reset_requested.connect(self._scale_reset)
        self.scale_sidebar.static_border_toggled.connect(self._scale_static_border_toggled)
        self.scale_sidebar.moving_border_toggled.connect(self._scale_moving_border_toggled)
        self.scale_sidebar.ref_lines_toggled.connect(self._scale_ref_lines_toggled)
        self.scale_sidebar.pdf_locked.connect(self._scale_pdf_locked)
        self.scale_sidebar.drawing_mode_changed.connect(self._scale_drawing_mode_changed)
        self.scale_sidebar.drawing_color_changed.connect(self._scale_drawing_color_changed)
        self._scale_splitter.addWidget(self.scale_sidebar)

        self.scale_canvas = ScaleCanvas()
        self.scale_canvas.click_to_upload.connect(self._scale_upload)
        self._scale_splitter.addWidget(self.scale_canvas)
        self._scale_splitter.setStretchFactor(0, 0)
        self._scale_splitter.setStretchFactor(1, 1)
        self._scale_splitter.setSizes([420, 1000])
        self._scale_splitter.setCollapsible(0, False)

        _scale_outer.addWidget(self._scale_splitter)
        self._workspace_stack.addWidget(scale_workspace)
        
        # ==== The Project Workspace ====
        self.project_widget = TheProjectWidget()
        self.project_widget.open_in_viewer.connect(self._open_file_from_project)
        self.project_widget.restore_viewer_tab.connect(self._restore_viewer_tab_from_project)
        self.project_widget.clear_viewer_tabs.connect(self._clear_all_viewer_tabs)
        self.project_widget.viewer_tabs_sync_requested.connect(self._push_viewers_to_project)
        self.project_widget.viewer_tabs_conflict_resolved.connect(self._reconcile_viewer_tabs_after_merge)
        self.project_widget.viewer_tab_screenshots_merged.connect(self._on_tab_screenshots_merged)
        self.project_widget.qc_model_remove_requested.connect(self._on_qc_model_remove)
        self.project_widget.qc_upload_requested.connect(self.upload_stl_file)
        self.project_widget.project_info_changed.connect(self.technical_sidebar.update_project_info)
        self.project_widget.read_only_changed.connect(self._on_project_read_only_changed)
        self.project_widget.set_technical_overview_refs(self.technical_overview, self.technical_sidebar)
        self.project_widget.restore_technical_overview.connect(self._restore_technical_overview_from_project)
        self.project_widget.set_scale_refs(self.scale_canvas, self.scale_sidebar)
        self.project_widget.restore_drawing_scale.connect(self._restore_drawing_scale_from_project)
        self._workspace_stack.addWidget(self.project_widget)

        # ==== Help Workspace ====
        self.help_widget = HelpWidget()
        self._workspace_stack.addWidget(self.help_widget)
        self._workspace_stack.setCurrentIndex(0)  # Start with 3D Viewer
        
        # ==== Education watermark overlays on all workspace areas ====
        if is_education():
            from ui.watermark_overlay import WatermarkOverlay
            # Overlay on the workspace stack itself (covers 3D, Technical, Scale)
            self._edu_workspace_watermark = WatermarkOverlay(self._workspace_stack)
            self._edu_workspace_watermark.raise_()
            # Keep it sized to the workspace stack
            self._workspace_stack.installEventFilter(self)
        
        logger.info("init_ui: Applying styling...")
        self.apply_styling()
        
        # Create initial empty tab
        self._create_new_tab()
        
        # Register language change listener
        on_language_changed(self._retranslate_ui)
        
        # Restore saved language preference
        from PyQt5.QtCore import QSettings
        saved_lang = QSettings("LYNS", "App").value("language", "en", type=str)
        if saved_lang != get_language():
            set_language(saved_lang)
        
        logger.info("init_ui: UI initialization complete")
    
    # ======================== User Account Widget ========================

    def _build_user_account_widget(self) -> QWidget:
        """Builds the user account pill shown on the right of the mode bar."""
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Avatar circle — coloured initials badge
        avatar = QLabel("A")
        avatar.setFixedSize(24, 24)
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setStyleSheet(f"""
            QLabel {{
                background-color: {default_theme.button_primary};
                color: white;
                border-radius: 12px;
                font-size: 11px;
                font-weight: bold;
                border: none;
            }}
        """)

        # Name + dropdown button
        self._user_btn = QPushButton("Admin  ▾")
        self._user_btn.setFlat(True)
        self._user_btn.setCursor(Qt.PointingHandCursor)
        self._user_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {default_theme.text_primary};
                border: none;
                font-size: 11px;
                font-weight: bold;
                padding: 0 2px;
            }}
            QPushButton:hover {{
                color: white;
            }}
        """)

        # Separator line before avatar
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFixedHeight(18)
        sep.setStyleSheet(f"color: {default_theme.border_light}; background: {default_theme.border_light}; max-width: 1px; border: none;")

        layout.addWidget(sep)
        layout.addWidget(avatar)
        layout.addWidget(self._user_btn)
        return container

    # ======================== Mode Switching ========================

    def _update_mode_btn_styles(self):
        """Update mode switcher button styles based on current mode."""
        # Selected: glossy / skeuomorphic — top shine + vertical depth + beveled edges (Qt has no inset shadow)
        _mode_font_size = '14px' if sys.platform == 'win32' else '13px'
        active_style = f"""
            QPushButton {{
                background-color: #ffffff;
                color: #000000;
                border: 1px solid #b0b8c8;
                border-radius: 6px;
                padding: 5px 14px;
                font-size: {_mode_font_size};
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #f0f2f5;
                border-color: #8090a8;
            }}
            QPushButton:pressed {{
                background-color: #e4e8ee;
            }}
        """
        inactive_style = f"""
            QPushButton {{
                background-color: {default_theme.button_primary};
                color: #ffffff;
                border: 1px solid {default_theme.button_primary};
                border-radius: 6px;
                padding: 5px 14px;
                font-size: {_mode_font_size};
                font-weight: normal;
            }}
            QPushButton:hover {{
                background-color: #ffffff;
                color: #000000;
                border-color: #8090a8;
                font-weight: bold;
            }}
        """
        self._mode_3d_btn.setStyleSheet(active_style if self._current_mode == "3d" else inactive_style)
        self._mode_tech_btn.setStyleSheet(active_style if self._current_mode == "technical" else inactive_style)
        self._mode_scale_btn.setStyleSheet(active_style if self._current_mode == "scale" else inactive_style)
        self._mode_project_btn.setStyleSheet(active_style if self._current_mode == "project" else inactive_style)
        self._mode_help_btn.setStyleSheet(active_style if self._current_mode == "help" else inactive_style)

    def _switch_mode(self, mode: str):
        """Switch between '3d', 'technical', 'scale', 'project', and 'help' workspace modes."""
        if mode == self._current_mode:
            return

        self._current_mode = mode
        self._mode_3d_btn.setChecked(mode == "3d")
        self._mode_tech_btn.setChecked(mode == "technical")
        self._mode_scale_btn.setChecked(mode == "scale")
        self._mode_project_btn.setChecked(mode == "project")
        self._mode_help_btn.setChecked(mode == "help")
        self._update_mode_btn_styles()

        if mode == "3d":
            # setCurrentIndex hides the project widget synchronously, which fires
            # hideEvent on QC → release_viewer → viewer restored to viewer_stack.
            # After this line the viewer is already back in viewer_stack.
            self._workspace_stack.setCurrentIndex(0)
            # viewer_stack.currentWidget may have drifted to Overview while the
            # viewer was reparented into the QC panel.  Restore it explicitly.
            tab = self._current_tab
            if tab and tab.viewer_widget:
                self.viewer_stack.setCurrentWidget(tab.viewer_widget)
            self.setWindowTitle(f"LYNS - {self._current_tab.filename}" if self._current_tab and self._current_tab.filename else "LYNS")
        elif mode == "technical":
            self._workspace_stack.setCurrentIndex(1)
            self.setWindowTitle("LYNS - Technical Overview")
            self._autofill_technical_object_title()
        elif mode == "scale":
            self._workspace_stack.setCurrentIndex(2)
            self.setWindowTitle("LYNS - Drawing Scale")
        elif mode == "project":
            # Push viewer refs BEFORE showing the project widget so that when
            # showEvent fires on the QC panel (if it was last active), _viewer_ref
            # is already correct and embed_viewer is not called mid-switch.
            try:
                self._push_viewers_to_project()
            except Exception:
                pass
            self._workspace_stack.setCurrentIndex(3)
            self.setWindowTitle("LYNS - The Project")
        elif mode == "help":
            self._workspace_stack.setCurrentIndex(4)
            self.setWindowTitle("LYNS - Help")

        # When leaving the 3D workspace ensure any 3D-only overlays/modes are disabled
        if mode != "3d":
            try:
                vw = getattr(self, 'viewer_widget', None)
                if vw is not None:
                    if hasattr(vw, 'disable_annotation_mode'):
                        vw.disable_annotation_mode()
                    if hasattr(vw, 'disable_screenshot_mode'):
                        vw.disable_screenshot_mode()
                    if hasattr(vw, 'disable_draw_mode'):
                        vw.disable_draw_mode()
                    if hasattr(vw, 'disable_ruler_mode'):
                        vw.disable_ruler_mode()
            except Exception:
                pass

        logger.info(f"_switch_mode: Switched to {mode} mode")

    def _autofill_technical_object_title(self):
        """Auto-copy the company name + product title from The Project's main
        info card into the Technical Overview 'Object Title' field, so users
        don't have to retype info that's already entered elsewhere. Only
        fills it in while it's still empty — never overwrites a value the
        user already typed."""
        try:
            sidebar = getattr(self, 'technical_sidebar', None)
            project_widget = getattr(self, 'project_widget', None)
            if sidebar is None or project_widget is None:
                return
            if sidebar.title_edit.text().strip():
                return
            info = project_widget._nav.get_info_data()
            company = (info.get('company') or '').strip()
            title = (info.get('title') or '').strip()
            combined = ' — '.join(p for p in (company, title) if p)
            if combined:
                sidebar.title_edit.setText(combined)
        except Exception:
            logger.debug("_autofill_technical_object_title: failed", exc_info=True)

    def _on_viewer_splitter_moved(self, _pos: int, _index: int):
        """Remember the last non-zero right panel width."""
        splitter = getattr(self, "_viewer_splitter", None)
        if splitter is None:
            return
        sizes = splitter.sizes()
        if len(sizes) >= 2 and sizes[1] > 0:
            self._right_panel_last_width = sizes[1]

    def _restore_right_panel_width(self):
        """Restore the right panel to a usable width if it was collapsed to zero."""
        splitter = getattr(self, "_viewer_splitter", None)
        if splitter is None or not self.right_panel_stack.isVisible():
            return
        sizes = splitter.sizes()
        if len(sizes) < 2:
            return
        if sizes[1] > 0:
            self._right_panel_last_width = sizes[1]
            return

        total_width = sum(sizes)
        if total_width <= 0:
            total_width = splitter.width()
        if total_width <= 0:
            return

        preferred_right = max(self._right_panel_default_width, getattr(self, "_right_panel_last_width", 0))
        preferred_right = min(preferred_right, max(260, total_width - 260))
        preferred_left = max(260, total_width - preferred_right)
        splitter.setSizes([preferred_left, preferred_right])
        self._right_panel_last_width = preferred_right
    
    def _toggle_language(self):
        """Toggle between English and French."""
        from PyQt5.QtCore import QSettings
        new_lang = "fr" if get_language() == "en" else "en"
        QSettings("LYNS", "App").setValue("language", new_lang)
        set_language(new_lang)
    
    def _retranslate_ui(self):
        """Update all mode bar texts when language changes."""
        self._mode_file_btn.setText(t("mode_bar.file"))
        _file_menu = self._mode_file_btn.menu()
        if _file_menu is not None:
            from core.edition import is_lite
            _actions = _file_menu.actions()
            if is_lite():
                _labels = ('mode_bar.lite_new_review', 'mode_bar.lite_open_review',
                           'mode_bar.lite_save_review', 'mode_bar.lite_save_review_as')
            else:
                _labels = ('project.topbar.new', 'project.topbar.open', 'project.topbar.save',
                           'project.topbar.save_as', 'project.topbar.version_history', None,
                           'project.topbar.export_review', 'project.topbar.import_review', None,
                           'project.topbar.password')
            for _act, _key in zip(_actions, _labels):
                if _key:
                    _act.setText(t(_key))
        self._mode_3d_btn.setText(t("mode_bar.viewer_3d"))
        self._mode_tech_btn.setText(t("mode_bar.technical"))
        self._mode_scale_btn.setText(t("mode_bar.drawing_scale"))
        self._mode_project_btn.setText(t("mode_bar.project"))
        self._mode_help_btn.setText(t("mode_bar.help"))
        self._lang_btn.setText("FR" if get_language() == "en" else "EN")
    
    def _tech_upload_image(self):
        """Handle upload request from technical sidebar — supports images, PDFs, and .lyns files."""
        path, _ = get_open_file_name(
            self, "Select Image, PDF, or .lyns file", "",
            "Supported Files (*.png *.jpg *.jpeg *.bmp *.pdf *.lyns *.ecto);;Images & PDFs (*.png *.jpg *.jpeg *.bmp *.pdf);;LYNS Files (*.lyns *.ecto);;All Files (*)"
        )
        if not path:
            return
        if path.lower().endswith('.ecto') or path.lower().endswith('.lyns'):
            self._load_technical_ecto(path)
        else:
            self.technical_overview.load_image_from_path(path)
    
    def _tech_toggle_annotation(self, enabled: bool):
        """Toggle annotation mode on the technical overview."""
        if enabled:
            self.technical_overview.enter_annotation_mode()
        else:
            self.technical_overview.exit_annotation_mode()

    def _tech_export_ecto(self):
        """Export technical overview as a passcode-protected .ecto file."""
        doc_path = self.technical_overview.get_document_path()
        if not doc_path:
            show_warning_dialog(self, "No Document", "Please upload an image or PDF first.")
            return

        passcode_hash = None
        if not is_education():
            # Ask for passcode (disabled in Education edition)
            from ui.passcode_dialog import PasscodeDialog
            dlg = PasscodeDialog(mode='set', parent=self)
            if dlg.exec() != PasscodeDialog.Accepted:
                return
            passcode_hash = dlg.get_passcode_hash()

        # Pick save location
        default_name = Path(doc_path).stem + '.lyns'
        save_path, _ = get_save_file_name(
            self, "Export Technical Overview .lyns", default_name,
            "LYNS Files (*.lyns);;All Files (*)"
        )
        if not save_path:
            return

        from core.ecto_format import EctoFormat
        annotations = self.technical_overview.get_annotations_data()
        metadata = self.technical_sidebar.get_metadata()

        success, msg = EctoFormat.export_technical(
            document_path=doc_path,
            annotations=annotations,
            metadata=metadata,
            output_path=save_path,
            passcode_hash=passcode_hash,
        )
        if success:
            self._tech_ecto_exported = True
            show_message_dialog(self, "Export Successful",
                                f"Technical overview exported to:\n{msg}")
        else:
            show_error_dialog(self, "Export Failed", f"Error: {msg}")

    def _tech_export_pdf(self):
        """Export technical overview as a PDF report with annotated image and table."""
        if is_education():
            show_message_dialog(self, "Education Version",
                                "PDF export is not available in the Education version.")
            return
        pixmap = self.technical_overview.canvas._pixmap
        if pixmap is None or pixmap.isNull():
            show_warning_dialog(self, "No Document", "Please upload an image or PDF first.")
            return

        metadata = self.technical_sidebar.get_metadata()
        default_name = "Technical_Overview_Report.pdf"
        doc_path = self.technical_overview.get_document_path()
        if doc_path:
            default_name = Path(doc_path).stem + "_report.pdf"

        save_path, _ = get_save_file_name(
            self, "Export PDF Report", default_name,
            "PDF Files (*.pdf);;All Files (*)"
        )
        if not save_path:
            return

        from core.technical_pdf_exporter import TechnicalPDFExporter
        annotations = self.technical_overview.get_annotations()
        success, msg = TechnicalPDFExporter.export(
            document_pixmap=pixmap,
            annotations=annotations,
            metadata=metadata,
            output_path=save_path,
        )
        if success:
            show_message_dialog(self, "PDF Exported", f"Report saved to:\n{msg}")
        else:
            show_error_dialog(self, "Export Failed", f"Error: {msg}")

    def _tech_reset(self):
        """Reset the technical overview workspace with unsaved-changes warning."""
        has_content = (
            self.technical_overview.get_annotations()
            or self.technical_overview.get_document_path()
        )

        if has_content and not self._tech_ecto_exported:
            if not ask_yes_no_dialog(
                self, "Unsaved Changes",
                "You have not exported this workspace as an .ecto file.\n\n"
                "All annotations, metadata, and the loaded document will be lost.\n\n"
                "Do you want to reset anyway?"
            ):
                return

        # Reset everything
        self.technical_overview.clear_all()
        self.technical_overview.canvas.clear_image()
        self.technical_sidebar.reset()
        self._tech_ecto_exported = False

    # ======================== Drawing Scale Mode ========================

    def _scale_upload(self):
        """Upload a drawing file for scale calibration."""
        path, _ = get_open_file_name(
            self, "Select Drawing", "",
            "Drawings (*.png *.jpg *.jpeg *.bmp *.pdf);;All Files (*)"
        )
        if path:
            self.scale_canvas.load_file(path)

    def _scale_unit_changed(self, unit: str):
        self.scale_canvas.set_unit(unit)

    def _scale_ratio_changed(self, ratio: float):
        self.scale_canvas.set_scale_ratio(ratio)

    def _scale_ruler_toggled(self, enabled: bool):
        self.scale_canvas.set_ruler_mode(enabled)

    def _scale_reset(self):
        """Clear the drawing and reset all Drawing Scale controls (canvas + sidebar)."""
        self.scale_canvas.reset_workspace()
        self.scale_sidebar.reset()

    def _scale_static_border_toggled(self, show: bool):
        """Handle static border visibility toggle."""
        self.scale_canvas.set_show_static_border(show)

    def _scale_moving_border_toggled(self, show: bool):
        """Handle moving border visibility toggle."""
        self.scale_canvas.set_show_moving_border(show)
    def _scale_ref_lines_toggled(self, show: bool):
        """Handle dotted reference lines visibility toggle."""
        self.scale_canvas.set_show_ref_lines(show)

    def _scale_pdf_locked(self, locked: bool):
        """Handle PDF lock/unlock toggle."""
        self.scale_canvas.set_pdf_locked(locked)

    def _scale_drawing_mode_changed(self, mode: str):
        """Handle drawing mode changes (arrow, rectangle, circle, or None)."""
        if mode == "clear":
            self.scale_canvas.clear_drawings()
        else:
            self.scale_canvas.set_drawing_mode(mode if mode else None)

    def _scale_drawing_color_changed(self, color):
        """Handle drawing color changes."""
        self.scale_canvas.set_drawing_color(color)

    # ======================== Tab Management ========================
    
    def _create_new_tab(self, file_path: str = None) -> int:
        """Create a new tab with its own viewer and annotation panel. Returns tab index."""
        tab = TabState()
        tab.tab_id = uuid.uuid4().hex

        # Create viewer widget
        try:
            if not USE_OFFSCREEN:
                tab.viewer_widget = STLViewerWidget()
            else:
                from viewer_widget_offscreen import STLViewerWidgetOffscreen
                tab.viewer_widget = STLViewerWidgetOffscreen()
        except Exception as e:
            logger.error(f"_create_new_tab: Failed to create viewer: {e}", exc_info=True)
            try:
                from viewer_widget_offscreen import STLViewerWidgetOffscreen
                tab.viewer_widget = STLViewerWidgetOffscreen()
            except Exception as e2:
                logger.error(f"_create_new_tab: Offscreen fallback failed: {e2}", exc_info=True)
                return -1
        
        # Connect viewer signals
        self._connect_viewer_signals_for(tab.viewer_widget)
        
        # Create annotation panel
        tab.annotation_panel = AnnotationPanel()
        tab.annotation_panel.hide()
        self._connect_annotation_panel_signals_for(tab)
        
        # Create arrow panel
        tab.arrow_panel = ArrowPanel()
        tab.arrow_panel.hide()
        self._connect_arrow_panel_signals_for(tab)
        
        # Create parts panel
        tab.parts_panel = PartsPanel()
        tab.parts_panel.hide()
        self._connect_parts_panel_signals_for(tab)
        
        # Add to stacks
        self.viewer_stack.addWidget(tab.viewer_widget)
        self.annotation_stack.addWidget(tab.annotation_panel)
        self.arrow_stack.addWidget(tab.arrow_panel)
        self.parts_stack.addWidget(tab.parts_panel)
        
        # Add to tabs list
        self.tabs.append(tab)
        tab_index = len(self.tabs) - 1
        
        # Insert tab in tab bar (before the "+" tab)
        display_name = "Untitled"
        if file_path:
            display_name = Path(file_path).name
            tab.file_path = file_path
            tab.filename = display_name
        # Insert before Overview tab (which sits just before "+")
        tab_bar_index = self.tab_bar.insertTab(self._overview_tab_index, _ecto_tab_caption(display_name))
        self._overview_tab_index += 1  # overview tab shifts right
        self._plus_tab_index += 1      # "+" tab also shifts right
        # File tabs keep the native close (×) button — setTabsClosable(True)
        # attaches one automatically; only Overview/"+" have theirs removed.

        # Switch to the new tab
        self.tab_bar.setCurrentIndex(tab_bar_index)
        
        return tab_index

    def _on_qc_model_remove(self, viewer_widget):
        """Close the tab whose viewer_widget was removed from the QC model strip."""
        for i, tab in enumerate(self.tabs):
            if tab.viewer_widget is viewer_widget:
                self._close_tab(i)
                return

    def _push_viewers_to_project(self):
        """Send all loaded (label, viewer_widget) pairs and tab states to the project widget."""
        if not hasattr(self, 'project_widget'):
            return
        # Sync the active tab's own state (mode flags + screenshots) before
        # reading self.tabs — screenshot_panel is one shared widget, so the
        # current tab's screenshots only land on the TabState itself here.
        self._save_current_tab_state()
        viewers = [
            (t.filename, t.viewer_widget)
            for t in self.tabs
            if t.viewer_widget is not None and t.filename is not None
        ]
        active_vw = getattr(self, 'viewer_widget', None)
        if hasattr(self.project_widget, 'set_viewers'):
            self.project_widget.set_viewers(viewers, active_viewer=active_vw)
        if hasattr(self.project_widget, 'set_viewer_tabs'):
            self.project_widget.set_viewer_tabs(self.tabs)

    def _on_tab_changed(self, index: int):
        """Handle tab bar selection change."""
        # If the "+" tab is clicked, create a new tab and upload
        if index == self._plus_tab_index:
            # Revert to previous tab first
            if self.current_tab_index >= 0:
                self.tab_bar.blockSignals(True)
                self.tab_bar.setCurrentIndex(self.current_tab_index)
                self.tab_bar.blockSignals(False)
            self.upload_stl_file()
            return

        # If the Overview pinned tab is clicked, show the overview grid
        if index == self._overview_tab_index:
            self._show_overview()
            return

        if index < 0 or index >= len(self.tabs):
            return
        
        # Save current tab state
        self._save_current_tab_state()

        # Stop rotate/record before switching viewers (they are viewer-specific)
        if self.toolbar.record_mode_enabled:
            self._exit_record_mode()
        elif self.toolbar.rotate_mode_enabled:
            prev_vw = self.viewer_widget
            if prev_vw and hasattr(prev_vw, 'stop_auto_rotate'):
                prev_vw.stop_auto_rotate()
            self.toolbar.reset_rotate_state()

        # Switch to new tab
        self.current_tab_index = index
        tab = self.tabs[index]

        # screenshot_panel is one shared widget across all tabs — swap its
        # visible content to this tab's own screenshots (captured earlier
        # this session or restored from the saved project).
        self.screenshot_panel.set_screenshots(tab.screenshots)

        # Show correct viewer, annotation panel, arrow panel, and parts panel
        self.viewer_stack.setCurrentWidget(tab.viewer_widget)
        self.annotation_stack.setCurrentWidget(tab.annotation_panel)
        self.arrow_stack.setCurrentWidget(tab.arrow_panel)
        self.parts_stack.setCurrentWidget(tab.parts_panel)
        
        # Determine which right panel to show
        if tab.parts_mode_active:
            tab.parts_panel.show()
            self.right_panel_stack.setCurrentWidget(self.parts_stack)
            self.right_panel_stack.show()
            self._restore_right_panel_width()
        elif tab.arrow_mode_active:
            tab.arrow_panel.show()
            self.right_panel_stack.setCurrentWidget(self.arrow_stack)
            self.right_panel_stack.show()
            self._restore_right_panel_width()
        elif tab.annotation_mode_active:
            tab.annotation_panel.show()
            self.right_panel_stack.setCurrentWidget(self.annotation_stack)
            self.right_panel_stack.show()
            self._restore_right_panel_width()
        elif tab.screenshot_mode_active:
            self.right_panel_stack.setCurrentWidget(self.screenshot_stack)
            self.right_panel_stack.show()
            self.screenshot_panel.show()
            self._restore_right_panel_width()
        elif tab.texture_mode_active:
            self.right_panel_stack.setCurrentWidget(self.texture_stack)
            self.right_panel_stack.show()
            self.texture_panel.show()
            self._restore_right_panel_width()
        else:
            tab.annotation_panel.hide()
            tab.arrow_panel.hide()
            tab.parts_panel.hide()
            self.right_panel_stack.setCurrentWidget(self._right_panel_placeholder)
            self.right_panel_stack.hide()
        
        # Update sidebar with this tab's data
        if tab.sidebar_data and tab.file_path:
            self.sidebar_panel.update_dimensions(tab.sidebar_data, tab.file_path)
            count = len(tab.annotation_panel.get_annotations())
            self.sidebar_panel.update_annotation_count(count)
        else:
            self.sidebar_panel.reset_all_data()

        has_file = tab.file_path is not None
        self.toolbar.set_stl_loaded(has_file)
        # set_stl_loaded() unconditionally re-enables the annotation button —
        # reapply this tab's own reader-mode gate on top of it, otherwise
        # switching tabs (including jumping back from the Overview grid)
        # silently undoes reader mode and lets a viewer add new annotations.
        self.toolbar.set_reader_mode(tab.reader_mode)
        if has_file:
            self.toolbar.set_loaded_filename(tab.filename)
            self.setWindowTitle(f"LYNS - {tab.filename}")
        else:
            self.toolbar.set_loaded_filename(None)
            self.setWindowTitle("LYNS")

        # Restore ruler mode
        if tab.ruler_active:
            self.toolbar.ruler_mode_enabled = True
            self.toolbar.ruler_btn.set_active(True)
            self.toolbar.ruler_btn.set_icon("📐")
            self.toolbar.ruler_btn.set_label("Ruler")
            self.ruler_toolbar.show()
        else:
            if self.toolbar.ruler_mode_enabled:
                self.toolbar.ruler_mode_enabled = False
                self.toolbar.ruler_btn.set_active(False)
                self.toolbar.ruler_btn.set_icon("📏")
                self.ruler_toolbar.hide()

        # Restore annotation mode
        if tab.annotation_mode_active:
            self.toolbar.annotation_mode_enabled = True
        else:
            if self.toolbar.annotation_mode_enabled:
                self.toolbar.reset_annotation_state()

        # Restore arrow mode
        if tab.arrow_mode_active:
            self.toolbar.arrow_mode_enabled = True
        else:
            if self.toolbar.arrow_mode_enabled:
                self.toolbar.reset_arrow_state()

        # Restore screenshot mode
        if tab.screenshot_mode_active:
            self.toolbar.screenshot_mode_enabled = True
            self.toolbar.screenshot_btn.set_active(True)
        else:
            if self.toolbar.screenshot_mode_enabled:
                self._exit_screenshot_mode()

        # Restore texture mode
        if tab.texture_mode_active:
            self.toolbar.texture_mode_enabled = True
            self.toolbar.texture_btn.set_active(True)
            self._ensure_texture_panel_ready()
            self._apply_current_texture_settings()
        else:
            if self.toolbar.texture_mode_enabled:
                self._exit_texture_mode()

        # Coming back from Overview — make sure toolbar is visible
        self.toolbar.show()
        self.ruler_toolbar.setVisible(tab.ruler_active)
        self.sidebar_panel.show()

        # Keep QC panel thumbnail in sync when switching tabs while in project mode
        if self._current_mode == "project":
            try:
                self._push_viewers_to_project()
            except Exception:
                pass

        logger.info(f"_on_tab_changed: Switched to tab {index} ({tab.filename or 'Untitled'})")

    # ======================== Overview Tab ========================

    def _show_overview(self):
        """Switch viewer_stack to the Overview widget and refresh its cards."""
        # Capture a fresh thumbnail for whichever tab was previously active
        if 0 <= self.current_tab_index < len(self.tabs):
            self._capture_thumbnail_for(self.current_tab_index)

        # Hide toolbar/ruler while in overview (they don't apply here)
        self.toolbar.hide()
        self.ruler_toolbar.hide()
        self.right_panel_stack.hide()

        # Show overview full-width (collapse sidebar data)
        self.sidebar_panel.hide()

        self.viewer_stack.setCurrentWidget(self.overview_widget)
        self.overview_widget.refresh(self.tabs)
        self.setWindowTitle("LYNS — Overview")
        logger.info("_show_overview: Overview tab activated")

    def _on_overview_tab_requested(self, tab_index: int):
        """Jump to a regular tab when the user clicks its card in the Overview."""
        if 0 <= tab_index < len(self.tabs):
            tab_bar_index = tab_index  # regular tabs have the same index in the tab bar
            self.tab_bar.setCurrentIndex(tab_bar_index)

    def _capture_thumbnail_for(self, tab_index: int):
        """Ask the viewer in the given tab to render a thumbnail and store it."""
        if tab_index < 0 or tab_index >= len(self.tabs):
            return
        tab = self.tabs[tab_index]
        vw = tab.viewer_widget
        if vw is None or tab.file_path is None:
            return
        if hasattr(vw, 'capture_thumbnail'):
            try:
                pix = vw.capture_thumbnail(480, 320)
                if pix and not pix.isNull():
                    tab.thumbnail = pix
            except Exception as e:
                logger.debug(f"_capture_thumbnail_for tab {tab_index}: {e}")

    def _capture_all_thumbnails(self):
        """Capture fresh thumbnails for every tab (called by Overview's Refresh button)."""
        for i in range(len(self.tabs)):
            self._capture_thumbnail_for(i)

    def _on_overview_rotate(self, tab_index: int, dx: float, dy: float):
        """Rotate camera and update thumbnail live at ~30 fps during drag."""
        if tab_index < 0 or tab_index >= len(self.tabs):
            return
        vw = self.tabs[tab_index].viewer_widget
        if vw is None or not hasattr(vw, '_on_gizmo_rotate'):
            return
        try:
            vw._on_gizmo_rotate(dx, dy)
            import time as _time
            now = _time.monotonic()
            if not hasattr(self, '_overview_thumb_times'):
                self._overview_thumb_times = {}
            last = self._overview_thumb_times.get(tab_index, 0.0)
            if now - last >= 0.033:   # ~30 fps cap
                self._overview_thumb_times[tab_index] = now
                self._refresh_overview_card(tab_index)
        except Exception as e:
            logger.debug(f"_on_overview_rotate: {e}")

    def _on_overview_drag_released(self, tab_index: int):
        """Drag ended — do one GPU capture and update the card with the final view."""
        self._refresh_overview_card(tab_index)

    def _refresh_overview_card(self, tab_index: int):
        """Re-capture thumbnail for one tab and push it to the overview card."""
        if tab_index < 0 or tab_index >= len(self.tabs):
            return
        tab = self.tabs[tab_index]
        vw  = tab.viewer_widget
        if vw is None or not hasattr(vw, 'capture_thumbnail'):
            return
        try:
            pix = vw.capture_thumbnail()
            if pix and not pix.isNull():
                tab.thumbnail = pix
                self.overview_widget.update_card_thumbnail(tab_index, pix)
        except Exception as e:
            logger.debug(f"_refresh_overview_card tab {tab_index}: {e}")

    # ======================== Auto-Rotate ========================

    def _on_rotate_speed_changed(self, speed: float):
        """Live-update the rotation speed while rotating."""
        vw = self.viewer_widget
        if vw and hasattr(vw, 'set_rotate_speed'):
            vw.set_rotate_speed(speed)

    def _on_rotate_axis_changed(self, axis: str):
        """Switch the rotation axis live."""
        vw = self.viewer_widget
        if vw and hasattr(vw, 'set_rotate_axis'):
            vw.set_rotate_axis(axis)

    def _toggle_rotate_mode(self):
        """Start or stop the turntable rotation."""
        vw = self.viewer_widget
        if self.toolbar.rotate_mode_enabled:
            if vw and hasattr(vw, 'start_auto_rotate') and vw.current_mesh is not None:
                vw.start_auto_rotate(
                    speed_deg_per_sec=float(self.toolbar._rotate_speed_slider.value()),
                    direction=self.record_panel.current_direction(),
                )
            else:
                # No mesh — revert button
                self.toolbar.reset_rotate_state()
        else:
            if vw and hasattr(vw, 'stop_auto_rotate'):
                vw.stop_auto_rotate()

    # ======================== Recording ========================

    def _toggle_record_mode(self):
        """Open the record panel (toolbar button). Recording starts only via the panel's Start button."""
        if self.toolbar.record_mode_enabled:
            self.record_panel.show_idle()
            self.right_panel_stack.setCurrentWidget(self.record_stack)
            self.right_panel_stack.show()
            self._restore_right_panel_width()
        else:
            self._exit_record_mode()

    def _on_panel_start_recording(self):
        """User clicked ▶ Start Recording inside the panel."""
        vw = self.viewer_widget
        if vw is None:
            return
        res = self.record_panel.current_resolution()
        fps = self.record_panel.current_fps()
        w, h = self._resolve_record_resolution(res, vw)
        if hasattr(vw, 'start_recording'):
            ok = vw.start_recording(width=w, height=h, fps=fps)
            if not ok:
                show_error_dialog(self, "Recording Error",
                                  "Could not initialise the offscreen renderer.")
                return
            if hasattr(vw, 'recording_frame_captured'):
                vw.recording_frame_captured.connect(self._on_recording_frame)
            if hasattr(vw, 'recording_error'):
                vw.recording_error.connect(self._on_recording_error)
        if self.record_panel.rotate_enabled():
            if hasattr(vw, 'start_auto_rotate') and vw.current_mesh is not None:
                vw.start_auto_rotate(
                    speed_deg_per_sec=self.record_panel.current_speed(),
                    direction=self.record_panel.current_direction(),
                )
                self.toolbar.rotate_mode_enabled = True
                self.toolbar.rotate_btn.set_active(True)
                self.toolbar.rotate_btn.set_label("Rotating…")
        self.record_panel.show_recording()
        self._record_stopped_tmp_path = ""
        logger.info("_on_panel_start_recording: recording started")

    def _on_panel_stop_recording(self):
        """User clicked ⏹ Stop — stop capture but keep temp file for Save/Discard."""
        vw = self.viewer_widget
        tmp_path = ""
        if vw and hasattr(vw, 'stop_recording'):
            try:
                tmp_path = vw.stop_recording()
            except Exception as e:
                logger.error(f"_on_panel_stop_recording: {e}")
            try:
                vw.recording_frame_captured.disconnect(self._on_recording_frame)
            except Exception:
                pass
            try:
                vw.recording_error.disconnect(self._on_recording_error)
            except Exception:
                pass
        if vw and hasattr(vw, 'stop_auto_rotate'):
            vw.stop_auto_rotate()
        self.toolbar.reset_rotate_state()
        self._record_stopped_tmp_path = tmp_path or ""
        self.record_panel.show_stopped()
        logger.info(f"_on_panel_stop_recording: tmp={tmp_path}")

    def _exit_record_mode(self):
        """Cancel / close record mode — stop any active capture and delete temp file."""
        import os
        vw = self.viewer_widget
        if vw and hasattr(vw, 'stop_recording'):
            try:
                tmp = vw.stop_recording()
                if tmp:
                    try:
                        os.unlink(tmp)
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"_exit_record_mode: stop_recording: {e}")
            try:
                vw.recording_frame_captured.disconnect(self._on_recording_frame)
            except Exception:
                pass
            try:
                vw.recording_error.disconnect(self._on_recording_error)
            except Exception:
                pass
        # Also clean up any leftover stopped-but-unsaved temp file
        if self._record_stopped_tmp_path:
            try:
                os.unlink(self._record_stopped_tmp_path)
            except Exception:
                pass
            self._record_stopped_tmp_path = ""
        if vw and hasattr(vw, 'stop_auto_rotate'):
            vw.stop_auto_rotate()
        self.toolbar.reset_rotate_state()
        self.record_panel.show_idle()
        self.right_panel_stack.setCurrentWidget(self._right_panel_placeholder)
        self.right_panel_stack.hide()
        self.toolbar.reset_record_state()

    def _on_panel_save_recording(self):
        """User clicked 💾 Save Video after stopping — prompt for path and move temp file."""
        import os, shutil
        tmp_path = self._record_stopped_tmp_path
        self._record_stopped_tmp_path = ""

        save_path, _ = get_save_file_name(
            self, "Save Recording", "", "MP4 Video (*.mp4)"
        )
        if save_path:
            if not save_path.lower().endswith(".mp4"):
                save_path += ".mp4"
            try:
                if tmp_path and os.path.exists(tmp_path):
                    shutil.move(tmp_path, save_path)
                    show_message_dialog(self, "Recording Saved",
                                       f"Video saved to:\n{save_path}")
                else:
                    show_error_dialog(self, "Recording Error",
                                      "No video data was found.")
            except Exception as e:
                show_error_dialog(self, "Save Failed", str(e))
        else:
            # User cancelled — delete temp
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

        self.record_panel.show_idle()
        self.right_panel_stack.setCurrentWidget(self._right_panel_placeholder)
        self.right_panel_stack.hide()
        self.toolbar.reset_record_state()

    def _on_panel_discard_recording(self):
        """User clicked Discard after stopping — delete temp file and close panel."""
        import os
        tmp_path = self._record_stopped_tmp_path
        self._record_stopped_tmp_path = ""
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        self.record_panel.show_idle()
        self.right_panel_stack.setCurrentWidget(self._right_panel_placeholder)
        self.right_panel_stack.hide()
        self.toolbar.reset_record_state()

    def _on_recording_frame(self, frame_count: int):
        """Update the record panel's live frame counter."""
        self.record_panel.update_frame_count(frame_count)

    def _on_recording_error(self, message: str):
        """Show recording error and exit mode."""
        show_error_dialog(self, "Recording Error", message)
        self._exit_record_mode()

    def _on_record_panel_rotate_toggled(self, enabled: bool):
        """Checkbox in record panel toggled rotate on/off."""
        vw = self.viewer_widget
        if enabled:
            if vw and hasattr(vw, 'start_auto_rotate') and vw.current_mesh is not None:
                vw.start_auto_rotate(
                    speed_deg_per_sec=self.record_panel.current_speed(),
                    direction=self.record_panel.current_direction(),
                )
                self.toolbar.rotate_mode_enabled = True
                self.toolbar.rotate_btn.set_active(True)
                self.toolbar.rotate_btn.set_label("Rotating…")
        else:
            if vw and hasattr(vw, 'stop_auto_rotate'):
                vw.stop_auto_rotate()
            self.toolbar.reset_rotate_state()

    def _on_record_panel_speed_changed(self, speed: float):
        """Speed slider in record panel moved."""
        vw = self.viewer_widget
        if vw and hasattr(vw, 'set_rotate_speed'):
            vw.set_rotate_speed(speed)

    def _on_record_panel_direction_changed(self, direction: int):
        """Direction toggle in record panel changed."""
        vw = self.viewer_widget
        if vw and hasattr(vw, 'set_rotate_direction'):
            vw.set_rotate_direction(direction)

    @staticmethod
    def _resolve_record_resolution(res: str, vw) -> tuple:
        """Convert resolution label to (width, height)."""
        if res == "720p":
            return (1280, 720)
        if res == "1080p":
            return (1920, 1080)
        # 'viewport' — use current canvas size
        try:
            w, h = vw._canvas.get_logical_size()
            return (int(w), int(h))
        except Exception:
            return (0, 0)

    def _scale_export(self):
        """Export the scaled drawing with measurements."""
        if not self.scale_canvas.has_image():
            return
        path, _ = get_save_file_name(
            self, "Export Scaled Drawing", "",
            "PNG Image (*.png);;JPEG Image (*.jpg);;PDF Document (*.pdf)"
        )
        if path:
            success, result = self.scale_canvas.export_scaled(path)
            if success:
                logger.info(f"Scaled drawing exported to: {result}")
            else:
                logger.error(f"Export failed: {result}")

    def _scale_add_ref(self):
        """Add an extra draggable reference line to the scale canvas."""
        self.scale_canvas.add_extra_ref_line()

    def _save_current_tab_state(self):
        """Save mode flags from the current tab before switching."""
        tab = self._current_tab
        if tab is None:
            return
        tab.ruler_active = self.toolbar.ruler_mode_enabled
        tab.annotation_mode_active = self.toolbar.annotation_mode_enabled
        tab.arrow_mode_active = self.toolbar.arrow_mode_enabled
        tab.parts_mode_active = getattr(self.toolbar, 'parts_mode_enabled', False)
        tab.screenshot_mode_active = self.toolbar.screenshot_mode_enabled
        tab.texture_mode_active = getattr(self.toolbar, 'texture_mode_enabled', False)
        tab.draw_mode_active = self.toolbar.draw_mode_enabled
        tab.screenshots = list(self.screenshot_panel.screenshots)

    def _on_tab_close_requested(self, index: int):
        """Handle tab close button click."""
        if index == self._plus_tab_index:
            return  # Can't close "+" tab
        if index == self._overview_tab_index:
            return  # Can't close the Overview tab
        if index < 0 or index >= len(self.tabs):
            return
        
        tab = self.tabs[index]
        
        # Check for unsaved annotations
        annotations = tab.annotation_panel.get_annotations()
        if annotations and not tab.annotations_exported:
            choice = ask_yes_no_cancel_dialog(
                self,
                "Unsaved Annotations",
                f"Tab '{tab.filename or 'Untitled'}' has {len(annotations)} annotation(s) that have not been exported.\n\n"
                "Would you like to export them as .lyns before closing?\n\n"
                "• Click 'Yes' to export first\n"
                "• Click 'No' to close without exporting\n"
                "• Click 'Cancel' to go back",
            )
            if choice == 'yes':
                # Switch to this tab first so sidebar export works
                self.tab_bar.setCurrentIndex(index)
                self.sidebar_panel.export_as_ecto()
                return
            elif choice == 'cancel':
                return
        
        self._close_tab(index)
    
    def _close_tab(self, index: int):
        """Close and destroy a tab at the given index."""
        tab = self.tabs[index]
        
        # Cleanup ecto temp dir
        if tab.ecto_temp_dir:
            try:
                from core.ecto_format import EctoFormat
                EctoFormat.cleanup_temp_dir(tab.ecto_temp_dir)
            except Exception:
                pass
        
        # Remove widgets from stacks
        self.viewer_stack.removeWidget(tab.viewer_widget)
        self.annotation_stack.removeWidget(tab.annotation_panel)
        self.arrow_stack.removeWidget(tab.arrow_panel)
        self.parts_stack.removeWidget(tab.parts_panel)

        # Close this tab's WebGPU render canvas explicitly (synchronously,
        # via .close()) before scheduling the widget tree's deletion below.
        # rendercanvas tracks every canvas in a loop-wide weak registry that
        # only forgets a canvas once .close() has run; a canvas whose C++
        # object gets torn down by plain deleteLater() first — without ever
        # going through .close() — stays in that registry as a dangling
        # entry. Nothing touches it again until the app quits, at which
        # point rendercanvas's own aboutToQuit handler iterates the
        # registry and crashes on it ("wrapped C/C++ object ... has been
        # deleted"), even though the crash's real cause was a tab closed
        # much earlier in the session. See the matching cleanup in
        # closeEvent for the same reasoning applied to tabs still open at
        # quit time.
        canvas = getattr(tab.viewer_widget, '_canvas', None)
        if canvas is not None:
            try:
                canvas.close()
            except Exception:
                pass

        # Destroy widgets
        tab.viewer_widget.deleteLater()
        tab.annotation_panel.deleteLater()
        tab.arrow_panel.deleteLater()
        tab.parts_panel.deleteLater()
        
        # Remove from lists
        self.tabs.pop(index)
        
        # Remove tab from tab bar
        self.tab_bar.blockSignals(True)
        self.tab_bar.removeTab(index)
        self._overview_tab_index -= 1
        self._plus_tab_index -= 1
        self.tab_bar.blockSignals(False)
        
        # If no tabs left, create a new empty one
        if len(self.tabs) == 0:
            self.current_tab_index = -1
            self._create_new_tab()
        else:
            # Adjust current index
            if self.current_tab_index >= len(self.tabs):
                self.current_tab_index = len(self.tabs) - 1
            elif self.current_tab_index > index:
                self.current_tab_index -= 1
            elif self.current_tab_index == index:
                self.current_tab_index = min(index, len(self.tabs) - 1)
            
            self.tab_bar.blockSignals(True)
            self.tab_bar.setCurrentIndex(self.current_tab_index)
            self.tab_bar.blockSignals(False)
            self._on_tab_changed(self.current_tab_index)

        if self._current_mode == "project":
            try:
                self._push_viewers_to_project()
            except Exception:
                pass

        logger.info(f"_close_tab: Closed tab {index}")
    
    def _find_empty_tab(self) -> int:
        """Find an empty (no file loaded) tab. Returns index or -1."""
        for i, tab in enumerate(self.tabs):
            if tab.file_path is None:
                return i
        return -1
    
    # ======================== Viewer / Annotation Signal Wiring ========================
    
    def _connect_viewer_signals_for(self, viewer):
        """Connect viewer widget signals for drag-and-drop."""
        if hasattr(viewer, 'file_dropped'):
            viewer.file_dropped.connect(self._load_dropped_file)
        if hasattr(viewer, 'click_to_upload'):
            viewer.click_to_upload.connect(self.upload_stl_file)
        if hasattr(viewer, 'drop_error'):
            viewer.drop_error.connect(self._show_drop_error)
        if hasattr(viewer, 'material_preset_applied'):
            viewer.material_preset_applied.connect(self._on_material_preset_applied)
    
    def _connect_annotation_panel_signals_for(self, tab: TabState):
        """Connect annotation panel signals for a specific tab."""
        panel = tab.annotation_panel
        panel.annotation_added.connect(self._on_annotation_added)
        panel.annotation_deleted.connect(self._on_annotation_deleted)
        panel.annotation_validated.connect(self._on_annotation_validated)
        # Annotation color changes from panel -> update viewer marker
        if hasattr(panel, 'annotation_color_changed'):
            panel.annotation_color_changed.connect(self._on_annotation_color_changed)
        panel.open_popup_requested.connect(self._on_open_popup_requested)
        panel.open_viewer_popup_requested.connect(self._on_open_viewer_popup_requested)
        panel.focus_annotation.connect(self._on_focus_annotation)
        panel.annotation_hovered.connect(self._on_annotation_hovered)
        panel.exit_annotation_mode.connect(self._exit_annotation_mode)
        panel.clear_all_requested.connect(self._on_clear_all_requested)
    
    def apply_styling(self):
        """Apply minimalistic styling with floating card design."""
        self.setStyleSheet(get_global_stylesheet())

    def _on_annotation_color_changed(self, annotation_id: int, color: str):
        """Update the viewer's annotation marker color when panel emits a change."""
        vw = getattr(self, 'viewer_widget', None)
        if vw and hasattr(vw, 'update_annotation_marker_color'):
            try:
                vw.update_annotation_marker_color(annotation_id, color)
            except Exception:
                logger.exception("_on_annotation_color_changed: failed to update viewer color")
    
    def eventFilter(self, obj, event):
        """Resize education watermark overlay when workspace stack resizes."""
        if is_education() and hasattr(self, '_edu_workspace_watermark') and obj is self._workspace_stack and event.type() == QEvent.Resize:
            self._edu_workspace_watermark.setGeometry(0, 0, self._workspace_stack.width(), self._workspace_stack.height())
            self._edu_workspace_watermark.raise_()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        """Trigger viewer render on resize (Windows black screen fix)."""
        super().resizeEvent(event)
        if sys.platform == 'win32' and self.viewer_widget and getattr(self.viewer_widget, 'plotter', None):
            QTimer.singleShot(100, self._trigger_viewer_render)
    
    def changeEvent(self, event):
        """Trigger viewer render on maximize (Windows black screen fix)."""
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange and sys.platform == 'win32' and self.isMaximized():
            QTimer.singleShot(200, self._trigger_viewer_render)
    
    def _trigger_viewer_render(self):
        """Force VTK refresh on viewer (called after resize/maximize)."""
        vw = self.viewer_widget
        plotter = getattr(vw, 'plotter', None) if vw else None
        if plotter is not None:
            try:
                import vtk
                picker = vtk.vtkPropPicker()
                picker.Pick(0, 0, 0, plotter.renderer)
            except Exception as e:
                logger.debug(f"trigger pick: {e}")
            try:
                bg = getattr(plotter, 'background_color', 'white')
                plotter.background_color = bg
                ren = getattr(plotter, 'renderer', None)
                if ren is not None and hasattr(ren, 'ResetCameraClippingRange'):
                    ren.ResetCameraClippingRange()
                if hasattr(vw, '_sync_overlay_viewport'):
                    vw._sync_overlay_viewport()
                plotter.render()
            except Exception as e:
                logger.warning(f"maximize render: {e}")
    
    def _connect_toolbar_signals(self):
        """Connect toolbar signals to handler methods."""
        self.toolbar.toggle_grid.connect(self._toggle_grid)
        self.toolbar.toggle_theme.connect(self._toggle_theme)
        self.toolbar.render_mode_changed.connect(self._set_render_mode)
        self.toolbar.reset_rotation.connect(self._reset_rotation)
        self.toolbar.view_front.connect(self._view_front)
        self.toolbar.view_rear.connect(self._view_rear)
        self.toolbar.view_left.connect(self._view_left)
        self.toolbar.view_right.connect(self._view_right)
        self.toolbar.view_top.connect(self._view_top)
        self.toolbar.view_bottom.connect(self._view_bottom)
        self.toolbar.toggle_fullscreen.connect(self._toggle_fullscreen)
        self.toolbar.toggle_ruler.connect(self._toggle_ruler_mode)
        self.toolbar.toggle_screenshot.connect(self._toggle_screenshot_mode)
        self.toolbar.toggle_texture.connect(self._toggle_texture_mode)
        self.toolbar.toggle_annotation.connect(self._toggle_annotation_mode)
        self.toolbar.toggle_arrow.connect(self._toggle_arrow_mode)
        self.toolbar.toggle_draw.connect(self._toggle_draw_mode)
        self.toolbar.toggle_parts.connect(self._toggle_parts_mode)
        self.toolbar.draw_color_changed.connect(self._on_draw_color_changed)
        self.toolbar.draw_eraser_toggled.connect(self._on_draw_eraser_toggled)
        self.toolbar.draw_text_toggled.connect(self._on_draw_text_toggled)
        self.toolbar.draw_font_size_changed.connect(self._on_draw_font_size_changed)
        self.toolbar.draw_undo_requested.connect(self._on_draw_undo)
        self.toolbar.draw_undo_text_requested.connect(self._on_draw_undo_text)
        self.toolbar.draw_clear_requested.connect(self._on_draw_clear)
        self.toolbar.draw_color_picker_requested.connect(self.toolbar.show_draw_color_picker)
        self.toolbar.load_file.connect(self.upload_stl_file)
        self.toolbar.clear_model.connect(self._clear_current_model)
        self.toolbar.toggle_rotate.connect(self._toggle_rotate_mode)
        self.toolbar.rotate_speed_changed.connect(self._on_rotate_speed_changed)
        self.toolbar.rotate_axis_changed.connect(self._on_rotate_axis_changed)
        self.toolbar.toggle_record.connect(self._toggle_record_mode)
        self.toolbar.open_converter.connect(self._open_converter_dialog)
    
    def _connect_ruler_toolbar_signals(self):
        """Connect ruler toolbar signals to handler methods."""
        self.ruler_toolbar.view_front.connect(self._ruler_view_front)
        self.ruler_toolbar.view_left.connect(self._ruler_view_left)
        self.ruler_toolbar.view_right.connect(self._ruler_view_right)
        self.ruler_toolbar.view_top.connect(self._ruler_view_top)
        self.ruler_toolbar.view_bottom.connect(self._ruler_view_bottom)
        self.ruler_toolbar.view_rear.connect(self._ruler_view_rear)
        self.ruler_toolbar.clear_measurements.connect(self._clear_measurements)
        self.ruler_toolbar.exit_ruler.connect(self._exit_ruler_mode)
        self.ruler_toolbar.unit_changed.connect(self._ruler_unit_changed)
    
    def _clear_current_model(self, skip_confirmation=False):
        """Clear the current model from the viewer."""
        logger.info("_clear_current_model: Clearing current model...")
        
        if self.annotation_panel is None or self.viewer_widget is None:
            return
        
        if not skip_confirmation:
            annotations = self.annotation_panel.get_annotations()
            if annotations:
                if not self._annotations_exported:
                    choice = ask_yes_no_cancel_dialog(
                        self,
                        "Unsaved Annotations",
                        f"You have {len(annotations)} annotation(s) that have not been exported.\n\n"
                        "Would you like to export them as .ecto before clearing?\n\n"
                        "• Click 'Yes' to export first\n"
                        "• Click 'No' to clear without exporting\n"
                        "• Click 'Cancel' to go back",
                    )
                    if choice == 'yes':
                        self.sidebar_panel.export_as_ecto()
                        return
                    elif choice == 'cancel':
                        return
                else:
                    if not ask_yes_no_dialog(
                        self,
                        "Clear Model",
                        f"You have {len(annotations)} annotation(s). Are you sure you want to clear everything?",
                    ):
                        return
        
        # Screenshot warning (second warning, after annotation)
        if not skip_confirmation and len(self.screenshot_panel.screenshots) > 0:
            n = len(self.screenshot_panel.screenshots)
            msg = f"You have {n} screenshot(s) that have not been saved. They will be removed. Continue?"
            if not confirm_dialog(self, "Unsaved Screenshots", msg):
                return
        
        # Clear the viewer
        if hasattr(self.viewer_widget, 'clear_viewer'):
            self.viewer_widget.clear_viewer()
        
        # Update toolbar state
        self.toolbar.set_stl_loaded(False)
        self.setWindowTitle("LYNS")
        self.toolbar.set_loaded_filename(None)
        
        # Clear all annotations from panel and viewer
        self._clear_all_annotations()
        
        # Clear ruler measurements and exit ruler mode if active
        if hasattr(self.viewer_widget, 'clear_measurements'):
            self.viewer_widget.clear_measurements()
        if self.toolbar.ruler_mode_enabled:
            self._exit_ruler_mode()
        
        # Hide annotation panel if visible
        if self.annotation_panel.isVisible():
            self._exit_annotation_mode()
        
        # Exit parts mode and hide parts panel
        if self.toolbar.parts_mode_enabled:
            self.toolbar.parts_mode_enabled = False
            self._exit_parts_mode()
        
        # Exit screenshot mode if active and clear all screenshots
        if self.toolbar.screenshot_mode_enabled:
            self._exit_screenshot_mode()
        self.screenshot_panel.clear_all()
        
        # Reset sidebar panel dimensions and calculations
        self.sidebar_panel.reset_all_data()
        
        
        # Reset tab state
        tab = self._current_tab
        if tab:
            tab.file_path = None
            tab.filename = None
            tab.sidebar_data = None
            tab.mesh = None
            tab.annotations_exported = False
            tab.screenshots = []
            self.tab_bar.setTabText(self.current_tab_index, _ecto_tab_caption("Untitled"))
        
        logger.info("_clear_current_model: Model and all data cleared")
    
    def _connect_viewer_signals(self):
        """Connect viewer widget signals for drag-and-drop (legacy, used by property)."""
        vw = self.viewer_widget
        if vw is None:
            return
        if hasattr(vw, 'file_dropped'):
            vw.file_dropped.connect(self._load_dropped_file)
        if hasattr(vw, 'click_to_upload'):
            vw.click_to_upload.connect(self.upload_stl_file)
        if hasattr(vw, 'drop_error'):
            vw.drop_error.connect(self._show_drop_error)
    
    def _load_dropped_file(self, file_path):
        """Load a file that was dropped on the viewer."""
        logger.info(f"_load_dropped_file: Loading dropped file: {file_path}")
        
        file_ext = file_path.lower()
        if file_ext.endswith('.ecto') or file_ext.endswith('.lyns'):
            self._load_ecto_file(file_path)
            return

        if not (file_ext.endswith('.stl') or file_ext.endswith('.step') or file_ext.endswith('.stp') or file_ext.endswith('.3dm') or file_ext.endswith('.obj') or file_ext.endswith('.iges') or file_ext.endswith('.igs') or file_ext.endswith('.dxf')):
            show_warning_dialog(
                self,
                "Invalid File",
                "Please select a valid 3D file (.stl, .step, .stp, .3dm, .obj, .iges, .igs, .dxf, or .lyns extension)."
            )
            return

        # If current tab has a file, create a new tab; otherwise reuse empty tab
        tab = self._current_tab
        if tab and tab.file_path is not None:
            self._create_new_tab()
        
        self._load_file_into_current_tab(file_path, from_conversion=False)
    
    def _open_converter_dialog(self):
        """Open the file converter dialog."""
        from ui.converter_dialog import ConverterDialog
        # Pre-populate with current file if it's a convertible format
        preset = None
        if self._current_tab and self._current_tab.file_path:
            ext = self._current_tab.file_path.lower()
            if ext.endswith('.3dm') or ext.endswith('.step') or ext.endswith('.stp'):
                preset = self._current_tab.file_path
        dlg = ConverterDialog(self, preset_file=preset)
        dlg.conversion_complete.connect(self._load_converted_file)
        dlg.exec_()

    def _load_converted_file(self, output_path: str):
        """Load a file that was created by the Convert File flow."""
        if self._current_mode != "3d":
            self._switch_mode("3d")
        if self._current_tab and self._current_tab.file_path is not None:
            self._create_new_tab()
        self._load_file_into_current_tab(output_path, from_conversion=True)
    
    def _open_file_from_project(self, file_path: str):
        """Open a file from the Files & Versions screen in the 3D viewer."""
        import os
        if not os.path.exists(file_path):
            from ui.modal_utils import show_message_dialog
            show_message_dialog(self, "File Not Found",
                                f"The file could not be found on disk:\n{file_path}")
            return
        self._switch_mode("3d")
        ext = file_path.lower()
        if ext.endswith('.ecto') or ext.endswith('.lyns'):
            self._load_ecto_file(file_path)
        else:
            if self._current_tab and self._current_tab.file_path is not None:
                self._create_new_tab()
            self._load_file_into_current_tab(file_path, from_conversion=False)

    def _restore_viewer_tab_from_project(self, tmp_path: str, original_name: str, tab_id: str = ''):
        """Open a viewer tab restored from a saved project's .lyns bundle.

        The bundle is written to a randomly-named temp file, so unlike
        _open_file_from_project we can't derive a sensible tab name from the
        path itself — it would show up as e.g. "tmpvl4chzig.ecto" instead of
        the model's real name (e.g. "test.stl"). Pass the original name through
        explicitly instead.

        tab_id — this tab's stable identity from the save file (see
        core/project_merge.py's viewer_tabs merger). Carried through onto
        the restored TabState so the NEXT save reuses the same id instead
        of minting a new one, which is what lets the merge engine recognize
        this as "the same tab, possibly edited" across two devices/sessions
        rather than treating every reload as a brand-new tab. Empty for
        saves written before tabs had stable ids — falls back to a fresh
        one, same as any other genuinely-new tab.
        """
        import os
        if not os.path.exists(tmp_path):
            return
        self._switch_mode("3d")
        self._load_tab_bundle(tmp_path, original_name, tab_id)

    def _load_tab_bundle(self, tmp_path: str, original_name: str, tab_id: str = ''):
        """Decode+load one viewer-tab bundle into the tab structure, without
        touching which workspace mode is currently visible. Split out of
        _restore_viewer_tab_from_project (which switches to 3D mode first,
        appropriate when opening a project) so
        _reconcile_viewer_tabs_after_merge can reuse the same load logic
        for a save-time merge fixup — that one must NOT yank the user into
        a different workspace mode mid-task, since Save can be triggered
        from anywhere."""
        import os
        if not os.path.exists(tmp_path):
            return
        # force_editable=True — this bundle is the project's own tab, being
        # restored on whichever device opened the project, never a file
        # someone shared with this user (see _load_ecto_file's docstring).
        self._load_ecto_file(tmp_path, display_name_override=original_name, force_editable=True)
        if self._current_tab is not None:
            self._current_tab.tab_id = tab_id or uuid.uuid4().hex

    def _reconcile_viewer_tabs_after_merge(self, updated: list, removed_ids: list):
        """Bring the live 3D viewer back in sync right after a save's merge
        changed a tab's content out from under this session — see
        TheProjectWidget.viewer_tabs_conflict_resolved's docstring. Runs
        silently in the background tab structure without switching
        workspace mode (see _load_tab_bundle). Reopens each affected tab
        from scratch (close + restore) rather than hot-swapping the live
        pygfx scene in place — simpler and far lower-risk, and this only
        ever runs right after a rare merge conflict."""
        import base64, os, tempfile

        def _index_by_id():
            return {t.tab_id: i for i, t in enumerate(self.tabs) if t.tab_id}

        for tid in removed_ids:
            idx = _index_by_id().get(tid)
            if idx is not None:
                self._close_tab(idx)

        for entry in updated:
            tid = entry.get('id')
            idx = _index_by_id().get(tid)
            if idx is not None:
                self._close_tab(idx)

            b64 = entry.get('bundle_b64', '')
            if not b64:
                continue
            fd, tmp_path = tempfile.mkstemp(suffix='.lyns')
            os.close(fd)
            try:
                Path(tmp_path).write_bytes(base64.b64decode(b64))
                self._load_tab_bundle(tmp_path, entry.get('tab_name', 'model.lyns'), tid or '')
            except Exception as e:
                logger.warning(f'_reconcile_viewer_tabs_after_merge: could not restore '
                                f'"{entry.get("tab_name")}": {e}')
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

        logger.info(f"_reconcile_viewer_tabs_after_merge: updated={len(updated)} removed={len(removed_ids)}")

    def _on_tab_screenshots_merged(self, tab_id: str):
        """A supplier-review import (ui/project_widget.py's
        _merge_supplier_annotations) just appended new screenshots onto
        the tab with this tab_id. screenshot_panel is one shared widget
        that only repaints from tab.screenshots on tab switch — if the
        merged-into tab is the one currently visible, refresh it now so
        the new screenshot shows up immediately instead of only after
        switching tabs away and back."""
        tab = self._current_tab
        if tab is not None and getattr(tab, 'tab_id', None) == tab_id:
            self.screenshot_panel.set_screenshots(tab.screenshots)

    def _restore_technical_overview_from_project(self, tmp_path: str):
        """Restore the Technical Overview workspace from a saved project's
        embedded .ecto bundle. Same import path as opening a standalone
        technical .ecto file (_load_technical_ecto), minus the passcode
        prompt — project saves never set a passcode on this bundle."""
        if not os.path.exists(tmp_path):
            return
        from core.ecto_format import EctoFormat
        doc_path, annotations, metadata, passcode_hash, temp_dir = EctoFormat.import_technical(tmp_path)
        if doc_path is None:
            logger.warning(f"_restore_technical_overview_from_project: import failed: {temp_dir}")
            return
        self.technical_overview.load_from_ecto(doc_path, annotations or [], passcode_hash)
        if metadata:
            self.technical_sidebar.set_metadata(metadata)
        self._tech_ecto_temp_dir = temp_dir

    def _restore_drawing_scale_from_project(self, tmp_path: str, state: dict, file_name: str = ''):
        """Restore the Drawing Scale workspace from a saved project's
        embedded source file + calibration/shapes state.

        ScaleCanvas keeps referencing tmp_path as its source file (unlike the
        viewer tabs / technical overview, which extract into their own
        throwaway storage), so we take ownership of it here instead of the
        caller deleting it — cleaned up on app close alongside
        _tech_ecto_temp_dir, and any previous one is cleaned up now.

        file_name — the file's real name, passed through as load_file's
        display_name so ScaleCanvas doesn't mistake tmp_path's randomly
        generated basename for it (see ScaleCanvas.get_source_filename).
        """
        if not os.path.exists(tmp_path):
            return
        old_tmp = getattr(self, '_scale_temp_path', None)
        if old_tmp and old_tmp != tmp_path and os.path.exists(old_tmp):
            try:
                os.remove(old_tmp)
            except OSError:
                pass
        self._scale_temp_path = tmp_path
        self.scale_canvas.load_file(tmp_path, display_name=file_name or None)
        self.scale_canvas.set_state(state)
        self.scale_sidebar.set_state(
            unit=state.get('unit', 'cm'),
            scale_ratio=state.get('scale_ratio', 1.0),
            show_static_border=state.get('show_static_border', True),
            show_moving_border=state.get('show_moving_border', True),
            show_ref_lines=state.get('show_ref_lines', True),
            pdf_locked=state.get('pdf_locked', False),
        )

    # ── LYNS Lite: Supplier Review Workflow (open/save a .lyns.review) ─────

    def _lite_has_review_loaded(self) -> bool:
        return getattr(self, '_lite_review_envelope', None) is not None

    def _lite_confirm_discard(self) -> bool:
        """Whatever's currently open (3D tabs, QC comments/photos, any
        feedback not yet saved back) belongs to the review being replaced.
        Lite has no reliable per-field dirty-tracking the way the full
        project editor does (see TheProjectWidget._unsaved_changes — never
        set by the supplier-feedback composer or new-pin flows), so unlike
        project_widget's own _confirm_discard this always asks whenever a
        review is loaded, rather than trying to guess if anything changed."""
        from ui.modal_utils import MessageModal, BaseModal
        dlg = MessageModal(
            self, t('project.msg.unsaved_title'), t('project.msg.unsaved_body'),
            theme=BaseModal.LIGHT,
            primary_text=t('project.msg.unsaved_discard'),
            secondary_text=t('common.cancel'),
        )
        result = {'discard': False}
        dlg.primary_btn.clicked.connect(lambda: (result.update(discard=True), dlg.accept()))
        if dlg.secondary_btn:
            dlg.secondary_btn.clicked.connect(lambda: (result.update(discard=False), dlg.reject()))
        dlg.exec_()
        return result['discard']

    def _lite_new_project(self):
        """LYNS Lite's File > New Review — close whatever's currently
        loaded and return to a blank workspace, ready to open a different
        review without it combining with the one just closed."""
        if self._lite_has_review_loaded() and not self._lite_confirm_discard():
            return
        # Reuses TheProjectWidget's own reset (clears every viewer tab, QC,
        # Technical Overview, Drawing Scale, and the project-info card) —
        # its own _unsaved_changes guard is a no-op here since Lite never
        # sets that flag, so this proceeds straight to the reset.
        self.project_widget._on_new_project()
        self._lite_review_path = None
        self._lite_review_envelope = None
        self.setWindowTitle("LYNS Lite")
        logger.info("_lite_new_project: workspace reset")

    def _lite_open_review(self):
        """LYNS Lite's File > Open Review — pick a .lyns.review file and
        load it. See _lite_load_review_file for what actually happens."""
        if self._lite_has_review_loaded() and not self._lite_confirm_discard():
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self, t('mode_bar.lite_open_review'), '',
            'LYNS Review (*.lyns.review);;All Files (*)'
        )
        if not file_path:
            return
        self._lite_load_review_file(file_path)

    def _lite_load_review_file(self, file_path: str):
        """Decode a .lyns.review envelope and load each section into the
        same widgets a full LYNS360 project would use — just restricted to
        what TheProjectWidget shows when is_lite() (see its _build_ui):
        only the Quality Control nav item, plus the always-present 3D
        Viewer / Technical Overview / Drawing Scale workspaces. Also used
        for the file-association double-click open path (see main.py).

        Each 3D tab is loaded with force_reader_mode=True — a supplier
        review is never "this machine's own editable project," even when
        LYNS360 and Lite happen to run on the same machine (see
        _load_ecto_file's docstring for why the plain creator_token check
        isn't enough on its own). The PM's existing annotations stay
        locked; the Lite-only "can still add new pins" bypass lives in
        ui/toolbar.py's set_reader_mode, and the "can still attach
        feedback to an existing pin" composer lives in
        ui/annotation_viewer_popup.py's AnnotationViewerPopup.

        Always resets the workspace first (see TheProjectWidget._on_new_project)
        regardless of what was open before — opening a second review used to
        just load its viewer tabs/QC/etc. on top of whatever the first one
        left behind, so two reviews' 3D tabs and Quality Control data ended
        up combined in one workspace instead of the second one replacing
        the first. Confirming whether to discard unsaved work is the
        caller's job (see _lite_open_review) — by the time this runs, the
        decision to load has already been made, so this proceeds unconditionally.
        """
        import base64
        import tempfile
        from core.review_format import load_review_file
        try:
            envelope = load_review_file(file_path)
        except Exception as e:
            logger.error(f'_lite_load_review_file: failed to read {file_path}: {e}')
            show_error_dialog(self, "Error", f"Failed to open .lyns.review file:\n{e}")
            return

        self.project_widget._on_new_project()

        # Kept around for _lite_save_review to preserve supplier/original
        # filename/exported_by and to know which tab_ids to re-bundle.
        self._lite_review_path = file_path
        self._lite_review_envelope = envelope

        # A review can bundle more than one open 3D model — each becomes its
        # own tab (see ui/export_review_dialog.py's multi-select tab picker).
        viewer_tabs = envelope.get('viewer_tabs') or []
        if viewer_tabs:
            self._switch_mode("3d")
        for viewer_tab in viewer_tabs:
            if not viewer_tab.get('bundle_b64'):
                continue
            fd, tmp_path = tempfile.mkstemp(suffix='.lyns')
            os.close(fd)
            try:
                Path(tmp_path).write_bytes(base64.b64decode(viewer_tab['bundle_b64']))
                self._load_ecto_file(
                    tmp_path,
                    display_name_override=viewer_tab.get('tab_name'),
                    force_editable=False,
                    force_reader_mode=True,
                )
                if self._current_tab is not None:
                    self._current_tab.tab_id = viewer_tab.get('id') or uuid.uuid4().hex
            except Exception as e:
                logger.warning(f'_lite_load_review_file: could not load a viewer tab: {e}')
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

        technical_overview = envelope.get('technical_overview')
        if technical_overview and technical_overview.get('bundle_b64'):
            fd, tmp_path = tempfile.mkstemp(suffix='.ecto')
            os.close(fd)
            try:
                Path(tmp_path).write_bytes(base64.b64decode(technical_overview['bundle_b64']))
                self._restore_technical_overview_from_project(tmp_path)
            except Exception as e:
                logger.warning(f'_lite_load_review_file: could not load technical_overview: {e}')
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

        drawing_scale = envelope.get('drawing_scale')
        if drawing_scale and drawing_scale.get('file_b64'):
            ext = drawing_scale.get('file_ext') or '.png'
            fd, tmp_path = tempfile.mkstemp(suffix=ext)
            os.close(fd)
            try:
                Path(tmp_path).write_bytes(base64.b64decode(drawing_scale['file_b64']))
                # Takes ownership of tmp_path — does not delete it (see its own docstring).
                self._restore_drawing_scale_from_project(
                    tmp_path, drawing_scale.get('state', {}), drawing_scale.get('file_name', '')
                )
            except Exception as e:
                logger.warning(f'_lite_load_review_file: could not load drawing_scale: {e}')

        qc_data = envelope.get('quality_control')
        if qc_data is not None:
            qc_widget = self.project_widget._ensure_screen('quality_control')
            if hasattr(qc_widget, 'set_data'):
                qc_widget.set_data(qc_data)

        # Report — always read-only in Lite (locked once at _build_ui time,
        # see TheProjectWidget's is_lite() branch), so this just needs the
        # data loaded in, same as QC above.
        report_data = envelope.get('report')
        if report_data is not None:
            report_widget = self.project_widget._ensure_screen('report')
            if hasattr(report_widget, 'set_data'):
                report_widget.set_data(report_data)

        project_info = envelope.get('project_info')
        if project_info is not None:
            self.project_widget._nav.set_info_data(project_info)
        self.project_widget._nav.set_read_only(True)

        self._switch_mode("project")
        original_name = envelope.get('original_filename') or 'Review'
        self.setWindowTitle(f"LYNS Lite - {original_name}")
        logger.info(f'_lite_load_review_file: loaded {file_path}')

    def _lite_save_review_as(self):
        """LYNS Lite's File > Save Review As — always prompts for a new
        location, even when a review is already loaded from/saved to one."""
        self._lite_save_review(force_dialog=True)

    def _lite_save_review(self, force_dialog: bool = False):
        """LYNS Lite's File > Save Review — re-bundles every open 3D tab that
        came from the review, Technical Overview, Drawing Scale, and the QC
        screen's current data (which is where the supplier's comments/
        control-point edits live) back into a .lyns.review file, preserving
        the supplier/original_filename/exported_by identity from whatever
        was opened.

        force_dialog — Save Review As (see above): always ask where to
        save, even if this review already has a known path."""
        envelope_in = getattr(self, '_lite_review_envelope', None)
        if envelope_in is None:
            from ui.modal_utils import show_message_dialog
            show_message_dialog(self, t('mode_bar.lite_save_review'), t('export_review.no_tabs'))
            return

        # Fresh tab snapshot before bundling — same reasoning as every other
        # save path (see TheProjectWidget.viewer_tabs_sync_requested's docstring).
        self.project_widget.viewer_tabs_sync_requested.emit()
        original_ids = [vt.get('id') for vt in (envelope_in.get('viewer_tabs') or []) if vt.get('id')]
        viewer_tabs = [
            entry for tid in original_ids
            if (entry := self.project_widget.bundle_viewer_tab_by_id(tid)) is not None
        ]
        if not viewer_tabs:
            viewer_tabs = envelope_in.get('viewer_tabs') or []

        qc_widget = self.project_widget._ensure_screen('quality_control')
        quality_control = qc_widget.get_data() if hasattr(qc_widget, 'get_data') else None

        technical_overview = self.project_widget._bundle_technical_overview()
        drawing_scale = self.project_widget._bundle_drawing_scale()

        from core.review_format import build_review_envelope, save_review_file, ensure_review_extension
        envelope_out = build_review_envelope(
            exported_by=envelope_in.get('exported_by', ''),
            original_filename=envelope_in.get('original_filename', 'project'),
            supplier=envelope_in.get('supplier', {}),
            viewer_tabs=viewer_tabs,
            technical_overview=technical_overview or envelope_in.get('technical_overview'),
            drawing_scale=drawing_scale or envelope_in.get('drawing_scale'),
            quality_control=quality_control if quality_control is not None else envelope_in.get('quality_control'),
            project_info=envelope_in.get('project_info'),
            # Report is locked read-only for the whole Lite session (see
            # TheProjectWidget's is_lite() branch) — nothing to re-bundle,
            # just carry the original data through unchanged.
            report=envelope_in.get('report'),
        )

        path = None if force_dialog else getattr(self, '_lite_review_path', None)
        if not path:
            default_name = os.path.basename(getattr(self, '_lite_review_path', None) or 'review.lyns.review')
            path, _ = QFileDialog.getSaveFileName(
                self, t('mode_bar.lite_save_review_as' if force_dialog else 'mode_bar.lite_save_review'),
                default_name, 'LYNS Review (*.lyns.review);;All Files (*)'
            )
            if not path:
                return
            path = ensure_review_extension(path)

        try:
            save_review_file(envelope_out, path)
        except Exception as e:
            logger.error(f'_lite_save_review: failed to write {path}: {e}')
            show_error_dialog(self, "Error", f"Failed to save .lyns.review file:\n{e}")
            return

        self._lite_review_path = path
        self._lite_review_envelope = envelope_out
        logger.info(f'_lite_save_review: saved {path}')
        from ui.modal_utils import show_message_dialog
        show_message_dialog(
            self, t('mode_bar.lite_save_review'),
            t('export_review.success').format(filename=os.path.basename(path))
        )

    def _clear_all_viewer_tabs(self):
        """Close every currently open viewer tab.

        Called right before a project's saved tabs are restored — otherwise
        whatever was already open in this session (e.g. models added via
        Quality Control) stays open alongside the restored ones, so opening
        a 2-tab project on top of 2 already-open tabs ends up showing 4.
        _close_tab auto-creates a fresh blank tab once the list empties out;
        that's the desired end state (ready to receive the first restored tab).
        """
        while len(self.tabs) > 1:
            self._close_tab(0)
        if self.tabs and self.tabs[0].file_path is not None:
            self._close_tab(0)

    def _load_file_into_current_tab(self, file_path: str, from_conversion: bool = False):
        """Load a 3D file into the current tab's viewer."""
        tab = self._current_tab
        if tab is None or tab.viewer_widget is None:
            return

        if self._current_mode == 'project' and hasattr(self, 'project_widget'):
            self.project_widget.show_qc_loading()

        # In project mode the viewer stack is hidden, so showEvent never fires on a newly
        # created tab's viewer.  Force-init it so load_stl() doesn't spend 5 s timing out.
        if not getattr(tab.viewer_widget, '_initialized', True):
            if hasattr(tab.viewer_widget, 'force_init'):
                tab.viewer_widget.force_init()

        success = tab.viewer_widget.load_stl(file_path)

        if self._current_mode == 'project' and hasattr(self, 'project_widget'):
            self.project_widget.hide_qc_loading()

        if not success:
            file_ext = file_path.lower()
            if file_ext.endswith('.step') or file_ext.endswith('.stp'):
                file_type = "STEP"
            elif file_ext.endswith('.3dm'):
                file_type = "3DM"
            elif file_ext.endswith('.obj'):
                file_type = "OBJ"
            elif file_ext.endswith('.iges') or file_ext.endswith('.igs'):
                file_type = "IGES"
            else:
                file_type = "STL"
            show_error_dialog(
                self,
                "Error",
                f"Failed to load {file_type} file:\n{file_path}\n\nPlease ensure the file is a valid {file_type} format."
            )
        else:
            filename = Path(file_path).name
            tab.file_path = file_path
            tab.filename = filename
            tab.loaded_via_conversion = from_conversion
            self.tab_bar.setTabText(self.current_tab_index, _ecto_tab_caption(filename))

            self.setWindowTitle(f"LYNS - {filename}")
            self.toolbar.set_loaded_filename(filename)
            self.toolbar.set_stl_loaded(True)
            
            # Update dimensions display and cache
            if hasattr(tab.viewer_widget, 'current_mesh'):
                mesh = tab.viewer_widget.current_mesh
                if mesh is not None:
                    mesh_data = MeshCalculator.get_mesh_data(mesh)
                    tab.sidebar_data = mesh_data
                    tab.mesh = mesh
                    self.sidebar_panel.update_dimensions(mesh_data, file_path)
            
            # Load any existing annotations for this file
            self._load_annotations_for_file(file_path)
            
            # Check if model is 2D and update tab state
            if hasattr(tab.viewer_widget, '_current_is_2d'):
                tab.is_2d_model = tab.viewer_widget._current_is_2d
            
            # Keep 3D view aligned with toolbar (default visual style is shaded)
            self._set_render_mode(self.toolbar.render_mode)

            # Ensure initial shading matches current texture panel slider defaults
            self._apply_current_texture_settings()
            
            # Update UI state for 2D models
            if hasattr(self.sidebar_panel, 'set_2d_mode'):
                self.sidebar_panel.set_2d_mode(tab.is_2d_model)

            # Capture thumbnail after model renders (slight delay so GPU has time)
            QTimer.singleShot(800, lambda idx=self.current_tab_index: self._capture_thumbnail_for(idx))

            # Keep QC model selector strip in sync after any file load
            try:
                self._push_viewers_to_project()
            except Exception:
                pass

    def _show_drop_error(self, error_msg):
        """Show an error message from drag-and-drop."""
        show_warning_dialog(self, "Upload Error", error_msg)
    
    def _toggle_grid(self):
        """Toggle the background grid."""
        vw = self.viewer_widget
        if vw is None:
            return
        if hasattr(vw, 'toggle_grid') and callable(getattr(vw, 'toggle_grid', None)):
            try:
                vw.toggle_grid()
            except Exception as e:
                logger.warning(f"Could not toggle grid (pygfx): {e}")
            return
        if hasattr(vw, 'plotter') and vw.plotter is not None:
            try:
                if self.toolbar.grid_enabled:
                    vw.plotter.show_grid()
                else:
                    vw.plotter.remove_bounds_axes()
            except Exception as e:
                logger.warning(f"Could not toggle grid: {e}")
    
    def _toggle_theme(self):
        """Toggle between light and dark viewer theme."""
        vw = self.viewer_widget
        if vw is None:
            return
        if hasattr(vw, 'set_background_color'):
            try:
                color = '#1a1a2e' if self.toolbar.dark_theme else '#ffffff'
                vw.set_background_color(color)
            except Exception as e:
                logger.warning(f"Could not toggle theme (pygfx): {e}")
            return
        if hasattr(vw, 'plotter') and vw.plotter is not None:
            try:
                if self.toolbar.dark_theme:
                    vw.plotter.background_color = '#1a1a2e'
                else:
                    vw.plotter.background_color = 'white'
            except Exception as e:
                logger.warning(f"Could not toggle theme: {e}")
    
    def _set_render_mode(self, mode):
        """Set render mode: solid, wireframe, or shaded."""
        vw = self.viewer_widget
        if vw is None:
            return
        if hasattr(vw, 'set_render_mode'):
            vw.set_render_mode(mode)
            return
        if hasattr(vw, 'current_actor') and vw.current_actor is not None:
            try:
                prop = vw.current_actor.GetProperty()
                if mode == 'wireframe':
                    prop.SetRepresentationToSurface()
                    prop.EdgeVisibilityOff()
                    prop.SetRepresentationToWireframe()
                elif mode == 'shaded':
                    prop.SetRepresentationToSurface()
                    prop.EdgeVisibilityOff()
                    prop.SetInterpolationToFlat()
                    prop.SetColor(0.72, 0.72, 0.76)
                    prop.SetAmbient(0.25)
                    prop.SetDiffuse(0.55)
                    prop.SetSpecular(0.65)
                    prop.SetSpecularPower(90)
                else:
                    prop.SetRepresentationToSurface()
                    prop.EdgeVisibilityOff()
                    prop.SetInterpolationToFlat()
                    prop.SetColor(0.68, 0.85, 0.90)
                    prop.SetAmbient(0.7)
                    prop.SetDiffuse(0.4)
                    prop.SetSpecular(0.2)
                    prop.SetSpecularPower(20)
                vw.plotter.render()
            except Exception as e:
                logger.warning(f"Could not set render mode: {e}")
    
    def _reset_rotation(self):
        """Reset view to default isometric rotation and clear drawings."""
        vw = self.viewer_widget
        if vw is None:
            return
        # Exit parts mode and hide the parts panel
        if self.toolbar.parts_mode_enabled:
            self.toolbar.parts_mode_enabled = False
            self._exit_parts_mode()
            self._save_current_tab_state()
        if hasattr(vw, 'clear_drawings'):
            try:
                vw.clear_drawings()
            except Exception as e:
                logger.warning(f"Could not clear drawings: {e}")
        if hasattr(vw, 'reset_view'):
            try:
                vw.reset_view()
            except Exception as e:
                logger.warning(f"Could not reset rotation (pygfx): {e}")
            return
        if hasattr(vw, 'plotter') and vw.plotter is not None:
            try:
                vw.plotter.reset_camera()
                vw.plotter.view_isometric()
            except Exception as e:
                logger.warning(f"Could not reset rotation: {e}")
    
    def _sync_ruler_toolbar_view(self, view_name):
        """Sync ruler toolbar active button when view changes from main toolbar."""
        if self.toolbar.ruler_mode_enabled and self.ruler_toolbar.isVisible():
            self.ruler_toolbar._update_view_buttons(view_name)

    def _ensure_ruler_mode_for_view(self):
        """If not in ruler mode, enable it so 6 views use orthographic projection."""
        vw = self.viewer_widget
        if vw is None:
            return
        if not self.toolbar.ruler_mode_enabled and hasattr(vw, 'enable_ruler_mode'):
            success = vw.enable_ruler_mode()
            if success:
                self.toolbar.ruler_mode_enabled = True
                self.toolbar.ruler_btn.set_active(True)
                self.toolbar.ruler_btn.set_icon("📐")
                self.toolbar.ruler_btn.set_label("Ruler")
                self.ruler_toolbar.show()

    def _view_front(self):
        """Set camera to front orthographic view."""
        vw = self.viewer_widget
        if vw is None:
            return
        if hasattr(vw, 'view_front_ortho'):
            self._ensure_ruler_mode_for_view()
            vw.view_front_ortho()
            self._sync_ruler_toolbar_view("front")
            return
        if hasattr(vw, 'plotter') and vw.plotter is not None:
            try:
                vw.plotter.view_yz()
            except Exception as e:
                logger.warning(f"Could not set front view: {e}")
    
    def _view_rear(self):
        vw = self.viewer_widget
        if vw is None:
            return
        if hasattr(vw, 'view_rear_ortho'):
            self._ensure_ruler_mode_for_view()
            vw.view_rear_ortho()
            self._sync_ruler_toolbar_view("rear")
    
    def _view_left(self):
        vw = self.viewer_widget
        if vw is None:
            return
        if hasattr(vw, 'view_left_ortho'):
            self._ensure_ruler_mode_for_view()
            vw.view_left_ortho()
            self._sync_ruler_toolbar_view("left")
    
    def _view_right(self):
        vw = self.viewer_widget
        if vw is None:
            return
        if hasattr(vw, 'view_right_ortho'):
            self._ensure_ruler_mode_for_view()
            vw.view_right_ortho()
            self._sync_ruler_toolbar_view("right")
    
    def _view_top(self):
        vw = self.viewer_widget
        if vw is None:
            return
        if hasattr(vw, 'view_top_ortho'):
            self._ensure_ruler_mode_for_view()
            vw.view_top_ortho()
            self._sync_ruler_toolbar_view("top")
            return
        if hasattr(vw, 'plotter') and vw.plotter is not None:
            try:
                vw.plotter.view_xy()
            except Exception as e:
                logger.warning(f"Could not set top view: {e}")
    
    def _view_bottom(self):
        vw = self.viewer_widget
        if vw is None:
            return
        if hasattr(vw, 'view_bottom_ortho'):
            self._ensure_ruler_mode_for_view()
            vw.view_bottom_ortho()
            self._sync_ruler_toolbar_view("bottom")
    
    # ========== Ruler Mode Methods ==========
    
    def _toggle_ruler_mode(self):
        """Toggle ruler/measurement mode."""
        vw = self.viewer_widget
        if vw is None:
            return
        if self.toolbar.ruler_mode_enabled:
            if hasattr(vw, 'enable_ruler_mode'):
                success = vw.enable_ruler_mode()
                if success:
                    logger.info("_toggle_ruler_mode: Showing ruler toolbar, setting front view")
                    self.ruler_toolbar.show()
                    self.ruler_toolbar.reset_to_front()
                    self._ruler_view_front()
                    QTimer.singleShot(100, self._ruler_view_front)
                    logger.info("_toggle_ruler_mode: Ruler mode enabled (front view set, deferred at 100ms)")
                else:
                    self.toolbar.ruler_mode_enabled = False
                    self.toolbar.ruler_btn.set_active(False)
                    logger.warning("_toggle_ruler_mode: Failed to enable ruler mode")
        else:
            self._exit_ruler_mode()
    
    def _exit_ruler_mode(self):
        """Exit ruler mode and restore normal view."""
        vw = self.viewer_widget
        if vw and hasattr(vw, 'disable_ruler_mode'):
            vw.disable_ruler_mode()
        self.ruler_toolbar.hide()
        self.toolbar.ruler_mode_enabled = False
        self.toolbar.ruler_btn.set_active(False)
        self.toolbar.ruler_btn.set_icon("📏")
        logger.info("_exit_ruler_mode: Ruler mode disabled")
    
    def _ruler_view_front(self):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'view_front_ortho'):
            vw.view_front_ortho()
    
    def _ruler_view_left(self):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'view_left_ortho'):
            vw.view_left_ortho()
    
    def _ruler_view_right(self):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'view_right_ortho'):
            vw.view_right_ortho()
    
    def _ruler_view_top(self):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'view_top_ortho'):
            vw.view_top_ortho()
    
    def _ruler_view_bottom(self):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'view_bottom_ortho'):
            vw.view_bottom_ortho()
    
    def _ruler_view_rear(self):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'view_rear_ortho'):
            vw.view_rear_ortho()
    
    def _clear_measurements(self):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'clear_measurements'):
            vw.clear_measurements()
    
    def _ruler_unit_changed(self, unit_key):
        vw = self.viewer_widget
        if vw and hasattr(vw, '_ruler_unit'):
            vw._ruler_unit = unit_key
            logger.info(f"_ruler_unit_changed: Unit set to {unit_key}")
    
    # ========== Annotation Mode Methods ==========
    
    def _connect_annotation_panel_signals(self):
        """Legacy: connect annotation panel signals (no longer used directly, see _connect_annotation_panel_signals_for)."""
        pass
    
    def _toggle_annotation_mode(self):
        """Toggle annotation mode."""
        vw = self.viewer_widget
        if vw is None:
            return
        if self.toolbar.annotation_mode_enabled:
            if hasattr(vw, 'enable_annotation_mode'):
                success = vw.enable_annotation_mode(
                    callback=self._on_annotation_point_picked
                )
                if success:
                    # Always exit screenshot mode - toolbar clears screenshot_mode_enabled before we run,
                    # so we must call _exit_screenshot_mode to hide zoom/overlay on the viewer
                    self._exit_screenshot_mode()
                    self.annotation_panel.show()
                    self.right_panel_stack.setCurrentWidget(self.annotation_stack)
                    self.right_panel_stack.show()
                    if self.toolbar.ruler_mode_enabled:
                        self._exit_ruler_mode()
                    if getattr(vw, 'draw_mode', False):
                        self._exit_draw_mode()
                    if hasattr(vw, 'reframe_for_viewport'):
                        QTimer.singleShot(50, vw.reframe_for_viewport)
                    logger.info("_toggle_annotation_mode: Annotation mode enabled")
                else:
                    self.toolbar.reset_annotation_state()
                    logger.warning("_toggle_annotation_mode: Failed to enable annotation mode")
        else:
            self._exit_annotation_mode()
    
    def _exit_annotation_mode(self):
        """Exit annotation mode; keep annotations saved and visible on the model."""
        vw = self.viewer_widget
        if vw and hasattr(vw, 'disable_annotation_mode'):
            vw.disable_annotation_mode()
        if self.annotation_panel:
            self.annotation_panel.hide()
        if self.toolbar.screenshot_mode_enabled:
            self.right_panel_stack.setCurrentWidget(self.screenshot_stack)
            self.right_panel_stack.show()
        else:
            self.right_panel_stack.setCurrentWidget(self._right_panel_placeholder)
            self.right_panel_stack.hide()
        if vw and hasattr(vw, 'reframe_for_viewport'):
            QTimer.singleShot(50, vw.reframe_for_viewport)
        self.toolbar.reset_annotation_state()
        logger.info("_exit_annotation_mode: Annotation mode disabled, annotations kept")
    
    # ========== Arrow Mode Methods ==========

    def _toggle_arrow_mode(self):
        """Toggle 3D arrow placement mode with control panel."""
        vw = self.viewer_widget
        if vw is None:
            return
        tab = self._current_tab
        if tab is None:
            return
        if self.toolbar.arrow_mode_enabled:
            if hasattr(vw, 'enable_arrow_mode'):
                # Exit other modes FIRST
                if self.toolbar.annotation_mode_enabled:
                    self._exit_annotation_mode()
                if self.toolbar.ruler_mode_enabled:
                    self._exit_ruler_mode()
                if self.toolbar.screenshot_mode_enabled:
                    self._exit_screenshot_mode()
                if getattr(vw, 'draw_mode', False):
                    self._exit_draw_mode()
                # Set callback so viewer notifies us of new arrows
                vw._arrow_added_callback = lambda aid: self._on_arrow_placed(aid)
                success = vw.enable_arrow_mode()
                if success:
                    # Show arrow panel
                    tab.arrow_panel.show()
                    self.arrow_stack.setCurrentWidget(tab.arrow_panel)
                    self.right_panel_stack.setCurrentWidget(self.arrow_stack)
                    self.right_panel_stack.show()
                    if hasattr(vw, 'reframe_for_viewport'):
                        QTimer.singleShot(50, vw.reframe_for_viewport)
                    logger.info("_toggle_arrow_mode: Arrow mode enabled with panel")
                else:
                    self.toolbar.reset_arrow_state()
                    logger.warning("_toggle_arrow_mode: Failed to enable arrow mode")
        else:
            self._exit_arrow_mode()

    def _exit_arrow_mode(self):
        """Exit arrow mode; arrows remain visible."""
        vw = self.viewer_widget
        tab = self._current_tab
        if vw and hasattr(vw, 'disable_arrow_mode'):
            vw.disable_arrow_mode()
            vw._arrow_added_callback = None
        if tab and tab.arrow_panel:
            tab.arrow_panel.hide()
        # Restore right panel
        if self.toolbar.annotation_mode_enabled and tab:
            self.right_panel_stack.setCurrentWidget(self.annotation_stack)
            self.right_panel_stack.show()
        elif self.toolbar.screenshot_mode_enabled:
            self.right_panel_stack.setCurrentWidget(self.screenshot_stack)
            self.right_panel_stack.show()
        else:
            self.right_panel_stack.setCurrentWidget(self._right_panel_placeholder)
            self.right_panel_stack.hide()
        if vw and hasattr(vw, 'reframe_for_viewport'):
            QTimer.singleShot(50, vw.reframe_for_viewport)
        self.toolbar.reset_arrow_state()
        logger.info("_exit_arrow_mode: Arrow mode disabled")

    def _on_arrow_placed(self, arrow_id: int):
        """Called when the viewer places a new arrow on the model."""
        tab = self._current_tab
        if tab and tab.arrow_panel:
            tab.arrow_panel.add_arrow(arrow_id)

    def _connect_arrow_panel_signals_for(self, tab: TabState):
        """Connect arrow panel signals for a specific tab."""
        panel = tab.arrow_panel
        panel.rotate_requested.connect(lambda aid, axis, angle: self._arrow_rotate(aid, axis, angle))
        panel.scale_requested.connect(lambda aid, factor: self._arrow_scale(aid, factor))
        panel.move_requested.connect(lambda aid, dx, dy, dz: self._arrow_move(aid, dx, dy, dz))
        panel.color_changed.connect(lambda aid, color: self._arrow_set_color(aid, color))
        panel.delete_requested.connect(lambda aid: self._arrow_delete(aid))
        panel.label_changed.connect(lambda aid, val, unit: self._arrow_set_label(aid, val, unit))
        panel.clear_all_requested.connect(self._arrow_clear_all)
        panel.undo_last_requested.connect(self._arrow_undo_last)
        panel.exit_arrow_mode.connect(self._exit_arrow_mode_from_panel)

    def _exit_arrow_mode_from_panel(self):
        """Exit arrow mode triggered from the panel close button."""
        if self.toolbar.arrow_mode_enabled:
            self.toolbar.arrow_mode_enabled = False
            self.toolbar.reset_arrow_state()
        self._exit_arrow_mode()

    def _arrow_rotate(self, arrow_id, axis, angle):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'rotate_arrow'):
            vw.rotate_arrow(arrow_id, axis, angle)

    def _arrow_scale(self, arrow_id, factor):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'scale_arrow'):
            vw.scale_arrow(arrow_id, factor)

    def _arrow_move(self, arrow_id, dx, dy, dz):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'move_arrow'):
            vw.move_arrow(arrow_id, dx, dy, dz)

    def _arrow_set_color(self, arrow_id, color):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'set_arrow_color'):
            vw.set_arrow_color(arrow_id, color)

    def _arrow_set_label(self, arrow_id, value_text, unit):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'set_arrow_label'):
            vw.set_arrow_label(arrow_id, value_text, unit)



    def _arrow_delete(self, arrow_id):
        vw = self.viewer_widget
        tab = self._current_tab
        if vw and hasattr(vw, 'remove_arrow'):
            vw.remove_arrow(arrow_id)
        if tab and tab.arrow_panel:
            tab.arrow_panel.remove_arrow(arrow_id)

    def _arrow_clear_all(self):
        vw = self.viewer_widget
        tab = self._current_tab
        if vw and hasattr(vw, 'clear_all_arrows'):
            vw.clear_all_arrows()
        if tab and tab.arrow_panel:
            tab.arrow_panel.clear_all()

    def _arrow_undo_last(self):
        vw = self.viewer_widget
        tab = self._current_tab
        if vw and hasattr(vw, '_arrow_objects') and vw._arrow_objects:
            last_id = vw._arrow_objects[-1]['id']
            vw.remove_arrow(last_id)
            if tab and tab.arrow_panel:
                tab.arrow_panel.remove_arrow(last_id)

    # ========== Parts Mode Methods ==========

    def _toggle_parts_mode(self):
        """Toggle parts visibility panel."""
        vw = self.viewer_widget
        if vw is None:
            return
        tab = self._current_tab
        if tab is None:
            return
        if self.toolbar.parts_mode_enabled:
            # Exit other modes
            if self.toolbar.annotation_mode_enabled:
                self._exit_annotation_mode()
            if self.toolbar.arrow_mode_enabled:
                self._exit_arrow_mode()
            if self.toolbar.ruler_mode_enabled:
                self._exit_ruler_mode()
            if self.toolbar.screenshot_mode_enabled:
                self._exit_screenshot_mode()
            if getattr(vw, 'draw_mode', False):
                self._exit_draw_mode()
            # Clear any previous cards — panel starts empty, populated on click
            tab.parts_panel.clear_all()
            tab.parts_panel.show()
            self.parts_stack.setCurrentWidget(tab.parts_panel)
            self.right_panel_stack.setCurrentWidget(self.parts_stack)
            self.right_panel_stack.show()
            # Cache hierarchy data for on-click lookup
            has_hierarchy = hasattr(vw, 'get_parts_hierarchy')
            has_flat = hasattr(vw, 'get_parts_list')
            if has_hierarchy:
                self._cached_parts_hierarchy = vw.get_parts_hierarchy()
            elif has_flat:
                self._cached_parts_hierarchy = vw.get_parts_list()
            else:
                self._cached_parts_hierarchy = []
            # Enable click-to-select in 3D viewport
            if hasattr(vw, 'enable_parts_pick_mode'):
                vw.enable_parts_pick_mode()
            if hasattr(vw, 'reframe_for_viewport'):
                QTimer.singleShot(50, vw.reframe_for_viewport)
            logger.info("_toggle_parts_mode: Parts mode enabled")
        else:
            self._exit_parts_mode()

    def _exit_parts_mode(self):
        """Exit parts mode."""
        tab = self._current_tab
        vw = self.viewer_widget
        if tab and tab.parts_panel:
            tab.parts_panel.hide()
        # Disable click-to-select in 3D viewport
        if vw and hasattr(vw, 'disable_parts_pick_mode'):
            vw.disable_parts_pick_mode()
        # Restore all parts visible
        if vw and hasattr(vw, 'show_all_parts'):
            vw.show_all_parts()
        if vw and hasattr(vw, 'unhighlight_parts'):
            vw.unhighlight_parts()
        self.right_panel_stack.setCurrentWidget(self._right_panel_placeholder)
        self.right_panel_stack.hide()
        parent = self.right_panel_stack.parentWidget()
        if parent:
            parent.updateGeometry()
        if vw and hasattr(vw, 'reframe_for_viewport'):
            QTimer.singleShot(50, vw.reframe_for_viewport)
        self.toolbar.reset_parts_state()
        logger.info("_exit_parts_mode: Parts mode disabled")

    def _exit_parts_mode_from_panel(self):
        """Exit parts mode triggered from the panel close button."""
        if self.toolbar.parts_mode_enabled:
            self.toolbar.parts_mode_enabled = False
            self.toolbar.reset_parts_state()
        self._exit_parts_mode()

    def _connect_parts_panel_signals_for(self, tab: TabState):
        """Connect parts panel signals for a specific tab."""
        panel = tab.parts_panel
        panel.part_visibility_changed.connect(lambda pid, vis: self._part_set_visible(pid, vis))
        panel.part_selected.connect(lambda pid: self._part_select(pid))
        panel.group_selected.connect(lambda pids: self._group_select(pids))
        panel.show_all_requested.connect(self._parts_show_all)
        panel.hide_all_requested.connect(self._parts_hide_all)
        panel.invert_visibility_requested.connect(self._parts_invert)
        panel.isolate_selected_requested.connect(lambda pid: self._part_isolate(pid))
        panel.isolate_group_requested.connect(lambda pids: self._group_isolate(pids))
        panel.exit_parts_mode.connect(self._exit_parts_mode_from_panel)

        # Connect viewer part_clicked signal to panel selection
        vw = tab.viewer_widget
        if vw and hasattr(vw, 'part_clicked'):
            vw.part_clicked.connect(lambda pid, p=panel: self._on_viewer_part_clicked(pid, p))

    def _part_set_visible(self, part_id, visible):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'set_part_visible'):
            vw.set_part_visible(part_id, visible)

    def _part_select(self, part_id):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'highlight_part'):
            vw.highlight_part(part_id)

    def _group_select(self, part_ids):
        """Highlight all parts in a group."""
        vw = self.viewer_widget
        if vw and hasattr(vw, 'highlight_parts'):
            vw.highlight_parts(part_ids)

    def _on_viewer_part_clicked(self, part_id, panel):
        """Handle click on a part in the 3D viewer — add card if needed, then select."""
        # Find the hierarchy entry that owns this part_id
        item = self._find_hierarchy_entry_for(part_id)
        if item:
            panel.add_part(item)
            panel.select_part_by_id(part_id)

    def _find_hierarchy_entry_for(self, part_id):
        """Find the hierarchy entry (standalone or group) that contains part_id."""
        cached = getattr(self, '_cached_parts_hierarchy', [])
        for entry in cached:
            if entry['id'] == part_id:
                return entry
            if part_id in entry.get('child_ids', []):
                return entry
        return None

    def _parts_show_all(self):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'show_all_parts'):
            vw.show_all_parts()

    def _parts_hide_all(self):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'hide_all_parts'):
            vw.hide_all_parts()

    def _parts_invert(self):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'invert_parts_visibility'):
            vw.invert_parts_visibility()

    def _part_isolate(self, part_id):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'isolate_part'):
            vw.isolate_part(part_id)

    def _group_isolate(self, part_ids):
        """Isolate a group — show only its child parts."""
        vw = self.viewer_widget
        if vw and hasattr(vw, 'isolate_parts'):
            vw.isolate_parts(part_ids)
        elif vw:
            # Fallback: hide all, then show group parts
            if hasattr(vw, 'hide_all_parts'):
                vw.hide_all_parts()
            if hasattr(vw, 'set_part_visible'):
                for pid in part_ids:
                    vw.set_part_visible(pid, True)

    # ========== Screenshot Mode Methods ==========
    
    def _toggle_screenshot_mode(self):
        """Toggle screenshot capture mode."""
        vw = self.viewer_widget
        if vw is None:
            return
        if self.toolbar.screenshot_mode_enabled:
            if hasattr(vw, 'enable_screenshot_mode'):
                success = vw.enable_screenshot_mode()
                if success:
                    vw._screenshot_captured_callback = self._on_screenshot_captured
                    vw._screenshot_pending_cb = self._on_screenshot_pending
                    if self.toolbar.ruler_mode_enabled:
                        self._exit_ruler_mode()
                    # Use viewer state, not toolbar flag — toolbar clears
                    # annotation_mode_enabled before emitting toggle_screenshot,
                    # so the flag check would always be False and the annotation
                    # event filter would stay installed (clicks still annotate).
                    if getattr(vw, 'annotation_mode', False):
                        self._exit_annotation_mode()
                    if getattr(vw, 'draw_mode', False):
                        self._exit_draw_mode()
                    if getattr(vw, '_texture_drop_mode', False):
                        self._exit_texture_mode()
                    self.right_panel_stack.setCurrentWidget(self.screenshot_stack)
                    self.right_panel_stack.show()
                    self.screenshot_panel.show()
                    self._restore_right_panel_width()
                    if hasattr(vw, 'reframe_for_viewport'):
                        QTimer.singleShot(50, vw.reframe_for_viewport)
                    self._show_snip_trigger()
                    logger.info("_toggle_screenshot_mode: Screenshot mode enabled")
                else:
                    self.toolbar.reset_screenshot_state()
        else:
            self._exit_screenshot_mode()
    
    def _show_snip_trigger(self):
        from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction
        from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QBrush
        import sys, os
        from pathlib import Path
        if self._snip_trigger is None:
            # Build a list of candidate paths — try frozen _MEIPASS first,
            # then the source tree relative to this file, then cwd.
            _frozen_base = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else None
            _src_base    = Path(__file__).resolve().parent
            _cwd_base    = Path(os.getcwd())

            candidates = []
            for base in filter(None, [_frozen_base, _src_base, _cwd_base]):
                candidates.append(base / 'assets' / 'toolbar_icon.png')
            # On Windows also accept the bundled .ico as a second-resort
            if sys.platform == 'win32':
                for base in filter(None, [_frozen_base, _src_base, _cwd_base]):
                    candidates.append(base / 'assets' / 'icon.ico')

            pix = QPixmap()
            for candidate in candidates:
                if candidate.exists():
                    pix = QPixmap(str(candidate))
                    if not pix.isNull():
                        break

            # Scale to a crisp 32×32 for the Windows notification area
            if not pix.isNull() and sys.platform == 'win32':
                pix = pix.scaled(32, 32, Qt.KeepAspectRatio,
                                 Qt.SmoothTransformation)

            if pix.isNull():
                # Last-resort fallback: draw a solid ECTO-blue circle with "E"
                sz = 32
                pix = QPixmap(sz, sz)
                pix.fill(QColor(0, 0, 0, 0))
                p2 = QPainter(pix)
                p2.setRenderHint(QPainter.Antialiasing)
                p2.setBrush(QBrush(QColor('#2596BE')))
                p2.setPen(Qt.NoPen)
                p2.drawEllipse(0, 0, sz, sz)
                p2.setPen(QColor('white'))
                f2 = QFont()
                f2.setPointSize(14)
                f2.setBold(True)
                p2.setFont(f2)
                p2.drawText(pix.rect(), Qt.AlignCenter, 'E')
                p2.end()

            tray = QSystemTrayIcon(QIcon(pix), self)
            tray.setToolTip('ECTO · Screenshot mode — click to snip')

            menu = QMenu()
            snip_act = QAction('📷  Snip screenshot', self)
            snip_act.triggered.connect(self._start_snip)
            exit_act = QAction('✕  Exit screenshot mode', self)
            exit_act.triggered.connect(self._exit_screenshot_mode_from_tray)
            menu.addAction(snip_act)
            menu.addSeparator()
            menu.addAction(exit_act)
            tray.setContextMenu(menu)

            tray.activated.connect(self._on_tray_activated)
            self._snip_trigger = tray

        self._snip_trigger.show()

    def _on_tray_activated(self, reason):
        from PyQt5.QtWidgets import QSystemTrayIcon
        if reason == QSystemTrayIcon.Trigger:   # left-click
            self._start_snip()

    def _exit_screenshot_mode_from_tray(self):
        """Exit screenshot mode when triggered from the tray menu."""
        self.toolbar.screenshot_mode_enabled = False
        self.toolbar.reset_screenshot_state()
        self._exit_screenshot_mode()

    def _hide_snip_trigger(self):
        if self._snip_trigger is not None:
            self._snip_trigger.hide()
            self._snip_trigger.deleteLater()
            self._snip_trigger = None

    def _exit_screenshot_mode(self):
        """Exit screenshot mode."""
        self._hide_snip_trigger()
        vw = self.viewer_widget
        if vw and hasattr(vw, 'disable_screenshot_mode'):
            vw.disable_screenshot_mode()
            vw._screenshot_captured_callback = None
            vw._screenshot_pending_cb = None
        self.screenshot_panel.hide()
        if self.toolbar.annotation_mode_enabled:
            self.right_panel_stack.setCurrentWidget(self.annotation_stack)
            self.right_panel_stack.show()
        else:
            self.right_panel_stack.setCurrentWidget(self._right_panel_placeholder)
            self.right_panel_stack.hide()
        # Skip reframe_for_viewport: screenshot mode doesn't change viewport size,
        # and reframing recenters the camera (undoing user rotate/zoom) which causes
        # a noticeable delay/jump when switching back to render mode.
        if vw and hasattr(vw, '_canvas') and vw._canvas is not None:
            try:
                vw._canvas.request_draw()
            except Exception:
                pass
        self.toolbar.reset_screenshot_state()
        logger.info("_exit_screenshot_mode: Screenshot mode disabled")

    def _on_capture_desktop(self):
        """Minimize ECTO so the user can navigate to the app they want to capture."""
        self._show_tray_icon_hint()
        self.showMinimized()

    def _show_tray_icon_hint(self):
        """Show a small on-screen card with the actual tray icon, so the user can
        visually match it to what they'll see in the menu bar (OS notification
        banners don't reliably show a custom icon, so we draw our own).

        Uses a manual paintEvent instead of a stylesheet background — a top-level
        frameless window with WA_TranslucentBackground doesn't reliably paint a
        QSS background/border on macOS, but a QPainter-drawn rounded rect does."""
        from PyQt5.QtWidgets import QWidget, QLabel, QHBoxLayout
        from PyQt5.QtGui import QPainter, QColor, QPen
        from PyQt5.QtCore import Qt, QTimer

        if self._snip_trigger is None:
            return

        class _TrayHintCard(QWidget):
            def paintEvent(self, event):
                p = QPainter(self)
                p.setRenderHint(QPainter.Antialiasing)
                p.setBrush(QColor(34, 38, 44, 245))
                p.setPen(QPen(QColor(58, 64, 72), 1))
                p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 10, 10)

        popup = _TrayHintCard(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        popup.setAttribute(Qt.WA_TranslucentBackground)

        layout = QHBoxLayout(popup)
        layout.setContentsMargins(14, 10, 18, 10)
        layout.setSpacing(10)

        icon_label = QLabel()
        icon_label.setPixmap(self._snip_trigger.icon().pixmap(28, 28))
        icon_label.setStyleSheet("background: transparent;")
        layout.addWidget(icon_label)

        location = "menu bar" if sys.platform == 'darwin' else "taskbar (system tray)"
        text_label = QLabel(f"Look for this icon in the {location}, then click it to snip your screenshot")
        text_label.setWordWrap(True)
        text_label.setMaximumWidth(260)
        text_label.setStyleSheet("color: #E0ECF4; font-size: 13px; background: transparent;")
        layout.addWidget(text_label)

        popup.adjustSize()

        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.right() - popup.width() - 20
        # macOS menu bar is top-right; Windows system tray is bottom-right.
        y = screen.top() + 10 if sys.platform == 'darwin' else screen.bottom() - popup.height() - 10
        popup.move(x, y)
        popup.show()

        self._tray_hint_popup = popup  # keep a reference alive until it closes
        QTimer.singleShot(6000, popup.close)

    def _start_snip(self):
        """Fire the actual screen capture — called from the tray icon."""
        import tempfile, os, time as _time

        if self._snip_thread and self._snip_thread.isRunning():
            return   # already capturing

        path = os.path.join(
            tempfile.gettempdir(),
            f'ectoform_snip_{int(_time.time() * 1000)}.png'
        )

        self._hide_snip_trigger()
        self.showMinimized()

        thread = _ScreenshotThread(path, parent=self)
        thread.captured.connect(self._on_snip_done)
        thread.cancelled.connect(self._on_snip_cancelled)
        thread.finished.connect(thread.deleteLater)
        self._snip_thread = thread
        thread.start()

    def _on_snip_done(self, path):
        import os
        from PyQt5.QtGui import QPixmap
        pix = QPixmap(path)
        try:
            os.unlink(path)
        except OSError:
            pass
        self._snip_thread = None
        if sys.platform == 'darwin':
            self.showFullScreen()
        else:
            self.showMaximized()
        self.raise_()
        self.activateWindow()
        if self.toolbar.screenshot_mode_enabled:
            self._show_snip_trigger()
        if not pix.isNull():
            self.screenshot_panel.add_screenshot(pix)

    def _on_snip_cancelled(self):
        self._snip_thread = None
        if sys.platform == 'darwin':
            self.showFullScreen()
        else:
            self.showNormal()
        self.raise_()
        self.activateWindow()
        if self.toolbar.screenshot_mode_enabled:
            self._show_snip_trigger()

    def _save_screenshot_to_report(self, pixmap):
        """Send a screenshot pixmap to the first empty slot in the report photo section."""
        from ui.modal_utils import show_message_dialog, show_error_dialog
        rw = self.project_widget._screen_widgets.get('report')
        if rw is None:
            # Report screen not yet loaded — force it to initialise
            rw = self.project_widget._ensure_screen('report')
        if rw is None:
            show_error_dialog(self, "Report unavailable",
                              "Open the Report screen at least once before sending screenshots.")
            return
        ok = rw.add_screenshot_to_report(pixmap)
        if ok:
            show_message_dialog(self, "Saved to report",
                                "Screenshot added to the next available slot\nin the report's photo section.")
        else:
            show_error_dialog(self, "Could not save",
                              "Failed to write the screenshot into the report.")

    # ========== Texture Mode Methods ==========

    def _apply_current_texture_settings(self):
        """Apply current texture panel slider values to the active viewer."""
        try:
            if self.texture_panel and hasattr(self.texture_panel, 'emit_current_settings'):
                self.texture_panel.emit_current_settings()
            elif self.texture_panel and hasattr(self.texture_panel, '_emit_settings'):
                # Backward-compatible fallback
                self.texture_panel._emit_settings()
        except Exception as e:
            logger.warning(f"_apply_current_texture_settings: {e}")

    def _toggle_texture_mode(self):
        """Toggle texture application mode."""
        vw = self.viewer_widget
        if vw is None:
            return
        if self.toolbar.texture_mode_enabled:
            # Exit other modes
            if self.toolbar.annotation_mode_enabled:
                self._exit_annotation_mode()
            if self.toolbar.arrow_mode_enabled:
                self._exit_arrow_mode()
            if self.toolbar.ruler_mode_enabled:
                self._exit_ruler_mode()
            if getattr(vw, 'screenshot_mode', False):
                self._exit_screenshot_mode()
            if getattr(vw, 'draw_mode', False):
                self._exit_draw_mode()
            if self.toolbar.parts_mode_enabled:
                self.toolbar.parts_mode_enabled = False
                self._exit_parts_mode()
            # Enable texture drop on viewer
            if hasattr(vw, 'enable_texture_drop_mode'):
                vw.enable_texture_drop_mode()
            self._ensure_texture_panel_ready()
            self.texture_panel.show()
            self.right_panel_stack.setCurrentWidget(self.texture_stack)
            self.right_panel_stack.show()
            self._apply_current_texture_settings()
            logger.info("_toggle_texture_mode: Texture mode enabled")
        else:
            self._exit_texture_mode()

    def _exit_texture_mode(self):
        """Exit texture mode."""
        vw = self.viewer_widget
        if vw and hasattr(vw, 'disable_texture_drop_mode'):
            vw.disable_texture_drop_mode()
        self.texture_panel.hide()
        self.right_panel_stack.setCurrentWidget(self._right_panel_placeholder)
        self.right_panel_stack.hide()
        if vw and hasattr(vw, '_safe_set_aspect'):
            try:
                vw._safe_set_aspect()
            except Exception:
                pass
        if vw and hasattr(vw, '_canvas') and vw._canvas is not None:
            try:
                vw._canvas.request_draw()
            except Exception:
                pass
        self.toolbar.reset_texture_state()
        logger.info("_exit_texture_mode: Texture mode disabled")

    def _exit_texture_mode_from_panel(self):
        """Exit texture mode triggered from the panel close button."""
        if self.toolbar.texture_mode_enabled:
            self.toolbar.texture_mode_enabled = False
            self.toolbar.reset_texture_state()
        self._exit_texture_mode()

    def _on_texture_settings_changed(self, settings):
        """Forward texture slider settings to the active viewer widget."""
        vw = self.viewer_widget
        if vw and hasattr(vw, 'update_texture_settings'):
            vw.update_texture_settings(settings)

    def _on_reset_textures_requested(self):
        """Remove all applied textures from the active viewer (back to default)."""
        vw = self.viewer_widget
        if vw and hasattr(vw, 'reset_all_textures'):
            vw.reset_all_textures()

    def _on_material_preset_applied(self, preset_data):
        """Sync simplified material sliders when a preset is dropped onto the model."""
        if self.texture_panel and hasattr(self.texture_panel, 'sync_material_controls'):
            self.texture_panel.sync_material_controls(preset_data)

    # ========== Draw Mode Methods ==========
    
    def _toggle_draw_mode(self):
        """Toggle freehand draw mode."""
        vw = self.viewer_widget
        if vw is None:
            return
        if self.toolbar.draw_mode_enabled:
            if hasattr(vw, 'enable_draw_mode'):
                success = vw.enable_draw_mode()
                if success:
                    # Exit other modes
                    if self.toolbar.ruler_mode_enabled:
                        self._exit_ruler_mode()
                    if self.toolbar.annotation_mode_enabled:
                        self._exit_annotation_mode()
                    if self.toolbar.screenshot_mode_enabled or getattr(vw, "screenshot_mode", False):
                        self._exit_screenshot_mode()
                    logger.info("_toggle_draw_mode: Draw mode enabled")
                else:
                    self.toolbar.reset_draw_state()
                    logger.warning("_toggle_draw_mode: Failed to enable draw mode")
        else:
            self._exit_draw_mode()
    
    def _exit_draw_mode(self):
        """Exit draw mode."""
        vw = self.viewer_widget
        if vw and hasattr(vw, 'disable_draw_mode'):
            vw.disable_draw_mode()
        self.toolbar.reset_draw_state()
        logger.info("_exit_draw_mode: Draw mode disabled")
    
    def _on_draw_color_changed(self, color: str):
        """Handle draw color change from toolbar."""
        vw = self.viewer_widget
        if vw and hasattr(vw, 'set_draw_color'):
            vw.set_draw_color(color)

    def _on_draw_eraser_toggled(self, enabled: bool):
        """Handle eraser mode toggle."""
        vw = self.viewer_widget
        if vw and hasattr(vw, 'set_eraser_mode'):
            vw.set_eraser_mode(enabled)

    def _on_draw_text_toggled(self, enabled: bool):
        """Handle text placement mode toggle."""
        vw = self.viewer_widget
        if vw and hasattr(vw, 'set_text_mode'):
            vw.set_text_mode(enabled)

    def _on_draw_font_size_changed(self, multiplier: float):
        """Forward font-size multiplier to the active viewer."""
        vw = self.viewer_widget
        if vw and hasattr(vw, 'set_font_size_multiplier'):
            vw.set_font_size_multiplier(multiplier)

    def _on_draw_undo(self):
        """Undo last pen stroke."""
        vw = self.viewer_widget
        if vw and hasattr(vw, 'undo_last_stroke'):
            vw.undo_last_stroke()

    def _on_draw_undo_text(self):
        """Undo last placed text label."""
        vw = self.viewer_widget
        if vw and hasattr(vw, 'undo_last_text'):
            vw.undo_last_text()

    def _on_draw_clear(self):
        """Clear all drawn strokes."""
        vw = self.viewer_widget
        if vw and hasattr(vw, 'clear_drawings'):
            vw.clear_drawings()

    
    def _on_screenshot_pending(self):
        """Called the instant a screenshot region is released, before the heavy
        offscreen render runs — add a buffering placeholder card immediately."""
        return self.screenshot_panel.add_pending_card()

    def _on_screenshot_captured(self, pixmap, pending_token=None):
        """Handle a captured screenshot from the viewer overlay."""
        if pending_token is not None:
            self.screenshot_panel.complete_pending_card(pending_token, pixmap)
        else:
            self.screenshot_panel.add_screenshot(pixmap)
        logger.info("_on_screenshot_captured: Screenshot added to panel")

    def _on_annotation_point_picked(self, point: tuple):
        """Handle point picked for annotation - creates gray dot."""
        logger.info(f"_on_annotation_point_picked: Point picked at {point}")
        
        if self.annotation_panel is None:
            return
        
        annotation = self.annotation_panel.add_annotation(point)

        vw = self.viewer_widget
        if vw and hasattr(vw, 'add_annotation_marker'):
            display_num = self.annotation_panel.get_display_number(annotation.id)
            # Marker color follows the point's own auto-assigned color (see
            # AnnotationPanel.add_annotation) instead of always starting gray,
            # so the 3D marker matches the sidebar card right away.
            marker_color = annotation.color or PENDING_COLOR
            vw.add_annotation_marker(
                annotation.id, point, marker_color,
                display_date=str(display_num or len(self.annotation_panel.annotations))
            )
    
    def _on_annotation_added(self, annotation):
        logger.info(f"_on_annotation_added: Annotation {annotation.id} added")
        self._update_sidebar_annotation_count()
    
    def _on_annotation_deleted(self, annotation_id: int):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'remove_annotation_marker'):
            vw.remove_annotation_marker(annotation_id)
        if self.annotation_panel is None:
            return
        annotations = self.annotation_panel.get_annotations()
        if annotations and vw and hasattr(vw, 'update_annotation_labels_from_list'):
            reader_mode = self.annotation_panel.is_reader_mode()
            annotations_with_display = []
            for i, ann in enumerate(annotations):
                display_number = i + 1
                # An explicit/palette color (see AnnotationPanel.add_annotation)
                # always wins, in reader mode too — read/unread only decides
                # the fallback for annotations that never got one, same as
                # the sidebar card's own _get_indicator_color.
                if reader_mode:
                    color = getattr(ann, 'color', None) or (VALIDATED_COLOR if ann.is_read else PENDING_COLOR)
                else:
                    color = getattr(ann, 'color', None) or PENDING_COLOR
                annotations_with_display.append((ann.id, display_number, color))
            vw.update_annotation_labels_from_list(annotations_with_display)
        logger.info(f"_on_annotation_deleted: Annotation {annotation_id} removed, markers renumbered")
        self._update_sidebar_annotation_count()
    
    def _on_open_popup_requested(self, annotation_id: int):
        from ui.annotation_popup import AnnotationPopup
        
        if self.annotation_panel is None:
            return
        annotation = self.annotation_panel.get_annotation_by_id(annotation_id)
        if annotation is None:
            return
        
        display_num = self.annotation_panel.get_display_number(annotation.id)
        popup = AnnotationPopup(
            annotation_id=annotation.id,
            point=annotation.point,
            text=annotation.text,
            image_paths=annotation.image_paths,
            label=annotation.label,
            created_at=annotation.created_at,
            display_number=display_num,
            supplier_notes=annotation.supplier_notes,
            pm_notes=annotation.pm_notes,
            added_by=annotation.added_by,
            parent=self
        )

        popup.annotation_validated.connect(self._on_popup_validated)
        popup.annotation_deleted.connect(self._on_popup_deleted)
        popup.note_added.connect(self._on_annotation_pm_note_added)
        popup.finished.connect(lambda: self._on_annotation_popup_closed(annotation_id))
        
        vw = self.viewer_widget
        if vw and hasattr(vw, 'set_annotation_selected'):
            vw.set_annotation_selected(annotation_id, True)
        
        popup.show()
        logger.info(f"_on_open_popup_requested: Opened popup for annotation {annotation_id}")
    
    def _on_open_viewer_popup_requested(self, annotation_id: int):
        from ui.annotation_viewer_popup import AnnotationViewerPopup
        from core.edition import is_lite

        if self.annotation_panel is None:
            return
        annotation = self.annotation_panel.get_annotation_by_id(annotation_id)
        if annotation is None:
            return

        # Only set inside LYNS Lite with a review actually loaded — that's
        # what makes the popup show the "add your feedback" composer (see
        # AnnotationViewerPopup's docstring). Outside Lite this is a plain
        # read-only popup, same as always.
        current_supplier = None
        if is_lite():
            envelope = getattr(self, '_lite_review_envelope', None)
            if envelope:
                current_supplier = envelope.get('supplier')

        display_num = self.annotation_panel.get_display_number(annotation.id)
        popup = AnnotationViewerPopup(
            annotation_id=annotation.id,
            point=annotation.point,
            text=annotation.text,
            image_paths=annotation.image_paths,
            label=annotation.label,
            created_at=annotation.created_at,
            display_number=display_num,
            supplier_notes=annotation.supplier_notes,
            pm_notes=annotation.pm_notes,
            added_by=annotation.added_by,
            current_supplier=current_supplier,
            parent=self
        )
        popup.note_added.connect(self._on_annotation_note_added)

        self.annotation_panel.mark_as_read(annotation_id)
        vw = self.viewer_widget

        if vw and hasattr(vw, 'set_annotation_selected'):
            vw.set_annotation_selected(annotation_id, True)

        popup.finished.connect(lambda: self._on_annotation_popup_closed(annotation_id))
        popup.show()

        logger.info(f"_on_open_viewer_popup_requested: Opened viewer popup for annotation {annotation_id}")

    def _on_annotation_note_added(self, annotation_id: int, note: dict):
        """A supplier just submitted feedback on an existing annotation in
        LYNS Lite's AnnotationViewerPopup — store it on the live annotation
        so it's included the next time this tab is bundled (Save Review)."""
        if self.annotation_panel is not None:
            self.annotation_panel.add_supplier_notes(annotation_id, [note])

    def _on_annotation_pm_note_added(self, annotation_id: int, note: dict):
        """The PM just posted a follow-up comment on an existing annotation
        in LYNS360's AnnotationPopup — store it on the live annotation so
        it's included the next time this tab is exported (Export Review),
        letting the supplier see the PM's reply on their next Lite session."""
        if self.annotation_panel is not None:
            self.annotation_panel.add_pm_notes(annotation_id, [note])
    
    def _on_popup_validated(self, annotation_id: int, text: str, image_paths: list, label: str = "Point"):
        if self.annotation_panel:
            self.annotation_panel.validate_annotation(annotation_id, text, image_paths, label)
        vw = self.viewer_widget
        if vw and hasattr(vw, 'update_annotation_marker_color'):
            # No more "validated" marker color to switch to on Done — keep
            # whatever color the point already had (explicit pick, or the
            # auto-assigned palette color from AnnotationPanel.add_annotation),
            # same "explicit color wins" rule used everywhere else the marker
            # color is computed (e.g. after deleting/renumbering).
            annotation = self.annotation_panel.get_annotation_by_id(annotation_id) if self.annotation_panel else None
            marker_color = getattr(annotation, 'color', None) or PENDING_COLOR
            vw.update_annotation_marker_color(annotation_id, marker_color)
        logger.info(f"_on_popup_validated: Annotation {annotation_id} updated")
    
    def _on_popup_deleted(self, annotation_id: int):
        if self.annotation_panel:
            self.annotation_panel.remove_annotation(annotation_id)
        logger.info(f"_on_popup_deleted: Annotation {annotation_id} deleted from popup")
    
    def _on_annotation_popup_closed(self, annotation_id: int):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'set_annotation_selected'):
            vw.set_annotation_selected(annotation_id, False)
    
    def _on_annotation_validated(self, annotation_id: int, text: str, image_paths: list, label: str = "Point"):
        logger.info(f"_on_annotation_validated: Annotation {annotation_id} updated")
    
    def _on_focus_annotation(self, annotation_id: int):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'focus_on_annotation'):
            vw.focus_on_annotation(annotation_id)
    
    def _on_annotation_hovered(self, annotation_id: int, is_hovered: bool):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'set_annotation_selected'):
            vw.set_annotation_selected(annotation_id, is_hovered)
    
    def _refresh_annotation_markers(self):
        vw = self.viewer_widget
        if not vw or not hasattr(vw, 'clear_all_annotation_markers'):
            return
        vw.clear_all_annotation_markers()
        if self.annotation_panel is None:
            return
        annotations = self.annotation_panel.get_annotations()
        if not annotations:
            return
        reader_mode = self.annotation_panel.is_reader_mode()
        for i, ann in enumerate(annotations):
            display_number = i + 1
            # Explicit/palette color always wins, reader mode included —
            # see the matching comment in _on_annotation_deleted.
            if reader_mode:
                color = getattr(ann, 'color', None) or (VALIDATED_COLOR if ann.is_read else PENDING_COLOR)
            else:
                color = getattr(ann, 'color', None) or PENDING_COLOR
            if hasattr(vw, 'add_annotation_marker'):
                vw.add_annotation_marker(ann.id, ann.point, color, display_date=str(display_number))
    
    def _on_clear_all_requested(self):
        if self.annotation_panel is None:
            return
        annotations = self.annotation_panel.get_annotations()
        if annotations:
            if not self._annotations_exported:
                choice = ask_yes_no_cancel_dialog(
                    self,
                    "Unsaved Annotations",
                    f"You have {len(annotations)} annotation(s) that have not been exported.\n\n"
                    "Would you like to export them as .ecto before clearing?\n\n"
                    "• Click 'Yes' to export first\n"
                    "• Click 'No' to clear without exporting\n"
                    "• Click 'Cancel' to go back",
                )
                if choice == 'yes':
                    self.sidebar_panel.export_as_ecto()
                    return
                elif choice == 'cancel':
                    return
            else:
                if not ask_yes_no_dialog(
                    self,
                    "Clear All",
                    f"You have {len(annotations)} annotation(s). Are you sure you want to clear everything?",
                ):
                    return
        # Screenshot warning (second, after annotation)
        if len(self.screenshot_panel.screenshots) > 0:
            n = len(self.screenshot_panel.screenshots)
            if not confirm_dialog(self, "Unsaved Screenshots", f"You have {n} screenshot(s) that have not been saved. They will be removed. Continue?"):
                return
        self._clear_current_model(skip_confirmation=True)

    def _clear_all_annotations(self):
        vw = self.viewer_widget
        if vw and hasattr(vw, 'clear_all_annotation_markers'):
            vw.clear_all_annotation_markers()
        if self.annotation_panel:
            self.annotation_panel.clear_all()
        logger.info("_clear_all_annotations: All annotations cleared")
        self._update_sidebar_annotation_count()
    
    def _update_sidebar_annotation_count(self):
        if self.annotation_panel is None:
            return
        count = len(self.annotation_panel.annotations)
        self.sidebar_panel.update_annotation_count(count)
        if count > 0:
            self._annotations_exported = False
    
    def _on_annotations_exported(self):
        self._annotations_exported = True
        logger.info("_on_annotations_exported: Annotations have been exported")

    def _toggle_fullscreen(self):
        if self.toolbar.is_fullscreen:
            self.showFullScreen()
        else:
            self.showNormal()
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self.isFullScreen():
            self.showNormal()
            self.toolbar.reset_fullscreen_state()
        else:
            super().keyPressEvent(event)

    
    def _on_project_read_only_changed(self, read_only: bool):
        """Mirror project_widget's read-only state into the 3D viewer:
        grey out annotate/draw/render-style and block adding new 3D files
        (see TheProjectWidget.read_only_changed's docstring for why)."""
        self._read_only = read_only
        self.toolbar.set_read_only(read_only)

    def upload_stl_file(self):
        """Open file dialog and load selected 3D or .ecto file."""
        if getattr(self, '_read_only', False):
            # Reached via either the "+" tab or Quality Control's own Upload
            # button (project_widget.qc_upload_requested) — gate here once
            # rather than at each call site so no future caller can bypass it.
            logger.info("upload_stl_file: blocked — project is read-only")
            return
        logger.info("upload_stl_file: Opening file dialog...")
        file_path, _ = get_open_file_name(
            self,
            "Select 3D File",
            "",
            "All Supported (*.stl *.step *.stp *.3dm *.obj *.iges *.igs *.dxf *.lyns *.ecto);;LYNS Bundle (*.lyns *.ecto);;3D Files (*.stl *.step *.stp *.3dm *.obj *.iges *.igs *.dxf);;STL Files (*.stl);;STEP Files (*.step *.stp);;3DM Files (*.3dm);;OBJ Files (*.obj);;IGES Files (*.iges *.igs);;DXF Files (*.dxf);;All Files (*)"
        )
        
        if file_path:
            logger.info(f"upload_stl_file: File selected: {file_path}")
            
            if file_path.lower().endswith('.ecto') or file_path.lower().endswith('.lyns'):
                self._load_ecto_file(file_path)
                return

            file_ext = file_path.lower()
            if not (file_ext.endswith('.stl') or file_ext.endswith('.step') or file_ext.endswith('.stp') or file_ext.endswith('.3dm') or file_ext.endswith('.obj') or file_ext.endswith('.iges') or file_ext.endswith('.igs') or file_ext.endswith('.dxf')):
                logger.warning(f"upload_stl_file: Invalid file extension: {file_path}")
                show_warning_dialog(
                    self,
                    "Invalid File",
                    "Please select a valid 3D file (.stl, .step, .stp, .3dm, .obj, .iges, .igs, .dxf, or .lyns extension)."
                )
                return
            
            # If current tab has a file, create a new tab; otherwise reuse empty tab
            tab = self._current_tab
            if tab and tab.file_path is not None:
                self._create_new_tab()
            
            logger.info("upload_stl_file: Loading 3D file into viewer...")
            self._load_file_into_current_tab(file_path, from_conversion=False)
        else:
            logger.info("upload_stl_file: File selection cancelled")
    
    def export_scaled_stl(self, file_path, scale_factor):
        """Export the current mesh scaled by the given factor."""
        logger.info(f"export_scaled_stl: Exporting scaled STL to {file_path} with scale {scale_factor}")
        
        vw = self.viewer_widget
        if not vw or not hasattr(vw, 'current_mesh') or vw.current_mesh is None:
            logger.error("export_scaled_stl: No mesh loaded")
            show_warning_dialog(self, "No Mesh Loaded", "Please load an STL file first before exporting.")
            return
        
        try:
            scaled_mesh = MeshCalculator.scale_mesh(vw.current_mesh, scale_factor)
            
            if scaled_mesh is None:
                logger.error("export_scaled_stl: Failed to scale mesh")
                show_error_dialog(self, "Export Error", "Failed to scale the mesh. Please try again.")
                return
            
            success = MeshCalculator.export_stl(scaled_mesh, file_path)
            
            if success:
                annotations = self.annotation_panel.export_annotations() if self.annotation_panel else []
                if annotations:
                    from core.annotation_exporter import AnnotationExporter
                    AnnotationExporter.save_annotations(
                        annotations, file_path, 
                        reader_mode=True,
                        bundle_images=True
                    )
                    logger.info(f"export_scaled_stl: Saved {len(annotations)} annotations with reader_mode")
                
                logger.info(f"export_scaled_stl: Successfully exported to {file_path}")
                msg = f"Scaled STL file exported successfully to:\n{file_path}"
                if annotations:
                    msg += f"\n\n{len(annotations)} annotations saved."
                show_message_dialog(self, "Export Successful", msg)
            else:
                logger.error(f"export_scaled_stl: Failed to export to {file_path}")
                show_error_dialog(self, "Export Error", f"Failed to export STL file to:\n{file_path}")
        except Exception as e:
            logger.error(f"export_scaled_stl: Error during export: {e}", exc_info=True)
            show_error_dialog(self, "Export Error", f"Error during export:\n{str(e)}")
    
    def _load_annotations_for_file(self, file_path: str):
        """Load annotations for a file if they exist and handle reader mode."""
        try:
            from core.annotation_exporter import AnnotationExporter
            
            self._clear_all_annotations()
            
            self.toolbar.set_reader_mode(False)
            if self.annotation_panel:
                self.annotation_panel.set_reader_mode(False)
            
            if not AnnotationExporter.annotations_exist(file_path):
                return
            
            annotations, msg, reader_mode = AnnotationExporter.load_annotations(file_path)
            if annotations and self.annotation_panel:
                self.annotation_panel.load_annotations(annotations)
                
                if reader_mode:
                    self.toolbar.set_reader_mode(True)
                    self.annotation_panel.set_reader_mode(True)
                    self.annotation_panel.show()
                    logger.info(f"Reader Mode enabled for {file_path}")
                
                vw = self.viewer_widget
                for i, ann_data in enumerate(annotations):
                    ann_id = ann_data['id']
                    point = tuple(ann_data['point'])
                    is_read = ann_data.get('is_read', False)
                    if reader_mode:
                        color = ann_data.get('color') or ('#1821b4' if is_read else '#36cd2e')
                    else:
                        color = ann_data.get('color') or '#909d92'
                    if vw and hasattr(vw, 'add_annotation_marker'):
                        vw.add_annotation_marker(ann_id, point, color, display_date=str(i + 1))
                
                logger.info(f"Loaded {len(annotations)} annotations for {file_path} (reader_mode={reader_mode})")
                self._update_sidebar_annotation_count()
                
        except Exception as e:
            logger.warning(f"Failed to load annotations: {e}")
    
    def save_current_annotations(self):
        title = self.windowTitle()
        if " - " not in title:
            return False
        logger.info("save_current_annotations: Annotations will be saved on export")
        return True
    
    def _load_ecto_file(self, ecto_path: str, display_name_override: Optional[str] = None,
                         force_editable: bool = False, force_reader_mode: bool = False):
        """Load an .ecto bundle file.

        display_name_override — when the bundle was written to a temp path
        (project-tab restore), use this instead of deriving a name from
        ecto_path, whose stem is a meaningless random temp filename.

        force_editable — used by project-tab restore (see
        _restore_viewer_tab_from_project). import_ecto()'s sender/reader
        check is based on core/creator_registry.py, a registry file kept
        in this machine's local app-data folder — it can never recognize a
        token minted on a different device, even one you own. That's fine
        for the genuine "someone emailed me a .ecto" case, but a project's
        own viewer tabs aren't shared with anyone; they're just this
        session's save/restore format for its own tabs. Without this
        override, reopening your own project on a second device always
        landed every tab in read-only "Reader Mode" for no real reason.

        force_reader_mode — used by _lite_load_review_file. The creator-
        token check above assumes "this machine created it" means "this is
        my own editable content," which breaks the Supplier Review
        Workflow when LYNS360 and LYNS Lite happen to run on the same
        machine (e.g. testing, or a shared workstation): the PM's own
        creator token is already registered locally, so without this flag
        the review's existing annotations would incorrectly open fully
        editable in Lite — no supplier-feedback composer at all, and no
        protection against silently overwriting the PM's original comment.
        A supplier review is never "your own project," regardless of which
        machine exported it, so this always wins over the token check.
        """
        logger.info(f"_load_ecto_file: Loading .ecto file: {ecto_path}")

        try:
            from core.ecto_format import EctoFormat

            # Check if this is a technical overview .ecto
            if EctoFormat.is_technical_ecto(ecto_path):
                self._load_technical_ecto(ecto_path)
                return
            
            model_path, annotations, reader_mode, temp_dir, drawings, texture_data, screenshots = EctoFormat.import_ecto(ecto_path)
            if force_editable:
                reader_mode = False
            if force_reader_mode:
                reader_mode = True

            if model_path is None:
                show_error_dialog(
                    self,
                    "Error",
                    f"Failed to open .ecto file:\n{temp_dir}"
                )
                return
            
            # If current tab has a file, create a new tab
            tab = self._current_tab
            if tab and tab.file_path is not None:
                self._create_new_tab()
                tab = self._current_tab
            
            # Cleanup previous ecto temp dir for this tab
            if tab and tab.ecto_temp_dir:
                EctoFormat.cleanup_temp_dir(tab.ecto_temp_dir)
            if tab:
                tab.ecto_temp_dir = temp_dir
            
            vw = self.viewer_widget
            if vw is None:
                return
            
            success = vw.load_stl(model_path)
            
            if not success:
                show_error_dialog(
                    self,
                    "Error",
                    f"Failed to load model from .ecto bundle"
                )
                EctoFormat.cleanup_temp_dir(temp_dir)
                if tab:
                    tab.ecto_temp_dir = None
                return
            
            if display_name_override:
                display_name = display_name_override
            else:
                filename = Path(ecto_path).stem
                display_name = f"{filename}.ecto"
            if tab:
                tab.file_path = ecto_path
                tab.filename = display_name
                tab.reader_mode = reader_mode
                self.tab_bar.setTabText(self.current_tab_index, _ecto_tab_caption(display_name))

            self.setWindowTitle(f"LYNS - {display_name}")
            self.toolbar.set_loaded_filename(display_name)
            self.toolbar.set_stl_loaded(True)
            
            self._set_render_mode(self.toolbar.render_mode)
            self._apply_current_texture_settings()
            
            if hasattr(vw, 'current_mesh'):
                mesh = vw.current_mesh
                if mesh is not None:
                    mesh_data = MeshCalculator.get_mesh_data(mesh)
                    if tab:
                        tab.sidebar_data = mesh_data
                        tab.mesh = mesh
                    self.sidebar_panel.update_dimensions(mesh_data, ecto_path)
            
            self._clear_all_annotations()
            
            self.toolbar.set_reader_mode(reader_mode)
            if self.annotation_panel:
                self.annotation_panel.set_reader_mode(reader_mode)
                self.annotation_panel.show()
            
            if annotations and self.annotation_panel:
                self.annotation_panel.load_annotations(annotations)
                
                for i, ann_data in enumerate(annotations):
                    ann_id = ann_data['id']
                    point = tuple(ann_data['point'])
                    if reader_mode:
                        is_read = ann_data.get('is_read', False)
                        color = ann_data.get('color') or (VALIDATED_COLOR if is_read else PENDING_COLOR)
                    else:
                        color = ann_data.get('color') or PENDING_COLOR
                    if vw and hasattr(vw, 'add_annotation_marker'):
                        vw.add_annotation_marker(ann_id, point, color, display_date=str(i + 1))
                
                logger.info(f"_load_ecto_file: Loaded {len(annotations)} annotations (reader_mode={reader_mode})")
                self._update_sidebar_annotation_count()
            
            # Restore drawings ( strokes on the 3D model surface)
            if drawings and vw and hasattr(vw, 'restore_draw_strokes'):
                vw.restore_draw_strokes(drawings)
                logger.info(f"_load_ecto_file: Restored {len(drawings)} drawing strokes")
            
            # Restore visual style (solid/wireframe/shaded) BEFORE any
            # material/texture preset below — set_render_mode() blindly
            # overwrites every part's .material with a plain generic one
            # (see viewer_widget_pygfx.py), so calling it AFTER restoring
            # per-part leather/color/image presets would wipe every one of
            # them out again, leaving the model visually untextured even
            # though the presets were genuinely applied a moment earlier
            # (this was exactly backwards before — the visible symptom was
            # "materials not showing" after reopening a saved project).
            # Also syncs the toolbar's own icon/state to match.
            saved_render_mode = texture_data.get('render_mode') if texture_data else None
            if saved_render_mode:
                self.toolbar._set_render_mode(saved_render_mode)

            # Restore material/texture if saved in bundle
            if texture_data and vw and hasattr(vw, '_apply_material_preset_to_mesh'):
                try:
                    restored_part_ids = set()
                    for part_texture in texture_data.get('parts_textures', []):
                        part_id = part_texture.get('part_id')
                        if part_id is None or not hasattr(vw, 'apply_material_preset_to_part'):
                            continue
                        vw.apply_material_preset_to_part(part_id, part_texture)
                        restored_part_ids.add(part_id)

                    mesh_obj = getattr(vw, '_mesh_obj', None)
                    has_root_texture = any(
                        texture_data.get(key)
                        for key in ('albedo_map_path', 'albedo_map', 'use_texture_maps', 'image_file')
                    ) and not texture_data.get('parts_textures')

                    if mesh_obj is not None and has_root_texture:
                        vw._apply_material_preset_to_mesh(mesh_obj, texture_data)

                    if restored_part_ids or has_root_texture:
                        logger.info(
                            f"_load_ecto_file: Restored material/texture (image_file={texture_data.get('image_file', False)}, "
                            f"parts={len(restored_part_ids)})"
                        )
                except Exception as tex_err:
                    logger.warning(f"_load_ecto_file: Failed to restore texture: {tex_err}")

            # Restore screenshots into this tab's own list, and refresh the
            # shared screenshot panel since this tab is the active one.
            if tab is not None:
                from PyQt5.QtGui import QPixmap as _QPixmap
                restored_shots = []
                for shot in (screenshots or []):
                    try:
                        pix = _QPixmap(shot['image_path'])
                        if not pix.isNull():
                            restored_shots.append((
                                pix, shot.get('timestamp', ''), shot.get('id') or uuid.uuid4().hex,
                                shot.get('note', ''),
                            ))
                    except Exception:
                        pass
                tab.screenshots = restored_shots
                self.screenshot_panel.set_screenshots(tab.screenshots)
                if restored_shots:
                    logger.info(f"_load_ecto_file: Restored {len(restored_shots)} screenshots")

            logger.info(f"_load_ecto_file: Successfully loaded .ecto file")
            
        except Exception as e:
            logger.error(f"_load_ecto_file: Error loading .ecto file: {e}", exc_info=True)
            show_error_dialog(self, "Error", f"Failed to open .ecto file:\n{str(e)}")
    
    def _load_technical_ecto(self, ecto_path: str):
        """Load a technical-overview .ecto file into the Technical Overview workspace."""
        from core.ecto_format import EctoFormat

        doc_path, annotations, metadata, passcode_hash, temp_dir = EctoFormat.import_technical(ecto_path)
        if doc_path is None:
            show_error_dialog(self, "Error", f"Failed to open technical .ecto:\n{temp_dir}")
            return

        # Switch to technical mode
        self._switch_mode("technical")

        # Load document + annotations
        self.technical_overview.load_from_ecto(doc_path, annotations or [], passcode_hash)

        # Load metadata into sidebar
        if metadata:
            self.technical_sidebar.set_metadata(metadata)

        # If passcode protected, prompt for passcode to unlock editing
        if passcode_hash:
            from ui.passcode_dialog import PasscodeDialog
            dlg = PasscodeDialog(mode='enter', stored_hash=passcode_hash, parent=self)
            if dlg.exec() == PasscodeDialog.Accepted:
                logger.info("Technical .ecto: passcode verified, edit mode enabled")
            else:
                # Lock editing: disable sidebar fields and annotation mode
                self.technical_sidebar.setEnabled(False)
                show_message_dialog(self, "View Only",
                                    "You can view this file but editing is locked.\n"
                                    "Enter the correct passcode to edit.")

        self.setWindowTitle(f"LYNS - {Path(ecto_path).name}")
        # Store temp dir for cleanup
        self._tech_ecto_temp_dir = temp_dir
        logger.info(f"_load_technical_ecto: Loaded {ecto_path}")

    def closeEvent(self, event):
        """Handle window close and cleanup.

        No standalone "unsaved annotations"/"unsaved screenshots" prompts
        here — both are already captured by a project Save (which bundles
        every tab's annotations and the screenshot panel in one go), so
        warning about them separately from the project's own unsaved-changes
        check would just be a redundant second/third popup for the same
        underlying "you have unsaved work" fact.
        """

        # Release the QC panel's embedded viewer back to viewer_stack BEFORE
        # Qt destroys the widget hierarchy.  If the viewer is still reparented
        # into the QC panel when aboutToQuit fires, rendercanvas tries to access
        # the already-destroyed QRenderWidget and aborts the process.
        try:
            if hasattr(self, 'project_widget'):
                qc = self.project_widget._screen_widgets.get('quality_control')
                if qc and hasattr(qc, '_left_panel'):
                    qc._left_panel.release_viewer()
        except Exception:
            pass

        # Release this session's lock on whatever project is currently open —
        # otherwise it stays marked as "open" until someone else's stale-lock
        # threshold expires, even though this session actually closed cleanly.
        try:
            if hasattr(self, 'project_widget'):
                self.project_widget.release_lock()
        except Exception:
            pass

        # Explicitly close every tab's WebGPU render canvas while its Qt
        # widget is still alive. rendercanvas registers each QRenderWidget
        # with a shared loop that reacts to QApplication.aboutToQuit; if a
        # canvas's C++ object gets torn down by normal Qt parent/child
        # deletion before that handler runs, rendercanvas tries to touch the
        # already-deleted widget and the app aborts with "wrapped C/C++
        # object ... has been deleted". Calling .close() here lets each
        # canvas unregister itself cleanly first, same reasoning as the
        # QC-panel release above.
        for tab in self.tabs:
            canvas = getattr(tab.viewer_widget, '_canvas', None)
            if canvas is not None:
                try:
                    canvas.close()
                except Exception:
                    pass

        # Cleanup all ecto temp directories
        for tab in self.tabs:
            if tab.ecto_temp_dir:
                try:
                    from core.ecto_format import EctoFormat
                    EctoFormat.cleanup_temp_dir(tab.ecto_temp_dir)
                except Exception:
                    pass
        # Cleanup technical overview temp dir
        if hasattr(self, '_tech_ecto_temp_dir') and self._tech_ecto_temp_dir:
            try:
                from core.ecto_format import EctoFormat
                EctoFormat.cleanup_temp_dir(self._tech_ecto_temp_dir)
            except Exception:
                pass
        # Cleanup drawing scale temp source file (restored from a saved project)
        if getattr(self, '_scale_temp_path', None) and os.path.exists(self._scale_temp_path):
            try:
                os.remove(self._scale_temp_path)
            except OSError:
                pass
        super().closeEvent(event)


def main():
    """Main function to run the application."""
    from PyQt5.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    window = STLViewerWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

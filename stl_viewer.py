"""
Main ECTOFORM Window with minimalistic UI.
"""
import sys
import logging
from pathlib import Path
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QFileDialog,
    QMessageBox, QSplitter, QFrame, QApplication
)
from PyQt5.QtCore import Qt
# Try QtInteractor first, fallback to offscreen if it fails
try:
    from viewer_widget import STLViewerWidget
    USE_OFFSCREEN = False
except Exception as e:
    print(f"Warning: Could not import QtInteractor viewer, using offscreen fallback: {e}", file=sys.stderr)
    from viewer_widget_offscreen import STLViewerWidgetOffscreen as STLViewerWidget
    USE_OFFSCREEN = True

from ui.sidebar_panel import SidebarPanel
from ui.toolbar import ViewControlsToolbar
from ui.ruler_toolbar import RulerToolbar
from ui.annotation_panel import AnnotationPanel
from ui.styles import get_global_stylesheet, default_theme
from core.mesh_calculator import MeshCalculator

logger = logging.getLogger(__name__)


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


class STLViewerWindow(QMainWindow):
    """Main window for STL file viewer application."""
    
    def __init__(self):
        debug_print("STLViewerWindow: Initializing...")
        logger.info("STLViewerWindow: Initializing...")
        super().__init__()
        debug_print("STLViewerWindow: Parent initialized")
        logger.info("STLViewerWindow: Parent initialized")
        self._annotations_exported = False  # Track if annotations have been exported
        self.init_ui()
        debug_print("STLViewerWindow: Initialization complete")
        logger.info("STLViewerWindow: Initialization complete")
    
    def init_ui(self):
        """Initialize the user interface."""
        logger.info("init_ui: Starting UI initialization...")
        
        logger.info("init_ui: Setting window title and size...")
        self.setWindowTitle("ECTOFORM")
        self.setMinimumSize(1200, 800)
        self.resize(1200, 800)
        
        # Center window on screen
        screen = QApplication.primaryScreen().geometry()
        window_geometry = self.frameGeometry()
        window_geometry.moveCenter(screen.center())
        self.move(window_geometry.topLeft())
        
        logger.info("init_ui: Creating central widget...")
        central_widget = QWidget()
        central_widget.setStyleSheet(f"background-color: {default_theme.background};")
        self.setCentralWidget(central_widget)
        
        logger.info("init_ui: Creating main layout...")
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        logger.info("init_ui: Creating splitter...")
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet(f"background-color: {default_theme.background};")
        main_layout.addWidget(splitter)
        
        logger.info("init_ui: Creating sidebar panel...")
        self.sidebar_panel = SidebarPanel()
        self.sidebar_panel.upload_btn.clicked.connect(self.upload_stl_file)
        self.sidebar_panel.export_scaled_stl.connect(self.export_scaled_stl)
        self.sidebar_panel.annotations_exported.connect(self._on_annotations_exported)
        splitter.addWidget(self.sidebar_panel)
        logger.info("init_ui: Sidebar panel created")
        
        # Create right panel container (toolbar + viewer)
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        
        # Create toolbar
        logger.info("init_ui: Creating toolbar...")
        self.toolbar = ViewControlsToolbar()
        self._connect_toolbar_signals()
        right_layout.addWidget(self.toolbar)
        logger.info("init_ui: Toolbar created")
        
        # Create ruler toolbar (hidden by default)
        logger.info("init_ui: Creating ruler toolbar...")
        self.ruler_toolbar = RulerToolbar()
        self.ruler_toolbar.hide()  # Hidden until ruler mode is activated
        self._connect_ruler_toolbar_signals()
        right_layout.addWidget(self.ruler_toolbar)
        logger.info("init_ui: Ruler toolbar created")
        
        debug_print("init_ui: Creating 3D viewer widget (this may take a moment)...")
        logger.info("init_ui: Creating 3D viewer widget (this may take a moment)...")
        
        # Create horizontal layout for viewer + annotation panel
        viewer_h_layout = QHBoxLayout()
        viewer_h_layout.setContentsMargins(0, 0, 0, 0)
        viewer_h_layout.setSpacing(0)
        
        try:
            # Try QtInteractor first
            if not USE_OFFSCREEN:
                self.viewer_widget = STLViewerWidget()
                debug_print("init_ui: 3D viewer widget (QtInteractor) created successfully")
                logger.info("init_ui: 3D viewer widget (QtInteractor) created successfully")
            else:
                # Use offscreen renderer
                from viewer_widget_offscreen import STLViewerWidgetOffscreen
                self.viewer_widget = STLViewerWidgetOffscreen()
                debug_print("init_ui: 3D viewer widget (Offscreen) created successfully")
                logger.info("init_ui: 3D viewer widget (Offscreen) created successfully")
            
            # Connect drag-and-drop signals
            self._connect_viewer_signals()
            
            viewer_h_layout.addWidget(self.viewer_widget, 1)  # Add with stretch factor
        except Exception as e:
            debug_print(f"init_ui: ERROR creating viewer widget: {e}")
            logger.error(f"init_ui: Error creating viewer widget: {e}", exc_info=True)
            # Try offscreen as fallback
            try:
                debug_print("init_ui: Trying offscreen renderer as fallback...")
                logger.info("init_ui: Trying offscreen renderer as fallback...")
                from viewer_widget_offscreen import STLViewerWidgetOffscreen
                self.viewer_widget = STLViewerWidgetOffscreen()
                self._connect_viewer_signals()
                viewer_h_layout.addWidget(self.viewer_widget, 1)
                debug_print("init_ui: Offscreen renderer fallback successful")
                logger.info("init_ui: Offscreen renderer fallback successful")
            except Exception as e2:
                debug_print(f"init_ui: Offscreen fallback also failed: {e2}")
                logger.error(f"init_ui: Offscreen fallback also failed: {e2}", exc_info=True)
                raise
        
        # Create annotation panel (hidden by default)
        logger.info("init_ui: Creating annotation panel...")
        self.annotation_panel = AnnotationPanel()
        self.annotation_panel.hide()
        self._connect_annotation_panel_signals()
        viewer_h_layout.addWidget(self.annotation_panel)
        logger.info("init_ui: Annotation panel created")
        
        # Add viewer container to right layout
        viewer_container = QWidget()
        viewer_container.setLayout(viewer_h_layout)
        right_layout.addWidget(viewer_container, 1)
        
        # Add right container to splitter
        splitter.addWidget(right_container)
        
        logger.info("init_ui: Configuring splitter...")
        splitter.setSizes([200, 1000])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        
        logger.info("init_ui: Applying styling...")
        self.apply_styling()
        logger.info("init_ui: UI initialization complete")
    
    def apply_styling(self):
        """Apply minimalistic styling with floating card design."""
        self.setStyleSheet(get_global_stylesheet())
    
    def _connect_toolbar_signals(self):
        """Connect toolbar signals to handler methods."""
        self.toolbar.toggle_grid.connect(self._toggle_grid)
        self.toolbar.toggle_theme.connect(self._toggle_theme)
        self.toolbar.render_mode_changed.connect(self._set_render_mode)
        self.toolbar.reset_rotation.connect(self._reset_rotation)
        self.toolbar.view_front.connect(self._view_front)
        self.toolbar.view_side.connect(self._view_side)
        self.toolbar.view_top.connect(self._view_top)
        self.toolbar.toggle_fullscreen.connect(self._toggle_fullscreen)
        self.toolbar.toggle_ruler.connect(self._toggle_ruler_mode)
        self.toolbar.toggle_annotation.connect(self._toggle_annotation_mode)
        self.toolbar.load_file.connect(self.upload_stl_file)
        self.toolbar.clear_model.connect(self._clear_current_model)
    
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
    
    def _clear_current_model(self):
        """Clear the current model from the viewer."""
        logger.info("_clear_current_model: Clearing current model...")
        
        # Check if there are unsaved annotations
        annotations = self.annotation_panel.get_annotations()
        if annotations:
            if not self._annotations_exported:
                # Warn user about unsaved annotations
                reply = QMessageBox.warning(
                    self,
                    "Unsaved Annotations",
                    f"You have {len(annotations)} annotation(s) that have not been exported.\n\n"
                    "Would you like to export them as .ecto before clearing?\n\n"
                    "• Click 'Yes' to export first\n"
                    "• Click 'No' to clear without exporting\n"
                    "• Click 'Cancel' to go back",
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                    QMessageBox.Yes
                )
                
                if reply == QMessageBox.Yes:
                    # Trigger export
                    self.sidebar_panel.export_as_ecto()
                    return  # Don't clear yet, user will export first
                elif reply == QMessageBox.Cancel:
                    return  # User cancelled, don't clear
                # If No, continue with clearing
            else:
                # Annotations were exported, just confirm clearing
                reply = QMessageBox.question(
                    self,
                    "Clear Model",
                    f"You have {len(annotations)} annotation(s). Are you sure you want to clear everything?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if reply == QMessageBox.No:
                    return
        
        # Clear the viewer
        if hasattr(self.viewer_widget, 'clear_viewer'):
            self.viewer_widget.clear_viewer()
        
        # Update toolbar state
        self.toolbar.set_stl_loaded(False)
        
        # Reset window title
        self.setWindowTitle("ECTOFORM")
        
        # Reset toolbar load button tooltip
        self.toolbar.set_loaded_filename(None)
        
        # Clear all annotations from panel and viewer
        self._clear_all_annotations()
        
        # Hide annotation panel if visible
        if self.annotation_panel.isVisible():
            self._exit_annotation_mode()
        
        # Reset sidebar panel dimensions and calculations
        self.sidebar_panel.reset_all_data()
        
        # Reset annotation export tracking
        self._annotations_exported = False
        
        logger.info("_clear_current_model: Model and all data cleared")
    
    def _connect_viewer_signals(self):
        """Connect viewer widget signals for drag-and-drop."""
        if hasattr(self.viewer_widget, 'file_dropped'):
            self.viewer_widget.file_dropped.connect(self._load_dropped_file)
        if hasattr(self.viewer_widget, 'click_to_upload'):
            self.viewer_widget.click_to_upload.connect(self.upload_stl_file)
        if hasattr(self.viewer_widget, 'drop_error'):
            self.viewer_widget.drop_error.connect(self._show_drop_error)
    
    def _load_dropped_file(self, file_path):
        """Load a file that was dropped on the viewer."""
        logger.info(f"_load_dropped_file: Loading dropped file: {file_path}")
        
        # Validate file extension (allow .ecto files too)
        file_ext = file_path.lower()
        if file_ext.endswith('.ecto'):
            # Handle .ecto files
            self._load_ecto_file(file_path)
            return
        
        if not (file_ext.endswith('.stl') or file_ext.endswith('.step') or file_ext.endswith('.stp') or file_ext.endswith('.3dm') or file_ext.endswith('.obj') or file_ext.endswith('.iges') or file_ext.endswith('.igs')):
            QMessageBox.warning(
                self,
                "Invalid File",
                "Please select a valid 3D file (.stl, .step, .stp, .3dm, .obj, .iges, .igs, or .ecto extension)."
            )
            return
        
        # Load and display the STL file
        success = self.viewer_widget.load_stl(file_path)
        
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
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to load {file_type} file:\n{file_path}\n\nPlease ensure the file is a valid {file_type} format."
            )
        else:
            # Update window title with filename
            filename = Path(file_path).name
            self.setWindowTitle(f"ECTOFORM - {filename}")
            # Update toolbar load button to show filename
            self.toolbar.set_loaded_filename(filename)
            # Enable toolbar controls
            self.toolbar.set_stl_loaded(True)
            # Update dimensions display
            if hasattr(self.viewer_widget, 'current_mesh'):
                mesh = self.viewer_widget.current_mesh
                if mesh is not None:
                    mesh_data = MeshCalculator.get_mesh_data(mesh)
                    self.sidebar_panel.update_dimensions(mesh_data, file_path)
            
            # Load any existing annotations for this file
            self._load_annotations_for_file(file_path)
    
    def _show_drop_error(self, error_msg):
        """Show an error message from drag-and-drop."""
        QMessageBox.warning(self, "Upload Error", error_msg)
    
    def _toggle_grid(self):
        """Toggle the background grid."""
        if hasattr(self.viewer_widget, 'plotter') and self.viewer_widget.plotter is not None:
            try:
                if self.toolbar.grid_enabled:
                    self.viewer_widget.plotter.show_grid()
                else:
                    self.viewer_widget.plotter.remove_bounds_axes()
            except Exception as e:
                logger.warning(f"Could not toggle grid: {e}")
    
    def _toggle_theme(self):
        """Toggle between light and dark viewer theme."""
        if hasattr(self.viewer_widget, 'plotter') and self.viewer_widget.plotter is not None:
            try:
                if self.toolbar.dark_theme:
                    self.viewer_widget.plotter.background_color = '#1a1a2e'
                else:
                    self.viewer_widget.plotter.background_color = 'white'
            except Exception as e:
                logger.warning(f"Could not toggle theme: {e}")
    
    def _set_render_mode(self, mode):
        """Set render mode: solid, wireframe, or shaded."""
        if hasattr(self.viewer_widget, 'current_actor') and self.viewer_widget.current_actor is not None:
            try:
                prop = self.viewer_widget.current_actor.GetProperty()
                if mode == 'wireframe':
                    prop.SetRepresentationToSurface()
                    prop.EdgeVisibilityOff()
                    prop.SetRepresentationToWireframe()
                elif mode == 'shaded':
                    # Shaded: silvery metallic look, no wires, shiny silver grey and black
                    prop.SetRepresentationToSurface()
                    prop.EdgeVisibilityOff()  # No wireframe edges
                    prop.SetColor(0.72, 0.72, 0.76)  # Silver grey
                    prop.SetAmbient(0.25)   # Darker ambient for pronounced shadows
                    prop.SetDiffuse(0.55)   # Moderate diffuse
                    prop.SetSpecular(0.65)  # Strong specular for shine
                    prop.SetSpecularPower(90)  # Sharp metallic highlights
                else:  # solid - unchanged from default
                    prop.SetRepresentationToSurface()
                    prop.EdgeVisibilityOff()
                    prop.SetColor(0.68, 0.85, 0.90)  # Restore lightblue
                    prop.SetAmbient(0.7)
                    prop.SetDiffuse(0.4)
                    prop.SetSpecular(0.2)
                    prop.SetSpecularPower(20)
                self.viewer_widget.plotter.render()
            except Exception as e:
                logger.warning(f"Could not set render mode: {e}")
    
    def _reset_rotation(self):
        """Reset view to default isometric rotation."""
        if hasattr(self.viewer_widget, 'plotter') and self.viewer_widget.plotter is not None:
            try:
                self.viewer_widget.plotter.reset_camera()
                self.viewer_widget.plotter.view_isometric()
            except Exception as e:
                logger.warning(f"Could not reset rotation: {e}")
    
    def _view_front(self):
        """Set camera to front view."""
        if hasattr(self.viewer_widget, 'plotter') and self.viewer_widget.plotter is not None:
            try:
                self.viewer_widget.plotter.view_yz()
            except Exception as e:
                logger.warning(f"Could not set front view: {e}")
    
    def _view_side(self):
        """Set camera to side view."""
        if hasattr(self.viewer_widget, 'plotter') and self.viewer_widget.plotter is not None:
            try:
                self.viewer_widget.plotter.view_xz()
            except Exception as e:
                logger.warning(f"Could not set side view: {e}")
    
    def _view_top(self):
        """Set camera to top view."""
        if hasattr(self.viewer_widget, 'plotter') and self.viewer_widget.plotter is not None:
            try:
                self.viewer_widget.plotter.view_xy()
            except Exception as e:
                logger.warning(f"Could not set top view: {e}")
    
    # ========== Ruler Mode Methods ==========
    
    def _toggle_ruler_mode(self):
        """Toggle ruler/measurement mode."""
        if self.toolbar.ruler_mode_enabled:
            # Enable ruler mode
            if hasattr(self.viewer_widget, 'enable_ruler_mode'):
                success = self.viewer_widget.enable_ruler_mode()
                if success:
                    self.ruler_toolbar.show()
                    self.ruler_toolbar.reset_to_front()
                    self._ruler_view_front()  # Auto-switch to front view
                    logger.info("_toggle_ruler_mode: Ruler mode enabled")
                else:
                    # Failed to enable, reset toolbar state
                    self.toolbar.ruler_mode_enabled = False
                    self.toolbar.ruler_btn.set_active(False)
                    logger.warning("_toggle_ruler_mode: Failed to enable ruler mode")
        else:
            # Disable ruler mode
            self._exit_ruler_mode()
    
    def _exit_ruler_mode(self):
        """Exit ruler mode and restore normal view."""
        if hasattr(self.viewer_widget, 'disable_ruler_mode'):
            self.viewer_widget.disable_ruler_mode()
        self.ruler_toolbar.hide()
        # Reset toolbar button state
        self.toolbar.ruler_mode_enabled = False
        self.toolbar.ruler_btn.set_active(False)
        self.toolbar.ruler_btn.set_icon("📏")
        logger.info("_exit_ruler_mode: Ruler mode disabled")
    
    def _ruler_view_front(self):
        """Set front orthographic view for measurement."""
        if hasattr(self.viewer_widget, 'view_front_ortho'):
            self.viewer_widget.view_front_ortho()
    
    def _ruler_view_left(self):
        """Set left orthographic view for measurement."""
        if hasattr(self.viewer_widget, 'view_left_ortho'):
            self.viewer_widget.view_left_ortho()
    
    def _ruler_view_right(self):
        """Set right orthographic view for measurement."""
        if hasattr(self.viewer_widget, 'view_right_ortho'):
            self.viewer_widget.view_right_ortho()
    
    def _ruler_view_top(self):
        """Set top orthographic view for measurement."""
        if hasattr(self.viewer_widget, 'view_top_ortho'):
            self.viewer_widget.view_top_ortho()
    
    def _ruler_view_bottom(self):
        """Set bottom orthographic view for measurement."""
        if hasattr(self.viewer_widget, 'view_bottom_ortho'):
            self.viewer_widget.view_bottom_ortho()
    
    def _ruler_view_rear(self):
        """Set rear orthographic view for measurement."""
        if hasattr(self.viewer_widget, 'view_rear_ortho'):
            self.viewer_widget.view_rear_ortho()
    
    def _clear_measurements(self):
        """Clear all measurements from the viewer."""
        if hasattr(self.viewer_widget, 'clear_measurements'):
            self.viewer_widget.clear_measurements()
    
    def _ruler_unit_changed(self, unit_key):
        """Handle unit change from ruler toolbar."""
        if hasattr(self.viewer_widget, '_ruler_unit'):
            self.viewer_widget._ruler_unit = unit_key
            logger.info(f"_ruler_unit_changed: Unit set to {unit_key}")
    
    # ========== Annotation Mode Methods ==========
    
    def _connect_annotation_panel_signals(self):
        """Connect annotation panel signals to handler methods."""
        self.annotation_panel.annotation_added.connect(self._on_annotation_added)
        self.annotation_panel.annotation_deleted.connect(self._on_annotation_deleted)
        self.annotation_panel.annotation_validated.connect(self._on_annotation_validated)
        self.annotation_panel.open_popup_requested.connect(self._on_open_popup_requested)
        self.annotation_panel.open_viewer_popup_requested.connect(self._on_open_viewer_popup_requested)
        self.annotation_panel.focus_annotation.connect(self._on_focus_annotation)
        self.annotation_panel.annotation_hovered.connect(self._on_annotation_hovered)
        self.annotation_panel.exit_annotation_mode.connect(self._exit_annotation_mode)
        self.annotation_panel.clear_all_requested.connect(self._clear_all_annotations)
    
    def _toggle_annotation_mode(self):
        """Toggle annotation mode."""
        if self.toolbar.annotation_mode_enabled:
            # Enable annotation mode
            if hasattr(self.viewer_widget, 'enable_annotation_mode'):
                success = self.viewer_widget.enable_annotation_mode(
                    callback=self._on_annotation_point_picked
                )
                if success:
                    self.annotation_panel.show()
                    # Exit ruler mode if active
                    if self.toolbar.ruler_mode_enabled:
                        self._exit_ruler_mode()
                    logger.info("_toggle_annotation_mode: Annotation mode enabled")
                else:
                    # Failed to enable, reset toolbar state
                    self.toolbar.reset_annotation_state()
                    logger.warning("_toggle_annotation_mode: Failed to enable annotation mode")
        else:
            # Disable annotation mode
            self._exit_annotation_mode()
    
    def _exit_annotation_mode(self):
        """Exit annotation mode; keep annotations saved and visible on the model."""
        if hasattr(self.viewer_widget, 'disable_annotation_mode'):
            self.viewer_widget.disable_annotation_mode()
        self.annotation_panel.hide()
        self.toolbar.reset_annotation_state()
        logger.info("_exit_annotation_mode: Annotation mode disabled, annotations kept")
    
    def _on_annotation_point_picked(self, point: tuple):
        """Handle point picked for annotation - creates gray dot."""
        logger.info(f"_on_annotation_point_picked: Point picked at {point}")
        
        # Add annotation to panel (pending/gray)
        annotation = self.annotation_panel.add_annotation(point)
        
        # Add gray visual marker to the viewer (display_number = position in list)
        if hasattr(self.viewer_widget, 'add_annotation_marker'):
            display_num = self.annotation_panel.get_display_number(annotation.id)
            self.viewer_widget.add_annotation_marker(
                annotation.id, point, '#909d92',
                display_date=str(display_num or len(self.annotation_panel.annotations))
            )  # Light grey
    
    def _on_annotation_added(self, annotation):
        """Handle annotation added event."""
        logger.info(f"_on_annotation_added: Annotation {annotation.id} added")
        self._update_sidebar_annotation_count()
    
    def _on_annotation_deleted(self, annotation_id: int):
        """Handle annotation deleted event - refresh all 3D markers with renumbered labels (1, 2, 3...)."""
        self._refresh_annotation_markers()
        logger.info(f"_on_annotation_deleted: Annotation {annotation_id} removed, markers renumbered")
        self._update_sidebar_annotation_count()
    
    def _on_open_popup_requested(self, annotation_id: int):
        """Handle request to open popup for an annotation."""
        from ui.annotation_popup import AnnotationPopup
        
        annotation = self.annotation_panel.get_annotation_by_id(annotation_id)
        if annotation is None:
            return
        
        # Create and show popup
        display_num = self.annotation_panel.get_display_number(annotation.id)
        popup = AnnotationPopup(
            annotation_id=annotation.id,
            point=annotation.point,
            text=annotation.text,
            image_paths=annotation.image_paths,
            label=annotation.label,
            created_at=annotation.created_at,
            display_number=display_num,
            parent=self
        )
        
        # Connect popup signals
        popup.annotation_validated.connect(self._on_popup_validated)
        popup.annotation_deleted.connect(self._on_popup_deleted)
        popup.finished.connect(lambda: self._on_annotation_popup_closed(annotation_id))
        
        # Highlight selected annotation dot in yellow
        if hasattr(self.viewer_widget, 'set_annotation_selected'):
            self.viewer_widget.set_annotation_selected(annotation_id, True)
        
        popup.show()
        logger.info(f"_on_open_popup_requested: Opened popup for annotation {annotation_id}")
    
    def _on_open_viewer_popup_requested(self, annotation_id: int):
        """Handle request to open viewer popup for an annotation (reader mode)."""
        from ui.annotation_viewer_popup import AnnotationViewerPopup
        
        annotation = self.annotation_panel.get_annotation_by_id(annotation_id)
        if annotation is None:
            return
        
        # Create and show viewer popup (read-only)
        display_num = self.annotation_panel.get_display_number(annotation.id)
        popup = AnnotationViewerPopup(
            annotation_id=annotation.id,
            point=annotation.point,
            text=annotation.text,
            image_paths=annotation.image_paths,
            label=annotation.label,
            created_at=annotation.created_at,
            display_number=display_num,
            parent=self
        )
        
        # Mark as read and update base color to blue
        self.annotation_panel.mark_as_read(annotation_id)
        if hasattr(self.viewer_widget, 'update_annotation_marker_color'):
            self.viewer_widget.update_annotation_marker_color(annotation_id, '#1821b4')  # Blue for read
        
        # Highlight selected annotation dot in yellow
        if hasattr(self.viewer_widget, 'set_annotation_selected'):
            self.viewer_widget.set_annotation_selected(annotation_id, True)
        
        popup.finished.connect(lambda: self._on_annotation_popup_closed(annotation_id))
        popup.show()
        
        logger.info(f"_on_open_viewer_popup_requested: Opened viewer popup for annotation {annotation_id}")
    
    def _on_popup_validated(self, annotation_id: int, text: str, image_paths: list, label: str = "Point"):
        """Handle annotation validated from popup - turn dot black."""
        # Update annotation in panel
        self.annotation_panel.validate_annotation(annotation_id, text, image_paths, label)
        
        # Update marker color to black (validated)
        if hasattr(self.viewer_widget, 'update_annotation_marker_color'):
            self.viewer_widget.update_annotation_marker_color(annotation_id, '#1821b4')  # Blue
        
        logger.info(f"_on_popup_validated: Annotation {annotation_id} validated")
    
    def _on_popup_deleted(self, annotation_id: int):
        """Handle annotation deleted from popup."""
        self.annotation_panel.remove_annotation(annotation_id)
        logger.info(f"_on_popup_deleted: Annotation {annotation_id} deleted from popup")
    
    def _on_annotation_popup_closed(self, annotation_id: int):
        """Restore annotation dot color when popup is closed."""
        if hasattr(self.viewer_widget, 'set_annotation_selected'):
            self.viewer_widget.set_annotation_selected(annotation_id, False)
    
    def _on_annotation_validated(self, annotation_id: int, text: str, image_paths: list, label: str = "Point"):
        """Handle annotation validated event from panel."""
        logger.info(f"_on_annotation_validated: Annotation {annotation_id} validated")
    
    def _on_focus_annotation(self, annotation_id: int):
        """Handle focus annotation request."""
        if hasattr(self.viewer_widget, 'focus_on_annotation'):
            self.viewer_widget.focus_on_annotation(annotation_id)
    
    def _on_annotation_hovered(self, annotation_id: int, is_hovered: bool):
        """Handle annotation card hover - highlight 3D marker yellow when hovering."""
        if hasattr(self.viewer_widget, 'set_annotation_selected'):
            self.viewer_widget.set_annotation_selected(annotation_id, is_hovered)
    
    def _refresh_annotation_markers(self):
        """Refresh all 3D markers with current display numbers (1, 2, 3...)."""
        if not hasattr(self.viewer_widget, 'clear_all_annotation_markers'):
            return
        self.viewer_widget.clear_all_annotation_markers()
        annotations = self.annotation_panel.get_annotations()
        if not annotations:
            return
        reader_mode = self.annotation_panel.is_reader_mode()
        for i, ann in enumerate(annotations):
            display_number = i + 1
            if reader_mode:
                color = '#1821b4' if ann.is_read else '#36cd2e'  # Blue=read, green=unread
            else:
                color = '#1821b4' if ann.is_validated else '#909d92'  # Blue=validated, grey=pending
            if hasattr(self.viewer_widget, 'add_annotation_marker'):
                self.viewer_widget.add_annotation_marker(ann.id, ann.point, color, display_date=str(display_number))
    
    def _clear_all_annotations(self):
        """Clear all annotations."""
        if hasattr(self.viewer_widget, 'clear_all_annotation_markers'):
            self.viewer_widget.clear_all_annotation_markers()
        self.annotation_panel.clear_all()
        logger.info("_clear_all_annotations: All annotations cleared")
        self._update_sidebar_annotation_count()
    
    def _update_sidebar_annotation_count(self):
        """Update the sidebar panel with the current annotation count."""
        count = len(self.annotation_panel.annotations)
        self.sidebar_panel.update_annotation_count(count)
        # Reset export flag when annotations change (new annotations added)
        if count > 0:
            self._annotations_exported = False
    
    def _on_annotations_exported(self):
        """Handle annotations exported event."""
        self._annotations_exported = True
        logger.info("_on_annotations_exported: Annotations have been exported")
    def _toggle_fullscreen(self):
        """Toggle fullscreen mode."""
        if self.toolbar.is_fullscreen:
            self.showFullScreen()
        else:
            self.showNormal()
    
    def keyPressEvent(self, event):
        """Handle key press events."""
        if event.key() == Qt.Key_Escape and self.isFullScreen():
            self.showNormal()
            self.toolbar.reset_fullscreen_state()
        else:
            super().keyPressEvent(event)

    
    def upload_stl_file(self):
        """Open file dialog and load selected 3D or .ecto file."""
        logger.info("upload_stl_file: Opening file dialog...")
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select 3D File",
            "",
            "All Supported (*.stl *.step *.stp *.3dm *.obj *.iges *.igs *.ecto);;ECTOFORM Bundle (*.ecto);;3D Files (*.stl *.step *.stp *.3dm *.obj *.iges *.igs);;STL Files (*.stl);;STEP Files (*.step *.stp);;3DM Files (*.3dm);;OBJ Files (*.obj);;IGES Files (*.iges *.igs);;All Files (*)"
        )
        
        if file_path:
            logger.info(f"upload_stl_file: File selected: {file_path}")
            
            # Check if it's an .ecto file
            if file_path.lower().endswith('.ecto'):
                self._load_ecto_file(file_path)
                return
            
            # Validate file extension for regular 3D files
            file_ext = file_path.lower()
            if not (file_ext.endswith('.stl') or file_ext.endswith('.step') or file_ext.endswith('.stp') or file_ext.endswith('.3dm') or file_ext.endswith('.obj') or file_ext.endswith('.iges') or file_ext.endswith('.igs')):
                logger.warning(f"upload_stl_file: Invalid file extension: {file_path}")
                QMessageBox.warning(
                    self,
                    "Invalid File",
                    "Please select a valid 3D file (.stl, .step, .stp, .3dm, .obj, .iges, .igs, or .ecto extension)."
                )
                return
            
            # Load and display the 3D file
            logger.info("upload_stl_file: Loading 3D file into viewer...")
            success = self.viewer_widget.load_stl(file_path)
            
            if not success:
                logger.error(f"upload_stl_file: Failed to load file: {file_path}")
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
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to load {file_type} file:\n{file_path}\n\nPlease ensure the file is a valid {file_type} format."
                )
            else:
                logger.info(f"upload_stl_file: STL file loaded successfully: {file_path}")
                # Update window title with filename
                filename = Path(file_path).name
                self.setWindowTitle(f"ECTOFORM - {filename}")
                # Update toolbar load button to show filename
                self.toolbar.set_loaded_filename(filename)
                # Enable toolbar controls
                self.toolbar.set_stl_loaded(True)
                # Update dimensions display
                if hasattr(self.viewer_widget, 'current_mesh'):
                    mesh = self.viewer_widget.current_mesh
                    if mesh is not None:
                        mesh_data = MeshCalculator.get_mesh_data(mesh)
                        self.sidebar_panel.update_dimensions(mesh_data, file_path)
                
                # Load any existing annotations for this file
                self._load_annotations_for_file(file_path)
        else:
            logger.info("upload_stl_file: File selection cancelled")
    
    def export_scaled_stl(self, file_path, scale_factor):
        """Export the current mesh scaled by the given factor."""
        logger.info(f"export_scaled_stl: Exporting scaled STL to {file_path} with scale {scale_factor}")
        
        if not hasattr(self.viewer_widget, 'current_mesh') or self.viewer_widget.current_mesh is None:
            logger.error("export_scaled_stl: No mesh loaded")
            QMessageBox.warning(
                self,
                "No Mesh Loaded",
                "Please load an STL file first before exporting."
            )
            return
        
        try:
            # Scale and export the mesh
            scaled_mesh = MeshCalculator.scale_mesh(self.viewer_widget.current_mesh, scale_factor)
            
            if scaled_mesh is None:
                logger.error("export_scaled_stl: Failed to scale mesh")
                QMessageBox.critical(
                    self,
                    "Export Error",
                    "Failed to scale the mesh. Please try again."
                )
                return
            
            success = MeshCalculator.export_stl(scaled_mesh, file_path)
            
            if success:
                # Also save annotations if any (with reader_mode enabled for recipients)
                annotations = self.annotation_panel.export_annotations()
                if annotations:
                    from core.annotation_exporter import AnnotationExporter
                    AnnotationExporter.save_annotations(
                        annotations, file_path, 
                        reader_mode=True,  # Enable reader mode for recipients
                        bundle_images=True  # Bundle images with export
                    )
                    logger.info(f"export_scaled_stl: Saved {len(annotations)} annotations with reader_mode")
                
                logger.info(f"export_scaled_stl: Successfully exported to {file_path}")
                msg = f"Scaled STL file exported successfully to:\n{file_path}"
                if annotations:
                    msg += f"\n\n{len(annotations)} annotations saved."
                QMessageBox.information(self, "Export Successful", msg)
            else:
                logger.error(f"export_scaled_stl: Failed to export to {file_path}")
                QMessageBox.critical(
                    self,
                    "Export Error",
                    f"Failed to export STL file to:\n{file_path}"
                )
        except Exception as e:
            logger.error(f"export_scaled_stl: Error during export: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Export Error",
                f"Error during export:\n{str(e)}"
            )
    
    def _load_annotations_for_file(self, file_path: str):
        """Load annotations for a file if they exist and handle reader mode."""
        try:
            from core.annotation_exporter import AnnotationExporter
            
            # Clear existing annotations first
            self._clear_all_annotations()
            
            # Reset reader mode
            self.toolbar.set_reader_mode(False)
            self.annotation_panel.set_reader_mode(False)
            
            # Check if annotations exist
            if not AnnotationExporter.annotations_exist(file_path):
                return
            
            # Load annotations with reader mode flag
            annotations, msg, reader_mode = AnnotationExporter.load_annotations(file_path)
            if annotations:
                self.annotation_panel.load_annotations(annotations)
                
                # Enable reader mode if flag is set
                if reader_mode:
                    self.toolbar.set_reader_mode(True)
                    self.annotation_panel.set_reader_mode(True)
                    # Show annotation panel in reader mode
                    self.annotation_panel.show()
                    logger.info(f"Reader Mode enabled for {file_path}")
                
                # Add markers to the viewer (display_number = 1, 2, 3...)
                for i, ann_data in enumerate(annotations):
                    ann_id = ann_data['id']
                    point = tuple(ann_data['point'])
                    is_validated = ann_data.get('is_validated', False)
                    is_read = ann_data.get('is_read', False)
                    # In reader mode: green=unread, blue=read. In normal mode: grey=pending, blue=validated.
                    if reader_mode:
                        color = '#1821b4' if is_read else '#36cd2e'  # Blue=read, green=unread
                    else:
                        color = '#1821b4' if is_validated else '#909d92'  # Blue if validated, light grey if pending
                    if hasattr(self.viewer_widget, 'add_annotation_marker'):
                        self.viewer_widget.add_annotation_marker(ann_id, point, color, display_date=str(i + 1))
                
                logger.info(f"Loaded {len(annotations)} annotations for {file_path} (reader_mode={reader_mode})")
                
                # Update sidebar annotation count
                self._update_sidebar_annotation_count()
                
        except Exception as e:
            logger.warning(f"Failed to load annotations: {e}")
    
    def save_current_annotations(self):
        """Save current annotations to the sidecar file."""
        # Get the current file path from window title
        title = self.windowTitle()
        if " - " not in title:
            return False
        
        filename = title.split(" - ", 1)[1]
        
        # We need the full path - this is a limitation, 
        # annotations will be saved on next export
        logger.info("save_current_annotations: Annotations will be saved on export")
        return True
    
    def _load_ecto_file(self, ecto_path: str):
        """Load an .ecto bundle file."""
        logger.info(f"_load_ecto_file: Loading .ecto file: {ecto_path}")
        
        try:
            from core.ecto_format import EctoFormat
            
            # Import the .ecto bundle
            model_path, annotations, reader_mode, temp_dir = EctoFormat.import_ecto(ecto_path)
            
            if model_path is None:
                # temp_dir contains error message in this case
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to open .ecto file:\n{temp_dir}"
                )
                return
            
            # Store temp_dir for cleanup on next load or app exit
            if hasattr(self, '_ecto_temp_dir') and self._ecto_temp_dir:
                EctoFormat.cleanup_temp_dir(self._ecto_temp_dir)
            self._ecto_temp_dir = temp_dir
            
            # Load the extracted model
            success = self.viewer_widget.load_stl(model_path)
            
            if not success:
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to load model from .ecto bundle"
                )
                EctoFormat.cleanup_temp_dir(temp_dir)
                self._ecto_temp_dir = None
                return
            
            # Update window title with original filename from .ecto
            filename = Path(ecto_path).stem  # Remove .ecto extension
            self.setWindowTitle(f"ECTOFORM - {filename}.ecto")
            self.toolbar.set_loaded_filename(f"{filename}.ecto")
            self.toolbar.set_stl_loaded(True)
            
            # Update dimensions display
            if hasattr(self.viewer_widget, 'current_mesh'):
                mesh = self.viewer_widget.current_mesh
                if mesh is not None:
                    mesh_data = MeshCalculator.get_mesh_data(mesh)
                    self.sidebar_panel.update_dimensions(mesh_data, ecto_path)
            
            # Clear existing annotations first
            self._clear_all_annotations()
            
            # Use reader_mode from import (sender vs reader detection via creator_token)
            self.toolbar.set_reader_mode(reader_mode)
            self.annotation_panel.set_reader_mode(reader_mode)
            self.annotation_panel.show()
            
            # Load annotations if present
            if annotations:
                self.annotation_panel.load_annotations(annotations)
                
                # Add markers: display_number = 1, 2, 3...
                for i, ann_data in enumerate(annotations):
                    ann_id = ann_data['id']
                    point = tuple(ann_data['point'])
                    if reader_mode:
                        is_read = ann_data.get('is_read', False)
                        color = '#1821b4' if is_read else '#36cd2e'  # Blue=read, green=unread
                    else:
                        is_validated = ann_data.get('is_validated', False)
                        color = '#1821b4' if is_validated else '#909d92'  # Blue=validated, grey=pending
                    if hasattr(self.viewer_widget, 'add_annotation_marker'):
                        self.viewer_widget.add_annotation_marker(ann_id, point, color, display_date=str(i + 1))
                
                logger.info(f"_load_ecto_file: Loaded {len(annotations)} annotations (reader_mode={reader_mode})")
                self._update_sidebar_annotation_count()
            
            logger.info(f"_load_ecto_file: Successfully loaded .ecto file")
            
        except Exception as e:
            logger.error(f"_load_ecto_file: Error loading .ecto file: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to open .ecto file:\n{str(e)}"
            )
    
    def closeEvent(self, event):
        """Handle window close - prompt for unsaved annotations, then cleanup."""
        # Check for unsaved annotations before closing
        annotations = self.annotation_panel.get_annotations()
        if annotations and not self._annotations_exported:
            reply = QMessageBox.warning(
                self,
                "Unsaved Annotations",
                f"You have {len(annotations)} annotation(s) that have not been exported.\n\n"
                "Would you like to export them as .ecto before closing?\n\n"
                "• Click 'Yes' to export first\n"
                "• Click 'No' to close without exporting\n"
                "• Click 'Cancel' to stay",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes
            )
            if reply == QMessageBox.Yes:
                event.ignore()
                self.sidebar_panel.export_as_ecto()
                return
            if reply == QMessageBox.Cancel:
                event.ignore()
                return
        # Cleanup any extracted .ecto temp directory
        if hasattr(self, '_ecto_temp_dir') and self._ecto_temp_dir:
            try:
                from core.ecto_format import EctoFormat
                EctoFormat.cleanup_temp_dir(self._ecto_temp_dir)
            except Exception:
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

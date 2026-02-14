"""
3D Viewer Widget using PyVista for STL file visualization.
"""
import sys
import os
import logging
import pyvista as pv
from pyvistaqt import QtInteractor
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QStackedLayout
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from ui.drop_zone_overlay import DropZoneOverlay

# Set PyVista environment variables for macOS compatibility
os.environ.setdefault('PYVISTA_OFF_SCREEN', 'false')
os.environ.setdefault('PYVISTA_USE_PANEL', 'false')

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


class STLViewerWidget(QWidget):
    """PyVista-based 3D viewer widget for displaying STL files."""
    
    # Signals for drag-and-drop functionality
    file_dropped = pyqtSignal(str)
    click_to_upload = pyqtSignal()
    drop_error = pyqtSignal(str)
    
    def __init__(self, parent=None):
        debug_print("STLViewerWidget: Initializing...")
        logger.info("STLViewerWidget: Initializing...")
        super().__init__(parent)
        debug_print("STLViewerWidget: Parent initialized")
        logger.info("STLViewerWidget: Parent initialized")
        
        # Set up stacked layout for overlay
        self.layout = QStackedLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setStackingMode(QStackedLayout.StackAll)
        
        # Container for the 3D viewer
        self.viewer_container = QWidget()
        self.viewer_layout = QVBoxLayout(self.viewer_container)
        self.viewer_layout.setContentsMargins(0, 0, 0, 0)
        
        # No placeholder - drop overlay handles empty state
        
        self.layout.addWidget(self.viewer_container)
        
        # Create drop zone overlay (shown when no model loaded)
        self.drop_overlay = DropZoneOverlay()
        self.drop_overlay.file_dropped.connect(self._on_file_dropped)
        self.drop_overlay.click_to_upload.connect(self._on_click_upload)
        self.drop_overlay.error_occurred.connect(self._on_drop_error)
        self.layout.addWidget(self.drop_overlay)
        
        # Show overlay on top initially
        self.layout.setCurrentWidget(self.drop_overlay)
        
        # Plotter will be initialized later
        self.plotter = None
        self.current_mesh = None
        self.current_actor = None  # Track the mesh actor to remove it specifically
        self._initialized = False
        self._model_loaded = False
        
        # Ruler/measurement mode state
        self.ruler_mode = False
        self.measurement_points = []
        self.measurement_actors = []  # Track measurement visualization actors

        # Ruler picking internals (VTK observer-based; more reliable than PyVista helpers in QtInteractor)
        self._ruler_click_observer_id = None
        self._ruler_picker = None
        
        # Annotation mode state
        self.annotation_mode = False
        self.annotations = []  # List of annotation data: {'id': int, 'point': tuple, 'actor': vtk_actor}
        self.annotation_actors = []  # Track annotation marker actors
        self._annotation_click_observer_id = None
        self._annotation_picker = None
        self._annotation_callback = None  # Callback when point is picked for annotation

        debug_print("STLViewerWidget: Basic initialization complete, QtInteractor will be created after window is shown")
        logger.info("STLViewerWidget: Basic initialization complete, QtInteractor will be created after window is shown")
    
    def showEvent(self, event):
        """Initialize QtInteractor when widget is first shown."""
        super().showEvent(event)
        
        if not self._initialized:
            debug_print("STLViewerWidget: showEvent triggered, scheduling QtInteractor initialization...")
            logger.info("STLViewerWidget: showEvent triggered, scheduling QtInteractor initialization...")
            # Use QTimer with longer delay to ensure window is fully rendered
            # Process events multiple times to ensure everything is ready
            QTimer.singleShot(500, self._initialize_plotter)
    
    def _initialize_plotter(self):
        """Initialize the PyVista plotter (called after window is shown)."""
        if self._initialized:
            return
        
        # Process events before starting initialization
        from PyQt5.QtWidgets import QApplication
        QApplication.processEvents()
        
        # Ensure widget is visible and has a window
        if not self.isVisible():
            debug_print("STLViewerWidget: Widget not visible yet, retrying in 200ms...")
            logger.warning("STLViewerWidget: Widget not visible yet, retrying...")
            QTimer.singleShot(200, self._initialize_plotter)
            return
        
        # Check if widget has a valid window handle
        if not self.window().isVisible():
            debug_print("STLViewerWidget: Parent window not visible yet, retrying in 200ms...")
            logger.warning("STLViewerWidget: Parent window not visible yet, retrying...")
            QTimer.singleShot(200, self._initialize_plotter)
            return
            
        try:
            debug_print("STLViewerWidget: Starting plotter initialization...")
            logger.info("STLViewerWidget: Starting plotter initialization...")
            logger.info(f"STLViewerWidget: PyVista version: {pv.__version__}")
            debug_print(f"STLViewerWidget: PyVista version: {pv.__version__}")
            debug_print(f"STLViewerWidget: Widget visible: {self.isVisible()}, Window visible: {self.window().isVisible()}")
            logger.info(f"STLViewerWidget: Widget visible: {self.isVisible()}, Window visible: {self.window().isVisible()}")
            safe_flush(sys.stderr)
            
            debug_print("STLViewerWidget: Creating QtInteractor (this may take a moment)...")
            logger.info("STLViewerWidget: Creating QtInteractor (this may take a moment)...")
            safe_flush(sys.stderr)
            
            # Process events multiple times before creating QtInteractor
            for _ in range(3):
                QApplication.processEvents()
            
            # Initialize PyVista plotter with Qt backend
            # This might block, but we've processed events first
            self.plotter = QtInteractor(self.viewer_container)
            
            debug_print("STLViewerWidget: QtInteractor created successfully")
            logger.info("STLViewerWidget: QtInteractor created successfully")
            safe_flush(sys.stderr)
            
            # Process events after QtInteractor creation
            QApplication.processEvents()
            
            # Add plotter to viewer container layout
            self.viewer_layout.addWidget(self.plotter.interactor)
            QApplication.processEvents()
            
            debug_print("STLViewerWidget: Configuring plotter settings...")
            logger.info("STLViewerWidget: Configuring plotter settings...")
            safe_flush(sys.stderr)
            
            # Configure plotter for smooth interaction with large models
            try:
                self.plotter.enable_anti_aliasing()
                debug_print("STLViewerWidget: Anti-aliasing enabled")
                logger.info("STLViewerWidget: Anti-aliasing enabled")
            except Exception as e:
                debug_print(f"STLViewerWidget: Could not enable anti-aliasing: {e}")
                logger.warning(f"STLViewerWidget: Could not enable anti-aliasing: {e}")
            
            # Shadows disabled to reduce excessive shadowing while preserving 3D look
            # try:
            #     self.plotter.enable_shadows()
            #     debug_print("STLViewerWidget: Shadows enabled")
            #     logger.info("STLViewerWidget: Shadows enabled")
            # except Exception as e:
            #     debug_print(f"STLViewerWidget: Could not enable shadows: {e}")
            #     logger.warning(f"STLViewerWidget: Could not enable shadows: {e}")
            
            debug_print("STLViewerWidget: Initializing empty scene...")
            logger.info("STLViewerWidget: Initializing empty scene...")
            safe_flush(sys.stderr)
            
            # Initialize with empty scene - do this carefully to avoid hangs
            try:
                self.plotter.background_color = 'white'
                QApplication.processEvents()
                debug_print("STLViewerWidget: Background color set")
                logger.info("STLViewerWidget: Background color set")
            except Exception as e:
                debug_print(f"STLViewerWidget: Could not set background color: {e}")
                logger.warning(f"STLViewerWidget: Could not set background color: {e}")
            
            QApplication.processEvents()
            
            # Add axes - this can sometimes hang, so do it carefully
            try:
                debug_print("STLViewerWidget: Adding axes...")
                logger.info("STLViewerWidget: Adding axes...")
                safe_flush(sys.stderr)
                self.plotter.add_axes()
                QApplication.processEvents()
                debug_print("STLViewerWidget: Axes added")
                logger.info("STLViewerWidget: Axes added")
            except Exception as e:
                debug_print(f"STLViewerWidget: Could not add axes: {e}")
                logger.warning(f"STLViewerWidget: Could not add axes: {e}")
                # Continue anyway - axes are optional
            
            QApplication.processEvents()
            
            # Don't force render immediately - let it render naturally
            # The render() call can block on macOS
            debug_print("STLViewerWidget: Scene configured, will render on next event loop")
            logger.info("STLViewerWidget: Scene configured, will render on next event loop")
            
            debug_print("STLViewerWidget: Empty scene initialized")
            logger.info("STLViewerWidget: Empty scene initialized")
            
            self._initialized = True
            debug_print("STLViewerWidget: QtInteractor initialization complete")
            logger.info("STLViewerWidget: QtInteractor initialization complete")
            safe_flush(sys.stderr)
            
            # Final event processing - multiple times to ensure UI updates
            for _ in range(5):
                QApplication.processEvents()
            
            # Update the widget to ensure it's visible
            self.update()
            self.repaint()
            QApplication.processEvents()
            
            debug_print("STLViewerWidget: All initialization complete, widget should be functional")
            logger.info("STLViewerWidget: All initialization complete, widget should be functional")
            safe_flush(sys.stderr)
            
        except Exception as e:
            debug_print(f"STLViewerWidget: ERROR during plotter initialization: {e}")
            logger.error(f"STLViewerWidget: Error during plotter initialization: {e}", exc_info=True)
            import traceback
            traceback.print_exc()
            # Don't raise - allow the app to continue
    
    def load_stl(self, file_path):
        """
        Load and display an STL or STEP file.
        
        Args:
            file_path (str): Path to the STL or STEP file
            
        Returns:
            bool: True if successful, False otherwise
        """
        logger.info(f"load_stl: Starting to load file: {file_path}")
        
        # Wait for plotter to be initialized if not ready
        if not self._initialized or self.plotter is None:
            logger.warning("load_stl: Plotter not initialized yet, waiting...")
            # Wait a bit for initialization
            from PyQt5.QtWidgets import QApplication
            for _ in range(50):  # Wait up to 5 seconds
                QApplication.processEvents()
                if self._initialized and self.plotter is not None:
                    break
                import time
                time.sleep(0.1)
            
            if not self._initialized or self.plotter is None:
                logger.error("load_stl: Plotter failed to initialize")
                return False
        
        try:
            # Remove previous mesh actor if it exists (instead of clearing everything)
            if self.current_actor is not None:
                logger.info("load_stl: Removing previous mesh actor...")
                try:
                    self.plotter.remove_actor(self.current_actor)
                    logger.info("load_stl: Previous mesh actor removed")
                    # Ensure renderer settings are preserved after removing actor
                    self._restore_renderer_settings()
                except Exception as e:
                    logger.warning(f"load_stl: Could not remove actor, using clear: {e}")
                    # Fallback to clear if remove_actor fails
                    self.plotter.clear()
                    self.plotter.add_axes()
                    # Restore renderer settings after clear
                    self._restore_renderer_settings()
            elif self.current_mesh is not None:
                # If we have a mesh but no actor reference, use clear
                logger.info("load_stl: Clearing previous mesh...")
                self.plotter.clear()
                self.plotter.add_axes()
                # Restore renderer settings after clear
                self._restore_renderer_settings()
            
            # Detect file format and load accordingly
            file_ext = file_path.lower()
            if file_ext.endswith('.step') or file_ext.endswith('.stp'):
                logger.info("load_stl: Detected STEP file, loading with StepLoader...")
                from core.step_loader import StepLoader
                try:
                    mesh = StepLoader.load_step(file_path)
                    logger.info(f"load_stl: STEP file loaded successfully. Mesh info: {mesh}")
                except Exception as e:
                    logger.error(f"load_stl: Failed to load STEP file: {e}", exc_info=True)
                    raise
            elif file_ext.endswith('.3dm'):
                logger.info("load_stl: Detected 3DM file, loading with Rhino3dmLoader...")
                from core.rhino3dm_loader import Rhino3dmLoader
                try:
                    mesh = Rhino3dmLoader.load_3dm(file_path)
                    logger.info(f"load_stl: 3DM file loaded successfully. Mesh info: {mesh}")
                except Exception as e:
                    logger.error(f"load_stl: Failed to load 3DM file: {e}", exc_info=True)
                    raise
            elif file_ext.endswith('.obj'):
                logger.info("load_stl: Detected OBJ file, attempting to load...")
                mesh = None
                load_error = None
                
                # Try PyVista first (fastest)
                try:
                    logger.info("load_stl: Trying PyVista OBJ reader...")
                    mesh = pv.read(file_path)
                    logger.info(f"load_stl: PyVista read completed. Mesh info: {mesh}")
                    
                    # Check if mesh is valid
                    if mesh is not None and mesh.n_points > 0:
                        logger.info("load_stl: PyVista successfully loaded OBJ file")
                    else:
                        logger.warning("load_stl: PyVista loaded empty mesh, trying meshio fallback...")
                        mesh = None  # Will trigger fallback
                except Exception as e:
                    logger.warning(f"load_stl: PyVista failed to load OBJ: {e}, trying meshio fallback...")
                    load_error = str(e)
                    mesh = None
                
                # Fallback to meshio if PyVista failed or produced empty mesh
                meshio_error = None
                if mesh is None or mesh.n_points == 0:
                    try:
                        logger.info("load_stl: Trying meshio OBJ reader...")
                        import meshio
                        meshio_mesh = meshio.read(file_path)
                        logger.info(f"load_stl: meshio read completed. Points: {len(meshio_mesh.points)}, Cells: {len(meshio_mesh.cells)}")
                        
                        # Convert meshio mesh to PyVista
                        if len(meshio_mesh.points) == 0:
                            raise ValueError("meshio loaded OBJ but found no points")
                        
                        points = meshio_mesh.points
                        
                        # Find triangle cells (most common for OBJ)
                        cells = None
                        cell_type = None
                        for cell_block in meshio_mesh.cells:
                            if cell_block.type == "triangle":
                                cells = cell_block.data
                                cell_type = "triangle"
                                break
                        
                        # If no triangles, try other cell types
                        if cells is None:
                            if len(meshio_mesh.cells) > 0:
                                cell_block = meshio_mesh.cells[0]
                                cells = cell_block.data
                                cell_type = cell_block.type
                                logger.warning(f"load_stl: Using cell type {cell_type} (not triangles)")
                            else:
                                raise ValueError("meshio loaded OBJ but found no cells")
                        
                        # Create PyVista mesh
                        if cell_type == "triangle":
                            mesh = pv.PolyData(points, cells)
                        else:
                            # For other cell types, create UnstructuredGrid and extract surface
                            unstructured = pv.UnstructuredGrid(cells, cell_type, points)
                            mesh = unstructured.extract_surface()
                        
                        logger.info(f"load_stl: Converted meshio mesh to PyVista. Points: {mesh.n_points}, Cells: {mesh.n_cells}")
                    except ImportError:
                        meshio_error = "meshio is not available"
                        logger.warning(f"load_stl: {meshio_error}, will try custom parser...")
                    except ValueError as e:
                        error_str = str(e)
                        # Check if this is a texture coordinate mismatch error
                        if "len(points)" in error_str and "point_data" in error_str:
                            meshio_error = f"meshio texture coordinate mismatch: {error_str}"
                            logger.warning(f"load_stl: {meshio_error}, will try custom parser...")
                        else:
                            # Other ValueError from meshio - re-raise
                            meshio_error = error_str
                            raise
                    except Exception as e:
                        meshio_error = str(e)
                        logger.warning(f"load_stl: meshio failed: {meshio_error}, will try custom parser...")
                
                # Third fallback: custom OBJ parser for files with texture coordinate mismatches
                if (mesh is None or mesh.n_points == 0) and meshio_error:
                    try:
                        logger.info("load_stl: Trying custom OBJ parser (handles texture coordinate mismatches)...")
                        from core.obj_loader import ObjLoader
                        mesh = ObjLoader.load_obj(file_path)
                        logger.info(f"load_stl: Custom OBJ parser successfully loaded file. Points: {mesh.n_points}, Cells: {mesh.n_cells}")
                    except ImportError:
                        error_msg = "OBJ file could not be loaded. All loaders failed (PyVista, meshio, and custom parser unavailable)."
                        if load_error:
                            error_msg += f" PyVista error: {load_error}."
                        if meshio_error:
                            error_msg += f" meshio error: {meshio_error}."
                        logger.error(f"load_stl: {error_msg}")
                        raise ValueError(error_msg)
                    except Exception as e:
                        error_msg = "OBJ file could not be loaded with any available method (PyVista, meshio, or custom parser)."
                        if load_error:
                            error_msg += f" PyVista error: {load_error}."
                        if meshio_error:
                            error_msg += f" meshio error: {meshio_error}."
                        error_msg += f" Custom parser error: {str(e)}"
                        logger.error(f"load_stl: {error_msg}")
                        raise ValueError(error_msg)
                
                # Final validation
                if mesh is None or mesh.n_points == 0:
                    error_msg = "OBJ file loaded but contains no geometry (zero points). The file may be corrupted or in an unsupported format."
                    if load_error:
                        error_msg += f" Reader error: {load_error}"
                    logger.error(f"load_stl: {error_msg}")
                    raise ValueError(error_msg)
            elif file_ext.endswith('.iges') or file_ext.endswith('.igs'):
                logger.info("load_stl: Detected IGES file, loading with IgesLoader...")
                from core.iges_loader import IgesLoader
                try:
                    mesh = IgesLoader.load_iges(file_path)
                    logger.info(f"load_stl: IGES file loaded successfully. Mesh info: {mesh}")
                except Exception as e:
                    logger.error(f"load_stl: Failed to load IGES file: {e}", exc_info=True)
                    raise
            else:
                logger.info("load_stl: Reading STL file with PyVista...")
                # Read STL file using PyVista
                mesh = pv.read(file_path)
                logger.info(f"load_stl: STL file read successfully. Mesh info: {mesh}")
            
            # Check if this is the first mesh load (before we update current_mesh)
            is_first_load = (self.current_mesh is None)
            
            # Validate mesh is not empty before proceeding
            if mesh is None:
                error_msg = "Failed to load mesh: file returned None. The file may be corrupted or in an unsupported format."
                logger.error(f"load_stl: {error_msg}")
                raise ValueError(error_msg)
            
            if mesh.n_points == 0:
                error_msg = f"Loaded mesh contains no geometry (zero points). The file may be corrupted, empty, or in an unsupported format."
                logger.error(f"load_stl: {error_msg}")
                raise ValueError(error_msg)
            
            logger.info(f"load_stl: Mesh validated - {mesh.n_points} points, {mesh.n_cells} cells")
            
            # Store the original mesh BEFORE processing for rendering
            # This ensures volume calculations use the unmodified mesh
            self.current_mesh = mesh.copy()
            
            # Prepare mesh for high-quality rendering (optional enhancements)
            # These steps are optional - if they fail, we'll use the original mesh
            logger.info("load_stl: Preparing mesh for rendering...")
            render_mesh = mesh  # Start with original mesh
            
            # Try to triangulate if needed (optional enhancement)
            try:
                if not render_mesh.is_all_triangles():
                    logger.info("load_stl: Triangulating mesh...")
                    render_mesh = render_mesh.triangulate()
                    logger.info("load_stl: Mesh triangulated successfully")
            except Exception as e:
                logger.warning(f"load_stl: Could not triangulate mesh: {e}, using original mesh")
                render_mesh = mesh  # Fallback to original mesh
            
            # Try to compute normals for proper smooth shading (optional enhancement)
            # This is critical for Windows rendering to show detail correctly
            logger.info("load_stl: Computing mesh normals...")
            try:
                render_mesh.compute_normals(inplace=True, point_normals=True, cell_normals=False)
                logger.info("load_stl: Mesh normals computed successfully")
            except Exception as e:
                logger.warning(f"load_stl: Could not compute normals: {e}, continuing anyway")
            
            logger.info("load_stl: Adding mesh to plotter...")
            # Ensure renderer settings are active before adding mesh (preserves quality when uploading)
            self._restore_renderer_settings()
            
            # Add mesh to plotter with consistent rendering parameters
            # Store the actor reference so we can remove it later
            # Use the processed mesh for rendering (with normals and triangulation if successful)
            self.current_actor = self.plotter.add_mesh(
                render_mesh,
                color='lightblue',
                show_edges=False,
                smooth_shading=False,
                ambient=0.7,  # Increased for less shadowing
                diffuse=0.4,  # Reduced to balance with higher ambient
                specular=0.2,  # Reduced for less harsh highlights
                specular_power=20  # Reduced for softer specular
            )
            logger.info("load_stl: Mesh added to plotter")
            
            # Ensure renderer settings are still active after adding mesh
            # This preserves visual quality when uploading files multiple times
            self._restore_renderer_settings()
            
            # Ensure axes are present (only add on first load)
            if is_first_load:
                self.plotter.add_axes()
            
            logger.info("load_stl: Resetting camera...")
            # Fit view to show entire model
            self.plotter.reset_camera()
            
            # Force renderer update to ensure consistent appearance
            # Explicitly render on Windows to ensure detail is visible
            from PyQt5.QtWidgets import QApplication
            import sys
            try:
                # Force render update, especially important on Windows
                self.plotter.render()
                logger.info("load_stl: Renderer updated explicitly")
            except Exception as e:
                logger.warning(f"load_stl: Could not force render: {e}, continuing anyway")
            
            QApplication.processEvents()
            logger.info("load_stl: STL file loaded successfully")
            
            # Hide overlay when model is loaded
            self._model_loaded = True
            self._show_overlay(False)

            return True
            
        except Exception as e:
            logger.error(f"load_stl: Error loading STL file: {e}", exc_info=True)
            return False
    
    def clear_viewer(self):
        """Clear the 3D viewer."""
        if self.plotter is None:
            return
        logger.info("clear_viewer: Clearing viewer...")
        # Remove mesh actor if it exists
        if self.current_actor is not None:
            try:
                self.plotter.remove_actor(self.current_actor)
            except:
                pass
        self.plotter.clear()
        self.plotter.add_axes()
        
        # Restore renderer settings after clearing
        self._restore_renderer_settings()
        
        self.current_mesh = None
        self.current_actor = None
        self._model_loaded = False
        # Show overlay again when cleared
        self._show_overlay(True)
        logger.info("clear_viewer: Viewer cleared")
    
    def _restore_renderer_settings(self):
        """Restore renderer settings after clearing to maintain visual quality."""
        if self.plotter is None:
            return
        
        try:
            # Re-enable anti-aliasing for sharpness
            self.plotter.enable_anti_aliasing()
            logger.info("_restore_renderer_settings: Anti-aliasing restored")
        except Exception as e:
            logger.warning(f"_restore_renderer_settings: Could not restore anti-aliasing: {e}")
        
        # Restore lighting settings for consistent visual quality
        try:
            # Remove existing lights and add fresh default lighting
            self.plotter.remove_all_lights()
            # Add a light kit for balanced illumination (like initial state)
            light = pv.Light(position=(1, 1, 1), light_type='scene light')
            light.intensity = 1.0
            self.plotter.add_light(light)
            
            # Add fill light from opposite side for softer shadows
            fill_light = pv.Light(position=(-1, -0.5, 0.5), light_type='scene light')
            fill_light.intensity = 0.4
            self.plotter.add_light(fill_light)
            
            logger.info("_restore_renderer_settings: Lighting restored")
        except Exception as e:
            logger.warning(f"_restore_renderer_settings: Could not restore lighting: {e}")
        
        # Preserve background color
        try:
            self.plotter.background_color = 'white'
            logger.debug("_restore_renderer_settings: Background color restored")
        except Exception as e:
            logger.debug(f"_restore_renderer_settings: Could not restore background color: {e}")
        
        # Force renderer update to ensure settings take effect
        try:
            self.plotter.render()
            logger.debug("_restore_renderer_settings: Renderer updated")
        except Exception as e:
            logger.debug(f"_restore_renderer_settings: Could not force render: {e}")
    
    def _on_file_dropped(self, file_path: str):
        """Handle file dropped on overlay."""
        self.file_dropped.emit(file_path)
    
    def _on_click_upload(self):
        """Handle click on overlay to upload."""
        self.click_to_upload.emit()
    
    def _on_drop_error(self, error_msg: str):
        """Handle drop error."""
        self.drop_error.emit(error_msg)
    
    def _show_overlay(self, show: bool):
        """Show or hide the drop zone overlay."""
        if show:
            self.drop_overlay.show()
            self.drop_overlay.raise_()
        else:
            self.drop_overlay.hide()
    
    # ========== Ruler/Measurement Mode Methods ==========

    def _get_vtk_interactor(self):
        """Safely get the underlying VTK render window interactor from pyvistaqt.
        
        pyvistaqt wraps the VTK interactor in a RenderWindowInteractor class.
        We need the actual vtkRenderWindowInteractor for AddObserver calls.
        """
        if self.plotter is None:
            return None

        # Method 1: Get from render window directly (most reliable)
        try:
            ren_win = self.plotter.ren_win
            if ren_win is not None:
                vtk_iren = ren_win.GetInteractor()
                if vtk_iren is not None and hasattr(vtk_iren, 'AddObserver'):
                    return vtk_iren
        except Exception:
            pass

        # Method 2: pyvistaqt stores underlying interactor
        iren = getattr(self.plotter, 'iren', None)
        if iren is not None:
            # Check if it's the wrapper or the actual VTK object
            if hasattr(iren, 'AddObserver'):
                return iren
            # Try to get underlying VTK interactor from wrapper
            if hasattr(iren, 'GetRenderWindow'):
                try:
                    rw = iren.GetRenderWindow()
                    if rw is not None:
                        vtk_iren = rw.GetInteractor()
                        if vtk_iren is not None and hasattr(vtk_iren, 'AddObserver'):
                            return vtk_iren
                except Exception:
                    pass

        # Method 3: Fallback via interactor attribute
        interactor_widget = getattr(self.plotter, 'interactor', None)
        if interactor_widget is not None:
            try:
                rw = interactor_widget.GetRenderWindow()
                if rw is not None:
                    vtk_iren = rw.GetInteractor()
                    if vtk_iren is not None and hasattr(vtk_iren, 'AddObserver'):
                        return vtk_iren
            except Exception:
                pass

        logger.warning("_get_vtk_interactor: Could not find VTK interactor with AddObserver")
        return None

    def _install_ruler_click_picking(self) -> bool:
        """Install a VTK observer for click-based picking (most reliable in QtInteractor)."""
        try:
            import vtk  # type: ignore
        except Exception as e:
            logger.warning(f"_install_ruler_click_picking: vtk import failed: {e}")
            return False

        iren = self._get_vtk_interactor()
        if iren is None:
            logger.warning("_install_ruler_click_picking: Could not get VTK interactor")
            return False

        # Remove any previous observer first (important: do this before creating a new picker)
        self._uninstall_ruler_click_picking()

        # Create picker (cell picker is robust; we snap to nearest vertex ourselves)
        self._ruler_picker = vtk.vtkCellPicker()
        try:
            # A slightly larger tolerance improves hit-testing reliability on high-DPI displays.
            # We still snap to the nearest vertex, so accuracy remains high.
            self._ruler_picker.SetTolerance(0.01)
        except Exception:
            pass

        # Try to restrict picking to just the model actor (avoid axes/background)
        if self.current_actor is not None:
            try:
                self.current_actor.SetPickable(True)
            except Exception:
                pass
            try:
                self._ruler_picker.PickFromListOn()
                self._ruler_picker.AddPickList(self.current_actor)
            except Exception as e:
                logger.debug(f"_install_ruler_click_picking: Could not restrict pick list: {e}")
                # Avoid the "empty pick list" situation, which would prevent ALL picking.
                try:
                    self._ruler_picker.PickFromListOff()
                except Exception:
                    pass

        try:
            self._ruler_click_observer_id = iren.AddObserver(
                "LeftButtonPressEvent",
                self._on_ruler_left_click,
                1.0,  # high priority
            )
            logger.info("_install_ruler_click_picking: VTK click observer installed")
            return True
        except Exception as e:
            logger.error(f"_install_ruler_click_picking: Failed to add observer: {e}", exc_info=True)
            self._ruler_click_observer_id = None
            self._ruler_picker = None
            return False

    def _uninstall_ruler_click_picking(self):
        """Remove VTK observer used for ruler picking."""
        if self._ruler_click_observer_id is None:
            self._ruler_picker = None
            return

        iren = self._get_vtk_interactor()
        try:
            if iren is not None:
                iren.RemoveObserver(self._ruler_click_observer_id)
                logger.info("_uninstall_ruler_click_picking: VTK click observer removed")
        except Exception as e:
            logger.debug(f"_uninstall_ruler_click_picking: Could not remove observer: {e}")
        finally:
            self._ruler_click_observer_id = None
            self._ruler_picker = None

    def _on_ruler_left_click(self, obj, event):
        """VTK callback for left-click picking while ruler mode is enabled.
        
        In ruler mode we use orthographic views, so we project the screen click
        directly onto the view plane (at the model's focal depth) instead of
        ray-casting to the mesh surface.  This avoids vertex-snapping sensitivity
        issues and lets the user place measurement dots exactly where they click.
        """
        if not self.ruler_mode or self.plotter is None:
            return

        iren = self._get_vtk_interactor()
        if iren is None:
            return

        try:
            x, y = iren.GetEventPosition()
        except Exception:
            return

        logger.info(f"_on_ruler_left_click: click screen=({x},{y})")

        renderer = getattr(self.plotter, 'renderer', None)
        if renderer is None:
            try:
                renderer = self.plotter.ren_win.GetRenderers().GetFirstRenderer()
            except Exception:
                renderer = None

        if renderer is None:
            logger.info("_on_ruler_left_click: No renderer available")
            return

        try:
            import vtk
            import numpy as np

            # --- Convert screen click to world coordinates on the focal plane ---
            # In orthographic projection the mapping is affine (no perspective),
            # so XY in the view plane are exact regardless of depth.
            camera = renderer.GetActiveCamera()
            focal_pt = np.array(camera.GetFocalPoint())

            # Use VTK coordinate system to convert display -> world at focal depth
            coord = vtk.vtkCoordinate()
            coord.SetCoordinateSystemToDisplay()
            coord.SetValue(float(x), float(y), 0.0)
            world_near = np.array(coord.GetComputedWorldValue(renderer))

            # world_near is on the near clip plane.  We need to shift it along the
            # camera direction so that the depth component equals the focal plane.
            cam_dir = np.array(camera.GetDirectionOfProjection())
            # Project difference onto camera direction to get depth offset
            offset = np.dot(focal_pt - world_near, cam_dir)
            world_pos = world_near + cam_dir * offset

            logger.info(
                f"_on_ruler_left_click: screen=({x},{y}) world={world_pos}"
            )

            self._on_point_picked(world_pos)
        except Exception as e:
            logger.error(f"_on_ruler_left_click: Picking failed: {e}", exc_info=True)

    def enable_ruler_mode(self):
        """Enable point-to-point measurement mode with orthographic projection."""
        if self.plotter is None:
            logger.warning("enable_ruler_mode: Plotter not initialized")
            return False

        if self.current_mesh is None:
            logger.warning("enable_ruler_mode: No mesh loaded")
            return False

        logger.info("enable_ruler_mode: Enabling ruler mode...")
        self.ruler_mode = True
        self.measurement_points = []

        # Ensure we don't have leftover picking/observers from a previous session
        self._uninstall_ruler_click_picking()
        try:
            self.plotter.disable_picking()
        except Exception:
            pass

        # Prefer VTK observer-based picking (more reliable than PyVista helpers under QtInteractor)
        if self._install_ruler_click_picking():
            try:
                self.plotter.enable_parallel_projection()
                logger.info("enable_ruler_mode: Orthographic projection enabled")
            except Exception as e:
                logger.warning(f"enable_ruler_mode: Could not enable orthographic projection: {e}")
            
            # Disable rotation but keep zoom - use zoom-only interaction style
            self._enable_zoom_only_interaction()
            return True

        # Fallback to PyVista picking helpers (if VTK interactor not available)
        try:
            self.plotter.enable_surface_point_picking(
                callback=self._on_point_picked,
                show_message=False,
                show_point=False,
                picker='cell',
            )
            logger.info("enable_ruler_mode: Surface point picking enabled (fallback)")
            self.plotter.enable_parallel_projection()
            logger.info("enable_ruler_mode: Orthographic projection enabled")
            return True
        except AttributeError:
            logger.info("enable_ruler_mode: Falling back to enable_point_picking...")
            try:
                self.plotter.enable_point_picking(
                    callback=self._on_point_picked,
                    show_message=False,
                    show_point=False,
                    use_mesh=True,
                )
                self.plotter.enable_parallel_projection()
                return True
            except Exception as e2:
                logger.error(f"enable_ruler_mode: Fallback also failed: {e2}", exc_info=True)
                self.ruler_mode = False
                return False
        except Exception as e:
            logger.error(f"enable_ruler_mode: Failed to enable ruler mode: {e}", exc_info=True)
            self.ruler_mode = False
            return False

    def disable_ruler_mode(self):
        """Disable measurement mode and restore perspective projection."""
        if self.plotter is None:
            return

        logger.info("disable_ruler_mode: Disabling ruler mode...")
        self.ruler_mode = False
        self.measurement_points = []

        # Remove our observer (if installed)
        self._uninstall_ruler_click_picking()

        try:
            self.plotter.disable_picking()
            logger.info("disable_ruler_mode: Picking disabled")
        except Exception as e:
            logger.warning(f"disable_ruler_mode: Could not disable picking: {e}")

        # Clear all measurement visualizations
        self.clear_measurements()

        try:
            self.plotter.disable_parallel_projection()
            logger.info("disable_ruler_mode: Perspective projection restored")
        except Exception as e:
            logger.warning(f"disable_ruler_mode: Could not restore projection: {e}")
        
        # Restore full interaction (rotation, pan, zoom)
        self._restore_full_interaction()

    def _snap_to_axis(self, point1, point2):
        """Snap point2 so the measurement is strictly horizontal or vertical on screen.
        
        Uses the camera's right and up vectors to determine screen-space axes,
        then constrains point2 to move only along the dominant screen direction.
        """
        import numpy as np
        try:
            camera = self.plotter.renderer.GetActiveCamera()
            # Get camera basis vectors
            view_up = np.array(camera.GetViewUp())
            cam_dir = np.array(camera.GetDirectionOfProjection())
            view_right = np.cross(cam_dir, view_up)
            # Normalize
            view_right = view_right / (np.linalg.norm(view_right) + 1e-12)
            view_up = view_up / (np.linalg.norm(view_up) + 1e-12)
            
            p1 = np.array(point1)
            p2 = np.array(point2)
            delta = p2 - p1
            
            # Project delta onto screen axes
            dx_screen = np.dot(delta, view_right)
            dy_screen = np.dot(delta, view_up)
            
            # Snap to the dominant axis
            if abs(dx_screen) >= abs(dy_screen):
                # Horizontal measurement
                snapped = p1 + view_right * dx_screen
            else:
                # Vertical measurement
                snapped = p1 + view_up * dy_screen
            
            logger.info(f"_snap_to_axis: Snapped from {point2} to {snapped} (dx={dx_screen:.4f}, dy={dy_screen:.4f})")
            return tuple(snapped)
        except Exception as e:
            logger.warning(f"_snap_to_axis: Could not snap, using original point: {e}")
            return point2

    def _on_point_picked(self, point):
        """Handle point picked for measurement."""
        if not self.ruler_mode or point is None:
            return
        
        logger.info(f"_on_point_picked: Point picked at {point}")
        
        # If this is the second point, snap to horizontal or vertical axis
        if len(self.measurement_points) == 1:
            point = self._snap_to_axis(self.measurement_points[0], point)
        
        self.measurement_points.append(point)
        
        # Calculate adaptive sphere size based on mesh bounds
        sphere_radius = self._get_measurement_marker_size()
        
        # Add sphere marker at picked point
        try:
            sphere = pv.Sphere(radius=sphere_radius, center=point)
            actor = self.plotter.add_mesh(
                sphere, 
                color='#FF69B4', 
                name=f'measure_pt_{len(self.measurement_points)}_{id(point)}'
            )
            # Make marker always render in front (disable depth testing)
            self._set_actor_always_on_top(actor)
            self.measurement_actors.append(actor)
            logger.info(f"_on_point_picked: Marker added at {point}")
        except Exception as e:
            logger.warning(f"_on_point_picked: Could not add marker: {e}")
        
        # If we have two points, calculate and display the measurement
        if len(self.measurement_points) == 2:
            distance = self._calculate_distance(
                self.measurement_points[0], 
                self.measurement_points[1]
            )
            self._draw_measurement_line(
                self.measurement_points[0],
                self.measurement_points[1],
                distance
            )
            # Reset for next measurement
            self.measurement_points = []
    
    def _get_measurement_marker_size(self):
        """Calculate appropriate marker size based on mesh bounds."""
        if self.current_mesh is None:
            return 1.0
        
        try:
            bounds = self.current_mesh.bounds
            max_dimension = max(
                bounds[1] - bounds[0],  # x range
                bounds[3] - bounds[2],  # y range
                bounds[5] - bounds[4],  # z range
            )
            # Marker size is ~0.25% of the largest dimension for precision
            return max(max_dimension * 0.0025, 0.03)
        except Exception as e:
            logger.warning(f"_get_measurement_marker_size: Could not calculate size: {e}")
            return 1.0
    
    def _calculate_distance(self, point1, point2):
        """Calculate Euclidean distance between two 3D points."""
        import numpy as np
        p1 = np.array(point1)
        p2 = np.array(point2)
        distance = np.linalg.norm(p2 - p1)
        logger.info(f"_calculate_distance: Distance = {distance:.4f}")
        return distance
    
    def _draw_measurement_line(self, point1, point2, distance):
        """Draw measurement line with arrowheads and distance label between two points."""
        import numpy as np
        
        try:
            p1 = np.array(point1)
            p2 = np.array(point2)
            direction = p2 - p1
            length = np.linalg.norm(direction)
            
            if length == 0:
                return
            
            dir_unit = direction / length
            
            # Arrow size proportional to measurement length (~4% of distance)
            arrow_tip_length = max(length * 0.04, 0.2)
            arrow_shaft_radius = max(length * 0.004, 0.05)
            arrow_tip_radius = arrow_shaft_radius * 2.5
            
            # Create the main line as a tube for smooth, crack-free rendering
            tube_radius = max(length * 0.0015, 0.02)
            line = pv.Line(point1, point2)
            tube = line.tube(radius=tube_radius, n_sides=16)
            line_actor = self.plotter.add_mesh(
                tube,
                color='black',
                smooth_shading=True,
                name=f'measure_line_{id(point1)}'
            )
            # Make line always render in front
            self._set_actor_always_on_top(line_actor)
            self.measurement_actors.append(line_actor)
            
            # Arrowhead at point1 (pointing from p2 toward p1)
            try:
                cone1 = pv.Cone(
                    center=p1 + dir_unit * (arrow_tip_length / 2),
                    direction=-dir_unit,
                    height=arrow_tip_length,
                    radius=arrow_tip_radius,
                    resolution=20,
                )
                cone1_actor = self.plotter.add_mesh(
                    cone1,
                    color='black',
                    name=f'measure_arrow1_{id(point1)}'
                )
                # Make arrowhead always render in front
                self._set_actor_always_on_top(cone1_actor)
                self.measurement_actors.append(cone1_actor)
            except Exception as e:
                logger.warning(f"_draw_measurement_line: Could not add arrowhead 1: {e}")
            
            # Arrowhead at point2 (pointing from p1 toward p2)
            try:
                cone2 = pv.Cone(
                    center=p2 - dir_unit * (arrow_tip_length / 2),
                    direction=dir_unit,
                    height=arrow_tip_length,
                    radius=arrow_tip_radius,
                    resolution=20,
                )
                cone2_actor = self.plotter.add_mesh(
                    cone2,
                    color='black',
                    name=f'measure_arrow2_{id(point1)}'
                )
                # Make arrowhead always render in front
                self._set_actor_always_on_top(cone2_actor)
                self.measurement_actors.append(cone2_actor)
            except Exception as e:
                logger.warning(f"_draw_measurement_line: Could not add arrowhead 2: {e}")
            
            # Calculate midpoint for label
            midpoint = [
                (point1[0] + point2[0]) / 2,
                (point1[1] + point2[1]) / 2,
                (point1[2] + point2[2]) / 2,
            ]
            
            # Add distance label at midpoint
            # Format distance with appropriate precision
            if distance < 1:
                label_text = f"{distance:.4f} mm"
            elif distance < 100:
                label_text = f"{distance:.2f} mm"
            else:
                label_text = f"{distance:.1f} mm"
            
            # Add the label using point labels
            label_points = pv.PolyData([midpoint])
            label_actor = self.plotter.add_point_labels(
                label_points,
                [label_text],
                font_size=12,
                text_color='black',
                font_family='arial',
                bold=True,
                show_points=False,
                always_visible=True,
                name=f'measure_label_{id(point1)}'
            )
            if label_actor:
                # Move label to overlay renderer so it renders in front of the object
                self._set_actor_always_on_top(label_actor)
                self.measurement_actors.append(label_actor)
            
            logger.info(f"_draw_measurement_line: Line and label drawn, distance = {label_text}")
            
            # Force render to show the measurement
            self.plotter.render()
            
        except Exception as e:
            logger.error(f"_draw_measurement_line: Failed to draw measurement: {e}", exc_info=True)
    
    def clear_measurements(self):
        """Clear all measurement visualizations from the viewer."""
        if self.plotter is None:
            return
        
        logger.info("clear_measurements: Clearing all measurements...")
        
        # Remove all measurement actors from both main and overlay renderers
        overlay = getattr(self, '_overlay_renderer', None)
        for actor in self.measurement_actors:
            try:
                self.plotter.remove_actor(actor)
            except Exception:
                pass
            try:
                if overlay is not None:
                    overlay.RemoveActor(actor)
            except Exception:
                pass
        
        self.measurement_actors = []
        self.measurement_points = []
        
        try:
            self.plotter.render()
        except Exception as e:
            logger.debug(f"clear_measurements: Could not render: {e}")
        
        logger.info("clear_measurements: Measurements cleared")
    
    # ========== Ruler Mode Interaction Control ==========
    
    def _enable_zoom_only_interaction(self):
        """Restrict interaction to zoom only (disable rotation and pan) for ruler mode."""
        try:
            import vtk
            iren = self._get_vtk_interactor()
            if iren is None:
                logger.warning("_enable_zoom_only_interaction: No interactor available")
                return
            
            # Store the original interactor style if not already stored
            if not hasattr(self, '_original_interactor_style'):
                self._original_interactor_style = iren.GetInteractorStyle()
            
            # Create a custom interactor style that only allows zoom (dolly)
            # vtkInteractorStyleRubberBandZoom allows only zoom
            zoom_style = vtk.vtkInteractorStyleRubberBandZoom()
            
            # Actually, we want scroll-wheel zoom which is better handled by
            # a custom style. Let's use TrackballCamera but intercept rotation.
            # Simpler approach: use vtkInteractorStyleImage which allows pan + zoom but no rotation
            # For static views, we want zoom only, so let's create minimal style
            
            # Use vtkInteractorStyleTrackballCamera but we'll filter events
            # Better: use vtkInteractorStyleImage which is 2D-like (pan + zoom, no rotate)
            image_style = vtk.vtkInteractorStyleImage()
            iren.SetInteractorStyle(image_style)
            
            logger.info("_enable_zoom_only_interaction: Zoom-only interaction enabled")
        except Exception as e:
            logger.warning(f"_enable_zoom_only_interaction: Failed: {e}")
    
    def _restore_full_interaction(self):
        """Restore full 3D interaction (rotation, pan, zoom)."""
        try:
            import vtk
            iren = self._get_vtk_interactor()
            if iren is None:
                return
            
            if hasattr(self, '_original_interactor_style') and self._original_interactor_style is not None:
                iren.SetInteractorStyle(self._original_interactor_style)
                logger.info("_restore_full_interaction: Original interaction style restored")
            else:
                # Fallback: set a standard trackball camera style
                trackball_style = vtk.vtkInteractorStyleTrackballCamera()
                iren.SetInteractorStyle(trackball_style)
                logger.info("_restore_full_interaction: Trackball camera style set")
        except Exception as e:
            logger.warning(f"_restore_full_interaction: Failed: {e}")
    
    def _get_overlay_renderer(self):
        """Get or create an overlay renderer that always renders on top of the main scene."""
        if getattr(self, '_overlay_renderer', None) is not None:
            return self._overlay_renderer
        
        try:
            import vtk
            render_window = self.plotter.render_window
            
            # Create overlay renderer on layer 1 (main scene is layer 0)
            self._overlay_renderer = vtk.vtkRenderer()
            self._overlay_renderer.SetLayer(1)
            self._overlay_renderer.InteractiveOff()
            
            # Transparent background so main scene shows through
            self._overlay_renderer.SetBackground(0, 0, 0)
            render_window.SetAlphaBitPlanes(True)
            self._overlay_renderer.SetBackgroundAlpha(0.0)
            
            # Enable multiple layers
            render_window.SetNumberOfLayers(2)
            render_window.AddRenderer(self._overlay_renderer)
            
            # Share the same camera so views stay in sync
            self._overlay_renderer.SetActiveCamera(
                self.plotter.renderer.GetActiveCamera()
            )
            
            logger.debug("_get_overlay_renderer: Overlay renderer created")
        except Exception as e:
            logger.warning(f"_get_overlay_renderer: Failed to create overlay renderer: {e}")
            self._overlay_renderer = None
        
        return self._overlay_renderer

    def _set_actor_always_on_top(self, actor):
        """Move an actor to the overlay renderer so it always renders in front.
        
        Also disables depth testing on the actor so it is never occluded.
        """
        if actor is None:
            return
        try:
            overlay = self._get_overlay_renderer()
            if overlay is not None:
                # Remove from main renderer and add to overlay
                self.plotter.renderer.RemoveActor(actor)
                overlay.AddActor(actor)
                logger.debug("_set_actor_always_on_top: Actor moved to overlay renderer")
            else:
                # Fallback: use polygon offset if overlay renderer unavailable
                mapper = actor.GetMapper()
                if mapper is not None:
                    mapper.SetResolveCoincidentTopologyToPolygonOffset()
                    mapper.SetRelativeCoincidentTopologyPolygonOffsetParameters(-2, -2)
                logger.debug("_set_actor_always_on_top: Fallback polygon offset applied")
            
            # Disable depth testing so actor is never hidden behind geometry
            try:
                prop = actor.GetProperty()
                if prop is not None:
                    prop.SetOpacity(1.0)
                    # Render on top by disabling depth comparison
                    prop.LightingOff()
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"_set_actor_always_on_top: Failed: {e}")
    
    # ========== Orthographic View Methods for Ruler Mode ==========
    
    def view_front_ortho(self):
        """Set camera to front view with orthographic projection."""
        if self.plotter is None:
            return
        try:
            self.plotter.view_yz()
            self.plotter.enable_parallel_projection()
            logger.info("view_front_ortho: Front orthographic view set")
        except Exception as e:
            logger.warning(f"view_front_ortho: Could not set view: {e}")
    
    def view_right_ortho(self):
        """Set camera to right view with orthographic projection."""
        if self.plotter is None:
            return
        try:
            self.plotter.view_xz()
            self.plotter.enable_parallel_projection()
            logger.info("view_right_ortho: Right orthographic view set")
        except Exception as e:
            logger.warning(f"view_right_ortho: Could not set view: {e}")
    
    def view_left_ortho(self):
        """Set camera to left view with orthographic projection."""
        if self.plotter is None:
            return
        try:
            # Left view: looking down the -Y axis
            self.plotter.view_xz(negative=True)
            self.plotter.enable_parallel_projection()
            logger.info("view_left_ortho: Left orthographic view set")
        except Exception as e:
            logger.warning(f"view_left_ortho: Could not set view: {e}")
    
    def view_top_ortho(self):
        """Set camera to top view with orthographic projection."""
        if self.plotter is None:
            return
        try:
            self.plotter.view_xy()
            self.plotter.enable_parallel_projection()
            logger.info("view_top_ortho: Top orthographic view set")
        except Exception as e:
            logger.warning(f"view_top_ortho: Could not set view: {e}")
    
    def view_bottom_ortho(self):
        """Set camera to bottom view with orthographic projection."""
        if self.plotter is None:
            return
        try:
            # Bottom view: looking down the -Z axis
            self.plotter.view_xy(negative=True)
            self.plotter.enable_parallel_projection()
            logger.info("view_bottom_ortho: Bottom orthographic view set")
        except Exception as e:
            logger.warning(f"view_bottom_ortho: Could not set view: {e}")
    
    def view_rear_ortho(self):
        """Set camera to rear view with orthographic projection."""
        if self.plotter is None:
            return
        try:
            # Rear view: looking down the -X axis
            self.plotter.view_yz(negative=True)
            self.plotter.enable_parallel_projection()
            logger.info("view_rear_ortho: Rear orthographic view set")
        except Exception as e:
            logger.warning(f"view_rear_ortho: Could not set view: {e}")
    
    # ========== Annotation Mode Methods ==========
    
    def enable_annotation_mode(self, callback=None):
        """Enable annotation mode for adding 3D point annotations.
        
        Args:
            callback: Function to call when a point is picked. Receives (point_tuple,).
        """
        if self.plotter is None:
            logger.warning("enable_annotation_mode: Plotter not initialized")
            return False
        
        if self.current_mesh is None:
            logger.warning("enable_annotation_mode: No mesh loaded")
            return False
        
        logger.info("enable_annotation_mode: Enabling annotation mode...")
        self.annotation_mode = True
        self._annotation_callback = callback
        
        # Disable ruler mode if active
        if self.ruler_mode:
            self.disable_ruler_mode()
        
        # Install click picking for annotations
        if self._install_annotation_click_picking():
            logger.info("enable_annotation_mode: Annotation mode enabled")
            return True
        
        logger.warning("enable_annotation_mode: Failed to install picking")
        self.annotation_mode = False
        return False
    
    def disable_annotation_mode(self):
        """Disable annotation mode."""
        if self.plotter is None:
            return
        
        logger.info("disable_annotation_mode: Disabling annotation mode...")
        self.annotation_mode = False
        self._annotation_callback = None
        
        # Remove our observer
        self._uninstall_annotation_click_picking()
        
        try:
            self.plotter.disable_picking()
        except Exception:
            pass
        
        logger.info("disable_annotation_mode: Annotation mode disabled")
    
    def _install_annotation_click_picking(self) -> bool:
        """Install VTK observer for annotation point picking."""
        try:
            import vtk
        except ImportError as e:
            logger.warning(f"_install_annotation_click_picking: vtk import failed: {e}")
            return False
        
        iren = self._get_vtk_interactor()
        if iren is None:
            logger.warning("_install_annotation_click_picking: Could not get VTK interactor")
            return False
        
        # Remove any previous observer
        self._uninstall_annotation_click_picking()
        
        # Create picker
        self._annotation_picker = vtk.vtkCellPicker()
        try:
            self._annotation_picker.SetTolerance(0.01)
        except Exception:
            pass
        
        # Restrict to model actor
        if self.current_actor is not None:
            try:
                self.current_actor.SetPickable(True)
                self._annotation_picker.PickFromListOn()
                self._annotation_picker.AddPickList(self.current_actor)
            except Exception as e:
                logger.debug(f"_install_annotation_click_picking: Could not restrict pick list: {e}")
                try:
                    self._annotation_picker.PickFromListOff()
                except Exception:
                    pass
        
        try:
            self._annotation_click_observer_id = iren.AddObserver(
                "LeftButtonPressEvent",
                self._on_annotation_left_click,
                1.0,
            )
            logger.info("_install_annotation_click_picking: VTK click observer installed")
            return True
        except Exception as e:
            logger.error(f"_install_annotation_click_picking: Failed to add observer: {e}", exc_info=True)
            self._annotation_click_observer_id = None
            self._annotation_picker = None
            return False
    
    def _uninstall_annotation_click_picking(self):
        """Remove VTK observer for annotation picking."""
        if self._annotation_click_observer_id is None:
            self._annotation_picker = None
            return
        
        iren = self._get_vtk_interactor()
        try:
            if iren is not None:
                iren.RemoveObserver(self._annotation_click_observer_id)
                logger.info("_uninstall_annotation_click_picking: Observer removed")
        except Exception as e:
            logger.debug(f"_uninstall_annotation_click_picking: Could not remove observer: {e}")
        finally:
            self._annotation_click_observer_id = None
            self._annotation_picker = None
    
    def _on_annotation_left_click(self, obj, event):
        """VTK callback for annotation point picking."""
        if not self.annotation_mode or self.plotter is None or self._annotation_picker is None:
            return
        
        iren = self._get_vtk_interactor()
        if iren is None:
            return
        
        try:
            x, y = iren.GetEventPosition()
        except Exception:
            return
        
        logger.info(f"_on_annotation_left_click: click screen=({x},{y})")
        
        renderer = getattr(self.plotter, 'renderer', None)
        if renderer is None:
            try:
                renderer = self.plotter.ren_win.GetRenderers().GetFirstRenderer()
            except Exception:
                renderer = None
        
        if renderer is None:
            logger.info("_on_annotation_left_click: No renderer available")
            return
        
        try:
            self._annotation_picker.Pick(x, y, 0, renderer)
            cell_id = self._annotation_picker.GetCellId()
            if cell_id == -1:
                logger.info(f"_on_annotation_left_click: No hit at ({x}, {y})")
                return
            
            picked_world = self._annotation_picker.GetPickPosition()
            
            # Snap to nearest mesh vertex
            snapped = picked_world
            try:
                if self.current_mesh is not None and hasattr(self.current_mesh, 'find_closest_point'):
                    idx = self.current_mesh.find_closest_point(picked_world)
                    snapped = self.current_mesh.points[int(idx)]
            except Exception as e:
                logger.debug(f"_on_annotation_left_click: Vertex snapping failed: {e}")
            
            point_tuple = tuple(float(c) for c in snapped)
            logger.info(f"_on_annotation_left_click: hit at {point_tuple}")
            
            # Call the callback if set
            if self._annotation_callback is not None:
                self._annotation_callback(point_tuple)
            
        except Exception as e:
            logger.error(f"_on_annotation_left_click: Picking failed: {e}", exc_info=True)
    
    def add_annotation_marker(self, annotation_id: int, point: tuple, color: str = '#9CA3AF') -> object:
        """Add a visible marker for an annotation point.
        
        Args:
            annotation_id: Unique ID for the annotation
            point: (x, y, z) world coordinates
            color: Marker color (hex string) - default gray for pending
            
        Returns:
            The actor for the marker, or None if failed
        """
        if self.plotter is None or self.current_mesh is None:
            return None
        
        try:
            # Flat 1.5% of max dimension — consistent across all model sizes
            try:
                bounds = self.current_mesh.bounds
                dim_x = bounds[1] - bounds[0]
                dim_y = bounds[3] - bounds[2]
                dim_z = bounds[5] - bounds[4]
                max_dim = max(dim_x, dim_y, dim_z)
                sphere_radius = max_dim * 0.012
                logger.info(
                    f"add_annotation_marker: dims=({dim_x:.2f}, {dim_y:.2f}, {dim_z:.2f}) "
                    f"max_dim={max_dim:.2f} → radius={sphere_radius:.4f} "
                    f"({sphere_radius/max_dim*100:.1f}% of model)"
                )
            except Exception:
                sphere_radius = 0.5
            
            sphere = pv.Sphere(radius=sphere_radius, center=point)
            actor = self.plotter.add_mesh(
                sphere,
                color=color,
                name=f'annotation_marker_{annotation_id}'
            )
            
            self.annotations.append({
                'id': annotation_id,
                'point': point,
                'actor': actor,
            })
            self.annotation_actors.append(actor)
            
            self.plotter.render()
            logger.info(f"add_annotation_marker: Added marker id={annotation_id} at {point} with color {color}")
            return actor
            
        except Exception as e:
            logger.error(f"add_annotation_marker: Failed: {e}", exc_info=True)
            return None
    
    def update_annotation_marker_color(self, annotation_id: int, color: str):
        """Update the color of an annotation marker.
        
        Args:
            annotation_id: The annotation ID
            color: New color (hex string)
        """
        for ann in self.annotations:
            if ann['id'] == annotation_id:
                try:
                    ann['actor'].GetProperty().SetColor(
                        *self._hex_to_rgb_normalized(color)
                    )
                    self.plotter.render()
                    logger.info(f"update_annotation_marker_color: Updated id={annotation_id} to {color}")
                except Exception as e:
                    logger.warning(f"update_annotation_marker_color: Failed: {e}")
                break
    
    def remove_annotation_marker(self, annotation_id: int):
        """Remove an annotation marker by ID."""
        if self.plotter is None:
            return
        
        for i, ann in enumerate(self.annotations):
            if ann['id'] == annotation_id:
                try:
                    self.plotter.remove_actor(ann['actor'])
                    if ann['actor'] in self.annotation_actors:
                        self.annotation_actors.remove(ann['actor'])
                except Exception as e:
                    logger.debug(f"remove_annotation_marker: Could not remove actor: {e}")
                self.annotations.pop(i)
                self.plotter.render()
                logger.info(f"remove_annotation_marker: Removed id={annotation_id}")
                break
    
    def clear_all_annotation_markers(self):
        """Remove all annotation markers."""
        if self.plotter is None:
            return
        
        logger.info("clear_all_annotation_markers: Clearing all annotations...")
        for ann in self.annotations:
            try:
                self.plotter.remove_actor(ann['actor'])
            except Exception:
                pass
        
        self.annotations = []
        self.annotation_actors = []
        
        try:
            self.plotter.render()
        except Exception:
            pass
        
        logger.info("clear_all_annotation_markers: All annotations cleared")
    
    def focus_on_annotation(self, annotation_id: int):
        """Focus the camera on a specific annotation point."""
        for ann in self.annotations:
            if ann['id'] == annotation_id:
                point = ann['point']
                try:
                    # Set camera to look at this point
                    self.plotter.camera.focal_point = point
                    self.plotter.reset_camera()
                    self.plotter.render()
                    logger.info(f"focus_on_annotation: Focused on id={annotation_id}")
                except Exception as e:
                    logger.warning(f"focus_on_annotation: Failed: {e}")
                break
    
    def _hex_to_rgb_normalized(self, hex_color: str) -> tuple:
        """Convert hex color to normalized RGB tuple."""
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16) / 255.0
        g = int(hex_color[2:4], 16) / 255.0
        b = int(hex_color[4:6], 16) / 255.0
        return (r, g, b)

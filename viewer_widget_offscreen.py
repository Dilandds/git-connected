"""
Alternative 3D Viewer Widget using PyVista offscreen rendering.
This is a fallback for when QtInteractor doesn't work on macOS.
"""
import sys
import os
import logging
import numpy as np
import pyvista as pv
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPixmap, QImage
import io

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


class STLViewerWidgetOffscreen(QWidget):
    """PyVista-based 3D viewer widget using offscreen rendering."""
    
    def __init__(self, parent=None):
        debug_print("STLViewerWidgetOffscreen: Initializing...")
        logger.info("STLViewerWidgetOffscreen: Initializing...")
        super().__init__(parent)
        
        # Set PyVista to offscreen mode
        try:
            pv.OFF_SCREEN = True
            # Try to start xvfb if available (Linux), but don't fail if not available (macOS)
            try:
                pv.start_xvfb()
            except:
                pass  # xvfb not available (e.g., on macOS), that's okay
        except Exception as e:
            debug_print(f"STLViewerWidgetOffscreen: Could not set offscreen mode: {e}")
            logger.warning(f"STLViewerWidgetOffscreen: Could not set offscreen mode: {e}")
        
        # Set up layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # Create image label for displaying rendered scene
        self.image_label = QLabel("Initializing 3D viewer...")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(400, 400)
        self.image_label.setStyleSheet("background-color: white; border: 1px solid #ccc;")
        self.layout.addWidget(self.image_label)
        
        # Create control buttons
        controls_layout = QHBoxLayout()
        self.rotate_left_btn = QPushButton("← Rotate")
        self.rotate_right_btn = QPushButton("Rotate →")
        self.zoom_in_btn = QPushButton("Zoom +")
        self.zoom_out_btn = QPushButton("Zoom -")
        self.reset_btn = QPushButton("Reset View")
        
        controls_layout.addWidget(self.rotate_left_btn)
        controls_layout.addWidget(self.rotate_right_btn)
        controls_layout.addWidget(self.zoom_in_btn)
        controls_layout.addWidget(self.zoom_out_btn)
        controls_layout.addWidget(self.reset_btn)
        controls_layout.addStretch()
        
        self.layout.addLayout(controls_layout)
        
        # Connect buttons
        self.rotate_left_btn.clicked.connect(lambda: self.rotate_view(-15))
        self.rotate_right_btn.clicked.connect(lambda: self.rotate_view(15))
        self.zoom_in_btn.clicked.connect(lambda: self.zoom_view(1.2))
        self.zoom_out_btn.clicked.connect(lambda: self.zoom_view(0.8))
        self.reset_btn.clicked.connect(self.reset_view)
        
        # Initialize plotter
        self.plotter = None
        self.current_mesh = None
        self.rotation_angle = 0
        
        # Initialize plotter
        self._initialize_plotter()
        
        debug_print("STLViewerWidgetOffscreen: Initialization complete")
        logger.info("STLViewerWidgetOffscreen: Initialization complete")
    
    def _initialize_plotter(self):
        """Initialize the offscreen plotter."""
        try:
            debug_print("STLViewerWidgetOffscreen: Creating offscreen plotter...")
            logger.info("STLViewerWidgetOffscreen: Creating offscreen plotter...")
            
            # Create offscreen plotter
            self.plotter = pv.Plotter(off_screen=True, window_size=[800, 600])
            self.plotter.background_color = 'white'
            
            debug_print("STLViewerWidgetOffscreen: Offscreen plotter created")
            logger.info("STLViewerWidgetOffscreen: Offscreen plotter created")
            
            # Render empty scene
            self._render_scene()
            
        except Exception as e:
            debug_print(f"STLViewerWidgetOffscreen: ERROR during initialization: {e}")
            logger.error(f"STLViewerWidgetOffscreen: Error during initialization: {e}", exc_info=True)
            self.image_label.setText(f"Error initializing 3D viewer: {str(e)}")
    
    def _render_scene(self):
        """Render the current scene to an image and display it."""
        if self.plotter is None:
            return
        
        try:
            # Render to numpy array
            image = self.plotter.screenshot()
            
            # Convert numpy array to QPixmap
            height, width, channel = image.shape
            bytes_per_line = 3 * width
            q_image = QImage(image.data, width, height, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(q_image)
            
            # Scale to fit label while maintaining aspect ratio
            label_size = self.image_label.size()
            if label_size.width() > 0 and label_size.height() > 0:
                pixmap = pixmap.scaled(label_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            # Display in label
            self.image_label.setPixmap(pixmap)
            self.image_label.setText("")  # Clear text
            
        except Exception as e:
            debug_print(f"STLViewerWidgetOffscreen: Error rendering scene: {e}")
            logger.error(f"STLViewerWidgetOffscreen: Error rendering scene: {e}", exc_info=True)
    
    def load_stl(self, file_path):
        """
        Load and display an STL or STEP file.
        
        Args:
            file_path (str): Path to the STL or STEP file
            
        Returns:
            bool: True if successful, False otherwise
        """
        logger.info(f"load_stl: Starting to load file: {file_path}")
        try:
            # Clear previous mesh
            if self.current_mesh is not None:
                self.plotter.clear()
            
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
            elif file_ext.endswith('.dxf'):
                logger.info("load_stl: Detected DXF file, loading with DxfLoader...")
                from core.dxf_loader import DxfLoader
                try:
                    mesh = DxfLoader.load_dxf(file_path)
                    logger.info(f"load_stl: DXF file loaded successfully. Mesh info: {mesh}")
                except Exception as e:
                    logger.error(f"load_stl: Failed to load DXF file: {e}", exc_info=True)
                    raise
            else:
                logger.info("load_stl: Reading STL file with PyVista...")
                # Read STL file using PyVista
                mesh = pv.read(file_path)
                logger.info(f"load_stl: STL file read successfully. Mesh info: {mesh}")
            
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
            logger.info("load_stl: Computing mesh normals...")
            try:
                render_mesh.compute_normals(inplace=True, point_normals=True, cell_normals=False)
                logger.info("load_stl: Mesh normals computed successfully")
            except Exception as e:
                logger.warning(f"load_stl: Could not compute normals: {e}, continuing anyway")
            
            logger.info("load_stl: Adding mesh to plotter...")
            # Add mesh to plotter
            # Use the processed mesh for rendering (with normals and triangulation if successful)
            self.plotter.add_mesh(
                render_mesh,
                color='lightblue',
                show_edges=False,
                smooth_shading=False,
                ambient=0.7,  # Increased for less shadowing
                diffuse=0.4,  # Reduced to balance with higher ambient
                specular=0.2,  # Reduced for less harsh highlights
                specular_power=20  # Reduced for softer specular
            )
            
            # Add axes
            self.plotter.add_axes()
            
            logger.info("load_stl: Resetting camera...")
            # Fit view to show entire model
            self.plotter.reset_camera()
            self.rotation_angle = 0
            
            # Render and display
            self._render_scene()
            
            logger.info("load_stl: STL file loaded successfully")
            return True
            
        except Exception as e:
            logger.error(f"load_stl: Error loading STL file: {e}", exc_info=True)
            return False
    
    def rotate_view(self, angle):
        """Rotate the view by the specified angle."""
        if self.plotter is None or self.current_mesh is None:
            return
        
        self.rotation_angle += angle
        self.plotter.camera_position = self.plotter.camera_position
        self.plotter.camera.azimuth(angle)
        self._render_scene()
    
    def zoom_view(self, factor):
        """Zoom the view by the specified factor."""
        if self.plotter is None or self.current_mesh is None:
            return
        
        self.plotter.camera.zoom(factor)
        self._render_scene()
    
    def reset_view(self):
        """Reset the view to default."""
        if self.plotter is None or self.current_mesh is None:
            return
        
        self.plotter.reset_camera()
        self.rotation_angle = 0
        self._render_scene()
    
    def clear_viewer(self):
        """Clear the 3D viewer."""
        if self.plotter is None:
            return
        logger.info("clear_viewer: Clearing viewer...")
        self.plotter.clear()
        self.plotter.add_axes()
        self.current_mesh = None
        self.rotation_angle = 0
        self._render_scene()
        logger.info("clear_viewer: Viewer cleared")
    
    def resizeEvent(self, event):
        """Handle resize events to update the displayed image."""
        super().resizeEvent(event)
        if self.plotter is not None and self.current_mesh is not None:
            # Re-render on resize
            QTimer.singleShot(100, self._render_scene)

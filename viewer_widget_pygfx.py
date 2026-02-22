"""
Minimal 3D Viewer Widget using pygfx + wgpu for STL file visualization.
WebGPU-based (avoids OpenGL) - intended to fix Windows black screen.
Settings match PyVista viewer for consistent default view and rendering.
"""
import sys
import os
import logging
import numpy as np
from PyQt5.QtWidgets import QWidget, QStackedLayout, QGridLayout
from PyQt5.QtCore import Qt, pyqtSignal
from ui.drop_zone_overlay import DropZoneOverlay

logger = logging.getLogger(__name__)


def _trimesh_to_pyvista(tm):
    """Convert trimesh (Trimesh or Scene) to PyVista PolyData for MeshCalculator compatibility."""
    import trimesh
    import numpy as np
    import pyvista as pv

    if isinstance(tm, trimesh.Scene):
        all_meshes = [g for g in tm.geometry.values() if isinstance(g, trimesh.Trimesh)]
        if not all_meshes:
            return None
        tm = trimesh.util.concatenate(all_meshes) if len(all_meshes) > 1 else all_meshes[0]

    if not isinstance(tm, trimesh.Trimesh):
        return None

    vertices = np.asarray(tm.vertices, dtype=np.float64)
    faces = np.asarray(tm.faces, dtype=np.int32)
    cells = np.column_stack([np.full(len(faces), 3), faces]).ravel().astype(np.int32)
    return pv.PolyData(vertices, cells)


def _debug_print(msg):
    print(f"[DEBUG] {msg}", file=sys.stderr)
    if sys.stderr:
        try:
            sys.stderr.flush()
        except (AttributeError, OSError):
            pass


class STLViewerWidget(QWidget):
    """Minimal pygfx-based 3D viewer for STL files. File upload and display only."""

    file_dropped = pyqtSignal(str)
    click_to_upload = pyqtSignal()
    drop_error = pyqtSignal(str)

    def __init__(self, parent=None):
        _debug_print("STLViewerWidget (pygfx): Initializing...")
        logger.info("STLViewerWidget (pygfx): Initializing...")
        super().__init__(parent)

        self.layout = QStackedLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setStackingMode(QStackedLayout.StackAll)

        self.viewer_container = QWidget()
        self.viewer_layout = QGridLayout(self.viewer_container)
        self.viewer_layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self.viewer_container)

        self.drop_overlay = DropZoneOverlay()
        self.drop_overlay.file_dropped.connect(self._on_file_dropped)
        self.drop_overlay.click_to_upload.connect(self._on_click_upload)
        self.drop_overlay.error_occurred.connect(self._on_drop_error)
        self.layout.addWidget(self.drop_overlay)

        self.layout.setCurrentWidget(self.drop_overlay)

        self._canvas = None
        self._renderer = None
        self._scene = None
        self._camera = None
        self._controller = None
        self._mesh_obj = None
        self.current_mesh = None  # Trimesh object for compatibility
        self.current_actor = None  # Not used; kept for hasattr checks
        self.plotter = None  # Not used; kept for hasattr checks
        self._model_loaded = False
        self._initialized = False
        self._render_mode = 'solid'

        _debug_print("STLViewerWidget (pygfx): Basic init complete")

    def showEvent(self, event):
        super().showEvent(event)
        if not self._initialized:
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(100, self._init_pygfx)

    def resizeEvent(self, event):
        """Update camera aspect on resize so framing stays correct."""
        super().resizeEvent(event)
        if self._initialized and self._camera is not None and self._canvas is not None:
            try:
                cw, ch = self._canvas.get_logical_size() if hasattr(self._canvas, 'get_logical_size') else (self.width(), self.height())
                if cw > 0 and ch > 0:
                    self._camera.aspect = cw / ch
            except Exception:
                pass

    def _init_pygfx(self):
        if self._initialized:
            return
        try:
            from PyQt5.QtWidgets import QApplication
            QApplication.processEvents()

            if not self.isVisible() or not self.window().isVisible():
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(200, self._init_pygfx)
                return

            _debug_print("STLViewerWidget (pygfx): Creating pygfx canvas...")
            import pygfx as gfx
            from rendercanvas.qt import QRenderWidget

            self._canvas = QRenderWidget(parent=self.viewer_container)
            self.viewer_layout.addWidget(self._canvas)

            self._renderer = gfx.WgpuRenderer(self._canvas)
            # SSAA for sharp edges (PyVista uses FXAA/SSAA)
            try:
                self._renderer.pixel_scale = 2
            except Exception:
                pass

            self._scene = gfx.Scene()
            # White background (PyVista: background_color='white')
            background = gfx.Background.from_color("#ffffff")
            self._scene.add(background)

            # PyVista-equivalent lighting: main (1,1,1) intensity 1.0, fill (-1,-0.5,0.5) intensity 0.4
            self._scene.add(gfx.AmbientLight())
            light1 = gfx.DirectionalLight(color="white", intensity=1.0)
            light1.local.position = (1, 1, 1)
            light1.look_at((0, 0, 0))
            self._scene.add(light1)
            light2 = gfx.DirectionalLight(color="white", intensity=0.4)
            light2.local.position = (-1, -0.5, 0.5)
            light2.look_at((0, 0, 0))
            self._scene.add(light2)

            # Axes (positioned when mesh loads)
            try:
                self._axes = gfx.AxesHelper(1.0)
                self._axes.visible = False  # Show when mesh loaded
                self._scene.add(self._axes)
            except Exception:
                self._axes = None

            w, h = max(400, self.width()), max(300, self.height())
            self._camera = gfx.PerspectiveCamera(50, w / h)
            self._camera.local.position = (0, 0, 5)
            self._camera.local.up = (0, 1, 0)  # Y-up: drag left/right rotates around Y axis
            self._camera.show_pos((0, 0, 0))

            self._controller = gfx.TrackballController(
                self._camera, register_events=self._renderer
            )
            self._controller.auto_update = True

            def animate():
                if self._renderer and self._scene and self._camera:
                    self._renderer.render(self._scene, self._camera)

            self._canvas.request_draw(animate)
            self._initialized = True
            _debug_print("STLViewerWidget (pygfx): pygfx initialized")
            logger.info("STLViewerWidget (pygfx): pygfx initialized")

        except Exception as e:
            _debug_print(f"STLViewerWidget (pygfx): ERROR: {e}")
            logger.error(f"STLViewerWidget (pygfx): Init failed: {e}", exc_info=True)

    def load_stl(self, file_path):
        """Load and display an STL file. Returns True if successful."""
        logger.info(f"load_stl (pygfx): Loading {file_path}")

        if not self._initialized or self._scene is None:
            logger.warning("load_stl (pygfx): Not initialized yet")
            from PyQt5.QtWidgets import QApplication
            for _ in range(50):
                QApplication.processEvents()
                if self._initialized and self._scene is not None:
                    break
                import time
                time.sleep(0.1)
            if not self._initialized or self._scene is None:
                logger.error("load_stl (pygfx): Init failed")
                return False

        file_ext = file_path.lower()
        supported = ('.stl', '.obj', '.ply')
        if not any(file_ext.endswith(ext) for ext in supported):
            logger.warning(f"load_stl (pygfx): Only STL/OBJ/PLY supported, got {file_ext}")
            return False

        try:
            import pygfx as gfx
            from pygfx.geometries import geometry_from_trimesh
            import trimesh

            if self._mesh_obj is not None:
                self._scene.remove(self._mesh_obj)
                self._mesh_obj = None

            # Load with trimesh (same as PyVista: compute normals for smooth shading)
            mesh_tri = trimesh.load(file_path, force='mesh')
            if isinstance(mesh_tri, trimesh.Scene):
                all_meshes = [g for g in mesh_tri.geometry.values() if isinstance(g, trimesh.Trimesh)]
                if not all_meshes:
                    raise ValueError("No meshes in file")
                mesh_tri = trimesh.util.concatenate(all_meshes) if len(all_meshes) > 1 else all_meshes[0]
            if not isinstance(mesh_tri, trimesh.Trimesh):
                raise ValueError("No mesh in file")

            # Compute vertex normals for smooth shading (PyVista: compute_normals point_normals=True)
            try:
                mesh_tri.fix_normals()
            except Exception:
                pass

            # PyVista-equivalent material (lightblue, soft specular). pygfx uses color, specular, shininess.
            material = gfx.MeshPhongMaterial(
                color="#add8e6",
                specular="#333333",  # Dim specular (~0.2) for softer highlights
                shininess=20,
            )
            geometry = geometry_from_trimesh(mesh_tri)
            mesh_obj = gfx.Mesh(geometry, material)
            self._mesh_obj = mesh_obj
            self._scene.add(self._mesh_obj)
            self.set_render_mode(self._render_mode)

            # Convert to PyVista for MeshCalculator compatibility
            pv_mesh = _trimesh_to_pyvista(mesh_tri)
            if pv_mesh is None:
                raise ValueError("Could not convert mesh for dimensions/volume calculation")
            self.current_mesh = pv_mesh
            self._model_loaded = True
            self._show_overlay(False)

            # Ensure layout is complete and canvas has valid size before framing
            from PyQt5.QtWidgets import QApplication
            QApplication.processEvents()

            # Pygfx-recommended: syncs camera + controller orbit center
            # Update camera aspect from current canvas size (critical for correct framing)
            try:
                cw, ch = self._canvas.get_logical_size() if hasattr(self._canvas, 'get_logical_size') else (self.width(), self.height())
            except Exception:
                cw, ch = max(1, self.width()), max(1, self.height())
            self._camera.aspect = cw / ch
            view_dir = (1.2, -0.8, -1.0)  # isometric-like, matches PyVista default
            self._camera.show_object(
                self._mesh_obj, view_dir=view_dir, scale=1.8, up=(0, 1, 0)
            )

            # No fixed orbit target — TrackballController rotates around viewport center

            # Position axes at mesh min corner (PyVista add_axes in corner)
            if getattr(self, '_axes', None) is not None:
                try:
                    b = np.asarray(mesh_tri.bounds)
                    if b.ndim == 2 and b.shape == (2, 3):
                        mins, maxs = b[0], b[1]
                    else:
                        mins = np.array([b[0], b[2], b[4]])
                        maxs = np.array([b[1], b[3], b[5]])
                    max_dim = max(
                        float(maxs[0] - mins[0]),
                        float(maxs[1] - mins[1]),
                        float(maxs[2] - mins[2]),
                        0.01,
                    ) * 0.15
                    self._axes.local.scale = (max_dim, max_dim, max_dim)
                    self._axes.local.position = (float(mins[0]), float(mins[1]), float(mins[2]))
                    self._axes.visible = True
                except Exception:
                    pass

            # Force immediate redraw so object appears without needing a click
            if self._canvas:
                self._canvas.request_draw()
            QApplication.processEvents()
            # Deferred redraws to ensure WebGPU pipeline is ready
            from PyQt5.QtCore import QTimer
            def _deferred_repaint():
                if self._canvas and getattr(self, '_model_loaded', False):
                    self._canvas.request_draw()
            QTimer.singleShot(50, _deferred_repaint)
            QTimer.singleShot(200, _deferred_repaint)

            logger.info("load_stl (pygfx): Loaded successfully")
            return True

        except Exception as e:
            logger.error(f"load_stl (pygfx): Error: {e}", exc_info=True)
            return False

    def set_render_mode(self, mode):
        """Set render mode: 'solid', 'wireframe', or 'shaded'."""
        if self._mesh_obj is None:
            return
        self._render_mode = mode
        import pygfx as gfx
        if mode == 'wireframe':
            self._mesh_obj.material = gfx.MeshBasicMaterial(
                wireframe=True, color="#333333", wireframe_thickness=1
            )
        elif mode == 'shaded':
            self._mesh_obj.material = gfx.MeshPhongMaterial(
                color="#b8b8c0", specular="#a0a0a0", shininess=90
            )
        else:  # solid
            self._mesh_obj.material = gfx.MeshPhongMaterial(
                color="#add8e6", specular="#333333", shininess=20
            )
        if self._canvas:
            self._canvas.request_draw()

    def clear_viewer(self):
        """Clear the 3D viewer."""
        if self._scene and self._mesh_obj:
            self._scene.remove(self._mesh_obj)
            self._mesh_obj = None
        if getattr(self, '_axes', None) is not None:
            try:
                self._axes.visible = False
            except Exception:
                pass
        self.current_mesh = None
        self._model_loaded = False
        self._show_overlay(True)
        if self._canvas:
            self._canvas.update()
        logger.info("clear_viewer (pygfx): Cleared")

    def _on_file_dropped(self, file_path):
        self.file_dropped.emit(file_path)

    def _on_click_upload(self):
        self.click_to_upload.emit()

    def _on_drop_error(self, error_msg):
        self.drop_error.emit(error_msg)

    def _show_overlay(self, show):
        if show:
            self.drop_overlay.show()
            self.drop_overlay.raise_()
        else:
            self.drop_overlay.hide()

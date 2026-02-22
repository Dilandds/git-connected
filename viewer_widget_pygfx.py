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


def _pyvista_to_trimesh(pv_mesh):
    """Convert PyVista PolyData to trimesh.Trimesh for pygfx rendering."""
    import trimesh
    import pyvista as pv

    try:
        pv_mesh = pv_mesh.triangulate()
    except Exception:
        pass
    verts = np.asarray(pv_mesh.points, dtype=np.float64)
    faces_arr = pv_mesh.faces
    # PyVista: [3, i0, i1, i2, 3, i3, i4, i5, ...] for triangles
    if len(faces_arr) >= 4 and len(faces_arr) % 4 == 0:
        faces = faces_arr.reshape(-1, 4)[:, 1:4]
    else:
        # Parse variable-length faces
        idx = 0
        faces_list = []
        while idx < len(faces_arr):
            n = int(faces_arr[idx])
            idx += 1
            if n == 3 and idx + 3 <= len(faces_arr):
                faces_list.append([faces_arr[idx], faces_arr[idx + 1], faces_arr[idx + 2]])
            idx += n
        faces = np.array(faces_list, dtype=np.int32) if faces_list else np.zeros((0, 3), dtype=np.int32)
    return trimesh.Trimesh(vertices=verts, faces=faces)


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
        self._grid_visible = False
        self._grid_objects = []  # All pygfx objects making up the bounding box grid

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
            self._background = gfx.Background.from_color("#ffffff")
            self._scene.add(self._background)

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
        """Load and display a 3D file (STL, STEP, 3DM, OBJ, IGES, PLY). Returns True if successful."""
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
        supported = ('.stl', '.obj', '.ply', '.step', '.stp', '.3dm', '.iges', '.igs')
        if not any(file_ext.endswith(ext) for ext in supported):
            logger.warning(f"load_stl (pygfx): Unsupported format, got {file_ext}")
            return False

        try:
            import pygfx as gfx
            from pygfx.geometries import geometry_from_trimesh
            import trimesh
            import pyvista as pv

            if self._mesh_obj is not None:
                self._scene.remove(self._mesh_obj)
                self._mesh_obj = None

            mesh_tri = None
            pv_mesh = None

            # STEP
            if file_ext.endswith('.step') or file_ext.endswith('.stp'):
                logger.info("load_stl (pygfx): Loading STEP with StepLoader...")
                from core.step_loader import StepLoader
                pv_mesh = StepLoader.load_step(file_path)
                if pv_mesh is None or pv_mesh.n_points == 0:
                    raise ValueError("STEP loader returned empty mesh")
                mesh_tri = _pyvista_to_trimesh(pv_mesh)
            # 3DM
            elif file_ext.endswith('.3dm'):
                logger.info("load_stl (pygfx): Loading 3DM with Rhino3dmLoader...")
                from core.rhino3dm_loader import Rhino3dmLoader
                pv_mesh = Rhino3dmLoader.load_3dm(file_path)
                if pv_mesh is None or pv_mesh.n_points == 0:
                    raise ValueError("3DM loader returned empty mesh")
                mesh_tri = _pyvista_to_trimesh(pv_mesh)
            # IGES
            elif file_ext.endswith('.iges') or file_ext.endswith('.igs'):
                logger.info("load_stl (pygfx): Loading IGES with IgesLoader...")
                from core.iges_loader import IgesLoader
                pv_mesh = IgesLoader.load_iges(file_path)
                if pv_mesh is None or pv_mesh.n_points == 0:
                    raise ValueError("IGES loader returned empty mesh")
                mesh_tri = _pyvista_to_trimesh(pv_mesh)
            # OBJ: try trimesh first, fallback to PyVista/meshio/ObjLoader
            elif file_ext.endswith('.obj'):
                mesh_tri = None
                try:
                    mesh_tri = trimesh.load(file_path, force='mesh')
                except Exception:
                    pass
                if mesh_tri is None or (isinstance(mesh_tri, trimesh.Trimesh) and len(mesh_tri.vertices) == 0):
                    try:
                        pv_mesh = pv.read(file_path)
                    except Exception:
                        try:
                            import meshio
                            meshio_mesh = meshio.read(file_path)
                            pts = meshio_mesh.points
                            cells = None
                            for cb in meshio_mesh.cells:
                                if cb.type == "triangle":
                                    cells = cb.data
                                    break
                            if cells is None and meshio_mesh.cells:
                                cells = meshio_mesh.cells[0].data
                            if cells is not None and len(pts) > 0:
                                n_verts = cells.shape[1] if cells.ndim == 2 else 3
                                cells_flat = np.column_stack([np.full(len(cells), n_verts), cells]).ravel().astype(np.int32)
                                pv_mesh = pv.PolyData(pts, cells_flat).triangulate()
                            else:
                                raise ValueError("No cells")
                        except Exception:
                            from core.obj_loader import ObjLoader
                            pv_mesh = ObjLoader.load_obj(file_path)
                    if pv_mesh is not None and pv_mesh.n_points > 0:
                        mesh_tri = _pyvista_to_trimesh(pv_mesh)
                if mesh_tri is None or (isinstance(mesh_tri, trimesh.Trimesh) and len(mesh_tri.vertices) == 0):
                    raise ValueError("OBJ file could not be loaded")
                if pv_mesh is None:
                    pv_mesh = _trimesh_to_pyvista(mesh_tri)
            # STL, PLY: trimesh
            else:
                mesh_tri = trimesh.load(file_path, force='mesh')
                if mesh_tri is None:
                    raise ValueError("No mesh in file")
                pv_mesh = _trimesh_to_pyvista(mesh_tri)

            # Normalize mesh_tri (Scene -> single Trimesh)
            if isinstance(mesh_tri, trimesh.Scene):
                all_meshes = [g for g in mesh_tri.geometry.values() if isinstance(g, trimesh.Trimesh)]
                if not all_meshes:
                    raise ValueError("No meshes in file")
                mesh_tri = trimesh.util.concatenate(all_meshes) if len(all_meshes) > 1 else all_meshes[0]
            if not isinstance(mesh_tri, trimesh.Trimesh) or len(mesh_tri.vertices) == 0:
                raise ValueError("No mesh in file")

            # Compute vertex normals for smooth shading
            try:
                mesh_tri.fix_normals()
            except Exception:
                pass

            # Ensure PyVista for MeshCalculator
            if pv_mesh is None:
                pv_mesh = _trimesh_to_pyvista(mesh_tri)
            if pv_mesh is None:
                raise ValueError("Could not convert mesh for dimensions/volume calculation")

            # PyVista-equivalent material (lightblue, soft specular)
            material = gfx.MeshPhongMaterial(
                color="#add8e6",
                specular="#333333",
                shininess=20,
            )
            geometry = geometry_from_trimesh(mesh_tri)
            mesh_obj = gfx.Mesh(geometry, material)
            self._mesh_obj = mesh_obj
            self._scene.add(self._mesh_obj)
            self.set_render_mode(self._render_mode)

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

    def set_background_color(self, color):
        """Set 3D viewer background color (e.g. '#ffffff' light, '#1a1a2e' dark)."""
        if not self._initialized or not hasattr(self, '_scene') or self._scene is None:
            return
        try:
            import pygfx as gfx
            if getattr(self, '_background', None) is not None:
                self._scene.remove(self._background)
            self._background = gfx.Background.from_color(color)
            self._scene.add(self._background)
            if self._canvas:
                self._canvas.request_draw()
            # Update drop overlay when visible (no model loaded)
            if not self._model_loaded and hasattr(self, 'drop_overlay'):
                self.drop_overlay.setStyleSheet(f"DropZoneOverlay {{ background-color: {color}; }}")
                is_dark = color.lower() == '#1a1a2e'
                primary = '#e2e8f0' if is_dark else '#1a1a2e'
                secondary = '#94a3b8' if is_dark else '#4a5568'
                helper = '#64748b' if is_dark else '#a0aec0'
                self.drop_overlay.primary_label.setStyleSheet(f"QLabel {{ font-size: 18px; font-weight: 600; color: {primary}; background: transparent; }}")
                self.drop_overlay.secondary_label.setStyleSheet(f"QLabel {{ font-size: 14px; font-weight: 400; color: {secondary}; background: transparent; }}")
                self.drop_overlay.helper_label.setStyleSheet(f"QLabel {{ font-size: 11px; font-weight: 400; color: {helper}; background: transparent; margin-top: 8px; }}")
        except Exception as e:
            logger.warning(f"set_background_color (pygfx): {e}")

    def clear_viewer(self):
        """Clear the 3D viewer."""
        self.remove_grid()
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
            self._canvas.request_draw()
        logger.info("clear_viewer (pygfx): Cleared")

    def _on_file_dropped(self, file_path):
        self.file_dropped.emit(file_path)

    def _on_click_upload(self):
        self.click_to_upload.emit()

    def _on_drop_error(self, error_msg):
        self.drop_error.emit(error_msg)

    # ── Bounding-box grid with axis labels & ticks ──────────────────────

    def show_grid(self):
        """Show a 3D bounding box with axis labels and tick marks around the loaded mesh."""
        if not self._initialized or self._scene is None or self.current_mesh is None:
            return
        self.remove_grid()
        self._grid_visible = True

        import pygfx as gfx

        bounds = self.current_mesh.bounds  # (xmin,xmax,ymin,ymax,zmin,zmax)
        xmin, xmax, ymin, ymax, zmin, zmax = [float(v) for v in bounds]

        # ── 12 edges of the bounding box ──
        corners = np.array([
            [xmin, ymin, zmin], [xmax, ymin, zmin],
            [xmax, ymax, zmin], [xmin, ymax, zmin],
            [xmin, ymin, zmax], [xmax, ymin, zmax],
            [xmax, ymax, zmax], [xmin, ymax, zmax],
        ], dtype=np.float32)
        edges = [
            (0,1),(1,2),(2,3),(3,0),  # bottom
            (4,5),(5,6),(6,7),(7,4),  # top
            (0,4),(1,5),(2,6),(3,7),  # verticals
        ]
        for a, b in edges:
            positions = np.array([corners[a], corners[b]], dtype=np.float32)
            geom = gfx.Geometry(positions=positions)
            line = gfx.Line(geom, gfx.LineMaterial(color="#888888", thickness=1.0))
            self._scene.add(line)
            self._grid_objects.append(line)

        # ── Helper: generate nice tick values ──
        def _nice_ticks(vmin, vmax, n=5):
            span = vmax - vmin
            if span <= 0:
                return [vmin]
            raw_step = span / n
            mag = 10 ** np.floor(np.log10(raw_step))
            residual = raw_step / mag
            if residual <= 1.5:
                nice = 1
            elif residual <= 3:
                nice = 2
            elif residual <= 7:
                nice = 5
            else:
                nice = 10
            step = nice * mag
            start = np.ceil(vmin / step) * step
            ticks = []
            v = start
            while v <= vmax + step * 0.01:
                ticks.append(round(float(v), 6))
                v += step
            return ticks

        # ── Helper: create a text label ──
        def _make_text(text, pos, font_size=10, anchor="middle-center"):
            geom = gfx.TextGeometry(text=text, font_size=font_size, anchor=anchor, screen_space=True)
            obj = gfx.Text(geom, gfx.TextMaterial(color="#333333"))
            obj.local.position = tuple(float(p) for p in pos)
            return obj

        # ── Helper: small tick line ──
        def _make_tick_line(p1, p2):
            positions = np.array([p1, p2], dtype=np.float32)
            geom = gfx.Geometry(positions=positions)
            return gfx.Line(geom, gfx.LineMaterial(color="#888888", thickness=1.0))

        tick_len_x = (ymax - ymin) * 0.02 if (ymax - ymin) > 0 else 0.1
        tick_len_y = (xmax - xmin) * 0.02 if (xmax - xmin) > 0 else 0.1
        tick_len_z = (xmax - xmin) * 0.02 if (xmax - xmin) > 0 else 0.1
        label_offset = 0.08  # fraction of axis range for label placement

        # ── X axis ticks & labels (along bottom-front edge at ymin, zmin) ──
        x_ticks = _nice_ticks(xmin, xmax)
        for v in x_ticks:
            tick = _make_tick_line([v, ymin, zmin], [v, ymin - tick_len_x, zmin])
            self._scene.add(tick)
            self._grid_objects.append(tick)
            lbl = _make_text(f"{v:.1f}", [v, ymin - tick_len_x * 3, zmin], font_size=9)
            self._scene.add(lbl)
            self._grid_objects.append(lbl)
        # Axis title
        x_title = _make_text("X Axis", [(xmin + xmax) / 2, ymin - (ymax - ymin) * label_offset * 2, zmin], font_size=12)
        self._scene.add(x_title)
        self._grid_objects.append(x_title)

        # ── Y axis ticks & labels (along bottom-left edge at xmin, zmin) ──
        y_ticks = _nice_ticks(ymin, ymax)
        for v in y_ticks:
            tick = _make_tick_line([xmin, v, zmin], [xmin - tick_len_y, v, zmin])
            self._scene.add(tick)
            self._grid_objects.append(tick)
            lbl = _make_text(f"{v:.1f}", [xmin - tick_len_y * 3, v, zmin], font_size=9)
            self._scene.add(lbl)
            self._grid_objects.append(lbl)
        y_title = _make_text("Y Axis", [xmin - (xmax - xmin) * label_offset * 2, (ymin + ymax) / 2, zmin], font_size=12)
        self._scene.add(y_title)
        self._grid_objects.append(y_title)

        # ── Z axis ticks & labels (along left-front vertical edge at xmin, ymin) ──
        z_ticks = _nice_ticks(zmin, zmax)
        for v in z_ticks:
            tick = _make_tick_line([xmin, ymin, v], [xmin - tick_len_z, ymin, v])
            self._scene.add(tick)
            self._grid_objects.append(tick)
            lbl = _make_text(f"{v:.1f}", [xmin - tick_len_z * 3, ymin, v], font_size=9)
            self._scene.add(lbl)
            self._grid_objects.append(lbl)
        z_title = _make_text("Z Axis", [xmin - (xmax - xmin) * label_offset * 2, ymin, (zmin + zmax) / 2], font_size=12)
        self._scene.add(z_title)
        self._grid_objects.append(z_title)

        if self._canvas:
            self._canvas.request_draw()

    def remove_grid(self):
        """Remove the bounding box grid from the scene."""
        for obj in self._grid_objects:
            try:
                self._scene.remove(obj)
            except Exception:
                pass
        self._grid_objects.clear()
        self._grid_visible = False
        if self._canvas:
            self._canvas.request_draw()

    def toggle_grid(self):
        """Toggle the bounding box grid on/off."""
        if self._grid_visible:
            self.remove_grid()
        else:
            self.show_grid()

    def _show_overlay(self, show):
        if show:
            self.drop_overlay.show()
            self.drop_overlay.raise_()
        else:
            self.drop_overlay.hide()

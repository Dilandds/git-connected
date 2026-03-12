"""
DXF file loader for converting DXF files to PyVista meshes.
Uses ezdxf library for parsing DXF entities.
"""
import logging
import numpy as np
import pyvista as pv

logger = logging.getLogger(__name__)


class DxfLoader:
    """Handles loading DXF files and converting them to PyVista meshes."""

    @staticmethod
    def load_dxf(file_path):
        """
        Load DXF file and convert 3D entities to a PyVista mesh.

        Args:
            file_path (str): Path to the DXF file

        Returns:
            pyvista.PolyData: PyVista mesh object

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file cannot be loaded or contains no 3D geometry
        """
        import os

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"DXF file not found: {file_path}")

        logger.info(f"DxfLoader: Loading DXF file: {file_path}")

        try:
            import ezdxf
        except ImportError:
            raise ValueError(
                "ezdxf library is required for DXF support. Install with: pip install ezdxf"
            )

        try:
            doc = ezdxf.readfile(file_path)
        except Exception as e:
            raise ValueError(f"Failed to read DXF file: {e}")

        msp = doc.modelspace()

        all_points = []
        all_faces = []
        point_offset = 0

        # 1. Extract 3DFACE entities
        for face in msp.query("3DFACE"):
            pts = [face.dxf.vtx0, face.dxf.vtx1, face.dxf.vtx2, face.dxf.vtx3]
            # Convert Vec3 to list
            pts = [[p[0], p[1], p[2]] for p in pts]

            # Check if it's a triangle (vtx2 == vtx3) or quad
            idx = point_offset
            all_points.extend(pts[:3])
            all_faces.append([3, idx, idx + 1, idx + 2])
            point_offset += 3

            # If quad (4th vertex differs from 3rd)
            if pts[2] != pts[3]:
                all_points.append(pts[3])
                all_faces.append([3, idx, idx + 2, idx + 3])
                point_offset += 1

        # 2. Extract MESH entities
        for mesh_entity in msp.query("MESH"):
            try:
                vertices = list(mesh_entity.vertices)
                faces_data = list(mesh_entity.faces)

                if not vertices or not faces_data:
                    continue

                v_pts = [[v[0], v[1], v[2]] for v in vertices]
                idx_base = point_offset
                all_points.extend(v_pts)

                for face_indices in faces_data:
                    fi = list(face_indices)
                    if len(fi) == 3:
                        all_faces.append([3, fi[0] + idx_base, fi[1] + idx_base, fi[2] + idx_base])
                    elif len(fi) >= 4:
                        # Triangulate quads/polygons as fan
                        for i in range(1, len(fi) - 1):
                            all_faces.append([3, fi[0] + idx_base, fi[i] + idx_base, fi[i + 1] + idx_base])

                point_offset += len(v_pts)
            except Exception as e:
                logger.warning(f"DxfLoader: Failed to process MESH entity: {e}")

        # 3. Extract POLYLINE entities (POLYFACE meshes)
        for polyline in msp.query("POLYLINE"):
            try:
                if not polyline.is_poly_face_mesh:
                    continue

                vertices = []
                face_indices_list = []

                for vertex in polyline.vertices:
                    if vertex.is_face_record:
                        # Face record: vtx0..vtx3 are 1-based indices
                        fi = []
                        for attr in ['vtx0', 'vtx1', 'vtx2', 'vtx3']:
                            val = getattr(vertex.dxf, attr, 0)
                            if val != 0:
                                fi.append(abs(val) - 1)  # Convert 1-based to 0-based
                        if len(fi) >= 3:
                            face_indices_list.append(fi)
                    else:
                        loc = vertex.dxf.location
                        vertices.append([loc[0], loc[1], loc[2]])

                if not vertices or not face_indices_list:
                    continue

                idx_base = point_offset
                all_points.extend(vertices)

                for fi in face_indices_list:
                    if len(fi) == 3:
                        all_faces.append([3, fi[0] + idx_base, fi[1] + idx_base, fi[2] + idx_base])
                    elif len(fi) >= 4:
                        for i in range(1, len(fi) - 1):
                            all_faces.append([3, fi[0] + idx_base, fi[i] + idx_base, fi[i + 1] + idx_base])

                point_offset += len(vertices)
            except Exception as e:
                logger.warning(f"DxfLoader: Failed to process POLYLINE entity: {e}")

        # 4. Extract LINE entities as degenerate geometry (for wireframe DXFs)
        if len(all_points) == 0:
            logger.info("DxfLoader: No solid geometry found, trying LINE/LWPOLYLINE entities...")
            # Try trimesh as fallback for complex DXF files
            try:
                import trimesh
                scene = trimesh.load(file_path)
                if isinstance(scene, trimesh.Scene):
                    meshes = [g for g in scene.geometry.values() if isinstance(g, trimesh.Trimesh)]
                    if meshes:
                        combined = trimesh.util.concatenate(meshes)
                        points_array = np.array(combined.vertices, dtype=np.float64)
                        faces_list = np.column_stack([
                            np.full(len(combined.faces), 3, dtype=np.int32),
                            combined.faces.astype(np.int32)
                        ])
                        pv_mesh = pv.PolyData(points_array, faces_list)
                        logger.info(f"DxfLoader: Loaded via trimesh. Points: {pv_mesh.n_points}")
                        return pv_mesh
                elif isinstance(scene, trimesh.Trimesh) and len(scene.vertices) > 0:
                    points_array = np.array(scene.vertices, dtype=np.float64)
                    faces_list = np.column_stack([
                        np.full(len(scene.faces), 3, dtype=np.int32),
                        scene.faces.astype(np.int32)
                    ])
                    pv_mesh = pv.PolyData(points_array, faces_list)
                    logger.info(f"DxfLoader: Loaded via trimesh. Points: {pv_mesh.n_points}")
                    return pv_mesh
            except Exception as e:
                logger.warning(f"DxfLoader: trimesh fallback failed: {e}")

        if len(all_points) == 0:
            raise ValueError(
                f"DXF file contains no 3D geometry: {file_path}\n"
                "The file may only contain 2D entities (lines, arcs, text).\n"
                "DXF import supports: 3DFACE, MESH, and POLYFACE entities."
            )

        # Build PyVista mesh
        points_array = np.array(all_points, dtype=np.float64)
        faces_array = np.hstack(all_faces).astype(np.int32)

        pv_mesh = pv.PolyData(points_array, faces_array)

        logger.info(
            f"DxfLoader: Successfully loaded DXF. Points: {pv_mesh.n_points}, Faces: {pv_mesh.n_cells}"
        )
        return pv_mesh

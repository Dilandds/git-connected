"""
3DM (Rhino 3D) file loader for converting 3DM files to PyVista meshes.
Uses rhino3dm library for loading.
"""
import logging
import numpy as np
import pyvista as pv

logger = logging.getLogger(__name__)


def _extract_rhino_mesh_numpy(mesh, point_offset: int):
    """Convert one rhino3dm.Mesh to numpy arrays, applying a global vertex offset.

    Returns (verts, pv_faces) where:
      verts    — float64 (N, 3) vertex positions
      pv_faces — int32   (K, 4) rows of [3, i, j, k] ready for PyVista
    Returns (None, None) if the mesh has no usable geometry.
    """
    vertices = mesh.Vertices
    faces = mesh.Faces
    if vertices is None or len(vertices) == 0 or faces is None or len(faces) == 0:
        return None, None

    # Vertices — list-comp avoids per-element Python overhead vs. .append loop
    verts = np.array([[v.X, v.Y, v.Z] for v in vertices], dtype=np.float64)

    # Faces — read all at once then vectorise quad→tri splitting
    raw = np.array([(f[0], f[1], f[2], f[3]) for f in faces], dtype=np.int32)
    is_tri = raw[:, 2] == raw[:, 3]  # rhino encodes tris as (A,B,C,C)

    tri_idx = raw[is_tri][:, :3]

    if (~is_tri).any():
        quads = raw[~is_tri]
        q_tri1 = quads[:, [0, 1, 2]]
        q_tri2 = quads[:, [0, 2, 3]]
        all_tris = np.vstack([tri_idx, q_tri1, q_tri2])
    else:
        all_tris = tri_idx

    if len(all_tris) == 0:
        return None, None

    all_tris = all_tris + point_offset

    # Build PyVista connectivity: prepend face-size column (always 3 for triangles)
    prefix = np.full((len(all_tris), 1), 3, dtype=np.int32)
    pv_faces = np.hstack([prefix, all_tris])

    return verts, pv_faces


def _get_brep_face_meshes(brep, rhino3dm, label="Brep"):
    """Extract rhino3dm render meshes from all faces of a Brep."""
    brep_faces = brep.Faces
    if brep_faces is None or len(brep_faces) == 0:
        logger.warning(f"Rhino3dmLoader: {label} has no faces")
        return []

    meshes = []
    for bf in brep_faces:
        try:
            m = bf.GetMesh(rhino3dm.MeshType.Render)
            if m is None:
                m = bf.GetMesh(rhino3dm.MeshType.Any)
            if m is not None:
                meshes.append(m)
        except Exception as e:
            logger.debug(f"Rhino3dmLoader: Could not get mesh from {label} face: {e}")
    return meshes


class Rhino3dmLoader:
    """Handles loading 3DM files and converting them to PyVista meshes."""

    @staticmethod
    def load_with_rhino3dm(file_path):
        """
        Load 3DM file using rhino3dm library.

        Args:
            file_path (str): Path to the 3DM file

        Returns:
            pyvista.PolyData: PyVista mesh object, or None if failed
        """
        try:
            import rhino3dm

            logger.info(f"Rhino3dmLoader: Attempting to load 3DM file with rhino3dm: {file_path}")

            model = rhino3dm.File3dm.Read(file_path)

            if model is None:
                logger.error("Rhino3dmLoader: Failed to read 3DM file - model is None")
                return None

            if model.Objects is None or len(model.Objects) == 0:
                logger.error("Rhino3dmLoader: 3DM file contains no objects")
                return None

            logger.info(f"Rhino3dmLoader: Found {len(model.Objects)} objects in 3DM file")

            # Accumulate per-object numpy arrays; concatenate once at the end.
            per_verts = []
            per_faces = []
            point_offset = 0

            geometry_types = {}
            processed_count = 0
            failed_count = 0

            for obj in model.Objects:
                geometry = obj.Geometry
                if geometry is None:
                    logger.warning("Rhino3dmLoader: Object has no geometry, skipping")
                    continue

                geom_type = type(geometry).__name__
                geometry_types[geom_type] = geometry_types.get(geom_type, 0) + 1

                # Collect rhino3dm Mesh objects for this object
                meshes_to_process = []

                if isinstance(geometry, rhino3dm.Mesh):
                    meshes_to_process = [geometry]
                    processed_count += 1

                elif isinstance(geometry, rhino3dm.Brep):
                    try:
                        meshes_to_process = _get_brep_face_meshes(geometry, rhino3dm, "Brep")
                        if meshes_to_process:
                            processed_count += 1
                        else:
                            failed_count += 1
                    except Exception as e:
                        logger.warning(f"Rhino3dmLoader: Failed to convert Brep to mesh: {e}", exc_info=True)
                        failed_count += 1

                elif isinstance(geometry, rhino3dm.Surface):
                    try:
                        brep = rhino3dm.Brep.CreateFromSurface(geometry)
                        if brep is None:
                            logger.debug("Rhino3dmLoader: Could not create Brep from Surface")
                            failed_count += 1
                        else:
                            meshes_to_process = _get_brep_face_meshes(brep, rhino3dm, "Surface->Brep")
                            if meshes_to_process:
                                processed_count += 1
                            else:
                                failed_count += 1
                    except Exception as e:
                        logger.warning(f"Rhino3dmLoader: Failed to convert Surface to mesh: {e}")
                        failed_count += 1

                elif isinstance(geometry, rhino3dm.Extrusion):
                    try:
                        brep = geometry.ToBrep()
                        if brep is None:
                            failed_count += 1
                        else:
                            meshes_to_process = _get_brep_face_meshes(brep, rhino3dm, "Extrusion->Brep")
                            if meshes_to_process:
                                processed_count += 1
                            else:
                                failed_count += 1
                    except Exception as e:
                        logger.warning(f"Rhino3dmLoader: Failed to convert Extrusion to mesh: {e}", exc_info=True)
                        failed_count += 1

                else:
                    logger.debug(f"Rhino3dmLoader: Skipping unsupported geometry type: {geom_type}")
                    continue

                # Extract geometry using numpy — same path for all object types
                for mesh in meshes_to_process:
                    verts, pv_faces = _extract_rhino_mesh_numpy(mesh, point_offset)
                    if verts is None:
                        continue
                    per_verts.append(verts)
                    per_faces.append(pv_faces)
                    point_offset += len(verts)
                    logger.debug(
                        f"Rhino3dmLoader: Extracted mesh: {len(verts)} verts, {len(pv_faces)} faces"
                    )

            if geometry_types:
                logger.info(f"Rhino3dmLoader: Geometry types found: {geometry_types}")

            logger.info(f"Rhino3dmLoader: Processed {processed_count} objects successfully, {failed_count} failed")

            if not per_verts:
                error_detail = (
                    f"Found {len(model.Objects)} objects with types: {list(geometry_types.keys())}. "
                    f"Processed {processed_count} successfully, {failed_count} failed. "
                    "Mesh/Brep objects may be empty or conversion failed."
                )
                logger.error(f"Rhino3dmLoader: No meshable geometry found in 3DM file. {error_detail}")
                return None

            # Single concatenation — far cheaper than repeated list.extend()
            points_array = np.concatenate(per_verts, axis=0)
            faces_array = np.concatenate(per_faces, axis=0).ravel().astype(np.int32)

            if len(faces_array) == 0:
                logger.error("Rhino3dmLoader: No faces found in 3DM file")
                return None

            pv_mesh = pv.PolyData(points_array, faces_array)

            logger.info(
                f"Rhino3dmLoader: Successfully loaded 3DM file. "
                f"Points: {len(points_array)}, Face entries: {len(faces_array)}"
            )
            return pv_mesh

        except ImportError:
            logger.error("Rhino3dmLoader: rhino3dm library not available. Install with: pip install rhino3dm")
            return None
        except Exception as e:
            logger.warning(f"Rhino3dmLoader: Failed to load with rhino3dm: {e}", exc_info=True)
            return None

    @staticmethod
    def load_3dm(file_path):
        """
        Load 3DM file using meshio.

        Args:
            file_path (str): Path to the 3DM file

        Returns:
            pyvista.PolyData: PyVista mesh object, or None if failed

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file cannot be loaded
        """
        import os

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"3DM file not found: {file_path}")

        logger.info(f"Rhino3dmLoader: Loading 3DM file: {file_path}")

        mesh = Rhino3dmLoader.load_with_rhino3dm(file_path)
        if mesh is not None:
            return mesh

        # Loading failed — collect detail for the error message
        try:
            import rhino3dm
            model = rhino3dm.File3dm.Read(file_path)
            if model is None:
                detail = "File could not be read (model is None)"
            elif model.Objects is None or len(model.Objects) == 0:
                detail = "File contains no objects"
            else:
                geometry_types = {}
                for obj in model.Objects:
                    if obj.Geometry:
                        geom_type = type(obj.Geometry).__name__
                        geometry_types[geom_type] = geometry_types.get(geom_type, 0) + 1
                detail = f"File contains {len(model.Objects)} objects with types: {list(geometry_types.keys())}"
        except Exception as e:
            detail = f"Error analyzing file: {str(e)}"

        error_msg = (
            f"Failed to load 3DM file: {file_path}\n\n"
            f"Details: {detail}\n\n"
            "rhino3dm failed to convert the geometry to a mesh.\n"
            "Please ensure:\n"
            "1. The file is a valid 3DM format\n"
            "2. rhino3dm is properly installed (pip install rhino3dm)\n"
            "3. The file contains meshable geometry (Mesh, Brep, Surface, or Extrusion)\n"
            "4. The file is not corrupted"
        )
        logger.error(f"Rhino3dmLoader: {error_msg}")
        raise ValueError(error_msg)

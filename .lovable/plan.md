

## Goal
Eliminate texture stretching on curved/cylindrical surfaces (visible on the exhaust pipe shown) by replacing the current single-axis planar UV projection with a normal-based "cube/box projection" UV bake.

## Root cause
`_generate_box_uvs()` in `viewer_widget_pygfx.py` does **single-plane projection** — it projects every vertex onto the two largest-span axes only. On a curved pipe, vertices on sides facing parallel to the projection direction get squashed to near-identical UVs, producing the long streaks the user sees.

This is the standard "planar projection on a cylinder" artifact. Stock pygfx materials sample one UV set per vertex, so the fix must happen at UV generation time on the CPU.

## Fix: per-vertex cube/box UV projection
Replace `_generate_box_uvs()` with a true 6-face cube projection:

1. Compute per-vertex normals (use `geom.normals` if present; otherwise derive from face normals averaged per vertex).
2. For each vertex, pick the dominant axis of its normal (`argmax(|nx|, |ny|, |nz|)`).
3. Project that vertex onto the perpendicular plane:
   - normal dominant on X → UV from (Y, Z)
   - normal dominant on Y → UV from (X, Z)
   - normal dominant on Z → UV from (X, Y)
4. Normalize using a single world-scale derived from the mesh bounding box's largest extent (so tiling stays consistent across all 3 planes — no UV size jumps between faces).
5. Keep returning a `(N, 2) float32` array — drop-in compatible with all existing callers (`_ensure_texcoords`, `_reset_and_scale_texcoords`, `_scale_texcoords`, `_apply_texture_to_mesh`).

This is essentially a discrete triplanar bake. It removes streaking on curved surfaces because each vertex uses the projection plane closest to its actual surface orientation. Visible seams between projection regions are minimized by sharing one global scale and by the existing seamless-edge blending already applied to textures.

## Implementation details

**File**: `viewer_widget_pygfx.py`

**Function to replace**: `_generate_box_uvs(self, vertices)` at line 4653.

**New signature**: `_generate_box_uvs(self, vertices, normals=None)` — backward compatible (normals optional; falls back to current behavior only if normals truly unavailable and cannot be computed).

**Helper**: small `_compute_vertex_normals(vertices)` if positions come without normals — but since meshes are built via pyvista/trimesh which compute normals, in practice we read `geom.normals` from the geometry buffer at the call sites.

**Update callers** (3 places) to pass normals when available:
- `_apply_texture_to_mesh` (line ~3714)
- `_ensure_texcoords` (line ~4151)
- `_reset_and_scale_texcoords` (line ~4183)

Each becomes:
```text
normals_buf = getattr(geom, 'normals', None)
normals_data = normals_buf.data if normals_buf is not None else None
uvs = self._generate_box_uvs(pos_data, normals_data)
```

**Important**: Since `_base_texcoords` is cached on geometry, any mesh that already has cached UVs will keep using the old planar bake until reload. Add a one-line cache-bust by versioning the cache attribute name (e.g. `_base_texcoords_v2`) so the new bake is used immediately on first texture application after the update.

## Why this is the right fix
- Targets the actual root cause (projection direction vs surface orientation) rather than masking with stronger tiling.
- No shader changes — works inside stock pygfx `MeshStandardMaterial` / `MeshPhongMaterial`.
- Drop-in: same return shape, same callers, same downstream tiling/scaling logic.
- Works for all current image presets (leathers, woods, stones, metals) and the procedural leather PBR path.
- Consistent global scale keeps tiling density uniform across the model — no visible "patch size" jumps between faces.

## Files changed
- `viewer_widget_pygfx.py` (replace `_generate_box_uvs`, update 3 call sites, version-bump UV cache key)

## Validation after implementation
- Reload the exhaust-pipe model, apply Lapis Lazuli / Leather Orange / Walnut Wood — confirm streaks on curved surfaces are gone.
- Confirm flat parts (mounting flanges) still render the texture cleanly without warping.
- Confirm tile-density slider still works (cache reset path).
- Confirm Education-mode upload restriction is untouched.


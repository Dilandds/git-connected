

# Fix: Tile Density slider only works once

## Problem
Two bugs prevent the Tile Density slider from working after the first change:

1. **No UV reset**: `_ensure_texcoords` returns early if UVs already exist (line 3921). So on subsequent slider changes, the "reset to base" step is skipped, and `_scale_texcoords` multiplies on top of already-scaled UVs — causing compounding or no visible effect.

2. **Wrong parameter type**: `_ensure_texcoords` expects a geometry object but receives a mesh object (`mesh_obj`). It fails silently because `mesh_obj` has no `positions` attribute directly.

## Fix (viewer_widget_pygfx.py)

### 1. Store base UVs and reset properly
In the tile density block (~line 4055-4062), instead of calling `_ensure_texcoords` (which doesn't reset), we will:
- On first call, generate base UVs and store them on the geometry as `_base_texcoords`
- On subsequent calls, copy from `_base_texcoords` back to `texcoords`, then scale

### 2. Handle mesh_obj vs geometry
Extract `geometry` from `mesh_obj` (and handle `Group` children) before operating on UVs.

### Implementation
Replace the tile density block with logic that:
```python
def _reset_and_scale_texcoords(self, mesh_obj, gfx, scale_factor):
    def _process_geom(geom):
        # Store base UVs on first call
        if not hasattr(geom, '_base_texcoords'):
            tc = getattr(geom, 'texcoords', None)
            if tc is None:
                pos = getattr(geom, 'positions', None)
                if pos is None: return
                pos_data = pos.data if hasattr(pos, 'data') else pos
                base = self._generate_box_uvs(pos_data)
            else:
                base = np.array(tc.data if hasattr(tc, 'data') else tc, dtype=np.float32).copy()
            geom._base_texcoords = base
        # Reset to base, then scale
        scaled = geom._base_texcoords.copy() * float(scale_factor)
        geom.texcoords = gfx.Buffer(scaled)

    geom = getattr(mesh_obj, 'geometry', None)
    if geom is not None:
        _process_geom(geom)
    elif hasattr(mesh_obj, 'children'):
        for child in mesh_obj.children:
            child_geom = getattr(child, 'geometry', None)
            if child_geom: _process_geom(child_geom)
```

Then call `self._reset_and_scale_texcoords(mesh_obj, gfx, tile_density)` instead of the current `_ensure_texcoords` + `_scale_texcoords` pair.

**Files to edit**: `viewer_widget_pygfx.py` only.


"""
Procedural texture generation for PBR materials.
Generates leather albedo, normal, and roughness maps using numpy.
No external image files needed.
"""
import numpy as np
import logging

logger = logging.getLogger(__name__)


def _perlin_noise_2d(shape, scale=8, seed=42):
    """Simple value-noise approximation for texture generation."""
    rng = np.random.RandomState(seed)
    h, w = shape
    # Low-res random grid
    grid_h = max(2, h // scale)
    grid_w = max(2, w // scale)
    grid = rng.rand(grid_h + 1, grid_w + 1).astype(np.float32)

    # Interpolation coordinates
    y_coords = np.linspace(0, grid_h - 1, h).astype(np.float32)
    x_coords = np.linspace(0, grid_w - 1, w).astype(np.float32)
    x_grid, y_grid = np.meshgrid(x_coords, y_coords)

    x0 = np.floor(x_grid).astype(int)
    y0 = np.floor(y_grid).astype(int)
    x1 = np.minimum(x0 + 1, grid_w)
    y1 = np.minimum(y0 + 1, grid_h)

    fx = x_grid - x0
    fy = y_grid - y0
    # Smoothstep
    fx = fx * fx * (3 - 2 * fx)
    fy = fy * fy * (3 - 2 * fy)

    top = grid[y0, x0] * (1 - fx) + grid[y0, x1] * fx
    bot = grid[y1, x0] * (1 - fx) + grid[y1, x1] * fx
    return top * (1 - fy) + bot * fy


def _fbm(shape, octaves=4, persistence=0.5, base_scale=8, seed=42):
    """Fractal Brownian Motion — layered noise for natural patterns."""
    result = np.zeros(shape, dtype=np.float32)
    amplitude = 1.0
    total_amp = 0.0
    for i in range(octaves):
        noise = _perlin_noise_2d(shape, scale=max(2, base_scale // (2 ** i)), seed=seed + i * 7)
        result += noise * amplitude
        total_amp += amplitude
        amplitude *= persistence
    return result / total_amp


def generate_leather_albedo(size=512):
    """Generate a leather albedo (base color) texture.
    Returns uint8 RGB array of shape (size, size, 3).
    Brown leather with patchy color variation.
    """
    # Base leather color (warm saddle brown)
    base_r, base_g, base_b = 139, 69, 19  # #8B4513

    # Large-scale color variation (patches)
    patches = _fbm((size, size), octaves=3, base_scale=64, seed=100)
    # Small-scale grain variation
    grain = _fbm((size, size), octaves=4, base_scale=16, seed=200)
    # Very fine detail
    fine = _fbm((size, size), octaves=3, base_scale=4, seed=300)

    # Combine: patches shift hue, grain adds darkness in creases
    variation = patches * 0.6 + grain * 0.3 + fine * 0.1

    # Map to color channels with warm brown palette
    r = base_r + (variation - 0.5) * 60  # ±30
    g = base_g + (variation - 0.5) * 40  # ±20
    b = base_b + (variation - 0.5) * 20  # ±10

    # Add darker crease lines using high-frequency noise
    creases = _fbm((size, size), octaves=5, base_scale=8, seed=400)
    crease_mask = np.clip((creases - 0.45) * 5, 0, 1)  # threshold to create lines
    r -= crease_mask * 25
    g -= crease_mask * 15
    b -= crease_mask * 8

    rgb = np.stack([
        np.clip(r, 0, 255),
        np.clip(g, 0, 255),
        np.clip(b, 0, 255),
    ], axis=-1).astype(np.uint8)

    return rgb


def generate_leather_normal(size=512):
    """Generate a leather normal map.
    Returns uint8 RGB array of shape (size, size, 3).
    Encodes surface grain bumps as a tangent-space normal map.
    """
    # Height map from layered noise (pores + wrinkles)
    wrinkles = _fbm((size, size), octaves=3, base_scale=32, seed=500)
    pores = _fbm((size, size), octaves=4, base_scale=8, seed=600)
    micro = _fbm((size, size), octaves=3, base_scale=3, seed=700)

    height = wrinkles * 0.4 + pores * 0.4 + micro * 0.2

    # Compute normals from height gradients (Sobel-like)
    strength = 2.0  # bump strength
    dy = np.zeros_like(height)
    dx = np.zeros_like(height)
    dy[1:-1, :] = (height[2:, :] - height[:-2, :]) * strength
    dx[:, 1:-1] = (height[:, 2:] - height[:, :-2]) * strength

    # Tangent-space normal: (dx, dy, 1) normalized, mapped to [0,255]
    nz = np.ones_like(dx)
    length = np.sqrt(dx * dx + dy * dy + nz * nz)
    nx = dx / length
    ny = dy / length
    nz_norm = nz / length

    # Map [-1,1] to [0,255]
    r = ((nx * 0.5 + 0.5) * 255).astype(np.uint8)
    g = ((ny * 0.5 + 0.5) * 255).astype(np.uint8)
    b = ((nz_norm * 0.5 + 0.5) * 255).astype(np.uint8)

    return np.stack([r, g, b], axis=-1)


def generate_leather_roughness(size=512):
    """Generate a leather roughness map.
    Returns uint8 grayscale array of shape (size, size).
    Dark = smoother (pore peaks catch light), Light = rougher (matte valleys).
    """
    # Pore pattern
    pores = _fbm((size, size), octaves=4, base_scale=8, seed=800)
    # Large-scale wear
    wear = _fbm((size, size), octaves=2, base_scale=48, seed=900)

    # Base roughness is high (leather is matte), with variation
    roughness = 0.7 + pores * 0.2 + wear * 0.1

    # Clamp and convert to uint8
    roughness = np.clip(roughness, 0, 1)
    return (roughness * 255).astype(np.uint8)


# Cache generated textures
_leather_cache = {}


def get_leather_textures(size=512):
    """Return cached (albedo, normal, roughness) numpy arrays."""
    if size not in _leather_cache:
        logger.info(f"Generating procedural leather textures at {size}x{size}...")
        _leather_cache[size] = (
            generate_leather_albedo(size),
            generate_leather_normal(size),
            generate_leather_roughness(size),
        )
        logger.info("Procedural leather textures generated.")
    return _leather_cache[size]

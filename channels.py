"""Channel isolation and normal-map (_ddna) reconstruction. Pure numpy/PIL, no UI."""

from __future__ import annotations

import numpy as np
from PIL import Image

_IDX = {"R": 0, "G": 1, "B": 2, "A": 3}


def full_rgb(image: Image.Image) -> Image.Image:
    return image.convert("RGBA")


def isolate(image: Image.Image, channel: str) -> Image.Image:
    """Show a single channel as grayscale (opaque)."""
    a = np.asarray(image.convert("RGBA"))
    g = a[:, :, _IDX[channel]]
    return Image.fromarray(np.dstack([g, g, g]), mode="RGB")


def reconstruct_normal(image: Image.Image) -> Image.Image:
    """BC5 normal maps store only X (R) and Y (G); rebuild Z into B.

    z = sqrt(1 - x^2 - y^2) with x,y mapped from [0,255] to [-1,1].
    """
    a = np.asarray(image.convert("RGBA")).astype(np.float32)
    x = a[:, :, 0] / 127.5 - 1.0
    y = a[:, :, 1] / 127.5 - 1.0
    z = np.sqrt(np.clip(1.0 - x * x - y * y, 0.0, 1.0))
    out = np.stack([
        (x * 0.5 + 0.5) * 255.0,
        (y * 0.5 + 0.5) * 255.0,
        (z * 0.5 + 0.5) * 255.0,
    ], axis=-1)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), mode="RGB")

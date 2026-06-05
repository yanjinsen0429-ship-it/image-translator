from __future__ import annotations

from typing import Sequence

import numpy as np
from PIL import Image, ImageDraw


Point = tuple[float, float]


def polygon_to_mask(
    image_size: tuple[int, int],
    polygon_points: Sequence[Point],
) -> np.ndarray:
    """Convert polygon geometry to a binary uint8 mask.

    `image_size` uses Pillow/frontend order: `(width, height)`.
    The returned numpy array uses image array order: `(height, width)`.
    """
    width, height = image_size
    mask_image = Image.new("L", (width, height), 0)

    if polygon_points:
        draw = ImageDraw.Draw(mask_image)
        draw.polygon([(float(x), float(y)) for x, y in polygon_points], fill=255)

    return np.array(mask_image, dtype=np.uint8)


def expand_mask(mask: np.ndarray, padding: int = 0) -> np.ndarray:
    """Expand a binary mask by a square padding radius."""
    if padding <= 0:
        return mask.copy()

    source = np.asarray(mask, dtype=np.uint8)
    padded = np.pad(source, padding, mode="constant", constant_values=0)
    expanded = np.zeros_like(source, dtype=np.uint8)

    kernel_size = padding * 2 + 1
    for y_offset in range(kernel_size):
        for x_offset in range(kernel_size):
            window = padded[
                y_offset : y_offset + source.shape[0],
                x_offset : x_offset + source.shape[1],
            ]
            expanded = np.maximum(expanded, window)

    return expanded

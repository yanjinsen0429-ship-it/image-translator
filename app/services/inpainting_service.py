from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from app.utils.image_mask import Point, expand_mask, polygon_to_mask


class InpaintingService:
    """v0.4 inpainting service.

    This stage only creates masks from OCR geometry. Text removal is left
    intentionally unimplemented for later v0.4 work.
    """

    def create_mask(
        self,
        image_size: tuple[int, int],
        polygon_points: list[Point],
        padding: int = 0,
        debug_output_path: Path | None = None,
    ) -> np.ndarray:
        """Create a text-region mask from OCR geometry."""
        mask = polygon_to_mask(image_size, polygon_points)
        expanded = expand_mask(mask, padding=padding)

        if debug_output_path is not None:
            debug_output_path.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(expanded).save(debug_output_path)

        return expanded

    def export_debug_mask(
        self,
        ocr_result: dict[str, Any],
        image_path: str | Path | None,
        debug_mask_dir: Path,
        image_id: str,
        padding: int = 2,
    ) -> Path | None:
        """Create and save a combined debug mask for OCR block polygons."""
        image_size = self._resolve_image_size(ocr_result, image_path)
        if image_size is None:
            return None

        width, height = image_size
        combined = np.zeros((height, width), dtype=np.uint8)

        for polygon_points in self._iter_ocr_polygons(ocr_result, image_size=image_size):
            mask = polygon_to_mask(image_size, polygon_points)
            combined = np.maximum(combined, mask)

        if not np.any(combined):
            return None

        expanded = expand_mask(combined, padding=padding)
        debug_mask_dir.mkdir(parents=True, exist_ok=True)
        output_path = debug_mask_dir / f"{image_id}_mask.png"
        Image.fromarray(expanded).save(output_path)
        return output_path

    def export_debug_inpainted(
        self,
        image_path: str | Path,
        mask_path: str | Path,
        debug_inpainted_dir: Path,
        image_id: str,
        radius: int = 3,
        algorithm: int | None = None,
    ) -> Path:
        """Create and save an inpainted background preview for debugging."""
        inpainted = self.remove_text(
            image=image_path,
            mask=mask_path,
            radius=radius,
            algorithm=algorithm,
        )
        debug_inpainted_dir.mkdir(parents=True, exist_ok=True)
        output_path = debug_inpainted_dir / f"{image_id}_inpainted.png"
        Image.fromarray(inpainted).save(output_path)
        return output_path

    def remove_text(
        self,
        image: str | Path | np.ndarray,
        mask: str | Path | np.ndarray,
        radius: int = 3,
        algorithm: int | None = None,
    ) -> np.ndarray:
        """Remove text from an image using a prepared mask."""
        image_array = self._load_image_array(image)
        mask_array = self._load_mask_array(mask)
        if mask_array.shape != image_array.shape[:2]:
            raise ValueError("Mask size must match image size.")

        method = cv2.INPAINT_TELEA if algorithm is None else algorithm
        return cv2.inpaint(image_array, mask_array, radius, method)

    def _resolve_image_size(
        self,
        ocr_result: dict[str, Any],
        image_path: str | Path | None,
    ) -> tuple[int, int] | None:
        width = ocr_result.get("image_width")
        height = ocr_result.get("image_height")
        if width and height:
            return int(width), int(height)

        if image_path is None:
            return None

        with Image.open(image_path) as image:
            return image.size

    def _iter_ocr_polygons(
        self,
        ocr_result: dict[str, Any],
        image_size: tuple[int, int] | None = None,
    ) -> list[list[Point]]:
        image_size = image_size or self._resolve_image_size(ocr_result, image_path=None)
        polygons: list[list[Point]] = []
        for block in ocr_result.get("blocks", []):
            if block.get("block_type") == "ignored":
                continue
            if block.get("image_processing_skip_reason"):
                continue
            bbox = block.get("bbox") or {}
            points = bbox.get("points")
            if not points:
                continue
            if image_size is not None and self._is_unsafe_large_short_text_bbox(block, image_size):
                continue
            polygon: list[Point] = []
            for point in points:
                if not isinstance(point, list | tuple) or len(point) < 2:
                    polygon = []
                    break
                polygon.append((float(point[0]), float(point[1])))
            if len(polygon) >= 3:
                polygons.append(polygon)
        return polygons

    def _is_unsafe_large_short_text_bbox(
        self,
        block: dict[str, Any],
        image_size: tuple[int, int],
    ) -> bool:
        if block.get("block_type") in {"ignored", "logo", "button"}:
            return False
        text = str(block.get("text") or block.get("source_text") or "").strip()
        if not text or len(text) > 4:
            return False
        bbox = self._block_bbox(block)
        if bbox is None:
            return False
        image_width, image_height = image_size
        image_area = max(1.0, float(image_width) * float(image_height))
        width = max(0.0, bbox[2] - bbox[0])
        height = max(0.0, bbox[3] - bbox[1])
        area_ratio = (width * height) / image_area
        return (
            area_ratio >= 0.18
            and width >= float(image_width) * 0.35
            and height >= float(image_height) * 0.25
        )

    def _block_bbox(self, block: dict[str, Any]) -> tuple[float, float, float, float] | None:
        bbox = block.get("bbox") or {}
        if isinstance(bbox, dict):
            if {"x", "y", "width", "height"}.issubset(bbox):
                x = float(bbox["x"])
                y = float(bbox["y"])
                return (x, y, x + float(bbox["width"]), y + float(bbox["height"]))
            points = bbox.get("points")
            if points:
                return self._points_bbox(points)
        if isinstance(bbox, list | tuple) and len(bbox) >= 4:
            return (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
        return None

    def _points_bbox(self, points: list[Any]) -> tuple[float, float, float, float] | None:
        try:
            xs = [float(point[0]) for point in points]
            ys = [float(point[1]) for point in points]
        except (TypeError, ValueError, IndexError):
            return None
        if not xs or not ys:
            return None
        return (min(xs), min(ys), max(xs), max(ys))

    def _load_image_array(self, image: str | Path | np.ndarray) -> np.ndarray:
        if isinstance(image, np.ndarray):
            image_array = image
        else:
            with Image.open(image) as loaded_image:
                image_array = np.array(loaded_image.convert("RGB"), dtype=np.uint8)

        if image_array.dtype != np.uint8:
            image_array = np.clip(image_array, 0, 255).astype(np.uint8)
        if image_array.ndim == 2:
            image_array = np.stack([image_array] * 3, axis=-1)
        if image_array.ndim != 3 or image_array.shape[2] not in {3, 4}:
            raise ValueError("Image must be a grayscale, RGB, or RGBA array.")
        if image_array.shape[2] == 4:
            image_array = image_array[:, :, :3]
        return image_array

    def _load_mask_array(self, mask: str | Path | np.ndarray) -> np.ndarray:
        if isinstance(mask, np.ndarray):
            mask_array = mask
        else:
            with Image.open(mask) as loaded_mask:
                mask_array = np.array(loaded_mask.convert("L"), dtype=np.uint8)

        if mask_array.ndim == 3:
            mask_array = mask_array[:, :, 0]
        if mask_array.dtype != np.uint8:
            mask_array = np.clip(mask_array, 0, 255).astype(np.uint8)
        return np.where(mask_array > 0, 255, 0).astype(np.uint8)

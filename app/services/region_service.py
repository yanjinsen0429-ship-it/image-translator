from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageDraw

from app.utils.geometry import BBox, bbox_center, bbox_height, bbox_width


RegionType = Literal["bubble", "caption_box", "text_box", "button_like", "unknown"]


@dataclass
class TextRegion:
    id: str
    region_type: RegionType
    bbox: BBox
    polygon: list[list[float]]
    score: float
    source: str = "heuristic"
    linked_block_ids: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def detect_text_regions(
    image_path: str | Path,
    layout_blocks: list[dict[str, Any]],
) -> list[TextRegion]:
    with Image.open(image_path) as image:
        gray = image.convert("L")

    width, height = gray.size
    if width <= 0 or height <= 0:
        return []

    bright_regions = _detect_components(
        gray=gray,
        predicate=lambda value: value >= 245,
        region_type="bubble",
        note="bright fill candidate",
    )
    dark_regions = _detect_components(
        gray=gray,
        predicate=lambda value: value <= 45,
        region_type="caption_box",
        note="dark box candidate",
    )
    button_regions = _button_like_regions(layout_blocks, image_size=(width, height))
    regions = [*bright_regions, *dark_regions, *button_regions]
    regions = _deduplicate_regions(regions)
    regions.sort(key=lambda region: (region.bbox[1], region.bbox[0]))

    linked: list[TextRegion] = []
    for index, region in enumerate(regions, start=1):
        region.id = f"region-{index}"
        region.linked_block_ids = _linked_block_ids(region.bbox, layout_blocks)
        linked.append(region)
    return linked


def _button_like_regions(
    layout_blocks: list[dict[str, Any]],
    image_size: tuple[int, int],
) -> list[TextRegion]:
    image_width, image_height = image_size
    regions: list[TextRegion] = []
    for block in layout_blocks:
        if block.get("block_type") != "button":
            continue
        bbox = _block_bbox(block)
        if bbox is None:
            continue
        pad_x = max(4.0, bbox_width(bbox) * 0.08)
        pad_y = max(4.0, bbox_height(bbox) * 0.25)
        expanded = (
            max(0.0, float(bbox[0]) - pad_x),
            max(0.0, float(bbox[1]) - pad_y),
            min(float(image_width), float(bbox[2]) + pad_x),
            min(float(image_height), float(bbox[3]) + pad_y),
        )
        block_id = block.get("id")
        regions.append(
            TextRegion(
                id="region-0",
                region_type="button_like",
                bbox=expanded,
                polygon=_bbox_to_polygon(expanded),
                score=0.75,
                linked_block_ids=[str(block_id)] if block_id is not None else [],
                notes=["layout button candidate", f"source_block={block_id}"],
            )
        )
    return regions


def export_region_debug_json(
    regions: list[TextRegion],
    output_path: str | Path,
    job_id: str | None = None,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "job_id": job_id,
        "region_count": len(regions),
        "regions": [_region_to_dict(region) for region in regions],
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def export_region_debug_overlay(
    image_path: str | Path,
    regions: list[TextRegion],
    debug_layout_dir: Path,
    image_id: str,
) -> Path:
    debug_layout_dir.mkdir(parents=True, exist_ok=True)
    output_path = debug_layout_dir / f"{image_id}_region_overlay.png"

    with Image.open(image_path) as image:
        overlay = image.convert("RGB")

    draw = ImageDraw.Draw(overlay)
    for region in regions:
        color = _region_color(region.region_type)
        x1, y1, x2, y2 = region.bbox
        draw.rectangle((x1, y1, x2, y2), outline=color, width=2)
        label = f"{region.id} {region.region_type} {region.score:.2f} links:{len(region.linked_block_ids)}"
        draw.text((x1, max(0, y1 - 12)), label, fill=color)

    overlay.save(output_path)
    return output_path


def _detect_components(
    gray: Image.Image,
    predicate,
    region_type: RegionType,
    note: str,
) -> list[TextRegion]:
    width, height = gray.size
    pixels = gray.load()
    visited: set[tuple[int, int]] = set()
    min_area = max(120, int(width * height * 0.002))
    max_area = int(width * height * 0.65)
    regions: list[TextRegion] = []

    for y in range(height):
        for x in range(width):
            if (x, y) in visited or not predicate(pixels[x, y]):
                continue
            component = _flood_component(x, y, width, height, pixels, predicate, visited)
            if not component:
                continue
            x1, y1, x2, y2, area = component
            if area < min_area or area > max_area:
                continue
            bbox = (x1, y1, x2 + 1, y2 + 1)
            box_area = max(1.0, bbox_width(bbox) * bbox_height(bbox))
            fill_ratio = area / box_area
            if fill_ratio < 0.45:
                continue
            score = min(1.0, fill_ratio)
            resolved_type = _resolve_region_type(region_type, bbox)
            regions.append(
                TextRegion(
                    id="region-0",
                    region_type=resolved_type,
                    bbox=bbox,
                    polygon=_bbox_to_polygon(bbox),
                    score=round(score, 4),
                    notes=[note, f"component_area={area}", f"fill_ratio={fill_ratio:.2f}"],
                )
            )
    return regions


def _flood_component(
    start_x: int,
    start_y: int,
    width: int,
    height: int,
    pixels,
    predicate,
    visited: set[tuple[int, int]],
) -> tuple[int, int, int, int, int] | None:
    queue: deque[tuple[int, int]] = deque([(start_x, start_y)])
    visited.add((start_x, start_y))
    x1 = x2 = start_x
    y1 = y2 = start_y
    area = 0

    while queue:
        x, y = queue.popleft()
        area += 1
        x1 = min(x1, x)
        y1 = min(y1, y)
        x2 = max(x2, x)
        y2 = max(y2, y)
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if nx < 0 or ny < 0 or nx >= width or ny >= height or (nx, ny) in visited:
                continue
            if predicate(pixels[nx, ny]):
                visited.add((nx, ny))
                queue.append((nx, ny))
    if area <= 0:
        return None
    return x1, y1, x2, y2, area


def _resolve_region_type(base_type: RegionType, bbox: BBox) -> RegionType:
    if base_type == "caption_box":
        width = bbox_width(bbox)
        height = bbox_height(bbox)
        if height <= 0:
            return "unknown"
        return "caption_box" if width / height >= 1.2 else "text_box"
    return base_type


def _linked_block_ids(region_bbox: BBox, layout_blocks: list[dict[str, Any]]) -> list[str]:
    linked: list[str] = []
    for block in layout_blocks:
        block_bbox = _block_bbox(block)
        if block_bbox is None:
            continue
        center = bbox_center(block_bbox)
        if _point_inside_bbox(center, region_bbox) or _overlap_ratio(block_bbox, region_bbox) >= 0.25:
            block_id = block.get("id")
            if block_id is not None:
                linked.append(str(block_id))
    return linked


def _block_bbox(block: dict[str, Any]) -> BBox | None:
    bbox = block.get("bbox")
    if isinstance(bbox, dict):
        x = bbox.get("x")
        y = bbox.get("y")
        width = bbox.get("width")
        height = bbox.get("height")
        if x is None or y is None or width is None or height is None:
            return None
        return (float(x), float(y), float(x) + float(width), float(y) + float(height))
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        return tuple(float(value) for value in bbox)
    return None


def _point_inside_bbox(point: tuple[float, float], bbox: BBox) -> bool:
    return float(bbox[0]) <= point[0] <= float(bbox[2]) and float(bbox[1]) <= point[1] <= float(bbox[3])


def _overlap_ratio(bbox_a: BBox, bbox_b: BBox) -> float:
    x1 = max(float(bbox_a[0]), float(bbox_b[0]))
    y1 = max(float(bbox_a[1]), float(bbox_b[1]))
    x2 = min(float(bbox_a[2]), float(bbox_b[2]))
    y2 = min(float(bbox_a[3]), float(bbox_b[3]))
    if x2 <= x1 or y2 <= y1:
        return 0.0
    overlap_area = (x2 - x1) * (y2 - y1)
    block_area = max(1.0, bbox_width(bbox_a) * bbox_height(bbox_a))
    return overlap_area / block_area


def _deduplicate_regions(regions: list[TextRegion]) -> list[TextRegion]:
    kept: list[TextRegion] = []
    for region in regions:
        if any(_overlap_ratio(region.bbox, other.bbox) >= 0.8 for other in kept):
            continue
        kept.append(region)
    return kept


def _bbox_to_polygon(bbox: BBox) -> list[list[float]]:
    x1, y1, x2, y2 = bbox
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def _region_to_dict(region: TextRegion) -> dict[str, Any]:
    return {
        "id": region.id,
        "region_type": region.region_type,
        "bbox": list(region.bbox),
        "polygon": region.polygon,
        "score": region.score,
        "source": region.source,
        "linked_block_ids": region.linked_block_ids,
        "notes": region.notes,
    }


def _region_color(region_type: RegionType) -> tuple[int, int, int]:
    if region_type == "bubble":
        return (0, 200, 255)
    if region_type == "caption_box":
        return (255, 170, 0)
    if region_type == "text_box":
        return (255, 90, 200)
    if region_type == "button_like":
        return (80, 220, 120)
    return (180, 180, 180)

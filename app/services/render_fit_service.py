from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.rendering_service import RenderingService


def export_render_fit_debug_json(
    layout_blocks: list[dict[str, Any]],
    translation_result: dict[str, Any],
    regions: list[Any],
    output_path: str | Path,
    job_id: str | None = None,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    records = build_render_fit_debug_records(
        layout_blocks=layout_blocks,
        translation_result=translation_result,
        regions=regions,
    )
    payload = {
        "job_id": job_id,
        "record_count": len(records),
        "records": records,
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def build_render_fit_debug_records(
    layout_blocks: list[dict[str, Any]],
    translation_result: dict[str, Any],
    regions: list[Any],
) -> list[dict[str, Any]]:
    translations = _translation_items_by_block_id(translation_result)
    renderer = RenderingService()
    return [
        _render_fit_record(
            block=block,
            translation_item=translations.get(str(block.get("id"))),
            regions=regions,
            renderer=renderer,
        )
        for block in layout_blocks
    ]


def _render_fit_record(
    block: dict[str, Any],
    translation_item: dict[str, Any] | None,
    regions: list[Any],
    renderer: RenderingService,
) -> dict[str, Any]:
    bbox = _block_bbox(block)
    bbox_dict = _bbox_dict(block, bbox)
    width = max(0.0, bbox[2] - bbox[0])
    height = max(0.0, bbox[3] - bbox[1])
    area = width * height
    block_id = str(block.get("id") or "")
    block_type = str(block.get("block_type") or "normal")
    original_text = str(block.get("text") or "")
    translated_text = _translated_text(translation_item)
    linked_region_ids = _linked_region_ids(block, regions)
    original_text_length = len(original_text)
    translated_text_length = len(translated_text or "")
    density = translated_text_length / area if area > 0 else 0.0
    layout = None
    min_font_size = 10 if block_type == "button" else 12
    max_font_size = max(min_font_size, min(48, int(max(1.0, height) * 0.8)))
    if translated_text:
        layout = renderer.calculate_text_layout(
            text=translated_text,
            bbox=bbox_dict,
            block_type=block_type,
        )
    text_area_ratio = _text_area_ratio(layout, area)
    selected_font_size = layout.get("font_size") if layout else None
    line_count = len(layout.get("lines", [])) if layout else 0
    possible_overflow = bool(layout.get("overflow")) if layout else False
    is_font_too_small = bool(translated_text and selected_font_size is not None and selected_font_size <= min_font_size)
    possible_underfilled_bbox = bool(translated_text and area > 0 and text_area_ratio < 0.18)
    debug_notes = _debug_notes(
        translated_text=translated_text,
        linked_region_ids=linked_region_ids,
        width=width,
        height=height,
        area=area,
        original_text_length=original_text_length,
        translated_text_length=translated_text_length,
        possible_underfilled_bbox=possible_underfilled_bbox,
        is_font_too_small=is_font_too_small,
        possible_overflow=possible_overflow,
    )
    return {
        "block_id": block_id,
        "block_type": block_type,
        "bbox": list(bbox),
        "linked_region_ids": linked_region_ids,
        "original_text": original_text,
        "translated_text": translated_text,
        "original_text_length": original_text_length,
        "translated_text_length": translated_text_length,
        "bbox_width": width,
        "bbox_height": height,
        "bbox_area": area,
        "estimated_text_density": round(density, 6),
        "linked_region_count": len(linked_region_ids),
        "selected_font_size": selected_font_size,
        "min_font_size": min_font_size,
        "max_font_size": max_font_size,
        "line_count": line_count,
        "text_area_ratio": round(text_area_ratio, 6),
        "is_font_too_small": is_font_too_small,
        "possible_underfilled_bbox": possible_underfilled_bbox,
        "possible_overflow": possible_overflow,
        "debug_notes": debug_notes,
    }


def _translation_items_by_block_id(translation_result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items = translation_result.get("items") or []
    return {
        str(item.get("block_id")): item
        for item in items
        if item.get("block_id") is not None
    }


def _translated_text(translation_item: dict[str, Any] | None) -> str | None:
    if translation_item is None:
        return None
    text = translation_item.get("translated_text")
    return str(text) if text is not None else None


def _block_bbox(block: dict[str, Any]) -> tuple[float, float, float, float]:
    bbox = block.get("bbox")
    if isinstance(bbox, dict):
        x = float(bbox.get("x") or 0)
        y = float(bbox.get("y") or 0)
        width = float(bbox.get("width") or 0)
        height = float(bbox.get("height") or 0)
        return _normalize_bbox((x, y, x + width, y + height))
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
        return _normalize_bbox((float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])))
    return (0, 0, 0, 0)


def _bbox_dict(block: dict[str, Any], bbox: tuple[float, float, float, float]) -> dict[str, Any]:
    x1, y1, x2, y2 = bbox
    source_bbox = block.get("bbox")
    points = source_bbox.get("points") if isinstance(source_bbox, dict) else block.get("polygon")
    return {
        "x": round(float(x1)),
        "y": round(float(y1)),
        "width": max(1, round(float(x2) - float(x1))),
        "height": max(1, round(float(y2) - float(y1))),
        "points": points,
    }


def _linked_region_ids(block: dict[str, Any], regions: list[Any]) -> list[str]:
    existing = block.get("linked_region_ids")
    if isinstance(existing, list):
        return [str(region_id) for region_id in existing]

    block_id = block.get("id")
    block_bbox = _block_bbox(block)
    linked: list[str] = []
    for region in regions:
        region_id = getattr(region, "id", None)
        if region_id is None and isinstance(region, dict):
            region_id = region.get("id")
        if region_id is None:
            continue

        linked_block_ids = getattr(region, "linked_block_ids", None)
        if linked_block_ids is None and isinstance(region, dict):
            linked_block_ids = region.get("linked_block_ids")
        if block_id is not None and linked_block_ids and str(block_id) in {str(item) for item in linked_block_ids}:
            linked.append(str(region_id))
            continue

        region_bbox = getattr(region, "bbox", None)
        if region_bbox is None and isinstance(region, dict):
            region_bbox = region.get("bbox")
        if region_bbox is None:
            continue
        region_bbox = _region_bbox(region_bbox)
        if _bbox_contains(region_bbox, block_bbox) or _point_inside_bbox(_bbox_center(block_bbox), region_bbox):
            linked.append(str(region_id))
            continue
        if _overlap_ratio(block_bbox, region_bbox) >= 0.25:
            linked.append(str(region_id))
    return linked


def _region_bbox(bbox: Any) -> tuple[float, float, float, float]:
    if isinstance(bbox, dict):
        x = float(bbox.get("x") or 0)
        y = float(bbox.get("y") or 0)
        width = float(bbox.get("width") or 0)
        height = float(bbox.get("height") or 0)
        return _normalize_bbox((x, y, x + width, y + height))
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
        return _normalize_bbox((float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])))
    return (0, 0, 0, 0)


def _text_area_ratio(layout: dict[str, Any] | None, bbox_area: float) -> float:
    if layout is None or bbox_area <= 0:
        return 0.0
    text_width = float(layout.get("text_width") or 0)
    text_height = float(layout.get("text_height") or 0)
    return min(1.0, max(0.0, (text_width * text_height) / bbox_area))


def _debug_notes(
    translated_text: str | None,
    linked_region_ids: list[str],
    width: float,
    height: float,
    area: float,
    original_text_length: int,
    translated_text_length: int,
    possible_underfilled_bbox: bool,
    is_font_too_small: bool,
    possible_overflow: bool,
) -> list[str]:
    notes: list[str] = []
    if not translated_text:
        notes.append("no_translated_text")
    if not linked_region_ids:
        notes.append("no_linked_region")
    if width < 24 or height < 16 or area < 500:
        notes.append("small_bbox")
    if translated_text_length >= 40 or (
        original_text_length > 0 and translated_text_length >= original_text_length * 2 and translated_text_length >= 20
    ):
        notes.append("long_translation")
    if height > max(1.0, width) * 1.5:
        notes.append("possible_vertical_text_region")
    if possible_underfilled_bbox:
        notes.append("possible_underfilled_bbox")
    if is_font_too_small:
        notes.append("possible_font_too_small")
    if possible_overflow:
        notes.append("possible_overflow")
    return notes


def _bbox_contains(container: tuple[float, float, float, float], inner: tuple[float, float, float, float]) -> bool:
    return (
        container[0] <= inner[0]
        and container[1] <= inner[1]
        and container[2] >= inner[2]
        and container[3] >= inner[3]
    )


def _point_inside_bbox(point: tuple[float, float], bbox: tuple[float, float, float, float]) -> bool:
    return bbox[0] <= point[0] <= bbox[2] and bbox[1] <= point[1] <= bbox[3]


def _bbox_center(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)


def _overlap_ratio(bbox_a: tuple[float, float, float, float], bbox_b: tuple[float, float, float, float]) -> float:
    x1 = max(bbox_a[0], bbox_b[0])
    y1 = max(bbox_a[1], bbox_b[1])
    x2 = min(bbox_a[2], bbox_b[2])
    y2 = min(bbox_a[3], bbox_b[3])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    overlap_area = (x2 - x1) * (y2 - y1)
    block_area = max(1.0, (bbox_a[2] - bbox_a[0]) * (bbox_a[3] - bbox_a[1]))
    return overlap_area / block_area


def _normalize_bbox(bbox: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    return tuple(int(value) if float(value).is_integer() else float(value) for value in bbox)  # type: ignore[return-value]

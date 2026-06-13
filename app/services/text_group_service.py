from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageDraw

from app.utils.geometry import BBox, bbox_height, bbox_union, bbox_width


TextDirection = Literal["horizontal", "vertical", "unknown"]
GROUPABLE_REGION_TYPES = {"bubble", "caption_box", "text_box"}


@dataclass
class TextGroup:
    group_id: str
    region_id: str
    region_type: str
    grouped_block_ids: list[str]
    group_bbox: BBox
    text_direction: TextDirection
    source_texts: list[str]
    merged_source_text: str
    can_render_inline: bool = True
    skipped_reason: str | None = None


def build_text_groups(
    layout_blocks: list[dict[str, Any]],
    regions: list[Any],
    skipped_candidates: list[dict[str, Any]] | None = None,
) -> list[TextGroup]:
    blocks_by_id = {
        str(block.get("id")): block
        for block in layout_blocks
        if block.get("id") is not None
    }
    used_block_ids: set[str] = set()
    groups: list[TextGroup] = []
    for region in regions:
        region_type = str(_region_value(region, "region_type") or "unknown")
        if region_type not in GROUPABLE_REGION_TYPES:
            continue
        linked_ids = [
            str(block_id)
            for block_id in (_region_value(region, "linked_block_ids") or [])
            if str(block_id) in blocks_by_id and str(block_id) not in used_block_ids
        ]
        linked_blocks = [blocks_by_id[block_id] for block_id in linked_ids]
        unsafe_blocks = [block for block in linked_blocks if not _is_groupable_block(block)]
        if unsafe_blocks:
            _append_skipped_candidate(
                skipped_candidates,
                region,
                linked_blocks,
                _source_blocks_skipped_reason(unsafe_blocks) or "unsafe_block_type",
            )
            continue

        candidate_blocks = linked_blocks
        if len(candidate_blocks) < 2:
            continue

        group_bbox = bbox_union([_block_bbox(block) for block in candidate_blocks])
        if _is_ui_short_label_region(region, candidate_blocks, group_bbox):
            _append_skipped_candidate(skipped_candidates, region, candidate_blocks, "ui_short_label")
            continue
        if _is_too_small_non_vertical_region(region, group_bbox):
            _append_skipped_candidate(skipped_candidates, region, candidate_blocks, "too_small_region")
            continue

        source_texts = [str(block.get("text") or "").strip() for block in candidate_blocks if str(block.get("text") or "").strip()]
        group = TextGroup(
            group_id=f"text_group_{_safe_id(str(_region_value(region, 'id') or len(groups) + 1))}",
            region_id=str(_region_value(region, "id") or ""),
            region_type=region_type,
            grouped_block_ids=[str(block.get("id")) for block in candidate_blocks],
            group_bbox=group_bbox,
            text_direction=_text_direction(region, candidate_blocks, group_bbox),
            source_texts=source_texts,
            merged_source_text=_merge_source_texts(source_texts),
            can_render_inline=_source_blocks_can_render_inline(candidate_blocks),
            skipped_reason=_source_blocks_skipped_reason(candidate_blocks),
        )
        groups.append(group)
        used_block_ids.update(group.grouped_block_ids)
    return groups


def apply_text_groups(
    layout_blocks: list[dict[str, Any]],
    text_groups: list[TextGroup],
) -> list[dict[str, Any]]:
    if not text_groups:
        return layout_blocks

    groups_by_first_block_id: dict[str, TextGroup] = {}
    grouped_block_ids: set[str] = set()
    for group in text_groups:
        if not group.grouped_block_ids:
            continue
        groups_by_first_block_id[group.grouped_block_ids[0]] = group
        grouped_block_ids.update(group.grouped_block_ids)

    output: list[dict[str, Any]] = []
    for block in layout_blocks:
        block_id = str(block.get("id"))
        group = groups_by_first_block_id.get(block_id)
        if group is not None:
            output.append(_group_to_block(group, layout_blocks))
            continue
        if block_id in grouped_block_ids:
            continue
        output.append(block)
    return output


def export_text_group_debug_json(
    blocks: list[dict[str, Any]],
    translation_result: dict[str, Any],
    output_path: str | Path,
    job_id: str | None = None,
    skipped_candidates: list[dict[str, Any]] | None = None,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    translations = {
        str(item.get("block_id")): item
        for item in translation_result.get("items", [])
        if item.get("block_id") is not None
    }
    groups = [
        _text_group_debug_record(block, translations.get(str(block.get("id"))))
        for block in blocks
        if block.get("is_text_group")
    ]
    payload = {
        "job_id": job_id,
        "group_count": len(groups),
        "skipped_candidate_count": len(skipped_candidates or []),
        "groups": groups,
        "skipped_candidates": skipped_candidates or [],
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def export_text_group_debug_overlay(
    image_path: str | Path,
    blocks: list[dict[str, Any]],
    output_path: str | Path,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(image_path) as image:
        overlay = image.convert("RGB")

    draw = ImageDraw.Draw(overlay)
    for block in blocks:
        if not block.get("is_text_group"):
            continue
        bbox = _block_bbox(block)
        x1, y1, x2, y2 = bbox
        color = (170, 70, 255) if block.get("text_direction") == "vertical" else (40, 170, 255)
        draw.rectangle((x1, y1, x2, y2), outline=color, width=3)
        label = (
            f"{block.get('group_id') or block.get('id')} "
            f"blocks={len(block.get('grouped_block_ids') or [])} "
            f"{block.get('text_direction') or 'unknown'}"
        )
        draw.text((x1, max(0, y1 - 12)), label, fill=color)

    overlay.save(output_path)
    return output_path


def _group_to_block(group: TextGroup, layout_blocks: list[dict[str, Any]]) -> dict[str, Any]:
    source_blocks = [
        block
        for block in layout_blocks
        if str(block.get("id")) in set(group.grouped_block_ids)
    ]
    x1, y1, x2, y2 = group.group_bbox
    return {
        "id": group.group_id,
        "text": group.merged_source_text,
        "bbox": {
            "x": round(float(x1)),
            "y": round(float(y1)),
            "width": round(float(x2) - float(x1)),
            "height": round(float(y2) - float(y1)),
            "points": _bbox_to_polygon(group.group_bbox),
        },
        "polygon": _bbox_to_polygon(group.group_bbox),
        "confidence": _average_confidence(source_blocks),
        "line_index": 0,
        "language": None,
        "source_items": source_blocks,
        "block_type": "normal",
        "source_block_ids": group.grouped_block_ids,
        "is_text_group": True,
        "group_id": group.group_id,
        "region_id": group.region_id,
        "region_type": group.region_type,
        "linked_region_ids": [group.region_id] if group.region_id else [],
        "text_direction": group.text_direction,
        "grouped_block_ids": group.grouped_block_ids,
        "source_texts": group.source_texts,
        "merged_source_text": group.merged_source_text,
        "can_render_inline": group.can_render_inline,
        "can_translate": group.skipped_reason is None,
        "can_mask": group.can_render_inline,
        "can_inpaint": group.can_render_inline,
        "can_render": group.can_render_inline,
        "can_group": True,
        "block_role": "manga_text_group",
        "ui_screen_mode": False,
        "ui_like": False,
        "skipped_reason": group.skipped_reason,
    }


def _text_group_debug_record(
    block: dict[str, Any],
    translation_item: dict[str, Any] | None,
) -> dict[str, Any]:
    bbox = _block_bbox(block)
    can_render_inline = block.get("can_render_inline") is not False
    return {
        "group_id": block.get("group_id") or block.get("id"),
        "region_id": block.get("region_id"),
        "region_type": block.get("region_type"),
        "text_direction": block.get("text_direction") or "unknown",
        "group_bbox": list(bbox),
        "grouped_block_ids": block.get("grouped_block_ids") or [],
        "source_texts": block.get("source_texts") or [],
        "merged_source_text": block.get("merged_source_text") or block.get("text"),
        "translated_text": translation_item.get("translated_text") if translation_item else None,
        "can_render_inline": can_render_inline,
        "can_translate": block.get("can_translate", can_render_inline),
        "can_mask": block.get("can_mask", can_render_inline),
        "can_inpaint": block.get("can_inpaint", can_render_inline),
        "can_render": block.get("can_render", can_render_inline),
        "block_role": block.get("block_role") or "manga_text_group",
        "ui_screen_mode": bool(block.get("ui_screen_mode")),
        "ui_like": bool(block.get("ui_like")),
        "skipped_reason": block.get("skipped_reason"),
        "whether_used_for_mask": can_render_inline,
        "whether_used_for_inpaint": can_render_inline,
        "whether_used_for_render": can_render_inline,
    }


def _is_groupable_block(block: dict[str, Any]) -> bool:
    if block.get("can_group") is False:
        return False
    return block.get("block_type") not in {"ignored", "logo", "button"}


def _is_ui_short_label_region(region: Any, blocks: list[dict[str, Any]], group_bbox: BBox) -> bool:
    region_type = str(_region_value(region, "region_type") or "unknown")
    if region_type == "bubble":
        return False

    region_bbox = _normalize_bbox(_region_value(region, "bbox") or group_bbox)
    region_height = bbox_height(region_bbox)
    region_width = bbox_width(region_bbox)
    group_height = bbox_height(group_bbox)
    group_width = bbox_width(group_bbox)
    texts = [str(block.get("text") or "").strip() for block in blocks if str(block.get("text") or "").strip()]
    if not texts:
        return True

    max_text_len = max(len(text) for text in texts)
    short_text_ratio = sum(1 for text in texts if len(text) <= 8) / len(texts)
    numeric_or_status_ratio = sum(1 for text in texts if _is_status_like_text(text)) / len(texts)
    low_horizontal_band = region_height <= 56 and region_width >= region_height * 3
    compact_group_band = group_height <= 48 and group_width >= max(group_height, 1) * 2.2

    return (
        (low_horizontal_band or compact_group_band)
        and short_text_ratio >= 0.66
        and (max_text_len <= 12 or numeric_or_status_ratio >= 0.33)
    )


def _is_too_small_non_vertical_region(region: Any, group_bbox: BBox) -> bool:
    region_bbox = _normalize_bbox(_region_value(region, "bbox") or group_bbox)
    if bbox_height(region_bbox) >= bbox_width(region_bbox) * 1.35:
        return False
    if str(_region_value(region, "region_type") or "unknown") == "bubble":
        return False
    return bbox_width(region_bbox) * bbox_height(region_bbox) < 4500


def _is_status_like_text(text: str) -> bool:
    clean = text.strip()
    if not clean:
        return True
    allowed = set("0123456789/.,:%+-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
    return all(char in allowed for char in clean)


def _append_skipped_candidate(
    skipped_candidates: list[dict[str, Any]] | None,
    region: Any,
    blocks: list[dict[str, Any]],
    reason: str,
) -> None:
    if skipped_candidates is None:
        return
    skipped_candidates.append(
        {
            "region_id": _region_value(region, "id"),
            "region_type": _region_value(region, "region_type") or "unknown",
            "linked_block_ids": [str(block.get("id")) for block in blocks if block.get("id") is not None],
            "source_texts": [str(block.get("text") or "").strip() for block in blocks if str(block.get("text") or "").strip()],
            "skipped_reason": reason,
        }
    )


def _source_blocks_can_render_inline(blocks: list[dict[str, Any]]) -> bool:
    return _source_blocks_skipped_reason(blocks) is None


def _source_blocks_skipped_reason(blocks: list[dict[str, Any]]) -> str | None:
    for block in blocks:
        if block.get("can_render_inline") is False:
            return (
                block.get("skipped_reason")
                or block.get("render_skip_reason")
                or block.get("image_processing_skip_reason")
                or "source_block_not_renderable"
            )
        reason = block.get("skipped_reason") or block.get("render_skip_reason") or block.get("image_processing_skip_reason")
        if reason:
            return str(reason)
    return None


def _text_direction(region: Any, blocks: list[dict[str, Any]], group_bbox: BBox) -> TextDirection:
    region_bbox = _region_value(region, "bbox") or group_bbox
    bbox = _normalize_bbox(region_bbox)
    if bbox_height(bbox) >= bbox_width(bbox) * 1.35:
        return "vertical"
    if bbox_width(bbox) >= bbox_height(bbox) * 1.35:
        return "horizontal"
    if len(blocks) >= 2:
        centers = [_bbox_center(_block_bbox(block)) for block in blocks]
        x_spread = max(center[0] for center in centers) - min(center[0] for center in centers)
        y_spread = max(center[1] for center in centers) - min(center[1] for center in centers)
        if y_spread > x_spread * 1.4:
            return "vertical"
        if x_spread > y_spread * 1.4:
            return "horizontal"
    return "unknown"


def _merge_source_texts(texts: list[str]) -> str:
    clean = [text.strip() for text in texts if text.strip()]
    return " ".join(clean)


def _block_bbox(block: dict[str, Any]) -> BBox:
    return _normalize_bbox(block.get("bbox"))


def _normalize_bbox(bbox: Any) -> BBox:
    if isinstance(bbox, dict):
        x = float(bbox.get("x") or 0)
        y = float(bbox.get("y") or 0)
        width = float(bbox.get("width") or 0)
        height = float(bbox.get("height") or 0)
        return _clean_bbox((x, y, x + width, y + height))
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
        return _clean_bbox((float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])))
    return (0, 0, 0, 0)


def _bbox_to_polygon(bbox: BBox) -> list[list[float]]:
    x1, y1, x2, y2 = bbox
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def _bbox_center(bbox: BBox) -> tuple[float, float]:
    return ((float(bbox[0]) + float(bbox[2])) / 2, (float(bbox[1]) + float(bbox[3])) / 2)


def _region_value(region: Any, key: str) -> Any:
    if isinstance(region, dict):
        return region.get(key)
    return getattr(region, key, None)


def _average_confidence(blocks: list[dict[str, Any]]) -> float | None:
    values = [block.get("confidence") for block in blocks if block.get("confidence") is not None]
    if not values:
        return None
    return sum(float(value) for value in values) / len(values)


def _safe_id(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)


def _clean_bbox(bbox: tuple[float, float, float, float]) -> BBox:
    return tuple(int(value) if float(value).is_integer() else float(value) for value in bbox)  # type: ignore[return-value]

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.utils.geometry import (
    BBox,
    bbox_height,
    bbox_union,
    bbox_width,
    height_similarity_ratio,
    horizontal_overlap_ratio,
    polygon_to_bbox,
    vertical_gap,
)


BlockType = Literal["normal", "paragraph", "button", "logo", "ignored"]


@dataclass
class LayoutBlock:
    id: str
    text: str
    polygon: list[list[float]]
    bbox: BBox
    source_block_ids: list[str]
    block_type: BlockType = "normal"
    confidence: float | None = None
    translated_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def normalize_ocr_block(block: dict[str, Any], index: int) -> dict[str, Any]:
    block_id = str(block.get("id") or f"ocr_{index}")
    text = str(block.get("text") or "")
    polygon = _extract_polygon(block)
    bbox = _extract_bbox(block, polygon)
    if polygon is None:
        polygon = _bbox_to_polygon(bbox)

    return {
        "id": block_id,
        "text": text,
        "polygon": polygon,
        "bbox": bbox,
        "confidence": block.get("confidence"),
    }


def classify_block(
    block: dict[str, Any],
    image_size: tuple[int, int] | None = None,
) -> BlockType:
    text = str(block.get("text") or "").strip()
    bbox = block.get("bbox")
    if not text or bbox is None:
        return "ignored"

    words = text.split()
    width = bbox_width(bbox)
    height = bbox_height(bbox)
    aspect_ratio = width / height if height > 0 else 0
    text_lower = text.lower()
    cta_terms = {
        "submit",
        "cancel",
        "report",
        "abuse report",
        "login",
        "log in",
        "sign up",
        "continue",
    }
    is_short = len(text) <= 30 or len(words) <= 4
    is_cta = text_lower in cta_terms

    if image_size is not None and is_short:
        image_width, image_height = image_size
        near_top = bbox[1] <= image_height * 0.15
        near_left = bbox[0] <= image_width * 0.25
        brand_like = text.replace(" ", "").isupper() or len(words) == 1
        if near_top and near_left and brand_like and not is_cta:
            return "logo"

    if is_short and aspect_ratio >= 2 and is_cta:
        return "button"

    return "normal"


def merge_ocr_blocks(
    ocr_blocks: list[dict[str, Any]],
    image_size: tuple[int, int] | None = None,
) -> list[LayoutBlock]:
    normalized = [normalize_ocr_block(block, index) for index, block in enumerate(ocr_blocks)]
    typed_blocks = [
        {
            **block,
            "block_type": classify_block(block, image_size=image_size),
        }
        for block in normalized
    ]
    typed_blocks.sort(key=lambda block: (block["bbox"][1], block["bbox"][0]))

    layout_blocks: list[LayoutBlock] = []
    current_group: list[dict[str, Any]] = []

    def flush_group() -> None:
        if not current_group:
            return
        layout_blocks.append(_group_to_layout_block(current_group))
        current_group.clear()

    for block in typed_blocks:
        if block["block_type"] != "normal":
            flush_group()
            layout_blocks.append(_single_to_layout_block(block))
            continue

        if not current_group:
            current_group.append(block)
            continue

        previous = current_group[-1]
        if _should_merge(previous, block):
            current_group.append(block)
        else:
            flush_group()
            current_group.append(block)

    flush_group()
    return layout_blocks


def _should_merge(block_a: dict[str, Any], block_b: dict[str, Any]) -> bool:
    bbox_a = block_a["bbox"]
    bbox_b = block_b["bbox"]
    max_height = max(bbox_height(bbox_a), bbox_height(bbox_b))
    return (
        vertical_gap(bbox_a, bbox_b) <= max_height * 1.2
        and horizontal_overlap_ratio(bbox_a, bbox_b) >= 0.4
        and height_similarity_ratio(bbox_a, bbox_b) >= 0.6
        and not _is_standalone_cta(block_a["text"])
        and not _is_standalone_cta(block_b["text"])
    )


def _single_to_layout_block(block: dict[str, Any]) -> LayoutBlock:
    return LayoutBlock(
        id=f"layout_{block['id']}",
        text=block["text"],
        polygon=block["polygon"],
        bbox=block["bbox"],
        source_block_ids=[block["id"]],
        block_type=block["block_type"],
        confidence=block.get("confidence"),
    )


def _group_to_layout_block(group: list[dict[str, Any]]) -> LayoutBlock:
    union_bbox = bbox_union([block["bbox"] for block in group])
    source_ids = [block["id"] for block in group]
    text = " ".join(block["text"].strip() for block in group if block["text"].strip())
    return LayoutBlock(
        id="layout_" + "_".join(source_ids),
        text=text,
        polygon=_bbox_to_polygon(union_bbox),
        bbox=union_bbox,
        source_block_ids=source_ids,
        block_type="paragraph" if len(group) > 1 else "normal",
        confidence=_average_confidence(group),
    )


def _average_confidence(group: list[dict[str, Any]]) -> float | None:
    values = [block.get("confidence") for block in group if block.get("confidence") is not None]
    if not values:
        return None
    return sum(float(value) for value in values) / len(values)


def _extract_polygon(block: dict[str, Any]) -> list[list[float]] | None:
    polygon = block.get("polygon")
    if polygon:
        return _normalize_polygon(polygon)

    bbox = block.get("bbox")
    if isinstance(bbox, dict) and bbox.get("points"):
        return _normalize_polygon(bbox["points"])
    return None


def _extract_bbox(block: dict[str, Any], polygon: list[list[float]] | None) -> BBox:
    bbox = block.get("bbox")
    if isinstance(bbox, dict):
        if {"x", "y", "width", "height"}.issubset(bbox):
            x1 = float(bbox["x"])
            y1 = float(bbox["y"])
            return _normalize_bbox((x1, y1, x1 + float(bbox["width"]), y1 + float(bbox["height"])))
        if bbox.get("points"):
            return polygon_to_bbox(bbox["points"])
    if isinstance(bbox, tuple | list) and len(bbox) >= 4:
        return _normalize_bbox((float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])))
    if polygon is not None:
        return polygon_to_bbox(polygon)
    return (0, 0, 0, 0)


def _normalize_polygon(polygon: list[list[Any]]) -> list[list[float]]:
    normalized: list[list[float]] = []
    for point in polygon:
        x = float(point[0])
        y = float(point[1])
        normalized.append([int(x) if x.is_integer() else x, int(y) if y.is_integer() else y])
    return normalized


def _normalize_bbox(bbox: BBox) -> BBox:
    return tuple(int(value) if float(value).is_integer() else float(value) for value in bbox)  # type: ignore[return-value]


def _bbox_to_polygon(bbox: BBox) -> list[list[float]]:
    x1, y1, x2, y2 = bbox
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def _is_standalone_cta(text: str) -> bool:
    text_lower = text.strip().lower()
    return text_lower in {
        "submit",
        "cancel",
        "report",
        "abuse report",
        "login",
        "log in",
        "sign up",
        "continue",
    }

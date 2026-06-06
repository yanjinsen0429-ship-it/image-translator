from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageDraw

from app.utils.geometry import (
    BBox,
    bbox_center,
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
    if is_likely_ocr_noise_block(block):
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


def is_likely_ocr_noise_block(block: dict[str, Any]) -> bool:
    text = str(block.get("text") or "").strip()
    bbox = block.get("bbox")
    if not text or bbox is None:
        return False

    if text in {"]", "[", "|", "/", "\\", "_", ".", ",", ":", ";"}:
        return True

    if text not in {"E", "I", "l"}:
        return False

    width = bbox_width(bbox)
    height = bbox_height(bbox)
    return width <= 12 and height <= 18 and (width * height) <= 216


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
    typed_blocks = refine_noise_blocks(typed_blocks)
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
            if current_group:
                previous = current_group[-1]
                if len(current_group) == 1 and _should_merge_button_pair(previous, block):
                    layout_blocks.append(_group_to_layout_block([previous, block], block_type="button"))
                    current_group.clear()
                    continue
                if len(current_group) > 1 and _should_extend_paragraph_with_short_cta(previous, block):
                    current_group.append(block)
                    continue
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


def refine_noise_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refined: list[dict[str, Any]] = []
    for block in blocks:
        if _is_isolated_single_letter_noise(block, blocks):
            refined.append({**block, "block_type": "ignored"})
        else:
            refined.append(block)
    return refined


def export_layout_debug_overlay(
    image_path: str | Path,
    blocks: list[dict[str, Any]],
    debug_layout_dir: Path,
    image_id: str,
) -> Path:
    debug_layout_dir.mkdir(parents=True, exist_ok=True)
    output_path = debug_layout_dir / f"{image_id}_layout_overlay.png"

    with Image.open(image_path) as image:
        overlay = image.convert("RGB")

    draw = ImageDraw.Draw(overlay)
    for index, block in enumerate(blocks, start=1):
        geometry = _render_geometry(block)
        if geometry is None:
            continue

        color = _overlay_color(block)
        label = _overlay_label(index, block)
        if len(geometry) >= 3:
            draw.line([*geometry, geometry[0]], fill=color, width=2)
            label_x, label_y = geometry[0]
        else:
            x1, y1 = geometry[0]
            x2, y2 = geometry[1]
            draw.rectangle((x1, y1, x2, y2), outline=color, width=2)
            label_x, label_y = x1, y1
        draw.text((label_x, max(0, label_y - 12)), label, fill=color)

    overlay.save(output_path)
    return output_path


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


def _should_merge_button_pair(block_a: dict[str, Any], block_b: dict[str, Any]) -> bool:
    bbox_a = block_a["bbox"]
    bbox_b = block_b["bbox"]
    union_bbox = bbox_union([bbox_a, bbox_b])
    max_height = max(bbox_height(bbox_a), bbox_height(bbox_b))
    center_a = bbox_center(bbox_a)
    center_b = bbox_center(bbox_b)
    center_y_delta = abs(center_a[1] - center_b[1])
    horizontal_gap = _horizontal_gap(bbox_a, bbox_b)
    combined_text = _join_texts([block_a["text"], block_b["text"]])
    union_height = bbox_height(union_bbox)
    union_aspect_ratio = bbox_width(union_bbox) / union_height if union_height > 0 else 0

    return (
        _is_short_text(block_a["text"])
        and _is_short_text(block_b["text"])
        and _is_button_phrase(combined_text)
        and height_similarity_ratio(bbox_a, bbox_b) >= 0.65
        and vertical_gap(bbox_a, bbox_b) <= max_height * 0.35
        and center_y_delta <= max_height * 0.45
        and horizontal_gap <= max_height * 0.75
        and union_aspect_ratio >= 2.0
    )


def _should_extend_paragraph_with_short_cta(block_a: dict[str, Any], block_b: dict[str, Any]) -> bool:
    bbox_a = block_a["bbox"]
    bbox_b = block_b["bbox"]
    max_height = max(bbox_height(bbox_a), bbox_height(bbox_b))
    return (
        _is_short_text(block_b["text"])
        and vertical_gap(bbox_a, bbox_b) <= max_height * 1.2
        and horizontal_overlap_ratio(bbox_a, bbox_b) >= 0.4
        and height_similarity_ratio(bbox_a, bbox_b) >= 0.6
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


def _group_to_layout_block(group: list[dict[str, Any]], block_type: BlockType | None = None) -> LayoutBlock:
    union_bbox = bbox_union([block["bbox"] for block in group])
    source_ids = [block["id"] for block in group]
    text = _join_texts([block["text"] for block in group])
    return LayoutBlock(
        id="layout_" + "_".join(source_ids),
        text=text,
        polygon=_bbox_to_polygon(union_bbox),
        bbox=union_bbox,
        source_block_ids=source_ids,
        block_type=block_type or ("paragraph" if len(group) > 1 else "normal"),
        confidence=_average_confidence(group),
    )


def _average_confidence(group: list[dict[str, Any]]) -> float | None:
    values = [block.get("confidence") for block in group if block.get("confidence") is not None]
    if not values:
        return None
    return sum(float(value) for value in values) / len(values)


def _is_isolated_single_letter_noise(
    block: dict[str, Any],
    blocks: list[dict[str, Any]],
) -> bool:
    text = str(block.get("text") or "").strip()
    if block.get("block_type") != "normal" or text not in {"E", "I", "l"}:
        return False

    has_nearby_text = any(
        other is not block
        and other.get("block_type") == "normal"
        and _is_text_neighbor(block, other)
        for other in blocks
    )
    if has_nearby_text:
        return False

    confidence = block.get("confidence")
    if confidence is not None and float(confidence) <= 0.65:
        return True

    return _is_oversized_single_character_bbox(block)


def _is_text_neighbor(block_a: dict[str, Any], block_b: dict[str, Any]) -> bool:
    bbox_a = block_a["bbox"]
    bbox_b = block_b["bbox"]
    max_height = max(bbox_height(bbox_a), bbox_height(bbox_b))
    return (
        vertical_gap(bbox_a, bbox_b) <= max_height * 1.2
        and horizontal_overlap_ratio(bbox_a, bbox_b) >= 0.25
    )


def _is_oversized_single_character_bbox(block: dict[str, Any]) -> bool:
    bbox = block["bbox"]
    width = bbox_width(bbox)
    height = bbox_height(bbox)
    return width >= 24 or height >= 36


def _render_geometry(block: dict[str, Any]) -> list[tuple[int, int]] | None:
    polygon = block.get("polygon")
    bbox = block.get("bbox")
    if not polygon and isinstance(bbox, dict):
        polygon = bbox.get("points")
    if polygon:
        points = []
        for point in polygon:
            if not isinstance(point, list | tuple) or len(point) < 2:
                return None
            points.append((round(float(point[0])), round(float(point[1]))))
        if len(points) >= 3:
            return points

    if isinstance(bbox, dict) and {"x", "y", "width", "height"}.issubset(bbox):
        x1 = round(float(bbox["x"]))
        y1 = round(float(bbox["y"]))
        x2 = x1 + round(float(bbox["width"]))
        y2 = y1 + round(float(bbox["height"]))
        return [(x1, y1), (x2, y2)]
    if isinstance(bbox, tuple | list) and len(bbox) >= 4:
        return [
            (round(float(bbox[0])), round(float(bbox[1]))),
            (round(float(bbox[2])), round(float(bbox[3]))),
        ]
    return None


def _overlay_color(block: dict[str, Any]) -> tuple[int, int, int]:
    if block.get("block_type") == "ignored":
        return (220, 20, 60)
    return (20, 140, 40)


def _overlay_label(index: int, block: dict[str, Any]) -> str:
    block_type = str(block.get("block_type") or "normal")
    text = str(block.get("text") or "").replace("\n", " ").strip()
    if len(text) > 24:
        text = f"{text[:24]}..."
    return f"#{index} {block_type}: {text}"


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


def _is_button_phrase(text: str) -> bool:
    return text.strip().lower() in {
        "abuse report",
        "submit",
        "cancel",
        "report",
        "login",
        "log in",
        "sign up",
        "continue",
    }


def _is_short_text(text: str) -> bool:
    words = text.strip().split()
    return bool(text.strip()) and (len(text.strip()) <= 18 or len(words) <= 3)


def _join_texts(texts: list[str]) -> str:
    return " ".join(text.strip() for text in texts if text.strip())


def _horizontal_gap(bbox_a: BBox, bbox_b: BBox) -> float:
    left = min(bbox_a, bbox_b, key=lambda bbox: bbox[0])
    right = max(bbox_a, bbox_b, key=lambda bbox: bbox[0])
    if float(right[0]) <= float(left[2]):
        return 0.0
    return float(right[0]) - float(left[2])

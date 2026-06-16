from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


CANDIDATE_MODES = {"game_ui", "manga", "document", "complex_background", "generic"}
UI_SKIP_REASONS = {
    "ui_resource_number",
    "ui_player_name",
    "ui_nav_label",
    "ui_icon_label",
    "ui_status_number",
    "ui_short_label",
    "ui_button_label",
}


def decide_image_mode(
    layout_blocks: list[dict[str, Any]],
    render_fit_records: list[dict[str, Any]],
    text_groups: list[Any] | None = None,
    translation_result: dict[str, Any] | None = None,
    regions: list[Any] | None = None,
) -> dict[str, Any]:
    signals = _collect_signals(
        layout_blocks=layout_blocks,
        render_fit_records=render_fit_records,
        text_groups=text_groups or [],
        translation_result=translation_result or {},
        regions=regions or [],
    )
    mode, confidence, reasons = _classify_from_signals(signals)
    return {
        "mode": mode,
        "confidence": confidence,
        "candidate_modes": sorted(CANDIDATE_MODES),
        "signals": signals,
        "reasons": reasons,
        "debug_only": True,
    }


def export_mode_debug_json(
    mode_decision: dict[str, Any],
    output_path: str | Path,
    job_id: str | None = None,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "job_id": job_id,
        **mode_decision,
        "debug_only": True,
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def _collect_signals(
    layout_blocks: list[dict[str, Any]],
    render_fit_records: list[dict[str, Any]],
    text_groups: list[Any],
    translation_result: dict[str, Any],
    regions: list[Any],
) -> dict[str, Any]:
    record_count = len(render_fit_records)
    skipped_records = [record for record in render_fit_records if record.get("can_render_inline") is False]
    inline_records = [record for record in render_fit_records if record.get("can_render_inline") is not False]
    skipped_reasons = Counter(
        str(record.get("skipped_reason") or record.get("fallback_reason") or "")
        for record in skipped_records
    )
    ui_role_counts = Counter(
        str(record.get("block_role") or "")
        for record in render_fit_records
        if str(record.get("block_role") or "") in UI_SKIP_REASONS
    )
    ui_guard_skipped_count = sum(skipped_reasons.get(reason, 0) for reason in UI_SKIP_REASONS)
    group_count = _group_count(layout_blocks, text_groups)
    vertical_group_count = _vertical_group_count(layout_blocks, text_groups)
    paragraph_block_count = sum(1 for block in layout_blocks if str(block.get("block_type") or "") == "paragraph")
    text_group_block_count = sum(1 for block in layout_blocks if block.get("is_text_group"))
    small_text_count = sum(1 for record in render_fit_records if _is_small_text_record(record))
    short_text_count = sum(1 for record in render_fit_records if len(str(record.get("original_text") or "").strip()) <= 4)
    linked_record_count = sum(1 for record in render_fit_records if int(record.get("linked_region_count") or 0) > 0)
    translation_items = (translation_result.get("items") or [])
    region_types = Counter(str(_value(region, "region_type") or "unknown") for region in regions)
    return {
        "record_count": record_count,
        "translation_item_count": len(translation_items),
        "inline_render_count": len(inline_records),
        "skipped_count": len(skipped_records),
        "skipped_ratio": _ratio(len(skipped_records), record_count),
        "ui_guard_skipped_count": ui_guard_skipped_count,
        "ui_guard_skipped_ratio": _ratio(ui_guard_skipped_count, record_count),
        "ui_role_counts": dict(ui_role_counts),
        "skipped_reason_counts": dict(skipped_reasons),
        "group_count": group_count,
        "vertical_group_count": vertical_group_count,
        "paragraph_block_count": paragraph_block_count,
        "text_group_block_count": text_group_block_count,
        "manga_region_count": sum(region_types.get(kind, 0) for kind in ("bubble", "caption_box", "text_box")),
        "small_text_count": small_text_count,
        "small_text_ratio": _ratio(small_text_count, record_count),
        "short_text_count": short_text_count,
        "short_text_ratio": _ratio(short_text_count, record_count),
        "linked_record_count": linked_record_count,
        "region_link_ratio": _ratio(linked_record_count, record_count),
        "overflow_count": sum(1 for record in render_fit_records if record.get("possible_overflow")),
    }


def _classify_from_signals(signals: dict[str, Any]) -> tuple[str, float, list[str]]:
    record_count = int(signals["record_count"])
    if record_count >= 10 and signals["translation_item_count"] == 0 and signals["inline_render_count"] == 0:
        if signals["ui_guard_skipped_ratio"] >= 0.6 and len(signals["ui_role_counts"]) >= 3:
            return (
                "game_ui",
                0.92,
                ["high_ui_guard_skipped_ratio", "multiple_ui_roles", "no_translation_items", "no_inline_render"],
            )

    if signals["paragraph_block_count"] >= 3 and signals["vertical_group_count"] == 0 and signals["group_count"] <= 1:
        return ("document", 0.78, ["paragraph_blocks_present", "few_manga_groups"])

    if (
        record_count >= 40
        and signals["skipped_ratio"] >= 0.6
        and signals["region_link_ratio"] <= 0.25
        and (signals["small_text_ratio"] >= 0.55 or signals["short_text_ratio"] >= 0.5)
    ):
        reasons = ["high_record_count", "high_skipped_ratio", "low_region_link_ratio"]
        if signals["small_text_ratio"] >= 0.55:
            reasons.append("high_small_text_ratio")
        if signals["short_text_ratio"] >= 0.5:
            reasons.append("high_short_text_ratio")
        return (
            "complex_background",
            0.84,
            reasons,
        )

    if signals["group_count"] > 0 and (signals["vertical_group_count"] > 0 or signals["manga_region_count"] > 0):
        reasons = ["manga_groups_present"]
        if signals["vertical_group_count"] > 0:
            reasons.append("vertical_groups_present")
        if signals["manga_region_count"] > 0:
            reasons.append("manga_regions_present")
        return ("manga", 0.86 if signals["vertical_group_count"] else 0.76, reasons)

    return ("generic", 0.35, ["insufficient_mode_signals"])


def _group_count(layout_blocks: list[dict[str, Any]], text_groups: list[Any]) -> int:
    if text_groups:
        return len(text_groups)
    return sum(1 for block in layout_blocks if block.get("is_text_group"))


def _vertical_group_count(layout_blocks: list[dict[str, Any]], text_groups: list[Any]) -> int:
    if text_groups:
        return sum(1 for group in text_groups if _value(group, "text_direction") == "vertical")
    return sum(1 for block in layout_blocks if block.get("is_text_group") and block.get("text_direction") == "vertical")


def _is_small_text_record(record: dict[str, Any]) -> bool:
    width = float(record.get("bbox_width") or 0)
    height = float(record.get("bbox_height") or 0)
    area = float(record.get("bbox_area") or (width * height))
    return width <= 48 or height <= 18 or area <= 1600


def _ratio(value: int | float, total: int | float) -> float:
    if not total:
        return 0.0
    return round(float(value) / float(total), 6)


def _value(item: Any, key: str) -> Any:
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)

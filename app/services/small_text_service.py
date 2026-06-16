from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


CLASSIFICATIONS = {"translate_only", "inline_render", "ignored_noise", "unknown"}


def classify_complex_small_text_blocks(
    sample_mode: str | None,
    layout_blocks: list[dict[str, Any]],
    render_fit_records: list[dict[str, Any]],
) -> dict[str, Any]:
    summary = _empty_summary()
    if sample_mode != "complex_background":
        return {
            "sample_mode": sample_mode,
            "debug_only": True,
            "classification_summary": summary,
            "records": [],
            "reasons": ["non_complex_background_mode"],
        }

    blocks_by_id = {
        str(block.get("id")): block
        for block in layout_blocks
        if block.get("id") is not None
    }
    records = [
        _classification_record(record, blocks_by_id.get(str(record.get("block_id"))))
        for record in render_fit_records
    ]
    counts = Counter(record["classification"] for record in records)
    for name in CLASSIFICATIONS:
        summary[f"{name}_count"] = counts.get(name, 0)
    return {
        "sample_mode": sample_mode,
        "debug_only": True,
        "classification_summary": summary,
        "records": records,
        "reasons": ["complex_background_mode"],
    }


def export_small_text_debug_json(
    payload: dict[str, Any],
    output_path: str | Path,
    job_id: str | None = None,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output = {
        "job_id": job_id,
        **payload,
        "debug_only": True,
    }
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def _classification_record(record: dict[str, Any], block: dict[str, Any] | None) -> dict[str, Any]:
    text = str(record.get("original_text") or (block or {}).get("text") or "")
    confidence = _first_number(record.get("confidence"), (block or {}).get("confidence"))
    classification, reasons = _classify_record(record=record, text=text, confidence=confidence)
    return {
        "block_id": str(record.get("block_id") or ""),
        "text": text,
        "bbox": list(record.get("bbox") or _block_bbox(block) or [0, 0, 0, 0]),
        "confidence": confidence,
        "skipped_reason": record.get("skipped_reason") or record.get("fallback_reason"),
        "translated_text": record.get("translated_text"),
        "can_render_inline": bool(record.get("can_render_inline")),
        "classification": classification,
        "reasons": reasons,
        "debug_only": True,
    }


def _classify_record(record: dict[str, Any], text: str, confidence: float | None) -> tuple[str, list[str]]:
    clean_text = text.strip()
    if _is_ignored_noise(record=record, text=clean_text, confidence=confidence):
        reasons = []
        if _text_len(clean_text) <= 1 and _is_low_confidence(confidence):
            reasons.append("low_confidence_single_character")
        if _text_len(clean_text) <= 1 and _is_large_bbox(record):
            reasons.append("large_bbox_single_character")
        if _text_len(clean_text) <= 2 and _is_tiny_bbox(record):
            reasons.append("tiny_bbox_short_text")
        return "ignored_noise", reasons or ["noise_like_text"]

    if record.get("can_render_inline") is True and record.get("translated_text"):
        return "inline_render", ["has_translated_text", "currently_renderable"]

    if record.get("can_render_inline") is False and _looks_text_like_fragment(clean_text, confidence):
        return "translate_only", ["complex_background_mode", "skipped_but_text_like", "possible_line_fragment"]

    return "unknown", ["insufficient_evidence"]


def _is_ignored_noise(record: dict[str, Any], text: str, confidence: float | None) -> bool:
    if not text:
        return True
    text_len = _text_len(text)
    if text_len <= 1 and _is_low_confidence(confidence):
        return True
    if text_len <= 1 and _is_large_bbox(record) and _is_low_confidence(confidence):
        return True
    if text_len <= 2 and _is_tiny_bbox(record) and not _has_alpha_sequence(text):
        return True
    return False


def _looks_text_like_fragment(text: str, confidence: float | None) -> bool:
    if not text or confidence is None or _is_low_confidence(confidence, threshold=0.18):
        return False
    if _has_alpha_sequence(text):
        return True
    return bool(re.search(r"[A-Za-z]{2,}[,.;:!?]?$", text))


def _has_alpha_sequence(text: str) -> bool:
    return bool(re.search(r"[A-Za-z]{2,}", text))


def _is_low_confidence(confidence: float | None, threshold: float = 0.3) -> bool:
    return confidence is not None and confidence < threshold


def _is_large_bbox(record: dict[str, Any]) -> bool:
    return float(record.get("bbox_area_ratio") or 0.0) >= 0.08


def _is_tiny_bbox(record: dict[str, Any]) -> bool:
    width = float(record.get("bbox_width") or 0)
    height = float(record.get("bbox_height") or 0)
    area = float(record.get("bbox_area") or width * height)
    return width <= 10 or height <= 10 or area <= 120


def _text_len(text: str) -> int:
    return len(text.strip())


def _empty_summary() -> dict[str, int]:
    return {
        "translate_only_count": 0,
        "inline_render_count": 0,
        "ignored_noise_count": 0,
        "unknown_count": 0,
    }


def _first_number(*values: Any) -> float | None:
    for value in values:
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _block_bbox(block: dict[str, Any] | None) -> list[float] | None:
    if not block:
        return None
    bbox = block.get("bbox")
    if isinstance(bbox, dict):
        x = float(bbox.get("x") or 0)
        y = float(bbox.get("y") or 0)
        width = float(bbox.get("width") or 0)
        height = float(bbox.get("height") or 0)
        return [x, y, x + width, y + height]
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
        return [float(value) for value in bbox[:4]]
    return None

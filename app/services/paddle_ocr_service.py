import json
from functools import lru_cache
from pathlib import Path
from typing import Any


class PaddleOCRError(RuntimeError):
    pass


@lru_cache(maxsize=4)
def _get_paddle_ocr(language: str) -> Any:
    try:
        from paddleocr import PaddleOCR
    except Exception as exc:  # pragma: no cover - exercised through caller fallback
        raise PaddleOCRError("PaddleOCR is not installed or cannot be imported.") from exc

    try:
        return PaddleOCR(
            lang=language,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
    except Exception as exc:  # pragma: no cover - depends on local OCR runtime
        raise PaddleOCRError("PaddleOCR initialization failed.") from exc


def run_paddle_ocr(
    image_path: str | Path,
    job_id: str,
    language: str,
    min_confidence: float,
) -> dict[str, Any]:
    ocr = _get_paddle_ocr(language)
    path = str(image_path)

    try:
        try:
            raw_result = ocr.predict(input=path)
        except TypeError:
            raw_result = ocr.predict(path)
    except Exception as exc:  # pragma: no cover - depends on local OCR runtime
        raise PaddleOCRError("PaddleOCR inference failed.") from exc

    return adapt_paddle_ocr_result(
        job_id=job_id,
        raw_result=raw_result,
        min_confidence=min_confidence,
        language=language,
    )


def adapt_paddle_ocr_result(
    job_id: str,
    raw_result: Any,
    min_confidence: float,
    language: str,
) -> dict[str, Any]:
    pages = _normalize_pages(raw_result)
    blocks: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for page in pages:
        texts = _as_list(page.get("rec_texts"))
        scores = _as_list(page.get("rec_scores"))
        polys = _as_list(page.get("rec_polys"))
        boxes = _as_list(page.get("rec_boxes"))

        for index, text in enumerate(texts):
            if text is None or str(text).strip() == "":
                continue

            confidence = _to_float(_get_index(scores, index), default=0.0)
            points = _points_from_raw(_get_index(polys, index))
            bbox = _bbox_from_points(points)
            if bbox is None:
                bbox = _bbox_from_box(_get_index(boxes, index))
            if bbox is None:
                bbox = {"x": 0, "y": 0, "width": 0, "height": 0, "points": None}

            block_id = f"block-{len(blocks) + 1}"
            if confidence < min_confidence:
                warnings.append(
                    {
                        "code": "OCR_LOW_CONFIDENCE",
                        "message": "OCR 置信度较低，请人工复核。",
                        "stage": "ocr",
                        "level": "warning",
                        "detail": f"confidence={confidence:.3f}, threshold={min_confidence:.3f}",
                        "block_id": block_id,
                    }
                )

            blocks.append(
                {
                    "id": block_id,
                    "text": str(text),
                    "bbox": bbox,
                    "confidence": confidence,
                    "line_index": len(blocks),
                    "language": language,
                    "source_items": [
                        {
                            "text": str(text),
                            "confidence": confidence,
                            "points": bbox["points"],
                        }
                    ],
                }
            )

    if not blocks:
        warnings.append(
            {
                "code": "OCR_NO_TEXT_FOUND",
                "message": "PaddleOCR 未识别到文字。",
                "stage": "ocr",
                "level": "warning",
                "detail": None,
                "block_id": None,
            }
        )

    return {
        "job_id": job_id,
        "image_width": None,
        "image_height": None,
        "blocks": blocks,
        "raw": {
            "mode": "paddleocr",
            "raw_page_count": len(pages),
            "raw_block_count": len(blocks),
            "language": language,
        },
        "warnings": warnings,
    }


def _normalize_pages(raw_result: Any) -> list[dict[str, Any]]:
    value = _to_jsonable(raw_result)
    if value is None:
        return []
    if isinstance(value, dict):
        return [_unwrap_result_page(value)]
    if isinstance(value, list):
        return [_unwrap_result_page(item) for item in value if isinstance(item, dict)]
    raise PaddleOCRError("Unexpected PaddleOCR result structure.")


def _unwrap_result_page(page: dict[str, Any]) -> dict[str, Any]:
    wrapped = page.get("res")
    if isinstance(wrapped, dict):
        return wrapped
    return page


def _to_jsonable(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return _to_jsonable(value.tolist())
    if hasattr(value, "json"):
        json_value = value.json
        if callable(json_value):
            json_value = json_value()
        if isinstance(json_value, str):
            return json.loads(json_value)
        return _to_jsonable(json_value)
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _get_index(values: list[Any], index: int) -> Any:
    if index >= len(values):
        return None
    return values[index]


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _points_from_raw(raw_points: Any) -> list[list[int]] | None:
    points = _to_jsonable(raw_points)
    if not isinstance(points, list) or len(points) < 4:
        return None

    normalized: list[list[int]] = []
    for point in points[:4]:
        if not isinstance(point, list) or len(point) < 2:
            return None
        normalized.append([round(float(point[0])), round(float(point[1]))])
    return normalized


def _bbox_from_points(points: list[list[int]] | None) -> dict[str, Any] | None:
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    x = min(xs)
    y = min(ys)
    return {
        "x": x,
        "y": y,
        "width": max(xs) - x,
        "height": max(ys) - y,
        "points": points,
    }


def _bbox_from_box(raw_box: Any) -> dict[str, Any] | None:
    box = _to_jsonable(raw_box)
    if not isinstance(box, list) or len(box) < 4:
        return None
    x1, y1, x2, y2 = [round(float(value)) for value in box[:4]]
    points = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
    return {
        "x": x1,
        "y": y1,
        "width": max(0, x2 - x1),
        "height": max(0, y2 - y1),
        "points": points,
    }

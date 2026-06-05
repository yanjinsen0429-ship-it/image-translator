import logging
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.paddle_ocr_service import run_paddle_ocr


logger = logging.getLogger(__name__)


def create_mock_ocr_result(job_id: str) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "image_width": None,
        "image_height": None,
        "blocks": [
            {
                "id": "block-1",
                "text": "This is mock OCR text from the uploaded image.",
                "bbox": {
                    "x": 24,
                    "y": 24,
                    "width": 360,
                    "height": 80,
                    "points": None,
                },
                "confidence": 1.0,
                "line_index": 0,
                "language": "en",
                "source_items": [],
            }
        ],
        "raw": {"mode": "mock"},
        "warnings": [
            {
                "code": "MOCK_OCR",
                "message": "当前使用 mock OCR，未进行真实文字识别。",
                "stage": "ocr",
                "level": "warning",
                "detail": None,
                "block_id": None,
            }
        ],
    }


def create_ocr_result(image_path: str | Path, job_id: str) -> dict[str, Any]:
    if settings.ocr_engine == "mock":
        return create_mock_ocr_result(job_id=job_id)

    if settings.ocr_engine != "paddle":
        return _fallback_to_mock(
            job_id=job_id,
            reason=f"Unsupported OCR engine: {settings.ocr_engine}",
            exc=None,
        )

    try:
        return run_paddle_ocr(
            image_path=image_path,
            job_id=job_id,
            language=settings.ocr_language,
            min_confidence=settings.ocr_min_confidence,
        )
    except Exception as exc:
        if not settings.ocr_fallback_to_mock:
            raise
        return _fallback_to_mock(
            job_id=job_id,
            reason=f"{type(exc).__name__}: {exc}",
            exc=exc,
        )


def _fallback_to_mock(
    job_id: str,
    reason: str,
    exc: Exception | None,
) -> dict[str, Any]:
    if exc is None:
        logger.warning("Falling back to mock OCR: %s", reason)
    else:
        logger.exception("Falling back to mock OCR: %s", reason)

    result = create_mock_ocr_result(job_id=job_id)
    result["raw"] = {
        **(result.get("raw") or {}),
        "mode": "mock",
        "fallback": True,
        "fallback_reason": reason,
    }
    result.setdefault("warnings", []).append(
        {
            "code": "OCR_FALLBACK_TO_MOCK",
            "message": "真实 OCR 不可用，已回退到 mock OCR。",
            "stage": "ocr",
            "level": "warning",
            "detail": reason,
            "block_id": None,
        }
    )
    return result

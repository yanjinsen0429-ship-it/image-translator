from typing import Any


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

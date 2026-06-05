from typing import Any


def create_mock_translation_result(
    job_id: str,
    ocr_result: dict[str, Any],
) -> dict[str, Any]:
    items = []
    for block in ocr_result.get("blocks", []):
        items.append(
            {
                "block_id": block["id"],
                "source_text": block["text"],
                "translated_text": "这是模拟翻译文本，用于验证上传到展示的最小闭环。",
                "status": "success",
                "error": None,
            }
        )

    return {
        "job_id": job_id,
        "items": items,
        "provider": "mock",
        "source_language": "en",
        "target_language": "zh-CN",
        "warnings": [
            {
                "code": "MOCK_TRANSLATION",
                "message": "当前使用 mock 翻译，未调用真实翻译 API。",
                "stage": "translate",
                "level": "warning",
                "detail": None,
                "block_id": None,
            }
        ],
        "errors": [],
    }

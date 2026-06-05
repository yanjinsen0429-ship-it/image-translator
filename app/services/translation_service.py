from typing import Any, Protocol

from app.core.config import settings


class TranslationProvider(Protocol):
    provider_name: str
    target_language: str

    def translate_text(
        self,
        text: str,
        block_id: str,
        source_language: str | None = None,
        bbox: dict[str, Any] | None = None,
        confidence: float | None = None,
    ) -> dict[str, Any]:
        pass

    def translate_blocks(self, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        pass


class MockTranslationProvider:
    provider_name = "mock"

    def __init__(self, target_language: str):
        self.target_language = target_language

    def translate_text(
        self,
        text: str,
        block_id: str,
        source_language: str | None = None,
        bbox: dict[str, Any] | None = None,
        confidence: float | None = None,
    ) -> dict[str, Any]:
        return {
            "block_id": block_id,
            "source_text": text,
            "translated_text": f"[mock {self.target_language}] 模拟翻译：{text}",
            "source_language": source_language,
            "target_language": self.target_language,
            "provider": self.provider_name,
            "bbox": bbox,
            "confidence": confidence,
            "status": "success",
            "error": None,
        }

    def translate_blocks(self, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items = []
        for block in blocks:
            items.append(
                self.translate_text(
                    text=block.get("text", ""),
                    block_id=block.get("id", ""),
                    source_language=block.get("language"),
                    bbox=block.get("bbox"),
                    confidence=block.get("confidence"),
                )
            )
        return items


def get_translation_provider(provider_name: str | None = None) -> TranslationProvider:
    name = provider_name or settings.translation_provider
    if name == "mock":
        return MockTranslationProvider(
            target_language=settings.translation_target_language,
        )

    return MockTranslationProvider(
        target_language=settings.translation_target_language,
    )


def create_translation_result(
    job_id: str,
    ocr_result: dict[str, Any],
) -> dict[str, Any]:
    provider = get_translation_provider()
    blocks = ocr_result.get("blocks", [])
    items = provider.translate_blocks(blocks)

    return {
        "job_id": job_id,
        "items": items,
        "provider": provider.provider_name,
        "source_language": _infer_source_language(blocks),
        "target_language": provider.target_language,
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


def create_mock_translation_result(
    job_id: str,
    ocr_result: dict[str, Any],
) -> dict[str, Any]:
    return create_translation_result(job_id=job_id, ocr_result=ocr_result)


def _infer_source_language(blocks: list[dict[str, Any]]) -> str | None:
    languages = [
        block.get("language")
        for block in blocks
        if block.get("language") is not None
    ]
    if not languages:
        return None
    first_language = languages[0]
    if all(language == first_language for language in languages):
        return first_language
    return "mixed"

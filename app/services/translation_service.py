import json
import logging
import urllib.error
import urllib.request
from typing import Any, Protocol

from app.core.config import settings

logger = logging.getLogger(__name__)

DEEPSEEK_SYSTEM_PROMPT = (
    "You are a translation engine. Translate the user's text into the target "
    "language. Output only the translated text. Preserve line breaks and basic "
    "punctuation. Do not explain. If the text is already in the target language, "
    "return it unchanged."
)


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
        return _build_translation_item(
            block_id=block_id,
            source_text=text,
            translated_text=f"[mock {self.target_language}] 模拟翻译：{text}",
            source_language=source_language,
            target_language=self.target_language,
            provider=self.provider_name,
            bbox=bbox,
            confidence=confidence,
            status="success",
            error=None,
        )

    def translate_blocks(self, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            self.translate_text(
                text=block.get("text", ""),
                block_id=block.get("id", ""),
                source_language=block.get("language"),
                bbox=block.get("bbox"),
                confidence=block.get("confidence"),
            )
            for block in blocks
        ]


class DeepSeekTranslationProvider:
    provider_name = "deepseek"

    def __init__(
        self,
        target_language: str,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: int,
    ):
        self.target_language = target_language
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def translate_text(
        self,
        text: str,
        block_id: str,
        source_language: str | None = None,
        bbox: dict[str, Any] | None = None,
        confidence: float | None = None,
    ) -> dict[str, Any]:
        if not text.strip():
            return _build_translation_item(
                block_id=block_id,
                source_text=text,
                translated_text="",
                source_language=source_language,
                target_language=self.target_language,
                provider=self.provider_name,
                bbox=bbox,
                confidence=confidence,
                status="skipped",
                error=None,
            )

        try:
            translated_text = self._request_translation(text)
        except Exception as exc:
            logger.exception("DeepSeek translation failed for block %s", block_id)
            return _build_translation_item(
                block_id=block_id,
                source_text=text,
                translated_text="",
                source_language=source_language,
                target_language=self.target_language,
                provider=self.provider_name,
                bbox=bbox,
                confidence=confidence,
                status="failed",
                error=str(exc),
            )

        return _build_translation_item(
            block_id=block_id,
            source_text=text,
            translated_text=translated_text,
            source_language=source_language,
            target_language=self.target_language,
            provider=self.provider_name,
            bbox=bbox,
            confidence=confidence,
            status="success",
            error=None,
        )

    def translate_blocks(self, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            self.translate_text(
                text=block.get("text", ""),
                block_id=block.get("id", ""),
                source_language=block.get("language"),
                bbox=block.get("bbox"),
                confidence=block.get("confidence"),
            )
            for block in blocks
        ]

    def _request_translation(self, text: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": DEEPSEEK_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Target language: {self.target_language}\n\n"
                        f"Text:\n{text}"
                    ),
                },
            ],
            "temperature": 0,
            "thinking": {"type": "disabled"},
            "stream": False,
        }
        request = urllib.request.Request(
            url=f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
            ) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"DeepSeek API returned HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"DeepSeek API request failed: {exc.reason}") from exc

        return self._parse_translation_response(body)

    def _parse_translation_response(self, body: str) -> str:
        data = json.loads(body)
        content = data["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("DeepSeek API returned non-text content")
        return content.strip()


def get_translation_provider(provider_name: str | None = None) -> TranslationProvider:
    name = (provider_name or settings.translation_provider).strip().lower()
    if name == "deepseek" and settings.deepseek_api_key.strip():
        return DeepSeekTranslationProvider(
            target_language=settings.translation_target_language,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            timeout_seconds=settings.deepseek_timeout_seconds,
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
        "warnings": _build_translation_warnings(provider.provider_name),
        "errors": _build_translation_errors(items),
    }


def create_mock_translation_result(
    job_id: str,
    ocr_result: dict[str, Any],
) -> dict[str, Any]:
    return create_translation_result(job_id=job_id, ocr_result=ocr_result)


def _build_translation_item(
    block_id: str,
    source_text: str,
    translated_text: str,
    source_language: str | None,
    target_language: str,
    provider: str,
    bbox: dict[str, Any] | None,
    confidence: float | None,
    status: str,
    error: str | None,
) -> dict[str, Any]:
    return {
        "block_id": block_id,
        "source_text": source_text,
        "translated_text": translated_text,
        "source_language": source_language,
        "target_language": target_language,
        "provider": provider,
        "bbox": bbox,
        "confidence": confidence,
        "status": status,
        "error": error,
    }


def _build_translation_warnings(actual_provider_name: str) -> list[dict[str, Any]]:
    requested_provider = settings.translation_provider.strip().lower()
    warnings = []

    if requested_provider == "deepseek" and actual_provider_name == "mock":
        warnings.append(
            {
                "code": "TRANSLATION_FALLBACK_TO_MOCK",
                "message": "DeepSeek API key is not configured; using mock translation.",
                "stage": "translate",
                "level": "warning",
                "detail": None,
                "block_id": None,
            }
        )

    if actual_provider_name == "mock":
        warnings.append(
            {
                "code": "MOCK_TRANSLATION",
                "message": "Current translation uses mock provider; no real translation API was called.",
                "stage": "translate",
                "level": "warning",
                "detail": None,
                "block_id": None,
            }
        )

    return warnings


def _build_translation_errors(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "code": "TRANSLATION_BLOCK_FAILED",
            "message": "Translation failed for one OCR block.",
            "stage": "translate",
            "level": "error",
            "detail": item.get("error"),
            "block_id": item.get("block_id"),
        }
        for item in items
        if item.get("status") == "failed"
    ]


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

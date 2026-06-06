import os
import unittest
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.translation_service import (
    DeepSeekTranslationProvider,
    MockTranslationProvider,
    create_translation_result,
    get_translation_provider,
)


def make_ocr_result() -> dict:
    return {
        "job_id": "job-translation",
        "blocks": [
            {
                "id": "block-1",
                "text": "你好世界",
                "bbox": {
                    "x": 10,
                    "y": 20,
                    "width": 100,
                    "height": 30,
                    "points": [[10, 20], [110, 20], [110, 50], [10, 50]],
                },
                "confidence": 0.96,
                "line_index": 0,
                "language": "ch",
                "source_items": [],
            },
            {
                "id": "block-2",
                "text": "Hello World",
                "bbox": {
                    "x": 10,
                    "y": 60,
                    "width": 150,
                    "height": 30,
                    "points": [[10, 60], [160, 60], [160, 90], [10, 90]],
                },
                "confidence": 0.98,
                "line_index": 1,
                "language": "en",
                "source_items": [],
            },
            {
                "id": "block-3",
                "text": "こんにちは",
                "bbox": {
                    "x": 10,
                    "y": 100,
                    "width": 120,
                    "height": 30,
                    "points": [[10, 100], [130, 100], [130, 130], [10, 130]],
                },
                "confidence": 0.9,
                "line_index": 2,
                "language": "japan",
                "source_items": [],
            },
        ],
    }


class MockTranslationProviderTests(unittest.TestCase):
    def test_single_text_translation_returns_structured_result(self):
        provider = MockTranslationProvider(target_language="zh-CN")

        result = provider.translate_text(
            text="Hello World",
            block_id="block-1",
            source_language="en",
        )

        self.assertEqual(result["block_id"], "block-1")
        self.assertEqual(result["source_text"], "Hello World")
        self.assertNotEqual(result["translated_text"], "")
        self.assertEqual(result["source_language"], "en")
        self.assertEqual(result["target_language"], "zh-CN")
        self.assertEqual(result["provider"], "mock")
        self.assertIsNone(result["confidence"])
        self.assertIsNone(result["error"])

    def test_batch_translation_preserves_input_order(self):
        provider = MockTranslationProvider(target_language="zh-CN")
        blocks = make_ocr_result()["blocks"]

        results = provider.translate_blocks(blocks)

        self.assertEqual(
            [item["block_id"] for item in results],
            ["block-1", "block-2", "block-3"],
        )
        self.assertEqual(
            [item["source_text"] for item in results],
            ["你好世界", "Hello World", "こんにちは"],
        )
        self.assertEqual(results[0]["bbox"]["x"], 10)
        self.assertEqual(results[0]["confidence"], 0.96)

    def test_ignored_block_is_skipped_without_calling_mock_translate_text(self):
        provider = MockTranslationProvider(target_language="zh-CN")
        blocks = [
            {
                "id": "noise-1",
                "text": "]",
                "block_type": "ignored",
                "bbox": {"x": 10, "y": 20, "width": 8, "height": 12, "points": None},
                "confidence": 0.5,
                "language": "en",
            }
        ]

        with patch.object(provider, "translate_text", wraps=provider.translate_text) as translate_text:
            results = provider.translate_blocks(blocks)

        translate_text.assert_not_called()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["block_id"], "noise-1")
        self.assertEqual(results[0]["source_text"], "]")
        self.assertEqual(results[0]["status"], "skipped")
        self.assertNotIn("模拟翻译", results[0]["translated_text"])

    def test_mixed_blocks_skip_ignored_and_preserve_order(self):
        provider = MockTranslationProvider(target_language="zh-CN")
        blocks = [
            {
                "id": "normal-1",
                "text": "Hello",
                "block_type": "normal",
                "bbox": {"x": 10, "y": 20, "width": 60, "height": 20, "points": None},
                "confidence": 0.96,
                "language": "en",
            },
            {
                "id": "noise-1",
                "text": "]",
                "block_type": "ignored",
                "bbox": {"x": 80, "y": 20, "width": 8, "height": 12, "points": None},
                "confidence": 0.5,
                "language": "en",
            },
            {
                "id": "normal-2",
                "text": "World",
                "block_type": "normal",
                "bbox": {"x": 10, "y": 50, "width": 60, "height": 20, "points": None},
                "confidence": 0.95,
                "language": "en",
            },
        ]

        with patch.object(provider, "translate_text", wraps=provider.translate_text) as translate_text:
            results = provider.translate_blocks(blocks)

        self.assertEqual([item["block_id"] for item in results], ["normal-1", "noise-1", "normal-2"])
        self.assertEqual([item["status"] for item in results], ["success", "skipped", "success"])
        self.assertEqual(translate_text.call_count, 2)
        self.assertIn("Hello", results[0]["translated_text"])
        self.assertNotIn("模拟翻译", results[1]["translated_text"])
        self.assertIn("World", results[2]["translated_text"])


class TranslationServiceTests(unittest.TestCase):
    def make_mock_settings(self) -> SimpleNamespace:
        return SimpleNamespace(
            translation_provider="mock",
            translation_target_language="zh-CN",
            deepseek_api_key="",
            deepseek_base_url="https://api.deepseek.com",
            deepseek_model="deepseek-v4-flash",
            deepseek_timeout_seconds=30,
        )

    def test_create_translation_result_handles_multiple_ocr_blocks(self):
        with patch("app.services.translation_service.settings", self.make_mock_settings()):
            result = create_translation_result(
                job_id="job-translation",
                ocr_result=make_ocr_result(),
            )

        self.assertEqual(result["job_id"], "job-translation")
        self.assertEqual(result["provider"], "mock")
        self.assertEqual(result["target_language"], "zh-CN")
        self.assertEqual(len(result["items"]), 3)
        self.assertEqual(
            [item["block_id"] for item in result["items"]],
            ["block-1", "block-2", "block-3"],
        )
        self.assertEqual(
            [item["source_text"] for item in result["items"]],
            ["你好世界", "Hello World", "こんにちは"],
        )
        self.assertTrue(all(item["translated_text"] for item in result["items"]))
        self.assertTrue(all(item["provider"] == "mock" for item in result["items"]))
        self.assertEqual(result["items"][2]["bbox"]["y"], 100)
        self.assertEqual(result["items"][2]["confidence"], 0.9)

    def test_create_translation_result_does_not_require_api_key(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("app.services.translation_service.settings", self.make_mock_settings()),
        ):
            result = create_translation_result(
                job_id="job-no-key",
                ocr_result=make_ocr_result(),
            )

        self.assertEqual(result["provider"], "mock")
        self.assertEqual(len(result["items"]), 3)
        self.assertEqual(result["errors"], [])

    def test_deepseek_without_api_key_falls_back_to_mock(self):
        fake_settings = SimpleNamespace(
            translation_provider="deepseek",
            translation_target_language="zh-CN",
            deepseek_api_key="",
            deepseek_base_url="https://api.deepseek.com",
            deepseek_model="deepseek-v4-flash",
            deepseek_timeout_seconds=30,
        )

        with patch("app.services.translation_service.settings", fake_settings):
            provider = get_translation_provider()
            result = create_translation_result(
                job_id="job-deepseek-no-key",
                ocr_result=make_ocr_result(),
            )

        self.assertIsInstance(provider, MockTranslationProvider)
        self.assertEqual(result["provider"], "mock")
        self.assertEqual(len(result["items"]), 3)
        self.assertTrue(
            any(
                warning["code"] == "TRANSLATION_FALLBACK_TO_MOCK"
                for warning in result["warnings"]
            )
        )


class DeepSeekTranslationProviderTests(unittest.TestCase):
    def make_provider(self) -> DeepSeekTranslationProvider:
        return DeepSeekTranslationProvider(
            target_language="zh-CN",
            api_key="test-key",
            base_url="https://api.deepseek.com",
            model="deepseek-v4-flash",
            timeout_seconds=30,
        )

    def test_deepseek_provider_can_be_instantiated(self):
        provider = self.make_provider()

        self.assertEqual(provider.provider_name, "deepseek")
        self.assertEqual(provider.target_language, "zh-CN")

    def test_deepseek_batch_translation_preserves_input_order(self):
        provider = self.make_provider()
        blocks = make_ocr_result()["blocks"]

        with patch.object(
            provider,
            "_request_translation",
            side_effect=["你好世界", "你好，世界", "你好"],
        ):
            results = provider.translate_blocks(blocks)

        self.assertEqual(
            [item["block_id"] for item in results],
            ["block-1", "block-2", "block-3"],
        )
        self.assertEqual(
            [item["source_text"] for item in results],
            ["你好世界", "Hello World", "こんにちは"],
        )
        self.assertEqual(
            [item["translated_text"] for item in results],
            ["你好世界", "你好，世界", "你好"],
        )
        self.assertTrue(all(item["provider"] == "deepseek" for item in results))
        self.assertTrue(all(item["error"] is None for item in results))

    def test_deepseek_batch_skips_ignored_block_without_request(self):
        provider = self.make_provider()
        blocks = [
            {
                "id": "normal-1",
                "text": "Hello",
                "block_type": "normal",
                "bbox": {"x": 10, "y": 20, "width": 60, "height": 20, "points": None},
                "confidence": 0.96,
                "language": "en",
            },
            {
                "id": "noise-1",
                "text": "|",
                "block_type": "ignored",
                "bbox": {"x": 80, "y": 20, "width": 6, "height": 18, "points": None},
                "confidence": 0.5,
                "language": "en",
            },
            {
                "id": "normal-2",
                "text": "World",
                "block_type": "normal",
                "bbox": {"x": 10, "y": 50, "width": 60, "height": 20, "points": None},
                "confidence": 0.95,
                "language": "en",
            },
        ]

        with patch.object(
            provider,
            "_request_translation",
            side_effect=["你好", "世界"],
        ) as request_translation:
            results = provider.translate_blocks(blocks)

        self.assertEqual([item["block_id"] for item in results], ["normal-1", "noise-1", "normal-2"])
        self.assertEqual([item["status"] for item in results], ["success", "skipped", "success"])
        self.assertEqual([item["translated_text"] for item in results], ["你好", "|", "世界"])
        self.assertEqual(request_translation.call_count, 2)
        self.assertEqual([call.args[0] for call in request_translation.call_args_list], ["Hello", "World"])

    def test_deepseek_api_exception_returns_failed_item(self):
        provider = self.make_provider()

        with (
            patch.object(
                provider,
                "_request_translation",
                side_effect=RuntimeError("network unavailable"),
            ),
            patch("app.services.translation_service.logger.exception"),
        ):
            result = provider.translate_text(
                text="Hello World",
                block_id="block-error",
                source_language="en",
            )

        self.assertEqual(result["block_id"], "block-error")
        self.assertEqual(result["source_text"], "Hello World")
        self.assertEqual(result["translated_text"], "")
        self.assertEqual(result["provider"], "deepseek")
        self.assertEqual(result["status"], "failed")
        self.assertIn("network unavailable", result["error"])

    def test_deepseek_request_disables_thinking_for_translation(self):
        provider = self.make_provider()
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            {"choices": [{"message": {"content": "你好世界"}}]},
        ).encode("utf-8")

        with patch("urllib.request.urlopen", return_value=response) as urlopen:
            translated_text = provider._request_translation("Hello World")

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(translated_text, "你好世界")
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(payload["temperature"], 0)


if __name__ == "__main__":
    unittest.main()

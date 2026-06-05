import os
import unittest
from unittest.mock import patch

from app.services.translation_service import (
    MockTranslationProvider,
    create_translation_result,
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


class TranslationServiceTests(unittest.TestCase):
    def test_create_translation_result_handles_multiple_ocr_blocks(self):
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
        with patch.dict(os.environ, {}, clear=True):
            result = create_translation_result(
                job_id="job-no-key",
                ocr_result=make_ocr_result(),
            )

        self.assertEqual(result["provider"], "mock")
        self.assertEqual(len(result["items"]), 3)
        self.assertEqual(result["errors"], [])


if __name__ == "__main__":
    unittest.main()

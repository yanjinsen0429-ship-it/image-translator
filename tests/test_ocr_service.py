import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.api.routes import translate_image
from app.services.paddle_ocr_service import adapt_paddle_ocr_result
from app.services.ocr_service import create_ocr_result


class PaddleOCRAdapterTests(unittest.TestCase):
    def test_paddle_adapter_converts_text_bbox_and_confidence(self):
        raw_result = [
            {
                "rec_texts": ["Hello world"],
                "rec_scores": [0.98],
                "rec_polys": [
                    [[10, 20], [110, 20], [110, 50], [10, 50]],
                ],
            }
        ]

        result = adapt_paddle_ocr_result(
            job_id="job-ocr",
            raw_result=raw_result,
            min_confidence=0.5,
            language="en",
        )

        self.assertEqual(result["job_id"], "job-ocr")
        self.assertEqual(result["raw"]["mode"], "paddleocr")
        self.assertEqual(result["raw"]["raw_block_count"], 1)
        self.assertEqual(result["blocks"][0]["text"], "Hello world")
        self.assertEqual(result["blocks"][0]["confidence"], 0.98)
        self.assertEqual(
            result["blocks"][0]["bbox"],
            {
                "x": 10,
                "y": 20,
                "width": 100,
                "height": 30,
                "points": [[10, 20], [110, 20], [110, 50], [10, 50]],
            },
        )

    def test_empty_paddle_result_returns_warning_without_crashing(self):
        result = adapt_paddle_ocr_result(
            job_id="job-empty",
            raw_result=[{"rec_texts": [], "rec_scores": [], "rec_polys": []}],
            min_confidence=0.5,
            language="en",
        )

        self.assertEqual(result["blocks"], [])
        self.assertEqual(result["warnings"][0]["code"], "OCR_NO_TEXT_FOUND")

    def test_paddle_adapter_accepts_wrapped_result_payload(self):
        raw_result = [
            {
                "res": {
                    "rec_texts": ["Wrapped text"],
                    "rec_scores": [0.88],
                    "rec_boxes": [[5, 7, 45, 27]],
                }
            }
        ]

        result = adapt_paddle_ocr_result(
            job_id="job-wrapped",
            raw_result=raw_result,
            min_confidence=0.5,
            language="en",
        )

        self.assertEqual(result["blocks"][0]["text"], "Wrapped text")
        self.assertEqual(
            result["blocks"][0]["bbox"],
            {
                "x": 5,
                "y": 7,
                "width": 40,
                "height": 20,
                "points": [[5, 7], [45, 7], [45, 27], [5, 27]],
            },
        )

    def test_low_confidence_result_adds_warning(self):
        result = adapt_paddle_ocr_result(
            job_id="job-low",
            raw_result=[
                {
                    "rec_texts": ["faint text"],
                    "rec_scores": [0.32],
                    "rec_polys": [
                        [[4, 6], [64, 6], [64, 26], [4, 26]],
                    ],
                }
            ],
            min_confidence=0.5,
            language="en",
        )

        self.assertEqual(result["blocks"][0]["text"], "faint text")
        self.assertIn(
            "OCR_LOW_CONFIDENCE",
            [warning["code"] for warning in result["warnings"]],
        )


class OCRFallbackTests(unittest.TestCase):
    def test_create_ocr_result_falls_back_to_mock_when_paddle_fails(self):
        with patch(
            "app.services.ocr_service.run_paddle_ocr",
            side_effect=RuntimeError("paddle is unavailable"),
        ):
            with self.assertLogs("app.services.ocr_service", level="ERROR") as logs:
                result = create_ocr_result("missing.png", job_id="job-fallback")

        self.assertEqual(result["job_id"], "job-fallback")
        self.assertIn("Falling back to mock OCR", logs.output[0])
        self.assertEqual(result["raw"]["mode"], "mock")
        self.assertTrue(result["raw"]["fallback"])
        self.assertIn(
            "OCR_FALLBACK_TO_MOCK",
            [warning["code"] for warning in result["warnings"]],
        )
        self.assertEqual(
            result["blocks"][0]["text"],
            "This is mock OCR text from the uploaded image.",
        )


class RouteCompatibilityTests(unittest.TestCase):
    def test_translate_route_returns_frontend_compatible_structure(self):
        class FakeUpload:
            filename = "sample.png"

            async def read(self):
                return b"fake-image-bytes"

        fake_ocr_result = {
            "job_id": "job-route",
            "image_width": 64,
            "image_height": 48,
            "blocks": [
                {
                    "id": "block-1",
                    "text": "Real OCR text",
                    "bbox": {
                        "x": 1,
                        "y": 2,
                        "width": 30,
                        "height": 12,
                        "points": [[1, 2], [31, 2], [31, 14], [1, 14]],
                    },
                    "confidence": 0.91,
                    "line_index": 0,
                    "language": "en",
                    "source_items": [],
                }
            ],
            "raw": {"mode": "paddleocr"},
            "warnings": [],
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_settings = SimpleNamespace(
                upload_dir=root / "uploads",
                output_dir=root / "outputs",
                debug_dir=root / "debug",
                storage_dir=root,
                allowed_extensions=(".png", ".jpg", ".jpeg", ".webp"),
                max_upload_bytes=10 * 1024 * 1024,
            )
            fake_translation_settings = SimpleNamespace(
                translation_provider="mock",
                translation_target_language="zh-CN",
                deepseek_api_key="",
                deepseek_base_url="https://api.deepseek.com",
                deepseek_model="deepseek-v4-flash",
                deepseek_timeout_seconds=30,
            )

            with (
                patch("app.api.routes.settings", fake_settings),
                patch("app.services.file_service.settings", fake_settings),
                patch("app.services.translation_service.settings", fake_translation_settings),
                patch("app.api.routes.create_ocr_result", return_value=fake_ocr_result),
            ):
                result = asyncio.run(translate_image(FakeUpload()))
                debug_mask_exists = (
                    root / "debug" / "mask" / f"{result['job_id']}_mask.png"
                ).exists()

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["ocr_result"]["blocks"][0]["text"], "Real OCR text")
        self.assertEqual(result["translation_result"]["provider"], "mock")
        self.assertEqual(
            result["translation_result"]["items"][0]["source_text"],
            "Real OCR text",
        )
        self.assertEqual(result["translation_result"]["items"][0]["provider"], "mock")
        self.assertIn("/storage/uploads/", result["input_file"])
        self.assertIn("/storage/outputs/", result["output_file"])
        self.assertEqual(result["download_url"], result["output_file"])
        self.assertTrue(debug_mask_exists)


if __name__ == "__main__":
    unittest.main()

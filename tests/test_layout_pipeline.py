import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.api.routes import translate_image
from app.services.translation_service import MockTranslationProvider


class LayoutPipelineTests(unittest.TestCase):
    def test_pipeline_uses_layout_blocks_for_translation(self) -> None:
        captured: dict = {}

        def fake_translation_result(job_id: str, ocr_result: dict) -> dict:
            captured["ocr_result"] = ocr_result
            return {
                "job_id": job_id,
                "items": [
                    {
                        "block_id": ocr_result["blocks"][0]["id"],
                        "source_text": ocr_result["blocks"][0]["text"],
                        "translated_text": "合并后的译文",
                        "source_language": None,
                        "target_language": "zh-CN",
                        "provider": "mock",
                        "bbox": ocr_result["blocks"][0]["bbox"],
                        "confidence": ocr_result["blocks"][0]["confidence"],
                        "status": "success",
                        "error": None,
                    }
                ],
                "provider": "mock",
                "source_language": None,
                "target_language": "zh-CN",
                "warnings": [],
                "errors": [],
            }

        self._run_route_with(
            fake_ocr_result=self._make_multiline_ocr_result(),
            translation_side_effect=fake_translation_result,
        )

        blocks = captured["ocr_result"]["blocks"]
        self.assertEqual(len(blocks), 1)
        self.assertEqual(
            blocks[0]["text"],
            "Don't lose years of work to one malicious abuse report",
        )
        self.assertEqual(blocks[0]["block_type"], "paragraph")
        self.assertEqual(blocks[0]["source_block_ids"], ["line-1", "line-2"])

    def test_pipeline_falls_back_when_layout_merge_fails(self) -> None:
        captured: dict = {}

        def fake_translation_result(job_id: str, ocr_result: dict) -> dict:
            captured["ocr_result"] = ocr_result
            return self._make_translation_result(job_id, ocr_result)

        with patch("app.api.routes.merge_ocr_blocks", side_effect=RuntimeError("layout failed")):
            self._run_route_with(
                fake_ocr_result=self._make_multiline_ocr_result(),
                translation_side_effect=fake_translation_result,
            )

        blocks = captured["ocr_result"]["blocks"]
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0]["id"], "line-1")
        self.assertEqual(blocks[1]["id"], "line-2")

    def test_logo_or_ignored_block_does_not_break_pipeline(self) -> None:
        provider = MockTranslationProvider(target_language="zh-CN")
        blocks = [
            {
                "id": "layout-logo",
                "text": "ACME",
                "block_type": "logo",
                "bbox": {"x": 10, "y": 10, "width": 80, "height": 24, "points": None},
                "confidence": 0.92,
            }
        ]

        results = provider.translate_blocks(blocks)

        self.assertEqual(results[0]["status"], "skipped")
        self.assertEqual(results[0]["translated_text"], "ACME")

    def test_existing_mock_translation_flow_still_passes(self) -> None:
        provider = MockTranslationProvider(target_language="zh-CN")

        result = provider.translate_blocks(
            [
                {
                    "id": "block-1",
                    "text": "Hello World",
                    "bbox": {"x": 0, "y": 0, "width": 100, "height": 20, "points": None},
                    "confidence": 0.9,
                }
            ]
        )

        self.assertEqual(result[0]["provider"], "mock")
        self.assertEqual(result[0]["status"], "success")
        self.assertEqual(result[0]["source_text"], "Hello World")

    def _run_route_with(self, fake_ocr_result: dict, translation_side_effect) -> dict:
        class FakeUpload:
            filename = "sample.png"

            async def read(self):
                return b"fake-image-bytes"

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
            with (
                patch("app.api.routes.settings", fake_settings),
                patch("app.services.file_service.settings", fake_settings),
                patch("app.api.routes.create_ocr_result", return_value=fake_ocr_result),
                patch("app.api.routes.create_translation_result", side_effect=translation_side_effect),
            ):
                return asyncio.run(translate_image(FakeUpload()))

    def _make_multiline_ocr_result(self) -> dict:
        return {
            "job_id": "job-layout",
            "image_width": 300,
            "image_height": 160,
            "blocks": [
                self._make_ocr_block(
                    block_id="line-1",
                    text="Don't lose years of work",
                    bbox=(20, 20, 220, 44),
                ),
                self._make_ocr_block(
                    block_id="line-2",
                    text="to one malicious abuse report",
                    bbox=(22, 48, 230, 72),
                ),
            ],
            "raw": {"mode": "test"},
            "warnings": [],
        }

    def _make_ocr_block(
        self,
        block_id: str,
        text: str,
        bbox: tuple[int, int, int, int],
    ) -> dict:
        x1, y1, x2, y2 = bbox
        return {
            "id": block_id,
            "text": text,
            "bbox": {
                "x": x1,
                "y": y1,
                "width": x2 - x1,
                "height": y2 - y1,
                "points": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
            },
            "confidence": 0.94,
            "line_index": 0,
            "language": "en",
            "source_items": [],
        }

    def _make_translation_result(self, job_id: str, ocr_result: dict) -> dict:
        items = [
            {
                "block_id": block["id"],
                "source_text": block["text"],
                "translated_text": f"mock: {block['text']}",
                "source_language": block.get("language"),
                "target_language": "zh-CN",
                "provider": "mock",
                "bbox": block.get("bbox"),
                "confidence": block.get("confidence"),
                "status": "success",
                "error": None,
            }
            for block in ocr_result["blocks"]
        ]
        return {
            "job_id": job_id,
            "items": items,
            "provider": "mock",
            "source_language": "en",
            "target_language": "zh-CN",
            "warnings": [],
            "errors": [],
        }


if __name__ == "__main__":
    unittest.main()

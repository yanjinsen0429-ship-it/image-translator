import asyncio
import io
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from app.api.routes import translate_image
from app.services.layout_service import export_layout_debug_overlay
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

    def test_final_output_uses_rendered_image_when_rendering_succeeds(self) -> None:
        rendered_pixel = (12, 34, 56)

        def fake_translation_result(job_id: str, ocr_result: dict) -> dict:
            return self._make_translation_result(job_id, ocr_result)

        def fake_debug_rendered(
            image_path: Path,
            translation_items: list[dict],
            debug_rendered_dir: Path,
            image_id: str,
        ) -> Path:
            debug_rendered_dir.mkdir(parents=True, exist_ok=True)
            rendered_path = debug_rendered_dir / f"{image_id}_rendered.png"
            Image.new("RGB", (8, 8), rendered_pixel).save(rendered_path)
            return rendered_path

        result, root = self._run_route_with_valid_image(
            fake_ocr_result=self._make_single_block_ocr_result(),
            translation_side_effect=fake_translation_result,
            rendered_side_effect=fake_debug_rendered,
        )

        output_path = root / result["output_file"].replace("/storage/", "")
        rendered_path = root / "debug" / "rendered" / f"{result['job_id']}_rendered.png"

        self.assertEqual(result["download_url"], result["output_file"])
        self.assertIn("/storage/outputs/", result["output_file"])
        self.assertTrue(rendered_path.exists())
        self.assertTrue(output_path.exists())
        self.assertNotEqual(output_path, rendered_path)
        with Image.open(output_path) as output_image:
            self.assertNotEqual(output_image.getpixel((0, 0)), (255, 255, 255))
            self.assertEqual(output_image.getpixel((0, 0)), rendered_pixel)

    def test_export_layout_debug_overlay_saves_overlay_image(self) -> None:
        blocks = [
            {
                "id": "layout-normal",
                "text": "Hello",
                "block_type": "normal",
                "bbox": {"x": 2, "y": 2, "width": 12, "height": 8, "points": [[2, 2], [14, 2], [14, 10], [2, 10]]},
            }
        ]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image_path = root / "input.png"
            Image.new("RGB", (32, 16), "white").save(image_path)

            overlay_path = export_layout_debug_overlay(
                image_path=image_path,
                blocks=blocks,
                debug_layout_dir=root / "debug" / "layout",
                image_id="image-123",
            )

            self.assertEqual(overlay_path, root / "debug" / "layout" / "image-123_layout_overlay.png")
            self.assertTrue(overlay_path.exists())
            with Image.open(overlay_path) as overlay_image:
                self.assertEqual(overlay_image.size, (32, 16))

    def test_export_layout_debug_overlay_handles_normal_and_ignored_without_mutation(self) -> None:
        blocks = [
            {
                "id": "layout-normal",
                "text": "Hello",
                "block_type": "normal",
                "bbox": {"x": 2, "y": 2, "width": 12, "height": 8, "points": [[2, 2], [14, 2], [14, 10], [2, 10]]},
            },
            {
                "id": "layout-ignored",
                "text": "]",
                "block_type": "ignored",
                "bbox": {"x": 20, "y": 2, "width": 6, "height": 8, "points": [[20, 2], [26, 2], [26, 10], [20, 10]]},
            },
        ]
        original_blocks = copy.deepcopy(blocks)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image_path = root / "input.png"
            Image.new("RGB", (32, 16), "white").save(image_path)

            overlay_path = export_layout_debug_overlay(
                image_path=image_path,
                blocks=blocks,
                debug_layout_dir=root / "debug" / "layout",
                image_id="image-123",
            )

            self.assertTrue(overlay_path.exists())

        self.assertEqual(blocks, original_blocks)
        self.assertEqual(blocks[1]["block_type"], "ignored")

    def test_pipeline_exports_layout_debug_overlay(self) -> None:
        def fake_translation_result(job_id: str, ocr_result: dict) -> dict:
            return self._make_translation_result(job_id, ocr_result)

        result, root = self._run_route_with_valid_image(
            fake_ocr_result=self._make_single_block_ocr_result(),
            translation_side_effect=fake_translation_result,
            rendered_side_effect=self._fake_debug_rendered,
        )

        overlay_path = root / "debug" / "layout" / f"{result['job_id']}_layout_overlay.png"

        self.assertTrue(overlay_path.exists())
        with Image.open(overlay_path) as overlay_image:
            self.assertEqual(overlay_image.size, (8, 8))

    def test_pipeline_exports_layout_debug_json(self) -> None:
        def fake_translation_result(job_id: str, ocr_result: dict) -> dict:
            return self._make_translation_result(job_id, ocr_result)

        result, root = self._run_route_with_valid_image(
            fake_ocr_result=self._make_single_block_ocr_result(),
            translation_side_effect=fake_translation_result,
            rendered_side_effect=self._fake_debug_rendered,
        )

        json_path = root / "debug" / "layout" / f"{result['job_id']}_layout_blocks.json"

        self.assertTrue(json_path.exists())
        data = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(data["job_id"], result["job_id"])
        self.assertEqual(len(data["blocks"]), 1)
        self.assertEqual(data["blocks"][0]["text"], "Hello World")
        self.assertIn("enters_translation", data["blocks"][0])

    def test_pipeline_keeps_refined_noise_out_of_returned_translation_items(self) -> None:
        captured_render: dict = {}

        def fake_debug_rendered(
            image_path: Path,
            translation_items: list[dict],
            debug_rendered_dir: Path,
            image_id: str,
        ) -> Path:
            captured_render["items"] = translation_items
            return self._fake_debug_rendered(
                image_path=image_path,
                translation_items=translation_items,
                debug_rendered_dir=debug_rendered_dir,
                image_id=image_id,
            )

        fake_translation_settings = SimpleNamespace(
            translation_provider="deepseek",
            translation_target_language="zh-CN",
            deepseek_api_key="test-key",
            deepseek_base_url="https://api.deepseek.com",
            deepseek_model="deepseek-v4-flash",
            deepseek_timeout_seconds=30,
        )

        with (
            patch("app.services.translation_service.settings", fake_translation_settings),
            patch(
                "app.services.translation_service.DeepSeekTranslationProvider._request_translation",
                return_value="你弄脏了我的鞋。",
            ) as request_translation,
        ):
            result, root = self._run_route_with_valid_image_and_real_translation(
                fake_ocr_result=self._make_noise_refine_ocr_result(),
                rendered_side_effect=fake_debug_rendered,
            )

        json_path = root / "debug" / "layout" / f"{result['job_id']}_layout_blocks.json"
        debug_data = json.loads(json_path.read_text(encoding="utf-8"))
        debug_blocks_by_text = {block["text"]: block for block in debug_data["blocks"]}

        self.assertEqual(
            request_translation.call_args_list[0].args[0],
            "I told you to be careful. It's your fault that you made my shoes dirty.",
        )
        self.assertEqual(request_translation.call_count, 1)
        for text in ("]", "E", "门"):
            self.assertEqual(debug_blocks_by_text[text]["block_type"], "ignored")
            self.assertTrue(debug_blocks_by_text[text]["is_ignored"])
            self.assertFalse(debug_blocks_by_text[text]["enters_translation"])
        self.assertEqual(
            [item["source_text"] for item in result["translation_result"]["items"]],
            ["I told you to be careful. It's your fault that you made my shoes dirty."],
        )
        self.assertEqual(
            [item["source_text"] for item in captured_render["items"]],
            ["I told you to be careful. It's your fault that you made my shoes dirty."],
        )
        self.assertNotIn(
            "skipped",
            [item.get("status") for item in result["translation_result"]["items"]],
        )

    def test_pipeline_uses_only_processable_layout_blocks_for_mask_generation(self) -> None:
        captured_mask: dict = {}

        def fake_debug_mask(**kwargs) -> Path:
            captured_mask["ocr_result"] = kwargs["ocr_result"]
            mask_path = kwargs["debug_mask_dir"] / f"{kwargs['image_id']}_mask.png"
            mask_path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("L", (8, 8), 255).save(mask_path)
            return mask_path

        fake_translation_settings = SimpleNamespace(
            translation_provider="deepseek",
            translation_target_language="zh-CN",
            deepseek_api_key="test-key",
            deepseek_base_url="https://api.deepseek.com",
            deepseek_model="deepseek-v4-flash",
            deepseek_timeout_seconds=30,
        )

        with (
            patch("app.services.translation_service.settings", fake_translation_settings),
            patch(
                "app.services.translation_service.DeepSeekTranslationProvider._request_translation",
                return_value="你弄脏了我的鞋。",
            ),
        ):
            self._run_route_with_valid_image_and_real_translation(
                fake_ocr_result=self._make_noise_refine_ocr_result(),
                rendered_side_effect=self._fake_debug_rendered,
                mask_side_effect=fake_debug_mask,
            )

        mask_blocks = captured_mask["ocr_result"]["blocks"]
        self.assertEqual(len(mask_blocks), 1)
        self.assertEqual(
            mask_blocks[0]["text"],
            "I told you to be careful. It's your fault that you made my shoes dirty.",
        )
        self.assertEqual(mask_blocks[0]["block_type"], "paragraph")
        self.assertNotIn("ignored", [block.get("block_type") for block in mask_blocks])

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

    def _run_route_with_valid_image(
        self,
        fake_ocr_result: dict,
        translation_side_effect,
        rendered_side_effect,
    ) -> tuple[dict, Path]:
        class FakeUpload:
            filename = "sample.png"

            async def read(self):
                buffer = io.BytesIO()
                Image.new("RGB", (8, 8), (255, 255, 255)).save(buffer, format="PNG")
                return buffer.getvalue()

        root_path = Path(tempfile.mkdtemp())
        fake_settings = SimpleNamespace(
            upload_dir=root_path / "uploads",
            output_dir=root_path / "outputs",
            debug_dir=root_path / "debug",
            storage_dir=root_path,
            allowed_extensions=(".png", ".jpg", ".jpeg", ".webp"),
            max_upload_bytes=10 * 1024 * 1024,
        )
        mask_path = root_path / "debug" / "mask" / "test_mask.png"
        inpainted_path = root_path / "debug" / "inpainted" / "test_inpainted.png"
        mask_path.parent.mkdir(parents=True, exist_ok=True)
        inpainted_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("L", (8, 8), 255).save(mask_path)
        Image.new("RGB", (8, 8), (200, 200, 200)).save(inpainted_path)

        with (
            patch("app.api.routes.settings", fake_settings),
            patch("app.services.file_service.settings", fake_settings),
            patch("app.api.routes.create_ocr_result", return_value=fake_ocr_result),
            patch("app.api.routes.create_translation_result", side_effect=translation_side_effect),
            patch(
                "app.api.routes.InpaintingService.export_debug_mask",
                return_value=mask_path,
            ),
            patch(
                "app.api.routes.InpaintingService.export_debug_inpainted",
                return_value=inpainted_path,
            ),
            patch(
                "app.api.routes.RenderingService.export_debug_rendered",
                side_effect=rendered_side_effect,
            ),
        ):
            return asyncio.run(translate_image(FakeUpload())), root_path

    def _run_route_with_valid_image_and_real_translation(
        self,
        fake_ocr_result: dict,
        rendered_side_effect,
        mask_side_effect=None,
    ) -> tuple[dict, Path]:
        class FakeUpload:
            filename = "sample.png"

            async def read(self):
                buffer = io.BytesIO()
                Image.new("RGB", (8, 8), (255, 255, 255)).save(buffer, format="PNG")
                return buffer.getvalue()

        root_path = Path(tempfile.mkdtemp())
        fake_settings = SimpleNamespace(
            upload_dir=root_path / "uploads",
            output_dir=root_path / "outputs",
            debug_dir=root_path / "debug",
            storage_dir=root_path,
            allowed_extensions=(".png", ".jpg", ".jpeg", ".webp"),
            max_upload_bytes=10 * 1024 * 1024,
        )
        mask_path = root_path / "debug" / "mask" / "test_mask.png"
        inpainted_path = root_path / "debug" / "inpainted" / "test_inpainted.png"
        mask_path.parent.mkdir(parents=True, exist_ok=True)
        inpainted_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("L", (8, 8), 255).save(mask_path)
        Image.new("RGB", (8, 8), (200, 200, 200)).save(inpainted_path)
        if mask_side_effect is None:
            mask_side_effect = lambda **kwargs: mask_path

        with (
            patch("app.api.routes.settings", fake_settings),
            patch("app.services.file_service.settings", fake_settings),
            patch("app.api.routes.create_ocr_result", return_value=fake_ocr_result),
            patch(
                "app.api.routes.InpaintingService.export_debug_mask",
                side_effect=mask_side_effect,
            ),
            patch(
                "app.api.routes.InpaintingService.export_debug_inpainted",
                return_value=inpainted_path,
            ),
            patch(
                "app.api.routes.RenderingService.export_debug_rendered",
                side_effect=rendered_side_effect,
            ),
        ):
            return asyncio.run(translate_image(FakeUpload())), root_path

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
        confidence: float = 0.94,
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
            "confidence": confidence,
            "line_index": 0,
            "language": "en",
            "source_items": [],
        }

    def _make_single_block_ocr_result(self) -> dict:
        return {
            "job_id": "job-layout",
            "image_width": 8,
            "image_height": 8,
            "blocks": [
                self._make_ocr_block(
                    block_id="block-1",
                    text="Hello World",
                    bbox=(1, 1, 7, 7),
                ),
            ],
            "raw": {"mode": "test"},
            "warnings": [],
        }

    def _make_noise_refine_ocr_result(self) -> dict:
        return {
            "job_id": "job-layout",
            "image_width": 3000,
            "image_height": 5000,
            "blocks": [
                self._make_ocr_block(
                    block_id="block-1",
                    text="I told you to be careful.",
                    bbox=(2121, 426, 2592, 500),
                ),
                self._make_ocr_block(
                    block_id="block-2",
                    text="It's your fault that",
                    bbox=(2124, 506, 2588, 570),
                ),
                self._make_ocr_block(
                    block_id="block-3",
                    text="you made my shoes",
                    bbox=(2126, 576, 2586, 636),
                ),
                self._make_ocr_block(
                    block_id="block-4",
                    text="dirty.",
                    bbox=(2127, 642, 2320, 700),
                ),
                self._make_ocr_block(
                    block_id="block-5",
                    text="]",
                    bbox=(946, 2439, 1454, 2984),
                    confidence=0.08,
                ),
                self._make_ocr_block(
                    block_id="block-6",
                    text="E",
                    bbox=(1519, 4083, 2259, 4824),
                    confidence=0.14,
                ),
                self._make_ocr_block(
                    block_id="block-7",
                    text="门",
                    bbox=(946, 2439, 1454, 2984),
                    confidence=0.08,
                ),
            ],
            "raw": {"mode": "test"},
            "warnings": [],
        }

    def _fake_debug_rendered(
        self,
        image_path: Path,
        translation_items: list[dict],
        debug_rendered_dir: Path,
        image_id: str,
    ) -> Path:
        debug_rendered_dir.mkdir(parents=True, exist_ok=True)
        rendered_path = debug_rendered_dir / f"{image_id}_rendered.png"
        Image.new("RGB", (8, 8), (12, 34, 56)).save(rendered_path)
        return rendered_path

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

import unittest
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from app.services.rendering_service import RenderingService
from app.utils import font_utils


class RenderingServiceSkeletonTest(unittest.TestCase):
    def test_rendering_service_can_be_instantiated(self) -> None:
        service = RenderingService()

        self.assertIsInstance(service, RenderingService)

    def test_rendering_service_methods_exist(self) -> None:
        service = RenderingService()

        self.assertTrue(callable(service.calculate_font_size))
        self.assertTrue(callable(service.wrap_text))
        self.assertTrue(callable(service.draw_translation))

    def test_font_utils_functions_exist(self) -> None:
        self.assertTrue(callable(font_utils.find_default_font))
        self.assertTrue(callable(font_utils.load_font))

    def test_draw_translation_keeps_image_size_and_changes_bbox_pixels(self) -> None:
        service = RenderingService()
        image = Image.new("RGB", (120, 80), "white")
        bbox = {"x": 10, "y": 10, "width": 80, "height": 32}

        rendered = service.draw_translation(image, bbox, "你好世界")

        self.assertEqual(rendered.size, image.size)
        before = np.array(image)
        after = np.array(rendered)
        self.assertFalse(
            np.array_equal(
                before[10:42, 10:90],
                after[10:42, 10:90],
            )
        )
        self.assertTrue(np.array_equal(before[0:5, 0:5], after[0:5, 0:5]))

    def test_draw_translation_with_empty_text_does_not_crash(self) -> None:
        service = RenderingService()
        image = Image.new("RGB", (80, 40), "white")
        bbox = {"x": 5, "y": 5, "width": 60, "height": 20}

        rendered = service.draw_translation(image, bbox, "")

        self.assertEqual(rendered.size, image.size)

    def test_export_debug_rendered_saves_rendered_png(self) -> None:
        service = RenderingService()
        image = Image.new("RGB", (120, 80), "white")
        translation_items = [
            {
                "translated_text": "你好世界",
                "bbox": {"x": 10, "y": 10, "width": 80, "height": 32},
            }
        ]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image_path = root / "inpainted.png"
            image.save(image_path)

            output_path = service.export_debug_rendered(
                image_path=image_path,
                translation_items=translation_items,
                debug_rendered_dir=root / "rendered",
                image_id="image-123",
            )

            self.assertEqual(output_path, root / "rendered" / "image-123_rendered.png")
            self.assertTrue(output_path.exists())
            with Image.open(output_path) as output_image:
                self.assertEqual(output_image.size, (120, 80))

    def test_wrap_chinese_text_within_bbox_width(self) -> None:
        service = RenderingService()
        font = service._load_font(18)
        max_width = 52

        lines = service.wrap_text("这是一个很长的中文句子", font=font, max_width=max_width)

        self.assertGreater(len(lines), 1)
        self.assertTrue(
            all(
                service.measure_text_width(line, font) <= max_width
                or len(line) == 1
                for line in lines
            )
        )

    def test_font_size_not_below_minimum(self) -> None:
        service = RenderingService()
        bbox = {"x": 0, "y": 0, "width": 42, "height": 18}

        layout = service.calculate_text_layout(
            text="这是一段很长的中文文本",
            bbox=bbox,
            block_type="normal",
        )

        self.assertGreaterEqual(layout["font_size"], 12)

    def test_button_text_uses_center_alignment(self) -> None:
        service = RenderingService()
        bbox = {"x": 20, "y": 10, "width": 120, "height": 40}

        layout = service.calculate_text_layout(
            text="OK",
            bbox=bbox,
            block_type="button",
        )

        self.assertEqual(layout["align"], "center")
        self.assertEqual(layout["vertical_align"], "middle")
        self.assertGreater(layout["start_x"], bbox["x"])
        self.assertGreater(layout["start_y"], bbox["y"])

    def test_multiline_text_total_height_fits_bbox_when_possible(self) -> None:
        service = RenderingService()
        bbox = {"x": 0, "y": 0, "width": 140, "height": 72}

        layout = service.calculate_text_layout(
            text="第一行文字第二行文字第三行文字",
            bbox=bbox,
            block_type="paragraph",
        )

        self.assertLessEqual(layout["text_height"], bbox["height"])
        self.assertFalse(layout["overflow"])

    def test_rendering_accepts_layout_block_dict(self) -> None:
        service = RenderingService()
        image = Image.new("RGB", (160, 90), "white")
        block = {
            "translated_text": "合并后的中文译文",
            "bbox": {"x": 10, "y": 10, "width": 120, "height": 48},
            "block_type": "paragraph",
        }

        rendered = service.draw_translation_block(image, block)

        self.assertEqual(rendered.size, image.size)

    def test_rendering_accepts_legacy_block_dict(self) -> None:
        service = RenderingService()
        image = Image.new("RGB", (160, 90), "white")
        block = {
            "translated_text": "旧格式译文",
            "bbox": {"x": 10, "y": 10, "width": 120, "height": 40},
        }

        rendered = service.draw_translation_block(image, block)

        self.assertEqual(rendered.size, image.size)

    def test_rendering_does_not_crash_on_long_text(self) -> None:
        service = RenderingService()
        image = Image.new("RGB", (180, 90), "white")
        bbox = {"x": 5, "y": 5, "width": 80, "height": 35}

        rendered = service.draw_translation(
            image,
            bbox,
            "这是一段非常非常非常长的中文文本用于测试溢出处理不会崩溃",
        )

        self.assertEqual(rendered.size, image.size)


if __name__ == "__main__":
    unittest.main()

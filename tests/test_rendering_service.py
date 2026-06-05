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


if __name__ == "__main__":
    unittest.main()

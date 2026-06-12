import unittest
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from app.services.inpainting_service import InpaintingService
from app.utils import image_mask


class InpaintingServiceSkeletonTest(unittest.TestCase):
    def test_inpainting_service_can_be_instantiated(self) -> None:
        service = InpaintingService()

        self.assertIsInstance(service, InpaintingService)

    def test_inpainting_service_methods_exist(self) -> None:
        service = InpaintingService()

        self.assertTrue(callable(service.create_mask))
        self.assertTrue(callable(service.remove_text))

    def test_image_mask_functions_exist(self) -> None:
        self.assertTrue(callable(image_mask.polygon_to_mask))
        self.assertTrue(callable(image_mask.expand_mask))

    def test_polygon_to_mask_returns_expected_size(self) -> None:
        polygon = [(2, 2), (7, 2), (7, 7), (2, 7)]

        mask = image_mask.polygon_to_mask((10, 12), polygon)

        self.assertEqual(mask.shape, (12, 10))
        self.assertEqual(mask.dtype, np.uint8)

    def test_polygon_to_mask_fills_polygon_area(self) -> None:
        polygon = [(2, 2), (7, 2), (7, 7), (2, 7)]

        mask = image_mask.polygon_to_mask((10, 10), polygon)

        self.assertGreater(mask.sum(), 0)
        self.assertEqual(mask[4, 4], 255)
        self.assertEqual(mask[0, 0], 0)

    def test_expand_mask_increases_white_area(self) -> None:
        polygon = [(4, 4), (5, 4), (5, 5), (4, 5)]
        mask = image_mask.polygon_to_mask((10, 10), polygon)

        expanded = image_mask.expand_mask(mask, padding=2)

        self.assertEqual(expanded.shape, mask.shape)
        self.assertGreater(np.count_nonzero(expanded), np.count_nonzero(mask))

    def test_create_mask_builds_expanded_mask_from_polygon(self) -> None:
        service = InpaintingService()
        polygon = [(2, 2), (7, 2), (7, 7), (2, 7)]

        mask = service.create_mask((10, 10), polygon, padding=1)

        self.assertEqual(mask.shape, (10, 10))
        self.assertGreater(np.count_nonzero(mask), 0)

    def test_export_debug_mask_from_ocr_result_saves_mask_png(self) -> None:
        service = InpaintingService()
        ocr_result = {
            "job_id": "image-123",
            "image_width": 20,
            "image_height": 20,
            "blocks": [
                {
                    "bbox": {
                        "points": [[2, 2], [7, 2], [7, 7], [2, 7]],
                    },
                },
                {
                    "bbox": {
                        "points": [[10, 10], [15, 10], [15, 15], [10, 15]],
                    },
                },
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            output_path = service.export_debug_mask(
                ocr_result=ocr_result,
                image_path=None,
                debug_mask_dir=Path(tmp) / "mask",
                image_id="image-123",
                padding=0,
            )

            self.assertEqual(output_path, Path(tmp) / "mask" / "image-123_mask.png")
            self.assertTrue(output_path.exists())

    def test_export_debug_mask_skips_ignored_blocks(self) -> None:
        service = InpaintingService()
        ocr_result = {
            "job_id": "image-123",
            "image_width": 30,
            "image_height": 20,
            "blocks": [
                {
                    "block_type": "normal",
                    "bbox": {
                        "points": [[2, 2], [8, 2], [8, 8], [2, 8]],
                    },
                },
                {
                    "block_type": "ignored",
                    "bbox": {
                        "points": [[20, 2], [26, 2], [26, 8], [20, 8]],
                    },
                },
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            output_path = service.export_debug_mask(
                ocr_result=ocr_result,
                image_path=None,
                debug_mask_dir=Path(tmp) / "mask",
                image_id="image-123",
                padding=0,
            )

            self.assertIsNotNone(output_path)
            with Image.open(output_path) as mask_image:
                mask = np.array(mask_image.convert("L"), dtype=np.uint8)

        self.assertEqual(mask[5, 5], 255)
        self.assertEqual(mask[5, 23], 0)

    def test_export_debug_mask_skips_large_short_text_bbox(self) -> None:
        service = InpaintingService()
        ocr_result = {
            "job_id": "image-123",
            "image_width": 120,
            "image_height": 100,
            "blocks": [
                {
                    "text": "CM",
                    "block_type": "normal",
                    "bbox": {
                        "points": [[0, 45], [100, 45], [100, 100], [0, 100]],
                    },
                },
                {
                    "text": "real text",
                    "block_type": "normal",
                    "bbox": {
                        "points": [[10, 10], [30, 10], [30, 20], [10, 20]],
                    },
                },
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            output_path = service.export_debug_mask(
                ocr_result=ocr_result,
                image_path=None,
                debug_mask_dir=Path(tmp) / "mask",
                image_id="image-123",
                padding=0,
            )

            self.assertIsNotNone(output_path)
            with Image.open(output_path) as mask_image:
                mask = np.array(mask_image.convert("L"), dtype=np.uint8)

        self.assertEqual(mask[12, 12], 255)
        self.assertEqual(mask[70, 50], 0)
        self.assertLess(np.count_nonzero(mask) / mask.size, 0.05)

    def test_remove_text_inpaints_mask_area_and_preserves_unmasked_area(self) -> None:
        service = InpaintingService()
        image = np.full((24, 24, 3), 255, dtype=np.uint8)
        image[8:16, 8:16] = 0
        mask = np.zeros((24, 24), dtype=np.uint8)
        mask[8:16, 8:16] = 255

        result = service.remove_text(image, mask)

        self.assertEqual(result.shape, image.shape)
        self.assertFalse(np.array_equal(result[12, 12], image[12, 12]))
        self.assertTrue(np.array_equal(result[2, 2], image[2, 2]))

    def test_export_debug_inpainted_saves_background_png(self) -> None:
        service = InpaintingService()
        image = np.full((24, 24, 3), 255, dtype=np.uint8)
        image[8:16, 8:16] = 0
        mask = np.zeros((24, 24), dtype=np.uint8)
        mask[8:16, 8:16] = 255

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image_path = root / "input.png"
            mask_path = root / "mask.png"
            Image.fromarray(image).save(image_path)
            Image.fromarray(mask).save(mask_path)

            output_path = service.export_debug_inpainted(
                image_path=image_path,
                mask_path=mask_path,
                debug_inpainted_dir=root / "inpainted",
                image_id="image-123",
            )

            self.assertEqual(
                output_path,
                root / "inpainted" / "image-123_inpainted.png",
            )
            self.assertTrue(output_path.exists())
            with Image.open(output_path) as output_image:
                self.assertEqual(output_image.size, (24, 24))


if __name__ == "__main__":
    unittest.main()

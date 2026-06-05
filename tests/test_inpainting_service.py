import unittest
import tempfile
from pathlib import Path

import numpy as np

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


if __name__ == "__main__":
    unittest.main()

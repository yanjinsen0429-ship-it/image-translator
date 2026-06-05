import unittest

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


if __name__ == "__main__":
    unittest.main()

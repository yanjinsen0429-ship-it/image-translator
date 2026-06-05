import unittest

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


if __name__ == "__main__":
    unittest.main()

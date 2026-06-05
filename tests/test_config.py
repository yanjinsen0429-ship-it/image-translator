import os
import unittest
from unittest.mock import patch

from app.core.config import Settings


class SettingsTests(unittest.TestCase):
    def test_default_ocr_language_is_ch(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()

        self.assertEqual(settings.ocr_language, "ch")

    def test_ocr_language_can_be_overridden_by_environment(self):
        with patch.dict(os.environ, {"OCR_LANGUAGE": "japan"}, clear=True):
            settings = Settings()

        self.assertEqual(settings.ocr_language, "japan")


if __name__ == "__main__":
    unittest.main()

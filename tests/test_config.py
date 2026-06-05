import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.config import Settings, load_environment_file


class SettingsTests(unittest.TestCase):
    def test_default_ocr_language_is_ch(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()

        self.assertEqual(settings.ocr_language, "ch")

    def test_ocr_language_can_be_overridden_by_environment(self):
        with patch.dict(os.environ, {"OCR_LANGUAGE": "japan"}, clear=True):
            settings = Settings()

        self.assertEqual(settings.ocr_language, "japan")

    def test_default_translation_provider_is_mock(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()

        self.assertEqual(settings.translation_provider, "mock")
        self.assertEqual(settings.translation_target_language, "zh-CN")

    def test_deepseek_settings_can_be_loaded_from_environment(self):
        with patch.dict(
            os.environ,
            {
                "TRANSLATION_PROVIDER": "deepseek",
                "DEEPSEEK_API_KEY": "test-key",
                "DEEPSEEK_BASE_URL": "https://example.test",
                "DEEPSEEK_MODEL": "deepseek-test",
                "DEEPSEEK_TIMEOUT_SECONDS": "9",
            },
            clear=True,
        ):
            settings = Settings()

        self.assertEqual(settings.translation_provider, "deepseek")
        self.assertEqual(settings.deepseek_api_key, "test-key")
        self.assertEqual(settings.deepseek_base_url, "https://example.test")
        self.assertEqual(settings.deepseek_model, "deepseek-test")
        self.assertEqual(settings.deepseek_timeout_seconds, 9)

    def test_dotenv_file_can_configure_translation_provider(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dotenv_path = Path(temp_dir) / ".env"
            dotenv_path.write_text(
                "\n".join(
                    [
                        "TRANSLATION_PROVIDER=deepseek",
                        "TRANSLATION_TARGET_LANGUAGE=zh-CN",
                        "DEEPSEEK_API_KEY=test-key-from-dotenv",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                load_environment_file(project_root=Path(temp_dir))
                settings = Settings()

        self.assertEqual(settings.translation_provider, "deepseek")
        self.assertEqual(settings.translation_target_language, "zh-CN")
        self.assertEqual(settings.deepseek_api_key, "test-key-from-dotenv")

    def test_environment_variables_override_dotenv_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dotenv_path = Path(temp_dir) / ".env"
            dotenv_path.write_text(
                "\n".join(
                    [
                        "TRANSLATION_PROVIDER=mock",
                        "DEEPSEEK_API_KEY=dotenv-key",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {
                    "TRANSLATION_PROVIDER": "deepseek",
                    "DEEPSEEK_API_KEY": "env-key",
                },
                clear=True,
            ):
                load_environment_file(project_root=Path(temp_dir))
                settings = Settings()

        self.assertEqual(settings.translation_provider, "deepseek")
        self.assertEqual(settings.deepseek_api_key, "env-key")


if __name__ == "__main__":
    unittest.main()

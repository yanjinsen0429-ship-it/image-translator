import tempfile
import unittest
from pathlib import Path

from app.services.file_service import (
    is_allowed_image,
    save_bytes_to_uploads,
    sanitize_filename,
)
from app.services.image_render_service import create_mock_output_image
from app.services.ocr_service import create_mock_ocr_result
from app.services.translation_service import create_mock_translation_result


class FileServiceTests(unittest.TestCase):
    def test_sanitize_filename_removes_path_parts_and_unsafe_characters(self):
        safe_name = sanitize_filename(r"..\evil folder/my image!!.png")

        self.assertEqual(safe_name, "my_image.png")

    def test_is_allowed_image_accepts_only_supported_extensions(self):
        self.assertTrue(is_allowed_image("sample.png"))
        self.assertTrue(is_allowed_image("sample.JPG"))
        self.assertTrue(is_allowed_image("sample.webp"))
        self.assertFalse(is_allowed_image("sample.gif"))
        self.assertFalse(is_allowed_image("sample.exe"))

    def test_save_bytes_to_uploads_writes_unique_safe_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            saved = save_bytes_to_uploads(
                b"fake-image-bytes",
                "../unsafe name.png",
                Path(tmp),
                job_id="job-123",
            )

            self.assertTrue(saved.exists())
            self.assertEqual(saved.read_bytes(), b"fake-image-bytes")
            self.assertEqual(saved.parent, Path(tmp))
            self.assertEqual(saved.name, "job-123_unsafe_name.png")


class MockPipelineTests(unittest.TestCase):
    def test_mock_output_image_is_copy_of_input_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "input.png"
            input_path.write_bytes(b"mock-image-content")

            output_path = create_mock_output_image(
                input_path=input_path,
                output_dir=root / "outputs",
                job_id="job-456",
            )

            self.assertTrue(output_path.exists())
            self.assertEqual(output_path.read_bytes(), b"mock-image-content")
            self.assertEqual(output_path.name, "job-456_mock_output.png")

    def test_mock_ocr_and_translation_share_block_ids(self):
        ocr_result = create_mock_ocr_result(job_id="job-789")
        translation_result = create_mock_translation_result(
            job_id="job-789",
            ocr_result=ocr_result,
        )

        self.assertEqual(ocr_result["job_id"], "job-789")
        self.assertEqual(ocr_result["blocks"][0]["id"], "block-1")
        self.assertIn("mock OCR", ocr_result["blocks"][0]["text"])
        self.assertEqual(
            translation_result["items"][0]["block_id"],
            ocr_result["blocks"][0]["id"],
        )
        self.assertIn("模拟翻译", translation_result["items"][0]["translated_text"])


if __name__ == "__main__":
    unittest.main()

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "run_visual_regression.py"


def load_visual_regression_module():
    spec = importlib.util.spec_from_file_location("run_visual_regression", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VisualRegressionToolTests(unittest.TestCase):
    def setUp(self):
        self.tool = load_visual_regression_module()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_image(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (20, 12), "white").save(path)

    def test_scan_samples_supports_common_and_uppercase_extensions(self):
        samples_dir = self.root / "samples"
        self._write_image(samples_dir / "01_phone_ui_document.PNG")
        self._write_image(samples_dir / "02_game_ui_home.jpg")
        self._write_image(samples_dir / "03_game_double_bubble.JPEG")
        self._write_image(samples_dir / "04_clean_single_bubble.WEBP")
        (samples_dir / "notes.txt").write_text("ignore", encoding="utf-8")

        samples = self.tool.scan_samples(samples_dir)

        self.assertEqual(
            [sample.path.name for sample in samples],
            [
                "01_phone_ui_document.PNG",
                "02_game_ui_home.jpg",
                "03_game_double_bubble.JPEG",
                "04_clean_single_bubble.WEBP",
            ],
        )
        self.assertEqual(samples[0].sample_name, "01_phone_ui_document")

    def test_empty_samples_dir_generates_summary_and_html(self):
        output_dir = self.root / "report"

        summary = self.tool.run_visual_regression(
            samples_dir=self.root / "missing",
            output_dir=output_dir,
            api_client=self.tool.UnavailableApiClient("not used"),
        )

        self.assertEqual(summary["total_samples"], 0)
        self.assertTrue((output_dir / "summary.json").exists())
        self.assertTrue((output_dir / "index.html").exists())

    def test_limit_processes_only_first_n_samples(self):
        samples_dir = self.root / "samples"
        self._write_image(samples_dir / "01_phone_ui_document.png")
        self._write_image(samples_dir / "02_game_ui_home.png")

        summary = self.tool.run_visual_regression(
            samples_dir=samples_dir,
            output_dir=self.root / "report",
            api_client=self.tool.UnavailableApiClient("not running"),
            limit=1,
            progress=lambda message: None,
        )

        self.assertEqual(summary["total_samples"], 1)
        self.assertEqual(summary["samples"][0]["sample_name"], "01_phone_ui_document")

    def test_filter_processes_only_matching_samples(self):
        samples_dir = self.root / "samples"
        self._write_image(samples_dir / "03_game_double_bubble.png")
        self._write_image(samples_dir / "04_clean_single_bubble.png")

        summary = self.tool.run_visual_regression(
            samples_dir=samples_dir,
            output_dir=self.root / "report",
            api_client=self.tool.UnavailableApiClient("not running"),
            sample_filter="clean_single",
            progress=lambda message: None,
        )

        self.assertEqual(summary["total_samples"], 1)
        self.assertEqual(summary["samples"][0]["sample_name"], "04_clean_single_bubble")

    def test_filter_with_no_matches_generates_empty_summary(self):
        samples_dir = self.root / "samples"
        self._write_image(samples_dir / "03_game_double_bubble.png")

        summary = self.tool.run_visual_regression(
            samples_dir=samples_dir,
            output_dir=self.root / "report",
            api_client=self.tool.UnavailableApiClient("not running"),
            sample_filter="clean_single",
            progress=lambda message: None,
        )

        self.assertEqual(summary["total_samples"], 0)
        self.assertEqual(summary["samples"], [])
        self.assertTrue((self.root / "report" / "summary.json").exists())
        self.assertTrue((self.root / "report" / "index.html").exists())

    def test_render_fit_metrics_are_parsed(self):
        records = [
            {
                "can_render_inline": True,
                "possible_overflow": True,
                "selected_font_size": 9,
                "is_complex_background": True,
                "is_ui_like_label": False,
            },
            {
                "can_render_inline": False,
                "skipped_reason": "small_bbox",
            },
        ]

        metrics, skipped = self.tool.collect_metrics(records)

        self.assertEqual(metrics["record_count"], 2)
        self.assertEqual(metrics["inline_render_count"], 1)
        self.assertEqual(metrics["skipped_count"], 1)
        self.assertEqual(metrics["overflow_count"], 1)
        self.assertEqual(metrics["font_too_small_count"], 1)
        self.assertEqual(metrics["complex_background_inline_count"], 1)
        self.assertEqual(skipped, {"small_bbox": 1})

    def test_text_group_metrics_are_parsed(self):
        payload = {
            "group_count": 2,
            "groups": [
                {
                    "group_id": "text_group_region-1",
                    "text_direction": "vertical",
                    "grouped_block_ids": ["a", "b"],
                },
                {
                    "group_id": "text_group_region-2",
                    "text_direction": "horizontal",
                    "grouped_block_ids": ["c"],
                },
            ],
        }

        metrics = self.tool.collect_text_group_metrics(payload)

        self.assertEqual(metrics["group_count"], 2)
        self.assertEqual(metrics["grouped_block_count"], 3)
        self.assertEqual(metrics["vertical_group_count"], 1)
        self.assertEqual(metrics["average_blocks_per_group"], 1.5)

    def test_mode_decision_is_included_in_sample_result(self):
        sample = self.tool.Sample(Path("02_game_ui_home.png"), "02_game_ui_home")
        payload = {
            "job_id": "job-mode",
            "ocr_result": {"warnings": [], "blocks": [{"text": "100"}]},
            "translation_result": {"items": []},
        }

        result = self.tool.build_sample_result(
            sample=sample,
            payload=payload,
            http_status=200,
            sample_dir=self.root,
            copied_paths={"output": "out.png", "render_fit": "render_fit.json", "mode": "mode.json"},
            records=[{"can_render_inline": False, "skipped_reason": "ui_nav_label"}],
            missing_debug_files=[],
            mode_decision={"mode": "game_ui", "debug_only": True, "reasons": ["no_inline_render"]},
        )

        self.assertEqual(result["mode"], "game_ui")
        self.assertEqual(result["mode_decision"]["reasons"], ["no_inline_render"])

    def test_mock_or_fallback_ocr_marks_sample_failed(self):
        sample = self.tool.Sample(Path("05_complex_background_small_text.png"), "05_complex_background_small_text")
        payload = {
            "job_id": "job1",
            "ocr_result": {
                "warnings": [{"code": "OCR_FALLBACK_TO_MOCK"}],
                "blocks": [{"text": "This is mock OCR text from the uploaded image."}],
            },
            "translation_result": {"items": [{"block_id": "layout_block-1"}]},
        }

        result = self.tool.build_sample_result(
            sample=sample,
            payload=payload,
            http_status=200,
            sample_dir=self.root,
            copied_paths={"output": "out.png", "render_fit": "render_fit.json"},
            records=[{"can_render_inline": True}],
            missing_debug_files=[],
        )

        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(result["used_mock_or_fallback_ocr"])
        self.assertIn("ocr_fallback_or_mock_ocr_used", result["fail_reasons"])

    def test_complex_sample_with_single_record_is_suspicious_fail(self):
        sample = self.tool.Sample(Path("03_game_double_bubble.webp"), "03_game_double_bubble")
        payload = {
            "job_id": "job2",
            "ocr_result": {"warnings": [], "blocks": [{"text": "hello"}]},
            "translation_result": {"items": [{"block_id": "layout_block-1"}]},
        }

        result = self.tool.build_sample_result(
            sample=sample,
            payload=payload,
            http_status=200,
            sample_dir=self.root,
            copied_paths={"output": "out.png", "render_fit": "render_fit.json"},
            records=[{"can_render_inline": True}],
            missing_debug_files=[],
        )

        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(result["suspicious_single_record"])
        self.assertIn("suspicious_single_record", result["fail_reasons"])

    def test_missing_debug_files_warn_without_crashing(self):
        sample = self.tool.Sample(Path("04_clean_single_bubble.webp"), "04_clean_single_bubble")
        payload = {
            "job_id": "job3",
            "ocr_result": {"warnings": [], "blocks": [{"text": "hello"}]},
            "translation_result": {"items": [{"block_id": "layout_block-1"}]},
        }

        result = self.tool.build_sample_result(
            sample=sample,
            payload=payload,
            http_status=200,
            sample_dir=self.root,
            copied_paths={"output": "out.png"},
            records=[],
            missing_debug_files=["render_fit.json", "region_overlay.png"],
        )

        self.assertEqual(result["status"], "FAIL")
        self.assertIn("missing_render_fit_json", result["fail_reasons"])
        self.assertEqual(result["missing_debug_files"], ["render_fit.json", "region_overlay.png"])

    def test_request_timeout_marks_sample_failed(self):
        sample_path = self.root / "01_phone_ui_document.png"
        self._write_image(sample_path)
        sample = self.tool.Sample(sample_path, "01_phone_ui_document")
        sample_dir = self.root / "report" / sample.sample_name
        sample_dir.mkdir(parents=True)
        self.tool.save_png(sample_path, sample_dir / "input.png")
        client = self.tool.RequestsApiClient("http://127.0.0.1:8000", read_timeout_seconds=1)

        with mock.patch.object(
            self.tool.requests,
            "post",
            side_effect=self.tool.requests.Timeout("read timed out"),
        ):
            result = self.tool.run_sample(client, sample, sample_dir)

        self.assertEqual(result["status"], "FAIL")
        self.assertIsNone(result["http_status"])
        self.assertIn("request_timeout", result["fail_reasons"])

    def test_service_unavailable_generates_reports_without_hanging(self):
        samples_dir = self.root / "samples"
        self._write_image(samples_dir / "01_phone_ui_document.png")
        output_dir = self.root / "report"

        summary = self.tool.run_visual_regression(
            samples_dir=samples_dir,
            output_dir=output_dir,
            api_client=self.tool.UnavailableApiClient("connection refused"),
            progress=lambda message: None,
        )

        self.assertEqual(summary["fail_count"], 1)
        self.assertIn("service_unavailable", summary["samples"][0]["fail_reasons"])
        self.assertTrue((output_dir / "summary.json").exists())
        self.assertTrue((output_dir / "index.html").exists())

    def test_progress_log_is_printed_for_each_sample(self):
        class FailingApiClient:
            def health(self):
                return {"ok": True}

            def translate(self, sample):
                return self_module.ApiResponse(http_status=500, payload={}, error_message="failed")

        self_module = self.tool
        samples_dir = self.root / "samples"
        self._write_image(samples_dir / "01_phone_ui_document.png")
        output_dir = self.root / "report"

        stream = io.StringIO()
        with redirect_stdout(stream):
            self.tool.run_visual_regression(
                samples_dir=samples_dir,
                output_dir=output_dir,
                api_client=FailingApiClient(),
            )

        output = stream.getvalue()
        self.assertIn("[1/1] processing 01_phone_ui_document", output)
        self.assertIn("[1/1] FAIL 01_phone_ui_document", output)

    def test_reports_are_written(self):
        output_dir = self.root / "report"
        summary = {
            "run_time": "2026-06-13T00:00:00+00:00",
            "total_samples": 1,
            "pass_count": 1,
            "warn_count": 0,
            "fail_count": 0,
            "report_dir": str(output_dir),
            "samples": [
                {
                    "sample_name": "04_clean_single_bubble",
                    "status": "PASS",
                    "fail_reasons": [],
                    "warn_reasons": [],
                    "paths": {},
                    "metrics": {"record_count": 2},
                    "skipped_reason_counts": {},
                }
            ],
        }

        self.tool.write_reports(summary, output_dir)

        saved = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["total_samples"], 1)
        self.assertIn("04_clean_single_bubble", (output_dir / "index.html").read_text(encoding="utf-8"))

    def test_report_html_displays_mode_decision(self):
        output_dir = self.root / "report"
        summary = {
            "run_time": "2026-06-13T00:00:00+00:00",
            "total_samples": 1,
            "pass_count": 1,
            "warn_count": 0,
            "fail_count": 0,
            "report_dir": str(output_dir),
            "samples": [
                {
                    "sample_name": "02_game_ui_home",
                    "status": "PASS",
                    "fail_reasons": [],
                    "warn_reasons": [],
                    "paths": {},
                    "metrics": {"record_count": 44},
                    "skipped_reason_counts": {"ui_nav_label": 16},
                    "mode": "game_ui",
                    "mode_decision": {
                        "mode": "game_ui",
                        "debug_only": True,
                        "reasons": ["high_ui_guard_skipped_ratio"],
                    },
                }
            ],
        }

        self.tool.write_reports(summary, output_dir)
        html = (output_dir / "index.html").read_text(encoding="utf-8")

        self.assertIn("mode=<code>game_ui</code>", html)
        self.assertIn("Mode Decision", html)
        self.assertIn("high_ui_guard_skipped_ratio", html)

    def test_index_html_uses_paths_relative_to_report_dir(self):
        output_dir = self.root / "storage" / "visual_regression" / "one"
        sample_dir = output_dir / "04_clean_single_bubble"
        self._write_image(sample_dir / "input.png")
        self._write_image(sample_dir / "output.png")
        self._write_image(sample_dir / "render_fit_overlay.png")
        self._write_image(sample_dir / "text_groups_overlay.png")
        self._write_image(sample_dir / "region_overlay.png")
        self._write_image(sample_dir / "layout_overlay.png")
        (sample_dir / "mode.json").write_text("{}", encoding="utf-8")
        self._write_image(sample_dir / "mask.png")
        self._write_image(sample_dir / "inpainted.png")
        self._write_image(sample_dir / "rendered.png")
        summary = {
            "run_time": "2026-06-13T00:00:00+00:00",
            "total_samples": 1,
            "pass_count": 1,
            "warn_count": 0,
            "fail_count": 0,
            "report_dir": output_dir.as_posix(),
            "samples": [
                {
                    "sample_name": "04_clean_single_bubble",
                    "status": "PASS",
                    "input": (sample_dir / "input.png").as_posix(),
                    "output": (sample_dir / "output.png").as_posix(),
                    "fail_reasons": [],
                    "warn_reasons": [],
                    "paths": {
                        "render_fit_overlay": str(sample_dir / "render_fit_overlay.png"),
                        "text_groups_overlay": str(sample_dir / "text_groups_overlay.png"),
                        "region_overlay": str(sample_dir / "region_overlay.png"),
                        "layout_overlay": str(sample_dir / "layout_overlay.png"),
                        "mode": str(sample_dir / "mode.json"),
                        "mask": str(sample_dir / "mask.png"),
                        "inpainted": str(sample_dir / "inpainted.png"),
                        "rendered": str(sample_dir / "rendered.png"),
                    },
                    "metrics": {"record_count": 2},
                    "skipped_reason_counts": {},
                }
            ],
        }

        self.tool.write_reports(summary, output_dir)
        html = (output_dir / "index.html").read_text(encoding="utf-8")

        self.assertIn('src="04_clean_single_bubble/input.png"', html)
        self.assertIn('src="04_clean_single_bubble/output.png"', html)
        self.assertIn('src="04_clean_single_bubble/render_fit_overlay.png"', html)
        self.assertIn('src="04_clean_single_bubble/text_groups_overlay.png"', html)
        self.assertIn('src="04_clean_single_bubble/region_overlay.png"', html)
        self.assertIn('src="04_clean_single_bubble/layout_overlay.png"', html)
        self.assertNotIn('src="04_clean_single_bubble/mode.json"', html)
        self.assertIn('src="04_clean_single_bubble/mask.png"', html)
        self.assertIn('src="04_clean_single_bubble/inpainted.png"', html)
        self.assertIn('src="04_clean_single_bubble/rendered.png"', html)
        self.assertNotIn("storage/visual_regression/one/storage/visual_regression/one", html)
        self.assertNotIn("\\", html)

    def test_index_html_marks_missing_images_without_img_tag(self):
        output_dir = self.root / "storage" / "visual_regression" / "one"
        sample_dir = output_dir / "04_clean_single_bubble"
        self._write_image(sample_dir / "input.png")
        summary = {
            "run_time": "2026-06-13T00:00:00+00:00",
            "total_samples": 1,
            "pass_count": 1,
            "warn_count": 0,
            "fail_count": 0,
            "report_dir": output_dir.as_posix(),
            "samples": [
                {
                    "sample_name": "04_clean_single_bubble",
                    "status": "PASS",
                    "input": (sample_dir / "input.png").as_posix(),
                    "output": (sample_dir / "missing_output.png").as_posix(),
                    "fail_reasons": [],
                    "warn_reasons": [],
                    "paths": {
                        "render_fit_overlay": (sample_dir / "missing_overlay.png").as_posix(),
                    },
                    "metrics": {},
                    "skipped_reason_counts": {},
                }
            ],
        }

        self.tool.write_reports(summary, output_dir)
        html = (output_dir / "index.html").read_text(encoding="utf-8")

        self.assertIn('src="04_clean_single_bubble/input.png"', html)
        self.assertNotIn('src="04_clean_single_bubble/missing_output.png"', html)
        self.assertNotIn('src="04_clean_single_bubble/missing_overlay.png"', html)
        self.assertIn("output missing: missing_output.png", html)
        self.assertIn("render_fit_overlay missing: missing_overlay.png", html)


if __name__ == "__main__":
    unittest.main()

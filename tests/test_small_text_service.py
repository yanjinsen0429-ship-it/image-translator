import copy
import json
import tempfile
import unittest
from pathlib import Path

from app.services.small_text_service import (
    classify_complex_small_text_blocks,
    export_small_text_debug_json,
)


class SmallTextServiceTests(unittest.TestCase):
    def test_complex_background_fragment_is_translate_only(self):
        payload = classify_complex_small_text_blocks(
            sample_mode="complex_background",
            layout_blocks=[_block("b1", text="hello", confidence=0.82)],
            render_fit_records=[
                _record("b1", text="hello", can_render_inline=False, skipped_reason="ui_icon_label")
            ],
        )

        self.assertEqual(payload["classification_summary"]["translate_only_count"], 1)
        self.assertEqual(payload["records"][0]["classification"], "translate_only")
        self.assertIn("skipped_but_text_like", payload["records"][0]["reasons"])
        self.assertTrue(payload["records"][0]["debug_only"])

    def test_renderable_translated_block_is_inline_render(self):
        payload = classify_complex_small_text_blocks(
            sample_mode="complex_background",
            layout_blocks=[_block("b2", text="masturbating,", confidence=0.91)],
            render_fit_records=[
                _record(
                    "b2",
                    text="masturbating,",
                    translated_text="自慰，",
                    can_render_inline=True,
                    skipped_reason=None,
                )
            ],
        )

        self.assertEqual(payload["classification_summary"]["inline_render_count"], 1)
        self.assertEqual(payload["records"][0]["classification"], "inline_render")
        self.assertIn("has_translated_text", payload["records"][0]["reasons"])
        self.assertIn("currently_renderable", payload["records"][0]["reasons"])

    def test_low_confidence_single_character_is_ignored_noise(self):
        payload = classify_complex_small_text_blocks(
            sample_mode="complex_background",
            layout_blocks=[_block("b3", text="2", confidence=0.12)],
            render_fit_records=[_record("b3", text="2", can_render_inline=False)],
        )

        self.assertEqual(payload["classification_summary"]["ignored_noise_count"], 1)
        self.assertEqual(payload["records"][0]["classification"], "ignored_noise")
        self.assertIn("low_confidence_single_character", payload["records"][0]["reasons"])

    def test_large_bbox_low_confidence_single_character_is_ignored_noise(self):
        payload = classify_complex_small_text_blocks(
            sample_mode="complex_background",
            layout_blocks=[_block("b4", text="心", confidence=0.11)],
            render_fit_records=[
                _record(
                    "b4",
                    text="心",
                    can_render_inline=False,
                    bbox=[0, 651, 889, 1490],
                    bbox_area_ratio=0.22,
                    skipped_reason="short_text_large_bbox",
                )
            ],
        )

        self.assertEqual(payload["classification_summary"]["ignored_noise_count"], 1)
        self.assertEqual(payload["records"][0]["classification"], "ignored_noise")
        self.assertIn("large_bbox_single_character", payload["records"][0]["reasons"])

    def test_insufficient_evidence_is_unknown(self):
        payload = classify_complex_small_text_blocks(
            sample_mode="complex_background",
            layout_blocks=[_block("b5", text="menu", confidence=None)],
            render_fit_records=[_record("b5", text="menu", can_render_inline=False)],
        )

        self.assertEqual(payload["classification_summary"]["unknown_count"], 1)
        self.assertEqual(payload["records"][0]["classification"], "unknown")

    def test_non_complex_background_returns_empty_debug_payload(self):
        payload = classify_complex_small_text_blocks(
            sample_mode="game_ui",
            layout_blocks=[_block("b1", text="hello", confidence=0.82)],
            render_fit_records=[_record("b1", text="hello", can_render_inline=False)],
        )

        self.assertEqual(payload["sample_mode"], "game_ui")
        self.assertEqual(payload["records"], [])
        self.assertTrue(payload["debug_only"])
        self.assertIn("non_complex_background_mode", payload["reasons"])

    def test_classification_does_not_mutate_inputs(self):
        blocks = [_block("b1", text="hello", confidence=0.82)]
        records = [_record("b1", text="hello", can_render_inline=False, skipped_reason="ui_icon_label")]
        before = copy.deepcopy((blocks, records))

        classify_complex_small_text_blocks(
            sample_mode="complex_background",
            layout_blocks=blocks,
            render_fit_records=records,
        )

        self.assertEqual((blocks, records), before)

    def test_export_small_text_debug_json_writes_payload(self):
        payload = classify_complex_small_text_blocks(
            sample_mode="complex_background",
            layout_blocks=[_block("b1", text="hello", confidence=0.82)],
            render_fit_records=[_record("b1", text="hello", can_render_inline=False, skipped_reason="ui_icon_label")],
        )
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "job_small_text.json"

            exported = export_small_text_debug_json(payload, output_path=output_path, job_id="job1")

            self.assertEqual(exported, output_path)
            saved = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["job_id"], "job1")
            self.assertTrue(saved["debug_only"])
            self.assertEqual(saved["classification_summary"]["translate_only_count"], 1)


def _block(block_id, *, text, confidence):
    return {
        "id": block_id,
        "text": text,
        "bbox": {"x": 10, "y": 10, "width": 40, "height": 12},
        "confidence": confidence,
    }


def _record(
    block_id,
    *,
    text,
    translated_text=None,
    can_render_inline=False,
    skipped_reason=None,
    bbox=None,
    bbox_area_ratio=0.01,
):
    bbox = bbox or [10, 10, 50, 22]
    return {
        "block_id": block_id,
        "original_text": text,
        "translated_text": translated_text,
        "bbox": bbox,
        "bbox_width": max(0, bbox[2] - bbox[0]),
        "bbox_height": max(0, bbox[3] - bbox[1]),
        "bbox_area": max(0, bbox[2] - bbox[0]) * max(0, bbox[3] - bbox[1]),
        "bbox_area_ratio": bbox_area_ratio,
        "can_render_inline": can_render_inline,
        "skipped_reason": skipped_reason,
    }


if __name__ == "__main__":
    unittest.main()

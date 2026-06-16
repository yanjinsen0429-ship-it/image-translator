import copy
import json
import tempfile
import unittest
from pathlib import Path

from app.services.mode_service import decide_image_mode, export_mode_debug_json


class ModeServiceTests(unittest.TestCase):
    def test_game_ui_mode_from_ui_guard_signals(self):
        records = [
            _record(can_render_inline=False, skipped_reason="ui_icon_label", block_role="ui_icon_label")
            for _ in range(18)
        ]
        records += [
            _record(can_render_inline=False, skipped_reason="ui_nav_label", block_role="ui_nav_label")
            for _ in range(16)
        ]
        records += [
            _record(can_render_inline=False, skipped_reason="ui_resource_number", block_role="ui_resource_number")
            for _ in range(4)
        ]

        decision = decide_image_mode(
            layout_blocks=[],
            render_fit_records=records,
            translation_result={"items": []},
        )

        self.assertEqual(decision["mode"], "game_ui")
        self.assertTrue(decision["debug_only"])
        self.assertGreaterEqual(decision["confidence"], 0.8)
        self.assertIn("high_ui_guard_skipped_ratio", decision["reasons"])
        self.assertIn("no_inline_render", decision["reasons"])
        self.assertEqual(decision["signals"]["translation_item_count"], 0)

    def test_manga_mode_from_vertical_text_groups(self):
        text_groups = [
            {"group_id": "g1", "text_direction": "vertical", "grouped_block_ids": ["a", "b"]},
            {"group_id": "g2", "text_direction": "horizontal", "grouped_block_ids": ["c", "d"]},
        ]

        decision = decide_image_mode(
            layout_blocks=[],
            render_fit_records=[_record() for _ in range(8)],
            text_groups=text_groups,
            translation_result={"items": [{"block_id": "g1"}]},
        )

        self.assertEqual(decision["mode"], "manga")
        self.assertIn("manga_groups_present", decision["reasons"])
        self.assertIn("vertical_groups_present", decision["reasons"])
        self.assertEqual(decision["signals"]["group_count"], 2)
        self.assertEqual(decision["signals"]["vertical_group_count"], 1)

    def test_document_mode_from_paragraph_blocks(self):
        blocks = [
            {"id": f"b{i}", "block_type": "paragraph", "text": "This is a document paragraph."}
            for i in range(4)
        ]

        decision = decide_image_mode(
            layout_blocks=blocks,
            render_fit_records=[_record(original_text="This is a document paragraph.") for _ in range(8)],
            translation_result={"items": [{"block_id": "b1"} for _ in range(6)]},
        )

        self.assertEqual(decision["mode"], "document")
        self.assertIn("paragraph_blocks_present", decision["reasons"])
        self.assertEqual(decision["signals"]["paragraph_block_count"], 4)

    def test_document_mode_tolerates_single_non_vertical_group(self):
        blocks = [
            {"id": f"b{i}", "block_type": "paragraph", "text": "This is a document paragraph."}
            for i in range(7)
        ]
        blocks.append(
            {
                "id": "text_group_region-1",
                "block_type": "normal",
                "is_text_group": True,
                "text_direction": "horizontal",
                "text": "+ Ask ChatGPT",
            }
        )

        decision = decide_image_mode(
            layout_blocks=blocks,
            render_fit_records=[_record(original_text="This is a document paragraph.") for _ in range(17)],
            text_groups=[{"group_id": "g1", "text_direction": "horizontal", "grouped_block_ids": ["a", "b"]}],
            regions=[{"id": "r1", "region_type": "text_box"}],
            translation_result={"items": [{"block_id": f"b{i}"} for i in range(16)]},
        )

        self.assertEqual(decision["mode"], "document")
        self.assertIn("paragraph_blocks_present", decision["reasons"])

    def test_complex_background_mode_from_dense_small_skipped_text(self):
        records = [
            _record(
                can_render_inline=False,
                skipped_reason="ui_icon_label",
                block_role="ui_icon_label",
                bbox_width=18,
                bbox_height=12,
                original_text="x",
                linked_region_count=0,
            )
            for _ in range(75)
        ]
        records += [
            _record(
                can_render_inline=True,
                bbox_width=20,
                bbox_height=10,
                original_text="word",
                linked_region_count=0,
            )
            for _ in range(6)
        ]

        decision = decide_image_mode(
            layout_blocks=[],
            render_fit_records=records,
            translation_result={"items": [{"block_id": "layout_block-22"}, {"block_id": "layout_block-23"}]},
        )

        self.assertEqual(decision["mode"], "complex_background")
        self.assertIn("high_record_count", decision["reasons"])
        self.assertIn("high_small_text_ratio", decision["reasons"])
        self.assertIn("low_region_link_ratio", decision["reasons"])

    def test_complex_background_mode_can_use_short_fragment_ratio(self):
        records = [
            _record(
                can_render_inline=False,
                skipped_reason="ui_player_name",
                block_role="ui_player_name",
                bbox_width=80,
                bbox_height=24,
                original_text="AB",
                linked_region_count=0,
            )
            for _ in range(43)
        ]
        records += [
            _record(
                can_render_inline=False,
                skipped_reason="ui_icon_label",
                block_role="ui_icon_label",
                bbox_width=90,
                bbox_height=28,
                original_text="fragment",
                linked_region_count=0,
            )
            for _ in range(37)
        ]
        records.append(
            _record(
                can_render_inline=True,
                bbox_width=140,
                bbox_height=30,
                original_text="masturbating,",
                linked_region_count=0,
            )
        )

        decision = decide_image_mode(
            layout_blocks=[],
            render_fit_records=records,
            translation_result={"items": [{"block_id": "layout_block-22"}, {"block_id": "layout_block-23"}]},
        )

        self.assertEqual(decision["mode"], "complex_background")
        self.assertIn("high_short_text_ratio", decision["reasons"])

    def test_generic_when_evidence_is_sparse(self):
        decision = decide_image_mode(
            layout_blocks=[{"id": "b1", "block_type": "normal", "text": "hello"}],
            render_fit_records=[_record(original_text="hello")],
            translation_result={"items": [{"block_id": "b1"}]},
        )

        self.assertEqual(decision["mode"], "generic")
        self.assertTrue(decision["debug_only"])
        self.assertIn("insufficient_mode_signals", decision["reasons"])

    def test_decision_does_not_mutate_inputs(self):
        blocks = [{"id": "b1", "block_type": "paragraph", "text": "A paragraph"}]
        records = [_record(original_text="A paragraph")]
        groups = [{"group_id": "g1", "text_direction": "vertical", "grouped_block_ids": ["b1"]}]
        before = copy.deepcopy((blocks, records, groups))

        decide_image_mode(
            layout_blocks=blocks,
            render_fit_records=records,
            text_groups=groups,
            translation_result={"items": [{"block_id": "b1"}]},
        )

        self.assertEqual((blocks, records, groups), before)

    def test_export_mode_debug_json_writes_payload(self):
        decision = decide_image_mode(
            layout_blocks=[],
            render_fit_records=[_record()],
            translation_result={"items": []},
        )
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "job_mode.json"

            exported = export_mode_debug_json(decision, output_path=output_path, job_id="job1")

            self.assertEqual(exported, output_path)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["job_id"], "job1")
            self.assertEqual(payload["mode"], decision["mode"])
            self.assertTrue(payload["debug_only"])
            self.assertIn("signals", payload)


def _record(
    *,
    can_render_inline=True,
    skipped_reason=None,
    block_role="text",
    bbox_width=80,
    bbox_height=24,
    original_text="hello",
    linked_region_count=1,
):
    return {
        "block_id": "layout_block-1",
        "can_render_inline": can_render_inline,
        "skipped_reason": skipped_reason,
        "block_role": block_role,
        "bbox_width": bbox_width,
        "bbox_height": bbox_height,
        "bbox_area": bbox_width * bbox_height,
        "original_text": original_text,
        "linked_region_count": linked_region_count,
    }


if __name__ == "__main__":
    unittest.main()

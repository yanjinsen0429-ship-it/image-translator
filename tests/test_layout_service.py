import copy
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from app.services.layout_service import (
    LayoutBlock,
    classify_block,
    export_layout_debug_json,
    merge_ocr_blocks,
    normalize_ocr_block,
)
from app.services.region_service import (
    TextRegion,
    detect_text_regions,
    export_region_debug_json,
    export_region_debug_overlay,
)


def make_block(
    text: str,
    bbox: tuple[int, int, int, int],
    block_id: str | None = None,
    confidence: float = 0.9,
) -> dict:
    x1, y1, x2, y2 = bbox
    block = {
        "text": text,
        "bbox": {
            "x": x1,
            "y": y1,
            "width": x2 - x1,
            "height": y2 - y1,
            "points": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
        },
        "confidence": confidence,
    }
    if block_id is not None:
        block["id"] = block_id
    return block


class LayoutServiceTests(unittest.TestCase):
    def test_normalize_ocr_block_generates_id_and_bbox(self) -> None:
        block = {
            "text": "Hello",
            "polygon": [[10, 20], [70, 20], [70, 45], [10, 45]],
            "confidence": 0.95,
        }

        normalized = normalize_ocr_block(block, index=3)

        self.assertEqual(normalized["id"], "ocr_3")
        self.assertEqual(normalized["bbox"], (10, 20, 70, 45))
        self.assertEqual(normalized["polygon"], [[10, 20], [70, 20], [70, 45], [10, 45]])
        self.assertEqual(normalized["confidence"], 0.95)

    def test_merges_multiline_english_paragraph(self) -> None:
        blocks = [
            make_block("Don't lose years of work", (20, 20, 220, 44), "a"),
            make_block("to one malicious abuse report", (22, 48, 230, 72), "b"),
        ]

        layout_blocks = merge_ocr_blocks(blocks)

        self.assertEqual(len(layout_blocks), 1)
        self.assertIsInstance(layout_blocks[0], LayoutBlock)
        self.assertEqual(
            layout_blocks[0].text,
            "Don't lose years of work to one malicious abuse report",
        )
        self.assertEqual(layout_blocks[0].block_type, "paragraph")

    def test_does_not_merge_blocks_with_large_vertical_gap(self) -> None:
        blocks = [
            make_block("First paragraph", (20, 20, 180, 44), "a"),
            make_block("Second paragraph", (20, 120, 190, 144), "b"),
        ]

        layout_blocks = merge_ocr_blocks(blocks)

        self.assertEqual(len(layout_blocks), 2)
        self.assertEqual([block.block_type for block in layout_blocks], ["normal", "normal"])

    def test_button_does_not_merge_with_paragraph(self) -> None:
        blocks = [
            make_block("Don't lose years of work", (20, 20, 220, 44), "a"),
            make_block("Abuse Report", (65, 48, 185, 78), "button"),
        ]

        layout_blocks = merge_ocr_blocks(blocks)

        self.assertEqual(len(layout_blocks), 2)
        self.assertIn("button", [block.block_type for block in layout_blocks])

    def test_logo_is_marked_as_logo_or_ignored(self) -> None:
        block = normalize_ocr_block(
            make_block("ACME", (12, 8, 90, 32), "logo"),
            index=0,
        )

        self.assertIn(classify_block(block, image_size=(400, 300)), {"logo", "ignored"})

    def test_standalone_closing_bracket_is_marked_as_ignored(self) -> None:
        block = normalize_ocr_block(make_block("]", (42, 60, 50, 72), "noise"), index=0)

        self.assertEqual(classify_block(block), "ignored")

    def test_standalone_closing_bracket_with_large_bbox_is_marked_as_ignored(self) -> None:
        block = normalize_ocr_block(make_block("]", (120, 200, 190, 300), "noise"), index=0)

        self.assertEqual(classify_block(block), "ignored")

    def test_standalone_vertical_bar_is_marked_as_ignored(self) -> None:
        block = normalize_ocr_block(make_block("|", (42, 60, 48, 78), "noise"), index=0)

        self.assertEqual(classify_block(block), "ignored")

    def test_standalone_vertical_bar_with_large_bbox_is_marked_as_ignored(self) -> None:
        block = normalize_ocr_block(make_block("|", (120, 200, 185, 310), "noise"), index=0)

        self.assertEqual(classify_block(block), "ignored")

    def test_small_isolated_e_is_marked_as_ignored(self) -> None:
        block = normalize_ocr_block(make_block("E", (42, 60, 51, 72), "noise"), index=0)

        self.assertEqual(classify_block(block), "ignored")

    def test_large_isolated_single_letter_noise_is_marked_as_ignored(self) -> None:
        for text in ("E", "I", "l"):
            with self.subTest(text=text):
                layout_blocks = merge_ocr_blocks(
                    [make_block(text, (120, 200, 190, 300), "noise", confidence=0.42)]
                )

                self.assertEqual(len(layout_blocks), 1)
                self.assertEqual(layout_blocks[0].text, text)
                self.assertEqual(layout_blocks[0].block_type, "ignored")

    def test_low_confidence_large_isolated_cjk_single_character_is_marked_as_ignored(self) -> None:
        layout_blocks = merge_ocr_blocks(
            [make_block("门", (946, 2439, 1454, 2984), "cjk-noise", confidence=0.08)]
        )

        self.assertEqual(len(layout_blocks), 1)
        self.assertEqual(layout_blocks[0].text, "门")
        self.assertEqual(layout_blocks[0].block_type, "ignored")

    def test_low_confidence_large_ignored_cjk_single_character_does_not_enter_translation(self) -> None:
        layout_block = merge_ocr_blocks(
            [make_block("门", (946, 2439, 1454, 2984), "cjk-noise", confidence=0.08)]
        )[0]
        blocks = [
            {
                "id": layout_block.id,
                "text": layout_block.text,
                "block_type": layout_block.block_type,
                "bbox": layout_block.bbox,
                "polygon": layout_block.polygon,
                "confidence": layout_block.confidence,
            }
        ]

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "layout_blocks.json"
            export_layout_debug_json(blocks=blocks, output_path=output_path)
            data = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertTrue(data["blocks"][0]["is_ignored"])
        self.assertFalse(data["blocks"][0]["enters_translation"])

    def test_high_confidence_cjk_single_character_is_not_marked_as_ignored(self) -> None:
        block = normalize_ocr_block(make_block("门", (20, 20, 48, 52), "real-cjk", confidence=0.95), index=0)

        self.assertNotEqual(classify_block(block), "ignored")

    def test_cjk_single_character_near_text_group_is_not_marked_as_ignored(self) -> None:
        layout_blocks = merge_ocr_blocks(
            [
                make_block("门", (20, 20, 70, 70), "cjk-1", confidence=0.08),
                make_block("口", (22, 76, 72, 126), "cjk-2", confidence=0.82),
            ]
        )

        self.assertNotIn("ignored", [block.block_type for block in layout_blocks])

    def test_single_letter_near_text_group_is_not_marked_as_ignored(self) -> None:
        layout_blocks = merge_ocr_blocks(
            [
                make_block("I", (20, 20, 60, 44), "i"),
                make_block("am here", (22, 48, 120, 72), "text"),
            ]
        )

        self.assertEqual(len(layout_blocks), 1)
        self.assertEqual(layout_blocks[0].text, "I am here")
        self.assertEqual(layout_blocks[0].block_type, "paragraph")

    def test_short_button_like_text_is_not_marked_as_ignored(self) -> None:
        for text in ("OK", "Go", "No", "Yes", "AI", "A", "B", "C", "1", "2", "3"):
            with self.subTest(text=text):
                block = normalize_ocr_block(make_block(text, (20, 20, 70, 44), text), index=0)

                self.assertNotEqual(classify_block(block), "ignored")

    def test_export_layout_debug_json_writes_block_facts_without_mutation(self) -> None:
        blocks = [
            {
                "id": "layout-normal",
                "text": "Hello",
                "block_type": "normal",
                "bbox": {"x": 10, "y": 20, "width": 40, "height": 12},
                "polygon": [[10, 20], [50, 20], [50, 32], [10, 32]],
                "confidence": 0.91,
                "source_block_ids": ["ocr-1"],
            },
            {
                "id": "layout-ignored",
                "text": "]",
                "block_type": "ignored",
                "bbox": {"x": 80, "y": 24, "width": 16, "height": 30},
                "confidence": 0.42,
            },
        ]
        original_blocks = copy.deepcopy(blocks)

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "debug" / "layout" / "job-1_layout_blocks.json"

            json_path = export_layout_debug_json(blocks=blocks, output_path=output_path)

            self.assertEqual(json_path, output_path)
            self.assertTrue(json_path.exists())
            data = json.loads(json_path.read_text(encoding="utf-8"))

        self.assertEqual(blocks, original_blocks)
        self.assertEqual(len(data["blocks"]), 2)
        normal = data["blocks"][0]
        ignored = data["blocks"][1]
        self.assertEqual(normal["index"], 1)
        self.assertEqual(normal["text"], "Hello")
        self.assertEqual(normal["block_type"], "normal")
        self.assertEqual(normal["bbox"], [10, 20, 50, 32])
        self.assertEqual(normal["width"], 40)
        self.assertEqual(normal["height"], 12)
        self.assertEqual(normal["area"], 480)
        self.assertEqual(normal["center"], [30, 26])
        self.assertFalse(normal["is_ignored"])
        self.assertTrue(normal["enters_translation"])
        self.assertIn("block_type", normal["raw_keys"])
        self.assertEqual(ignored["text"], "]")
        self.assertEqual(ignored["block_type"], "ignored")
        self.assertTrue(ignored["is_ignored"])
        self.assertFalse(ignored["enters_translation"])

    def test_region_links_block_when_region_contains_block_bbox(self) -> None:
        blocks = [
            {
                "id": "layout-contained",
                "text": "Inside bubble",
                "bbox": {"x": 42, "y": 34, "width": 40, "height": 14},
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "bubble.png"
            image = Image.new("RGB", (160, 120), (120, 120, 120))
            draw = ImageDraw.Draw(image)
            draw.rectangle((25, 20, 135, 90), fill="white")
            image.save(image_path)

            regions = detect_text_regions(image_path=image_path, layout_blocks=blocks)

        self.assertTrue(any("layout-contained" in region.linked_block_ids for region in regions))

    def test_layout_debug_json_includes_linked_region_ids(self) -> None:
        blocks = [
            {
                "id": "layout-contained",
                "text": "Inside bubble",
                "block_type": "normal",
                "bbox": {"x": 42, "y": 34, "width": 40, "height": 14},
            }
        ]
        regions = [
            TextRegion(
                id="region-1",
                region_type="bubble",
                bbox=(25, 20, 135, 90),
                polygon=[[25, 20], [135, 20], [135, 90], [25, 90]],
                score=0.98,
                linked_block_ids=["layout-contained"],
            )
        ]

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "layout_blocks.json"
            export_layout_debug_json(blocks=blocks, output_path=output_path, regions=regions)
            data = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(data["blocks"][0]["linked_region_ids"], ["region-1"])
        self.assertNotIn("no_linked_text_region", data["blocks"][0]["debug_notes"])

    def test_layout_debug_json_marks_empty_linked_region_ids_without_regions(self) -> None:
        blocks = [
            {
                "id": "layout-orphan",
                "text": "No region",
                "block_type": "normal",
                "bbox": {"x": 42, "y": 34, "width": 40, "height": 14},
            }
        ]

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "layout_blocks.json"
            export_layout_debug_json(blocks=blocks, output_path=output_path, regions=[])
            data = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(data["blocks"][0]["linked_region_ids"], [])
        self.assertIn("no_linked_text_region", data["blocks"][0]["debug_notes"])

    def test_render_fit_debug_json_writes_layout_records(self) -> None:
        from app.services.render_fit_service import export_render_fit_debug_json

        blocks = [
            {
                "id": "layout-linked",
                "text": "Hello",
                "block_type": "normal",
                "bbox": {"x": 20, "y": 20, "width": 80, "height": 40},
                "linked_region_ids": ["region-1"],
            },
            {
                "id": "layout-orphan",
                "text": "Missing translation",
                "block_type": "normal",
                "bbox": {"x": 120, "y": 20, "width": 20, "height": 12},
            },
        ]
        original_blocks = copy.deepcopy(blocks)
        regions = [
            TextRegion(
                id="region-1",
                region_type="bubble",
                bbox=(10, 10, 110, 70),
                polygon=[[10, 10], [110, 10], [110, 70], [10, 70]],
                score=0.9,
                linked_block_ids=["layout-linked"],
            )
        ]
        translation_result = {
            "items": [
                {
                    "block_id": "layout-linked",
                    "source_text": "Hello",
                    "translated_text": "你好世界",
                    "status": "success",
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "render_fit.json"
            json_path = export_render_fit_debug_json(
                layout_blocks=blocks,
                translation_result=translation_result,
                regions=regions,
                output_path=output_path,
                job_id="job-fit",
            )
            data = json.loads(json_path.read_text(encoding="utf-8"))

        self.assertEqual(blocks, original_blocks)
        self.assertEqual(json_path, output_path)
        self.assertEqual(data["job_id"], "job-fit")
        self.assertEqual(data["record_count"], 2)
        linked = data["records"][0]
        orphan = data["records"][1]
        self.assertEqual(linked["block_id"], "layout-linked")
        self.assertEqual(linked["linked_region_ids"], ["region-1"])
        self.assertEqual(linked["linked_region_count"], 1)
        self.assertEqual(linked["original_text_length"], 5)
        self.assertEqual(linked["translated_text_length"], 4)
        self.assertEqual(linked["bbox_width"], 80)
        self.assertEqual(linked["bbox_height"], 40)
        self.assertEqual(linked["bbox_area"], 3200)
        self.assertIn("estimated_text_density", linked)
        self.assertIn("selected_font_size", linked)
        self.assertIn("line_count", linked)
        self.assertNotIn("no_translated_text", linked["debug_notes"])
        self.assertEqual(orphan["linked_region_ids"], [])
        self.assertIn("no_linked_region", orphan["debug_notes"])
        self.assertIn("no_translated_text", orphan["debug_notes"])

    def test_render_fit_debug_overlay_writes_risk_summary(self) -> None:
        from app.services.render_fit_service import export_render_fit_debug_overlay

        records = [
            {
                "block_id": "layout-block-3",
                "bbox": [10, 10, 70, 40],
                "translated_text_length": 12,
                "selected_font_size": 18,
                "linked_region_count": 1,
                "debug_notes": [],
            },
            {
                "block_id": "layout-block-4",
                "bbox": [80, 10, 110, 32],
                "translated_text_length": 0,
                "selected_font_size": None,
                "linked_region_count": 0,
                "debug_notes": ["no_linked_region", "no_translated_text"],
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image_path = root / "input.png"
            Image.new("RGB", (140, 80), "white").save(image_path)
            output_path = root / "debug" / "layout" / "render_fit_overlay.png"

            overlay_path = export_render_fit_debug_overlay(
                image=image_path,
                layout_blocks=[],
                render_fit_records=records,
                output_path=output_path,
            )

            with Image.open(overlay_path) as overlay_image:
                overlay_size = overlay_image.size
                changed_pixel = overlay_image.getpixel((10, 10))

        self.assertEqual(overlay_path, output_path)
        self.assertEqual(overlay_size, (140, 80))
        self.assertNotEqual(changed_pixel, (255, 255, 255))

    def test_render_fit_debug_overlay_handles_empty_records(self) -> None:
        from app.services.render_fit_service import export_render_fit_debug_overlay

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image_path = root / "input.png"
            Image.new("RGB", (24, 16), "white").save(image_path)
            output_path = root / "debug" / "layout" / "empty_render_fit_overlay.png"

            overlay_path = export_render_fit_debug_overlay(
                image=image_path,
                layout_blocks=[],
                render_fit_records=[],
                output_path=output_path,
            )

            with Image.open(overlay_path) as overlay_image:
                overlay_size = overlay_image.size

        self.assertEqual(overlay_path, output_path)
        self.assertEqual(overlay_size, (24, 16))

    def test_render_fit_debug_json_marks_large_short_text_bbox_skip_reason(self) -> None:
        from app.services.render_fit_service import export_render_fit_debug_json

        blocks = [
            {
                "id": "layout-huge-cm",
                "text": "CM",
                "block_type": "normal",
                "bbox": {"x": 0, "y": 45, "width": 100, "height": 55},
                "render_skip_reason": "short_text_large_bbox",
                "image_processing_skip_reason": "short_text_large_bbox",
            }
        ]
        translation_result = {
            "items": [
                {
                    "block_id": "layout-huge-cm",
                    "source_text": "CM",
                    "translated_text": "厘米",
                    "status": "success",
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "render_fit.json"
            json_path = export_render_fit_debug_json(
                layout_blocks=blocks,
                translation_result=translation_result,
                regions=[],
                output_path=output_path,
                job_id="job-fit",
            )
            data = json.loads(json_path.read_text(encoding="utf-8"))

        record = data["records"][0]
        self.assertEqual(json_path, output_path)
        self.assertEqual(record["translated_text"], "厘米")
        self.assertEqual(record["skipped_reason"], "short_text_large_bbox")
        self.assertIn("short_text_large_bbox", record["debug_notes"])

    def test_detects_white_bubble_candidate_from_synthetic_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "bubble.png"
            image = Image.new("RGB", (160, 120), (120, 120, 120))
            draw = ImageDraw.Draw(image)
            draw.ellipse((30, 25, 130, 90), fill="white", outline="black", width=3)
            image.save(image_path)

            regions = detect_text_regions(image_path=image_path, layout_blocks=[])

        self.assertTrue(any(region.region_type == "bubble" for region in regions))
        bubble = next(region for region in regions if region.region_type == "bubble")
        self.assertGreaterEqual(bubble.bbox[0], 25)
        self.assertLessEqual(bubble.bbox[2], 135)
        self.assertGreater(bubble.score, 0)

    def test_detects_dark_caption_box_candidate_from_synthetic_image(self) -> None:
        blocks = [
            {
                "id": "layout-caption",
                "text": "Caption",
                "bbox": {"x": 52, "y": 42, "width": 50, "height": 16},
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "caption.png"
            image = Image.new("RGB", (160, 100), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((35, 25, 125, 75), fill="black")
            image.save(image_path)

            regions = detect_text_regions(image_path=image_path, layout_blocks=blocks)

        self.assertTrue(any(region.region_type in {"caption_box", "text_box"} for region in regions))
        caption = next(region for region in regions if region.region_type in {"caption_box", "text_box"})
        self.assertIn("layout-caption", caption.linked_block_ids)
        self.assertIn("dark", " ".join(caption.notes))

    def test_creates_button_like_region_from_button_layout_block(self) -> None:
        blocks = [
            {
                "id": "layout-button",
                "text": "Abuse report",
                "block_type": "button",
                "bbox": {"x": 40, "y": 50, "width": 90, "height": 24},
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "button.png"
            Image.new("RGB", (180, 120), (35, 35, 55)).save(image_path)

            regions = detect_text_regions(image_path=image_path, layout_blocks=blocks)

        self.assertTrue(any(region.region_type == "button_like" for region in regions))
        button_region = next(region for region in regions if region.region_type == "button_like")
        self.assertIn("layout-button", button_region.linked_block_ids)
        self.assertIn("layout button", " ".join(button_region.notes))

    def test_region_debug_json_and_overlay_are_written(self) -> None:
        blocks = [
            {
                "id": "layout-block",
                "text": "Hello",
                "bbox": {"x": 42, "y": 34, "width": 40, "height": 14},
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image_path = root / "bubble.png"
            image = Image.new("RGB", (140, 100), (130, 130, 130))
            draw = ImageDraw.Draw(image)
            draw.ellipse((25, 20, 115, 80), fill="white", outline="black", width=3)
            image.save(image_path)
            regions = detect_text_regions(image_path=image_path, layout_blocks=blocks)

            json_path = export_region_debug_json(
                regions=regions,
                output_path=root / "debug" / "layout" / "job_regions.json",
                job_id="job",
            )
            overlay_path = export_region_debug_overlay(
                image_path=image_path,
                regions=regions,
                debug_layout_dir=root / "debug" / "layout",
                image_id="job",
            )

            data = json.loads(json_path.read_text(encoding="utf-8"))
            with Image.open(overlay_path) as overlay_image:
                overlay_size = overlay_image.size

        self.assertEqual(data["job_id"], "job")
        self.assertEqual(data["region_count"], len(data["regions"]))
        self.assertGreaterEqual(data["region_count"], 1)
        self.assertIn("linked_block_ids", data["regions"][0])
        self.assertEqual(overlay_size, (140, 100))

    def test_region_debug_json_writes_empty_list_for_plain_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image_path = root / "plain.png"
            Image.new("RGB", (120, 80), (128, 128, 128)).save(image_path)
            regions = detect_text_regions(image_path=image_path, layout_blocks=[])

            json_path = export_region_debug_json(
                regions=regions,
                output_path=root / "debug" / "layout" / "plain_regions.json",
                job_id="plain",
            )
            data = json.loads(json_path.read_text(encoding="utf-8"))

        self.assertEqual(regions, [])
        self.assertEqual(data["job_id"], "plain")
        self.assertEqual(data["region_count"], 0)
        self.assertEqual(data["regions"], [])

    def test_merged_bbox_covers_source_blocks(self) -> None:
        blocks = [
            make_block("Line one", (20, 20, 160, 44), "a"),
            make_block("Line two", (24, 46, 180, 70), "b"),
        ]

        merged = merge_ocr_blocks(blocks)[0]

        self.assertEqual(merged.bbox, (20, 20, 180, 70))
        self.assertEqual(merged.polygon, [[20, 20], [180, 20], [180, 70], [20, 70]])

    def test_layout_preserves_source_block_ids(self) -> None:
        blocks = [
            make_block("Line one", (20, 20, 160, 44), "a"),
            make_block("Line two", (24, 46, 180, 70), "b"),
        ]

        merged = merge_ocr_blocks(blocks)[0]

        self.assertEqual(merged.source_block_ids, ["a", "b"])

    def test_merged_text_uses_spaces_not_newlines(self) -> None:
        blocks = [
            make_block("Line one", (20, 20, 160, 44), "a"),
            make_block("Line two", (24, 46, 180, 70), "b"),
        ]

        merged = merge_ocr_blocks(blocks)[0]

        self.assertEqual(merged.text, "Line one Line two")
        self.assertNotIn("\n", merged.text)

    def test_button_horizontal_text_blocks_are_merged(self) -> None:
        blocks = [
            make_block("Abuse", (247, 693, 380, 734), "abuse"),
            make_block("report", (379, 696, 512, 738), "report"),
        ]

        layout_blocks = merge_ocr_blocks(blocks)

        self.assertEqual(len(layout_blocks), 1)
        self.assertEqual(layout_blocks[0].text, "Abuse report")
        self.assertEqual(layout_blocks[0].block_type, "button")
        self.assertEqual(layout_blocks[0].source_block_ids, ["abuse", "report"])

    def test_paragraph_is_not_classified_as_button_merge(self) -> None:
        blocks = [
            make_block("Don't lose years of work", (20, 20, 220, 44), "a"),
            make_block("to one malicious abuse", (22, 48, 230, 72), "b"),
            make_block("report", (24, 76, 120, 100), "c"),
        ]

        layout_blocks = merge_ocr_blocks(blocks)

        self.assertEqual(len(layout_blocks), 1)
        self.assertEqual(
            layout_blocks[0].text,
            "Don't lose years of work to one malicious abuse report",
        )
        self.assertEqual(layout_blocks[0].block_type, "paragraph")

    def test_far_apart_short_text_blocks_are_not_button_merged(self) -> None:
        blocks = [
            make_block("Abuse", (20, 20, 90, 44), "abuse"),
            make_block("report", (220, 22, 300, 46), "report"),
        ]

        layout_blocks = merge_ocr_blocks(blocks)

        self.assertEqual(len(layout_blocks), 2)
        self.assertNotEqual(layout_blocks[0].text, "Abuse report")

    def test_different_height_short_text_blocks_are_not_button_merged(self) -> None:
        blocks = [
            make_block("Abuse", (20, 20, 170, 74), "abuse"),
            make_block("report", (172, 42, 230, 62), "report"),
        ]

        layout_blocks = merge_ocr_blocks(blocks)

        self.assertEqual(len(layout_blocks), 2)
        self.assertNotEqual(layout_blocks[0].text, "Abuse report")


if __name__ == "__main__":
    unittest.main()

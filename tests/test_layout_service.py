import unittest

from app.services.layout_service import (
    LayoutBlock,
    classify_block,
    merge_ocr_blocks,
    normalize_ocr_block,
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

    def test_standalone_vertical_bar_is_marked_as_ignored(self) -> None:
        block = normalize_ocr_block(make_block("|", (42, 60, 48, 78), "noise"), index=0)

        self.assertEqual(classify_block(block), "ignored")

    def test_small_isolated_e_is_marked_as_ignored(self) -> None:
        block = normalize_ocr_block(make_block("E", (42, 60, 51, 72), "noise"), index=0)

        self.assertEqual(classify_block(block), "ignored")

    def test_short_button_like_text_is_not_marked_as_ignored(self) -> None:
        for text in ("OK", "Go", "No", "Yes"):
            with self.subTest(text=text):
                block = normalize_ocr_block(make_block(text, (20, 20, 70, 44), text), index=0)

                self.assertNotEqual(classify_block(block), "ignored")

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

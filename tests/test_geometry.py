import unittest

from app.utils.geometry import (
    bbox_center,
    bbox_height,
    bbox_union,
    bbox_width,
    height_similarity_ratio,
    horizontal_overlap_ratio,
    polygon_to_bbox,
    vertical_gap,
)


class GeometryTests(unittest.TestCase):
    def test_polygon_to_bbox(self) -> None:
        polygon = [[10, 20], [90, 18], [94, 42], [8, 45]]

        self.assertEqual(polygon_to_bbox(polygon), (8, 18, 94, 45))

    def test_bbox_union_returns_covering_box(self) -> None:
        bboxes = [(10, 20, 50, 40), (30, 35, 90, 70), (5, 10, 12, 18)]

        self.assertEqual(bbox_union(bboxes), (5, 10, 90, 70))

    def test_bbox_width_and_height(self) -> None:
        bbox = (10, 20, 70, 55)

        self.assertEqual(bbox_width(bbox), 60)
        self.assertEqual(bbox_height(bbox), 35)

    def test_bbox_center(self) -> None:
        self.assertEqual(bbox_center((10, 20, 70, 60)), (40.0, 40.0))

    def test_vertical_gap_returns_zero_when_overlapping(self) -> None:
        self.assertEqual(vertical_gap((10, 10, 50, 30), (12, 25, 60, 45)), 0)

    def test_vertical_gap_between_separated_boxes(self) -> None:
        self.assertEqual(vertical_gap((10, 10, 50, 30), (12, 45, 60, 65)), 15)

    def test_horizontal_overlap_ratio(self) -> None:
        ratio = horizontal_overlap_ratio((10, 10, 60, 30), (30, 40, 90, 60))

        self.assertAlmostEqual(ratio, 30 / 50)

    def test_height_similarity_ratio(self) -> None:
        ratio = height_similarity_ratio((10, 10, 60, 30), (20, 40, 80, 70))

        self.assertAlmostEqual(ratio, 20 / 30)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from typing import Iterable, Sequence


BBox = tuple[float, float, float, float]
Point = Sequence[float]
Polygon = Sequence[Point]


def polygon_to_bbox(polygon: Polygon) -> BBox:
    xs = [float(point[0]) for point in polygon]
    ys = [float(point[1]) for point in polygon]
    return _normalize_number_tuple((min(xs), min(ys), max(xs), max(ys)))


def bbox_union(bboxes: Iterable[BBox]) -> BBox:
    items = list(bboxes)
    if not items:
        raise ValueError("bbox_union requires at least one bbox.")

    x1 = min(bbox[0] for bbox in items)
    y1 = min(bbox[1] for bbox in items)
    x2 = max(bbox[2] for bbox in items)
    y2 = max(bbox[3] for bbox in items)
    return _normalize_number_tuple((x1, y1, x2, y2))


def bbox_width(bbox: BBox) -> float:
    return max(0.0, float(bbox[2]) - float(bbox[0]))


def bbox_height(bbox: BBox) -> float:
    return max(0.0, float(bbox[3]) - float(bbox[1]))


def bbox_center(bbox: BBox) -> tuple[float, float]:
    return (
        float(bbox[0]) + bbox_width(bbox) / 2,
        float(bbox[1]) + bbox_height(bbox) / 2,
    )


def vertical_gap(bbox_a: BBox, bbox_b: BBox) -> float:
    top = min(bbox_a, bbox_b, key=lambda bbox: bbox[1])
    bottom = max(bbox_a, bbox_b, key=lambda bbox: bbox[1])
    if float(bottom[1]) <= float(top[3]):
        return 0.0
    return float(bottom[1]) - float(top[3])


def horizontal_overlap_ratio(bbox_a: BBox, bbox_b: BBox) -> float:
    overlap = max(0.0, min(float(bbox_a[2]), float(bbox_b[2])) - max(float(bbox_a[0]), float(bbox_b[0])))
    min_width = min(bbox_width(bbox_a), bbox_width(bbox_b))
    if min_width <= 0:
        return 0.0
    return overlap / min_width


def height_similarity_ratio(bbox_a: BBox, bbox_b: BBox) -> float:
    height_a = bbox_height(bbox_a)
    height_b = bbox_height(bbox_b)
    max_height = max(height_a, height_b)
    if max_height <= 0:
        return 0.0
    return min(height_a, height_b) / max_height


def _normalize_number_tuple(values: BBox) -> BBox:
    normalized: list[float] = []
    for value in values:
        if float(value).is_integer():
            normalized.append(int(value))
        else:
            normalized.append(float(value))
    return tuple(normalized)  # type: ignore[return-value]

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageStat


class RenderingService:
    """v0.4 translated text rendering service.

    This stage writes translated text into OCR bounding boxes for debug output.
    """

    def calculate_font_size(
        self,
        bbox: dict[str, Any],
        line_count: int = 1,
        min_font_size: int = 12,
    ) -> int:
        """Calculate a font size for a target text box."""
        height = max(1, int(bbox.get("height", 16)))
        max_font_size = self._max_font_size(
            width=max(1, int(bbox.get("width", 1))),
            height=height,
            text_length=1,
            min_font_size=min_font_size,
        )
        return max(min_font_size, min(max_font_size, int(height / max(1, line_count) * 0.86)))

    def calculate_text_layout(
        self,
        text: str,
        bbox: dict[str, Any],
        block_type: str = "normal",
    ) -> dict[str, Any]:
        """Fit text into a bbox and return draw-ready layout details."""
        width = max(1, int(bbox.get("width", 1)))
        height = max(1, int(bbox.get("height", 1)))
        clean_text = text.strip()
        min_font_size = self._min_font_size(width=width, height=height, block_type=block_type)
        max_font_size = self._max_font_size(
            width=width,
            height=height,
            text_length=len(clean_text),
            min_font_size=min_font_size,
        )
        content_box = self._content_box(bbox)
        prefer_single_line = len(clean_text) <= 8 or block_type == "button"
        best_layout: dict[str, Any] | None = None
        best_fitting_layout: dict[str, Any] | None = None
        for font_size in range(max_font_size, min_font_size - 1, -1):
            font = self._load_font(font_size)
            lines = self.wrap_text(clean_text, font=font, max_width=content_box["width"])
            text_width = max([self.measure_text_width(line, font) for line in lines] or [0])
            text_height = self._line_block_height(font, len(lines))
            overflow = text_width > content_box["width"] or text_height > content_box["height"]
            layout = self._build_layout(
                bbox=bbox,
                block_type=block_type,
                font=font,
                font_size=font_size,
                lines=lines,
                text_width=text_width,
                text_height=text_height,
                overflow=overflow,
                content_box=content_box,
                min_font_size=min_font_size,
                max_font_size=max_font_size,
            )
            if best_layout is None:
                best_layout = layout
            if not overflow:
                if best_fitting_layout is None:
                    best_fitting_layout = layout
                if not prefer_single_line or len(lines) <= 1:
                    return layout

        return best_fitting_layout or best_layout or self._build_layout(
            bbox=bbox,
            block_type=block_type,
            font=self._load_font(min_font_size),
            font_size=min_font_size,
            lines=[],
            text_width=0,
            text_height=0,
            overflow=False,
            content_box=content_box,
            min_font_size=min_font_size,
            max_font_size=max_font_size,
        )

    def wrap_text(
        self,
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        max_width: int,
    ) -> list[str]:
        """Wrap translated text for a target text box."""
        if not text:
            return []

        draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        lines: list[str] = []
        current = ""
        for token in self._iter_wrap_units(text):
            if token == "\n":
                if current:
                    lines.append(current.rstrip())
                    current = ""
                continue
            candidate = f"{current}{token}"
            if current and draw.textlength(candidate, font=font) > max_width:
                lines.append(current.rstrip())
                current = token.lstrip()
            else:
                current = candidate
        if current:
            lines.append(current.rstrip())
        return self._rebalance_short_final_line(lines, font=font, max_width=max_width)

    def draw_translation(
        self,
        image: str | Path | Image.Image,
        bbox: dict[str, Any],
        translated_text: str,
        fill: tuple[int, int, int] | None = None,
        block_type: str = "normal",
    ) -> Image.Image:
        """Draw translated text onto an image."""
        output = self._load_image(image)
        if not translated_text:
            return output
        text_fill = fill or self.choose_text_color(output, bbox)
        stroke_fill = self._contrast_stroke_color(text_fill)

        layout = self.calculate_text_layout(
            text=translated_text,
            bbox=bbox,
            block_type=block_type,
        )
        draw = ImageDraw.Draw(output)
        line_height = self._line_height(layout["font"])
        max_lines = max(1, int(bbox.get("height", 1)) // max(1, line_height))
        for index, line in enumerate(layout["lines"][:max_lines]):
            line_width = self.measure_text_width(line, layout["font"])
            if layout["align"] == "center":
                x = layout["content_x"] + max(0, int((layout["content_width"] - line_width) / 2))
            else:
                x = layout["start_x"]
            draw.text(
                (x, layout["start_y"] + index * line_height),
                line,
                font=layout["font"],
                fill=text_fill,
                stroke_width=1,
                stroke_fill=stroke_fill,
            )

        return output

    def draw_translation_block(
        self,
        image: str | Path | Image.Image,
        block: Any,
        fill: tuple[int, int, int] | None = None,
    ) -> Image.Image:
        """Draw a legacy translation item or layout block dict."""
        normalized = self._normalize_render_block(block)
        if normalized["bbox"] is None:
            return self._load_image(image)
        return self.draw_translation(
            image=image,
            bbox=normalized["bbox"],
            translated_text=normalized["text"],
            fill=fill,
            block_type=normalized["block_type"],
        )

    def sample_background_luminance(
        self,
        image: str | Path | Image.Image,
        bbox: dict[str, Any],
    ) -> float:
        """Return average luminance for the target drawing area."""
        loaded = self._load_image(image)
        image_width, image_height = loaded.size
        x1 = max(0, min(image_width, int(bbox.get("x", 0))))
        y1 = max(0, min(image_height, int(bbox.get("y", 0))))
        x2 = max(x1 + 1, min(image_width, x1 + max(1, int(bbox.get("width", 1)))))
        y2 = max(y1 + 1, min(image_height, y1 + max(1, int(bbox.get("height", 1)))))
        crop = loaded.crop((x1, y1, x2, y2)).convert("L")
        return float(ImageStat.Stat(crop).mean[0])

    def choose_text_color(
        self,
        image: str | Path | Image.Image,
        bbox: dict[str, Any],
    ) -> tuple[int, int, int]:
        """Choose black or white text based on bbox background brightness."""
        luminance = self.sample_background_luminance(image, bbox)
        return (255, 255, 255) if luminance < 128 else (0, 0, 0)

    def export_debug_rendered(
        self,
        image_path: str | Path,
        translation_items: list[dict[str, Any]],
        debug_rendered_dir: Path,
        image_id: str,
    ) -> Path:
        """Save an image with translated text drawn into OCR boxes."""
        rendered = self._load_image(image_path)
        for item in translation_items:
            if self._should_skip_render_item(item, image_size=rendered.size):
                continue
            rendered = self.draw_translation_block(rendered, item)

        debug_rendered_dir.mkdir(parents=True, exist_ok=True)
        output_path = debug_rendered_dir / f"{image_id}_rendered.png"
        rendered.save(output_path)
        return output_path

    def _load_image(self, image: str | Path | Image.Image) -> Image.Image:
        if isinstance(image, Image.Image):
            return image.copy().convert("RGB")
        return Image.open(image).convert("RGB")

    def _load_font(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        for font_path in self._candidate_font_paths():
            if font_path.exists():
                return ImageFont.truetype(str(font_path), size=size)
        try:
            return ImageFont.truetype("arial.ttf", size=size)
        except OSError:
            return ImageFont.load_default()

    def measure_text_width(
        self,
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    ) -> float:
        return ImageDraw.Draw(Image.new("RGB", (1, 1))).textlength(text, font=font)

    def _contrast_stroke_color(
        self,
        fill: tuple[int, int, int],
    ) -> tuple[int, int, int]:
        return (0, 0, 0) if fill == (255, 255, 255) else (255, 255, 255)

    def _candidate_font_paths(self) -> list[Path]:
        windows_fonts = Path("C:/Windows/Fonts")
        return [
            windows_fonts / "msyh.ttc",
            windows_fonts / "msyhbd.ttc",
            windows_fonts / "simhei.ttf",
            windows_fonts / "simsun.ttc",
            windows_fonts / "NotoSansCJK-Regular.ttc",
        ]

    def _iter_wrap_units(self, text: str) -> list[str]:
        units: list[str] = []
        buffer = ""
        for char in text:
            if char == "\n":
                if buffer:
                    units.append(buffer)
                    buffer = ""
                units.append("\n")
            elif char.isspace():
                buffer += char
                units.append(buffer)
                buffer = ""
            elif ord(char) < 128:
                buffer += char
            else:
                if buffer:
                    units.append(buffer)
                    buffer = ""
                units.append(char)
        if buffer:
            units.append(buffer)
        return units

    def _min_font_size(self, width: int, height: int, block_type: str) -> int:
        default = 10 if block_type == "button" else 12
        if width < 12 or height < 12:
            return 6
        if height < 20:
            return min(default, 8)
        return default

    def _max_font_size(
        self,
        width: int,
        height: int,
        text_length: int,
        min_font_size: int,
    ) -> int:
        if width < 12 or height < 12:
            return max(min_font_size, 8)
        short_text_bonus = 1.0 if text_length <= 8 else 0.9
        height_limit = int(height * 0.9 * short_text_bonus)
        width_limit = int(width * (0.42 if text_length <= 4 else 0.32))
        return max(min_font_size, min(72, max(height_limit, min_font_size), max(width_limit, min_font_size)))

    def _content_box(self, bbox: dict[str, Any]) -> dict[str, int]:
        x = int(bbox.get("x", 0))
        y = int(bbox.get("y", 0))
        width = max(1, int(bbox.get("width", 1)))
        height = max(1, int(bbox.get("height", 1)))
        if width < 12 or height < 12:
            pad_x = 0
            pad_y = 0
        else:
            pad_x = min(max(2, int(width * 0.06)), max(0, (width - 1) // 4))
            pad_y = min(max(2, int(height * 0.08)), max(0, (height - 1) // 4))
        return {
            "x": x + pad_x,
            "y": y + pad_y,
            "width": max(1, width - pad_x * 2),
            "height": max(1, height - pad_y * 2),
            "pad_x": pad_x,
            "pad_y": pad_y,
        }

    def _rebalance_short_final_line(
        self,
        lines: list[str],
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        max_width: int,
    ) -> list[str]:
        if len(lines) < 2:
            return lines
        balanced = lines[:]
        for index in range(1, len(balanced)):
            previous = balanced[index - 1]
            current = balanced[index]
            if len(current) != 1 or len(previous) <= 2:
                continue
            candidate_current = previous[-1] + current
            if self.measure_text_width(candidate_current, font) <= max_width:
                balanced[index - 1] = previous[:-1]
                balanced[index] = candidate_current
        return balanced

    def _line_height(self, font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> int:
        bbox = font.getbbox("Ag")
        return max(1, bbox[3] - bbox[1] + 2)

    def _line_block_height(
        self,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        line_count: int,
    ) -> int:
        return self._line_height(font) * max(1, line_count)

    def _build_layout(
        self,
        bbox: dict[str, Any],
        block_type: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        font_size: int,
        lines: list[str],
        text_width: float,
        text_height: int,
        overflow: bool,
        content_box: dict[str, int],
        min_font_size: int,
        max_font_size: int,
    ) -> dict[str, Any]:
        align = "center"
        vertical_align = "middle"
        start_x = content_box["x"] + max(0, int((content_box["width"] - text_width) / 2))
        start_y = content_box["y"] + max(0, int((content_box["height"] - text_height) / 2))

        return {
            "font": font,
            "font_size": font_size,
            "min_font_size": min_font_size,
            "max_font_size": max_font_size,
            "lines": lines,
            "line_count": len(lines),
            "text_width": text_width,
            "text_height": text_height,
            "overflow": overflow,
            "align": align,
            "vertical_align": vertical_align,
            "start_x": start_x,
            "start_y": start_y,
            "content_x": content_box["x"],
            "content_y": content_box["y"],
            "content_width": content_box["width"],
            "content_height": content_box["height"],
            "padding_x": content_box["pad_x"],
            "padding_y": content_box["pad_y"],
        }

    def _choose_short_text_layout(
        self,
        current: dict[str, Any],
        candidate: dict[str, Any],
    ) -> dict[str, Any]:
        current_key = self._short_text_layout_rank(current)
        candidate_key = self._short_text_layout_rank(candidate)
        return candidate if candidate_key > current_key else current

    def _short_text_layout_rank(self, layout: dict[str, Any]) -> tuple[int, int, int]:
        return (
            0 if layout["overflow"] else 1,
            -len(layout["lines"]),
            layout["font_size"],
        )

    def _normalize_render_block(self, block: Any) -> dict[str, Any]:
        if not isinstance(block, dict):
            block = getattr(block, "__dict__", {})

        text = block.get("translated_text") or block.get("text") or ""
        bbox = block.get("bbox")
        if bbox is None and block.get("polygon"):
            bbox = self._bbox_from_polygon(block["polygon"])
        if isinstance(bbox, tuple | list) and len(bbox) >= 4:
            x1, y1, x2, y2 = bbox[:4]
            bbox = {
                "x": int(x1),
                "y": int(y1),
                "width": int(x2) - int(x1),
                "height": int(y2) - int(y1),
                "points": block.get("polygon"),
            }

        return {
            "text": text,
            "bbox": bbox,
            "block_type": block.get("block_type") or "normal",
        }

    def _bbox_from_polygon(self, polygon: list[list[Any]]) -> dict[str, Any]:
        xs = [float(point[0]) for point in polygon]
        ys = [float(point[1]) for point in polygon]
        x1 = int(min(xs))
        y1 = int(min(ys))
        x2 = int(max(xs))
        y2 = int(max(ys))
        return {
            "x": x1,
            "y": y1,
            "width": x2 - x1,
            "height": y2 - y1,
            "points": polygon,
        }

    def _should_skip_render_item(
        self,
        item: dict[str, Any],
        image_size: tuple[int, int] | None = None,
    ) -> bool:
        if item.get("status") == "skipped" or item.get("block_type") == "ignored":
            return True
        if item.get("render_skip_reason"):
            return True
        if image_size is not None and self._is_unsafe_large_short_text_bbox(item, image_size):
            return True
        return False

    def _is_unsafe_large_short_text_bbox(
        self,
        item: dict[str, Any],
        image_size: tuple[int, int],
    ) -> bool:
        if item.get("block_type") in {"ignored", "logo", "button"}:
            return False
        text = str(item.get("source_text") or item.get("text") or item.get("translated_text") or "").strip()
        if not text or len(text) > 4:
            return False
        bbox = self._item_bbox(item)
        if bbox is None:
            return False
        image_width, image_height = image_size
        image_area = max(1.0, float(image_width) * float(image_height))
        width = max(0.0, bbox[2] - bbox[0])
        height = max(0.0, bbox[3] - bbox[1])
        area_ratio = (width * height) / image_area
        return (
            area_ratio >= 0.18
            and width >= float(image_width) * 0.35
            and height >= float(image_height) * 0.25
        )

    def _item_bbox(self, item: dict[str, Any]) -> tuple[float, float, float, float] | None:
        bbox = item.get("bbox")
        if isinstance(bbox, dict):
            if {"x", "y", "width", "height"}.issubset(bbox):
                x = float(bbox["x"])
                y = float(bbox["y"])
                return (x, y, x + float(bbox["width"]), y + float(bbox["height"]))
            points = bbox.get("points")
            if points:
                return self._points_bbox(points)
        if isinstance(bbox, tuple | list) and len(bbox) >= 4:
            return (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
        polygon = item.get("polygon")
        if polygon:
            return self._points_bbox(polygon)
        return None

    def _points_bbox(self, points: list[Any]) -> tuple[float, float, float, float] | None:
        try:
            xs = [float(point[0]) for point in points]
            ys = [float(point[1]) for point in points]
        except (TypeError, ValueError, IndexError):
            return None
        if not xs or not ys:
            return None
        return (min(xs), min(ys), max(xs), max(ys))

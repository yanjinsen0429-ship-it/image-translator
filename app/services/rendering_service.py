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
        return max(min_font_size, min(48, int(height / max(1, line_count) * 0.8)))

    def calculate_text_layout(
        self,
        text: str,
        bbox: dict[str, Any],
        block_type: str = "normal",
    ) -> dict[str, Any]:
        """Fit text into a bbox and return draw-ready layout details."""
        width = max(1, int(bbox.get("width", 1)))
        height = max(1, int(bbox.get("height", 1)))
        min_font_size = 10 if block_type == "button" else 12
        max_font_size = max(min_font_size, min(48, int(height * 0.8)))
        prefer_fewer_lines = len(text.strip()) <= 12 or block_type == "button"

        best_layout: dict[str, Any] | None = None
        for font_size in range(max_font_size, min_font_size - 1, -1):
            font = self._load_font(font_size)
            lines = self.wrap_text(text, font=font, max_width=width)
            text_width = max([self.measure_text_width(line, font) for line in lines] or [0])
            text_height = self._line_block_height(font, len(lines))
            overflow = text_width > width or text_height > height
            layout = self._build_layout(
                bbox=bbox,
                block_type=block_type,
                font=font,
                font_size=font_size,
                lines=lines,
                text_width=text_width,
                text_height=text_height,
                overflow=overflow,
            )
            if best_layout is None:
                best_layout = layout
            elif prefer_fewer_lines:
                best_layout = self._choose_short_text_layout(best_layout, layout)
            else:
                best_layout = layout
            if not overflow:
                if not prefer_fewer_lines:
                    break

        return best_layout or self._build_layout(
            bbox=bbox,
            block_type=block_type,
            font=self._load_font(min_font_size),
            font_size=min_font_size,
            lines=[],
            text_width=0,
            text_height=0,
            overflow=False,
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
        return lines

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
                x = int(bbox.get("x", 0)) + max(0, (int(bbox.get("width", 1)) - int(line_width)) // 2)
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
            if self._should_skip_render_item(item):
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
    ) -> dict[str, Any]:
        x = int(bbox.get("x", 0))
        y = int(bbox.get("y", 0))
        width = max(1, int(bbox.get("width", 1)))
        height = max(1, int(bbox.get("height", 1)))
        align = "center" if block_type == "button" or (len("".join(lines)) <= 8 and len(lines) <= 1) else "left"
        vertical_align = "middle" if block_type == "button" else "top"
        start_x = x
        if align == "center":
            start_x = x + max(0, int((width - text_width) / 2))
        start_y = y
        if vertical_align == "middle":
            start_y = y + max(0, int((height - text_height) / 2))

        return {
            "font": font,
            "font_size": font_size,
            "lines": lines,
            "text_width": text_width,
            "text_height": text_height,
            "overflow": overflow,
            "align": align,
            "vertical_align": vertical_align,
            "start_x": start_x,
            "start_y": start_y,
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

    def _should_skip_render_item(self, item: dict[str, Any]) -> bool:
        return item.get("status") == "skipped" or item.get("block_type") == "ignored"

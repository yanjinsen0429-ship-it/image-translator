from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


class RenderingService:
    """v0.4 translated text rendering service.

    This stage writes translated text into OCR bounding boxes for debug output.
    """

    def calculate_font_size(self, bbox: dict[str, Any], line_count: int = 1) -> int:
        """Calculate a font size for a target text box."""
        height = max(1, int(bbox.get("height", 16)))
        return max(8, min(48, int(height / max(1, line_count) * 0.72)))

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
        fill: tuple[int, int, int] = (0, 0, 0),
    ) -> Image.Image:
        """Draw translated text onto an image."""
        output = self._load_image(image)
        if not translated_text:
            return output

        x = int(bbox.get("x", 0))
        y = int(bbox.get("y", 0))
        width = max(1, int(bbox.get("width", 1)))
        height = max(1, int(bbox.get("height", 1)))
        font = self._load_font(self.calculate_font_size(bbox))
        lines = self.wrap_text(translated_text, font=font, max_width=width)

        while lines and self._line_block_height(font, len(lines)) > height and font.size > 8:
            font = self._load_font(font.size - 1)
            lines = self.wrap_text(translated_text, font=font, max_width=width)

        draw = ImageDraw.Draw(output)
        line_height = self._line_height(font)
        max_lines = max(1, height // max(1, line_height))
        for index, line in enumerate(lines[:max_lines]):
            draw.text((x, y + index * line_height), line, font=font, fill=fill)

        return output

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
            bbox = item.get("bbox")
            text = item.get("translated_text") or ""
            if not bbox:
                continue
            rendered = self.draw_translation(rendered, bbox, text)

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

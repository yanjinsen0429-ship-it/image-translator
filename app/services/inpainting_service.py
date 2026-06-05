from __future__ import annotations

from typing import Any


class InpaintingService:
    """v0.4 inpainting service skeleton.

    Business logic will be added in later v0.4 implementation steps.
    """

    def create_mask(self, *args: Any, **kwargs: Any) -> None:
        """Create a text-region mask from OCR geometry."""
        return None

    def remove_text(self, *args: Any, **kwargs: Any) -> None:
        """Remove text from an image using a prepared mask."""
        return None

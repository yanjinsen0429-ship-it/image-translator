from typing import Any, Literal

from pydantic import BaseModel


class BBox(BaseModel):
    x: int
    y: int
    width: int
    height: int
    points: list[list[int]] | None = None


class Issue(BaseModel):
    code: str
    message: str
    stage: str
    level: Literal["warning", "error"]
    detail: str | None = None
    block_id: str | None = None


class OCRBlock(BaseModel):
    id: str
    text: str
    bbox: BBox
    confidence: float
    line_index: int
    language: str | None = None
    source_items: list[dict[str, Any]] = []


class OCRResult(BaseModel):
    job_id: str
    image_width: int | None = None
    image_height: int | None = None
    blocks: list[OCRBlock]
    raw: dict[str, Any] | None = None
    warnings: list[Issue] = []


class TranslationItem(BaseModel):
    block_id: str
    source_text: str
    translated_text: str
    status: Literal["success", "skipped", "failed"]
    error: str | None = None


class TranslationResult(BaseModel):
    job_id: str
    items: list[TranslationItem]
    provider: str
    source_language: str
    target_language: str
    warnings: list[Issue] = []
    errors: list[Issue] = []


class ImageProcessResult(BaseModel):
    job_id: str
    status: Literal["success", "partial_success", "failed"]
    input_file: str
    output_file: str
    download_url: str
    ocr_result: OCRResult
    translation_result: TranslationResult
    warnings: list[Issue] = []
    errors: list[Issue] = []

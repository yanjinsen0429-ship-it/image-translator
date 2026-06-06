import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.core.config import settings
from app.models.schemas import ImageProcessResult
from app.services.file_service import (
    UploadError,
    create_job_id,
    save_bytes_to_uploads,
    storage_url_for,
)
from app.services.image_render_service import create_mock_output_image
from app.services.inpainting_service import InpaintingService
from app.services.layout_service import (
    LayoutBlock,
    export_layout_debug_json,
    export_layout_debug_overlay,
    merge_ocr_blocks,
)
from app.services.ocr_service import create_ocr_result
from app.services.rendering_service import RenderingService
from app.services.render_fit_service import export_render_fit_debug_json
from app.services.region_service import (
    detect_text_regions,
    export_region_debug_json,
    export_region_debug_overlay,
)
from app.services.translation_service import create_translation_result

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/images/translate", response_model=ImageProcessResult)
async def translate_image(file: UploadFile = File(...)) -> dict:
    job_id = create_job_id()

    try:
        content = await file.read()
        input_path = save_bytes_to_uploads(
            content=content,
            original_filename=file.filename or "upload",
            upload_dir=settings.upload_dir,
            job_id=job_id,
        )
    except UploadError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": exc.code,
                "message": exc.message,
                "stage": "upload",
            },
        ) from exc

    output_path = create_mock_output_image(
        input_path=input_path,
        output_dir=settings.output_dir,
        job_id=job_id,
    )
    ocr_result = create_ocr_result(image_path=input_path, job_id=job_id)
    translation_input = _create_translation_input_from_layout(ocr_result)
    try:
        export_layout_debug_overlay(
            image_path=input_path,
            blocks=translation_input.get("blocks", []),
            debug_layout_dir=settings.debug_dir / "layout",
            image_id=job_id,
        )
    except Exception:
        logger.exception("Failed to export debug layout overlay for job %s", job_id)
    regions = []
    try:
        regions = detect_text_regions(
            image_path=input_path,
            layout_blocks=translation_input.get("blocks", []),
        )
        export_region_debug_overlay(
            image_path=input_path,
            regions=regions,
            debug_layout_dir=settings.debug_dir / "layout",
            image_id=job_id,
        )
        export_region_debug_json(
            regions=regions,
            output_path=settings.debug_dir / "layout" / f"{job_id}_regions.json",
            job_id=job_id,
        )
    except Exception:
        logger.exception("Failed to export debug text regions for job %s", job_id)
    try:
        export_layout_debug_json(
            blocks=translation_input.get("blocks", []),
            output_path=settings.debug_dir / "layout" / f"{job_id}_layout_blocks.json",
            job_id=job_id,
            regions=regions,
        )
    except Exception:
        logger.exception("Failed to export debug layout JSON for job %s", job_id)

    inpainted_path = None
    try:
        inpainting_service = InpaintingService()
        image_processing_input = _without_ignored_blocks(translation_input)
        mask_path = inpainting_service.export_debug_mask(
            ocr_result=image_processing_input,
            image_path=input_path,
            debug_mask_dir=settings.debug_dir / "mask",
            image_id=job_id,
        )
        if mask_path is not None:
            inpainted_path = inpainting_service.export_debug_inpainted(
                image_path=input_path,
                mask_path=mask_path,
                debug_inpainted_dir=settings.debug_dir / "inpainted",
                image_id=job_id,
            )
    except Exception:
        logger.exception("Failed to export debug OCR mask for job %s", job_id)

    translation_result = create_translation_result(
        job_id=job_id,
        ocr_result=translation_input,
    )
    translation_result = _without_skipped_translation_items(translation_result)
    try:
        export_render_fit_debug_json(
            layout_blocks=translation_input.get("blocks", []),
            translation_result=translation_result,
            regions=regions,
            output_path=settings.debug_dir / "layout" / f"{job_id}_render_fit.json",
            job_id=job_id,
        )
    except Exception:
        logger.exception("Failed to export debug render fit JSON for job %s", job_id)
    try:
        if inpainted_path is not None:
            rendered_path = RenderingService().export_debug_rendered(
                image_path=inpainted_path,
                translation_items=translation_result.get("items", []),
                debug_rendered_dir=settings.debug_dir / "rendered",
                image_id=job_id,
            )
            output_path = _publish_rendered_output(
                rendered_path=rendered_path,
                output_dir=settings.output_dir,
                job_id=job_id,
            )
    except Exception:
        logger.exception("Failed to export debug rendered image for job %s", job_id)

    return {
        "job_id": job_id,
        "status": "success",
        "input_file": storage_url_for(input_path),
        "output_file": storage_url_for(output_path),
        "download_url": storage_url_for(output_path),
        "ocr_result": ocr_result,
        "translation_result": translation_result,
        "warnings": [
            {
                "code": "MOCK_PIPELINE",
                "message": "当前仍使用 mock 翻译和 mock 输出图，未进行真实翻译、擦字或重绘。",
                "stage": "render",
                "level": "warning",
                "detail": None,
                "block_id": None,
            }
        ],
        "errors": [],
    }


def _without_ignored_blocks(ocr_result: dict) -> dict:
    return {
        **ocr_result,
        "blocks": [
            block
            for block in ocr_result.get("blocks", [])
            if block.get("block_type") != "ignored"
        ],
    }


def _without_skipped_translation_items(translation_result: dict) -> dict:
    return {
        **translation_result,
        "items": [
            item
            for item in translation_result.get("items", [])
            if item.get("status") != "skipped"
        ],
    }


def _create_translation_input_from_layout(ocr_result: dict) -> dict:
    try:
        layout_blocks = merge_ocr_blocks(
            ocr_result.get("blocks", []),
            image_size=_ocr_image_size(ocr_result),
        )
    except Exception:
        logger.exception("Failed to merge OCR blocks for layout; falling back to OCR blocks.")
        return ocr_result

    return {
        **ocr_result,
        "blocks": [_layout_block_to_translation_block(block) for block in layout_blocks],
        "raw": {
            **(ocr_result.get("raw") or {}),
            "layout_enabled": True,
            "layout_block_count": len(layout_blocks),
        },
    }


def _publish_rendered_output(rendered_path: Path, output_dir: Path, job_id: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{job_id}_output.png"
    shutil.copyfile(rendered_path, output_path)
    return output_path


def _ocr_image_size(ocr_result: dict) -> tuple[int, int] | None:
    width = ocr_result.get("image_width")
    height = ocr_result.get("image_height")
    if width and height:
        return int(width), int(height)
    return None


def _layout_block_to_translation_block(block: LayoutBlock) -> dict:
    x1, y1, x2, y2 = block.bbox
    return {
        "id": block.id,
        "text": block.text,
        "bbox": {
            "x": round(float(x1)),
            "y": round(float(y1)),
            "width": round(float(x2) - float(x1)),
            "height": round(float(y2) - float(y1)),
            "points": block.polygon,
        },
        "confidence": block.confidence,
        "line_index": 0,
        "language": None,
        "source_items": [],
        "block_type": block.block_type,
        "source_block_ids": block.source_block_ids,
        "polygon": block.polygon,
    }

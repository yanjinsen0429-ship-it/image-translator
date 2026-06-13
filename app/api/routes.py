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
from app.services.render_fit_service import (
    build_render_fit_debug_records,
    export_render_fit_debug_json,
    export_render_fit_debug_overlay,
)
from app.services.region_service import (
    detect_text_regions,
    export_region_debug_json,
    export_region_debug_overlay,
)
from app.services.text_group_service import (
    apply_text_groups,
    build_text_groups,
    export_text_group_debug_json,
    export_text_group_debug_overlay,
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
    skipped_text_group_candidates: list[dict] = []
    try:
        text_groups = build_text_groups(
            layout_blocks=translation_input.get("blocks", []),
            regions=regions,
            skipped_candidates=skipped_text_group_candidates,
        )
        translation_input = {
            **translation_input,
            "blocks": apply_text_groups(translation_input.get("blocks", []), text_groups),
        }
    except Exception:
        logger.exception("Failed to group text regions for job %s", job_id)
    translation_input = _with_unsafe_block_guards(translation_input, regions=regions)
    translation_input = _with_renderable_block_decisions(translation_input)
    renderable_input = _with_renderable_blocks_only(translation_input)
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
        mask_path = inpainting_service.export_debug_mask(
            ocr_result=renderable_input,
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
    render_translation_result = _translation_result_for_renderable_blocks(
        translation_result=translation_result,
        renderable_blocks=renderable_input.get("blocks", []),
    )
    try:
        export_text_group_debug_json(
            blocks=translation_input.get("blocks", []),
            translation_result=translation_result,
            output_path=settings.debug_dir / "layout" / f"{job_id}_text_groups.json",
            job_id=job_id,
            skipped_candidates=skipped_text_group_candidates,
        )
        export_text_group_debug_overlay(
            image_path=input_path,
            blocks=translation_input.get("blocks", []),
            output_path=settings.debug_dir / "layout" / f"{job_id}_text_groups_overlay.png",
        )
        render_fit_records = build_render_fit_debug_records(
            layout_blocks=translation_input.get("blocks", []),
            translation_result=translation_result,
            regions=regions,
        )
        export_render_fit_debug_json(
            layout_blocks=translation_input.get("blocks", []),
            translation_result=translation_result,
            regions=regions,
            output_path=settings.debug_dir / "layout" / f"{job_id}_render_fit.json",
            job_id=job_id,
            render_fit_records=render_fit_records,
        )
        export_render_fit_debug_overlay(
            image=input_path,
            layout_blocks=translation_input.get("blocks", []),
            render_fit_records=render_fit_records,
            output_path=settings.debug_dir / "layout" / f"{job_id}_render_fit_overlay.png",
        )
    except Exception:
        logger.exception("Failed to export debug render fit artifacts for job %s", job_id)
    try:
        if inpainted_path is not None:
            rendered_path = RenderingService().export_debug_rendered(
                image_path=inpainted_path,
                translation_items=render_translation_result.get("items", []),
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


def _with_renderable_block_decisions(ocr_result: dict) -> dict:
    return {
        **ocr_result,
        "blocks": [
            _with_renderable_block_decision(block)
            for block in ocr_result.get("blocks", [])
        ],
    }


def _with_renderable_block_decision(block: dict) -> dict:
    skipped_reason = _renderable_skip_reason(block)
    return {
        **block,
        "can_render_inline": skipped_reason is None,
        "skipped_reason": skipped_reason,
    }


def _renderable_skip_reason(block: dict) -> str | None:
    if block.get("can_render_inline") is False:
        return (
            block.get("skipped_reason")
            or block.get("render_skip_reason")
            or block.get("image_processing_skip_reason")
            or "render_inline_disabled"
        )
    if block.get("block_type") in {"ignored", "logo"}:
        return f"block_type={block.get('block_type')}"
    return block.get("skipped_reason") or block.get("render_skip_reason") or block.get("image_processing_skip_reason")


def _with_renderable_blocks_only(ocr_result: dict) -> dict:
    return {
        **ocr_result,
        "blocks": [
            block
            for block in ocr_result.get("blocks", [])
            if block.get("can_render_inline") is True
        ],
    }


def _translation_result_for_renderable_blocks(translation_result: dict, renderable_blocks: list[dict]) -> dict:
    renderable_block_ids = {
        str(block.get("id"))
        for block in renderable_blocks
        if block.get("id") is not None
    }
    return {
        **translation_result,
        "items": [
            item
            for item in translation_result.get("items", [])
            if str(item.get("block_id")) in renderable_block_ids
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


def _with_unsafe_block_guards(ocr_result: dict, regions: list | None = None) -> dict:
    image_size = _ocr_image_size(ocr_result)
    if image_size is None:
        return ocr_result

    return {
        **ocr_result,
        "blocks": [
            _with_unsafe_block_guard(block, image_size=image_size, regions=regions or [])
            for block in ocr_result.get("blocks", [])
        ],
    }


def _with_unsafe_block_guard(
    block: dict,
    image_size: tuple[int, int],
    regions: list,
) -> dict:
    skip_reason = _unsafe_large_short_text_bbox_reason(
        block=block,
        image_size=image_size,
        regions=regions,
    )
    if skip_reason is None:
        return block
    return {
        **block,
        "image_processing_skip_reason": skip_reason,
        "render_skip_reason": skip_reason,
    }


def _unsafe_large_short_text_bbox_reason(
    block: dict,
    image_size: tuple[int, int],
    regions: list,
) -> str | None:
    if block.get("block_type") in {"ignored", "logo", "button"}:
        return None
    text = str(block.get("text") or "").strip()
    if not text or len(text) > 4:
        return None
    if _block_has_linked_text_region(block, regions):
        return None

    bbox = _block_bbox(block)
    if bbox is None:
        return None
    image_width, image_height = image_size
    image_area = max(1.0, float(image_width) * float(image_height))
    width = max(0.0, bbox[2] - bbox[0])
    height = max(0.0, bbox[3] - bbox[1])
    area_ratio = (width * height) / image_area
    if (
        area_ratio >= 0.18
        and width >= float(image_width) * 0.35
        and height >= float(image_height) * 0.25
    ):
        return "short_text_large_bbox"
    return None


def _block_has_linked_text_region(block: dict, regions: list) -> bool:
    block_id = block.get("id")
    region_id = block.get("region_id")
    grouped_block_ids = {str(item) for item in block.get("grouped_block_ids", [])}
    if block_id is None:
        block_id = ""
    for region in regions:
        current_region_id = getattr(region, "id", None)
        if current_region_id is None and isinstance(region, dict):
            current_region_id = region.get("id")
        if region_id is not None and str(region_id) == str(current_region_id):
            return True

        linked_block_ids = getattr(region, "linked_block_ids", None)
        if linked_block_ids is None and isinstance(region, dict):
            linked_block_ids = region.get("linked_block_ids")
        if linked_block_ids and str(block_id) in {str(item) for item in linked_block_ids}:
            return True
        if linked_block_ids and grouped_block_ids.intersection({str(item) for item in linked_block_ids}):
            return True
    return False


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


def _block_bbox(block: dict) -> tuple[float, float, float, float] | None:
    bbox = block.get("bbox")
    if isinstance(bbox, dict):
        if {"x", "y", "width", "height"}.issubset(bbox):
            x = float(bbox["x"])
            y = float(bbox["y"])
            return (x, y, x + float(bbox["width"]), y + float(bbox["height"]))
        points = bbox.get("points")
        if points:
            return _points_bbox(points)
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
        return (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
    points = block.get("polygon")
    if points:
        return _points_bbox(points)
    return None


def _points_bbox(points: list) -> tuple[float, float, float, float] | None:
    try:
        xs = [float(point[0]) for point in points]
        ys = [float(point[1]) for point in points]
    except (TypeError, ValueError, IndexError):
        return None
    if not xs or not ys:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


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

import logging
import re
import shutil
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from PIL import Image

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
from app.services.mode_service import decide_image_mode, export_mode_debug_json
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
from app.services.small_text_service import (
    classify_complex_small_text_blocks,
    export_small_text_debug_json,
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
    ocr_result = _with_image_size_from_file(ocr_result, input_path)
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
    translation_input = _with_ui_screen_guards(translation_input, regions=regions)
    skipped_text_group_candidates: list[dict] = []
    text_groups = []
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
    translatable_input = _with_translatable_blocks_only(translation_input)
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
        ocr_result=translatable_input,
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
        mode_decision = decide_image_mode(
            layout_blocks=translation_input.get("blocks", []),
            render_fit_records=render_fit_records,
            text_groups=text_groups,
            translation_result=translation_result,
            regions=regions,
        )
        export_mode_debug_json(
            mode_decision=mode_decision,
            output_path=settings.debug_dir / "layout" / f"{job_id}_mode.json",
            job_id=job_id,
        )
        small_text_payload = classify_complex_small_text_blocks(
            sample_mode=mode_decision.get("mode"),
            layout_blocks=translation_input.get("blocks", []),
            render_fit_records=render_fit_records,
        )
        export_small_text_debug_json(
            payload=small_text_payload,
            output_path=settings.debug_dir / "layout" / f"{job_id}_small_text.json",
            job_id=job_id,
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
    can_translate = block.get("can_translate", skipped_reason is None)
    can_mask = block.get("can_mask", skipped_reason is None)
    can_inpaint = block.get("can_inpaint", can_mask)
    can_render = block.get("can_render", skipped_reason is None)
    can_group = block.get("can_group", skipped_reason is None)
    return {
        **block,
        "block_role": block.get("block_role") or _default_block_role(block),
        "ui_screen_mode": bool(block.get("ui_screen_mode")),
        "ui_like": bool(block.get("ui_like")),
        "can_translate": bool(can_translate),
        "can_mask": bool(can_mask),
        "can_inpaint": bool(can_inpaint),
        "can_render": bool(can_render),
        "can_group": bool(can_group),
        "can_render_inline": bool(can_render) and skipped_reason is None,
        "skipped_reason": skipped_reason,
    }


def _renderable_skip_reason(block: dict) -> str | None:
    if block.get("can_render") is False:
        return (
            block.get("skipped_reason")
            or block.get("render_skip_reason")
            or block.get("image_processing_skip_reason")
            or "render_inline_disabled"
        )
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


def _with_translatable_blocks_only(ocr_result: dict) -> dict:
    return {
        **ocr_result,
        "blocks": [
            block
            for block in ocr_result.get("blocks", [])
            if block.get("can_translate") is not False
        ],
    }


def _with_renderable_blocks_only(ocr_result: dict) -> dict:
    return {
        **ocr_result,
        "blocks": [
            block
            for block in ocr_result.get("blocks", [])
            if (
                block.get("can_render_inline") is True
                and block.get("can_mask") is not False
                and block.get("can_inpaint") is not False
                and block.get("can_render") is not False
            )
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


def _with_ui_screen_guards(ocr_result: dict, regions: list | None = None) -> dict:
    image_size = _ocr_image_size(ocr_result)
    if image_size is None:
        return {
            **ocr_result,
            "blocks": [_with_default_decision_fields(block, ui_screen_mode=False) for block in ocr_result.get("blocks", [])],
        }

    blocks = ocr_result.get("blocks", [])
    ui_screen_mode = _is_ui_screen(blocks=blocks, image_size=image_size, regions=regions or [])
    return {
        **ocr_result,
        "blocks": [
            _with_ui_block_decision(
                block=block,
                image_size=image_size,
                ui_screen_mode=ui_screen_mode,
                regions=regions or [],
            )
            for block in blocks
        ],
        "raw": {
            **(ocr_result.get("raw") or {}),
            "ui_screen_mode": ui_screen_mode,
        },
    }


def _with_ui_block_decision(
    block: dict,
    image_size: tuple[int, int],
    ui_screen_mode: bool,
    regions: list,
) -> dict:
    if not ui_screen_mode or block.get("is_text_group") or _block_has_manga_region(block, regions):
        return _with_default_decision_fields(block, ui_screen_mode=ui_screen_mode)

    role = _ui_block_role(block, image_size)
    if role is None:
        return _with_default_decision_fields(block, ui_screen_mode=ui_screen_mode)

    return {
        **block,
        "block_role": role,
        "ui_screen_mode": ui_screen_mode,
        "ui_like": True,
        "can_translate": False,
        "can_mask": False,
        "can_inpaint": False,
        "can_render": False,
        "can_group": False,
        "can_render_inline": False,
        "skipped_reason": role,
        "image_processing_skip_reason": role,
        "render_skip_reason": role,
    }


def _with_default_decision_fields(block: dict, ui_screen_mode: bool) -> dict:
    return {
        **block,
        "block_role": block.get("block_role") or _default_block_role(block),
        "ui_screen_mode": ui_screen_mode,
        "ui_like": bool(block.get("ui_like")),
        "can_translate": block.get("can_translate", block.get("block_type") not in {"ignored", "logo"}),
        "can_mask": block.get("can_mask", True),
        "can_inpaint": block.get("can_inpaint", True),
        "can_render": block.get("can_render", True),
        "can_group": block.get("can_group", True),
    }


def _default_block_role(block: dict) -> str:
    if block.get("is_text_group"):
        return "manga_text_group"
    block_type = str(block.get("block_type") or "")
    if block_type in {"button", "logo", "ignored"}:
        return block_type
    return "text"


def _is_ui_screen(blocks: list[dict], image_size: tuple[int, int], regions: list) -> bool:
    if len(blocks) < 6:
        return False
    if _has_manga_regions(regions):
        return False

    ui_role_count = 0
    edge_small_count = 0
    for block in blocks:
        if _ui_block_role(block, image_size) is not None:
            ui_role_count += 1
        if _is_edge_small_block(block, image_size):
            edge_small_count += 1

    block_count = max(1, len(blocks))
    return (
        ui_role_count >= 5
        and ui_role_count / block_count >= 0.5
        and edge_small_count >= 4
    )


def _has_manga_regions(regions: list) -> bool:
    for region in regions:
        region_type = str(_region_value(region, "region_type") or "unknown")
        if region_type == "bubble":
            return True
        if region_type in {"caption_box", "text_box"}:
            bbox = _region_value(region, "bbox")
            if bbox is None:
                continue
            x1, y1, x2, y2 = _normalize_bbox_tuple(bbox)
            width = max(0.0, x2 - x1)
            height = max(0.0, y2 - y1)
            if height >= width * 1.25 or (width * height) >= 30000:
                return True
    return False


def _block_has_manga_region(block: dict, regions: list) -> bool:
    region_id = block.get("region_id")
    linked_region_ids = {str(item) for item in block.get("linked_region_ids", [])}
    for region in regions:
        current_region_id = _region_value(region, "id")
        region_type = str(_region_value(region, "region_type") or "unknown")
        if region_type not in {"bubble", "caption_box", "text_box"}:
            continue
        if region_type == "text_box":
            bbox = _region_value(region, "bbox")
            if bbox is not None:
                x1, y1, x2, y2 = _normalize_bbox_tuple(bbox)
                width = max(0.0, x2 - x1)
                height = max(0.0, y2 - y1)
                if height < width * 1.25 and (width * height) < 30000:
                    continue
        if region_id is not None and str(region_id) == str(current_region_id):
            return True
        if current_region_id is not None and str(current_region_id) in linked_region_ids:
            return True
    return False


def _ui_block_role(block: dict, image_size: tuple[int, int]) -> str | None:
    block_type = str(block.get("block_type") or "normal")
    if block_type == "ignored":
        return None

    text = _clean_block_text(block)
    if not text:
        return None
    if len(text) > 32:
        return None
    if block_type == "button":
        return "ui_button_label"

    bbox = _block_bbox(block)
    if bbox is None:
        return None
    image_width, image_height = image_size
    x1, y1, x2, y2 = bbox
    center_y = (y1 + y2) / 2.0
    width = max(0.0, x2 - x1)
    height = max(0.0, y2 - y1)
    top_band = center_y <= image_height * 0.24
    bottom_band = center_y >= image_height * 0.76

    if _is_resource_number(text):
        return "ui_resource_number"
    if top_band and _is_player_or_level_text(text):
        return "ui_player_name"
    if _is_status_number(text):
        return "ui_status_number"
    if bottom_band and _is_short_label_text(text):
        return "ui_nav_label"
    if _is_button_label_text(text):
        return "ui_button_label"
    if (
        _is_short_label_text(text)
        and width <= image_width * 0.22
        and height <= image_height * 0.18
    ):
        return "ui_icon_label"
    if _is_short_label_text(text) and (top_band or bottom_band):
        return "ui_short_label"
    return None


def _is_edge_small_block(block: dict, image_size: tuple[int, int]) -> bool:
    bbox = _block_bbox(block)
    if bbox is None:
        return False
    image_width, image_height = image_size
    x1, y1, x2, y2 = bbox
    width = max(0.0, x2 - x1)
    height = max(0.0, y2 - y1)
    center_y = (y1 + y2) / 2.0
    near_edge = center_y <= image_height * 0.28 or center_y >= image_height * 0.72
    return near_edge and width <= image_width * 0.35 and height <= image_height * 0.2


def _clean_block_text(block: dict) -> str:
    return " ".join(str(block.get("text") or "").split())


def _is_resource_number(text: str) -> bool:
    clean = text.replace(" ", "")
    return bool(
        re.fullmatch(r"(?:\d{1,3}(?:,\d{3})+|\d+/\d+)(?:\d{1,3}(?:,\d{3})+|\d+/\d+)*", clean)
    )


def _is_status_number(text: str) -> bool:
    return bool(re.fullmatch(r"(?:LV\.?\s*)?\d+(?:[:.%]\d+)?%?", text.strip(), flags=re.IGNORECASE))


def _is_player_or_level_text(text: str) -> bool:
    clean = text.strip()
    if re.fullmatch(r"LV\.?\s*\d+", clean, flags=re.IGNORECASE):
        return True
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{2,15}", clean))


def _is_short_label_text(text: str) -> bool:
    clean = text.strip()
    return 1 <= len(clean) <= 12 and "\n" not in clean


def _is_button_label_text(text: str) -> bool:
    return text.strip().lower() in {"start", "ok", "go", "yes", "no", "play", "claim"}


def _region_value(region, key: str):
    if isinstance(region, dict):
        return region.get(key)
    return getattr(region, key, None)


def _normalize_bbox_tuple(bbox) -> tuple[float, float, float, float]:
    if isinstance(bbox, dict):
        x = float(bbox.get("x") or 0)
        y = float(bbox.get("y") or 0)
        return (x, y, x + float(bbox.get("width") or 0), y + float(bbox.get("height") or 0))
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
        return (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
    return (0.0, 0.0, 0.0, 0.0)


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


def _with_image_size_from_file(ocr_result: dict, image_path: Path) -> dict:
    if _ocr_image_size(ocr_result) is not None:
        return ocr_result
    try:
        with Image.open(image_path) as image:
            width, height = image.size
    except Exception:
        return ocr_result
    return {
        **ocr_result,
        "image_width": width,
        "image_height": height,
    }


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

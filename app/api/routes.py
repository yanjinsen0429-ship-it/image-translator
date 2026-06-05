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
from app.services.ocr_service import create_ocr_result
from app.services.translation_service import create_mock_translation_result

router = APIRouter()


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
    translation_result = create_mock_translation_result(
        job_id=job_id,
        ocr_result=ocr_result,
    )

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

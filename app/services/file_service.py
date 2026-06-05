import re
import uuid
from pathlib import Path

from app.core.config import settings


class UploadError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def create_job_id() -> str:
    return uuid.uuid4().hex


def sanitize_filename(filename: str) -> str:
    raw_name = (filename or "upload").replace("\\", "/").split("/")[-1]
    name = Path(raw_name).name
    suffix = Path(name).suffix.lower()
    stem = Path(name).stem
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
    if not safe_stem:
        safe_stem = "upload"
    return f"{safe_stem}{suffix}"


def is_allowed_image(filename: str) -> bool:
    return Path(filename).suffix.lower() in settings.allowed_extensions


def save_bytes_to_uploads(
    content: bytes,
    original_filename: str,
    upload_dir: Path,
    job_id: str,
) -> Path:
    if not content:
        raise UploadError("UPLOAD_EMPTY_FILE", "请选择一张非空图片。")

    safe_name = sanitize_filename(original_filename)
    if not is_allowed_image(safe_name):
        raise UploadError(
            "UPLOAD_INVALID_TYPE",
            "只支持 png、jpg、jpeg、webp 格式的图片。",
        )

    if len(content) > settings.max_upload_bytes:
        raise UploadError(
            "UPLOAD_TOO_LARGE",
            "图片过大，请上传 10MB 以内的图片。",
        )

    upload_dir.mkdir(parents=True, exist_ok=True)
    saved_path = upload_dir / f"{job_id}_{safe_name}"
    saved_path.write_bytes(content)
    return saved_path


def storage_url_for(path: Path) -> str:
    relative_path = path.resolve().relative_to(settings.storage_dir.resolve())
    return f"/storage/{relative_path.as_posix()}"

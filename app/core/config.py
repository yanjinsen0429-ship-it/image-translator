import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    return float(value)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    project_root: Path = Path(__file__).resolve().parents[2]
    frontend_dir: Path = project_root / "frontend"
    frontend_static_dir: Path = frontend_dir / "src"
    storage_dir: Path = project_root / "storage"
    upload_dir: Path = storage_dir / "uploads"
    output_dir: Path = storage_dir / "outputs"
    debug_dir: Path = storage_dir / "debug"
    allowed_extensions: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".webp")
    max_upload_bytes: int = 10 * 1024 * 1024
    ocr_engine: str = field(default_factory=lambda: os.getenv("OCR_ENGINE", "paddle"))
    ocr_language: str = field(default_factory=lambda: os.getenv("OCR_LANGUAGE", "ch"))
    ocr_min_confidence: float = field(
        default_factory=lambda: _env_float("OCR_MIN_CONFIDENCE", 0.5)
    )
    ocr_fallback_to_mock: bool = field(
        default_factory=lambda: _env_bool("OCR_FALLBACK_TO_MOCK", True)
    )
    translation_provider: str = field(
        default_factory=lambda: os.getenv("TRANSLATION_PROVIDER", "mock")
    )
    translation_target_language: str = field(
        default_factory=lambda: os.getenv("TRANSLATION_TARGET_LANGUAGE", "zh-CN")
    )


settings = Settings()


def ensure_runtime_directories() -> None:
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    settings.debug_dir.mkdir(parents=True, exist_ok=True)

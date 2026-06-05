import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_environment_file(project_root: Path = PROJECT_ROOT) -> None:
    dotenv_path = project_root / ".env"
    if not dotenv_path.exists():
        return

    try:
        from dotenv import load_dotenv
    except ImportError:
        _load_dotenv_fallback(dotenv_path)
        return

    load_dotenv(dotenv_path=dotenv_path, override=False)


def _load_dotenv_fallback(dotenv_path: Path) -> None:
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


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


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    return int(value)


@dataclass(frozen=True)
class Settings:
    project_root: Path = PROJECT_ROOT
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
    deepseek_api_key: str = field(
        default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", "")
    )
    deepseek_base_url: str = field(
        default_factory=lambda: os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    )
    deepseek_model: str = field(
        default_factory=lambda: os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    )
    deepseek_timeout_seconds: int = field(
        default_factory=lambda: _env_int("DEEPSEEK_TIMEOUT_SECONDS", 30)
    )


load_environment_file()
settings = Settings()


def ensure_runtime_directories() -> None:
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    settings.debug_dir.mkdir(parents=True, exist_ok=True)

from dataclasses import dataclass
from pathlib import Path


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


settings = Settings()


def ensure_runtime_directories() -> None:
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    settings.debug_dir.mkdir(parents=True, exist_ok=True)

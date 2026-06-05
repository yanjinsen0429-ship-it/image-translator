import shutil
from pathlib import Path


def create_mock_output_image(input_path: Path, output_dir: Path, job_id: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = input_path.suffix.lower() or ".png"
    output_path = output_dir / f"{job_id}_mock_output{suffix}"
    shutil.copyfile(input_path, output_path)
    return output_path

from __future__ import annotations

import argparse
import html
import json
import mimetypes
import os
import shutil
import sys
import webbrowser
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple

from PIL import Image

try:
    import requests
except ImportError:  # pragma: no cover - exercised by CLI users without requests
    requests = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SAMPLES_DIR = PROJECT_ROOT / "tests" / "visual_samples"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "storage" / "visual_regression" / "latest"
DEFAULT_API_BASE_URL = os.getenv("IMAGE_TRANSLATOR_API_BASE_URL", "http://127.0.0.1:8000")
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
SINGLE_RECORD_ALLOWED = {"04_clean_single_bubble"}


class Sample(NamedTuple):
    path: Path
    sample_name: str


class ApiResponse(NamedTuple):
    http_status: int | None
    payload: Any
    error_message: str | None = None
    error_code: str | None = None


class RequestsApiClient:
    def __init__(
        self,
        api_base_url: str,
        read_timeout_seconds: float = 180,
        connect_timeout_seconds: float = 5,
    ):
        if requests is None:
            raise RuntimeError("The requests package is required for real API visual regression runs.")
        self.api_base_url = api_base_url.rstrip("/")
        self.read_timeout_seconds = read_timeout_seconds
        self.connect_timeout_seconds = connect_timeout_seconds

    def health(self) -> dict[str, Any]:
        try:
            response = requests.get(
                f"{self.api_base_url}/api/health",
                timeout=(self.connect_timeout_seconds, min(10, self.read_timeout_seconds)),
            )
        except requests.Timeout as exc:
            return {"ok": False, "error_code": "request_timeout", "error_message": str(exc)}
        except requests.RequestException as exc:
            return {"ok": False, "error_code": "service_unavailable", "error_message": str(exc)}
        return {
            "ok": response.status_code == 200,
            "http_status": response.status_code,
            "body": _safe_response_json(response),
        }

    def translate(self, sample: Sample) -> ApiResponse:
        mime = mime_type_for(sample.path)
        upload_name = f"{sample.sample_name}{effective_suffix(sample.path)}"
        try:
            with sample.path.open("rb") as handle:
                response = requests.post(
                    f"{self.api_base_url}/api/images/translate",
                    files={"file": (upload_name, handle, mime)},
                    timeout=(self.connect_timeout_seconds, self.read_timeout_seconds),
                )
        except requests.Timeout as exc:
            return ApiResponse(
                http_status=None,
                payload=None,
                error_message=str(exc),
                error_code="request_timeout",
            )
        except requests.RequestException as exc:
            return ApiResponse(
                http_status=None,
                payload=None,
                error_message=str(exc),
                error_code="service_unavailable",
            )
        return ApiResponse(
            http_status=response.status_code,
            payload=_safe_response_json(response),
            error_message=None if response.status_code == 200 else response.text,
        )


class UnavailableApiClient:
    def __init__(self, message: str):
        self.message = message

    def health(self) -> dict[str, Any]:
        return {"ok": False, "error_message": self.message}

    def translate(self, sample: Sample) -> ApiResponse:
        return ApiResponse(
            http_status=None,
            payload=None,
            error_message=self.message,
            error_code="service_unavailable",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Image-Translator visual regression samples.")
    parser.add_argument("--samples", default=str(DEFAULT_SAMPLES_DIR), help="Sample image directory.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_DIR), help="Report output directory.")
    parser.add_argument("--api-base-url", default=DEFAULT_API_BASE_URL, help="Local API base URL.")
    parser.add_argument("--filter", default=None, help="Only process samples whose sample_name contains KEYWORD.")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N samples after filtering.")
    parser.add_argument(
        "--timeout",
        type=float,
        default=180,
        help="Per-sample read timeout in seconds. Connect timeout is fixed at 5 seconds.",
    )
    parser.add_argument("--open", action="store_true", help="Open the generated HTML report.")
    args = parser.parse_args()

    summary = run_visual_regression(
        samples_dir=Path(args.samples),
        output_dir=Path(args.output),
        api_client=RequestsApiClient(args.api_base_url, read_timeout_seconds=args.timeout),
        open_report=args.open,
        sample_filter=args.filter,
        limit=args.limit,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if summary.get("fail_count", 0) else 0


def run_visual_regression(
    samples_dir: Path,
    output_dir: Path,
    api_client: Any | None = None,
    open_report: bool = False,
    sample_filter: str | None = None,
    limit: int | None = None,
    progress=print,
) -> dict[str, Any]:
    samples_dir = Path(samples_dir)
    output_dir = Path(output_dir)
    api_client = api_client or RequestsApiClient(DEFAULT_API_BASE_URL)
    samples = scan_samples(samples_dir)
    samples = select_samples(samples, sample_filter=sample_filter, limit=limit)

    reset_output_dir(output_dir)
    service_status = {"ok": None, "message": "not checked because there are no samples"}
    results: list[dict[str, Any]] = []
    if samples:
        service_status = api_client.health()
        for index, sample in enumerate(samples, start=1):
            progress(f"[{index}/{len(samples)}] processing {sample.sample_name}...")
            sample_dir = output_dir / sample.sample_name
            sample_dir.mkdir(parents=True, exist_ok=True)
            save_png(sample.path, sample_dir / "input.png")
            if not service_status.get("ok"):
                result = build_service_unavailable_result(sample, sample_dir, service_status)
                results.append(result)
                log_sample_result(progress, index, len(samples), result)
                continue
            result = run_sample(api_client, sample, sample_dir)
            results.append(result)
            log_sample_result(progress, index, len(samples), result)

    summary = build_summary(output_dir=output_dir, samples=results, service_status=service_status)
    write_reports(summary, output_dir)
    if open_report:
        webbrowser.open((output_dir / "index.html").resolve().as_uri())
    return summary


def select_samples(
    samples: list[Sample],
    sample_filter: str | None = None,
    limit: int | None = None,
) -> list[Sample]:
    selected = samples
    if sample_filter:
        keyword = sample_filter.lower()
        selected = [sample for sample in selected if keyword in sample.sample_name.lower()]
    if limit is not None:
        selected = selected[: max(0, limit)]
    return selected


def scan_samples(samples_dir: Path) -> list[Sample]:
    samples_dir = Path(samples_dir)
    if not samples_dir.exists() or not samples_dir.is_dir():
        return []
    samples = [
        Sample(path=path, sample_name=sample_name_for(path))
        for path in samples_dir.iterdir()
        if path.is_file() and effective_suffix(path) in ALLOWED_EXTENSIONS
    ]
    return sorted(samples, key=lambda sample: sample.sample_name)


def effective_suffix(path: Path) -> str:
    name = path.name.lower()
    suffix = ""
    while True:
        current = Path(name).suffix
        if current not in ALLOWED_EXTENSIONS:
            break
        suffix = current
        name = name[: -len(current)]
    return suffix or path.suffix.lower()


def sample_name_for(path: Path) -> str:
    name = path.name
    changed = True
    while changed:
        changed = False
        lower = name.lower()
        for suffix in ALLOWED_EXTENSIONS:
            if lower.endswith(suffix):
                name = name[: -len(suffix)]
                changed = True
                break
    return name


def reset_output_dir(output_dir: Path) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def run_sample(api_client: Any, sample: Sample, sample_dir: Path) -> dict[str, Any]:
    response = api_client.translate(sample)
    if response.http_status != 200 or not isinstance(response.payload, dict):
        return build_sample_result(
            sample=sample,
            payload=response.payload if isinstance(response.payload, dict) else {},
            http_status=response.http_status,
            sample_dir=sample_dir,
            copied_paths={},
            records=[],
            missing_debug_files=[],
            error_message=response.error_message or _payload_error(response.payload),
            extra_fail_reasons=[response.error_code] if response.error_code else None,
        )

    payload = response.payload
    job_id = payload.get("job_id")
    copied_paths, missing_debug_files = collect_artifacts(payload=payload, job_id=job_id, sample_dir=sample_dir)
    records = load_render_fit_records(sample_dir / "render_fit.json")
    text_group_metrics = collect_text_group_metrics(load_json_payload(sample_dir / "text_groups.json"))
    mode_decision = load_json_payload(sample_dir / "mode.json")
    return build_sample_result(
        sample=sample,
        payload=payload,
        http_status=response.http_status,
        sample_dir=sample_dir,
        copied_paths=copied_paths,
        records=records,
        missing_debug_files=missing_debug_files,
        text_group_metrics=text_group_metrics,
        mode_decision=mode_decision,
    )


def build_service_unavailable_result(
    sample: Sample,
    sample_dir: Path,
    service_status: dict[str, Any],
) -> dict[str, Any]:
    return build_sample_result(
        sample=sample,
        payload={},
        http_status=None,
        sample_dir=sample_dir,
        copied_paths={},
        records=[],
        missing_debug_files=[],
        error_message=service_status.get("error_message") or json.dumps(service_status, ensure_ascii=False),
        extra_fail_reasons=[service_status.get("error_code") or "service_unavailable"],
    )


def collect_artifacts(
    payload: dict[str, Any],
    job_id: str | None,
    sample_dir: Path,
) -> tuple[dict[str, str], list[str]]:
    copied: dict[str, str] = {}
    missing: list[str] = []
    output_path = storage_url_to_path(payload.get("output_file"))
    if output_path and output_path.exists():
        save_png(output_path, sample_dir / "output.png")
        copied["output"] = rel(sample_dir / "output.png")
    else:
        missing.append("output.png")

    if not job_id:
        missing.append("job_id")
        return copied, missing

    layout_dir = PROJECT_ROOT / "storage" / "debug" / "layout"
    debug_files = {
        "render_fit": layout_dir / f"{job_id}_render_fit.json",
        "render_fit_overlay": layout_dir / f"{job_id}_render_fit_overlay.png",
        "regions": layout_dir / f"{job_id}_regions.json",
        "region_overlay": layout_dir / f"{job_id}_region_overlay.png",
        "layout_blocks": layout_dir / f"{job_id}_layout_blocks.json",
        "layout_overlay": layout_dir / f"{job_id}_layout_overlay.png",
        "text_groups": layout_dir / f"{job_id}_text_groups.json",
        "text_groups_overlay": layout_dir / f"{job_id}_text_groups_overlay.png",
        "mode": layout_dir / f"{job_id}_mode.json",
        "mask": PROJECT_ROOT / "storage" / "debug" / "mask" / f"{job_id}_mask.png",
        "inpainted": PROJECT_ROOT / "storage" / "debug" / "inpainted" / f"{job_id}_inpainted.png",
        "rendered": PROJECT_ROOT / "storage" / "debug" / "rendered" / f"{job_id}_rendered.png",
    }
    destinations = {
        "render_fit": sample_dir / "render_fit.json",
        "render_fit_overlay": sample_dir / "render_fit_overlay.png",
        "regions": sample_dir / "regions.json",
        "region_overlay": sample_dir / "region_overlay.png",
        "layout_blocks": sample_dir / "layout_blocks.json",
        "layout_overlay": sample_dir / "layout_overlay.png",
        "text_groups": sample_dir / "text_groups.json",
        "text_groups_overlay": sample_dir / "text_groups_overlay.png",
        "mode": sample_dir / "mode.json",
        "mask": sample_dir / "mask.png",
        "inpainted": sample_dir / "inpainted.png",
        "rendered": sample_dir / "rendered.png",
    }
    for key, source in debug_files.items():
        destination = destinations[key]
        if source.exists():
            shutil.copy2(source, destination)
            copied[key] = rel(destination)
        else:
            missing.append(destination.name)
    return copied, missing


def build_sample_result(
    sample: Sample,
    payload: dict[str, Any],
    http_status: int | None,
    sample_dir: Path,
    copied_paths: dict[str, str],
    records: list[dict[str, Any]],
    missing_debug_files: list[str],
    error_message: str | None = None,
    extra_fail_reasons: list[str] | None = None,
    text_group_metrics: dict[str, Any] | None = None,
    mode_decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metrics, skipped_reason_counts = collect_metrics(records)
    metrics.update(text_group_metrics or empty_text_group_metrics())
    used_mock = used_mock_or_fallback_ocr(payload)
    translation_items = (payload.get("translation_result") or {}).get("items", [])
    suspicious_single = (
        http_status == 200
        and "render_fit" in copied_paths
        and metrics["record_count"] <= 1
        and sample.sample_name not in SINGLE_RECORD_ALLOWED
    )
    result = {
        "sample_name": sample.sample_name,
        "input_source": rel(sample.path) if sample.path.is_absolute() or sample.path.exists() else str(sample.path),
        "input": rel(sample_dir / "input.png") if (sample_dir / "input.png").exists() else None,
        "output": copied_paths.get("output"),
        "status": "PASS",
        "fail_reasons": list(extra_fail_reasons or []),
        "warn_reasons": [],
        "paths": copied_paths,
        "http_status": http_status,
        "job_id": payload.get("job_id"),
        "record_count": metrics["record_count"],
        "translation_item_count": len(translation_items),
        "used_mock_or_fallback_ocr": used_mock,
        "suspicious_single_record": suspicious_single,
        "metrics": metrics,
        "skipped_reason_counts": skipped_reason_counts,
        "mode": (mode_decision or {}).get("mode"),
        "mode_decision": mode_decision or {},
        "missing_debug_files": missing_debug_files,
        "error_message": error_message,
    }
    apply_fail_rules(result, records)
    apply_warn_rules(result, records)
    finalize_status(result)
    return result


def collect_metrics(records: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, int]]:
    skipped = [record for record in records if record.get("can_render_inline") is False]
    inline = [record for record in records if record.get("can_render_inline") is not False]
    skipped_reason_counts = Counter(
        str(record.get("skipped_reason") or record.get("fallback_reason") or "")
        for record in skipped
    )
    metrics = {
        "record_count": len(records),
        "inline_render_count": len(inline),
        "skipped_count": len(skipped),
        "overflow_count": sum(1 for record in records if record.get("possible_overflow")),
        "font_too_small_count": sum(1 for record in inline if number(record.get("selected_font_size"), 999) < 10),
        "complex_background_inline_count": sum(
            1 for record in inline if record.get("is_complex_background") and not record.get("is_ui_like_label")
        ),
        "noise_like_inline_count": sum(1 for record in inline if is_noise_like_inline(record)),
        "skipped_without_reason_count": sum(
            1 for record in skipped if not (record.get("skipped_reason") or record.get("fallback_reason"))
        ),
    }
    return metrics, dict(skipped_reason_counts)


def collect_text_group_metrics(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return empty_text_group_metrics()
    groups = list(payload.get("groups") or [])
    group_count = int(payload.get("group_count") or len(groups))
    grouped_block_count = sum(len(group.get("grouped_block_ids") or []) for group in groups)
    vertical_group_count = sum(1 for group in groups if group.get("text_direction") == "vertical")
    return {
        "group_count": group_count,
        "grouped_block_count": grouped_block_count,
        "vertical_group_count": vertical_group_count,
        "average_blocks_per_group": round(grouped_block_count / group_count, 3) if group_count else 0,
    }


def empty_text_group_metrics() -> dict[str, Any]:
    return {
        "group_count": 0,
        "grouped_block_count": 0,
        "vertical_group_count": 0,
        "average_blocks_per_group": 0,
    }


def apply_fail_rules(result: dict[str, Any], records: list[dict[str, Any]]) -> None:
    if result.get("http_status") != 200:
        add_reason(result, "fail_reasons", "http_error")
    if not result.get("output"):
        add_reason(result, "fail_reasons", "missing_output")
    if "render_fit.json" in result.get("missing_debug_files", []):
        add_reason(result, "fail_reasons", "missing_render_fit_json")
    if result.get("used_mock_or_fallback_ocr"):
        add_reason(result, "fail_reasons", "ocr_fallback_or_mock_ocr_used")
    if result.get("suspicious_single_record"):
        add_reason(result, "fail_reasons", "suspicious_single_record")
    inline = [record for record in records if record.get("can_render_inline") is not False]
    skipped = [record for record in records if record.get("can_render_inline") is False]
    if any(is_bad_complex_inline(record) for record in inline):
        add_reason(result, "fail_reasons", "complex_background_dense_text_inline")
    if any(is_short_large_bbox_inline(record) for record in inline):
        add_reason(result, "fail_reasons", "short_text_large_bbox_inline")
    if any(record.get("enters_render") for record in skipped):
        add_reason(result, "fail_reasons", "skipped_record_enters_render")
    if any(record.get("enters_image_processing") for record in skipped):
        add_reason(result, "fail_reasons", "skipped_record_enters_image_processing")


def apply_warn_rules(result: dict[str, Any], records: list[dict[str, Any]]) -> None:
    metrics = result.get("metrics", {})
    if metrics.get("font_too_small_count"):
        add_reason(result, "warn_reasons", "inline_font_size_below_10")
    if metrics.get("overflow_count"):
        add_reason(result, "warn_reasons", "overflow_records_present")
    if metrics.get("skipped_without_reason_count"):
        add_reason(result, "warn_reasons", "skipped_without_reason")
    if metrics.get("noise_like_inline_count"):
        add_reason(result, "warn_reasons", "noise_like_inline")
    if metrics.get("record_count", 0) >= 3 and metrics.get("inline_render_count") == 0:
        add_reason(result, "warn_reasons", "inline_render_count_zero")
    if metrics.get("record_count", 0) >= 10:
        skipped_ratio = metrics.get("skipped_count", 0) / max(1, metrics.get("record_count", 0))
        if skipped_ratio > 0.85:
            add_reason(result, "warn_reasons", "skipped_count_high")
    for missing in result.get("missing_debug_files", []):
        if missing != "render_fit.json" and missing != "output.png":
            add_reason(result, "warn_reasons", f"missing_debug_file:{missing}")


def finalize_status(result: dict[str, Any]) -> None:
    if result["fail_reasons"]:
        result["status"] = "FAIL"
    elif result["warn_reasons"]:
        result["status"] = "WARN"
    else:
        result["status"] = "PASS"


def log_sample_result(progress, index: int, total: int, result: dict[str, Any]) -> None:
    reasons = result.get("fail_reasons") or result.get("warn_reasons") or []
    progress(
        f"[{index}/{total}] {result.get('status')} "
        f"{result.get('sample_name')} reasons={reasons}"
    )


def build_summary(
    output_dir: Path,
    samples: list[dict[str, Any]],
    service_status: dict[str, Any],
) -> dict[str, Any]:
    pass_count = sum(1 for sample in samples if sample["status"] == "PASS")
    warn_count = sum(1 for sample in samples if sample["status"] == "WARN")
    fail_count = sum(1 for sample in samples if sample["status"] == "FAIL")
    return {
        "run_time": datetime.now(timezone.utc).isoformat(),
        "total_samples": len(samples),
        "pass_count": pass_count,
        "warn_count": warn_count,
        "fail_count": fail_count,
        "report_dir": rel(output_dir),
        "service_status": service_status,
        "samples": samples,
    }


def write_reports(summary: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "index.html").write_text(render_html(summary), encoding="utf-8")


def render_html(summary: dict[str, Any]) -> str:
    report_dir = summary_report_dir(summary)
    samples_html = "\n".join(render_sample_html(sample, report_dir) for sample in summary.get("samples", []))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>Image Translator Visual Regression</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #222; }}
    h1 {{ margin: 0 0 8px; }}
    .summary {{ margin-bottom: 20px; line-height: 1.5; }}
    .sample {{ border: 1px solid #ccc; border-left-width: 8px; border-radius: 6px; margin: 18px 0; padding: 16px; }}
    .PASS {{ border-left-color: #2e7d32; }}
    .WARN {{ border-left-color: #f9a825; }}
    .FAIL {{ border-left-color: #c62828; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; align-items: start; }}
    figure {{ margin: 0; }}
    img {{ max-width: 100%; border: 1px solid #ddd; background: #fafafa; }}
    figcaption {{ font-size: 13px; margin-bottom: 4px; color: #555; }}
    pre {{ background: #f5f5f5; padding: 10px; overflow: auto; }}
    code {{ background: #f5f5f5; padding: 2px 4px; }}
  </style>
</head>
<body>
  <h1>Image Translator Visual Regression</h1>
  <div class="summary">
    <div>run_time: <code>{escape(summary.get("run_time"))}</code></div>
    <div>total={summary.get("total_samples", 0)} pass={summary.get("pass_count", 0)} warn={summary.get("warn_count", 0)} fail={summary.get("fail_count", 0)}</div>
  </div>
  {samples_html or "<p>No samples found.</p>"}
</body>
</html>
"""


def render_sample_html(sample: dict[str, Any], report_dir: Path) -> str:
    status = escape(sample.get("status"))
    paths = sample.get("paths", {})
    figures = "".join(
        figure_html(path, caption, report_dir)
        for caption, path in [
            ("input", sample.get("input")),
            ("output", sample.get("output")),
            ("render_fit_overlay", paths.get("render_fit_overlay")),
            ("text_groups_overlay", paths.get("text_groups_overlay")),
            ("region_overlay", paths.get("region_overlay")),
            ("layout_overlay", paths.get("layout_overlay")),
            ("mask", paths.get("mask")),
            ("inpainted", paths.get("inpainted")),
            ("rendered", paths.get("rendered")),
        ]
    )
    metrics = escape(json.dumps(sample.get("metrics", {}), ensure_ascii=False, indent=2))
    skipped = escape(json.dumps(sample.get("skipped_reason_counts", {}), ensure_ascii=False, indent=2))
    mode_decision = escape(json.dumps(sample.get("mode_decision", {}), ensure_ascii=False, indent=2))
    return f"""
<section class="sample {status}">
  <h2>{escape(sample.get("sample_name"))} [{status}]</h2>
  <p>
    job_id=<code>{escape(sample.get("job_id"))}</code>
    http=<code>{escape(sample.get("http_status"))}</code>
    record_count=<code>{escape(sample.get("record_count"))}</code>
    translation_item_count=<code>{escape(sample.get("translation_item_count"))}</code>
    used_mock_or_fallback_ocr=<code>{escape(sample.get("used_mock_or_fallback_ocr"))}</code>
    mode=<code>{escape(sample.get("mode") or "-")}</code>
  </p>
  <p>fail: {escape(', '.join(sample.get("fail_reasons", [])) or "-")}</p>
  <p>warn: {escape(', '.join(sample.get("warn_reasons", [])) or "-")}</p>
  <div class="grid">{figures}</div>
  <h3>Metrics</h3>
  <pre>{metrics}</pre>
  <h3>Skipped Reasons</h3>
  <pre>{skipped}</pre>
  <h3>Mode Decision</h3>
  <pre>{mode_decision}</pre>
</section>
"""


def figure_html(path: str | None, caption: str, report_dir: Path) -> str:
    if not path:
        return f"<figure><figcaption>{escape(caption)} missing</figcaption></figure>"
    source = resolve_report_asset(path)
    if not source.exists():
        return f"<figure><figcaption>{escape(caption)} missing: {escape(Path(path).name)}</figcaption></figure>"
    return f'<figure><figcaption>{escape(caption)}</figcaption><img src="{escape(report_relative_src(source, report_dir))}" alt="{escape(caption)}"></figure>'


def summary_report_dir(summary: dict[str, Any]) -> Path:
    report_dir = Path(str(summary.get("report_dir") or DEFAULT_OUTPUT_DIR))
    if report_dir.is_absolute():
        return report_dir
    return PROJECT_ROOT / report_dir


def resolve_report_asset(path: str | Path) -> Path:
    asset = Path(path)
    if asset.is_absolute():
        return asset
    return PROJECT_ROOT / asset


def report_relative_src(path: Path, report_dir: Path) -> str:
    try:
        return path.resolve().relative_to(report_dir.resolve()).as_posix()
    except ValueError:
        return path.as_posix().replace("\\", "/")


def load_render_fit_records(path: Path) -> list[dict[str, Any]]:
    payload = load_json_payload(path)
    return list(payload.get("records", []))


def load_json_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_png(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        image.convert("RGBA").save(destination)


def storage_url_to_path(url: str | None) -> Path | None:
    if not url or not str(url).startswith("/storage/"):
        return None
    return PROJECT_ROOT / str(url).lstrip("/").replace("/", "\\")


def mime_type_for(path: Path) -> str:
    suffix = effective_suffix(path)
    known = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    return known.get(suffix) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def used_mock_or_fallback_ocr(payload: dict[str, Any]) -> bool:
    ocr_result = payload.get("ocr_result") or {}
    warnings = ocr_result.get("warnings") or []
    warning_text = json.dumps(warnings, ensure_ascii=False).lower()
    if "mock" in warning_text or "fallback" in warning_text:
        return True
    for block in ocr_result.get("blocks", []):
        text = str(block.get("text") or "").lower()
        if "mock ocr" in text or "mock" in text:
            return True
    return False


def is_bad_complex_inline(record: dict[str, Any]) -> bool:
    if not record.get("is_complex_background") or record.get("is_ui_like_label"):
        return False
    return (
        number(record.get("selected_font_size"), 0) < 14
        or number(record.get("text_area_ratio"), 0) < 0.18
        or number(record.get("line_count"), 0) > 4
    )


def is_short_large_bbox_inline(record: dict[str, Any]) -> bool:
    text_length = number(record.get("translated_text_length"), None)
    if text_length is None:
        text_length = number(record.get("original_text_length"), 0)
    return text_length <= 2 and number(record.get("bbox_area_ratio"), 0) >= 0.08


def is_noise_like_inline(record: dict[str, Any]) -> bool:
    if record.get("is_noise_like_text"):
        return True
    text = str(record.get("original_text") or "").strip()
    return len(text) == 1 and (text.isdigit() or not text.isalnum())


def number(value: Any, default: float | None) -> float | None:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def add_reason(result: dict[str, Any], key: str, reason: str) -> None:
    if reason not in result[key]:
        result[key].append(reason)


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def escape(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _safe_response_json(response: Any) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def _payload_error(payload: Any) -> str | None:
    if payload is None:
        return None
    if isinstance(payload, str):
        return payload
    return json.dumps(payload, ensure_ascii=False)


if __name__ == "__main__":
    raise SystemExit(main())

# v0.7 Visual Quality Status

## Baseline

v0.7 starts from the sealed v0.6 baseline:

- Commit: `9c195c8 docs: finalize v0.6 release verification`
- Tag: `v0.6`
- Branch: `feature/v0.7-visual-quality`
- OCR runtime remains pinned:
  - `paddleocr==3.2.0`
  - `paddlepaddle==3.1.1`
  - `paddlex==3.2.1`

Do not upgrade PaddleOCR / PaddlePaddle / PaddleX during v0.7 visual quality work unless there is a separate environment validation step.

## Step 1A Branch and Plan

### Goal

Start v0.7 on a dedicated branch, read the v0.6 release documentation, and define the v0.7 work split.

### Result

- Branch `feature/v0.7-visual-quality` is used for v0.7 work.
- v0.6 release documentation remains the source of truth for the sealed baseline.
- No code, docs, tests, dependencies, samples, or visual regression outputs were changed in Step 1A.

### Planned v0.7 Focus

- Complex small text mode.
- Noisy inline filtering.
- Overflow quality improvement.
- Initial image mode system design.
- Formal webp sample workflow only after conversion / compatibility behavior is clear.

## Step 1B Baseline Inventory

### Goal

Inventory the existing v0.6 visual regression artifacts and identify target samples for v0.7 without rerunning tests or visual regression.

### Baseline Findings

- `storage/visual_regression/latest` contains the latest valid v0.6 visual regression output.
- All 7 formal samples used real OCR in the v0.6 baseline.
- `02_game_ui_home` is protected by the v0.6 UI guard. `translation_item_count=0` and `inline_render_count=0` are expected for that sample.
- `05_complex_background_small_text` remains the main complex small text target for v0.7.
- `06_bw_manga_page` remains the main overflow / noisy inline target for v0.7.
- `storage/visual_regression/` is local output and must not be committed.
- `tests/visual_samples/` remains a local sample directory and must not be committed.
- `webp` samples are not formal OCR regression samples under the current PaddleOCR / PaddleX runtime.

## Step 1C Mode Decision Debug Only

### Goal

Add an image-level mode decision debug artifact so future v0.7 work can inspect what kind of page was processed before adding real mode-specific behavior.

This step is debug-only.

### Changes

- Added `app/services/mode_service.py`.
- Added image-level mode decision export:
  - `storage/debug/layout/{job_id}_mode.json`
- Updated the visual regression tool to copy and summarize per-sample `mode.json`.
- Updated the visual regression HTML report to show the detected mode and mode decision payload.
- Added unit tests for mode classification and visual regression report integration.

### Candidate Modes

- `game_ui`
- `manga`
- `document`
- `complex_background`
- `generic`

### Signals

Mode decision reads existing debug signals only:

- render fit record count
- translation item count
- inline render count
- skipped count and skipped reason distribution
- UI guard role counts
- text group count
- vertical text group count
- paragraph block count
- small text ratio
- region link ratio
- overflow count

### Expected Sample Direction

- `01_phone_ui_document`: should lean `document`.
- `02_game_ui_home`: should lean `game_ui`.
- `05_complex_background_small_text`: should lean `complex_background`.
- `06_bw_manga_page`: should lean `manga`.
- `07_color_vertical_manga`: should lean `manga`.
- `03_game_double_bubble` and `04_clean_single_bubble` may be `generic` or `manga` depending on region/group signals.

### Non-Goals

Step 1C does not:

- change OCR behavior
- change translation behavior
- change mask / inpaint / render behavior
- change block type
- release skipped blocks
- fix complex small text
- fix noisy inline text
- fix overflow
- alter game UI guard behavior
- submit visual regression outputs or local visual samples

### Tests

Run:

```text
python -m unittest discover -s tests -p "test*.py" -v
```

Step 1C must pass full unittest before commit.

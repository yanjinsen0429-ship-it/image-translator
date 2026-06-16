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

## Step 2A Complex Small Text Translate-Only Debug

### Goal

Add debug-only classification for complex-background small text. The purpose is to separate text-like fragments that may be useful later from inline-renderable text and OCR noise, without changing the current output pipeline.

Primary target sample:

- `05_complex_background_small_text`

### Changes

- Added `app/services/small_text_service.py`.
- Added small text debug export:
  - `storage/debug/layout/{job_id}_small_text.json`
- Updated the visual regression tool to copy per-sample `small_text.json`.
- Updated visual regression `summary.json` / HTML to include small text classification counts.
- Added unit tests for small text classification and visual regression summary integration.

### Classification Types

- `translate_only`
- `inline_render`
- `ignored_noise`
- `unknown`

### Rule Summary

- `translate_only`: text-like English fragments in `complex_background` mode that are currently skipped and may need future line reconstruction.
- `inline_render`: blocks that already have translated text and are currently renderable.
- `ignored_noise`: low-confidence single characters, tiny noise-like boxes, or very large low-confidence single-character boxes.
- `unknown`: fallback when evidence is insufficient.

### Debug Payload

Each record includes:

- `block_id`
- `text`
- `bbox`
- `confidence`
- `skipped_reason`
- `translated_text`
- `can_render_inline`
- `classification`
- `reasons`
- `debug_only`

The payload summary includes:

- `translate_only_count`
- `inline_render_count`
- `ignored_noise_count`
- `unknown_count`

### Non-Goals

Step 2A does not:

- change OCR behavior
- change translation provider calls
- change mask / inpaint / render inputs
- release skipped blocks
- make `translate_only` enter the real translation provider
- make `translate_only` enter mask / inpaint / render
- fix noisy inline text
- fix manga overflow
- implement line reconstruction

### Known Limits

- `translate_only` is a debug classification only; it does not mean the text is in the final translation result.
- Complex small text visual quality is not fixed in this step.
- Line reconstruction is still future work.

### Tests

Run:

```text
python -m unittest discover -s tests -p "test*.py" -v
```

Step 2A must pass full unittest before commit.

Actual result:

```text
Ran 171 tests
OK
```

### Visual Regression

Recommended command:

```text
python scripts/run_visual_regression.py --samples storage/visual_regression/png_samples_latest --output storage/visual_regression/v0.7_step2a --timeout 300
```

Expected scope:

- `05_complex_background_small_text` should include `small_text.json`.
- `05_complex_background_small_text` should remain `complex_background`.
- `02_game_ui_home` should remain `game_ui` with `translation_item_count=0` and `inline_render_count=0`.
- `06_bw_manga_page` and `07_color_vertical_manga` should remain `manga`.
- This step is debug-only, so visual PASS/WARN status is not expected to materially improve.

Actual result:

```text
samples: storage/visual_regression/png_samples_latest
output: storage/visual_regression/v0.7_step2a
PASS=3, WARN=4, FAIL=0
```

Mode checks:

```text
01_phone_ui_document: document
02_game_ui_home: game_ui
03_game_double_bubble: generic
04_clean_single_bubble: generic
05_complex_background_small_text: complex_background
06_bw_manga_page: manga
07_color_vertical_manga: manga
```

`05_complex_background_small_text` small text classification summary:

```text
translate_only_count=71
inline_render_count=1
ignored_noise_count=2
unknown_count=7
```

Protected sample checks:

- `02_game_ui_home` remains `game_ui`, with `translation_item_count=0` and `inline_render_count=0`.
- `06_bw_manga_page` remains `manga`.
- `07_color_vertical_manga` remains `manga`.

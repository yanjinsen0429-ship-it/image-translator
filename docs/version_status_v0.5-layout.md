# v0.5 Layout Version Status

## 1. Version Info

- Version: `v0.5-layout`
- Status: Ready for final review / 封版前检查
- Base Version: `v0.4-inpainting`
- Branch: `main`

## 2. Goals

`v0.5-layout` focuses on improving the layout layer between OCR and final image rendering. The goal is to make translated output more readable and more coherent without changing OCR, translation provider, inpainting, frontend UI, batch processing, or export features.

Main goals:

- OCR Block Merge
- Layout Analysis
- Smart Layout
- Font Optimization
- Initial Button / Logo handling
- Final output path fix
- Adaptive text color

## 3. Completed Features

### Geometry Utilities

- Added geometry helpers for bbox and polygon handling.
- Added bbox union, width, height, overlap, vertical gap, and similarity utilities.

### Layout Service

- Added `layout_service`.
- Added `LayoutBlock` intermediate structure.
- Added OCR block normalization.
- Added initial block classification:
  - `normal`
  - `paragraph`
  - `button`
  - `logo`
  - `ignored`
- Added conservative OCR block merge.
- Added fallback behavior when layout merge fails.

### LayoutBlock Structure

`LayoutBlock` includes:

- `id`
- `text`
- `translated_text`
- `polygon`
- `bbox`
- `source_block_ids`
- `block_type`
- `confidence`
- `metadata`

### Pipeline Integration

- Connected layout analysis before translation.
- Translation now receives merged layout blocks when layout merge succeeds.
- Layout merge failure falls back to original OCR blocks.
- `logo` and `ignored` blocks are compatible with translation skipped behavior.

### Smart Rendering

- Added bbox-based text wrapping.
- Added dynamic font size estimation.
- Added minimum font size protection.
- Added bbox area fitting.
- Added button horizontal and vertical centering.
- Added compatibility with legacy block dict.
- Added compatibility with layout block dict.
- Added short-text preference for single-line rendering when it fits.

### Final Output Fix

- Fixed the issue where the API still returned mock output or the original image after rendering succeeded.
- When rendering succeeds, the rendered image is published to:

```text
storage/outputs/{job_id}_output.png
```

- API response now points to the final translated output image.
- Debug rendered output is still kept under:

```text
storage/debug/rendered/{job_id}_rendered.png
```

- The previous mock output remains a fallback / intermediate artifact, but is no longer returned as the final user output after successful rendering.

### Adaptive Text Color

- Added background luminance sampling in the target bbox.
- Dark background uses white text.
- Light background uses black text.
- Added 1px inverse-color stroke.
- Improved readability on dark images.

### Tests

- Added geometry tests.
- Added layout service tests.
- Added layout pipeline tests.
- Added rendering service tests for:
  - short text single-line preference
  - rendered final output publishing
  - adaptive text color on dark backgrounds
  - adaptive text color on light backgrounds
  - rendering compatibility and stability

## 4. Pipeline After v0.5

```text
Image
→ OCR
→ Layout Analysis / OCR Block Merge
→ Translation
→ Mask Generation
→ Inpainting
→ Smart Rendering
→ Final Output
```

## 5. Modified Files

Main files involved in `v0.5-layout`:

- `app/utils/geometry.py`
- `app/services/layout_service.py`
- `app/api/routes.py`
- `app/services/translation_service.py`
- `app/services/rendering_service.py`
- `tests/test_geometry.py`
- `tests/test_layout_service.py`
- `tests/test_layout_pipeline.py`
- `tests/test_rendering_service.py`
- `docs/version_status_v0.5-layout.md`

## 6. Test Result

Latest full unittest result:

```text
Ran 74 tests
OK
```

## 7. Manual Verification

Manual verification was performed with a real uploaded image containing:

- multi-line English headline
- button text
- side caption text
- logo / brand text
- dark background

Verified results:

- Final output is now a Chinese translated image.
- API output path points to `storage/outputs/{job_id}_output.png`.
- Final output no longer incorrectly points to mock output.
- Debug rendered output remains available under `storage/debug/rendered/`.
- Dark background text is rendered in white and is more readable.
- Multi-line headline is merged and translated more naturally than v0.4 line-by-line output.

## 8. Known Limitations

The following issues are intentionally not solved in `v0.5-layout`:

- Button horizontal text merge is not complete.
- Logo / brand text skip is not complete.
- Manga / speech bubble level layout is not complete.
- Caption box layout is not complete.
- Complex background color judgment is still heuristic.
- Image blending is still basic inpainting plus rendering.
- Some translated text may still feel visually less natural than the original design.
- The project has not yet reached ChatGPT image translation quality for manga, speech bubbles, posters, or complex illustration layouts.

## 9. Next Version Recommendation

Recommended next version:

```text
v0.6 Visual Quality / Manga Layout
```

Recommended focus:

- Bubble / text box detection
- Button horizontal merge
- Logo / brand text skip
- Manga dialogue layout
- Caption box layout
- Concise translation mode
- Stroke / shadow / local contrast tuning
- Better visual blending
- More natural font style and placement

Batch processing is recommended to move later, such as `v0.7` or beyond, because visual quality is currently more important than throughput.

## 10. Git History

`v0.5-layout` related commits:

- `b97559f feat: add layout block merge pipeline`
- `57e5458 feat: improve smart text rendering layout`
- `be1ccae feat: polish layout rendering output quality`

## 11. Final Acceptance Checklist

- [x] Unit tests pass.
- [x] Layout merge pipeline is implemented.
- [x] Smart rendering initial version is implemented.
- [x] Final output path is fixed.
- [x] Adaptive text color is implemented.
- [x] Manual image verification completed.
- [x] Version status document updated.
- [ ] Working tree is clean after docs commit.
- [ ] User confirms final review.
- [ ] Tag can be created only after confirmation.

Suggested tag name after final confirmation:

```text
v0.5-layout
```

Suggested final release flow:

1. Run full unittest.
2. Confirm working tree is clean.
3. Create tag `v0.5-layout`.
4. Push `main`.
5. Push tags.

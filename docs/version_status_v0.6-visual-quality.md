# v0.6 Visual Quality / Manga Layout

## Step 1 Button Horizontal Merge

### Status

Done

### Goal

This step improves the layout analysis stage so OCR text fragments inside a button can be merged before translation.

Typical OCR output may split one button phrase into multiple OCR blocks:

```text
Abuse
report
```

After this step, layout analysis can merge the button-like fragments into one `button` layout block:

```text
Abuse report
```

This lets translation process the full button phrase instead of translating each fragment separately.

### Changes

- Added conservative button-like OCR block merge logic in `layout_service`.
- Added detection for short adjacent OCR blocks that form a known button phrase.
- Merged button text with spaces, not newlines.
- Set merged button block `block_type` to `button`.
- Preserved source OCR block ids on the merged layout block.
- Preserved existing paragraph merge behavior.
- Added safeguards against merging distant blocks or blocks with very different heights.

### Tests

Command:

```powershell
python -m unittest
```

Expected result:

```text
OK
```

Step-specific coverage:

- Button fragments such as `Abuse` + `report` merge into one button block.
- Normal multi-line paragraph text is not forced into button merge.
- Distant short text blocks are not button-merged.
- Short text blocks with very different heights are not button-merged.
- Existing layout pipeline behavior remains compatible.

### Acceptance Criteria

- `Abuse` and `report` inside the same button-like area merge into one layout block.
- The merged text is `Abuse report`.
- The merged block type is `button`.
- Paragraph merge behavior is preserved.
- False positives are avoided for distant blocks.
- False positives are avoided for blocks with significantly different heights.
- OCR, translation providers, inpainting, rendering, frontend, batch, and export logic are unchanged.

### Known Limits

- This step only handles conservative button horizontal merge.
- Logo / brand text skip is not implemented in this step.
- Bubble detection is not implemented in this step.
- Concise translation mode is not implemented in this step.
- Manga dialogue layout is not implemented in this step.
- Visual polish beyond button merge is not implemented in this step.

## Step 2A OCR Noise Marking Only

### Status

Done

### Goal

- Identify obvious OCR noise at the layout layer.
- Mark high-confidence noise blocks as `ignored`.
- Prepare for later Non-text Protection work.
- Do not directly change the final output image in this step.

### Changes

- Added `is_likely_ocr_noise_block` in `layout_service`.
- Marked standalone symbols such as `]` and `|` as `ignored`.
- Marked very small isolated `E` / `I` / `l` OCR blocks as `ignored`.
- Preserved normal short text such as `OK`, `Go`, `No`, and `Yes`.
- Did not modify routes, mask generation, inpainting, or rendering.

### Tests

Command:

```powershell
python -m unittest discover -s tests -p "test*.py" -v
```

Result:

```text
Ran 82 tests
OK
```

- This was not `Ran 0 tests`.
- The discover verbose command is the recommended test command for this project.

### Acceptance Criteria

- Standalone `]` is marked as `ignored`.
- Standalone `|` is marked as `ignored`.
- A very small bbox containing isolated `E` is marked as `ignored`.
- `OK`, `Go`, `No`, and `Yes` are not marked as `ignored`.
- Paragraph merge does not regress.
- Button Horizontal Merge does not regress.
- `routes.py` is not modified.
- Mask, inpaint, and render flows are not connected to this step.
- Full unittest discover passes.

### Known Limits

- This step only marks blocks at the layout layer.
- This step does not directly fix final image false-positive damage.
- This step does not block mask, inpaint, or render because it is not connected to the main output flow yet.
- This step cannot identify every possible OCR noise block.
- Logo / brand skip is not implemented in this step.
- Bubble detection is not implemented in this step.
- Concise translation mode is not implemented in this step.
- Visual polish is not implemented in this step.

## Step 2B Skip Ignored Blocks in Translation

### Status

Done

### Goal

- Prevent `ignored` layout blocks from entering real translation work.
- Avoid calling translation providers for obvious OCR noise.
- Keep the existing provider mechanism unchanged.
- Do not connect this step to mask, inpaint, or render behavior.

### Changes

- Verified the existing translation skip path for `block_type == "ignored"`.
- Kept provider selection, DeepSeek request handling, mock translation, dotenv, and fallback behavior unchanged.
- Preserved the existing skipped translation item structure for ignored blocks.
- Added regression tests proving ignored blocks do not call mock `translate_text`.
- Added regression tests proving ignored blocks do not call DeepSeek `_request_translation`.
- Added mixed-block coverage to preserve output order while skipping ignored blocks.

### Tests

Command:

```powershell
python -m unittest discover -s tests -p "test*.py" -v
```

Result:

```text
Ran 85 tests
OK
```

- This was not `Ran 0 tests`.
- The discover verbose command is the recommended test command for this project.

### Acceptance Criteria

- Ignored blocks do not call the mock provider translation entry point.
- Ignored blocks do not call the DeepSeek request entry point.
- Ignored blocks return skipped translation items instead of normal translated text.
- Normal blocks still translate normally.
- Mixed normal / ignored / normal blocks preserve output order.
- Step 2A OCR noise marking tests still pass.
- Button Horizontal Merge tests still pass.
- Mask, inpaint, and render flows are not modified.
- Full unittest discover passes.

### Known Limits

- This step only skips translation work.
- This step does not directly fix final image false-positive damage.
- This step does not skip mask, inpaint, or render.
- Final non-text image protection still requires a later Step 2C.
- Logo / brand skip is not expanded in this step.
- Bubble detection is not implemented in this step.
- Concise translation mode is not implemented in this step.

## Step 2C-0 Debug Mask / Block Overlay

### Status

Done

### Goal

- Add a diagnostic overlay for OCR/layout blocks before attempting another image-processing fix.
- Help identify which OCR/layout block covers non-text regions such as skirt, legs, shoes, clothing folds, or background lines.
- Show block geometry, text, `block_type`, and whether the block is `ignored`.
- Do not change mask, inpaint, render, OCR, translation, or frontend behavior.

### Changes

- Added `export_layout_debug_overlay` in `layout_service`.
- Added route-level export of layout overlay images after layout merge.
- Output path:

```text
storage/debug/layout/{job_id}_layout_overlay.png
```

- The overlay draws each layout block bbox / polygon and labels it as:

```text
#index block_type: text preview
```

- `ignored` blocks use a distinct color from processable blocks.
- The overlay function does not mutate source block dictionaries or change `block_type`.
- Final output image processing remains unchanged.

### Tests

Command:

```powershell
python -m unittest discover -s tests -p "test*.py" -v
```

Result:

```text
Ran 88 tests
OK
```

- This was not `Ran 0 tests`.
- The discover verbose command is the recommended test command for this project.

### Manual Check

Manual character-image overlay inspection is the next step:

- Check which block covers the skirt region.
- Check which block covers the shoes region.
- Check which block covers the leg region.
- Record each suspicious block's text and `block_type`.
- Confirm whether suspicious blocks are `ignored` or still processable.

### Known Limits

- This step is diagnostic only.
- This step does not directly fix final image false-positive damage.
- This step does not change mask generation.
- This step does not change inpaint behavior.
- This step does not change render behavior.
- A later Step 2C-1 should be designed from the overlay evidence.

## Step 2A.1 Improve OCR Noise Marking for Large False Positive Blocks

### Status

Done

### Goal

- Improve OCR noise marking for obvious large false-positive layout blocks.
- Mark isolated large `]`, `|`, `E`, `I`, and `l` OCR artifacts as `ignored` when the signal is conservative enough.
- Preserve real short text and paragraph merge behavior.
- Do not change final image output, mask generation, inpainting, rendering, routes, OCR providers, or frontend behavior.

### Changes

- Kept standalone punctuation noise marking for obvious symbols such as `]` and `|`.
- Added a layout refinement pass after initial block classification.
- Marked isolated single-letter `E` / `I` / `l` blocks as `ignored` when low confidence or using an oversized single-character bbox.
- Avoided ignoring single-letter blocks when they have nearby normal text that can form a paragraph.
- Preserved Step 1 `Abuse` + `report` => `Abuse report` button merge behavior.
- Preserved existing paragraph merge behavior.

### Tests

Command:

```powershell
python -m unittest discover -s tests -p "test*.py" -v
```

Result:

```text
Ran 92 tests
OK
```

- This was not `Ran 0 tests`.
- The discover verbose command is the recommended test command for this project.

Step-specific coverage:

- Large isolated `]` is marked as `ignored`.
- Large isolated `|` is marked as `ignored`.
- Large isolated `E`, `I`, and `l` are marked as `ignored`.
- Normal short text such as `OK`, `Go`, `No`, `Yes`, `AI`, `A`, `B`, `C`, `1`, `2`, and `3` is preserved.
- A single-letter block near paragraph text is not marked as `ignored`.
- Button Horizontal Merge and paragraph merge regressions are covered.

### Manual Check

Manual character-image retest was not run in this step.

Recommended retest checklist:

- Confirm translation results no longer include skirt / shoe noise such as standalone `]` or `E` sent to DeepSeek.
- Confirm the debug overlay marks those suspicious skirt / shoe OCR blocks as `ignored`.
- Confirm final output damage improves after the later image-processing connection step.

### Known Limits

- This remains a conservative layout-layer heuristic.
- Complete-word false positives may still pass through.
- This step does not connect ignored blocks to mask, inpaint, or render behavior.
- Logo / brand skip is not expanded in this step.
- Bubble detection is not implemented in this step.
- Visual polish is not implemented in this step.

## Step 2C-0.1 Export Layout Debug JSON

### Status

Done

### Goal

- Export structured layout block debug information for every image processing run.
- Help diagnose why OCR artifacts such as `]` and `E` are not marked as `ignored`.
- Record final layout block facts before translation.
- Do not fix OCR noise rules in this step.
- Do not change translation, mask, inpaint, render, or final image output behavior.

### Changes

- Added `export_layout_debug_json` in `layout_service`.
- Added route-level export after layout merge and before translation.
- Output path:

```text
storage/debug/layout/{job_id}_layout_blocks.json
```

- The JSON includes per-block fields such as:
  - `index`
  - `id`
  - `text`
  - `block_type`
  - `bbox`
  - `polygon`
  - `confidence`
  - `width`
  - `height`
  - `area`
  - `center`
  - `is_ignored`
  - `raw_keys`
  - `enters_translation`
  - `translation_skip_reason`
  - `enters_image_processing`
  - `image_processing_note`
  - `nearby_blocks`
  - `debug_notes`
- The JSON export creates `storage/debug/layout` automatically when needed.
- The JSON export does not mutate source block dictionaries.
- The overlay export and JSON export are isolated so JSON can still be written if overlay rendering fails.
- Final image processing remains unchanged.

### Tests

Command:

```powershell
python -m unittest discover -s tests -p "test*.py" -v
```

Result:

```text
Ran 94 tests
OK
```

- This was not `Ran 0 tests`.
- The discover verbose command is the recommended test command for this project.

Step-specific coverage:

- `export_layout_debug_json` creates a JSON file.
- JSON contains both normal and ignored blocks.
- JSON contains `text`, `block_type`, `bbox`, `width`, `height`, `area`, and `is_ignored`.
- JSON export does not mutate original block dictionaries.
- The route pipeline writes `{job_id}_layout_blocks.json` under `debug/layout`.

### Manual Check

Manual character-image JSON inspection is the next step:

- Find blocks where `text` is `]` or `E`.
- Check each block's final `block_type`.
- Check `bbox`, `width`, `height`, `area`, and `confidence`.
- Check `nearby_blocks`.
- Check `enters_translation` and `translation_skip_reason`.
- Use those facts to decide why the block was not marked `ignored`.

### Known Limits

- This step is diagnostic only.
- This step does not fix final image false-positive damage.
- This step does not change OCR noise marking rules.
- This step does not change translation behavior.
- This step does not change mask generation.
- This step does not change inpaint behavior.
- This step does not change render behavior.

## Step 2A.2 Low-confidence Single CJK Noise Guard

### Status

Done

### Goal

- Handle OCR false positives where non-text character-art regions are detected as a low-confidence single CJK character.
- Cover the observed character-image case where the skirt / leg region was detected as `门`.
- Mark only very clear noise as `ignored` at the layout layer.
- Do not change translation providers, mask generation, inpainting, rendering, routes, frontend, or final image output behavior.

### Changes

- Added a low-confidence single CJK noise guard in `layout_service`.
- The rule requires all of the following:
  - single CJK character
  - low confidence, currently `confidence < 0.2`
  - large bbox area, currently `area > 50000`
  - isolated from nearby normal text blocks
  - initial `block_type` is `normal`
- The observed `门` case with bbox `[946, 2439, 1454, 2984]` and confidence `0.08` is marked as `ignored`.
- Existing OCR noise rules remain in place for standalone symbols and isolated `E` / `I` / `l`.
- Image processing remains unchanged.

### Tests

Command:

```powershell
python -m unittest discover -s tests -p "test*.py" -v
```

Result:

```text
Ran 98 tests
OK
```

- This was not `Ran 0 tests`.
- The discover verbose command is the recommended test command for this project.

Step-specific coverage:

- Low-confidence large isolated `门` is marked as `ignored`.
- The ignored `门` block reports `enters_translation == false` in layout debug JSON.
- High-confidence normal-size `门` is not marked as `ignored`.
- A CJK single character near another text block is not marked as `ignored`.
- Existing English short-text protections remain covered.
- Existing `]`, `|`, and large isolated `E` noise behavior remains covered.
- Button Horizontal Merge and paragraph merge regressions remain covered.

### Manual Check

Manual character-image retest was not run in this step.

Recommended retest checklist:

- Confirm the layout debug JSON block where `text == "门"` now has `block_type == "ignored"`.
- Confirm the same block has `is_ignored == true` and `enters_translation == false`.
- Confirm translation results no longer include `门` or a DeepSeek result for that block.
- Confirm `E` remains `ignored`.
- Check whether skirt / leg white-block damage improves.
- If `门` is ignored but final image damage remains, the remaining issue is that image processing still does not consume layout `block_type`, which belongs to a later Step 2C-1.

### Known Limits

- This remains a conservative heuristic.
- If OCR produces a high-confidence single CJK character, it will be preserved.
- If OCR produces a complete word or phrase false positive, this rule may not catch it.
- This step does not handle bubble detection.
- This step does not expand logo / brand skip.
- This step does not add visual polish.
- This step does not change mask, inpaint, or render behavior.

## Step 2A.3 Ensure Refined Noise Blocks Reach Translation

### Status

Done

### Goal

- Verify that refined layout noise blocks reach the real route translation pipeline.
- Ensure refined `ignored` blocks do not appear as visible translated items in the web response.
- Keep layout debug JSON aligned with the refined layout block state.
- Do not add OCR noise rules in this step.
- Do not change OCR, translation providers, mask generation, inpainting, rendering service logic, frontend, or final image output architecture.

### Root Cause

- `merge_ocr_blocks()` already called `refine_noise_blocks()`.
- `routes.py` already passed the refined layout blocks to `create_translation_result()`.
- Debug JSON and translation input were based on the same refined layout block list.
- The confusing web result came from skipped ignored blocks still being kept in `translation_result.items`.
- Skipped items preserve their source text and provider name, so the frontend displayed entries such as `]` / `E` with `provider: deepseek` even though DeepSeek request was skipped.
- Those skipped items were also passed to debug rendering, where they could be drawn back as source text.

### Changes

- Added route-level filtering of skipped translation items after translation result creation.
- Kept the actual translation provider skip behavior unchanged.
- Kept debug JSON exporting the refined layout block facts, including ignored blocks and `enters_translation == false`.
- Kept ignored blocks out of returned web `translation_result.items`.
- Kept ignored blocks out of route-level render input.
- Did not modify `layout_service` noise rules in this step.
- Did not modify image processing services or frontend.

### Tests

Command:

```powershell
python -m unittest discover -s tests -p "test*.py" -v
```

Result:

```text
Ran 99 tests
OK
```

- This was not `Ran 0 tests`.
- The discover verbose command is the recommended test command for this project.

Step-specific coverage:

- Route pipeline uses refined layout blocks before translation.
- Standalone `]` is `ignored` in the real route pipeline.
- Large isolated `E` is `ignored` in the real route pipeline.
- Low-confidence large single CJK `门` is `ignored` in the real route pipeline.
- DeepSeek request is only called for the real paragraph block.
- Ignored skipped blocks are not returned as visible translation items.
- Ignored skipped blocks are not passed to route-level render input.
- Debug JSON block types match the refined layout state.
- Paragraph merge remains covered.
- `Abuse` + `report` button merge remains covered.

### Manual Check

Manual character-image retest was not run in this step.

Recommended retest checklist:

- Confirm layout debug JSON still shows `]`, `E`, and `门` as `ignored`.
- Confirm web translation result no longer lists those ignored blocks as DeepSeek translation items.
- Confirm only real paragraph text appears in visible translation results.
- Confirm output image behavior separately; if white-block damage remains, that belongs to a later image-processing step.

### Known Limits

- This step does not change OCR detection.
- This step does not add new noise heuristics.
- This step does not change DeepSeek or mock provider logic.
- This step does not change mask, inpaint, or render service internals.
- This step does not fix final image false-positive erasure if image processing still consumes raw OCR geometry.
- Bubble detection, logo skip expansion, and visual polish remain out of scope.

## Step 2C-1 Skip Ignored Blocks in Image Processing

### Status

Done

### Goal

- Prevent `ignored` layout blocks from participating in image processing.
- Reduce false-positive erasure in non-text regions such as character skirt, legs, and shoes.
- Ensure ignored blocks do not generate mask regions.
- Ensure ignored / skipped items are not rendered back into the output.
- Keep normal paragraph and button blocks on the existing mask / inpaint / render path.

### Changes

- Added route-level filtering before mask generation.
- Mask generation now receives processable refined layout blocks instead of raw OCR blocks.
- Blocks with `block_type == "ignored"` are removed from the route-level image processing input.
- Added a defensive skip in `InpaintingService` so ignored blocks do not produce mask polygons.
- Added a defensive skip in `RenderingService` so `status == "skipped"` or `block_type == "ignored"` items are not drawn.
- Kept inpaint behavior unchanged; it receives the mask that no longer contains ignored regions.
- Kept normal blocks on the existing image processing flow.
- Did not change mask padding, inpaint radius, rendering style, OCR, providers, or frontend.

### Tests

Command:

```powershell
python -m unittest discover -s tests -p "test*.py" -v
```

Result:

```text
Ran 102 tests
OK
```

- This was not `Ran 0 tests`.
- The discover verbose command is the recommended test command for this project.

Step-specific coverage:

- `InpaintingService.export_debug_mask` skips ignored blocks.
- Normal mask regions are still generated.
- Route-level mask generation receives only processable layout blocks.
- Refined ignored `]`, `E`, and `门` do not enter mask generation.
- `RenderingService.export_debug_rendered` skips skipped / ignored items.
- Normal render items still render.
- Step 2A.3 remains covered: ignored noise blocks do not appear in returned translation items.
- Button Horizontal Merge remains covered.
- Paragraph merge remains covered.

### Manual Check

Manual character-image retest was not run in this step.

Recommended retest checklist:

- Confirm translation results still do not show `]`, `E`, or `门`.
- Confirm layout debug JSON still marks `]`, `E`, and `门` as `ignored`.
- Confirm output image has reduced or removed white erasure around skirt, legs, and shoes.
- Confirm dialogue text still translates and renders normally.
- Record any remaining small artifacts as known limits rather than expanding into CV, bubble detection, or visual polish in this step.

### Known Limits

- This remains heuristic protection based on existing ignored block classification.
- If OCR false positives are not marked `ignored`, they may still enter image processing.
- This step does not expand logo / brand skip.
- This step does not implement bubble detection.
- This step does not implement visual polish.

## Step 4A Text Box / Bubble Candidate Detection Debug Only

### Status

Done

### Goal

- Add lightweight candidate detection for comic bubbles, caption boxes, text boxes, and button-like text containers.
- Produce debug-only artifacts that help inspect where future OCR / mask / render improvements could use container regions.
- Do not change OCR results, translation input, mask generation, inpainting, rendering, or the final output image.

### Changes

- Added `app/services/region_service.py`.
- Added a `TextRegion` debug structure with `id`, `region_type`, `bbox`, `polygon`, `score`, `source`, `linked_block_ids`, and `notes`.
- Added heuristic bright-region detection for bubble candidates.
- Added heuristic dark-region detection for caption/text box candidates.
- Added debug-only `button_like` regions derived from existing button layout blocks.
- Linked detected regions to layout blocks when a block center is inside the region bbox or when bbox overlap is high enough.
- Added region debug overlay export:

```text
storage/debug/layout/{job_id}_region_overlay.png
```

- Added region debug JSON export:

```text
storage/debug/layout/{job_id}_regions.json
```

- Wired route-level debug export after layout debug output.
- The detected regions are not passed into OCR, translation, mask, inpaint, render, or response item generation.

### Tests

Command:

```powershell
python -m unittest discover -s tests -p "test*.py" -v
```

Result:

```text
Ran 108 tests
OK
```

- This was not `Ran 0 tests`.
- Region-specific coverage includes synthetic white bubble detection, dark caption/text box detection, debug JSON export, debug overlay export, layout block linking, empty-region JSON export, button-like region export, and route-level debug artifact export.
- Existing regression coverage remains active for Abuse + report button merge, OCR noise ignored blocks, ignored blocks skipped in image processing, and paragraph merge.

### Manual Check

- Checked a web screenshot region overlay.
  - Output: `storage/debug/layout/manual_web_step4a_region_overlay.png`
  - JSON: `storage/debug/layout/manual_web_step4a_regions.json`
  - Result: detected one `button_like` region around the Abuse report button linked to `layout_block-6_block-7`.
- Checked a manga / illustration region overlay.
  - Output: `storage/debug/layout/manual_manga_step4a_region_overlay.png`
  - JSON: `storage/debug/layout/manual_manga_step4a_regions.json`
  - Result: detected 14 candidate regions, mostly `bubble`, with several linked to OCR/layout blocks.
- Final output image quality was not expected to change in this step because region detection is debug-only.

### Known Limits

- Current detection is heuristic candidate detection only.
- It does not guarantee detection of every bubble or text box.
- False positives are possible, especially on large bright or dark visual areas.
- It does not handle vertical Japanese OCR.
- It does not change final translated images.
- It does not handle logo skip.
- It does not perform manga layout.
- Step 4B / Step 5 may later use these regions for actual OCR, mask, or render improvements.

## Step 4B Link Layout Blocks with Text Regions Debug Only

### Status

Done

### Goal

- Add bidirectional debug links between layout blocks and Step 4A text region candidates.
- Make it easier to inspect whether OCR/layout text sits inside a detected bubble, caption box, text box, or button-like container.
- Keep the feature debug-only and avoid changing OCR, translation, mask, inpaint, render, frontend, block classification, or final output images.

### Changes

- Kept `linked_block_ids` in `storage/debug/layout/{job_id}_regions.json`.
- Added `linked_region_ids` to each block record in `storage/debug/layout/{job_id}_layout_blocks.json`.
- Added bbox containment as an explicit region-to-block link condition.
- Preserved the Step 4A center-inside-region and overlap-based linking behavior.
- Allowed one block to link to multiple regions and one region to link to multiple blocks.
- Added `no_linked_text_region` to layout debug notes when a block has no linked region.
- Changed region overlay labels to include linked block count as `links={count}`.
- Reordered route-level debug export so region candidates are detected before layout JSON serialization.
- The detected regions and links are not passed into translation, mask, inpaint, render, or response item generation.

### Tests

Command:

```powershell
python -m unittest discover -s tests -p "test*.py" -v
```

Result:

```text
Ran 112 tests
OK
```

- This was not `Ran 0 tests`.
- Added coverage for region bbox containment linking, `linked_region_ids` in layout debug JSON, empty `linked_region_ids` with `no_linked_text_region`, and route-level consistency between `_regions.json` and `_layout_blocks.json`.
- Step 4A coverage remains active for region JSON / overlay generation.
- Step 2 ignored/image processing protection remains covered.

### Manual Check

- Checked a web screenshot region overlay.
  - Output: `storage/debug/layout/manual_step4b_web_region_overlay.png`
  - JSON: `storage/debug/layout/manual_step4b_web_regions.json`
  - Layout JSON: `storage/debug/layout/manual_step4b_web_layout_blocks.json`
  - Result: detected one `button_like` region with one linked layout block.
- Checked a manga / illustration region overlay.
  - Output: `storage/debug/layout/manual_step4b_manga_region_overlay.png`
  - JSON: `storage/debug/layout/manual_step4b_manga_regions.json`
  - Layout JSON: `storage/debug/layout/manual_step4b_manga_layout_blocks.json`
  - Result: detected 14 candidate regions and 12 layout blocks with linked region ids.
- Confirmed overlay labels show `region_type`, score, and `links={count}`.
- Final translated output was not expected to change because Step 4B remains debug-only.

### Known Limits

- This step only links existing debug candidates and layout blocks.
- It does not improve region detection quality.
- It does not use regions for OCR, translation, mask, inpaint, render, or layout.
- It does not handle logo skip; `trust name` remains a known limit.
- False positive or missing region candidates from Step 4A remain possible.

## Step 4C Render Fit Debug Only

### Status

Done

### Goal

- Add structured render-fit debug output for each layout block.
- Help inspect why translated text may look too small, underuse a bubble bbox, overflow, or sit in an awkward text region.
- Keep the feature debug-only and avoid changing OCR, translation, mask, inpaint, render, frontend, block classification, API response structure, or final output images.

### Changes

- Added `app/services/render_fit_service.py`.
- Added render fit debug JSON export:

```text
storage/debug/layout/{job_id}_render_fit.json
```

- Each record includes:
  - `block_id`
  - `block_type`
  - `bbox`
  - `linked_region_ids`
  - `original_text`
  - `translated_text`
  - text lengths
  - bbox width / height / area
  - estimated text density
  - linked region count
  - selected / min / max font size estimate
  - line count
  - text area ratio
  - possible underfill / overflow / small-font flags
  - `debug_notes`
- Uses existing `RenderingService.calculate_text_layout()` for debug estimation only.
- Route exports render fit JSON after translation result creation, using the same layout blocks and region candidates.
- No render fit data is passed into mask, inpaint, render, response payloads, or final output decisions.
- No render fit overlay was added in this step.

### Tests

Command:

```powershell
python -m unittest discover -s tests -p "test*.py" -v
```

Result:

```text
Ran 114 tests
OK
```

- This was not `Ran 0 tests`.
- Added coverage for render fit JSON generation, one record per layout block, `linked_region_ids`, translated text length, no-translation notes, no-linked-region notes, and route-level `_render_fit.json` export.
- Step 4A / Step 4B coverage remains active.
- Step 2 ignored/image processing protection remains covered.

### Manual Check

- Checked a web screenshot render fit JSON.
  - Output: `storage/debug/layout/manual_step4c_web_render_fit.json`
  - Result: 4 records, 1 record with linked region ids.
  - Notes included `long_translation`, `no_linked_region`, and `no_translated_text`.
- Checked a manga / illustration render fit JSON.
  - Output: `storage/debug/layout/manual_step4c_manga_render_fit.json`
  - Result: 14 records, 12 records with linked region ids.
  - Notes included `possible_font_too_small`, `possible_overflow`, `possible_underfilled_bbox`, `possible_vertical_text_region`, and `small_bbox`.
- Final translated output was not expected to change because Step 4C remains debug-only.

### Known Limits

- This step is diagnostic only.
- Font and layout values are estimates from current renderer helpers, not a new render policy.
- It does not change true rendering behavior.
- It does not add overlay output.
- It does not improve OCR, translation, mask, inpaint, render, frontend, manga layout, or logo skip.

## Step 4D Render Fit Overlay Debug Only

### Status

Done

### Goal

- Add a visual render-fit debug overlay based on Step 4C render fit records.
- Help inspect per-layout-block render risk at a glance, including missing region links, missing translation, overflow, underfilled boxes, small font, and vertical text hints.
- Keep the feature debug-only and avoid changing OCR, translation, provider behavior, mask, inpaint, true render behavior, frontend, block classification, API response structure, or final output images.

### Changes

- Added render fit debug overlay export:

```text
storage/debug/layout/{job_id}_render_fit_overlay.png
```

- Added `export_render_fit_debug_overlay()` to `app/services/render_fit_service.py`.
- The overlay draws each render fit record bbox over the source image.
- Overlay labels are intentionally compact:

```text
b3 len=12 fs=18 links=1 notes=0
```

- Label fields include short block id, translated text length, selected font size, linked region count, and debug note count.
- Overlay colors are based on debug notes:
  - normal records use a green outline
  - `no_linked_region` / `possible_vertical_text_region` use a blue outline
  - `possible_underfilled_bbox` / `possible_font_too_small` use an orange outline
  - `possible_overflow` / `no_translated_text` use a red outline
- Route exports render fit JSON and overlay from the same render fit records.
- No render fit overlay data is passed into mask, inpaint, render, response payloads, or final output decisions.

### Tests

Command:

```powershell
python -m unittest discover -s tests -p "test*.py" -v
```

Result:

```text
Ran 116 tests
OK
```

- This was not `Ran 0 tests`.
- Added coverage for render fit overlay generation, risk-summary drawing, empty-record overlay generation, and route-level `_render_fit_overlay.png` export.
- Step 4C render fit JSON coverage remains active.
- Step 4A / Step 4B coverage remains active.
- Step 2 ignored/image processing protection remains covered.

### Manual Check

- Manually generated and opened web overlay:

```text
storage/debug/layout/manual_step4d_web_render_fit_overlay.png
```

- Manually generated and opened manga overlay:

```text
storage/debug/layout/manual_step4d_manga_render_fit_overlay.png
```

- Confirmed both overlays render bbox outlines and compact labels.
- Confirmed risky records use visibly different outline colors.
- Confirmed this manual check only opened debug overlay images and did not change final translated output.

### Known Limits

- This step is visual diagnosis only.
- Overlay labels are summaries; full details remain in `_render_fit.json`.
- It does not change true rendering behavior.
- It does not improve OCR, translation, mask, inpaint, render, frontend, manga layout, or logo skip.

## Step 5A Improve Render Text Fit and Centering

### Status

Done

### Goal

- Start the first real render quality improvement after the Step 4C / 4D diagnostics.
- Improve translated text fit inside existing OCR/layout bboxes.
- Increase readability for short text and reduce underfilled bboxes.
- Improve horizontal and vertical centering for normal, paragraph, and button text.
- Keep OCR, translation, provider, mask, inpaint, frontend, layout detection, region detection, and `block_type` logic unchanged.

### Changes

- Updated `RenderingService.calculate_text_layout()` to choose the largest font size that fits the padded bbox content area.
- Raised the dynamic max font size ceiling for roomy short-text bboxes.
- Preserved a single-line preference for short text when a fitting single-line layout exists.
- Added a padded content box so rendered text avoids bbox edges.
- Changed normal / paragraph text layout to center every line horizontally.
- Changed normal / paragraph text layout to vertically center the whole text block.
- Updated Chinese wrapping to use measured character-based wrapping and rebalance one-character final lines when width allows.
- Added layout metadata used by render fit debug, including `line_count`, `min_font_size`, `max_font_size`, content box, and padding fields.
- Updated `render_fit_service` to read the renderer's real min / max font size values when translated text is available.
- This step changes final output because real render placement, font size, wrapping, and centering changed.

### Tests

Command:

```powershell
python -m unittest discover -s tests -p "test*.py" -v
```

Result:

```text
Ran 120 tests
OK
```

- This was not `Ran 0 tests`.
- Added coverage for roomy short Chinese text using a readable larger font.
- Added coverage for multi-line Chinese text staying near bbox center.
- Added coverage for Chinese wrapping avoiding single-character lines when width allows.
- Added coverage for tiny bboxes not crashing and still returning layout metadata.
- Step 4C render fit JSON coverage remains active.
- Step 4D render fit overlay coverage remains active.
- Step 4A / Step 4B region-layout debug coverage remains active.
- Step 2 ignored / image processing protection remains covered.

### Manual Check

- Ran the route on a web image:

```text
storage/uploads/99596b25a5ac45659dfb670d3acf7864_webpage-retest.webp
```

- Output:

```text
storage/outputs/2843ed02a2ac438284a4e21d8e2ebaa5_output.png
```

- Debug:

```text
storage/debug/layout/2843ed02a2ac438284a4e21d8e2ebaa5_render_fit.json
storage/debug/layout/2843ed02a2ac438284a4e21d8e2ebaa5_render_fit_overlay.png
```

- Ran the route on a manga image:

```text
storage/uploads/6bd68d1bca4e4885b000aaa8ddba8720_IMG_7523.jpg
```

- Output:

```text
storage/outputs/60d2434796554b48841dfc33a48a609b_output.png
```

- Debug:

```text
storage/debug/layout/60d2434796554b48841dfc33a48a609b_render_fit.json
storage/debug/layout/60d2434796554b48841dfc33a48a609b_render_fit_overlay.png
```

- Current local PaddleOCR inference failed with `PaddleOCRError` and the route used the existing mock OCR fallback, so those route-level manual outputs verify generation and no obvious image corruption, but not real OCR text quality.
- Re-rendered existing Step 4C manual web records with the new renderer:

```text
storage/debug/rendered/manual_step5a_web_rendered.png
storage/debug/layout/manual_step5a_web_render_fit.json
storage/debug/layout/manual_step5a_web_render_fit_overlay.png
```

- Re-rendered existing Step 4C manual manga records with the new renderer:

```text
storage/debug/rendered/manual_step5a_manga_rendered.png
storage/debug/layout/manual_step5a_manga_render_fit.json
storage/debug/layout/manual_step5a_manga_render_fit_overlay.png
```

- Web re-render showed larger centered text with no obvious overflow or large abnormal region.
- Manga re-render showed centered text in existing bboxes. Narrow vertical OCR bboxes still produce small horizontal text, which remains out of scope for this step.
- Render fit JSON and render fit overlay were generated for both manual samples.

### Known Limits

- This step still renders text horizontally.
- It does not implement vertical Japanese / manga text layout.
- It does not fit text to bubble shapes; it only fits rectangular bboxes.
- It does not change OCR, translation, provider behavior, mask, inpaint, frontend, layout detection, region detection, or `block_type`.
- It does not address logo / brand skip; `trust name` remains a known limit.

## Step 5T Visual Regression Tool

### Status

Done

### Goal

- Add a repeatable visual regression tool for batch-running local sample images.
- Reduce manual browser uploads when checking render / mask / debug regressions.
- Provide a stable baseline tool before any future Step 5B-redux / 5C / 5D work.
- Keep OCR provider, translation provider, frontend, rendering rules, render-fit rules, mask, inpaint, and business pipeline behavior unchanged.

### Usage

Place visual samples in:

```text
tests/visual_samples/
```

Supported image extensions:

```text
png / jpg / jpeg / webp
```

Uppercase extensions such as `.JPG`, `.JPEG`, `.WEBP`, and `.PNG` are supported.

Run:

```powershell
python scripts/run_visual_regression.py
```

Optional arguments:

```powershell
python scripts/run_visual_regression.py --samples tests/visual_samples --output storage/visual_regression/latest
python scripts/run_visual_regression.py --open
```

The tool calls the running local API:

```text
http://127.0.0.1:8000/api/images/translate
```

using multipart form upload with the same `file` field used by the frontend.

### Output

Default output directory:

```text
storage/visual_regression/latest/
```

Generated files:

```text
storage/visual_regression/latest/index.html
storage/visual_regression/latest/summary.json
storage/visual_regression/latest/<sample_name>/input.png
storage/visual_regression/latest/<sample_name>/output.png
storage/visual_regression/latest/<sample_name>/render_fit.json
storage/visual_regression/latest/<sample_name>/render_fit_overlay.png
storage/visual_regression/latest/<sample_name>/regions.json
storage/visual_regression/latest/<sample_name>/region_overlay.png
storage/visual_regression/latest/<sample_name>/layout_blocks.json
storage/visual_regression/latest/<sample_name>/layout_overlay.png
storage/visual_regression/latest/<sample_name>/mask.png
storage/visual_regression/latest/<sample_name>/inpainted.png
storage/visual_regression/latest/<sample_name>/rendered.png
```

Missing debug artifacts do not crash the run; they are recorded in `summary.json`.

### PASS / WARN / FAIL

`FAIL` means the sample is not suitable as a passing visual-regression result:

- output image is missing.
- `render_fit.json` is missing.
- OCR fallback / mock OCR was used.
- a complex sample produced only one render-fit record.
- complex background dense text is still inline rendered.
- short text with an abnormal large bbox is still inline rendered.
- skipped records still indicate render or image-processing entry.

`WARN` means the output should be inspected:

- inline selected font size is below 10.
- overflow is present.
- skipped block has no skipped reason.
- noise-like text is still inline rendered.
- inline render count is zero for multi-record samples.
- skipped count is very high.
- optional debug files are missing.

`PASS` means the automatic checks found no blocking or warning condition. It does not replace final human visual judgment.

### Tests

Command:

```powershell
python -m unittest discover -s tests -p "test*.py" -v
```

Coverage added:

- sample scanning for `png / jpg / jpeg / webp`.
- uppercase extension scanning.
- empty sample directory behavior.
- `summary.json` generation.
- `index.html` generation.
- render-fit metrics parsing.
- mock / fallback OCR marked as `FAIL`.
- suspicious single-record complex samples marked as `FAIL`.
- missing debug files recorded without crashing.

### Known Limits

- This tool requires the local backend service to be running for real API mode.
- If PaddleOCR fails and the backend falls back to mock OCR, the sample is marked `FAIL`.
- The tool is a regression aid, not an aesthetic judge.
- It does not modify rendering, render-fit, OCR, translation, provider, frontend, mask, or inpaint behavior.
- It does not continue or restore the reverted Step 5B / 5B-hotfix work.

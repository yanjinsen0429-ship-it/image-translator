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

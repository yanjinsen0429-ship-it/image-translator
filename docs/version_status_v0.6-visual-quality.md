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

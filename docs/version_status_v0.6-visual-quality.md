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

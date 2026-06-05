# v0.4 Inpainting 当前版本状态

当前状态：`completed`

## 版本目标

`v0.4-inpainting` 的目标是在 `v0.3-translation` 基础上，完成从 OCR bbox 到图片擦字、背景修复、中文译文绘制回图片的本地调试闭环。

本版本仍保持现有 Web 上传、OCR、DeepSeek 翻译和下载链路可用，并通过 debug 输出验证图像处理各阶段结果。

## 已完成内容

- 保留 PaddleOCR OCR 流程。
- 保留 DeepSeek Translation Provider。
- 基于 OCR block 的 `bbox.points` 生成二值 mask。
- 导出 debug mask 图片。
- 使用 OpenCV `cv2.inpaint` 执行本地背景修复。
- 导出 debug inpainted background 图片。
- 使用 PIL 将中文译文绘制到修复后的背景图上。
- 支持基础中文字体加载、字号估算和自动换行。
- 导出 debug rendered 图片。
- 保持 API 响应结构不变。
- 保持前端展示逻辑不变。
- 保持 `storage/outputs/` 当前 mock 输出图逻辑不变。
- 单元测试已覆盖 mask、inpainting、rendering 的基础行为。

## 真实验收结果

真实图片验证已通过：

- OCR 能识别图片文本。
- DeepSeek 能返回中文译文。
- 后端能生成 `storage/debug/mask/{job_id}_mask.png`。
- 后端能生成 `storage/debug/inpainted/{job_id}_inpainted.png`。
- 后端能生成 `storage/debug/rendered/{job_id}_rendered.png`。
- rendered debug 图片中，英文原文已被擦除，并写入中文译文。

## Debug 输出目录

```text
storage/debug/mask/{job_id}_mask.png
storage/debug/inpainted/{job_id}_inpainted.png
storage/debug/rendered/{job_id}_rendered.png
```

说明：

- `mask/` 用于检查 OCR polygon 转换出来的文字区域。
- `inpainted/` 用于检查 OpenCV 背景修复效果。
- `rendered/` 用于检查译文写回图片后的效果。

## 本阶段不做什么

本版本不处理以下内容：

- 不优化复杂排版。
- 不做高级字体匹配。
- 不做漫画分镜理解。
- 不做批量图片处理。
- 不做浏览器插件。
- 不改 DeepSeek 调用逻辑。
- 不改 PaddleOCR 识别逻辑。
- 不改前端展示与 API 响应结构。

## 已知问题

- 排版比较粗糙。
- 小字区域字号偏小。
- OCR 分块导致译文语义有时不自然。
- 按钮、Logo、特殊图形区域效果一般。
- OpenCV inpainting 对复杂背景、渐变、纹理和艺术字效果有限。
- 竖排文字、多行密集文字、描边字仍可能需要专门优化。

这些问题不在 v0.4 继续处理，留到下一阶段。

## 下一版本建议

建议下一阶段命名为 `v0.5-layout`。

优先目标：

- 优化译文排版。
- 优化字号估算。
- 优化换行策略。
- 优化不同 bbox 下的文字对齐。
- 评估 OCR block 合并策略，减少逐块翻译导致的语义割裂。
- 针对按钮、Logo、特殊区域增加跳过或弱处理策略。

## 当前结论

`v0.4-inpainting` 已完成本地调试闭环，可以作为阶段版本封版。

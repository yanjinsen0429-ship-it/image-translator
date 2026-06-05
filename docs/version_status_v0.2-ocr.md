# v0.2 OCR 当前版本状态

当前版本号：`v0.2-ocr`。

本版本在 `v0.1-alpha` mock Web 骨架基础上接入 PaddleOCR，用于验证上传单张图片后返回真实 OCR 文本、bbox 和 confidence 的最小闭环。

## 已实现功能

- FastAPI Web 骨架继续可用。
- 本地网页继续支持单图上传。
- 上传原图继续保存到 `storage/uploads/`。
- mock 输出图继续生成到 `storage/outputs/`。
- 后端新增真实 PaddleOCR OCR 入口。
- 默认 OCR 语言为 `ch`，更适合当前中英混合图片场景。
- OCR 结果返回统一结构，包含 `text`、`bbox` 和 `confidence`。
- `bbox` 主格式为 `x`、`y`、`width`、`height`，并尽量保留 PaddleOCR 四点坐标 `points`。
- 前端继续在 OCR 文本区域展示 OCR 文本。
- mock 翻译继续保留。
- mock 输出图继续保留。
- PaddleOCR 不可用或推理失败时会 fallback 到 mock OCR。
- 已通过包含中文、英文、日文的混合测试图片验证。

## 未实现功能

- 真实翻译 API。
- 真实擦字重绘。
- 中文写回图片。
- OCR 框可视化。
- 浏览器插件。
- 批量处理。
- 人工校对界面。
- 任务历史和队列。

## 已知限制

- `requirements.txt` 只包含 `paddleocr==3.6.0`，PaddlePaddle CPU 版需要按 README 单独安装。
- 首次运行 PaddleOCR 可能下载模型，耗时取决于网络环境。
- Windows + Python 3.11 下 PaddleOCR / PaddlePaddle 安装可能受 pip、网络、CPU 架构影响。
- 当前默认使用 CPU 推理，速度可能较慢。
- PaddleOCR 真实返回结构如随版本变化，适配层可能需要调整。
- 日文漫画、竖排文字、复杂字体和艺术字识别效果可能有限；基础中英日混合测试已通过，但后续复杂日文场景可能仍需要切换或配置专用语言模型。
- 翻译仍为 mock 文本，输出图仍只是原图复制。

## 下一阶段目标

- 继续补充更多真实图片样本验证 PaddleOCR 效果。
- 根据复杂图片和日文场景的真实响应微调适配层。
- 继续评估英文、中文、日文模型选择。
- 增强 README 中的安装故障排查说明。
- 在 OCR 稳定后，再进入真实翻译 API 接入阶段。

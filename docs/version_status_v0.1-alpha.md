# v0.1-alpha 当前版本状态

当前版本标记为 `v0.1-alpha`。

本版本是一个 mock Web 骨架，用于验证从本地网页上传单张图片、后端保存原图、生成 mock 输出图、再由前端展示结果的最小闭环。

## 已完成

- FastAPI 可以启动。
- 本地网页可以打开。
- 支持单图上传。
- 上传原图会保存到 `storage/uploads/`。
- mock 输出图会生成到 `storage/outputs/`。
- 前端会显示原图、mock 输出图、mock OCR、mock 翻译和下载按钮。

## 尚未实现

- 真实 OCR。
- 真实翻译 API。
- 真实擦字重绘。
- 浏览器插件。
- 批量处理。

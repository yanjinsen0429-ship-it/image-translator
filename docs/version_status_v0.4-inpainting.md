# v0.4 Inpainting 当前版本状态

当前状态：`planning`

## 版本目标

`v0.4-inpainting` 的目标是在现有 `v0.3-translation` 基础上，进入图片擦字与回填前的图像处理阶段。

本阶段计划围绕 OCR block 的 `bbox` 信息，设计并逐步实现：

- 根据 OCR 结果生成文字区域 mask。
- 对原图中文字区域进行擦除或修复。
- 为后续中文回填预留稳定的图像输出结构。
- 保持现有 OCR 和翻译链路继续可用。

## 技术方案概述

计划继续沿用当前主流程：

```text
图片上传
-> PaddleOCR
-> TranslationProvider
-> 基于 OCR bbox 生成 mask
-> 图像修复 / inpainting
-> 输出处理后的图片
```

初步技术方向：

- 继续使用 `OCRResult / OCRBlock / BBox` 作为文字区域来源。
- 新增独立图像处理服务，不把擦字逻辑堆进 `app/api/routes.py` 或 `app/main.py`。
- 优先考虑轻量本地方案，例如 OpenCV mask + inpaint，先完成可验证闭环。
- 后续再评估更高质量的深度学习 inpainting 方案。
- 输出图仍写入 `storage/outputs/`，保持现有下载链路兼容。

## 本阶段不做什么

`v0.4-inpainting` 第一阶段不做以下内容：

- 不改 OCR 语言模型配置。
- 不重构 PaddleOCR 服务。
- 不改 DeepSeek Provider 架构。
- 不接入新的真实翻译 Provider。
- 不实现复杂漫画分镜理解。
- 不实现中文文字排版回填。
- 不实现字体匹配。
- 不实现批量图片处理。
- 不实现浏览器插件。
- 不引入账号系统或云端部署。

## 风险点

- OCR bbox 不一定精准，mask 过小会残留文字，mask 过大会破坏背景。
- OpenCV inpaint 对复杂背景、渐变、网点、漫画纹理的修复质量有限。
- 日文竖排、艺术字、描边字和气泡文字可能需要特殊 mask 扩张策略。
- 多段文字相邻时，mask 合并策略可能影响修复质量。
- 大图处理可能带来 CPU 耗时和内存占用问题。
- 输出图质量验证需要真实图片样本，单元测试只能覆盖结构和基础流程。

## 计划改动文件

预计可能新增或修改：

- `app/core/config.py`
  - 增加 inpainting 开关、mask padding、inpaint 参数等配置。
- `app/models/schemas.py`
  - 如有需要，补充 inpainting 结果结构或状态字段。
- `app/services/image_render_service.py`
  - 从当前 mock 原图复制升级为调用图像处理服务。
- `app/services/inpainting_service.py`
  - 新增独立擦字 / 修复服务。
- `app/api/routes.py`
  - 保持薄调用层，只串联服务和返回结果。
- `requirements.txt`
  - 如需 OpenCV，再新增轻量依赖。
- `tests/test_inpainting_service.py`
  - 覆盖 mask 生成、空 bbox、异常 fallback 等场景。
- `README.md`
  - 补充 v0.4 本地验证说明。
- `docs/version_status_v0.4-inpainting.md`
  - 持续记录本阶段状态。

## 验收标准

本阶段完成时应满足：

- 上传图片后，OCR 和翻译链路仍正常。
- 后端能基于 OCR bbox 生成文字区域 mask。
- 输出图不再只是原图复制，而是经过本地 inpainting 处理。
- 擦字失败时接口不崩溃，能保留可诊断错误或 fallback。
- `storage/uploads/` 继续保存原图。
- `storage/outputs/` 继续生成可下载输出图。
- 前端仍能显示原图、输出图、OCR 文本、翻译结果和下载按钮。
- 单元测试覆盖核心图像处理逻辑。
- 不提交 `.env`、测试图片或真实 API Key。

## 当前状态

`planning`

当前仅创建 v0.4 规划文档，尚未修改任何业务代码。

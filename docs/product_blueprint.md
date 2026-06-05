# 本地图片翻译/译图工具项目蓝图

## 1. 项目定位

### 1.1 要解决的问题

本项目旨在实现一个本地运行的“图片翻译/译图工具”：用户上传一张包含外文文字的图片，系统自动识别图片中的文字，将其翻译为中文，并在图片原位置附近重新排版中文译文，最终输出一张可下载的译图。

核心目标不是做通用图片编辑器，而是打通“图片输入 -> OCR -> 翻译 -> 擦除原文 -> 写入译文 -> 输出图片”的最小闭环。

### 1.2 当前阶段做什么

当前阶段聚焦本地 MVP：

- 支持单张本地图片上传；
- 识别图片中的英文或其他常见外文文本；
- 将识别文本翻译为中文；
- 尽量在原文字区域擦除原文；
- 将中文译文写回图片；
- 提供处理结果预览和下载；
- 保留中间结果，便于调试 OCR、翻译和重绘效果。

### 1.3 当前阶段不做什么

v0.1 阶段不追求完整商业化体验：

- 不做浏览器插件；
- 不做网页图片自动抓取；
- 不做批量翻译；
- 不做漫画级复杂嵌字；
- 不做复杂气泡识别；
- 不做手动框选和精修编辑器；
- 不做账号、计费、云同步；
- 不保证所有字体、背景、透视、艺术字都能完美还原。

### 1.4 与沉浸式翻译图片翻译功能的差距

沉浸式翻译的图片翻译通常面向浏览器场景，强调网页内图片自动检测、跨域处理、在线服务集成、交互式体验和更成熟的排版效果。

本项目当前阶段的差距主要在：

- 场景差距：只处理用户主动上传的本地图片，不自动处理网页图片；
- 体验差距：没有浏览器内悬浮按钮、右键菜单、自动替换等交互；
- 算法差距：OCR、擦字、排版策略更基础；
- 质量差距：复杂背景、竖排文字、艺术字、多语言混排效果有限；
- 工程差距：尚未处理浏览器插件跨域、权限、缓存、并发队列等问题。

当前目标是先做一个可运行、可验证、可逐步演进的本地译图核心。

## 2. 核心技术链路

### 2.1 图片输入

用户通过前端上传图片。后端接收文件后进行校验：

- 支持格式：PNG、JPG、JPEG、WEBP；
- 限制文件大小；
- 校验 MIME 类型；
- 生成任务 ID；
- 保存原图到本地工作目录。

### 2.2 OCR 文字检测与识别

OCR 服务负责从图片中检测文字区域并识别文本内容。

输出内容包括：

- 文本内容；
- 文本框坐标；
- 置信度；
- 行级或块级结构；
- 原始 OCR 引擎返回信息。

v0.1 可优先使用 PaddleOCR 或 EasyOCR。优先选择在 Windows 本地更容易跑通的方案。

### 2.3 文本结构化

OCR 结果不能直接交给翻译和排版，需要结构化处理：

- 合并属于同一句或同一区域的文本框；
- 按阅读顺序排序；
- 过滤低置信度文本；
- 记录每个文本块对应的 bbox；
- 保留原始行信息，方便调试。

v0.1 以简单规则为主，不做复杂版面分析。

### 2.4 翻译

翻译服务接收结构化文本块，返回中文译文。

翻译方式应通过配置切换：

- OpenAI API；
- 其他兼容 OpenAI 格式的模型服务；
- 本地 mock 翻译，用于无 API key 时调试流程。

v0.1 应保证即使翻译失败，也能返回明确错误，而不是让整个服务崩溃。

### 2.5 原文字区域擦除

图像重绘服务根据 OCR bbox 擦除原文区域。

v0.1 可采用基础方案：

- 使用 bbox 区域附近颜色估算背景；
- 对文字区域填充背景色；
- 可选轻微模糊或扩张 bbox；
- 保留 warning，提示擦除质量可能不佳。

后续版本可引入 OpenCV inpaint 或更强的图像修复模型。

### 2.6 中文译文排版

中文译文需要写回原文字区域附近。

v0.1 排版原则：

- 优先写入原 bbox；
- 根据 bbox 宽高动态计算字号；
- 自动换行；
- 使用可配置中文字体；
- 文字颜色默认黑色或根据背景亮度简单判断；
- 超出区域时缩小字号，仍超出则截断并给出 warning。

### 2.7 输出图片

处理完成后生成输出图片：

- 保存译图；
- 返回预览 URL；
- 返回下载 URL；
- 返回 OCR、翻译、重绘 warning；
- 保留任务状态，方便前端展示。

## 3. 模块设计

### 3.1 FastAPI 后端

职责：

- 提供 HTTP API；
- 接收图片上传；
- 创建处理任务；
- 调用 OCR、翻译、图像重绘服务；
- 返回处理结果；
- 暴露静态文件访问或下载接口。

建议接口：

- `POST /api/images/translate`：上传图片并处理；
- `GET /api/jobs/{job_id}`：查询任务状态；
- `GET /api/files/{file_id}`：下载或预览文件；
- `GET /api/health`：健康检查。

### 3.2 前端上传页面

职责：

- 提供图片上传入口；
- 展示原图预览；
- 展示处理中状态；
- 展示译图结果；
- 显示 warning/error；
- 提供下载按钮。

v0.1 前端应保持简单，不做复杂编辑器。

### 3.3 OCR 服务

职责：

- 封装具体 OCR 引擎；
- 输入图片路径；
- 输出统一 OCRResult；
- 屏蔽 PaddleOCR/EasyOCR 的原始差异；
- 记录置信度和原始返回值。

### 3.4 翻译服务

职责：

- 输入结构化文本块；
- 调用翻译提供方；
- 输出 TranslationResult；
- 支持 mock 模式；
- 处理超时、限流、空文本和 API 错误。

### 3.5 图像重绘服务

职责：

- 输入原图、OCR bbox、译文；
- 擦除原文；
- 排版中文；
- 保存输出图片；
- 返回处理后的图片路径和 warning。

### 3.6 文件管理服务

职责：

- 生成 job_id；
- 管理上传文件、输出文件、中间文件；
- 控制目录结构；
- 清理过期文件；
- 提供文件 URL 映射。

### 3.7 配置管理

配置项包括：

- 服务端口；
- 上传目录；
- 输出目录；
- 最大文件大小；
- OCR 引擎；
- 翻译 provider；
- API key；
- 中文字体路径；
- 日志级别；
- 是否保存中间结果。

应使用 `.env` + settings 模块统一管理，避免配置散落在业务代码里。

### 3.8 日志与错误处理

日志应覆盖：

- 上传成功/失败；
- OCR 耗时和识别数量；
- 翻译耗时和失败原因；
- 重绘耗时；
- 输出文件路径；
- warning/error 明细。

错误应结构化返回，避免只返回 500 和一段不可读异常。

## 4. 数据结构设计

### 4.1 OCR 结果结构

OCRResult：

- `job_id`：任务 ID；
- `image_width`：图片宽度；
- `image_height`：图片高度；
- `blocks`：OCR 文本块列表；
- `raw`：可选，原始 OCR 返回；
- `warnings`：OCR 阶段 warning。

OCRBlock：

- `id`：文本块 ID；
- `text`：识别文本；
- `bbox`：文字框坐标；
- `confidence`：置信度；
- `line_index`：行序号；
- `language`：可选语言；
- `source_items`：合并前的原始 OCR 项。

BBox：

- `x`：左上角 x；
- `y`：左上角 y；
- `width`：宽度；
- `height`：高度；
- `points`：可选四点坐标。

### 4.2 翻译结果结构

TranslationResult：

- `job_id`；
- `items`：翻译项列表；
- `provider`：翻译提供方；
- `source_language`：源语言；
- `target_language`：目标语言，v0.1 默认为 `zh-CN`；
- `warnings`；
- `errors`。

TranslationItem：

- `block_id`：对应 OCRBlock ID；
- `source_text`：原文；
- `translated_text`：中文译文；
- `status`：`success`、`skipped`、`failed`；
- `error`：单条翻译失败原因。

### 4.3 图片处理结果结构

ImageProcessResult：

- `job_id`；
- `status`：`success`、`partial_success`、`failed`；
- `input_file`：原图路径或 URL；
- `output_file`：译图路径或 URL；
- `ocr_result`：OCRResult 摘要；
- `translation_result`：TranslationResult 摘要；
- `rendered_blocks`：已写回图片的文本块；
- `warnings`；
- `errors`；
- `created_at`；
- `duration_ms`。

RenderedBlock：

- `block_id`；
- `bbox`；
- `translated_text`；
- `font_size`；
- `font_path`；
- `status`；
- `warning`。

### 4.4 warning/error 结构

Issue：

- `code`：机器可读错误码；
- `message`：用户可读信息；
- `stage`：`upload`、`ocr`、`translate`、`erase`、`render`、`file`；
- `level`：`warning` 或 `error`；
- `detail`：调试信息；
- `block_id`：可选，关联具体文本块。

示例错误码：

- `UPLOAD_INVALID_TYPE`；
- `OCR_NO_TEXT_FOUND`；
- `OCR_LOW_CONFIDENCE`；
- `TRANSLATION_TIMEOUT`；
- `TRANSLATION_PROVIDER_ERROR`；
- `FONT_NOT_FOUND`；
- `TEXT_OVERFLOW`；
- `INPAINT_LOW_QUALITY`；
- `OUTPUT_SAVE_FAILED`。

## 5. 推荐项目目录结构

```text
project-root/
  app/
    main.py
    api/
      routes.py
      schemas.py
    core/
      config.py
      logging.py
      errors.py
    services/
      ocr_service.py
      translation_service.py
      image_render_service.py
      file_service.py
    models/
      ocr.py
      translation.py
      image_result.py
      issue.py
    utils/
      image.py
      text_layout.py
      font.py
  frontend/
    index.html
    src/
      main.js
      styles.css
  storage/
    uploads/
    outputs/
    debug/
  fonts/
  tests/
    test_ocr_schema.py
    test_translation_service.py
    test_file_service.py
    test_image_render_service.py
  docs/
    product_blueprint.md
  .env.example
  README.md
  requirements.txt
```

原则：

- `main.py` 只负责创建 FastAPI app 和注册路由；
- API 层不直接写 OCR、翻译、绘图逻辑；
- services 层承载业务流程；
- models/schemas 保持数据结构清晰；
- README 必须说明如何安装、配置、运行和验证。

## 6. MVP 范围

### 6.1 v0.1 必须实现

- FastAPI 服务可启动；
- 前端可上传单张图片；
- 后端保存上传图片；
- OCR 能返回统一结构；
- 翻译服务能返回中文译文，至少支持 mock 或真实 provider 之一；
- 图像重绘服务能擦除原文字区域并写入中文；
- 输出图片可预览、可下载；
- 出错时返回结构化错误；
- README 包含运行步骤；
- 至少有基础测试覆盖数据结构、文件保存、mock 翻译和主流程。

### 6.2 v0.1 不实现

- 浏览器插件；
- 批量处理；
- 登录系统；
- 任务队列；
- 高级图像修复模型；
- 手动编辑译文；
- 多模板排版；
- 自动识别网页图片；
- 云端部署适配。

### 6.3 v0.1 的验收标准

- 在 Windows 本地按 README 步骤可以启动后端；
- 打开前端页面后可以上传一张测试图片；
- 处理完成后能看到输出译图；
- 输出图片中原文区域被基础擦除；
- 中文译文能写入对应区域；
- OCR 无文字、翻译失败、字体缺失等情况不会导致服务无提示崩溃；
- 项目结构没有把主要逻辑堆在 `main.py`；
- README 与实际运行方式一致。

## 7. 技术风险

### 7.1 OCR 准确率

风险：复杂字体、低分辨率、倾斜文字、背景干扰会降低识别准确率。

应对：

- 保留 OCR confidence；
- 低置信度文本给 warning；
- 保存 OCR debug 结果；
- 后续支持用户手动修正。

### 7.2 图片文字框坐标

风险：OCR bbox 可能过小、偏移或无法覆盖完整文字，影响擦除和排版。

应对：

- bbox 做适度扩张；
- 保留四点坐标；
- v0.1 使用矩形近似；
- 后续支持旋转框和多边形区域。

### 7.3 中文字体

风险：Windows 环境字体路径不稳定，缺字体会导致中文乱码或无法绘制。

应对：

- 项目内提供推荐字体目录；
- 配置 `FONT_PATH`；
- 启动时检查字体；
- 字体缺失返回明确错误。

### 7.4 擦字质量

风险：纯色填充在复杂背景上效果较差。

应对：

- v0.1 接受基础效果；
- 对复杂背景返回 warning；
- 后续引入 OpenCV inpaint；
- 更后续考虑模型级图像修复。

### 7.5 中文排版

风险：中文译文通常比原文更短或更长，可能溢出区域。

应对：

- 自动换行；
- 动态字号；
- 最小字号限制；
- 超出时 warning；
- 后续支持用户手动调整。

### 7.6 Windows 环境依赖

风险：OCR、OpenCV、字体、Python 包在 Windows 上安装容易出问题。

应对：

- 固定 Python 版本建议；
- 提供 `requirements.txt`；
- README 写明安装步骤；
- 优先选择 Windows 友好的依赖；
- 避免 v0.1 引入过重模型。

### 7.7 后续浏览器插件跨域问题

风险：浏览器插件处理网页图片会遇到 CORS、canvas taint、鉴权图片、跨域下载限制。

应对：

- v0.1 不做插件；
- 后续插件通过 background/service worker 拉取图片；
- 必要时让本地后端代理下载；
- 明确权限申请和用户确认流程。

## 8. 后续版本路线

### 8.1 v0.1：本地单图 MVP

目标：跑通完整链路。

内容：

- 上传单张图片；
- OCR；
- 翻译；
- 基础擦除；
- 中文写回；
- 输出下载；
- 基础错误处理和 README。

### 8.2 v0.2：质量增强

目标：提升译图可用性。

内容：

- OCR debug 可视化；
- bbox 扩张参数；
- 更稳定的字体配置；
- 更好的自动换行；
- 翻译失败局部降级；
- 输出处理中间 JSON。

### 8.3 v0.3：交互修正

目标：允许用户修正机器结果。

内容：

- 展示 OCR 文本块；
- 用户可编辑译文；
- 用户可选择跳过某些文本块；
- 重新生成输出图；
- 简单任务历史。

### 8.4 v0.4：图像修复增强

目标：提升擦字质量。

内容：

- OpenCV inpaint；
- 背景复杂度检测；
- 更合理的文字颜色选择；
- 支持半透明区域处理。

### 8.5 v0.5：批量与任务管理

目标：处理多图场景。

内容：

- 多图片上传；
- 任务队列；
- 批量下载；
- 失败任务重试；
- 存储清理策略。

### 8.6 v0.7：浏览器插件原型

目标：验证网页图片翻译入口。

内容：

- 浏览器插件右键菜单；
- 将图片发送到本地后端；
- 接收译图结果；
- 处理基础跨域和权限问题。

### 8.7 v1.0：稳定可用版本

目标：形成可长期维护的本地译图工具。

内容：

- 稳定 API；
- 完整 README；
- 配置清晰；
- 错误可诊断；
- 支持常见图片格式；
- 有基础测试；
- 本地前端体验完整；
- 插件方案有明确边界。

## 9. 开发纪律

### 9.1 每次修改前说明范围

每次修改前必须说明：

- 准备修改哪些文件；
- 每个文件为什么要改；
- 本次不改哪些相关内容；
- 是否会影响 README 或配置。

### 9.2 每次修改后说明验证方式

每次修改后必须说明：

- 运行了哪些命令；
- 测试是否通过；
- 如何手动验证；
- 如果没有验证，必须说明原因。

### 9.3 不一次性堆太多功能

每次迭代只解决一个清晰目标，例如：

- 先完成上传；
- 再接 OCR；
- 再接翻译；
- 再做绘图；
- 最后整合前端。

避免一次同时改 OCR、翻译、前端、配置和重绘。

### 9.4 优先保证可运行

任何阶段都应保证项目处于可启动状态。即使功能简单，也比功能很多但跑不起来更重要。

### 9.5 避免所有逻辑塞进 main.py

`main.py` 只负责应用入口。OCR、翻译、文件管理、图像处理必须拆到独立模块，避免后续无法维护。

### 9.6 README 必须和代码同步

当以下内容变化时，必须同步 README：

- 启动方式；
- 依赖安装；
- `.env` 配置；
- API 路径；
- 支持的图片格式；
- 已知限制；
- 验证方式。

README 是项目的使用入口，不是最后才补的装饰文档。

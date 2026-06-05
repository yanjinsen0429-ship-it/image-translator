# 本地图片翻译/译图工具 v0.3 Translation

这是一个本地运行的图片翻译/译图工具 Web 骨架。当前 v0.3 Translation 阶段在 v0.2 OCR 基础上接入翻译 Provider 架构，并支持 DeepSeek 真实翻译。

当前版本已接入真实 OCR 和 DeepSeek 翻译 Provider，但仍不做真实擦字重绘、不把中文写回图片。输出图当前仍为原图复制；真实图片回填属于 v0.4 之后的阶段。

## 功能范围

- 上传单张图片；
- 只允许 `png`、`jpg`、`jpeg`、`webp`；
- 后端保存原图到 `storage/uploads/`；
- 后端复制原图到 `storage/outputs/` 作为当前阶段输出图；
- 优先返回 PaddleOCR 识别出的真实 OCR 文本、bbox 和 confidence；
- PaddleOCR 不可用时回退到 mock OCR 文本；
- 默认返回 mock 翻译文本；
- 当 `TRANSLATION_PROVIDER=deepseek` 且 `DEEPSEEK_API_KEY` 存在时，调用 DeepSeek 返回真实翻译文本；
- 前端展示原图、输出图预览、OCR 文本、翻译结果和下载按钮；
- 上传失败或格式错误时显示清晰错误信息。

## 安装依赖

建议使用虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

v0.2 OCR 接入使用 PaddleOCR。`requirements.txt` 中包含 `paddleocr==3.6.0`，但 PaddlePaddle CPU 版建议按官方源单独安装：

```powershell
python -m pip install paddlepaddle==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
```

建议先使用 CPU 版本跑通真实 OCR，暂不默认启用 GPU/CUDA 依赖。首次运行 PaddleOCR 时可能会下载 OCR 模型，耗时取决于网络环境；如果模型下载失败，请检查网络或按 PaddleOCR 官方文档配置模型下载方式。

默认 OCR 语言为 `ch`，会优先使用更适合中文、英文混合图片的 PaddleOCR 识别模型。日文场景当前可作为混合文本尝试识别，后续还需要继续评估和优化专用日文模型配置。如需强制使用英文模型，可在启动服务前设置环境变量：

```powershell
$env:OCR_LANGUAGE = "en"
uvicorn app.main:app --reload
```

## 本地配置

项目启动时会自动读取根目录 `.env` 文件。系统环境变量优先级高于 `.env`，没有 `.env` 时会默认以 mock 模式运行。

第一次配置：

```powershell
Copy-Item .env.example .env
```

编辑 `.env`：

```dotenv
TRANSLATION_PROVIDER=deepseek
TRANSLATION_TARGET_LANGUAGE=zh-CN
DEEPSEEK_API_KEY=你的真实 key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_TIMEOUT_SECONDS=30
```

不要提交 `.env`。项目已在 `.gitignore` 中忽略 `.env`，只提交 `.env.example`。

mock 模式：

```dotenv
TRANSLATION_PROVIDER=mock
```

DeepSeek 模式：

```dotenv
TRANSLATION_PROVIDER=deepseek
DEEPSEEK_API_KEY=你的真实 key
```

## 启动项目

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

启动后打开：

```text
http://127.0.0.1:8000
```

也可以在 VS Code 集成终端中运行：

```powershell
.\scripts\run_dev.ps1
```

## 手动测试

1. 打开 `http://127.0.0.1:8000`。
2. 选择一张 `png`、`jpg`、`jpeg` 或 `webp` 图片。
3. 点击“上传并翻译”。
4. 页面应显示原图预览、输出图预览、OCR 文本、翻译结果和下载按钮。
5. 如果已安装 PaddleOCR 和 PaddlePaddle CPU 版，OCR 文本应来自图片真实识别结果。
6. 如果 PaddleOCR 不可用，页面应正常显示 mock OCR fallback 文本。
7. 如果 `.env` 中启用 DeepSeek，翻译结果中 `provider` 应显示 `deepseek`。
8. 尝试上传 `gif` 或其他不支持格式，页面应显示格式错误提示。

## 自动测试

当前测试使用 Python 标准库 `unittest`，不需要额外测试依赖。

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_config tests.test_ocr_service tests.test_translation_service
```

## 当前 mock 内容

- v0.2 起优先调用 PaddleOCR 返回真实 OCR 文本、bbox 和 confidence；
- 当 PaddleOCR 未安装、初始化失败、模型下载失败或推理失败时，会自动回退到固定 mock OCR 结果；
- `app/services/translation_service.py` 默认返回固定 mock 翻译结果；
- `TRANSLATION_PROVIDER=deepseek` 且配置真实 `DEEPSEEK_API_KEY` 时，会调用 DeepSeek 翻译；
- `app/services/image_render_service.py` 仅复制原图作为当前阶段输出图；
- 没有真实擦字或图片重绘，真实图片回填属于 v0.4。

## v0.2 OCR 验证

当前 v0.2 OCR 已通过包含中文、英文、日文的混合测试图片验证：PaddleOCR 能正常运行并返回真实 OCR 结果；默认语言配置为 `ch`。

1. 安装依赖：`python -m pip install -r requirements.txt`。
2. 单独安装 PaddlePaddle CPU 版：
   ```powershell
   python -m pip install paddlepaddle==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
   ```
3. 启动服务：`uvicorn app.main:app --reload`。
4. 打开 `http://127.0.0.1:8000`。
5. 上传一张包含清晰文字的图片。
6. 页面 OCR 文本区域应显示图片中的真实 OCR 文本，而不是固定 mock OCR 文本。
7. API 响应中的 `ocr_result.blocks[*].bbox` 应包含 `x`、`y`、`width`、`height`，尽量包含 `points`。
8. API 响应中的 `ocr_result.blocks[*].confidence` 应包含 OCR 置信度。
9. API 响应中的 `ocr_result.raw.language` 默认应为 `ch`；如设置了 `OCR_LANGUAGE`，应显示对应覆盖值。
10. mock 模式下 `translation_result.provider` 为 `mock`，DeepSeek 模式下为 `deepseek`；输出图仍为 `storage/outputs/` 下的原图复制结果。

## 项目结构

```text
app/
  main.py
  api/
    routes.py
  core/
    config.py
  services/
    file_service.py
    ocr_service.py
    paddle_ocr_service.py
    translation_service.py
    image_render_service.py
  models/
    schemas.py
frontend/
  index.html
  src/
    main.js
    styles.css
storage/
  uploads/
    .gitkeep
  outputs/
    .gitkeep
  debug/
    .gitkeep
docs/
  product_blueprint.md
  version_status_v0.1-alpha.md
  version_status_v0.2-ocr.md
tests/
  test_services.py
  test_ocr_service.py
README.md
requirements.txt
.gitignore
.env.example
```

## 已知限制

- OCR 依赖 PaddleOCR 和 PaddlePaddle，本地未安装或初始化失败时会回退到 mock OCR；
- 首次运行 PaddleOCR 可能下载模型，受网络环境影响；
- CPU 推理速度可能较慢；
- 日文漫画、竖排文字、复杂字体和艺术字识别效果可能有限，虽已通过基础中英日混合测试，后续仍可能需要继续评估和配置专用语言模型；
- 默认翻译 Provider 是 mock；配置 DeepSeek 后可返回真实翻译文本；
- 输出图只是原图复制，真实图片回填属于 v0.4；
- 没有批量上传；
- 没有任务历史；
- 没有浏览器插件。

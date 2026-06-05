# Image Translator v0.4 Inpainting

`image-translator` 是一个本地运行的图片翻译工具。

当前版本：`v0.4-inpainting`

当前阶段已经完成从图片上传到 OCR、翻译、mask 生成、OpenCV 擦字、中文译文绘制和 debug 输出的本地闭环。

## 当前功能

- PaddleOCR：识别图片文字，并返回文本、bbox、polygon 和 confidence。
- DeepSeek Translation：通过 DeepSeek Provider 返回真实中文翻译。
- OCR Polygon Detection：使用 OCR block 的 `bbox.points` 作为文字区域来源。
- Mask Generation：根据 OCR polygon 生成二值 mask。
- OpenCV Inpainting：使用 OpenCV `cv2.inpaint` 擦除原文字并修复背景。
- Chinese Text Rendering：使用 PIL 将中文译文绘制回修复后的图片。
- Debug Outputs：输出 mask、inpainted background 和 rendered image，便于逐步检查效果。

## 项目流程

```text
Image
→ OCR
→ Translation
→ Mask
→ Inpainting
→ Rendering
→ Output Image
```

当前 Web 页面仍保持原有上传与结果展示结构；v0.4 的图像处理结果主要通过 debug 输出目录验证。

## Debug 输出

真实上传流程中会生成：

```text
storage/debug/mask/{job_id}_mask.png
storage/debug/inpainted/{job_id}_inpainted.png
storage/debug/rendered/{job_id}_rendered.png
```

其中：

- `mask/`：OCR polygon 生成的文字区域 mask。
- `inpainted/`：OpenCV 擦字和背景修复后的图片。
- `rendered/`：写入中文译文后的 debug 图片。

## 安装依赖

建议使用虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

PaddleOCR 需要单独安装 PaddlePaddle CPU 版：

```powershell
python -m pip install paddlepaddle==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
```

首次运行 PaddleOCR 时可能会下载模型。默认 OCR 语言为 `ch`，更适合中英混合图片；如果强制使用英文模型，可以设置：

```powershell
$env:OCR_LANGUAGE = "en"
```

## 本地配置

项目启动时会自动读取根目录 `.env` 文件。系统环境变量优先级高于 `.env`；没有 `.env` 时默认以 mock 翻译模式运行。

第一次配置：

```powershell
Copy-Item .env.example .env
```

DeepSeek 模式示例：

```dotenv
TRANSLATION_PROVIDER=deepseek
TRANSLATION_TARGET_LANGUAGE=zh-CN
DEEPSEEK_API_KEY=你的真实 key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_TIMEOUT_SECONDS=30
```

mock 模式：

```dotenv
TRANSLATION_PROVIDER=mock
```

不要提交 `.env`。项目已在 `.gitignore` 中忽略 `.env`，只提交 `.env.example`。

## 启动项目

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

或在 VS Code 集成终端运行：

```powershell
.\scripts\run_dev.ps1
```

浏览器打开：

```text
http://127.0.0.1:8000
```

## 手动验证

1. 打开 `http://127.0.0.1:8000`。
2. 上传一张包含清晰文字的图片。
3. 页面应显示原图、输出图预览、OCR 文本、翻译结果和下载按钮。
4. 翻译结果中 `provider` 应显示当前 Provider，例如 `deepseek` 或 `mock`。
5. 检查 debug 输出：
   - `storage/debug/mask/{job_id}_mask.png`
   - `storage/debug/inpainted/{job_id}_inpainted.png`
   - `storage/debug/rendered/{job_id}_rendered.png`
6. `rendered` 图片应能看到原文区域被擦除，并写入中文译文。

## 自动测试

当前测试使用 Python 标准库 `unittest`：

```powershell
.\.venv\Scripts\python.exe -m unittest discover tests
```

## 当前目录结构

```text
app/
  main.py
  api/
    routes.py
  core/
    config.py
  models/
    schemas.py
  services/
    file_service.py
    image_render_service.py
    inpainting_service.py
    ocr_service.py
    paddle_ocr_service.py
    rendering_service.py
    translation_service.py
  utils/
    font_utils.py
    image_mask.py
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
  version_status_v0.3-translation.md
  version_status_v0.4-inpainting.md
scripts/
  run_dev.ps1
tests/
  test_config.py
  test_inpainting_service.py
  test_ocr_service.py
  test_rendering_service.py
  test_services.py
  test_translation_service.py
README.md
requirements.txt
.gitignore
.env.example
```

## 版本历史

- `v0.1-alpha`
  - FastAPI Web 骨架。
  - 单图上传。
  - mock OCR、mock 翻译、mock 输出图。

- `v0.2-ocr`
  - 接入 PaddleOCR。
  - 返回真实 OCR 文本、bbox、confidence。
  - 默认 OCR 语言为 `ch`。
  - 保留 mock OCR fallback。

- `v0.3-translation`
  - 建立 Translation Provider 架构。
  - 接入 DeepSeek Provider。
  - 支持 `.env` 自动读取。
  - 保留 mock translation fallback。

- `v0.4-inpainting`
  - 根据 OCR polygon 生成 mask。
  - 导出 debug mask。
  - 使用 OpenCV inpainting 擦除原文字。
  - 导出 debug inpainted background。
  - 使用 PIL 绘制中文译文。
  - 导出 debug rendered image。

## 已知限制

- 排版仍较粗糙。
- 小字区域字号可能偏小。
- OCR 分块会导致译文语义有时不自然。
- 按钮、Logo、特殊图形区域效果一般。
- OpenCV inpainting 对复杂背景、渐变、纹理和艺术字效果有限。
- 竖排文字、多行密集文字、描边字仍需要后续优化。
- 当前尚未实现批量处理、浏览器插件、账号系统或云端部署。

## 下一阶段规划

下一阶段建议版本：`v0.5-layout`

目标：

- 优化译文排版。
- 优化字号估算。
- 优化换行策略。
- 优化 bbox 内文字对齐。
- 评估 OCR block 合并策略，减少逐块翻译导致的语义割裂。
- 针对按钮、Logo、特殊区域增加跳过或弱处理策略。

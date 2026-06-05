# v0.3 Translation 当前版本状态

当前阶段：`v0.3 Translation`。

本阶段在 `v0.2-ocr` 基础上完成 Translation Provider 架构，并接入 DeepSeek 真实翻译 Provider。当前仍然保留 mock 翻译 fallback，输出图仍为原图复制；真实图片回填属于 v0.4 之后的阶段。

## 已实现功能

- FastAPI Web 上传流程继续可用。
- PaddleOCR OCR 流程继续可用。
- `ocr_language` 默认保持 `ch`。
- OCRResult / OCRBlock / bbox 结构继续作为翻译输入来源。
- Translation Provider 架构已建立。
- `MockTranslationProvider` 继续可用。
- `DeepSeekTranslationProvider` 已接入。
- 默认 `TRANSLATION_PROVIDER=mock`，无 API Key 时仍能运行。
- `TRANSLATION_PROVIDER=deepseek` 且 `DEEPSEEK_API_KEY` 存在时调用 DeepSeek。
- DeepSeek 失败时按 block 返回 error，不让上传流程崩溃。
- 前端展示每个 OCR block 的原文、译文、provider 和 error。
- `.env` 自动读取已支持，系统环境变量优先级高于 `.env`。
- VS Code 集成终端可直接启动本地服务。

## 未实现功能

- 真实擦字。
- 图片重绘。
- 中文回填图片。
- 批量处理。
- 浏览器插件。
- 人工校对界面。
- 账号系统。
- 云端部署。

## 本地运行流程

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

以后启动：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

或：

```powershell
.\scripts\run_dev.ps1
```

浏览器打开：

```text
http://127.0.0.1:8000
```

mock 模式：

```dotenv
TRANSLATION_PROVIDER=mock
```

DeepSeek 模式：

```dotenv
TRANSLATION_PROVIDER=deepseek
DEEPSEEK_API_KEY=你的真实 key
```

## 已知限制

- `.env` 不应提交到 Git。
- DeepSeek API Key 必须由本地 `.env` 或系统环境变量提供。
- 输出图仍为原图复制。
- 真实图片回填属于 v0.4。
- OCR 质量仍取决于 PaddleOCR 模型和图片清晰度。
- 日文漫画、竖排文字、艺术字等复杂场景仍可能需要后续优化。
- 当前没有真实擦字和中文回填，因此本阶段只代表翻译层接通。

## 下一阶段目标

- 稳定真实翻译 Provider 的错误处理和重试策略。
- 增加更多真实图片样本回归验证。
- 进入 v0.4 前再评估擦字、重绘和中文回填方案。

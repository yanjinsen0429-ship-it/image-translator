# 本地图片翻译/译图工具 v0.1 mock MVP

这是一个本地运行的最小 Web 骨架，用来验证“上传图片 -> 保存原图 -> 复制为 mock 输出图 -> 页面展示结果”的闭环。

当前版本不接入真实 OCR、不接入真实翻译 API、不做真实擦字重绘。

## 功能范围

- 上传单张图片；
- 只允许 `png`、`jpg`、`jpeg`、`webp`；
- 后端保存原图到 `storage/uploads/`；
- 后端复制原图到 `storage/outputs/` 作为 mock 输出图；
- 返回 mock OCR 文本；
- 返回 mock 翻译文本；
- 前端展示原图、mock 输出图、mock OCR、mock 翻译和下载按钮；
- 上传失败或格式错误时显示清晰错误信息。

## 安装依赖

建议使用虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 启动项目

```powershell
uvicorn app.main:app --reload
```

启动后打开：

```text
http://127.0.0.1:8000
```

## 手动测试

1. 打开 `http://127.0.0.1:8000`。
2. 选择一张 `png`、`jpg`、`jpeg` 或 `webp` 图片。
3. 点击“上传并生成 mock 结果”。
4. 页面应显示原图预览、mock 输出图预览、mock OCR 文本、mock 翻译文本和下载按钮。
5. 尝试上传 `gif` 或其他不支持格式，页面应显示格式错误提示。

## 自动测试

当前测试使用 Python 标准库 `unittest`，不需要额外测试依赖。

```powershell
python -m unittest tests.test_services -v
```

## 当前 mock 内容

- `app/services/ocr_service.py` 返回固定 mock OCR 结果；
- `app/services/translation_service.py` 返回固定 mock 翻译结果；
- `app/services/image_render_service.py` 仅复制原图作为 mock 输出图；
- 没有真实 OCR；
- 没有真实翻译 API；
- 没有真实擦字或图片重绘。

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
tests/
  test_services.py
README.md
requirements.txt
.gitignore
.env.example
```

## 已知限制

- 图片内容不会被真实识别；
- 翻译结果是固定模拟文本；
- 输出图只是原图复制；
- 没有批量上传；
- 没有任务历史；
- 没有浏览器插件。

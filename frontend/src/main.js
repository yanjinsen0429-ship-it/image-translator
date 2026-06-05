const form = document.querySelector("#uploadForm");
const input = document.querySelector("#imageInput");
const submitButton = document.querySelector("#submitButton");
const message = document.querySelector("#message");
const sourcePreview = document.querySelector("#sourcePreview");
const outputPreview = document.querySelector("#outputPreview");
const sourceEmpty = document.querySelector("#sourceEmpty");
const outputEmpty = document.querySelector("#outputEmpty");
const ocrText = document.querySelector("#ocrText");
const translationText = document.querySelector("#translationText");
const downloadLink = document.querySelector("#downloadLink");

const allowedExtensions = [".png", ".jpg", ".jpeg", ".webp"];

function setMessage(text, type = "info") {
  message.textContent = text;
  message.dataset.type = type;
}

function hasAllowedExtension(fileName) {
  const lowerName = fileName.toLowerCase();
  return allowedExtensions.some((extension) => lowerName.endsWith(extension));
}

function resetResult() {
  outputPreview.removeAttribute("src");
  outputPreview.hidden = true;
  outputEmpty.hidden = false;
  downloadLink.hidden = true;
  downloadLink.removeAttribute("href");
  ocrText.textContent = "等待上传图片";
  translationText.textContent = "等待上传图片";
}

function showLocalPreview(file) {
  sourcePreview.src = URL.createObjectURL(file);
  sourcePreview.hidden = false;
  sourceEmpty.hidden = true;
}

function renderResult(data) {
  outputPreview.src = `${data.output_file}?t=${Date.now()}`;
  outputPreview.hidden = false;
  outputEmpty.hidden = true;

  downloadLink.href = data.download_url;
  downloadLink.hidden = false;

  const ocrLines = data.ocr_result.blocks.map((block) => block.text);
  const translationLines = data.translation_result.items.map((item) => item.translated_text);

  ocrText.textContent = ocrLines.join("\n") || "没有 mock OCR 文本";
  translationText.textContent = translationLines.join("\n") || "没有 mock 翻译文本";
}

function extractErrorMessage(errorPayload) {
  if (errorPayload && errorPayload.detail && errorPayload.detail.message) {
    return errorPayload.detail.message;
  }
  return "上传失败，请检查图片格式后重试。";
}

input.addEventListener("change", () => {
  resetResult();
  const file = input.files[0];
  if (!file) {
    sourcePreview.removeAttribute("src");
    sourcePreview.hidden = true;
    sourceEmpty.hidden = false;
    setMessage("");
    return;
  }

  if (!hasAllowedExtension(file.name)) {
    setMessage("只支持 png、jpg、jpeg、webp 格式的图片。", "error");
    input.value = "";
    return;
  }

  showLocalPreview(file);
  setMessage("已选择图片，可以上传。");
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = input.files[0];

  if (!file) {
    setMessage("请先选择一张图片。", "error");
    return;
  }

  if (!hasAllowedExtension(file.name)) {
    setMessage("只支持 png、jpg、jpeg、webp 格式的图片。", "error");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);

  submitButton.disabled = true;
  setMessage("正在上传并生成 mock 输出图...");

  try {
    const response = await fetch("/api/images/translate", {
      method: "POST",
      body: formData,
    });
    const data = await response.json();

    if (!response.ok) {
      throw data;
    }

    renderResult(data);
    setMessage("mock 处理完成。", "success");
  } catch (error) {
    resetResult();
    setMessage(extractErrorMessage(error), "error");
  } finally {
    submitButton.disabled = false;
  }
});

resetResult();
sourcePreview.hidden = true;

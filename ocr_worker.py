import contextlib
import json
import os
import sys
from pathlib import Path


# PaddleOCR 实例：缓存模型对象，避免每次请求重复加载。
paddle_ocr = None
# 项目根目录：作为 runtime 和缓存目录的路径基准。
base_dir = Path(__file__).resolve().parent
# 内置运行时目录：保存项目自带 Python、模型和依赖缓存。
runtime_dir = base_dir / "runtime"
# 总缓存目录：集中放置 OCR 相关外部模型缓存。
cache_dir = runtime_dir / "cache"
# PaddleX 缓存目录：保存 PaddleOCR 官方模型文件。
paddlex_cache_dir = cache_dir / "paddlex"
# 官方模型目录：定位已下载的检测和识别模型。
official_models_dir = paddlex_cache_dir / "official_models"


# 配置运行时缓存：设置 OCR 依赖使用的本地缓存目录。
def configure_runtime_cache():
    cache_dir.mkdir(parents=True, exist_ok=True)
    paddlex_cache_dir.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(paddlex_cache_dir))
    os.environ.setdefault("HF_HOME", str(cache_dir / "huggingface"))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(cache_dir / "huggingface" / "hub"))
    os.environ.setdefault("MODELSCOPE_CACHE", str(cache_dir / "modelscope"))
    os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "huggingface")


configure_runtime_cache()


# Worker 主循环：从标准输入读取请求并输出 JSON 识别结果。
def main():
    # 输入请求行：逐行读取父进程发送的 OCR 请求。
    for line in sys.stdin:
        # 清理后请求行：去除空白并跳过空行。
        line = line.strip()

        if not line:
            continue

        try:
            # OCR 请求对象：解析输入 JSON 并提取图片路径。
            request = json.loads(line)
            # OCR 识别文本：执行图片文字识别得到输出文本。
            text = recognize_text(request.get("image", ""))
            write_response({"success": True, "text": text})
        # 请求处理异常：把 worker 内部错误返回给父进程。
        except Exception as error:
            write_response({"success": False, "text": "", "error": str(error)})


# 识别图片文本：调用 PaddleOCR 并合并识别出的文本片段。
def recognize_text(image_file):
    # 图片路径：把请求中的文件路径转换为 Path 以便校验。
    image_path = Path(image_file)

    if not image_path.exists():
        raise FileNotFoundError(f"找不到图片: {image_path}")

    # 识别文本列表：收集 OCR 返回的每一段文本。
    texts = []

    with contextlib.redirect_stdout(sys.stderr):
        # OCR 原始结果：执行模型预测并转为列表便于遍历。
        results = list(get_paddle_ocr().predict(str(image_path)))

    # 单个 OCR 结果：逐条提取 PaddleOCR 返回的结构化数据。
    for result in results:
        # 结果 JSON 数据：读取 PaddleOCR 结果中的 JSON 表示。
        data = result.json

        if callable(data):
            # 可调用 JSON 数据：兼容 json 属性为函数的结果对象。
            data = data()

        texts.extend(data.get("res", {}).get("rec_texts", []))

    return " ".join(texts)


# 获取 PaddleOCR：惰性加载并复用 OCR 模型实例。
def get_paddle_ocr():
    global paddle_ocr

    if paddle_ocr is None:
        with contextlib.redirect_stdout(sys.stderr):
            from paddleocr import PaddleOCR

            # PaddleOCR 实例：配置本地模型目录和 CPU 推理参数。
            paddle_ocr = PaddleOCR(
                text_detection_model_name="PP-OCRv4_mobile_det",
                text_detection_model_dir=str(
                    official_models_dir / "PP-OCRv4_mobile_det"
                ),
                text_recognition_model_name="PP-OCRv5_server_rec",
                text_recognition_model_dir=str(
                    official_models_dir / "PP-OCRv5_server_rec"
                ),
                device="cpu",
                enable_mkldnn=False,
                cpu_threads=4,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )

    return paddle_ocr


# 写入响应：把识别结果序列化为一行 JSON 输出给父进程。
def write_response(data):
    sys.stdout.write(json.dumps(data, ensure_ascii=True) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()

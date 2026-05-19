import contextlib
import json
import sys
from pathlib import Path


paddle_ocr = None


def main():
    for line in sys.stdin:
        line = line.strip()

        if not line:
            continue

        try:
            request = json.loads(line)
            text = recognize_text(request.get("image", ""))
            write_response({"success": True, "text": text})
        except Exception as error:
            write_response({"success": False, "text": "", "error": str(error)})


def recognize_text(image_file):
    image_path = Path(image_file)

    if not image_path.exists():
        raise FileNotFoundError(f"找不到图片: {image_path}")

    texts = []

    with contextlib.redirect_stdout(sys.stderr):
        results = list(get_paddle_ocr().predict(str(image_path)))

    for result in results:
        data = result.json

        if callable(data):
            data = data()

        texts.extend(data.get("res", {}).get("rec_texts", []))

    return " ".join(texts)


def get_paddle_ocr():
    global paddle_ocr

    if paddle_ocr is None:
        with contextlib.redirect_stdout(sys.stderr):
            from paddleocr import PaddleOCR

            paddle_ocr = PaddleOCR(
                text_detection_model_name="PP-OCRv4_mobile_det",
                text_recognition_model_name="PP-OCRv5_server_rec",
                device="cpu",
                enable_mkldnn=False,
                cpu_threads=4,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )

    return paddle_ocr


def write_response(data):
    sys.stdout.write(json.dumps(data, ensure_ascii=True) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()

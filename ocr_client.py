import json
import subprocess
import threading
from pathlib import Path

import log


base_dir = Path(__file__).resolve().parent
worker_python = base_dir / ".venv-ocr" / "Scripts" / "python.exe"
worker_script = base_dir / "ocr_worker.py"

ocr_process = None
ocr_lock = threading.Lock()
missing_environment_logged = False


def recognize_text(image_file):
    with ocr_lock:
        text = send_request(image_file)

        if text is not None:
            return text

        stop_ocr_worker()
        text = send_request(image_file)

        if text is None:
            return ""

        return text


def send_request(image_file):
    process = start_ocr_worker()

    if process is None:
        return ""

    request = {"image": str(Path(image_file).resolve())}

    try:
        process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
        process.stdin.flush()
        line = read_response_line(process)
    except Exception as error:
        log.write(f"OCR子进程通信异常: {error}")
        return None

    if not line:
        log.write("OCR子进程无响应")
        return None

    response = json.loads(line)

    if not response.get("success"):
        log.write(f"OCR识别失败: {response.get('error', '未知错误')}")
        return ""

    return response.get("text", "")


def read_response_line(process):
    for _ in range(200):
        line = process.stdout.readline()

        if not line:
            return ""

        line = line.strip()

        if line.startswith("{"):
            return line

    log.write("OCR子进程输出过多，未找到JSON响应")
    return ""


def start_ocr_worker():
    global ocr_process
    global missing_environment_logged

    if ocr_process and ocr_process.poll() is None:
        return ocr_process

    ocr_process = None

    if not worker_python.exists():
        if not missing_environment_logged:
            log.write("找不到 OCR 环境，请先运行 setup_ocr.bat")
            missing_environment_logged = True
        return None

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    ocr_process = subprocess.Popen(
        [str(worker_python), str(worker_script)],
        cwd=str(base_dir),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=creationflags,
    )
    log.write(f"OCR子进程启动 pid={ocr_process.pid}")

    return ocr_process


def stop_ocr_worker():
    global ocr_process

    process = ocr_process
    ocr_process = None

    if not process:
        return

    pid = process.pid

    try:
        if process.stdin:
            process.stdin.close()
    except Exception:
        pass

    if process.poll() is None:
        process.terminate()

        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)

    log.write(f"OCR子进程已停止 pid={pid}")

import json
import os
import subprocess
import threading
from pathlib import Path

import log


# 项目根目录：作为 OCR 运行时和工作脚本路径的基准。
base_dir = Path(__file__).resolve().parent
# OCR 子进程 Python：指向项目内置的 Python 解释器。
worker_python = base_dir / "runtime" / "python310" / "python.exe"
# OCR 子进程脚本：指向负责实际识别的 worker 入口。
worker_script = base_dir / "ocr_worker.py"

# OCR 子进程对象：缓存当前存活的 OCR worker 进程。
ocr_process = None
# OCR 请求锁：串行化 stdin/stdout 通信，避免响应串线。
ocr_lock = threading.Lock()
# 环境缺失日志标记：避免重复输出运行时缺失提示。
missing_environment_logged = False


# 识别文本：向 OCR worker 发送图片并在失败时重启重试一次。
def recognize_text(image_file):
    with ocr_lock:
        # 首次识别文本：保存第一次 worker 请求返回的识别结果。
        text = send_request(image_file)

        if text is not None:
            return text

        stop_ocr_worker()
        # 重试识别文本：worker 重启后再次请求 OCR 结果。
        text = send_request(image_file)

        if text is None:
            return ""

        return text


# 发送 OCR 请求：把图片路径写入子进程并读取 JSON 响应。
def send_request(image_file):
    # OCR 子进程：确保有可用 worker 处理识别请求。
    process = start_ocr_worker()

    if process is None:
        return ""

    # OCR 请求数据：封装待识别图片的绝对路径。
    request = {"image": str(Path(image_file).resolve())}

    try:
        process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
        process.stdin.flush()
        # OCR 响应行：读取 worker 输出的单行 JSON 响应。
        line = read_response_line(process)
    # OCR 通信异常：记录 stdin/stdout 交互失败原因。
    except Exception as error:
        log.write(f"OCR子进程通信异常: {error}")
        return None

    if not line:
        log.write("OCR子进程无响应")
        return None

    # OCR 响应对象：解析 worker 返回的 JSON 结果。
    response = json.loads(line)

    if not response.get("success"):
        log.write(f"OCR识别失败: {response.get('error', '未知错误')}")
        return ""

    return response.get("text", "")


# 读取响应行：跳过非 JSON 输出并提取 worker 的响应。
def read_response_line(process):
    # 响应读取次数：限制最多读取行数，避免 worker 噪声无限阻塞。
    for _ in range(200):
        # 子进程输出行：读取 OCR worker 的一行标准输出。
        line = process.stdout.readline()

        if not line:
            return ""

        # 清理后输出行：去除首尾空白后判断是否为 JSON。
        line = line.strip()

        if line.startswith("{"):
            return line

    log.write("OCR子进程输出过多，未找到JSON响应")
    return ""


# 启动 OCR worker：惰性创建并复用 OCR 子进程。
def start_ocr_worker():
    global ocr_process
    global missing_environment_logged

    if ocr_process and ocr_process.poll() is None:
        return ocr_process

    # OCR 子进程引用：旧进程不可用时先清空缓存。
    ocr_process = None

    if not worker_python.exists():
        if not missing_environment_logged:
            log.write("找不到项目内 Python 运行时，请先运行 setup_ocr.bat")
            # 环境缺失日志标记：记录已经提示过运行时缺失。
            missing_environment_logged = True
        return None

    # 子进程创建标志：在 Windows 下尽量隐藏 worker 控制台窗口。
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    # OCR 子进程对象：启动项目内置 Python 执行 worker 脚本。
    ocr_process = subprocess.Popen(
        [str(worker_python), str(worker_script)],
        cwd=str(base_dir),
        env=create_worker_env(),
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


# 创建 worker 环境：为 OCR 模型和缓存设置隔离目录。
def create_worker_env():
    # 子进程环境变量：复制当前环境后补充 OCR 缓存路径。
    env = os.environ.copy()
    # OCR 缓存目录：集中保存 Paddle、HuggingFace 和 ModelScope 缓存。
    cache_dir = base_dir / "runtime" / "cache"
    # PaddleX 缓存变量：指定 PaddleX 模型缓存根目录。
    env["PADDLE_PDX_CACHE_HOME"] = str(cache_dir / "paddlex")
    # HuggingFace 缓存变量：指定 HuggingFace 通用缓存目录。
    env["HF_HOME"] = str(cache_dir / "huggingface")
    # HuggingFace Hub 缓存变量：指定模型仓库缓存目录。
    env["HUGGINGFACE_HUB_CACHE"] = str(cache_dir / "huggingface" / "hub")
    # ModelScope 缓存变量：指定 ModelScope 模型缓存目录。
    env["MODELSCOPE_CACHE"] = str(cache_dir / "modelscope")
    # Paddle 模型源变量：指定 PaddleX 优先从 HuggingFace 取模型。
    env["PADDLE_PDX_MODEL_SOURCE"] = "huggingface"
    return env


# 停止 OCR worker：关闭当前子进程并清理全局引用。
def stop_ocr_worker():
    global ocr_process

    # 待停止进程：保留当前 worker 引用以执行关闭流程。
    process = ocr_process
    # OCR 子进程引用：停止流程开始后立即清空全局缓存。
    ocr_process = None

    if not process:
        return

    # 待停止进程号：用于日志记录和 taskkill 调用。
    pid = process.pid

    close_stdin(process)
    terminate_process_tree(process)

    log.write(f"OCR子进程已停止 pid={pid}")


# 关闭标准输入：通知 worker 不再接收新的请求。
def close_stdin(process):
    try:
        if process.stdin:
            process.stdin.close()
    except Exception:
        pass


# 终止进程树：优先使用 taskkill 清理 worker 及其子进程。
def terminate_process_tree(process):
    if process.poll() is not None:
        return

    # taskkill 输出目标：静默吞掉终止命令的标准输出和错误输出。
    taskkill = getattr(subprocess, "DEVNULL", None)

    try:
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=taskkill,
            stderr=taskkill,
            check=False,
        )
        process.wait(timeout=3)
        return
    except Exception:
        pass

    if process.poll() is None:
        process.terminate()

        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)

from datetime import datetime
from pathlib import Path
import sys


# 日志文件路径：保存程序运行过程中的控制台和操作日志。
log_file = Path(__file__).resolve().parent.parent / "log.txt"


# 切换日志文件：多开时每个进程写自己的实例或账号目录。
def set_log_file(path, clear=False):
    global log_file

    log_file = Path(path)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    if clear:
        log_file.write_text("", encoding="utf-8")


# 清空当前日志文件：供网页日志区手动清空使用。
def clear():
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text("", encoding="utf-8")


# 按运行目录切换日志：日志文件固定叫 log.txt。
def use_run_dir(run_dir, clear=False):
    set_log_file(Path(run_dir) / "log.txt", clear=clear)


# 启动日志：清空旧日志并写入新的开始标记。
def start_log():
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text("", encoding="utf-8")
    write("日志开始")


# 写入日志：格式化消息并追加到日志文件。
def write(message):
    # 格式化日志行：加入时间戳后的完整日志文本。
    line = format_line(message)
    write_line(line)


# 写入控制台日志：同时写入文件和可用的终端输出。
def write_console(message):
    # 格式化日志行：加入时间戳后供文件和终端复用。
    line = format_line(message)
    write_line(line)
    print_console(line)


# 格式化日志行：为原始消息添加当前时间戳。
def format_line(message):
    # 当前时间文本：记录日志产生的小时、分钟和秒。
    now = datetime.now().strftime("%H:%M:%S")
    return f"[{now}] {message}"


# 追加日志行：把单行文本写入日志文件末尾。
def write_line(line):
    # 日志文件句柄：以追加模式写入 UTF-8 日志内容。
    with log_file.open("a", encoding="utf-8") as file:
        file.write(line + "\n")


# 打印控制台：仅在标准输出是交互终端时打印日志。
def print_console(line):
    if not sys.stdout or not sys.stdout.isatty():
        return

    print(line, flush=True)


# 读取日志：返回当前日志文件的全部文本内容。
def read():
    if not log_file.exists():
        return ""

    return log_file.read_text(encoding="utf-8")

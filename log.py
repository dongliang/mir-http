from datetime import datetime
from pathlib import Path


log_file = Path(__file__).resolve().parent / "log.txt"


def start_log():
    log_file.write_text("", encoding="utf-8")
    write("日志开始")


def write(message):
    now = datetime.now().strftime("%H:%M:%S")
    line = f"[{now}] {message}"

    with log_file.open("a", encoding="utf-8") as file:
        file.write(line + "\n")


def read():
    if not log_file.exists():
        return ""

    return log_file.read_text(encoding="utf-8")

from datetime import datetime
from pathlib import Path
import sys


log_file = Path(__file__).resolve().parent / "log.txt"


def start_log():
    log_file.write_text("", encoding="utf-8")
    write("日志开始")


def write(message):
    line = format_line(message)
    write_line(line)


def write_console(message):
    line = format_line(message)
    write_line(line)
    print_console(line)


def format_line(message):
    now = datetime.now().strftime("%H:%M:%S")
    return f"[{now}] {message}"


def write_line(line):
    with log_file.open("a", encoding="utf-8") as file:
        file.write(line + "\n")


def print_console(line):
    if not sys.stdout or not sys.stdout.isatty():
        return

    print(line, flush=True)


def read():
    if not log_file.exists():
        return ""

    return log_file.read_text(encoding="utf-8")

from datetime import datetime
from pathlib import Path


text_box = None
log_file = Path(__file__).resolve().parent / "log.txt"


def set_text_box(box):
    global text_box
    text_box = box


def start_log():
    log_file.write_text("", encoding="utf-8")
    write("日志开始")


def write(message):
    now = datetime.now().strftime("%H:%M:%S")
    line = f"[{now}] {message}"

    with log_file.open("a", encoding="utf-8") as file:
        file.write(line + "\n")

    if text_box:
        text_box.insert("end", line + "\n")
        text_box.see("end")

import re
import time

import dm
import log


last_debug_time = 0


def get_map_coordinate():
    text, region_text = get_map_coordinate_text()
    map_name, x, y = parse_map_coordinate_text(text)
    write_debug_once_per_second(text, region_text, map_name, x, y)
    return map_name, x, y


def get_map_coordinate_text():
    if not dm.is_window_bound():
        return "", "未绑定"

    dm_object = dm.get_dm()
    width, height = dm.get_bound_client_size()

    regions = [
        ("map_line", 0, max(0, height - 36), min(width, 280), height - 1),
        ("bottom_left", 0, max(0, height - 70), min(width, 380), height - 1),
    ]

    last_text = ""
    last_region_text = ""

    for name, x1, y1, x2, y2 in regions:
        region_text = f"{name}=({x1},{y1},{x2},{y2}) size={width}x{height}"

        try:
            text = dm_object.Ocr(x1, y1, x2, y2, "ffffff-808080", 0.5)
        except Exception as error:
            text = f"OCR异常: {error}"

        last_text = text
        last_region_text = region_text

        map_name, x, y = parse_map_coordinate_text(text)

        if x and y:
            return text, region_text

    return last_text, last_region_text


def parse_map_coordinate_text(text):
    numbers = re.findall(r"\d+", text)

    if len(numbers) < 2:
        return "", "", ""

    x = numbers[-2]
    y = numbers[-1]

    first_number = re.search(r"\d+", text)
    map_name = ""

    if first_number:
        map_name = text[: first_number.start()]
        map_name = re.sub(r"[\s:：,，/\\]+", "", map_name)

    return map_name, x, y


def write_debug_once_per_second(text, region_text, map_name, x, y):
    global last_debug_time

    now = time.time()

    if now - last_debug_time < 1:
        return

    last_debug_time = now
    log.write(f"地图OCR 区域={region_text} 原文={text!r} 解析=({map_name}, {x}, {y})")

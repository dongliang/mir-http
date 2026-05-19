import re
import threading
from pathlib import Path

import dm
import ocr_client


coordinate_image = Path(__file__).resolve().parent / "screenshots" / "map_coordinate.bmp"
coordinate_lock = threading.Lock()


def get_map_coordinate():
    with coordinate_lock:
        return read_map_coordinate()


def read_map_coordinate():
    if not dm.is_window_bound():
        return "", "", ""

    width, height = dm.get_bound_client_size()
    if width <= 0 or height <= 0:
        return "", "", ""

    x1, y1 = 0, max(0, height - 32)
    x2, y2 = min(width - 1, 170), height - 1

    coordinate_image.parent.mkdir(exist_ok=True)
    result = dm.get_dm().Capture(x1, y1, x2, y2, str(coordinate_image))

    if result != 1:
        return "", "", ""

    text = ocr_client.recognize_text(coordinate_image)
    return parse_map_coordinate_text(text)

def parse_map_coordinate_text(text):
    pairs = re.findall(r"([^\d\s:：,，/\\]{0,20})\s*(\d{1,4})\s*[:：,，]\s*(\d{1,4})", text)

    if pairs:
        map_name, x, y = pairs[-1]
        return map_name, x, y

    numbers = list(re.finditer(r"\d+", text))

    if len(numbers) < 2:
        return "", "", ""

    x = numbers[-2].group()
    y = numbers[-1].group()
    map_name = text[: numbers[-2].start()]
    map_name = re.sub(r"[\s:：,，/\\]+", "", map_name)

    return map_name, x, y

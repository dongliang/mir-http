import re
import threading
from pathlib import Path

import dm
import ocr_client


coordinate_image = Path(__file__).resolve().parent / "screenshots" / "map_coordinate.bmp"
coordinate_lock = threading.Lock()

directions = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
    "up_left": (-1, -1),
    "up_right": (1, -1),
    "down_left": (-1, 1),
    "down_right": (1, 1),
}

walk_click_directions = {
    "up": (0, -2),
    "down": (0, 1),
    "left": (-1, -1),
    "right": (1, -1),
    "up_left": (-1, -2),
    "up_right": (1, -2),
    "down_left": (-1, 0),
    "down_right": (1, 0),
}

move_actions = {
    "walk": {"button": "left", "offset": 65, "step": 1},
    "run": {"button": "right", "offset": 130, "step": 2},
}


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


def move_player(action, direction):
    if action not in move_actions:
        return {"success": False, "message": f"未知移动类型: {action}"}

    if direction not in directions:
        return {"success": False, "message": f"未知方向: {direction}"}

    if not dm.is_window_bound():
        return {"success": False, "message": "还没有绑定窗口"}

    width, height = dm.get_bound_client_size()

    if width <= 0 or height <= 0:
        return {"success": False, "message": f"窗口尺寸异常 size={width}x{height}"}

    move = calculate_move(action, direction, width, height)
    success, message = dm.click_bound_client(move["click_x"], move["click_y"], move["button"])

    return {
        "success": success,
        "action": action,
        "direction": direction,
        "click_x": move["click_x"],
        "click_y": move["click_y"],
        "delta_x": move["delta_x"],
        "delta_y": move["delta_y"],
        "message": message,
    }


def calculate_move(action, direction, width, height):
    dx, dy = directions[direction]
    config = move_actions[action]
    click_dx, click_dy = get_click_direction(action, direction)
    center_x = width // 2
    center_y = height // 2

    return {
        "button": config["button"],
        "click_x": center_x + click_dx * config["offset"],
        "click_y": center_y + click_dy * config["offset"],
        "delta_x": dx * config["step"],
        "delta_y": dy * config["step"],
    }


def get_click_direction(action, direction):
    if action == "walk":
        return walk_click_directions[direction]

    return directions[direction]

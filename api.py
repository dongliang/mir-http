import re
import threading
from pathlib import Path

import op
import ocr_client


# 地图坐标截图路径：保存游戏底部坐标区域截图，供 OCR 识别使用。
coordinate_image = Path(__file__).resolve().parent / "screenshots" / "map_coordinate.bmp"
# 坐标读取锁：串行化截图和 OCR 流程，避免并发读写同一张截图。
coordinate_lock = threading.Lock()
# 底部界面高度：估算游戏底栏高度，用来计算角色移动点击原点。
BOTTOM_UI_HEIGHT = 155

# 移动方向向量：把方向名称映射为地图坐标变化量。
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

# 走路点击方向：描述走路动作在屏幕上的点击方向。
walk_click_directions = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
    "up_left": (-1, -1),
    "up_right": (1, -1),
    "down_left": (-1, 1),
    "down_right": (1, 1),
}

# 跑步点击方向：描述跑步动作在屏幕上的点击方向。
run_click_directions = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
    "up_left": (-1, -1),
    "up_right": (1, -1),
    "down_left": (-1, 1),
    "down_right": (1, 1),
}

# 移动动作配置：定义移动动作使用的鼠标按钮、点击距离和坐标步长。
move_actions = {
    "walk": {"button": "left", "offset": 65, "step": 1},
    "run": {"button": "right", "offset": 130, "step": 2},
}


# 获取地图坐标：对外提供线程安全的地图坐标读取入口。
def get_map_coordinate():
    with coordinate_lock:
        return read_map_coordinate()


# 读取地图坐标：从绑定窗口截图底部区域并交给 OCR 解析坐标。
def read_map_coordinate():
    if not op.is_window_bound():
        return "", "", ""

    # 绑定窗口尺寸：用于确定坐标区域截图范围。
    width, height = op.get_bound_client_size()
    if width <= 0 or height <= 0:
        return "", "", ""

    # 截图左上角：从窗口底部开始裁剪坐标显示区域。
    x1, y1 = 0, max(0, height - 32)
    # 截图右下角：限制坐标区域宽度并覆盖底部最后一行。
    x2, y2 = min(width - 1, 170), height - 1

    coordinate_image.parent.mkdir(exist_ok=True)
    # 截图结果：记录 OP 截图接口是否成功保存坐标图片。
    result = op.get_op().Capture(x1, y1, x2, y2, str(coordinate_image))

    if result != 1:
        return "", "", ""

    # OCR 文本：承载坐标截图识别出的原始文字。
    text = ocr_client.recognize_text(coordinate_image)
    return parse_map_coordinate_text(text)

# 解析地图坐标文本：从 OCR 文本中提取地图名和 x/y 坐标。
def parse_map_coordinate_text(text):
    # 坐标匹配组：优先匹配“地图名 x:y”形式的 OCR 结果。
    pairs = re.findall(r"([^\d\s:：,，/\\]{0,20})\s*(\d{1,4})\s*[:：,，]\s*(\d{1,4})", text)

    if pairs:
        # 最后一组坐标：选择最靠后的匹配结果作为当前地图坐标。
        map_name, x, y = pairs[-1]
        return map_name, x, y

    # 数字匹配列表：在宽松模式下从文本中寻找所有数字片段。
    numbers = list(re.finditer(r"\d+", text))

    if len(numbers) < 2:
        return "", "", ""

    # 横坐标文本：取倒数第二个数字作为地图 x 坐标。
    x = numbers[-2].group()
    # 纵坐标文本：取最后一个数字作为地图 y 坐标。
    y = numbers[-1].group()
    # 地图名前缀：取坐标数字之前的文本作为候选地图名。
    map_name = text[: numbers[-2].start()]
    # 清理后地图名：去除分隔符和空白，降低 OCR 噪声影响。
    map_name = re.sub(r"[\s:：,，/\\]+", "", map_name)

    return map_name, x, y


# 移动角色：校验动作和方向后在绑定窗口内执行点击移动。
def move_player(action, direction):
    if action not in move_actions:
        return {"success": False, "message": f"未知移动类型: {action}"}

    if direction not in directions:
        return {"success": False, "message": f"未知方向: {direction}"}

    if not op.is_window_bound():
        return {"success": False, "message": "还没有绑定窗口"}

    # 绑定窗口尺寸：用于把动作方向换算成屏幕点击坐标。
    width, height = op.get_bound_client_size()

    if width <= 0 or height <= 0:
        return {"success": False, "message": f"窗口尺寸异常 size={width}x{height}"}

    # 移动点击参数：保存本次动作的按钮、坐标和地图增量。
    move = calculate_move(action, direction, width, height)
    # 点击执行结果：记录 OP 鼠标点击是否成功及其说明。
    success, message = op.click_bound_client(move["click_x"], move["click_y"], move["button"])
    # 返回消息：补充窗口尺寸，便于排查点击位置问题。
    message = f"{message} client_size={width}x{height}"

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


# 计算移动点击：把动作和方向转换为客户端内的点击坐标。
def calculate_move(action, direction, width, height):
    # 地图方向增量：描述移动后地图坐标预期变化。
    dx, dy = directions[direction]
    # 动作配置：读取按钮、点击距离和步长等动作参数。
    config = move_actions[action]
    # 点击方向向量：描述鼠标在屏幕上应该偏移的方向。
    click_dx, click_dy = get_click_direction(action, direction)
    # 移动原点：以游戏可操作区域中心作为点击基准。
    origin_x, origin_y = get_move_origin(width, height)

    return {
        "button": config["button"],
        "click_x": round(origin_x + click_dx * config["offset"]),
        "click_y": round(origin_y + click_dy * config["offset"]),
        "delta_x": dx * config["step"],
        "delta_y": dy * config["step"],
    }


# 获取移动原点：根据窗口尺寸和底部 UI 高度计算可操作区域中心。
def get_move_origin(width, height):
    # 可操作区域高度：排除底部 UI 后得到角色移动区域高度。
    play_area_height = max(1, height - BOTTOM_UI_HEIGHT)
    return width // 2, play_area_height // 2


# 获取点击方向：根据走路或跑步动作选择对应点击方向表。
def get_click_direction(action, direction):
    if action == "walk":
        return walk_click_directions[direction]

    return run_click_directions[direction]

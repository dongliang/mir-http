import re
import threading
import time
from pathlib import Path

import ocr_client
import op
import overlay
import win32


# 项目根目录：作为截图和运行资源路径的基准目录。
base_dir = Path(__file__).resolve().parent
# 截图目录：保存绑定窗口截图和调试图片。
screenshot_dir = base_dir / "screenshots"
# 地图坐标截图路径：保存游戏底部坐标区域截图，供 OCR 识别使用。
coordinate_image = screenshot_dir / "map_coordinate.bmp"
# 坐标读取锁：串行化截图和 OCR 流程，避免并发读写同一张截图。
coordinate_lock = threading.Lock()
# 底部界面高度：估算游戏底栏高度，用来计算角色移动点击原点。
BOTTOM_UI_HEIGHT = 155
# 默认键盘测试键：用于页面测试按钮验证后台键盘输入链路。
keyboard_test_key = "M"

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

# 常用虚拟键码表：HTTP API 可以用这些名字指定按键。
keyboard_key_map = {
    "BACKSPACE": 0x08,
    "TAB": 0x09,
    "ENTER": 0x0D,
    "RETURN": 0x0D,
    "SHIFT": 0x10,
    "CTRL": 0x11,
    "CONTROL": 0x11,
    "ALT": 0x12,
    "PAUSE": 0x13,
    "CAPSLOCK": 0x14,
    "CAPS": 0x14,
    "ESC": 0x1B,
    "ESCAPE": 0x1B,
    "SPACE": 0x20,
    "PAGEUP": 0x21,
    "PAGEDOWN": 0x22,
    "END": 0x23,
    "HOME": 0x24,
    "LEFT": 0x25,
    "UP": 0x26,
    "RIGHT": 0x27,
    "DOWN": 0x28,
    "INSERT": 0x2D,
    "INS": 0x2D,
    "DELETE": 0x2E,
    "DEL": 0x2E,
    ";": 0xBA,
    "=": 0xBB,
    ",": 0xBC,
    "-": 0xBD,
    ".": 0xBE,
    "/": 0xBF,
    "`": 0xC0,
    "[": 0xDB,
    "\\": 0xDC,
    "]": 0xDD,
    "'": 0xDE,
}

for key_code in range(ord("A"), ord("Z") + 1):
    keyboard_key_map[chr(key_code)] = key_code

for key_code in range(ord("0"), ord("9") + 1):
    keyboard_key_map[chr(key_code)] = key_code

for key_index in range(1, 13):
    keyboard_key_map[f"F{key_index}"] = 0x70 + key_index - 1


# 启动 OP：业务层统一入口，初始化 OP 并规整返回结构。
def start_op():
    try:
        success, version, message = op.start_op()
        return {
            "success": success,
            "version": version,
            "message": message,
        }
    # OP 初始化异常：捕获底层依赖或加载失败的错误信息。
    except Exception as error:
        return {
            "success": False,
            "version": "",
            "message": f"OP 初始化异常: {error}",
        }


# 绑定窗口：按标题关键字查找窗口并交给 OP 绑定。
def bind_window(keyword):
    # 绑定关键字：清理外部输入，避免空白影响窗口匹配。
    keyword = (keyword or "").strip()

    if not keyword:
        return {
            "success": False,
            "title": "",
            "message": "绑定关键字不能为空",
        }

    # 目标窗口：保存按标题关键字找到的窗口句柄和标题。
    hwnd, title = win32.find_window_by_title(keyword)

    if not hwnd:
        return {
            "success": False,
            "title": "",
            "message": f"找不到标题包含 {keyword} 的窗口",
        }

    success, title, message = op.bind_window(hwnd, title)
    return {
        "success": success,
        "title": title,
        "message": message,
    }


# 解绑窗口：释放 OP 绑定并隐藏现有点击提示。
def unbind_window():
    success, title, message = op.unbind_window()

    if success:
        hide_overlay_safely()

    return {
        "success": success,
        "title": title,
        "message": message,
    }


# 应用运行设置：把内存中的应用设置同步到业务辅助模块。
def apply_app_settings(app_settings):
    if not app_settings.get("overlay_enabled", True):
        hide_overlay_safely()


# Overlay 切换：反转点击提示开关并返回页面状态消息。
def toggle_overlay(app_settings):
    # Overlay 开关设置：反转当前点击提示启用状态。
    app_settings["overlay_enabled"] = not app_settings["overlay_enabled"]
    apply_app_settings(app_settings)
    # Overlay 状态文本：把布尔开关转换为用户可读中文状态。
    state = "开启" if app_settings["overlay_enabled"] else "关闭"
    # Overlay 返回消息：描述本次切换后的提示状态。
    message = f"点击提示 Overlay 已{state}"
    return {
        "success": True,
        "message": message,
    }


# 获取状态：聚合玩家坐标、绑定窗口和应用设置。
def get_status(player_info, app_settings):
    return {
        "player": {
            "map_name": player_info["map_name"],
            "x": player_info["x"],
            "y": player_info["y"],
        },
        "bound_window": op.get_bound_window(),
        "settings": {
            "overlay_enabled": app_settings["overlay_enabled"],
        },
    }


# 获取绑定窗口尺寸：根据绑定模式修正 Win32 客户区尺寸。
def get_bound_client_size():
    # 绑定窗口状态：读取当前 hwnd 供 Win32 查询。
    bound = op.get_bound_window()
    raw_width, raw_height = win32.get_client_size(bound["hwnd"])

    if raw_width <= 0 or raw_height <= 0:
        return raw_width, raw_height

    # 坐标缩放比例：补偿部分绑定模式下 OP 坐标减半的问题。
    scale = op.get_bind_coordinate_scale()
    return max(1, round(raw_width * scale)), max(1, round(raw_height * scale))


# 截图：截取当前绑定窗口并返回截图保存路径。
def capture_screenshot():
    if not op.is_window_bound():
        return {
            "success": False,
            "path": "",
            "message": "还没有绑定窗口",
        }

    # 绑定窗口尺寸：确定截图范围是否有效。
    width, height = get_bound_client_size()

    if width <= 0 or height <= 0:
        return {
            "success": False,
            "path": "",
            "message": f"窗口尺寸异常 size={width}x{height}",
        }

    # 截图文件路径：为本次截图选择一个未占用的文件名。
    screenshot_file = get_next_screenshot_file()
    success, message = op.capture_bound_client(0, 0, width, height, screenshot_file)

    if success and screenshot_file.exists():
        return {
            "success": True,
            "path": str(screenshot_file),
            "message": f"绑定窗口截图成功 path={screenshot_file} size={width}x{height} {message}",
        }

    return {
        "success": False,
        "path": str(screenshot_file),
        "message": message,
    }


# 获取下一张截图文件：在截图目录中生成递增编号文件名。
def get_next_screenshot_file():
    screenshot_dir.mkdir(exist_ok=True)

    # 截图序号：从 1 开始递增查找可用文件名。
    index = 1

    while True:
        # 候选截图文件：保存当前序号对应的截图路径。
        screenshot_file = screenshot_dir / f"screenshot_{index:04d}.bmp"

        if not screenshot_file.exists():
            return screenshot_file

        # 下一截图序号：当前文件已存在时继续向后查找。
        index += 1


# 获取地图坐标：对外提供线程安全的地图坐标读取入口。
def get_map_coordinate():
    with coordinate_lock:
        return read_map_coordinate()


# 读取地图坐标：从绑定窗口截图底部区域并交给 OCR 解析坐标。
def read_map_coordinate():
    if not op.is_window_bound():
        return "", "", ""

    # 绑定窗口尺寸：用于确定坐标区域截图范围。
    width, height = get_bound_client_size()
    if width <= 0 or height <= 0:
        return "", "", ""

    # 截图左上角：从窗口底部开始裁剪坐标显示区域。
    x1, y1 = 0, max(0, height - 32)
    # 截图右下角：限制坐标区域宽度并覆盖底部最后一行。
    x2, y2 = min(width - 1, 170), height - 1

    coordinate_image.parent.mkdir(exist_ok=True)
    success, _ = op.capture_bound_client(x1, y1, x2, y2, coordinate_image)

    if not success:
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
def move_player(action, direction, show_overlay=True):
    if action not in move_actions:
        return {"success": False, "message": f"未知移动类型: {action}"}

    if direction not in directions:
        return {"success": False, "message": f"未知方向: {direction}"}

    if not op.is_window_bound():
        return {"success": False, "message": "还没有绑定窗口"}

    # 绑定窗口尺寸：用于把动作方向换算成屏幕点击坐标。
    width, height = get_bound_client_size()

    if width <= 0 or height <= 0:
        return {"success": False, "message": f"窗口尺寸异常 size={width}x{height}"}

    # 移动点击参数：保存本次动作的按钮、坐标和地图增量。
    move = calculate_move(action, direction, width, height)

    if show_overlay:
        hide_overlay_safely()

    # 点击执行结果：记录 OP 鼠标点击是否成功及其说明。
    success, message = op.click_bound_client(move["click_x"], move["click_y"], move["button"])

    if success and show_overlay:
        show_click_overlay(move["click_x"], move["click_y"])

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


# 键盘输入：业务层统一入口，解析按键名并按稳定节奏发送后台输入。
def press_keyboard(key, hold_ms=120, repeat=1, interval_ms=80):
    if not op.is_window_bound():
        return {
            "success": False,
            "key": str(key or "").strip(),
            "hold_ms": hold_ms,
            "repeat": repeat,
            "interval_ms": interval_ms,
            "message": "还没有绑定窗口",
        }

    try:
        key_name, vk_code = resolve_keyboard_key(key)
        hold_seconds = normalize_number(hold_ms, 120, 20, 2000) / 1000
        interval_seconds = normalize_number(interval_ms, 80, 0, 2000) / 1000
        repeat_count = normalize_number(repeat, 1, 1, 100)
    except ValueError as error:
        return {
            "success": False,
            "key": str(key or "").strip(),
            "hold_ms": hold_ms,
            "repeat": repeat,
            "interval_ms": interval_ms,
            "message": str(error),
        }

    for index in range(repeat_count):
        success, message = op.press_bound_key(vk_code, key_name, hold_seconds)

        if not success:
            return {
                "success": False,
                "key": key_name,
                "hold_ms": round(hold_seconds * 1000),
                "repeat": repeat_count,
                "interval_ms": round(interval_seconds * 1000),
                "message": f"后台键盘输入失败 key={key_name} repeat={index + 1}/{repeat_count} detail={message}",
            }

        if index < repeat_count - 1 and interval_seconds > 0:
            time.sleep(interval_seconds)

    message = f"后台键盘输入成功 key={key_name} vk={vk_code} repeat={repeat_count} hold_ms={round(hold_seconds * 1000)} interval_ms={round(interval_seconds * 1000)} mode={op.format_active_bind_mode()}"
    return {
        "success": True,
        "key": key_name,
        "hold_ms": round(hold_seconds * 1000),
        "repeat": repeat_count,
        "interval_ms": round(interval_seconds * 1000),
        "message": message,
    }


# 测试键盘输入：使用默认测试键验证当前游戏窗口是否能收到后台按键。
def test_keyboard():
    return press_keyboard(keyboard_test_key)


# 解析键盘按键：支持 M、F9、ENTER、0x4D 或十进制虚拟键码。
def resolve_keyboard_key(key):
    key_text = str(key or "").strip()

    if not key_text:
        raise ValueError("key 不能为空")

    upper_key = key_text.upper()

    if upper_key.startswith("VK_"):
        upper_key = upper_key[3:]

    if upper_key.startswith("0X"):
        return upper_key, int(upper_key, 16)

    if upper_key.isdigit():
        return upper_key, int(upper_key)

    if upper_key in keyboard_key_map:
        return upper_key, keyboard_key_map[upper_key]

    raise ValueError(f"不支持的按键 key={key_text}")


# 规整数字参数：避免按住太短、重复过多或接口传入非法值。
def normalize_number(value, default, minimum, maximum):
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        number = default

    return max(minimum, min(maximum, number))


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


# 显示点击提示：业务层根据当前绑定窗口和 OP 缩放设置绘制 Overlay。
def show_click_overlay(x, y):
    try:
        bound = op.get_bound_window()
        overlay.show_click(
            bound["hwnd"],
            int(x),
            int(y),
            scale=op.get_bind_coordinate_scale(),
        )
    except Exception:
        pass


# 隐藏点击提示：吞掉绘制层异常，避免影响主业务动作。
def hide_overlay_safely():
    try:
        overlay.hide()
    except Exception:
        pass

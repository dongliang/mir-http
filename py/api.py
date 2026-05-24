import ctypes
import math
import re
import tempfile
import threading
import time
from ctypes import wintypes
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

import op
import win32


# 项目根目录：业务脚本在 py/ 下，运行资源仍在项目根目录。
base_dir = Path(__file__).resolve().parent.parent
# 截图目录：保存绑定窗口截图和调试图片。
screenshot_dir = base_dir / "screenshots"
# 调试图片目录：保存怪物名 OP 字库识别截图，便于排查缺字或区域偏移。
debug_image_dir = base_dir / "DebugImage"
# 文本配置目录：保存可运行时重载的简单清单。
txt_dir = base_dir / "txt"
# 怪物关键字清单：每行一个允许攻击的怪物名关键字。
monster_keyword_file = txt_dir / "monster.txt"
# 怪物名 OCR 颜色清单：每行一个 OP 颜色格式，例如 00f7f7-101010。
monster_name_color_file = txt_dir / "monster_name_colors.txt"
# 地图坐标截图路径：保存游戏底部坐标区域截图，供诊断使用。
coordinate_image = screenshot_dir / "map_coordinate.bmp"
# PNG 资源目录：保存血条特征图等图像匹配资源。
png_dir = base_dir / "png"
# 参考资源目录：保存当前绑定的大地图图片。
ref_dir = base_dir / "ref"
# 当前地图图片：网页巡逻面板直接显示这张图。
map_image_file = ref_dir / "map.png"
# 地图最大坐标截图：运行时诊断文件，不提交。
map_max_coordinate_image = screenshot_dir / "map_max_coordinate.bmp"
# 怪物血条特征图：血条最左侧小片段，用于统一查找满血和残血怪物。
monster_blood_feature_image = png_dir / "残血血条特征图.png"
# 红色血条模板：用于读取血条标准宽高。
red_blood_bar_image = png_dir / "红色血条.png"
# 自身绿色血条特征图：用于自动加血检测玩家头顶血条。
player_blood_feature_image = png_dir / "自身绿色残血血条特征图.png"
# 自身绿色血条模板：用于读取玩家血条宽高和绿色填充色。
green_blood_bar_image = png_dir / "自身绿色血条.png"
# 坐标读取锁：串行化截图和 OP 字库识别流程，避免并发读写同一张截图。
coordinate_lock = threading.Lock()
# 怪物扫描锁：串行化截图、鼠标悬停和 OP 字库识别流程。
monster_scan_lock = threading.Lock()
# 自动加血锁：避免页面主动刷新和后台刷新同时触发 F1。
auto_heal_lock = threading.Lock()
# 地图角点快捷键锁：保护热键配置和最近触发状态。
map_corner_hotkey_lock = threading.Lock()
map_corner_hotkey_stop_event = threading.Event()
map_corner_hotkey_thread = None
map_corner_hotkey_state = {
    "hotkey": "",
    "keys": [],
    "last_message": "",
}
# 绑定玩家位置：绑定窗口时通过 OP 字库定位玩家名称得到脚底基准点。
bound_player_position = {}
# 怪物关键字清单缓存：运行时加载，可由网页按钮重载。
monster_keyword_lock = threading.Lock()
monster_keyword_state = {
    "loaded": False,
    "mtime": 0,
    "keywords": [],
    "message": "",
}
# 怪物名 OCR 颜色缓存：运行时加载，可由网页按钮重载。
monster_name_color_lock = threading.Lock()
monster_name_color_state = {
    "loaded": False,
    "mtime": 0,
    "colors": [],
    "message": "",
}
# 底部界面高度：估算游戏底栏高度，用来计算角色移动点击原点。
BOTTOM_UI_HEIGHT = 245
# 默认键盘测试键：用于页面测试按钮验证后台键盘输入链路。
keyboard_test_key = "M"
# 大地图图片宽度：游戏大地图固定宽度，用于网页和逻辑坐标换算。
MAP_IMAGE_WIDTH = 550
# 大地图图片高度：游戏大地图固定高度，用于网页和逻辑坐标换算。
MAP_IMAGE_HEIGHT = 350
# 最大逻辑坐标识别框偏移：相对大地图右下角向内取一块区域。
MAP_MAX_COORDINATE_OCR_OFFSET = {
    "left": -190,
    "top": -55,
    "right": -2,
    "bottom": -2,
}
# 地图右下角悬停等待：给游戏显示鼠标指向逻辑坐标留出时间。
MAP_HOVER_WAIT_SECONDS = 0.25
# 玩家名称识别：绑定时在旧中心点附近用 OP 字库定位名字和脚底点。
PLAYER_NAME_SEARCH_HALF_WIDTH = 220
PLAYER_NAME_SEARCH_TOP_PADDING = 100
PLAYER_NAME_SEARCH_BOTTOM_PADDING = 220
PLAYER_NAME_TEXT_WIDTH = 12
PLAYER_NAME_TEXT_HEIGHT = 12
PLAYER_NAME_TO_FOOT_OFFSET_X = 0
PLAYER_NAME_TO_FOOT_OFFSET_Y = 32
# 怪物悬停偏移：血条底边到怪物名字中点的位置，兼作怪物位置和鼠标悬停点。
MONSTER_HOVER_OFFSET_Y = 45
# 怪物名识别横向半宽：总宽约 100 像素，覆盖“变异骷髅(妖孽)”并减少背景干扰。
MONSTER_NAME_HALF_WIDTH = 50
# 怪物名识别上边距：血条底边向下到名字区域顶部的距离。
MONSTER_NAME_TOP_OFFSET = 32
# 怪物名识别下边距：血条底边向下到名字区域底部的距离。
MONSTER_NAME_BOTTOM_OFFSET = 52
# 血条特征匹配阈值：0 表示完全一致，保留极小容差兼容截图格式差异。
MONSTER_FEATURE_MATCH_THRESHOLD = 0.001
# 怪物名字显示等待时间：鼠标悬停后等待游戏显示名字。
MONSTER_HOVER_WAIT_SECONDS = 0.25
# 怪物名字识别最大截图次数：第一次未截到字或识别为空时短暂重试。
MONSTER_NAME_OCR_MAX_ATTEMPTS = 2
# 怪物名字识别重试等待时间：给 hover 名字显示留出额外缓冲。
MONSTER_NAME_OCR_RETRY_DELAY_SECONDS = 0.2
# 怪物名默认 OCR 颜色：配置文件缺失或为空时使用。
DEFAULT_MONSTER_NAME_OCR_COLORS = [
    "00f7f7-101010",
    "00ffff-101010",
    "ffffff-101010",
    "ffff00-101010",
]
# 怪物血条刷新搜索范围：识别名字前围绕旧血条局部重扫，降低怪物移动影响。
MONSTER_REFRESH_SEARCH_HALF_WIDTH = 180
MONSTER_REFRESH_SEARCH_TOP_OFFSET = 100
MONSTER_REFRESH_SEARCH_BOTTOM_OFFSET = 160
MONSTER_REFRESH_MAX_DISTANCE = 180
# 血条模板几何：来自 png/红色血条.png，填充区 x=2..61，总填充长度 60。
HEALTH_BAR_TEMPLATE_WIDTH = 64
HEALTH_BAR_FILL_START_X = 2
HEALTH_BAR_FULL_FILL_PIXELS = 60
# 红色血条填充色：来自 png/红色血条.png，填充像素为纯 RGB(255, 0, 0)。
RED_HEALTH_BAR_RGB = (255, 0, 0)
# 绿色血条兜底填充色：自身绿色血条模板读取失败时使用。
GREEN_HEALTH_BAR_RGB = (0, 255, 0)
# 自动加血默认配置和边界：页面和接口都会按这些范围规整输入。
AUTO_HEAL_DEFAULT_THRESHOLD_PERCENT = 50
AUTO_HEAL_DEFAULT_INTERVAL_MS = 1000
AUTO_HEAL_MIN_THRESHOLD_PERCENT = 1
AUTO_HEAL_MAX_THRESHOLD_PERCENT = 100
AUTO_HEAL_MIN_INTERVAL_MS = 500
AUTO_HEAL_MAX_INTERVAL_MS = 60000
# idle 卡住保护默认配置和边界。
IDLE_STUCK_DEFAULT_SECONDS = 30
IDLE_STUCK_MIN_SECONDS = 5
IDLE_STUCK_MAX_SECONDS = 600
# 地图角点快捷键默认值：只在当前前台窗口是已绑定窗口时触发。
MAP_CORNER_HOTKEY_DEFAULT = "F8"
MAP_CORNER_HOTKEY_POLL_SECONDS = 0.05
MAP_CORNER_HOTKEY_COOLDOWN_SECONDS = 0.5
MAP_CORNER_HOTKEY_DISABLED_VALUES = {"", "NONE", "OFF", "DISABLED", "禁用", "关闭"}
HOTKEY_MODIFIER_NAMES = {
    "CTRL": "CTRL",
    "CONTROL": "CTRL",
    "ALT": "ALT",
    "SHIFT": "SHIFT",
}
HOTKEY_MODIFIER_ORDER = ["CTRL", "ALT", "SHIFT"]
GA_ROOT = 2

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


# 配置地图角点快捷键。
def configure_map_corner_hotkey(hotkey):
    global map_corner_hotkey_thread

    normalized_hotkey, keys = normalize_hotkey(hotkey)

    with map_corner_hotkey_lock:
        map_corner_hotkey_state["hotkey"] = normalized_hotkey
        map_corner_hotkey_state["keys"] = keys
        map_corner_hotkey_state["last_message"] = get_map_corner_hotkey_config_message(normalized_hotkey)

    if map_corner_hotkey_thread and map_corner_hotkey_thread.is_alive():
        return normalized_hotkey

    map_corner_hotkey_stop_event.clear()
    map_corner_hotkey_thread = threading.Thread(
        target=map_corner_hotkey_loop,
        daemon=True,
    )
    map_corner_hotkey_thread.start()
    return normalized_hotkey


# 停止地图角点快捷键监听。
def stop_map_corner_hotkey():
    map_corner_hotkey_stop_event.set()


# 地图角点快捷键监听循环：只有焦点在绑定窗口时才执行动作。
def map_corner_hotkey_loop():
    was_pressed = False
    last_trigger_at = 0.0

    while not map_corner_hotkey_stop_event.is_set():
        hotkey, keys = get_map_corner_hotkey_snapshot()

        if not keys:
            was_pressed = False
            map_corner_hotkey_stop_event.wait(MAP_CORNER_HOTKEY_POLL_SECONDS)
            continue

        pressed = is_bound_window_foreground() and are_hotkey_keys_down(keys)
        now = time.time()

        if pressed and not was_pressed and now - last_trigger_at >= MAP_CORNER_HOTKEY_COOLDOWN_SECONDS:
            result = move_mouse_to_map_rect_corner()
            set_map_corner_hotkey_last_message(f"{hotkey} {result.get('message', '')}")
            last_trigger_at = now

        was_pressed = pressed
        map_corner_hotkey_stop_event.wait(MAP_CORNER_HOTKEY_POLL_SECONDS)


# 读取当前快捷键配置快照。
def get_map_corner_hotkey_snapshot():
    with map_corner_hotkey_lock:
        return map_corner_hotkey_state["hotkey"], list(map_corner_hotkey_state["keys"])


# 写入快捷键最近消息。
def set_map_corner_hotkey_last_message(message):
    with map_corner_hotkey_lock:
        map_corner_hotkey_state["last_message"] = str(message or "")


# 读取快捷键最近消息。
def get_map_corner_hotkey_last_message():
    with map_corner_hotkey_lock:
        return map_corner_hotkey_state.get("last_message", "")


# 判断快捷键所有按键是否按下。
def are_hotkey_keys_down(keys):
    return all(is_vk_key_down(vk_code) for vk_code in keys)


# 判断单个虚拟键是否按下。
def is_vk_key_down(vk_code):
    try:
        user32 = ctypes.windll.user32
        user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        user32.GetAsyncKeyState.restype = ctypes.c_short
        return bool(user32.GetAsyncKeyState(int(vk_code)) & 0x8000)
    except Exception:
        return False


# 判断当前前台窗口是否为已绑定窗口。
def is_bound_window_foreground():
    bound = op.get_bound_window()
    hwnd = bound.get("hwnd")

    if not hwnd:
        return False

    try:
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
        user32.GetAncestor.restype = wintypes.HWND
        foreground = int(user32.GetForegroundWindow())
        foreground_root = int(user32.GetAncestor(foreground, GA_ROOT)) or foreground
    except Exception:
        return False

    return foreground == int(hwnd) or foreground_root == int(hwnd)


# 标准化快捷键文本并生成虚拟键列表。
def normalize_hotkey(hotkey):
    text = str(hotkey or "").strip().upper()
    text = text.replace("＋", "+").replace(" ", "")

    if text in MAP_CORNER_HOTKEY_DISABLED_VALUES:
        return "", []

    parts = [part for part in text.split("+") if part]
    if not parts:
        return "", []

    modifiers = []
    main_key = ""
    main_vk = None

    for part in parts:
        modifier_name = HOTKEY_MODIFIER_NAMES.get(part)

        if modifier_name:
            if modifier_name not in modifiers:
                modifiers.append(modifier_name)
            continue

        if main_key:
            raise ValueError("快捷键只能包含一个主按键")

        main_key, main_vk = resolve_keyboard_key(part)

        if main_key in HOTKEY_MODIFIER_NAMES:
            raise ValueError("快捷键不能只使用修饰键")

    if main_vk is None:
        raise ValueError("快捷键需要包含一个主按键")

    ordered_modifiers = [modifier for modifier in HOTKEY_MODIFIER_ORDER if modifier in modifiers]
    keys = [keyboard_key_map[modifier] for modifier in ordered_modifiers]
    keys.append(main_vk)
    return "+".join([*ordered_modifiers, main_key]), keys


# 获取快捷键配置消息。
def get_map_corner_hotkey_config_message(hotkey):
    if hotkey:
        return f"地图角点快捷键已设置为 {hotkey}"

    return "地图角点快捷键已禁用"


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

    if not success:
        clear_bound_player_position()
        return {
            "success": success,
            "title": title,
            "message": message,
        }

    position_result = bind_player_position(keyword)

    if not position_result["success"]:
        unbind_success, _, unbind_message = op.unbind_window()
        clear_bound_player_position()
        return {
            "success": False,
            "title": title,
            "message": (
                f"{message}；玩家名称定位失败: {position_result['message']}；"
                f"已自动解绑 success={unbind_success} {unbind_message}"
            ),
        }

    return {
        "success": success,
        "title": title,
        "message": f"{message}；{position_result['message']}",
        "player_position": get_bound_player_position(),
    }


# 解绑窗口：释放 OP 绑定并隐藏现有点击提示。
def unbind_window():
    success, title, message = op.unbind_window()

    if success:
        clear_bound_player_position()

    return {
        "success": success,
        "title": title,
        "message": message,
    }


# 绑定玩家脚底点：截图并用玩家名称 OCR 定位移动基准。
def bind_player_position(player_name):
    player_name = (player_name or "").strip()

    if not player_name:
        return {
            "success": False,
            "message": "玩家名称不能为空",
        }

    width, height = get_bound_client_size()

    if width <= 0 or height <= 0:
        return {
            "success": False,
            "message": f"窗口尺寸异常 size={width}x{height}",
        }

    result = locate_player_name(player_name, width, height)

    if not result["success"]:
        return result

    set_bound_player_position(result)
    foot = result["foot_point"]
    name_center = result["name_center"]
    return {
        "success": True,
        "message": (
            f"玩家名称定位成功 name={player_name} "
            f"name_center={name_center['x']},{name_center['y']} "
            f"foot={foot['x']},{foot['y']} method=op_dict"
        ),
    }


# 在绑定窗口中用 OP 字库定位玩家名称。
def locate_player_name(player_name, width, height):
    search_box = get_player_name_search_box(width, height)
    matches = op.find_text(
        search_box["left"],
        search_box["top"],
        search_box["right"] - 1,
        search_box["bottom"] - 1,
        player_name,
    )

    if not matches:
        text = op.ocr_text(
            search_box["left"],
            search_box["top"],
            search_box["right"] - 1,
            search_box["bottom"] - 1,
        )
        return {
            "success": False,
            "message": (
                f"没有识别到玩家名 name={player_name} "
                f"search={format_box(search_box)} text={text!r}"
            ),
        }

    match = select_nearest_text_match(matches, search_box)
    name_box = make_op_text_box(match["x"], match["y"], player_name, width, height)
    center_x = (name_box["left"] + name_box["right"]) / 2
    center_y = (name_box["top"] + name_box["bottom"]) / 2
    foot_x = clamp_number(round(center_x + PLAYER_NAME_TO_FOOT_OFFSET_X), 0, width - 1)
    foot_y = clamp_number(round(center_y + PLAYER_NAME_TO_FOOT_OFFSET_Y), 0, height - 1)

    return {
        "success": True,
        "name": player_name,
        "matched_text": match["text"],
        "score": 1.0,
        "name_box": round_box(name_box),
        "name_center": {
            "x": round(center_x),
            "y": round(center_y),
        },
        "foot_point": {
            "x": foot_x,
            "y": foot_y,
        },
        "search_box": search_box,
    }


# 获取玩家名称搜索框：用旧的可操作区中心作为绑定时的粗定位。
def get_player_name_search_box(width, height):
    origin_x, origin_y = get_move_origin(width, height)
    return clamp_box(
        origin_x - PLAYER_NAME_SEARCH_HALF_WIDTH,
        origin_y - PLAYER_NAME_SEARCH_TOP_PADDING,
        origin_x + PLAYER_NAME_SEARCH_HALF_WIDTH,
        origin_y + PLAYER_NAME_SEARCH_BOTTOM_PADDING,
        width,
        height,
    )


# 清理玩家名称文本，只保留可比较字符。
def normalize_player_name_text(text):
    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9_]", "", str(text or ""))


# 从 OP 找字结果中选离搜索框中心最近的匹配。
def select_nearest_text_match(matches, search_box):
    origin_x = (search_box["left"] + search_box["right"]) / 2
    origin_y = (search_box["top"] + search_box["bottom"]) / 2
    return min(matches, key=lambda item: math.dist((item["x"], item["y"]), (origin_x, origin_y)))


# 根据 OP 找字左上角估算文字框。
def make_op_text_box(x, y, text, width, height):
    text_width = max(PLAYER_NAME_TEXT_WIDTH, len(text or "") * PLAYER_NAME_TEXT_WIDTH)
    return clamp_box(
        int(x),
        int(y),
        int(x) + text_width,
        int(y) + PLAYER_NAME_TEXT_HEIGHT,
        width,
        height,
    )


# 记录当前绑定玩家脚底定位。
def set_bound_player_position(position):
    global bound_player_position
    bound_player_position = {
        "name": position["name"],
        "matched_text": position["matched_text"],
        "score": position["score"],
        "name_box": dict(position["name_box"]),
        "name_center": dict(position["name_center"]),
        "foot_point": dict(position["foot_point"]),
        "search_box": dict(position["search_box"]),
        "offset": {
            "x": PLAYER_NAME_TO_FOOT_OFFSET_X,
            "y": PLAYER_NAME_TO_FOOT_OFFSET_Y,
        },
    }


# 清空当前绑定玩家定位。
def clear_bound_player_position():
    global bound_player_position
    bound_player_position = {}


# 获取当前绑定玩家定位副本。
def get_bound_player_position():
    if not bound_player_position:
        return {}

    return {
        "name": bound_player_position.get("name", ""),
        "matched_text": bound_player_position.get("matched_text", ""),
        "score": bound_player_position.get("score", 0.0),
        "name_box": dict(bound_player_position.get("name_box", {})),
        "name_center": dict(bound_player_position.get("name_center", {})),
        "foot_point": dict(bound_player_position.get("foot_point", {})),
        "search_box": dict(bound_player_position.get("search_box", {})),
        "offset": dict(bound_player_position.get("offset", {})),
    }


# 读取当前绑定玩家脚底点；缺失时直接报错，避免继续点错。
def get_bound_player_foot_point():
    position = get_bound_player_position()
    foot = position.get("foot_point", {})

    if not foot:
        raise ValueError("玩家脚底定位不可用，请重新绑定窗口")

    return int(foot["x"]), int(foot["y"]), position


# 四舍五入矩形，便于 JSON 展示。
def round_box(box):
    return {
        "left": round(float(box["left"]), 2),
        "top": round(float(box["top"]), 2),
        "right": round(float(box["right"]), 2),
        "bottom": round(float(box["bottom"]), 2),
    }


# 格式化矩形，便于错误日志查看。
def format_box(box):
    return f"{box['left']},{box['top']},{box['right']},{box['bottom']}"


# 应用运行设置：把内存中的应用设置同步到业务辅助模块。
def apply_app_settings(app_settings):
    hotkey = app_settings.get("map_corner_hotkey", MAP_CORNER_HOTKEY_DEFAULT)

    try:
        app_settings["map_corner_hotkey"] = configure_map_corner_hotkey(hotkey)
    except ValueError:
        app_settings["map_corner_hotkey"] = configure_map_corner_hotkey(MAP_CORNER_HOTKEY_DEFAULT)


# 读取怪物关键字清单：每行一个关键字，空行和 # 注释会跳过。
def load_monster_keywords(force=False):
    with monster_keyword_lock:
        try:
            return load_monster_keywords_locked(force)
        except Exception as error:
            monster_keyword_state["loaded"] = True
            monster_keyword_state["keywords"] = []
            monster_keyword_state["message"] = f"怪物清单加载异常: {error}"
            return get_monster_keyword_status_locked()


# 执行怪物关键字清单加载。
def load_monster_keywords_locked(force=False):
    if not monster_keyword_file.exists():
        monster_keyword_state["loaded"] = True
        monster_keyword_state["mtime"] = 0
        monster_keyword_state["keywords"] = []
        monster_keyword_state["message"] = f"怪物清单不存在 path={monster_keyword_file}"
        return get_monster_keyword_status_locked()

    current_mtime = monster_keyword_file.stat().st_mtime_ns

    if (
        not force
        and monster_keyword_state.get("loaded")
        and monster_keyword_state.get("mtime") == current_mtime
    ):
        return get_monster_keyword_status_locked()

    text = read_text_file_with_fallback(monster_keyword_file)
    keywords = parse_monster_keywords(text)
    monster_keyword_state["loaded"] = True
    monster_keyword_state["mtime"] = current_mtime
    monster_keyword_state["keywords"] = keywords
    monster_keyword_state["message"] = f"怪物清单加载完成 count={len(keywords)} path={monster_keyword_file}"
    return get_monster_keyword_status_locked()


# 重新加载怪物关键字清单：供网页按钮调用。
def reload_monster_keywords():
    return load_monster_keywords(force=True)


# 重新加载 txt 目录下的运行配置。
def reload_text_configs():
    monster_filter = load_monster_keywords(force=True)
    monster_name_colors = load_monster_name_colors(force=True)
    return make_text_config_reload_result(monster_filter, monster_name_colors)


# 启动时加载 txt 目录下的运行配置。
def load_text_configs():
    monster_filter = load_monster_keywords(force=True)
    monster_name_colors = load_monster_name_colors(force=True)
    return make_text_config_reload_result(monster_filter, monster_name_colors)


# 组合 txt 配置重载结果。
def make_text_config_reload_result(monster_filter, monster_name_colors):
    message = (
        f"TXT 配置加载完成 "
        f"monsters={monster_filter.get('count', 0)} "
        f"colors={monster_name_colors.get('count', 0)}"
    )
    return {
        "success": True,
        "monster_filter": monster_filter,
        "monster_name_colors": monster_name_colors,
        "message": message,
    }


# 复制怪物关键字清单状态。
def get_monster_keyword_status():
    if not monster_keyword_state.get("loaded"):
        return load_monster_keywords(force=False)

    with monster_keyword_lock:
        return get_monster_keyword_status_locked()


# 在已持有锁时复制怪物关键字清单状态。
def get_monster_keyword_status_locked():
    keywords = list(monster_keyword_state.get("keywords", []))
    return {
        "path": str(monster_keyword_file),
        "count": len(keywords),
        "keywords": keywords,
        "message": monster_keyword_state.get("message", ""),
    }


# 读取怪物名 OCR 颜色清单。
def load_monster_name_colors(force=False):
    with monster_name_color_lock:
        try:
            return load_monster_name_colors_locked(force)
        except Exception as error:
            monster_name_color_state["loaded"] = True
            monster_name_color_state["colors"] = list(DEFAULT_MONSTER_NAME_OCR_COLORS)
            monster_name_color_state["message"] = f"怪物名颜色加载异常，使用默认颜色: {error}"
            return get_monster_name_color_status_locked()


# 执行怪物名 OCR 颜色清单加载。
def load_monster_name_colors_locked(force=False):
    if not monster_name_color_file.exists():
        monster_name_color_state["loaded"] = True
        monster_name_color_state["mtime"] = 0
        monster_name_color_state["colors"] = list(DEFAULT_MONSTER_NAME_OCR_COLORS)
        monster_name_color_state["message"] = f"怪物名颜色清单不存在，使用默认颜色 path={monster_name_color_file}"
        return get_monster_name_color_status_locked()

    current_mtime = monster_name_color_file.stat().st_mtime_ns

    if (
        not force
        and monster_name_color_state.get("loaded")
        and monster_name_color_state.get("mtime") == current_mtime
    ):
        return get_monster_name_color_status_locked()

    text = read_text_file_with_fallback(monster_name_color_file)
    colors = parse_ocr_colors(text)

    if not colors:
        colors = list(DEFAULT_MONSTER_NAME_OCR_COLORS)
        message = f"怪物名颜色清单为空，使用默认颜色 count={len(colors)} path={monster_name_color_file}"
    else:
        message = f"怪物名颜色清单加载完成 count={len(colors)} path={monster_name_color_file}"

    monster_name_color_state["loaded"] = True
    monster_name_color_state["mtime"] = current_mtime
    monster_name_color_state["colors"] = colors
    monster_name_color_state["message"] = message
    return get_monster_name_color_status_locked()


# 复制怪物名 OCR 颜色状态。
def get_monster_name_color_status():
    if not monster_name_color_state.get("loaded"):
        return load_monster_name_colors(force=False)

    with monster_name_color_lock:
        return get_monster_name_color_status_locked()


# 在已持有锁时复制怪物名 OCR 颜色状态。
def get_monster_name_color_status_locked():
    colors = list(monster_name_color_state.get("colors", []))
    return {
        "path": str(monster_name_color_file),
        "count": len(colors),
        "colors": colors,
        "message": monster_name_color_state.get("message", ""),
    }


# 读取当前怪物名 OCR 颜色列表。
def get_monster_name_ocr_colors():
    return get_monster_name_color_status().get("colors", []) or list(DEFAULT_MONSTER_NAME_OCR_COLORS)


# 按常见文本编码读取清单文件。
def read_text_file_with_fallback(path):
    data = path.read_bytes()

    for encoding in ("utf-8-sig", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue

    return data.decode("utf-8", errors="replace")


# 解析怪物关键字清单文本。
def parse_monster_keywords(text):
    keywords = []
    seen = set()

    for line in str(text or "").splitlines():
        keyword = line.strip()

        if not keyword or keyword.startswith("#"):
            continue

        if keyword in seen:
            continue

        seen.add(keyword)
        keywords.append(keyword)

    return keywords


# 解析 OP OCR 颜色清单文本。
def parse_ocr_colors(text):
    colors = []
    seen = set()

    for line in str(text or "").splitlines():
        color = normalize_ocr_color_line(line)

        if not color or color in seen:
            continue

        seen.add(color)
        colors.append(color)

    return colors


# 规范化单行 OP OCR 颜色：支持 00f7f7 或 00f7f7-101010。
def normalize_ocr_color_line(line):
    value = str(line or "").split("#", 1)[0].strip().lower()

    if not value:
        return ""

    if re.fullmatch(r"[0-9a-f]{6}", value):
        return f"{value}-101010"

    if re.fullmatch(r"[0-9a-f]{6}-[0-9a-f]{6}", value):
        return value

    return ""


# 获取状态：聚合玩家坐标、绑定窗口、应用设置、地图、巡逻、战斗和状态机。
def get_status(
    player_info,
    app_settings,
    current_map=None,
    patrol_points=None,
    patrol_state=None,
    patrol_control=None,
    battle_control=None,
    current_state=None,
    auto_heal_state=None,
    idle_stuck_state=None,
):
    return {
        "player": {
            "map_name": player_info["map_name"],
            "x": player_info["x"],
            "y": player_info["y"],
        },
        "player_position": get_bound_player_position(),
        "bound_window": op.get_bound_window(),
        "settings": make_app_settings_status(app_settings),
        "map": make_map_status(current_map),
        "patrol": make_patrol_status(patrol_points, patrol_state, patrol_control),
        "battle": make_battle_status(battle_control),
        "monster_filter": get_monster_keyword_status(),
        "monster_name_colors": get_monster_name_color_status(),
        "state": make_state_status(current_state),
        "auto_heal": make_auto_heal_status(app_settings, auto_heal_state),
        "idle_stuck": make_idle_stuck_status(app_settings, idle_stuck_state),
    }


# 生成应用设置状态。
def make_app_settings_status(app_settings):
    return {
        "map_corner_hotkey": app_settings.get("map_corner_hotkey", MAP_CORNER_HOTKEY_DEFAULT),
        "map_corner_hotkey_last_message": get_map_corner_hotkey_last_message(),
    }


# 生成地图状态：复制可序列化字段，避免前端拿到内部可变对象引用。
def make_map_status(current_map):
    if not current_map:
        return {}

    return {
        "path": current_map.get("path", ""),
        "url": current_map.get("url", ""),
        "rect": dict(current_map.get("rect", {})),
        "max_x": current_map.get("max_x", 0),
        "max_y": current_map.get("max_y", 0),
        "ocr_box": dict(current_map.get("ocr_box", {})),
        "ocr_offset": dict(current_map.get("ocr_offset", {})),
        "ocr_text": current_map.get("ocr_text", ""),
    }


# 生成巡逻状态：返回当前保存的巡逻点、索引和开关。
def make_patrol_status(patrol_points, patrol_state, patrol_control=None):
    points = []

    for point in patrol_points or []:
        points.append({
            "x": int(point.get("x", 0)),
            "y": int(point.get("y", 0)),
        })

    return {
        "points": points,
        "index": int((patrol_state or {}).get("index", -1)),
        "enabled": bool((patrol_control or {}).get("enabled", False)),
    }


# 生成战斗开关状态。
def make_battle_status(battle_control):
    return {
        "enabled": bool((battle_control or {}).get("enabled", False)),
    }


# 生成当前状态机状态。
def make_state_status(current_state):
    return {
        "name": (current_state or {}).get("name", "idle"),
    }


# 生成自动加血状态：返回页面展示和轮询同步需要的字段。
def make_auto_heal_status(app_settings, auto_heal_state=None):
    state = auto_heal_state or {}
    last_hp_percent = state.get("last_hp_percent", "")

    if last_hp_percent is None:
        last_hp_percent = ""

    return {
        "enabled": bool(app_settings.get("auto_heal_enabled", False)),
        "threshold_percent": normalize_number(
            app_settings.get("auto_heal_threshold_percent"),
            AUTO_HEAL_DEFAULT_THRESHOLD_PERCENT,
            AUTO_HEAL_MIN_THRESHOLD_PERCENT,
            AUTO_HEAL_MAX_THRESHOLD_PERCENT,
        ),
        "interval_ms": normalize_number(
            app_settings.get("auto_heal_interval_ms"),
            AUTO_HEAL_DEFAULT_INTERVAL_MS,
            AUTO_HEAL_MIN_INTERVAL_MS,
            AUTO_HEAL_MAX_INTERVAL_MS,
        ),
        "last_hp_percent": last_hp_percent,
        "triggered_low": bool(state.get("triggered_low", False)),
        "last_message": state.get("last_message", ""),
    }


# 生成 idle 卡住保护状态：返回页面展示和轮询同步需要的字段。
def make_idle_stuck_status(app_settings, idle_stuck_state=None):
    state = idle_stuck_state or {}
    coordinate = make_idle_stuck_coordinate_status(state.get("last_coordinate"))
    stationary_seconds = int(state.get("stationary_seconds") or 0)
    started_at = state.get("stationary_started_at") or 0

    if coordinate and started_at:
        stationary_seconds = max(stationary_seconds, int(time.time() - float(started_at)))

    return {
        "enabled": bool(app_settings.get("idle_stuck_enabled", True)),
        "seconds": normalize_number(
            app_settings.get("idle_stuck_seconds"),
            IDLE_STUCK_DEFAULT_SECONDS,
            IDLE_STUCK_MIN_SECONDS,
            IDLE_STUCK_MAX_SECONDS,
        ),
        "coordinate": coordinate,
        "stationary_seconds": stationary_seconds,
        "last_message": state.get("last_message", ""),
    }


# 生成 idle 卡住保护坐标状态。
def make_idle_stuck_coordinate_status(coordinate):
    if not coordinate or len(coordinate) != 3:
        return {}

    map_name, x, y = coordinate
    return {
        "map_name": str(map_name),
        "x": int(x),
        "y": int(y),
    }


# 获取绑定窗口尺寸：直接使用 OP 返回的客户区尺寸。
def get_bound_client_size():
    # 绑定窗口状态：读取当前 hwnd 供 OP 查询。
    bound = op.get_bound_window()
    return op.get_client_size(bound["hwnd"])


# 获取绑定窗口尺寸诊断：返回 OP 读到的客户区尺寸。
def get_bound_client_info():
    bound = op.get_bound_window()
    width, height = op.get_client_size(bound["hwnd"])

    return {
        "width": width,
        "height": height,
        "raw_width": width,
        "raw_height": height,
    }


# 获取大地图交互矩形：大地图固定 550x350，按 OP 有效客户区居中。
def get_map_rect(width, height):
    left = round((width - MAP_IMAGE_WIDTH) / 2)
    top = round((height - MAP_IMAGE_HEIGHT) / 2)
    return left, top, left + MAP_IMAGE_WIDTH, top + MAP_IMAGE_HEIGHT


# 移动鼠标到大地图右下角：用前台鼠标移动验证地图交互 rect 角点。
def move_mouse_to_map_rect_corner():
    if not op.is_window_bound():
        return {
            "success": False,
            "message": "还没有绑定窗口",
        }

    client = get_bound_client_info()
    width, height = client["width"], client["height"]

    if width <= 0 or height <= 0:
        return {
            "success": False,
            "client": client,
            "message": f"窗口尺寸异常 size={width}x{height}",
        }

    left, top, right, bottom = get_map_rect(width, height)
    rect = make_map_rect(left, top, right, bottom)
    x, y = right - 1, bottom - 1
    raw_x = clamp_number(x, 0, max(0, client["raw_width"] - 1))
    raw_y = clamp_number(y, 0, max(0, client["raw_height"] - 1))
    bound = op.get_bound_window()
    screen_x, screen_y = win32.client_to_screen(bound["hwnd"], raw_x, raw_y)
    success = win32.move_cursor_to_screen(screen_x, screen_y)

    return {
        "success": success,
        "x": x,
        "y": y,
        "raw_x": raw_x,
        "raw_y": raw_y,
        "screen_x": screen_x,
        "screen_y": screen_y,
        "rect": rect,
        "client": client,
        "message": (
            f"地图角点前台移动 {'成功' if success else '失败'} "
            f"op={x},{y} raw={raw_x},{raw_y} screen={screen_x},{screen_y} "
            f"rect={left},{top},{right},{bottom}"
        ),
    }


# 绑定当前大地图：截图保存地图图片，并 OCR 鼠标悬停右下角时的最大逻辑坐标。
def bind_current_map(player_info=None):
    with coordinate_lock:
        try:
            return bind_current_map_locked(player_info)
        except Exception as error:
            return {
                "success": False,
                "message": f"绑定地图异常: {error}",
            }


# 执行地图绑定：由锁保护截图、鼠标悬停和 OCR 过程。
def bind_current_map_locked(player_info=None):
    if not op.is_window_bound():
        return {
            "success": False,
            "message": "还没有绑定窗口",
        }

    width, height = get_bound_client_size()

    if width <= 0 or height <= 0:
        return {
            "success": False,
            "message": f"窗口尺寸异常 size={width}x{height}",
        }

    left, top, right, bottom = get_map_rect(width, height)
    map_rect = make_map_rect(left, top, right, bottom)
    hover_x, hover_y = right - 1, bottom - 1

    move_success, move_message = op.move_mouse_to(hover_x, hover_y)

    if not move_success:
        return {
            "success": False,
            "message": f"地图右下角悬停失败: {move_message}",
            "map": {},
        }

    time.sleep(MAP_HOVER_WAIT_SECONDS)

    ref_dir.mkdir(exist_ok=True)
    capture_success, capture_message = capture_bound_client_checked(
        left,
        top,
        right - 1,
        bottom - 1,
        map_image_file,
    )

    if not capture_success:
        return {
            "success": False,
            "message": f"地图截图失败: {capture_message}",
            "map": {},
        }

    ocr_box = get_map_max_coordinate_ocr_box(map_rect, width, height)
    crop_map_max_coordinate_image(map_rect, ocr_box)
    text = op.ocr_text(
        ocr_box["left"],
        ocr_box["top"],
        ocr_box["right"] - 1,
        ocr_box["bottom"] - 1,
    )
    max_x, max_y = parse_map_max_coordinate_text(text, player_info)

    current_map = {
        "path": str(map_image_file),
        "url": f"/ref/map.png?v={int(time.time() * 1000)}",
        "rect": map_rect,
        "max_x": max_x,
        "max_y": max_y,
        "ocr_box": ocr_box,
        "ocr_offset": dict(MAP_MAX_COORDINATE_OCR_OFFSET),
        "ocr_text": text,
    }

    return {
        "success": True,
        "map": current_map,
        "message": (
            f"绑定地图成功 path={map_image_file} max={max_x}:{max_y} "
            f"rect={left},{top},{right},{bottom} "
            f"ocr_box={ocr_box['left']},{ocr_box['top']},{ocr_box['right']},{ocr_box['bottom']} "
            f"text={text!r} hover={hover_x},{hover_y} {capture_message}"
        ),
    }


# 创建地图矩形状态：统一 right/bottom 作为开区间。
def make_map_rect(left, top, right, bottom):
    return {
        "left": int(left),
        "top": int(top),
        "right": int(right),
        "bottom": int(bottom),
        "width": int(right - left),
        "height": int(bottom - top),
    }


# 获取最大坐标 OCR 框：按右下角偏移计算客户区坐标矩形。
def get_map_max_coordinate_ocr_box(map_rect, width, height):
    return clamp_box(
        map_rect["right"] + MAP_MAX_COORDINATE_OCR_OFFSET["left"],
        map_rect["bottom"] + MAP_MAX_COORDINATE_OCR_OFFSET["top"],
        map_rect["right"] + MAP_MAX_COORDINATE_OCR_OFFSET["right"],
        map_rect["bottom"] + MAP_MAX_COORDINATE_OCR_OFFSET["bottom"],
        width,
        height,
    )


# 从地图截图中裁出最大坐标 OCR 区域。
def crop_map_max_coordinate_image(map_rect, ocr_box):
    left = ocr_box["left"] - map_rect["left"]
    top = ocr_box["top"] - map_rect["top"]
    right = ocr_box["right"] - map_rect["left"]
    bottom = ocr_box["bottom"] - map_rect["top"]

    map_max_coordinate_image.parent.mkdir(exist_ok=True)

    with Image.open(map_image_file) as image:
        image.crop((left, top, right, bottom)).save(map_max_coordinate_image)


# 解析地图最大逻辑坐标 OCR 文本。
def parse_map_max_coordinate_text(text, player_info=None):
    pairs = re.findall(r"(\d{1,4})\s*[:：,，/\\]\s*(\d{1,4})", text or "")

    if pairs:
        x_text, y_text = pairs[-1]
    else:
        numbers = re.findall(r"\d+", text or "")

        if len(numbers) >= 2:
            x_text, y_text = numbers[-2], numbers[-1]
        elif len(numbers) == 1:
            x_text, y_text = split_compact_map_max_coordinate(numbers[0], player_info, text)
        else:
            raise ValueError(f"无法识别地图最大逻辑坐标 text={text!r}")

    max_x, max_y = int(x_text), int(y_text)

    if max_x <= 0 or max_y <= 0:
        raise ValueError(f"地图最大逻辑坐标异常 max={max_x}:{max_y} text={text!r}")

    player_x, player_y = get_player_logic_coordinate(player_info)

    if player_x is not None and max_x < player_x:
        raise ValueError(f"地图最大 X 小于当前玩家 X max_x={max_x} player_x={player_x} text={text!r}")

    if player_y is not None and max_y < player_y:
        raise ValueError(f"地图最大 Y 小于当前玩家 Y max_y={max_y} player_y={player_y} text={text!r}")

    return max_x, max_y


# 拆分冒号漏识别的最大坐标，例如 699698 -> 699:698。
def split_compact_map_max_coordinate(number_text, player_info=None, raw_text=""):
    digits = re.sub(r"\D+", "", str(number_text or ""))

    if len(digits) < 2 or len(digits) > 8:
        raise ValueError(f"无法识别地图最大逻辑坐标 text={raw_text!r}")

    player_x, player_y = get_player_logic_coordinate(player_info)
    candidates = []

    for split_at in range(1, len(digits)):
        x_text = digits[:split_at]
        y_text = digits[split_at:]

        if len(x_text) > 4 or len(y_text) > 4:
            continue

        x, y = int(x_text), int(y_text)

        if x <= 0 or y <= 0:
            continue

        if player_x is not None and x < player_x:
            continue

        if player_y is not None and y < player_y:
            continue

        # 分割点越接近中间越可信，避免 6 位数被拆成 6:99698 这类异常坐标。
        candidates.append((abs(len(x_text) - len(y_text)), x, y, x_text, y_text))

    if not candidates:
        raise ValueError(f"无法识别地图最大逻辑坐标 text={raw_text!r}")

    _, _, _, x_text, y_text = sorted(candidates)[0]
    return x_text, y_text


# 读取玩家当前逻辑坐标：用于过滤明显误识别的最大地图坐标。
def get_player_logic_coordinate(player_info):
    if not player_info:
        return None, None

    return parse_optional_int(player_info.get("x")), parse_optional_int(player_info.get("y"))


# 解析可选整数。
def parse_optional_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


# 地图图片坐标转逻辑坐标。
def map_pixel_to_logic(pixel_x, pixel_y, max_x, max_y):
    max_x, max_y = validate_map_max_coordinate(max_x, max_y)
    pixel_x = clamp_number(round(pixel_x), 0, MAP_IMAGE_WIDTH - 1)
    pixel_y = clamp_number(round(pixel_y), 0, MAP_IMAGE_HEIGHT - 1)

    return {
        "x": round(pixel_x * max_x / (MAP_IMAGE_WIDTH - 1)),
        "y": round(pixel_y * max_y / (MAP_IMAGE_HEIGHT - 1)),
    }


# 逻辑坐标转地图图片坐标。
def logic_to_map_pixel(logic_x, logic_y, max_x, max_y):
    max_x, max_y = validate_map_max_coordinate(max_x, max_y)
    logic_x = clamp_number(round(logic_x), 0, max_x)
    logic_y = clamp_number(round(logic_y), 0, max_y)

    return {
        "x": round(logic_x * (MAP_IMAGE_WIDTH - 1) / max_x),
        "y": round(logic_y * (MAP_IMAGE_HEIGHT - 1) / max_y),
    }


# 校验地图最大坐标。
def validate_map_max_coordinate(max_x, max_y):
    max_x = int(max_x)
    max_y = int(max_y)

    if max_x <= 0 or max_y <= 0:
        raise ValueError(f"地图最大逻辑坐标异常 max={max_x}:{max_y}")

    return max_x, max_y


# 逻辑坐标转客户区点击坐标。
def logic_to_client_point(logic_x, logic_y, current_map):
    if not current_map:
        raise ValueError("还没有绑定地图")

    rect = current_map.get("rect", {})
    max_x, max_y = validate_map_max_coordinate(current_map.get("max_x", 0), current_map.get("max_y", 0))
    pixel = logic_to_map_pixel(logic_x, logic_y, max_x, max_y)

    return {
        "client_x": int(rect.get("left", 0)) + pixel["x"],
        "client_y": int(rect.get("top", 0)) + pixel["y"],
        "map_x": pixel["x"],
        "map_y": pixel["y"],
    }


# 移动到指定逻辑巡逻点：打开地图、点击目标点、关闭地图。
def move_to_logic_point(point, current_map):
    if not op.is_window_bound():
        return {
            "success": False,
            "message": "还没有绑定窗口",
        }

    try:
        logic_x = int(point.get("x", 0))
        logic_y = int(point.get("y", 0))
        target = logic_to_client_point(logic_x, logic_y, current_map)
    except (TypeError, ValueError) as error:
        return {
            "success": False,
            "message": str(error),
        }

    open_result = press_keyboard("M", hold_ms=120, repeat=2, interval_ms=120)

    if not open_result["success"]:
        return {
            "success": False,
            "point": {"x": logic_x, "y": logic_y},
            "target": target,
            "message": f"打开地图失败: {open_result['message']}",
            "open_keyboard": open_result,
        }

    time.sleep(0.2)
    click_success, click_message = op.click_mouse_at(target["client_x"], target["client_y"], "left")

    time.sleep(0.1)
    close_result = press_keyboard("M", hold_ms=120, repeat=1, interval_ms=80)
    success = click_success and close_result["success"]

    return {
        "success": success,
        "point": {"x": logic_x, "y": logic_y},
        "target": target,
        "open_keyboard": open_result,
        "close_keyboard": close_result,
        "message": (
            f"移动到巡逻点 {'成功' if success else '失败'} "
            f"logic={logic_x}:{logic_y} map={target['map_x']},{target['map_y']} "
            f"client={target['client_x']},{target['client_y']} "
            f"click={click_message} close={close_result['message']}"
        ),
    }


# 攻击怪物：左键点击怪物 hover 点，让游戏自动跑过去攻击。
def attack_monster(monster):
    if not op.is_window_bound():
        return {
            "success": False,
            "message": "还没有绑定窗口",
        }

    monster = monster or {}
    position = monster.get("position", {})

    try:
        x = int(position.get("x", 0))
        y = int(position.get("y", 0))
    except (TypeError, ValueError):
        return {
            "success": False,
            "message": f"怪物位置异常 position={position}",
        }

    width, height = get_bound_client_size()

    if width <= 0 or height <= 0:
        return {
            "success": False,
            "message": f"窗口尺寸异常 size={width}x{height}",
        }

    x = clamp_number(x, 0, width - 1)
    y = clamp_number(y, 0, height - 1)

    filter_result = verify_monster_name_before_attack(monster, x, y, width, height)

    if not filter_result["allowed"]:
        filter_reason = filter_result.get("reason", "monster_filter_failed")
        reason = "monster_filter_mismatch" if filter_reason == "keyword_not_found" else filter_reason

        return {
            "success": False,
            "reason": reason,
            "filter_reason": filter_reason,
            "x": x,
            "y": y,
            "filter": filter_result,
            "monster": {
                "id": monster.get("id", 0),
                "distance": monster.get("distance", ""),
                "hp_percent": monster.get("hp_percent", ""),
            },
            "message": (
                f"跳过怪物，名称不在清单内 "
                f"text={filter_result.get('text', '')!r} "
                f"keywords={filter_result.get('keywords', [])} "
                f"box={filter_result.get('box', {})}"
            ),
        }

    position = filter_result.get("position", {})
    x = int(position.get("x", x))
    y = int(position.get("y", y))
    success, message = op.click_mouse_at(x, y, "left")

    return {
        "success": success,
        "x": x,
        "y": y,
        "filter": filter_result,
        "monster": {
            "id": monster.get("id", 0),
            "distance": monster.get("distance", ""),
            "hp_percent": monster.get("hp_percent", ""),
        },
        "message": (
            f"攻击怪物 {message} hp={monster.get('hp_percent', '')}% "
            f"distance={monster.get('distance', '')} "
            f"matched={filter_result.get('matched_keyword', '')} "
            f"text={filter_result.get('text', '')!r}"
        ),
    }


# 攻击前校验怪物名：只有命中 txt/monster.txt 中的关键字才允许点击。
def verify_monster_name_before_attack(monster, x, y, width, height):
    keyword_status = load_monster_keywords(force=False)
    keywords = keyword_status.get("keywords", [])

    if not keywords:
        return {
            "allowed": False,
            "reason": "empty_keyword_list",
            "keywords": keywords,
            "text": "",
            "matched_keyword": "",
            "box": {},
            "position": {"x": x, "y": y},
            "message": keyword_status.get("message", ""),
        }

    blood_bar = monster.get("blood_bar", {})

    if not is_valid_blood_bar(blood_bar):
        return {
            "allowed": False,
            "reason": "missing_blood_bar",
            "keywords": keywords,
            "text": "",
            "matched_keyword": "",
            "box": {},
            "position": {"x": x, "y": y},
            "message": "怪物缺少血条坐标，无法做名字过滤",
        }

    name_result = recognize_monster_name(x, y, blood_bar, save_debug=False)
    move_success = name_result.get("move_success", True)
    move_message = name_result.get("move_message", "")

    if not move_success:
        return {
            "allowed": False,
            "reason": "hover_failed",
            "keywords": keywords,
            "matched_keyword": "",
            "text": name_result.get("name_text", ""),
            "box": name_result.get("ocr_box", {}),
            "blood_bar": name_result.get("blood_bar", {}),
            "position": name_result.get("position", {"x": x, "y": y}),
            "move_success": move_success,
            "move_message": move_message,
            "name_result": name_result,
        }

    if not name_result.get("success", False):
        return {
            "allowed": False,
            "reason": "monster_name_failed",
            "keywords": keywords,
            "matched_keyword": "",
            "text": get_monster_name_filter_text(name_result),
            "box": name_result.get("ocr_box", {}),
            "blood_bar": name_result.get("blood_bar", {}),
            "position": name_result.get("position", {"x": x, "y": y}),
            "move_success": move_success,
            "move_message": move_message,
            "name_result": name_result,
        }

    matched_keyword = get_matched_monster_keyword(name_result, keywords)
    text = get_monster_name_filter_text(name_result)

    return {
        "allowed": bool(matched_keyword),
        "reason": "" if matched_keyword else "keyword_not_found",
        "keywords": keywords,
        "matched_keyword": matched_keyword,
        "text": text,
        "box": name_result.get("ocr_box", {}),
        "blood_bar": name_result.get("blood_bar", {}),
        "position": name_result.get("position", {"x": x, "y": y}),
        "move_success": move_success,
        "move_message": move_message,
        "name_result": name_result,
    }


# 从统一怪物名识别结果里读取命中的怪物关键字。
def get_matched_monster_keyword(name_result, keywords):
    text = get_monster_name_filter_text(name_result)

    for keyword in keywords:
        if keyword and keyword in text:
            return keyword

    return ""


# 拼出怪物过滤用文本：同时保留清洗名和原始识别文本。
def get_monster_name_filter_text(name_result):
    parts = [
        name_result.get("name", ""),
        name_result.get("name_text", ""),
        name_result.get("raw_text", ""),
    ]
    return " ".join(str(part or "") for part in parts)


# 获取玩家当前屏幕位置：复用移动原点算法得到角色脚站地块位置。
def get_player_screen_position():
    if not op.is_window_bound():
        return {
            "success": False,
            "player_x": 0,
            "player_y": 0,
            "message": "还没有绑定窗口",
        }

    client = get_bound_client_info()
    width, height = client["width"], client["height"]

    if width <= 0 or height <= 0:
        return {
            "success": False,
            "player_x": 0,
            "player_y": 0,
            "client": client,
            "message": f"窗口尺寸异常 size={width}x{height}",
        }

    try:
        player_x, player_y, position = get_bound_player_foot_point()
    except ValueError as error:
        return {
            "success": False,
            "player_x": 0,
            "player_y": 0,
            "client": client,
            "message": str(error),
        }

    return {
        "success": True,
        "player_x": player_x,
        "player_y": player_y,
        "player_position": position,
        "client": client,
        "bottom_ui_height": BOTTOM_UI_HEIGHT,
        "message": f"玩家屏幕位置 x={player_x} y={player_y} client_size={width}x{height}",
    }


# 更新地图角点快捷键设置。
def update_map_corner_hotkey_settings(app_settings, data):
    data = data if isinstance(data, dict) else {}
    hotkey = data.get("hotkey", app_settings.get("map_corner_hotkey", MAP_CORNER_HOTKEY_DEFAULT))

    try:
        normalized_hotkey = configure_map_corner_hotkey(hotkey)
    except ValueError as error:
        return {
            "success": False,
            "message": str(error),
            "settings": make_app_settings_status(app_settings),
        }

    app_settings["map_corner_hotkey"] = normalized_hotkey
    message = get_map_corner_hotkey_config_message(normalized_hotkey)
    set_map_corner_hotkey_last_message(message)
    return {
        "success": True,
        "message": message,
        "settings": make_app_settings_status(app_settings),
    }


# 更新自动加血设置：规整页面输入并重置本轮低血触发状态。
def update_auto_heal_settings(app_settings, auto_heal_state, data):
    data = data if isinstance(data, dict) else {}
    enabled = normalize_bool(data.get("enabled", app_settings.get("auto_heal_enabled", False)))
    threshold_percent = normalize_number(
        data.get("threshold_percent"),
        AUTO_HEAL_DEFAULT_THRESHOLD_PERCENT,
        AUTO_HEAL_MIN_THRESHOLD_PERCENT,
        AUTO_HEAL_MAX_THRESHOLD_PERCENT,
    )
    interval_ms = normalize_number(
        data.get("interval_ms"),
        AUTO_HEAL_DEFAULT_INTERVAL_MS,
        AUTO_HEAL_MIN_INTERVAL_MS,
        AUTO_HEAL_MAX_INTERVAL_MS,
    )

    app_settings["auto_heal_enabled"] = enabled
    app_settings["auto_heal_threshold_percent"] = threshold_percent
    app_settings["auto_heal_interval_ms"] = interval_ms

    if auto_heal_state is not None:
        auto_heal_state["last_checked_at"] = 0.0
        auto_heal_state["triggered_low"] = False

    state_text = "开" if enabled else "关"
    message = f"自动加血设置已更新: {state_text} threshold={threshold_percent}% interval={interval_ms}ms"

    if auto_heal_state is not None:
        auto_heal_state["last_message"] = message

    return {
        "success": True,
        "message": message,
        "auto_heal": make_auto_heal_status(app_settings, auto_heal_state),
    }


# 更新 idle 卡住保护设置：规整页面输入并重新开始停留计时。
def update_idle_stuck_settings(app_settings, idle_stuck_state, data):
    data = data if isinstance(data, dict) else {}
    enabled = normalize_bool(data.get("enabled", app_settings.get("idle_stuck_enabled", True)))
    seconds = normalize_number(
        data.get("seconds"),
        IDLE_STUCK_DEFAULT_SECONDS,
        IDLE_STUCK_MIN_SECONDS,
        IDLE_STUCK_MAX_SECONDS,
    )

    app_settings["idle_stuck_enabled"] = enabled
    app_settings["idle_stuck_seconds"] = seconds

    if idle_stuck_state is not None:
        idle_stuck_state["last_coordinate"] = None
        idle_stuck_state["stationary_started_at"] = 0.0
        idle_stuck_state["stationary_seconds"] = 0

    state_text = "开" if enabled else "关"
    message = f"卡住跳点设置已更新: {state_text} seconds={seconds}"

    if idle_stuck_state is not None:
        idle_stuck_state["last_message"] = message

    return {
        "success": True,
        "message": message,
        "idle_stuck": make_idle_stuck_status(app_settings, idle_stuck_state),
    }


# 自动加血检测：独立于状态机，按间隔读取自身血量，低血时每次检测按一次 F1。
def update_auto_heal(app_settings, auto_heal_state):
    if not app_settings.get("auto_heal_enabled", False):
        if auto_heal_state is not None:
            auto_heal_state["triggered_low"] = False
        return {"success": True, "message": ""}

    if auto_heal_state is None:
        auto_heal_state = {}

    if not auto_heal_lock.acquire(blocking=False):
        return {"success": True, "message": ""}

    try:
        return update_auto_heal_locked(app_settings, auto_heal_state)
    finally:
        auto_heal_lock.release()


# 执行自动加血检测：由锁保护，避免并发按键。
def update_auto_heal_locked(app_settings, auto_heal_state):
    now = time.time()
    interval_ms = normalize_number(
        app_settings.get("auto_heal_interval_ms"),
        AUTO_HEAL_DEFAULT_INTERVAL_MS,
        AUTO_HEAL_MIN_INTERVAL_MS,
        AUTO_HEAL_MAX_INTERVAL_MS,
    )
    last_checked_at = float(auto_heal_state.get("last_checked_at") or 0.0)

    if now - last_checked_at < interval_ms / 1000:
        return {"success": True, "message": ""}

    auto_heal_state["last_checked_at"] = now
    threshold_percent = normalize_number(
        app_settings.get("auto_heal_threshold_percent"),
        AUTO_HEAL_DEFAULT_THRESHOLD_PERCENT,
        AUTO_HEAL_MIN_THRESHOLD_PERCENT,
        AUTO_HEAL_MAX_THRESHOLD_PERCENT,
    )
    result = read_player_health_percent()

    if not result.get("success"):
        message = f"自动加血检测失败: {result.get('message', '')}"
        return {
            "success": False,
            "message": set_auto_heal_message(auto_heal_state, message),
        }

    hp_percent = int(result.get("hp_percent", 0))
    auto_heal_state["last_hp_percent"] = hp_percent
    auto_heal_state["last_blood_bar"] = result.get("blood_bar", {})

    if hp_percent >= threshold_percent:
        if auto_heal_state.get("triggered_low", False):
            auto_heal_state["triggered_low"] = False
            message = f"自动加血血量恢复: hp={hp_percent}% threshold={threshold_percent}%"
            return {
                "success": True,
                "message": set_auto_heal_message(auto_heal_state, message),
            }

        set_auto_heal_message(
            auto_heal_state,
            f"自动加血检测正常: hp={hp_percent}% threshold={threshold_percent}%",
            log_once=False,
        )
        return {"success": True, "message": ""}

    move_success, move_message = op.move_mouse_to(0, 0)

    if not move_success:
        message = f"自动加血移动鼠标失败: hp={hp_percent}% threshold={threshold_percent}% {move_message}"
        return {
            "success": False,
            "message": set_auto_heal_message(auto_heal_state, message),
        }

    key_result = press_keyboard("F1", hold_ms=120, repeat=1, interval_ms=80)

    if not key_result.get("success"):
        message = f"自动加血按 F1 失败: hp={hp_percent}% threshold={threshold_percent}% {key_result.get('message', '')}"
        return {
            "success": False,
            "message": set_auto_heal_message(auto_heal_state, message),
        }

    auto_heal_state["triggered_low"] = True
    message = f"自动加血触发: hp={hp_percent}% threshold={threshold_percent}% mouse=0,0 key=F1"
    return {
        "success": True,
        "message": set_auto_heal_message(auto_heal_state, message),
    }


# 写入自动加血状态消息，并按需避免同一错误反复刷日志。
def set_auto_heal_message(auto_heal_state, message, log_once=True):
    auto_heal_state["last_message"] = message

    if not log_once:
        return ""

    if auto_heal_state.get("last_logged_message") == message:
        return ""

    auto_heal_state["last_logged_message"] = message
    return message


# 读取玩家自身血量百分比：用绿色自身血条特征图定位头顶血条。
def read_player_health_percent():
    if not op.is_window_bound():
        return {
            "success": False,
            "message": "还没有绑定窗口",
        }

    if not player_blood_feature_image.exists():
        return {
            "success": False,
            "message": f"找不到自身血条特征图: {player_blood_feature_image}",
        }

    if not green_blood_bar_image.exists():
        return {
            "success": False,
            "message": f"找不到自身绿色血条模板: {green_blood_bar_image}",
        }

    client = get_bound_client_info()
    width, height = client["width"], client["height"]

    if width <= 0 or height <= 0:
        return {
            "success": False,
            "client": client,
            "message": f"窗口尺寸异常 size={width}x{height}",
        }

    try:
        player_x, player_y, position = get_bound_player_foot_point()
    except ValueError as error:
        return {
            "success": False,
            "client": client,
            "message": str(error),
        }

    with tempfile.TemporaryDirectory(prefix="mir2_player_hp_") as temp_dir:
        scan_file = Path(temp_dir) / "screen.bmp"
        success, capture_message = capture_bound_client_checked(
            0,
            0,
            width - 1,
            height - 1,
            scan_file,
        )

        if not success or not scan_file.exists():
            return {
                "success": False,
                "client": client,
                "message": f"自身血量截图失败: {capture_message}",
            }

        matches = find_player_blood_feature_matches(scan_file)

        if not matches:
            return {
                "success": False,
                "client": client,
                "message": "没有找到自身绿色血条",
            }

        match = min(matches, key=lambda item: get_match_distance_to_point(item, player_x, player_y))
        blood_bar = make_blood_bar_from_match(match, width, height)
        target_rgb = get_health_bar_fill_rgb(green_blood_bar_image)

        with Image.open(scan_file) as scan_image:
            hp_percent = calculate_health_bar_percent(scan_image, blood_bar, target_rgb)

    return {
        "success": True,
        "hp_percent": hp_percent,
        "blood_bar": blood_bar,
        "match_count": len(matches),
        "player": {
            "x": player_x,
            "y": player_y,
        },
        "player_position": position,
        "client": client,
        "message": f"自身血量检测完成 hp={hp_percent}% matches={len(matches)} bar={blood_bar}",
    }


# 查找玩家自身绿色血条特征。
def find_player_blood_feature_matches(screen_file):
    screen = read_cv2_image(screen_file)
    templates = get_player_blood_feature_templates()
    matches = []

    for template in templates:
        image = template["image"]

        if image.shape[0] > screen.shape[0] or image.shape[1] > screen.shape[1]:
            continue

        result = cv2.matchTemplate(screen, image, cv2.TM_SQDIFF_NORMED)
        ys, xs = np.where(result <= MONSTER_FEATURE_MATCH_THRESHOLD)

        for y, x in zip(ys, xs):
            matches.append({
                "x": int(x),
                "y": int(y),
                "width": template["blood_width"],
                "height": template["blood_height"],
            })

    return dedupe_matches(filter_player_blood_matches(screen, matches))


# 获取玩家自身血条模板：使用资源原始尺寸匹配当前截图。
def get_player_blood_feature_templates():
    feature = read_cv2_image(player_blood_feature_image)
    blood_width, blood_height = get_image_size(green_blood_bar_image)

    return [{
        "image": feature,
        "blood_width": blood_width,
        "blood_height": blood_height,
    }]


# 过滤底部 UI 区域，避免把界面血量槽误认为玩家头顶血条。
def filter_player_blood_matches(screen, matches):
    play_area_bottom = max(1, screen.shape[0] - BOTTOM_UI_HEIGHT)
    filtered = []

    for match in matches:
        bar_bottom = int(match["y"]) + int(match.get("height", 0))

        if bar_bottom >= play_area_bottom:
            continue

        filtered.append(match)

    return filtered


# 把血条匹配点转换为 right/bottom 开区间矩形。
def make_blood_bar_from_match(match, width, height):
    bar_left = int(match["x"])
    bar_top = int(match["y"])
    bar_right = min(width, bar_left + int(match.get("width", 0)))
    bar_bottom = min(height, bar_top + int(match.get("height", 0)))
    return {
        "left": bar_left,
        "top": bar_top,
        "right": bar_right,
        "bottom": bar_bottom,
    }


# 计算匹配血条中心到指定点的距离。
def get_match_distance_to_point(match, x, y):
    center_x = int(match["x"]) + int(match.get("width", 0)) / 2
    center_y = int(match["y"]) + int(match.get("height", 0)) / 2
    return math.dist((x, y), (center_x, center_y))


# 从血条模板读取主要填充色，失败时回退到纯绿色。
def get_health_bar_fill_rgb(image_file):
    try:
        with Image.open(image_file) as image:
            pixels = np.array(image.convert("RGB"))

        bright_pixels = pixels[np.any(pixels > 80, axis=2)]

        if len(bright_pixels) == 0:
            return GREEN_HEALTH_BAR_RGB

        colors, counts = np.unique(bright_pixels.reshape(-1, 3), axis=0, return_counts=True)
        color = colors[int(counts.argmax())]
        return int(color[0]), int(color[1]), int(color[2])
    except Exception:
        return GREEN_HEALTH_BAR_RGB


# 截图：截取当前绑定窗口并返回截图保存路径。
def capture_screenshot():
    if not op.is_window_bound():
        return {
            "success": False,
            "path": "",
            "client": {},
            "image": {},
            "message": "还没有绑定窗口",
        }

    # 绑定窗口尺寸：同时保留原始尺寸和实际截图尺寸，方便排查分辨率问题。
    client = get_bound_client_info()
    width, height = client["width"], client["height"]

    if width <= 0 or height <= 0:
        return {
            "success": False,
            "path": "",
            "client": client,
            "image": {},
            "message": f"窗口尺寸异常 size={width}x{height}",
        }

    # 截图文件路径：为本次截图选择一个未占用的文件名。
    screenshot_file = get_next_screenshot_file()
    success, message = capture_bound_client_checked(0, 0, width, height, screenshot_file)

    if success and screenshot_file.exists():
        image = get_image_dimensions(screenshot_file)
        image_text = ""

        if image:
            image_text = f" image={image['width']}x{image['height']}"

        return {
            "success": True,
            "path": str(screenshot_file),
            "client": client,
            "image": image,
            "message": (
                f"绑定窗口截图成功 path={screenshot_file} "
                f"client={width}x{height} raw={client['raw_width']}x{client['raw_height']}"
                f"{image_text} {message}"
            ),
        }

    return {
        "success": False,
        "path": str(screenshot_file),
        "client": client,
        "image": {},
        "message": message,
    }


# 截取绑定窗口区域并检测黑屏：黑屏时重启 OP 后重试一次。
def capture_bound_client_checked(x1, y1, x2, y2, file_path):
    success, message = op.capture_bound_client(x1, y1, x2, y2, file_path)

    if success and Path(file_path).exists() and image_has_content(file_path):
        return True, message

    if not success:
        return success, message

    rebind_success, _, rebind_message = op.restart_and_rebind_window()

    if not rebind_success:
        return False, f"{message}；截图黑屏，自动重启绑定失败: {rebind_message}"

    retry_success, retry_message = op.capture_bound_client(x1, y1, x2, y2, file_path)

    if retry_success and Path(file_path).exists() and image_has_content(file_path):
        return True, f"{message}；首次截图黑屏，已自动重启绑定: {rebind_message}；{retry_message}"

    return False, f"{message}；截图黑屏，自动重启绑定后仍失败: {rebind_message}；{retry_message}"


# 判断截图是否有非黑内容。
def image_has_content(image_file):
    try:
        with Image.open(image_file) as image:
            return image.convert("RGB").getbbox() is not None
    except Exception:
        return False


# 读取图片尺寸：截图诊断用，失败时返回空字典避免影响主流程。
def get_image_dimensions(image_file):
    try:
        with Image.open(image_file) as image:
            return {
                "width": image.width,
                "height": image.height,
            }
    except Exception:
        return {}


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


# 扫描怪物：查找血条、读取血量，并计算到玩家的距离。
def scan_monsters():
    with monster_scan_lock:
        try:
            return scan_monsters_locked()
        except Exception as error:
            return {
                "success": False,
                "monsters": [],
                "message": f"怪物扫描异常: {error}",
            }


# 执行怪物扫描：由锁保护的实际扫描流程。
def scan_monsters_locked():
    if not op.is_window_bound():
        return {
            "success": False,
            "monsters": [],
            "message": "还没有绑定窗口",
        }

    if not monster_blood_feature_image.exists():
        return {
            "success": False,
            "monsters": [],
            "message": f"找不到血条特征图: {monster_blood_feature_image}",
        }

    if not red_blood_bar_image.exists():
        return {
            "success": False,
            "monsters": [],
            "message": f"找不到红色血条模板: {red_blood_bar_image}",
        }

    client = get_bound_client_info()
    width, height = client["width"], client["height"]

    if width <= 0 or height <= 0:
        return {
            "success": False,
            "monsters": [],
            "client": client,
            "message": f"窗口尺寸异常 size={width}x{height}",
        }

    try:
        player_x, player_y, position = get_bound_player_foot_point()
    except ValueError as error:
        return {
            "success": False,
            "monsters": [],
            "client": client,
            "message": str(error),
        }

    blood_width, blood_height = get_image_size(red_blood_bar_image)
    debug_points = [
        make_debug_point(player_x, player_y, "blue"),
    ]

    with tempfile.TemporaryDirectory(prefix="mir2_monster_scan_") as temp_dir:
        temp_path = Path(temp_dir)
        scan_file = temp_path / "screen.bmp"
        success, capture_message = capture_bound_client_checked(
            0,
            0,
            width - 1,
            height - 1,
            scan_file,
        )

        if not success or not scan_file.exists():
            return {
                "success": False,
                "monsters": [],
                "client": client,
                "message": f"怪物扫描截图失败: {capture_message}",
            }

        matches = find_blood_feature_matches(scan_file, ignore_bottom_ui=True)
        monsters = []

        with Image.open(scan_file) as scan_image:
            for index, match in enumerate(matches, start=1):
                monster = read_monster_from_match(
                    index,
                    match,
                    scan_image,
                    temp_path,
                    width,
                    height,
                    blood_width,
                    blood_height,
                    player_x,
                    player_y,
                )
                monsters.append(monster)
                debug_points.extend(monster["debug_points"])

    monsters.sort(key=lambda monster: monster["distance"])

    for index, monster in enumerate(monsters, start=1):
        monster["id"] = index

    return {
        "success": True,
        "monsters": monsters,
        "count": len(monsters),
        "player": {
            "x": player_x,
            "y": player_y,
        },
        "player_position": position,
        "client": client,
        "debug_points": debug_points,
        "message": f"怪物扫描完成 count={len(monsters)} player={player_x},{player_y} client_size={width}x{height}",
    }


# 根据一个血条匹配点读取怪物信息。
def read_monster_from_match(index, match, scan_image, temp_path, width, height, blood_width, blood_height, player_x, player_y):
    bar_left = match["x"]
    bar_top = match["y"]
    match_blood_width = match.get("width", blood_width)
    match_blood_height = match.get("height", blood_height)
    bar_right = min(width, bar_left + match_blood_width)
    bar_bottom = min(height, bar_top + match_blood_height)
    blood_bar = {
        "left": bar_left,
        "top": bar_top,
        "right": bar_right,
        "bottom": bar_bottom,
    }
    hover_x, hover_y = get_monster_hover_from_bar(blood_bar, width, height)
    bar_center_x = round((bar_left + bar_right) / 2)

    name_box = clamp_box(
        bar_center_x - MONSTER_NAME_HALF_WIDTH,
        bar_bottom + MONSTER_NAME_TOP_OFFSET,
        bar_center_x + MONSTER_NAME_HALF_WIDTH,
        bar_bottom + MONSTER_NAME_BOTTOM_OFFSET,
        width,
        height,
    )

    distance = round(math.dist((player_x, player_y), (hover_x, hover_y)))
    hp_percent = calculate_health_bar_percent(scan_image, blood_bar, RED_HEALTH_BAR_RGB)

    return {
        "id": index,
        "name": "未识别",
        "distance": distance,
        "hp_percent": hp_percent,
        "name_text": "",
        "position": {
            "x": hover_x,
            "y": hover_y,
        },
        "blood_bar": blood_bar,
        "ocr_boxes": {
            "name": name_box,
        },
        "debug_points": [
            make_debug_point(bar_left, bar_top, "red"),
            make_debug_point(hover_x, hover_y, "orange"),
            make_debug_point(*box_center(name_box), "purple"),
        ],
    }


# 识别单个怪物名称：按表格传入的位置和血条信息补充名称。
def recognize_monster_name(position_x, position_y, blood_bar=None, save_debug=True):
    with monster_scan_lock:
        try:
            return recognize_monster_name_locked(position_x, position_y, blood_bar, save_debug)
        except Exception as error:
            return {
                "success": False,
                "name": "未识别",
                "name_text": "",
                "message": f"怪物名称识别异常: {error}",
            }


# 执行单个怪物名称识别：只悬停并 OCR 当前指定怪物。
def recognize_monster_name_locked(position_x, position_y, blood_bar=None, save_debug=True):
    if not op.is_window_bound():
        return {
            "success": False,
            "name": "未识别",
            "name_text": "",
            "message": "还没有绑定窗口",
        }

    client = get_bound_client_info()
    width, height = client["width"], client["height"]

    if width <= 0 or height <= 0:
        return {
            "success": False,
            "name": "未识别",
            "name_text": "",
            "client": client,
            "message": f"窗口尺寸异常 size={width}x{height}",
        }

    active_blood_bar = None

    if blood_bar and is_valid_blood_bar(blood_bar):
        active_blood_bar = refresh_monster_blood_bar(blood_bar, width, height)

    if active_blood_bar:
        hover_x, hover_y = get_monster_hover_from_bar(active_blood_bar, width, height)
        name_box = get_monster_name_box_from_bar(active_blood_bar, width, height)
    else:
        hover_x = clamp_number(position_x, 0, width - 1)
        hover_y = clamp_number(position_y, 0, height - 1)
        name_box = get_monster_name_box_from_position(hover_x, hover_y, width, height)

    move_success, move_message = op.move_mouse_to(hover_x, hover_y)

    if not move_success:
        debug_points = []

        if active_blood_bar:
            debug_points.append(make_debug_point(active_blood_bar["left"], active_blood_bar["top"], "red"))

        debug_points.extend([
            make_debug_point(hover_x, hover_y, "orange"),
            make_debug_point(*box_center(name_box), "purple"),
        ])

        return {
            "success": False,
            "name": "未识别",
            "name_text": "",
            "position": {
                "x": hover_x,
                "y": hover_y,
            },
            "ocr_box": name_box,
            "blood_bar": active_blood_bar,
            "raw_text": "",
            "mask_text": "",
            "used_attempt": 0,
            "reject_reason": "hover_failed",
            "debug_images": [],
            "move_success": move_success,
            "move_message": move_message,
            "client": client,
            "debug_points": debug_points,
            "message": f"怪物名称识别失败: {move_message}",
        }

    time.sleep(MONSTER_HOVER_WAIT_SECONDS)

    name_result = recognize_monster_name_box(name_box, save_debug)
    name_text = name_result["text"]
    name = name_result["name"]
    debug_points = []

    if active_blood_bar:
        debug_points.append(make_debug_point(active_blood_bar["left"], active_blood_bar["top"], "red"))

    debug_points.extend([
        make_debug_point(hover_x, hover_y, "orange"),
        make_debug_point(*box_center(name_box), "purple"),
    ])

    return {
        "success": True,
        "name": name,
        "name_text": name_text,
        "position": {
            "x": hover_x,
            "y": hover_y,
        },
        "ocr_box": name_box,
        "blood_bar": active_blood_bar,
        "raw_text": name_result["raw_text"],
        "mask_text": name_result["mask_text"],
        "color": name_result.get("color", ""),
        "used_attempt": name_result["used_attempt"],
        "reject_reason": name_result["reject_reason"],
        "debug_images": name_result["debug_images"],
        "move_success": move_success,
        "move_message": move_message,
        "client": client,
        "debug_points": debug_points,
        "message": (
            f"怪物名称识别完成 name={name} text={name_text} "
            f"raw={name_result['raw_text']} mask={name_result['mask_text']} "
            f"color={name_result.get('color', '')} "
            f"attempt={name_result['used_attempt']} reject={name_result['reject_reason']} "
            f"bar={active_blood_bar} pos={hover_x},{hover_y}"
        ),
    }


# 根据血条位置计算怪物名 OCR 区域。
def get_monster_name_box_from_bar(blood_bar, width, height):
    bar_left = int(blood_bar["left"])
    bar_right = int(blood_bar["right"])
    bar_bottom = int(blood_bar["bottom"])
    bar_center_x = round((bar_left + bar_right) / 2)

    return clamp_box(
        bar_center_x - MONSTER_NAME_HALF_WIDTH,
        bar_bottom + MONSTER_NAME_TOP_OFFSET,
        bar_center_x + MONSTER_NAME_HALF_WIDTH,
        bar_bottom + MONSTER_NAME_BOTTOM_OFFSET,
        width,
        height,
    )


# 根据怪物位置反推怪物名 OCR 区域：用于没有血条信息时兜底。
def get_monster_name_box_from_position(x, y, width, height):
    return clamp_box(
        x - MONSTER_NAME_HALF_WIDTH,
        y - (MONSTER_HOVER_OFFSET_Y - MONSTER_NAME_TOP_OFFSET),
        x + MONSTER_NAME_HALF_WIDTH,
        y - (MONSTER_HOVER_OFFSET_Y - MONSTER_NAME_BOTTOM_OFFSET),
        width,
        height,
    )


# 判断血条字典是否可用。
def is_valid_blood_bar(blood_bar):
    return (
        isinstance(blood_bar, dict)
        and {"left", "top", "right", "bottom"}.issubset(blood_bar)
        and int(blood_bar["right"]) > int(blood_bar["left"])
        and int(blood_bar["bottom"]) > int(blood_bar["top"])
    )


# 根据血条位置计算怪物悬停/距离点。
def get_monster_hover_from_bar(blood_bar, width, height):
    bar_left = int(blood_bar["left"])
    bar_right = int(blood_bar["right"])
    bar_bottom = int(blood_bar["bottom"])
    bar_center_x = round((bar_left + bar_right) / 2)
    return (
        clamp_number(bar_center_x, 0, width - 1),
        clamp_number(bar_bottom + MONSTER_HOVER_OFFSET_Y, 0, height - 1),
    )


# 名字识别前刷新血条位置：怪物可能在列表扫描和点按钮之间移动。
def refresh_monster_blood_bar(blood_bar, width, height):
    if not is_valid_blood_bar(blood_bar):
        return None

    original = normalize_blood_bar(blood_bar, width, height)
    center_x = round((original["left"] + original["right"]) / 2)
    search_box = clamp_box(
        center_x - MONSTER_REFRESH_SEARCH_HALF_WIDTH,
        original["top"] - MONSTER_REFRESH_SEARCH_TOP_OFFSET,
        center_x + MONSTER_REFRESH_SEARCH_HALF_WIDTH,
        original["top"] + MONSTER_REFRESH_SEARCH_BOTTOM_OFFSET,
        width,
        height,
    )

    with tempfile.TemporaryDirectory(prefix="mir2_monster_refresh_") as temp_dir:
        search_file = Path(temp_dir) / "search.bmp"
        success, _ = capture_bound_client_checked(
            search_box["left"],
            search_box["top"],
            search_box["right"] - 1,
            search_box["bottom"] - 1,
            search_file,
        )

        if not success or not search_file.exists():
            return original

        matches = find_blood_feature_matches(search_file)

    if not matches:
        return original

    original_local_center = (
        center_x - search_box["left"],
        round((original["top"] + original["bottom"]) / 2) - search_box["top"],
    )
    nearest = min(
        matches,
        key=lambda match: math.dist(
            original_local_center,
            (
                match["x"] + match.get("width", 0) / 2,
                match["y"] + match.get("height", 0) / 2,
            ),
        ),
    )
    nearest_distance = math.dist(
        original_local_center,
        (
            nearest["x"] + nearest.get("width", 0) / 2,
            nearest["y"] + nearest.get("height", 0) / 2,
        ),
    )

    if nearest_distance > MONSTER_REFRESH_MAX_DISTANCE:
        return original

    return {
        "left": search_box["left"] + int(nearest["x"]),
        "top": search_box["top"] + int(nearest["y"]),
        "right": search_box["left"] + int(nearest["x"]) + int(nearest.get("width", 0)),
        "bottom": search_box["top"] + int(nearest["y"]) + int(nearest.get("height", 0)),
    }


# 规范化血条范围：限制到客户区内。
def normalize_blood_bar(blood_bar, width, height):
    return clamp_box(
        int(blood_bar["left"]),
        int(blood_bar["top"]),
        int(blood_bar["right"]),
        int(blood_bar["bottom"]),
        width,
        height,
    )


# 计算血条百分比：按目标颜色连续填充长度计算，适用于任意颜色血条。
def calculate_health_bar_percent(image, health_bar, target_rgb, tolerance=20):
    if not is_valid_box(health_bar):
        return 0

    pixels = np.array(image.convert("RGB"))
    image_height, image_width = pixels.shape[:2]
    box = normalize_blood_bar(health_bar, image_width, image_height)
    bar_width = box["right"] - box["left"]
    bar_height = box["bottom"] - box["top"]

    if bar_width <= 0 or bar_height <= 0:
        return 0

    fill_start = scale_health_bar_value(HEALTH_BAR_FILL_START_X, bar_width)
    full_fill_pixels = scale_health_bar_value(HEALTH_BAR_FULL_FILL_PIXELS, bar_width)

    if full_fill_pixels <= 0:
        return 0

    crop = pixels[box["top"]:box["bottom"], box["left"]:box["right"]]
    fill_rows = get_health_bar_fill_rows(bar_height)
    fill_pixels = 0

    for column_index in range(fill_start, min(bar_width, fill_start + full_fill_pixels)):
        column = crop[fill_rows, column_index, :]

        if not is_health_bar_filled_column(column, target_rgb, tolerance):
            break

        fill_pixels += 1

    percent = round(fill_pixels * 100 / full_fill_pixels)
    return clamp_number(percent, 0, 100)


# 按模板宽度把血条几何常量换算到当前截图血条宽度。
def scale_health_bar_value(value, bar_width):
    return max(0, round(value * bar_width / HEALTH_BAR_TEMPLATE_WIDTH))


# 获取血条内部填充行：排除上下黑边，按当前血条尺寸换算。
def get_health_bar_fill_rows(bar_height):
    if bar_height <= 2:
        return np.arange(0, bar_height)

    top = max(0, round(2 * bar_height / 8))
    bottom = min(bar_height, round(6 * bar_height / 8))

    if bottom <= top:
        return np.arange(0, bar_height)

    return np.arange(top, bottom)


# 判断一列是否接近目标血条颜色。
def is_health_bar_filled_column(column, target_rgb, tolerance):
    if len(column) == 0:
        return False

    target = np.array(target_rgb, dtype=np.int16)
    delta = np.abs(column.astype(np.int16) - target)
    matching_pixels = np.all(delta <= tolerance, axis=1)
    return int(matching_pixels.sum()) * 2 >= len(column)


# 识别怪物名区域：用 OP 大漠字库直接识别绑定窗口文字。
def recognize_monster_name_box(box, save_debug=True):
    empty_result = {
        "name": "未识别",
        "text": "",
        "raw_text": "",
        "mask_text": "",
        "color": "",
        "used_attempt": 0,
        "reject_reason": "",
        "debug_images": [],
    }

    if not is_valid_box(box):
        return empty_result

    if save_debug:
        debug_image_dir.mkdir(exist_ok=True)
        debug_prefix = get_debug_image_prefix("monster_name")

    last_result = empty_result
    ocr_colors = get_monster_name_ocr_colors()

    for attempt in range(1, MONSTER_NAME_OCR_MAX_ATTEMPTS + 1):
        if attempt > 1:
            time.sleep(MONSTER_NAME_OCR_RETRY_DELAY_SECONDS)

        raw_file = ""

        if save_debug:
            raw_file = debug_image_dir / f"{debug_prefix}_raw_{attempt}.bmp"
            success, _ = capture_bound_client_checked(
                box["left"],
                box["top"],
                box["right"] - 1,
                box["bottom"] - 1,
                raw_file,
            )

            if not success:
                last_result = {
                    **last_result,
                    "used_attempt": attempt,
                    "debug_images": [
                        *last_result["debug_images"],
                        {
                            "attempt": attempt,
                            "raw": str(raw_file),
                            "raw_text": "",
                            "mask_text": "",
                        },
                    ],
                }
                continue

        for ocr_color in ocr_colors:
            raw_text = op.ocr_text(
                box["left"],
                box["top"],
                box["right"] - 1,
                box["bottom"] - 1,
                color=ocr_color,
            )
            mask_text = ""
            selected_text = raw_text
            selected_name = clean_monster_name(selected_text)
            reject_reason = get_monster_name_reject_reason(selected_name)
            debug_images = last_result["debug_images"]

            if save_debug:
                debug_images = [
                    *debug_images,
                    {
                        "attempt": attempt,
                        "raw": str(raw_file),
                        "color": ocr_color,
                        "raw_text": raw_text,
                        "mask_text": mask_text,
                    },
                ]

            if reject_reason:
                last_result = {
                    "name": "未识别",
                    "text": selected_text,
                    "raw_text": raw_text,
                    "mask_text": mask_text,
                    "color": ocr_color,
                    "used_attempt": attempt,
                    "reject_reason": reject_reason,
                    "debug_images": debug_images,
                }
                continue

            last_result = {
                "name": selected_name,
                "text": selected_text,
                "raw_text": raw_text,
                "mask_text": mask_text,
                "color": ocr_color,
                "used_attempt": attempt,
                "reject_reason": "",
                "debug_images": debug_images,
            }

            if selected_name != "未识别":
                return last_result

    return last_result


# 创建本次调试图片文件名前缀：时间戳加短序号，便于按一次识别归档。
def get_debug_image_prefix(prefix):
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    sequence = time.time_ns() % 1_000_000
    return f"{prefix}_{timestamp}_{sequence:06d}"


# 判断 OCR 结果是否像是误读到了主角名。
def get_monster_name_reject_reason(name):
    if name == "未识别":
        return ""

    player_name = get_bound_player_name()

    if not player_name:
        return ""

    if name in player_name or player_name in name:
        return "player_name_contamination"

    return ""


# 从窗口标题中提取主角名，例如“^纵横四海 - 闪电侠”。
def get_bound_player_name():
    position = get_bound_player_position()
    player_name = normalize_player_name_text(position.get("name", ""))

    if player_name:
        return player_name

    title = op.get_bound_window().get("title", "")
    match = re.search(r"[-－]\s*([^\s\-－]+)\s*$", title)

    if not match:
        return ""

    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9_]", "", match.group(1))


# 查找血条左侧特征：返回所有精确匹配的左上角坐标。
def find_blood_feature_matches(screen_file, ignore_bottom_ui=False):
    screen = read_cv2_image(screen_file)
    templates = get_blood_feature_templates()
    matches = []

    for template in templates:
        image = template["image"]

        if image.shape[0] > screen.shape[0] or image.shape[1] > screen.shape[1]:
            continue

        result = cv2.matchTemplate(screen, image, cv2.TM_SQDIFF_NORMED)
        ys, xs = np.where(result <= MONSTER_FEATURE_MATCH_THRESHOLD)

        for y, x in zip(ys, xs):
            matches.append({
                "x": int(x),
                "y": int(y),
                "width": template["blood_width"],
                "height": template["blood_height"],
            })

    if ignore_bottom_ui:
        matches = filter_play_area_blood_matches(screen, matches)

    if not matches:
        matches = find_red_bar_component_matches(screen, ignore_bottom_ui)

    return dedupe_matches(matches)


# 过滤底部界面里的误匹配：怪物点击点落到底栏时不当作可攻击怪物。
def filter_play_area_blood_matches(screen, matches):
    play_area_bottom = max(1, screen.shape[0] - BOTTOM_UI_HEIGHT)
    filtered = []

    for match in matches:
        bar_bottom = int(match["y"]) + int(match.get("height", 0))
        hover_y = bar_bottom + MONSTER_HOVER_OFFSET_Y

        if hover_y >= play_area_bottom:
            continue

        filtered.append(match)

    return filtered


# 获取血条特征模板：使用资源原始尺寸匹配当前截图。
def get_blood_feature_templates():
    feature = read_cv2_image(monster_blood_feature_image)
    blood_width, blood_height = get_image_size(red_blood_bar_image)

    return [{
        "image": feature,
        "blood_width": blood_width,
        "blood_height": blood_height,
    }]


# 查找红色水平血条组件：作为特征模板未命中时的兜底。
def find_red_bar_component_matches(screen, ignore_bottom_ui=False):
    red_mask = (
        (screen[:, :, 2] > 140)
        & (screen[:, :, 1] < 100)
        & (screen[:, :, 0] < 100)
    )
    component_count, _, stats, _ = cv2.connectedComponentsWithStats(red_mask.astype("uint8"), 8)
    matches = []
    play_area_bottom = max(1, screen.shape[0] - BOTTOM_UI_HEIGHT)

    for index in range(1, component_count):
        x, y, width, height, area = stats[index]

        if ignore_bottom_ui and y + height + MONSTER_HOVER_OFFSET_Y >= play_area_bottom:
            continue

        if width < 8 or width > 90:
            continue

        if height < 1 or height > 4:
            continue

        if area < width * height * 0.8:
            continue

        matches.append({
            "x": max(0, int(x) - 1),
            "y": max(0, int(y) - 1),
            "width": int(width) + 2,
            "height": int(height) + 2,
        })

    return matches


# 读取 OpenCV 图片：兼容 Windows 中文路径。
def read_cv2_image(image_file):
    image_path = Path(image_file)
    data = np.fromfile(str(image_path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)

    if image is None:
        raise RuntimeError(f"读取图片失败: {image_path}")

    return image


# 去重匹配点：避免同一血条附近重复命中。
def dedupe_matches(matches):
    deduped = []

    for match in sorted(matches, key=lambda item: (item["y"], item["x"])):
        duplicate = False

        for existing in deduped:
            x_limit = max(4, min(match.get("width", 4), existing.get("width", 4)) // 2)
            y_limit = max(4, min(match.get("height", 4), existing.get("height", 4)) * 2)

            if (
                abs(match["x"] - existing["x"]) <= x_limit
                and abs(match["y"] - existing["y"]) <= y_limit
            ):
                duplicate = True
                break

        if not duplicate:
            deduped.append(match)

    return deduped


# 获取图片尺寸：用于血条模板宽高。
def get_image_size(image_file):
    with Image.open(image_file) as image:
        return image.size


# 清理怪物名识别文本：优先取 4 个以内中文字符。
def clean_monster_name(text):
    cleaned = re.sub(r"\s+", "", text or "")
    match = re.search(r"[\u4e00-\u9fff]{1,6}", cleaned)

    if match:
        return match.group(0)[:4]

    if cleaned:
        return cleaned[:8]

    return "未识别"


# 限制矩形范围：使用 right/bottom 作为开区间。
def clamp_box(left, top, right, bottom, width, height):
    left = clamp_number(round(left), 0, max(0, width - 1))
    top = clamp_number(round(top), 0, max(0, height - 1))
    right = clamp_number(round(right), left + 1, width)
    bottom = clamp_number(round(bottom), top + 1, height)

    return {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
    }


# 判断矩形是否可用于截图。
def is_valid_box(box):
    return box["right"] > box["left"] and box["bottom"] > box["top"]


# 获取矩形中心点。
def box_center(box):
    return round((box["left"] + box["right"]) / 2), round((box["top"] + box["bottom"]) / 2)


# 限制数值范围。
def clamp_number(value, minimum, maximum):
    return max(minimum, min(maximum, int(value)))


# 创建调试点。
def make_debug_point(x, y, color):
    return {
        "x": int(x),
        "y": int(y),
        "color": color,
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

    # OP 字库文本：承载坐标区域识别出的原始文字。
    text = op.ocr_text(x1, y1, x2, y2)
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
    width, height = get_bound_client_size()

    if width <= 0 or height <= 0:
        return {"success": False, "message": f"窗口尺寸异常 size={width}x{height}"}

    try:
        player_x, player_y, position = get_bound_player_foot_point()
    except ValueError as error:
        return {
            "success": False,
            "action": action,
            "direction": direction,
            "message": str(error),
        }

    # 移动点击参数：保存本次动作的按钮、坐标和地图增量。
    move = calculate_move(action, direction, width, height, player_x, player_y)

    # 点击执行结果：记录 OP 鼠标点击是否成功及其说明。
    success, message = op.click_mouse_at(move["click_x"], move["click_y"], move["button"])

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
        "player_position": position,
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


# 规整布尔开关：兼容 JSON 布尔值和页面字符串。
def normalize_bool(value):
    if isinstance(value, bool):
        return value

    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on", "开", "开启"}


# 计算移动点击：把动作和方向转换为客户端内的点击坐标。
def calculate_move(action, direction, width, height, origin_x, origin_y):
    # 地图方向增量：描述移动后地图坐标预期变化。
    dx, dy = directions[direction]
    # 动作配置：读取按钮、点击距离和步长等动作参数。
    config = move_actions[action]
    # 点击方向向量：描述鼠标在屏幕上应该偏移的方向。
    click_dx, click_dy = get_click_direction(action, direction)
    # 移动原点：以绑定时 OCR 定位到的玩家脚底作为点击基准。
    origin_x = int(origin_x)
    origin_y = int(origin_y)

    return {
        "button": config["button"],
        "click_x": clamp_number(round(origin_x + click_dx * config["offset"]), 0, width - 1),
        "click_y": clamp_number(round(origin_y + click_dy * config["offset"]), 0, height - 1),
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

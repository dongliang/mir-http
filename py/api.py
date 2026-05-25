import ctypes
import json
import math
import os
import re
import shutil
import tempfile
import threading
import time
import unicodedata
from ctypes import wintypes
from pathlib import Path
from urllib.parse import quote

import cv2
import numpy as np
from PIL import Image

import op
import win32


# 项目根目录：业务脚本在 py/ 下，运行资源仍在项目根目录。
base_dir = Path(__file__).resolve().parent.parent
# 文本配置目录：保存可运行时重载的简单清单。
txt_dir = base_dir / "txt"
# 账号配置目录：每个账号一份可独立调整的 txt 配置。
accounts_dir = base_dir / "accounts"
# 项目地图目录：保存手动截取的地图图片、元信息和全局巡逻点。
maps_dir = base_dir / "maps"
# PNG 资源目录：保存血条特征图等图像匹配资源。
png_dir = base_dir / "png"


# 生成未绑定时的实例目录名：优先使用 start.bat 注入的端口，缺省用进程号。
def get_runtime_instance_name():
    port_text = os.environ.get("MIR2AUTO_HTTP_PORT", "").strip()

    if port_text.isdigit():
        return f"port_{port_text}"

    return f"pid_{os.getpid()}"


# 获取未绑定实例目录。
def get_initial_output_dir():
    return accounts_dir / "_runtime" / get_runtime_instance_name()


# 切换当前进程输出目录：截图、地图和诊断图都跟随这个目录。
def configure_output_dir(run_dir):
    global output_dir
    global screenshot_dir
    global debug_image_dir
    global coordinate_image
    global map_max_coordinate_image

    output_dir = Path(run_dir)
    screenshot_dir = output_dir / "screenshots"
    debug_image_dir = output_dir / "DebugImage"
    coordinate_image = screenshot_dir / "map_coordinate.bmp"
    map_max_coordinate_image = screenshot_dir / "map_max_coordinate.bmp"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


# 切换到未绑定实例目录。
def configure_initial_output_dir():
    return configure_output_dir(get_initial_output_dir())


# 切换到账号目录。
def configure_account_output_dir(account):
    return configure_output_dir(get_account_dir(account))


# 获取当前进程输出目录。
def get_output_dir():
    return output_dir


# 当前运行输出目录：启动未绑定时按端口或进程号隔离。
output_dir = configure_initial_output_dir()
# 地图图片文件名：项目级地图库中固定保存为 image.png。
MAP_IMAGE_NAME = "image.png"
# 地图元信息文件名：保存最大逻辑坐标和截图时的诊断信息。
MAP_METADATA_NAME = "map.json"
# 巡逻点文件名：全局和账号目录下都使用同一个中文文件名。
PATROL_POINTS_FILE_NAME = "巡逻点.txt"
# 怪物血条特征图：血条最左侧小片段，用于统一查找满血和残血怪物。
monster_blood_feature_image = png_dir / "残血血条特征图.png"
# 自身绿色血条特征图：用于自动加血检测玩家头顶血条。
player_blood_feature_image = png_dir / "自身绿色残血血条特征图.png"
# 坐标读取锁：串行化截图和 OP 字库识别流程，避免并发读写同一张截图。
coordinate_lock = threading.Lock()
# 怪物扫描锁：串行化截图、鼠标悬停和 OP 字库识别流程。
monster_scan_lock = threading.Lock()
# 自动加血锁：避免页面主动刷新和后台刷新同时触发 F1。
auto_heal_lock = threading.Lock()
# 账号配置锁：保护当前账号名称和账号目录创建。
account_lock = threading.Lock()
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
# 当前账号配置：为空时读取根目录 txt/。
account_state = {
    "current": "",
}
# 怪物关键字清单缓存：运行时加载，可由网页按钮重载。
monster_keyword_lock = threading.Lock()
monster_keyword_state = {
    "loaded": False,
    "mtime": 0,
    "path": "",
    "keywords": [],
    "message": "",
}
# 怪物名 OCR 颜色缓存：运行时加载，可由网页按钮重载。
monster_name_color_lock = threading.Lock()
monster_name_color_state = {
    "loaded": False,
    "mtime": 0,
    "path": "",
    "colors": [],
    "message": "",
}
# 物品关键字清单缓存：运行时加载，可由网页按钮重载。
item_keyword_lock = threading.Lock()
item_keyword_state = {
    "loaded": False,
    "mtime": 0,
    "path": "",
    "keywords": [],
    "entries": [],
    "message": "",
}
# 物品名 OCR 颜色缓存：运行时加载，可由网页按钮重载。
item_name_color_lock = threading.Lock()
item_name_color_state = {
    "loaded": False,
    "mtime": 0,
    "path": "",
    "colors": [],
    "message": "",
}
# 捡取物品运行状态：保存最近目标和消息，供页面状态展示。
getitem_runtime_lock = threading.Lock()
getitem_runtime_state = {
    "last_target": {},
    "last_message": "",
}
# 地图坐标识别原文：保存最近一次 OP OCR 返回的 raw 文本，供页面常驻显示。
map_coordinate_debug_state = {
    "raw": "",
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
# 大地图自动打开：预检查失败时后台按 M 两次后再绑定。
MAP_AUTO_OPEN_KEY = "M"
MAP_AUTO_OPEN_HOLD_MS = 120
MAP_AUTO_OPEN_REPEAT = 2
MAP_AUTO_OPEN_INTERVAL_MS = 150
MAP_AUTO_OPEN_WAIT_SECONDS = 0.5
# 大地图自动隐藏：绑定成功后后台按 M 一次收起地图。
MAP_AUTO_HIDE_KEY = "M"
MAP_AUTO_HIDE_HOLD_MS = 120
MAP_AUTO_HIDE_REPEAT = 1
MAP_AUTO_HIDE_INTERVAL_MS = 80
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
MONSTER_HOVER_WAIT_SECONDS = 0.5
# 怪物名字识别最大截图次数：第一次未截到字或识别为空时短暂重试。
MONSTER_NAME_OCR_MAX_ATTEMPTS = 2
# 怪物名字识别重试等待时间：给 hover 名字显示留出额外缓冲。
MONSTER_NAME_OCR_RETRY_DELAY_SECONDS = 0.5
# 怪物名字 OCR 相似度：彩色抗锯齿文字比白字更容易抖，略低于默认值。
MONSTER_NAME_OCR_SIM = 0.85
# 怪物名默认 OCR 颜色：配置文件缺失或为空时使用。
DEFAULT_MONSTER_NAME_OCR_COLORS = [
    "00f7f7-101010",
    "00ffff-101010",
    "ffffff-101010",
    "ffff00-101010",
]
# 物品名默认 OCR 颜色：配置文件缺失或为空时使用。
DEFAULT_ITEM_NAME_OCR_COLORS = [
    "ffffff-101010",
    "ffff00-101010",
    "00ffff-101010",
]
# 捡取安全检测范围：以角色脚底为中心，只用于近身怪物检测。
GETITEM_SEARCH_WIDTH = 350
GETITEM_SEARCH_HEIGHT = 250
# 物品文字尺寸和点击偏移：OP 找字返回文字左上角，点击地面物品中心。
ITEM_NAME_TEXT_WIDTH = 12
ITEM_NAME_TEXT_ASCII_WIDTH = 6
ITEM_NAME_TEXT_HEIGHT = 12
ITEM_CLICK_OFFSET_Y = 32
ITEM_NAME_OCR_SIM = 0.85
# 同一目标跟踪半径：同名物品优先追踪上次点击附近的命中。
GETITEM_TARGET_MATCH_RADIUS = 120
# 逻辑坐标到达半径：物品拾取按格子判断，0 表示必须走到估算目标格。
GETITEM_TARGET_ARRIVAL_RADIUS = 0
# 捡取移动动作切换：距离 2 格以内走路，更远时跑步。
GETITEM_WALK_MAX_LOGIC_DISTANCE = 2
# 捡取点击后等待角色走路的默认间隔。
GETITEM_DEFAULT_STEP_WAIT_MS = 100
GETITEM_MIN_STEP_WAIT_MS = 100
GETITEM_MAX_STEP_WAIT_MS = 10000
# 拾取专用投影：逻辑坐标轴在游戏客户区屏幕上的像素偏移。
GETITEM_LOGIC_X_SCREEN_DX = 51
GETITEM_LOGIC_X_SCREEN_DY = 1
GETITEM_LOGIC_Y_SCREEN_DX = -1
GETITEM_LOGIC_Y_SCREEN_DY = 31
# 怪物血条刷新搜索范围：识别名字前围绕旧血条局部重扫，降低怪物移动影响。
MONSTER_REFRESH_SEARCH_HALF_WIDTH = 180
MONSTER_REFRESH_SEARCH_TOP_OFFSET = 100
MONSTER_REFRESH_SEARCH_BOTTOM_OFFSET = 160
MONSTER_REFRESH_MAX_DISTANCE = 180
# 血条填充像素：从匹配框第二列、第二行开始检测，避开黑色边框。
HEALTH_BAR_WIDTH_PIXELS = 32
HEALTH_BAR_FILL_START_X = 1
HEALTH_BAR_FILL_START_Y = 1
HEALTH_BAR_FULL_FILL_PIXELS = 30
# 怪物红色血条填充色。
RED_HEALTH_BAR_RGB = (255, 0, 0)
# 玩家绿色血条填充色。
GREEN_HEALTH_BAR_RGB = (0, 255, 0)
# 自动加血默认配置和边界：页面和接口都会按这些范围规整输入。
AUTO_HEAL_DEFAULT_THRESHOLD_PERCENT = 85
AUTO_HEAL_DEFAULT_INTERVAL_MS = 1000
AUTO_HEAL_MIN_THRESHOLD_PERCENT = 1
AUTO_HEAL_MAX_THRESHOLD_PERCENT = 100
AUTO_HEAL_MIN_INTERVAL_MS = 500
AUTO_HEAL_MAX_INTERVAL_MS = 60000
# 宝宝加血默认配置：找怪时识别到当前账号召唤物后按阈值触发。
PET_HEAL_DEFAULT_THRESHOLD_PERCENT = 85
PET_HEAL_MIN_THRESHOLD_PERCENT = 1
PET_HEAL_MAX_THRESHOLD_PERCENT = 100
PET_HEAL_DEFAULT_KEY = "F1"
PET_HEAL_COOLDOWN_SECONDS = 3.0
# idle 卡住保护默认配置和边界。
IDLE_STUCK_DEFAULT_SECONDS = 30
IDLE_STUCK_MIN_SECONDS = 5
IDLE_STUCK_MAX_SECONDS = 600
# 战斗找怪默认配置：近处优先、连续无怪跳点和锁定目标找回。
NO_MONSTER_SCAN_LIMIT_DEFAULT = 3
NO_MONSTER_SCAN_LIMIT_MIN = 1
NO_MONSTER_SCAN_LIMIT_MAX = 20
NEAR_MONSTER_LOGIC_RADIUS = 6
TARGET_RECHECK_SECONDS = 1.0
ATTACK_CLICK_INTERVAL_SECONDS = 2.0
TARGET_LOST_SCAN_COUNT = 2
LOCK_STRONG_RADIUS = 1
LOCK_WEAK_RADIUS = 2
LOCK_WEAK_SCREEN_RADIUS = 120
LOCK_HP_RISE_TOLERANCE = 15
IGNORED_TARGET_SECONDS = 8
IGNORED_TARGET_RADIUS = 2
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
    "walk": {"button": "left", "offset": 130, "step": 1},
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

    account_result = activate_account(keyword)

    if not account_result["success"]:
        unbind_success, _, unbind_message = op.unbind_window()
        clear_bound_player_position()
        return {
            "success": False,
            "title": title,
            "message": (
                f"{message}；账号切换失败: {account_result['message']}；"
                f"已自动解绑 success={unbind_success} {unbind_message}"
            ),
            "account": account_result,
            "output_dir": str(get_output_dir()),
        }

    return {
        "success": success,
        "title": title,
        "message": f"{message}；{position_result['message']}；{account_result['message']}",
        "player_position": get_bound_player_position(),
        "account": account_result,
        "output_dir": account_result.get("output_dir", str(get_output_dir())),
    }


# 解绑窗口：释放 OP 绑定并隐藏现有点击提示。
def unbind_window():
    success, title, message = op.unbind_window()

    if success:
        clear_bound_player_position()
        text_config = clear_current_account()
        message = f"{message}；账号已清空；{text_config.get('message', '')}"

    return {
        "success": success,
        "title": title,
        "message": message,
        "output_dir": str(get_output_dir()),
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


# 清理账号目录名：保留可读名称，只替换 Windows 文件名非法字符。
def normalize_account_name(account):
    name = str(account or "").strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", name)
    return name.strip(" .")


# 列出已有账号目录。
def list_accounts():
    if not accounts_dir.exists():
        return []

    return sorted(
        path.name
        for path in accounts_dir.iterdir()
        if path.is_dir() and path.name != "_runtime"
    )


# 获取当前账号名。
def get_current_account():
    with account_lock:
        return account_state.get("current", "")


# 清空当前账号，后续配置读取回到根目录 txt/。
def clear_current_account():
    with account_lock:
        account_state["current"] = ""

    output = configure_initial_output_dir()
    result = load_text_configs()
    result["output_dir"] = str(output)
    return result


# 获取账号配置目录。
def get_account_dir(account):
    return accounts_dir / normalize_account_name(account)


# 清理地图目录名：保留地图显示名，只替换 Windows 文件名非法字符。
def normalize_map_name(map_name):
    name = str(map_name or "").strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", name)
    return name.strip(" .")


# 获取项目级地图目录。
def get_map_dir(map_name):
    return maps_dir / normalize_map_name(map_name)


# 获取项目级地图图片文件。
def get_map_image_file(map_name):
    return get_map_dir(map_name) / MAP_IMAGE_NAME


# 获取项目级地图元信息文件。
def get_map_metadata_file(map_name):
    return get_map_dir(map_name) / MAP_METADATA_NAME


# 获取项目级巡逻点文件。
def get_global_patrol_points_file(map_name):
    return get_map_dir(map_name) / PATROL_POINTS_FILE_NAME


# 获取账号级地图目录。
def get_account_map_dir(account, map_name):
    return get_account_dir(account) / "maps" / normalize_map_name(map_name)


# 获取账号级巡逻点文件。
def get_account_patrol_points_file(account, map_name):
    return get_account_map_dir(account, map_name) / PATROL_POINTS_FILE_NAME


# 获取地图图片 HTTP 地址。
def make_map_image_url(map_name, image_file):
    version = int(Path(image_file).stat().st_mtime_ns)
    return f"/api/map/image?name={quote(str(map_name), safe='')}&v={version}"


# 获取当前 TXT 配置目录：未绑定账号时使用根目录 txt/。
def get_current_txt_config_dir():
    account = get_current_account()

    if account:
        return get_account_dir(account)

    return txt_dir


# 获取当前怪物关键字清单路径。
def get_monster_keyword_file():
    return get_current_txt_config_dir() / "monster.txt"


# 获取当前怪物名颜色清单路径。
def get_monster_name_color_file():
    return get_current_txt_config_dir() / "monster_name_colors.txt"


# 获取当前物品关键字清单路径。
def get_item_keyword_file():
    return get_current_txt_config_dir() / "item.txt"


# 获取当前物品名颜色清单路径。
def get_item_name_color_file():
    return get_current_txt_config_dir() / "item_name_colors.txt"


# 复制根目录 txt/*.txt 到指定账号目录。
def copy_root_txt_files_to_account(account_dir, overwrite=False):
    account_dir.mkdir(parents=True, exist_ok=True)
    copied = []

    if not txt_dir.exists():
        return copied

    for source_file in sorted(txt_dir.glob("*.txt")):
        target_file = account_dir / source_file.name

        if target_file.exists() and not overwrite:
            continue

        shutil.copy2(source_file, target_file)
        copied.append(str(target_file))

    return copied


# 创建或切换账号，并在首次创建时复制根目录 txt 配置。
def activate_account(account):
    name = normalize_account_name(account)

    if not name:
        return {
            "success": False,
            "account": "",
            "created": False,
            "copied": [],
            "message": "账号名不能为空",
        }

    try:
        with account_lock:
            account_dir = get_account_dir(name)
            created = not account_dir.exists()
            copied = copy_root_txt_files_to_account(account_dir, overwrite=False) if created else []
            output = configure_account_output_dir(name)
            account_state["current"] = name
    except Exception as error:
        return {
            "success": False,
            "account": name,
            "created": False,
            "copied": [],
            "message": f"账号配置切换失败 account={name}: {error}",
        }

    text_config = load_text_configs()
    return {
        "success": True,
        "account": name,
        "created": created,
        "copied": copied,
        "config_dir": str(account_dir),
        "output_dir": str(output),
        "text_config": text_config,
        "message": (
            f"账号配置已切换 account={name} "
            f"created={created} copied={len(copied)} config_dir={account_dir} output_dir={output}；"
            f"{text_config.get('message', '')}"
        ),
    }


# 把根目录 txt/*.txt 覆盖复制到所有已有账号目录。
def overwrite_account_configs():
    accounts = list_accounts()
    copied_count = 0
    errors = []

    for account in accounts:
        try:
            copied_count += len(copy_root_txt_files_to_account(get_account_dir(account), overwrite=True))
        except Exception as error:
            errors.append(f"{account}: {error}")

    text_config = None
    current_account = get_current_account()

    if current_account and current_account in accounts:
        text_config = load_text_configs()

    message = f"复写配置完成 accounts={len(accounts)} files={copied_count}"

    if errors:
        message = f"{message}；失败 {len(errors)} 个: {' | '.join(errors)}"

    if text_config:
        message = f"{message}；当前账号配置已重载；{text_config.get('message', '')}"

    return {
        "success": not errors,
        "accounts": make_accounts_status(),
        "copied_files": copied_count,
        "errors": errors,
        "text_config": text_config or {},
        "message": message,
    }


# 生成账号状态。
def make_accounts_status():
    current = get_current_account()
    return {
        "current": current,
        "items": list_accounts(),
        "config_dir": str(get_current_txt_config_dir()),
        "output_dir": str(get_output_dir()),
    }


# 读取怪物关键字清单：每行一个关键字，空行和 # 注释会跳过。
def load_monster_keywords(force=False):
    with monster_keyword_lock:
        try:
            return load_monster_keywords_locked(force)
        except Exception as error:
            monster_keyword_file = get_monster_keyword_file()
            monster_keyword_state["loaded"] = True
            monster_keyword_state["path"] = str(monster_keyword_file)
            monster_keyword_state["keywords"] = []
            monster_keyword_state["message"] = f"怪物清单加载异常: {error}"
            return get_monster_keyword_status_locked()


# 执行怪物关键字清单加载。
def load_monster_keywords_locked(force=False):
    monster_keyword_file = get_monster_keyword_file()

    if not monster_keyword_file.exists():
        monster_keyword_state["loaded"] = True
        monster_keyword_state["mtime"] = 0
        monster_keyword_state["path"] = str(monster_keyword_file)
        monster_keyword_state["keywords"] = []
        monster_keyword_state["message"] = f"怪物清单不存在 path={monster_keyword_file}"
        return get_monster_keyword_status_locked()

    current_mtime = monster_keyword_file.stat().st_mtime_ns
    current_path = str(monster_keyword_file)

    if (
        not force
        and monster_keyword_state.get("loaded")
        and monster_keyword_state.get("path") == current_path
        and monster_keyword_state.get("mtime") == current_mtime
    ):
        return get_monster_keyword_status_locked()

    text = read_text_file_with_fallback(monster_keyword_file)
    keywords = parse_monster_keywords(text)
    monster_keyword_state["loaded"] = True
    monster_keyword_state["mtime"] = current_mtime
    monster_keyword_state["path"] = current_path
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
    item_filter = load_item_keywords(force=True)
    item_name_colors = load_item_name_colors(force=True)
    return make_text_config_reload_result(
        monster_filter,
        monster_name_colors,
        item_filter,
        item_name_colors,
    )


# 启动时加载 txt 目录下的运行配置。
def load_text_configs():
    monster_filter = load_monster_keywords(force=True)
    monster_name_colors = load_monster_name_colors(force=True)
    item_filter = load_item_keywords(force=True)
    item_name_colors = load_item_name_colors(force=True)
    return make_text_config_reload_result(
        monster_filter,
        monster_name_colors,
        item_filter,
        item_name_colors,
    )


# 组合 txt 配置重载结果。
def make_text_config_reload_result(monster_filter, monster_name_colors, item_filter, item_name_colors):
    message = (
        f"TXT 配置加载完成 "
        f"monsters={monster_filter.get('count', 0)} "
        f"monster_colors={monster_name_colors.get('count', 0)} "
        f"items={item_filter.get('count', 0)} "
        f"item_colors={item_name_colors.get('count', 0)}"
    )
    return {
        "success": True,
        "monster_filter": monster_filter,
        "monster_name_colors": monster_name_colors,
        "item_filter": item_filter,
        "item_name_colors": item_name_colors,
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
        "path": monster_keyword_state.get("path") or str(get_monster_keyword_file()),
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
            monster_name_color_file = get_monster_name_color_file()
            monster_name_color_state["loaded"] = True
            monster_name_color_state["path"] = str(monster_name_color_file)
            monster_name_color_state["colors"] = list(DEFAULT_MONSTER_NAME_OCR_COLORS)
            monster_name_color_state["message"] = f"怪物名颜色加载异常，使用默认颜色: {error}"
            return get_monster_name_color_status_locked()


# 执行怪物名 OCR 颜色清单加载。
def load_monster_name_colors_locked(force=False):
    monster_name_color_file = get_monster_name_color_file()

    if not monster_name_color_file.exists():
        monster_name_color_state["loaded"] = True
        monster_name_color_state["mtime"] = 0
        monster_name_color_state["path"] = str(monster_name_color_file)
        monster_name_color_state["colors"] = list(DEFAULT_MONSTER_NAME_OCR_COLORS)
        monster_name_color_state["message"] = f"怪物名颜色清单不存在，使用默认颜色 path={monster_name_color_file}"
        return get_monster_name_color_status_locked()

    current_mtime = monster_name_color_file.stat().st_mtime_ns
    current_path = str(monster_name_color_file)

    if (
        not force
        and monster_name_color_state.get("loaded")
        and monster_name_color_state.get("path") == current_path
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
    monster_name_color_state["path"] = current_path
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
        "path": monster_name_color_state.get("path") or str(get_monster_name_color_file()),
        "count": len(colors),
        "colors": colors,
        "message": monster_name_color_state.get("message", ""),
    }


# 读取当前怪物名 OCR 颜色列表。
def get_monster_name_ocr_colors():
    return get_monster_name_color_status().get("colors", []) or list(DEFAULT_MONSTER_NAME_OCR_COLORS)


# 读取物品关键字清单：每行一个关键字，空行和 # 注释会跳过。
def load_item_keywords(force=False):
    with item_keyword_lock:
        try:
            return load_item_keywords_locked(force)
        except Exception as error:
            item_keyword_file = get_item_keyword_file()
            item_keyword_state["loaded"] = True
            item_keyword_state["path"] = str(item_keyword_file)
            item_keyword_state["keywords"] = []
            item_keyword_state["entries"] = []
            item_keyword_state["message"] = f"物品清单加载异常: {error}"
            return get_item_keyword_status_locked()


# 执行物品关键字清单加载。
def load_item_keywords_locked(force=False):
    item_keyword_file = get_item_keyword_file()

    if not item_keyword_file.exists():
        item_keyword_state["loaded"] = True
        item_keyword_state["mtime"] = 0
        item_keyword_state["path"] = str(item_keyword_file)
        item_keyword_state["keywords"] = []
        item_keyword_state["entries"] = []
        item_keyword_state["message"] = f"物品清单不存在 path={item_keyword_file}"
        return get_item_keyword_status_locked()

    current_mtime = item_keyword_file.stat().st_mtime_ns
    current_path = str(item_keyword_file)

    if (
        not force
        and item_keyword_state.get("loaded")
        and item_keyword_state.get("path") == current_path
        and item_keyword_state.get("mtime") == current_mtime
    ):
        return get_item_keyword_status_locked()

    text = read_text_file_with_fallback(item_keyword_file)
    entries = parse_item_keywords(text)
    keywords = [entry["keyword"] for entry in entries]
    item_keyword_state["loaded"] = True
    item_keyword_state["mtime"] = current_mtime
    item_keyword_state["path"] = current_path
    item_keyword_state["keywords"] = keywords
    item_keyword_state["entries"] = entries
    item_keyword_state["message"] = f"物品清单加载完成 count={len(keywords)} path={item_keyword_file}"
    return get_item_keyword_status_locked()


# 复制物品关键字清单状态。
def get_item_keyword_status():
    if not item_keyword_state.get("loaded"):
        return load_item_keywords(force=False)

    with item_keyword_lock:
        return get_item_keyword_status_locked()


# 在已持有锁时复制物品关键字清单状态。
def get_item_keyword_status_locked():
    entries = copy_item_keyword_entries(item_keyword_state.get("entries", []))
    keywords = [entry["keyword"] for entry in entries]

    if not entries:
        keywords = list(item_keyword_state.get("keywords", []))
        entries = [{"keyword": keyword, "anchor": keyword} for keyword in keywords]

    return {
        "path": item_keyword_state.get("path") or str(get_item_keyword_file()),
        "count": len(keywords),
        "keywords": keywords,
        "entries": entries,
        "message": item_keyword_state.get("message", ""),
    }


# 读取物品名 OCR 颜色清单。
def load_item_name_colors(force=False):
    with item_name_color_lock:
        try:
            return load_item_name_colors_locked(force)
        except Exception as error:
            item_name_color_file = get_item_name_color_file()
            item_name_color_state["loaded"] = True
            item_name_color_state["path"] = str(item_name_color_file)
            item_name_color_state["colors"] = list(DEFAULT_ITEM_NAME_OCR_COLORS)
            item_name_color_state["message"] = f"物品名颜色加载异常，使用默认颜色: {error}"
            return get_item_name_color_status_locked()


# 执行物品名 OCR 颜色清单加载。
def load_item_name_colors_locked(force=False):
    item_name_color_file = get_item_name_color_file()

    if not item_name_color_file.exists():
        item_name_color_state["loaded"] = True
        item_name_color_state["mtime"] = 0
        item_name_color_state["path"] = str(item_name_color_file)
        item_name_color_state["colors"] = list(DEFAULT_ITEM_NAME_OCR_COLORS)
        item_name_color_state["message"] = f"物品名颜色清单不存在，使用默认颜色 path={item_name_color_file}"
        return get_item_name_color_status_locked()

    current_mtime = item_name_color_file.stat().st_mtime_ns
    current_path = str(item_name_color_file)

    if (
        not force
        and item_name_color_state.get("loaded")
        and item_name_color_state.get("path") == current_path
        and item_name_color_state.get("mtime") == current_mtime
    ):
        return get_item_name_color_status_locked()

    text = read_text_file_with_fallback(item_name_color_file)
    colors = parse_ocr_colors(text)

    if not colors:
        colors = list(DEFAULT_ITEM_NAME_OCR_COLORS)
        message = f"物品名颜色清单为空，使用默认颜色 count={len(colors)} path={item_name_color_file}"
    else:
        message = f"物品名颜色清单加载完成 count={len(colors)} path={item_name_color_file}"

    item_name_color_state["loaded"] = True
    item_name_color_state["mtime"] = current_mtime
    item_name_color_state["path"] = current_path
    item_name_color_state["colors"] = colors
    item_name_color_state["message"] = message
    return get_item_name_color_status_locked()


# 复制物品名 OCR 颜色状态。
def get_item_name_color_status():
    if not item_name_color_state.get("loaded"):
        return load_item_name_colors(force=False)

    with item_name_color_lock:
        return get_item_name_color_status_locked()


# 在已持有锁时复制物品名 OCR 颜色状态。
def get_item_name_color_status_locked():
    colors = list(item_name_color_state.get("colors", []))
    return {
        "path": item_name_color_state.get("path") or str(get_item_name_color_file()),
        "count": len(colors),
        "colors": colors,
        "message": item_name_color_state.get("message", ""),
    }


# 读取当前物品名 OCR 颜色列表。
def get_item_name_ocr_colors():
    return get_item_name_color_status().get("colors", []) or list(DEFAULT_ITEM_NAME_OCR_COLORS)


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


# 解析物品关键字清单：支持“识别词|锚点词”，锚点词只用于估算地面点。
def parse_item_keywords(text):
    entries = []
    index_by_keyword = {}

    for line in str(text or "").splitlines():
        raw_line = line.strip()

        if not raw_line or raw_line.startswith("#"):
            continue

        keyword, anchor = split_item_keyword_line(raw_line)

        if not keyword:
            continue

        entry = {
            "keyword": keyword,
            "anchor": anchor or keyword,
        }

        if keyword in index_by_keyword:
            entries[index_by_keyword[keyword]] = entry
            continue

        index_by_keyword[keyword] = len(entries)
        entries.append(entry)

    return entries


# 拆分物品识别词和可选锚点词。
def split_item_keyword_line(line):
    if "|" not in line:
        keyword = line.strip()
        return keyword, keyword

    keyword, anchor = line.split("|", 1)
    keyword = keyword.strip()
    anchor = anchor.strip() or keyword
    return keyword, anchor


# 复制物品关键字配置，避免外部修改缓存。
def copy_item_keyword_entries(entries):
    result = []

    for entry in entries or []:
        keyword = str(entry.get("keyword", "")).strip()
        anchor = str(entry.get("anchor", "")).strip() or keyword

        if not keyword:
            continue

        result.append({
            "keyword": keyword,
            "anchor": anchor,
        })

    return result


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
    battle_runtime_state=None,
    pet_heal_state=None,
):
    return {
        "player": {
            "map_name": player_info["map_name"],
            "x": player_info["x"],
            "y": player_info["y"],
            "map_raw": get_map_coordinate_raw_text(),
        },
        "player_position": get_bound_player_position(),
        "bound_window": op.get_bound_window(),
        "settings": make_app_settings_status(app_settings),
        "map": make_map_status(current_map),
        "patrol": make_patrol_status(patrol_points, patrol_state, patrol_control),
        "battle": make_battle_status(battle_control, app_settings, battle_runtime_state),
        "accounts": make_accounts_status(),
        "monster_filter": get_monster_keyword_status(),
        "monster_name_colors": get_monster_name_color_status(),
        "state": make_state_status(current_state),
        "auto_heal": make_auto_heal_status(app_settings, auto_heal_state),
        "pet_heal": make_pet_heal_status(app_settings, pet_heal_state),
        "idle_stuck": make_idle_stuck_status(app_settings, idle_stuck_state),
        "getitem": make_getitem_status(app_settings),
    }


# 生成应用设置状态。
def make_app_settings_status(app_settings):
    return {
        "map_corner_hotkey": app_settings.get("map_corner_hotkey", MAP_CORNER_HOTKEY_DEFAULT),
        "map_corner_hotkey_last_message": get_map_corner_hotkey_last_message(),
        "monster_name_debug_enabled": bool(app_settings.get("monster_name_debug_enabled", False)),
    }


# 生成地图状态：复制可序列化字段，避免前端拿到内部可变对象引用。
def make_map_status(current_map):
    if not current_map:
        return {}

    return {
        "name": current_map.get("name", ""),
        "path": current_map.get("path", ""),
        "url": current_map.get("url", ""),
        "rect": dict(current_map.get("rect", {})),
        "max_x": current_map.get("max_x", 0),
        "max_y": current_map.get("max_y", 0),
        "ocr_box": dict(current_map.get("ocr_box", {})),
        "ocr_offset": dict(current_map.get("ocr_offset", {})),
        "ocr_text": current_map.get("ocr_text", ""),
        "source": current_map.get("source", ""),
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
        "source": (patrol_state or {}).get("source", ""),
        "path": (patrol_state or {}).get("path", ""),
    }


# 生成战斗开关状态。
def make_battle_status(battle_control, app_settings=None, battle_runtime_state=None):
    runtime = battle_runtime_state or {}
    limit = get_no_monster_scan_limit(app_settings or {})
    return {
        "enabled": bool((battle_control or {}).get("enabled", False)),
        "no_monster_scan_limit": limit,
        "no_monster_count": normalize_number(runtime.get("no_monster_count"), 0, 0, limit),
        "last_no_monster_reason": runtime.get("last_no_monster_reason", ""),
        "locked_target": make_locked_target_status(runtime.get("last_target", {})),
        "ignored_targets": make_ignored_targets_status(runtime.get("ignored_targets", [])),
        "last_message": runtime.get("last_message", ""),
    }


# 生成锁定目标状态：只暴露页面调试需要的稳定字段。
def make_locked_target_status(target):
    if not target:
        return {}

    last_logic = target.get("last_logic", {})
    origin_logic = target.get("origin_logic", {})
    last_position = target.get("last_position", {})
    return {
        "origin_logic": make_logic_status(origin_logic),
        "last_logic": make_logic_status(last_logic),
        "last_hp_percent": target.get("last_hp_percent", ""),
        "miss_count": int(target.get("miss_count") or 0),
        "last_position": {
            "x": int(last_position.get("x", 0)) if last_position else 0,
            "y": int(last_position.get("y", 0)) if last_position else 0,
        },
        "last_seen_seconds": get_elapsed_seconds(target.get("last_seen_at")),
    }


# 生成忽略目标状态：过滤过期条目，只返回逻辑点和剩余时间。
def make_ignored_targets_status(targets):
    now = time.time()
    items = []

    for target in targets or []:
        expires_at = float(target.get("expires_at") or 0)

        if expires_at <= now:
            continue

        items.append({
            "logic": make_logic_status(target.get("logic", {})),
            "remaining_seconds": max(0, round(expires_at - now, 1)),
            "reason": target.get("reason", ""),
        })

    return items


# 生成逻辑坐标状态。
def make_logic_status(logic):
    if not is_valid_logic(logic):
        return {}

    return {
        "x": int(logic.get("x")),
        "y": int(logic.get("y")),
    }


# 计算距某时间点的秒数，供页面展示。
def get_elapsed_seconds(started_at):
    try:
        started_at = float(started_at)
    except (TypeError, ValueError):
        return ""

    if started_at <= 0:
        return ""

    return round(max(0, time.time() - started_at), 1)


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


# 生成宝宝加血状态。
def make_pet_heal_status(app_settings, pet_heal_state=None):
    state = pet_heal_state or {}
    last_hp_percent = state.get("last_hp_percent", "")

    if last_hp_percent is None:
        last_hp_percent = ""

    return {
        "enabled": bool(app_settings.get("pet_heal_enabled", False)),
        "threshold_percent": normalize_number(
            app_settings.get("pet_heal_threshold_percent"),
            PET_HEAL_DEFAULT_THRESHOLD_PERCENT,
            PET_HEAL_MIN_THRESHOLD_PERCENT,
            PET_HEAL_MAX_THRESHOLD_PERCENT,
        ),
        "key": normalize_pet_heal_key(app_settings.get("pet_heal_key", PET_HEAL_DEFAULT_KEY)),
        "last_hp_percent": last_hp_percent,
        "last_target": dict(state.get("last_target", {})),
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


# 生成捡取物品状态：返回页面展示和轮询同步需要的字段。
def make_getitem_status(app_settings):
    runtime = get_getitem_runtime_status()
    return {
        "enabled": bool(app_settings.get("getitem_enabled", True)),
        "step_wait_ms": get_getitem_step_wait_ms(app_settings),
        "item_filter": get_item_keyword_status(),
        "item_name_colors": get_item_name_color_status(),
        "last_target": runtime.get("last_target", {}),
        "last_message": runtime.get("last_message", ""),
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


# 获取玩家状态里的当前地图名。
def get_player_map_name(player_info=None):
    if not player_info:
        return ""

    return str(player_info.get("map_name", "") or "").strip()


# 获取当前可操作窗口对应的大地图矩形；窗口不可用时回退到元信息里的旧矩形。
def get_runtime_map_rect(metadata=None):
    metadata = metadata or {}

    if op.is_window_bound():
        width, height = get_bound_client_size()

        if width > 0 and height > 0:
            return make_map_rect(*get_map_rect(width, height))

    rect = metadata.get("rect", {})

    if isinstance(rect, dict) and rect:
        return dict(rect)

    return make_map_rect(0, 0, MAP_IMAGE_WIDTH, MAP_IMAGE_HEIGHT)


# 读取已保存地图元信息。
def read_map_metadata(map_name):
    metadata_file = get_map_metadata_file(map_name)

    if not metadata_file.exists():
        raise FileNotFoundError(f"找不到地图元信息: {metadata_file}")

    return json.loads(metadata_file.read_text(encoding="utf-8"))


# 写入已保存地图元信息。
def write_map_metadata(map_name, metadata):
    metadata_file = get_map_metadata_file(map_name)
    metadata_file.parent.mkdir(parents=True, exist_ok=True)
    metadata_file.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# 用已保存图片和元信息生成当前地图状态。
def make_saved_map_status(map_name, metadata=None):
    metadata = metadata or read_map_metadata(map_name)
    image_file = get_map_image_file(map_name)
    max_x, max_y = validate_map_max_coordinate(
        metadata.get("max_x", 0),
        metadata.get("max_y", 0),
    )

    return {
        "name": str(metadata.get("name") or map_name),
        "path": str(image_file),
        "url": make_map_image_url(map_name, image_file),
        "rect": get_runtime_map_rect(metadata),
        "max_x": max_x,
        "max_y": max_y,
        "ocr_box": dict(metadata.get("ocr_box", {})),
        "ocr_offset": dict(metadata.get("ocr_offset", MAP_MAX_COORDINATE_OCR_OFFSET)),
        "ocr_text": metadata.get("ocr_text", ""),
        "source": "saved",
    }


# 加载已手动保存的地图；没有保存过就只返回空地图。
def load_saved_map(map_name):
    name = str(map_name or "").strip()

    if not normalize_map_name(name):
        return {
            "success": False,
            "map": {},
            "message": "地图名为空，跳过加载地图",
        }

    image_file = get_map_image_file(name)
    metadata_file = get_map_metadata_file(name)

    if not image_file.exists() or not metadata_file.exists():
        return {
            "success": False,
            "map": {},
            "message": f"未找到已保存地图 name={name} image={image_file}",
        }

    try:
        metadata = read_map_metadata(name)
        current_map = make_saved_map_status(name, metadata)
    except Exception as error:
        return {
            "success": False,
            "map": {},
            "message": f"加载地图失败 name={name}: {error}",
        }

    return {
        "success": True,
        "map": current_map,
        "message": f"加载地图成功 name={name} path={image_file}",
    }


# 规范化并校验巡逻点。
def normalize_patrol_points(points_data, current_map):
    if not current_map:
        raise ValueError("还没有加载地图")

    max_x, max_y = validate_map_max_coordinate(
        current_map.get("max_x", 0),
        current_map.get("max_y", 0),
    )

    if not isinstance(points_data, list):
        raise ValueError("巡逻点数据格式错误")

    points = []

    for index, point in enumerate(points_data):
        try:
            x = int(point.get("x", 0))
            y = int(point.get("y", 0))
        except (AttributeError, TypeError, ValueError):
            raise ValueError("巡逻点坐标格式错误")

        if x < 0 or x > max_x or y < 0 or y > max_y:
            raise ValueError(f"第 {index + 1} 个巡逻点超出地图范围 point={x}:{y} max={max_x}:{max_y}")

        points.append({"x": x, "y": y})

    return points


# 从文本读取巡逻点，每行格式为 x,y。
def parse_patrol_points_text(text, current_map):
    points = []

    for line_number, raw_line in enumerate(str(text or "").splitlines(), start=1):
        line = raw_line.split("#", 1)[0].strip()

        if not line:
            continue

        parts = [part.strip() for part in line.split(",", 1)]

        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(f"第 {line_number} 行巡逻点格式错误: {raw_line}")

        points.append({"x": int(parts[0]), "y": int(parts[1])})

    return normalize_patrol_points(points, current_map)


# 加载当前地图巡逻点：账号文件优先，否则读取全局文件。
def load_patrol_points_for_map(map_name, current_map):
    name = str(map_name or "").strip()

    if not normalize_map_name(name):
        return {
            "success": True,
            "points": [],
            "source": "",
            "path": "",
            "message": "地图名为空，巡逻点已清空",
        }

    account = get_current_account()
    candidates = []

    if account:
        candidates.append(("account", get_account_patrol_points_file(account, name)))

    candidates.append(("global", get_global_patrol_points_file(name)))

    for source, patrol_file in candidates:
        if not patrol_file.exists():
            continue

        try:
            points = parse_patrol_points_text(patrol_file.read_text(encoding="utf-8"), current_map)
        except Exception as error:
            return {
                "success": False,
                "points": [],
                "source": source,
                "path": str(patrol_file),
                "message": f"读取巡逻点失败 source={source} path={patrol_file}: {error}",
            }

        return {
            "success": True,
            "points": points,
            "source": source,
            "path": str(patrol_file),
            "message": f"读取巡逻点成功 source={source} count={len(points)} path={patrol_file}",
        }

    return {
        "success": True,
        "points": [],
        "source": "",
        "path": "",
        "message": f"当前地图没有巡逻点 name={name}",
    }


# 保存巡逻点到全局或账号目录。
def save_patrol_points_for_map(map_name, current_map, points_data, target):
    name = str(map_name or "").strip()

    if not normalize_map_name(name):
        raise ValueError("地图名为空，不能保存巡逻点")

    points = normalize_patrol_points(points_data, current_map)

    if target == "account":
        account = get_current_account()

        if not account:
            return {
                "success": False,
                "points": [],
                "message": "还没有绑定账号，不能保存账号巡逻点",
            }

        patrol_file = get_account_patrol_points_file(account, name)
        source = "account"
    else:
        patrol_file = get_global_patrol_points_file(name)
        source = "global"

    patrol_file.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(f"{point['x']},{point['y']}" for point in points)

    if text:
        text += "\n"

    patrol_file.write_text(text, encoding="utf-8")
    return {
        "success": True,
        "points": points,
        "source": source,
        "path": str(patrol_file),
        "message": f"保存巡逻点成功 source={source} count={len(points)} path={patrol_file}",
    }


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


# 截取当前大地图：预检查失败时先尝试后台打开地图。
def bind_current_map_with_auto_open(player_info=None):
    precheck = precheck_current_map_ready(player_info)

    if precheck["success"]:
        result = bind_current_map(player_info)
        result["message"] = f"地图预检查通过 max={precheck['max_x']}:{precheck['max_y']}；{result['message']}"
        return hide_current_map_after_bind(result)

    keyboard_result = press_keyboard(
        MAP_AUTO_OPEN_KEY,
        hold_ms=MAP_AUTO_OPEN_HOLD_MS,
        repeat=MAP_AUTO_OPEN_REPEAT,
        interval_ms=MAP_AUTO_OPEN_INTERVAL_MS,
    )
    time.sleep(MAP_AUTO_OPEN_WAIT_SECONDS)
    result = bind_current_map(player_info)
    result["message"] = (
        f"地图预检查失败: {precheck['message']}；"
        f"已尝试后台按 {MAP_AUTO_OPEN_KEY} {MAP_AUTO_OPEN_REPEAT} 次: {keyboard_result['message']}；"
        f"{result['message']}"
    )
    return hide_current_map_after_bind(result)


# 截取成功后隐藏大地图：不影响截取结果，只把隐藏动作写入返回信息。
def hide_current_map_after_bind(result):
    if not result.get("success"):
        return result

    hide_result = press_keyboard(
        MAP_AUTO_HIDE_KEY,
        hold_ms=MAP_AUTO_HIDE_HOLD_MS,
        repeat=MAP_AUTO_HIDE_REPEAT,
        interval_ms=MAP_AUTO_HIDE_INTERVAL_MS,
    )
    result["hide_keyboard"] = hide_result
    result["message"] = f"{result['message']}；截取成功后隐藏地图: {hide_result['message']}"
    return result


# 预检查当前大地图是否已经打开并能读到右下角最大坐标。
def precheck_current_map_ready(player_info=None):
    with coordinate_lock:
        try:
            return precheck_current_map_ready_locked(player_info)
        except Exception as error:
            return {
                "success": False,
                "message": f"地图预检查异常: {error}",
            }


# 执行大地图预检查：只 hover 和 OCR，不保存地图截图。
def precheck_current_map_ready_locked(player_info=None):
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
        }

    time.sleep(MAP_HOVER_WAIT_SECONDS)
    ocr_box = get_map_max_coordinate_ocr_box(map_rect, width, height)
    text = op.ocr_text(
        ocr_box["left"],
        ocr_box["top"],
        ocr_box["right"] - 1,
        ocr_box["bottom"] - 1,
    )
    max_x, max_y = parse_map_max_coordinate_text(text, player_info)

    return {
        "success": True,
        "max_x": max_x,
        "max_y": max_y,
        "rect": map_rect,
        "ocr_box": ocr_box,
        "ocr_text": text,
        "message": (
            f"地图预检查通过 max={max_x}:{max_y} "
            f"ocr_box={ocr_box['left']},{ocr_box['top']},{ocr_box['right']},{ocr_box['bottom']} "
            f"text={text!r} hover={hover_x},{hover_y}"
        ),
    }


# 截取当前大地图：截图保存地图图片，并 OCR 鼠标悬停右下角时的最大逻辑坐标。
def bind_current_map(player_info=None):
    with coordinate_lock:
        try:
            return bind_current_map_locked(player_info)
        except Exception as error:
            return {
                "success": False,
                "message": f"截取地图异常: {error}",
            }


# 执行地图截取：由锁保护截图、鼠标悬停和 OCR 过程。
def bind_current_map_locked(player_info=None):
    if not op.is_window_bound():
        return {
            "success": False,
            "message": "还没有绑定窗口",
        }

    map_name = get_player_map_name(player_info)

    if not normalize_map_name(map_name):
        return {
            "success": False,
            "message": "当前地图名为空，不能截取地图",
            "map": {},
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

    image_file = get_map_image_file(map_name)
    image_file.parent.mkdir(parents=True, exist_ok=True)
    capture_success, capture_message = capture_bound_client_checked(
        left,
        top,
        right - 1,
        bottom - 1,
        image_file,
    )

    if not capture_success:
        return {
            "success": False,
            "message": f"地图截图失败: {capture_message}",
            "map": {},
        }

    ocr_box = get_map_max_coordinate_ocr_box(map_rect, width, height)
    crop_map_max_coordinate_image(map_rect, ocr_box, image_file)
    text = op.ocr_text(
        ocr_box["left"],
        ocr_box["top"],
        ocr_box["right"] - 1,
        ocr_box["bottom"] - 1,
    )
    max_x, max_y = parse_map_max_coordinate_text(text, player_info)
    metadata = {
        "name": map_name,
        "rect": map_rect,
        "max_x": max_x,
        "max_y": max_y,
        "ocr_box": ocr_box,
        "ocr_offset": dict(MAP_MAX_COORDINATE_OCR_OFFSET),
        "ocr_text": text,
        "updated_at": int(time.time()),
    }
    write_map_metadata(map_name, metadata)
    current_map = make_saved_map_status(map_name, metadata)

    return {
        "success": True,
        "map": current_map,
        "message": (
            f"截取地图成功 name={map_name} path={image_file} max={max_x}:{max_y} "
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
def crop_map_max_coordinate_image(map_rect, ocr_box, source_image_file):
    left = ocr_box["left"] - map_rect["left"]
    top = ocr_box["top"] - map_rect["top"]
    right = ocr_box["right"] - map_rect["left"]
    bottom = ocr_box["bottom"] - map_rect["top"]

    map_max_coordinate_image.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(source_image_file) as image:
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


# 游戏客户区屏幕坐标转逻辑坐标：用于拾取物品，不用于大地图。
def screen_to_logic_point(screen_x, screen_y, player_screen_x, player_screen_y, player_logic_x, player_logic_y):
    screen_x = float(screen_x)
    screen_y = float(screen_y)
    player_screen_x = float(player_screen_x)
    player_screen_y = float(player_screen_y)
    player_logic_x = int(float(player_logic_x))
    player_logic_y = int(float(player_logic_y))

    screen_dx = screen_x - player_screen_x
    screen_dy = screen_y - player_screen_y
    determinant = (
        GETITEM_LOGIC_X_SCREEN_DX * GETITEM_LOGIC_Y_SCREEN_DY
        - GETITEM_LOGIC_Y_SCREEN_DX * GETITEM_LOGIC_X_SCREEN_DY
    )
    logic_dx_float = (
        GETITEM_LOGIC_Y_SCREEN_DY * screen_dx
        - GETITEM_LOGIC_Y_SCREEN_DX * screen_dy
    ) / determinant
    logic_dy_float = (
        -GETITEM_LOGIC_X_SCREEN_DY * screen_dx
        + GETITEM_LOGIC_X_SCREEN_DX * screen_dy
    ) / determinant
    logic_dx = round(logic_dx_float)
    logic_dy = round(logic_dy_float)

    return {
        "x": player_logic_x + logic_dx,
        "y": player_logic_y + logic_dy,
        "logic_dx": logic_dx,
        "logic_dy": logic_dy,
        "logic_dx_float": logic_dx_float,
        "logic_dy_float": logic_dy_float,
        "screen_dx": screen_dx,
        "screen_dy": screen_dy,
        "screen": {
            "x": round(screen_x),
            "y": round(screen_y),
        },
        "player": {
            "screen_x": round(player_screen_x),
            "screen_y": round(player_screen_y),
            "logic_x": player_logic_x,
            "logic_y": player_logic_y,
        },
    }


# 逻辑坐标转游戏客户区屏幕坐标：用于拾取物品，不用于大地图。
def logic_to_screen_point(logic_x, logic_y, player_logic_x, player_logic_y, player_screen_x, player_screen_y):
    logic_x = int(float(logic_x))
    logic_y = int(float(logic_y))
    player_logic_x = int(float(player_logic_x))
    player_logic_y = int(float(player_logic_y))
    player_screen_x = float(player_screen_x)
    player_screen_y = float(player_screen_y)
    logic_dx = logic_x - player_logic_x
    logic_dy = logic_y - player_logic_y
    screen_dx = (
        logic_dx * GETITEM_LOGIC_X_SCREEN_DX
        + logic_dy * GETITEM_LOGIC_Y_SCREEN_DX
    )
    screen_dy = (
        logic_dx * GETITEM_LOGIC_X_SCREEN_DY
        + logic_dy * GETITEM_LOGIC_Y_SCREEN_DY
    )
    screen_x = player_screen_x + screen_dx
    screen_y = player_screen_y + screen_dy

    return {
        "x": round(screen_x),
        "y": round(screen_y),
        "logic_dx": logic_dx,
        "logic_dy": logic_dy,
        "screen_dx": screen_dx,
        "screen_dy": screen_dy,
        "logic": {
            "x": logic_x,
            "y": logic_y,
        },
        "player": {
            "screen_x": round(player_screen_x),
            "screen_y": round(player_screen_y),
            "logic_x": player_logic_x,
            "logic_y": player_logic_y,
        },
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
        raise ValueError("还没有加载地图")

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
def attack_monster(monster, save_name_debug=False):
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

    filter_result = verify_monster_name_before_attack(
        monster,
        x,
        y,
        width,
        height,
        save_name_debug=save_name_debug,
    )

    if not filter_result["allowed"]:
        filter_reason = filter_result.get("reason", "monster_filter_failed")
        reason = (
            "monster_filter_mismatch"
            if filter_reason in {"keyword_not_found", "full_name_not_found", "player_summon"}
            else filter_reason
        )

        return {
            "success": False,
            "reason": reason,
            "filter_reason": filter_reason,
            "x": x,
            "y": y,
            "filter": filter_result,
            "name_message": filter_result.get("name_message", ""),
            "name_messages": filter_result.get("name_messages", []),
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
        "name_message": filter_result.get("name_message", ""),
        "name_messages": filter_result.get("name_messages", []),
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


# 攻击前校验怪物名：只有完整等于 txt/monster.txt 中的一行才允许点击。
def verify_monster_name_before_attack(monster, x, y, width, height, save_name_debug=False):
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

    name_result = recognize_monster_name(x, y, blood_bar, save_debug=save_name_debug)
    move_success = name_result.get("move_success", True)
    move_message = name_result.get("move_message", "")
    name_message = name_result.get("message", "")
    name_messages = list(name_result.get("ocr_logs", []))

    if name_message:
        name_messages.append(name_message)

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
            "name_message": name_message,
            "name_messages": name_messages,
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
            "name_message": name_message,
            "name_messages": name_messages,
        }

    names = get_monster_full_name_candidates(name_result)

    if is_current_account_summon_name(name_result):
        return {
            "allowed": False,
            "reason": "player_summon",
            "keywords": keywords,
            "matched_keyword": "",
            "text": " ".join(names),
            "names": names,
            "box": name_result.get("ocr_box", {}),
            "blood_bar": name_result.get("blood_bar", {}),
            "position": name_result.get("position", {"x": x, "y": y}),
            "move_success": move_success,
            "move_message": move_message,
            "name_result": name_result,
            "name_message": name_message,
            "name_messages": name_messages,
        }

    matched_keyword = get_matched_monster_full_name(name_result, keywords)
    text = " ".join(names)

    return {
        "allowed": bool(matched_keyword),
        "reason": "" if matched_keyword else "full_name_not_found",
        "keywords": keywords,
        "matched_keyword": matched_keyword,
        "text": text,
        "names": names,
        "box": name_result.get("ocr_box", {}),
        "blood_bar": name_result.get("blood_bar", {}),
        "position": name_result.get("position", {"x": x, "y": y}),
        "move_success": move_success,
        "move_message": move_message,
        "name_result": name_result,
        "name_message": name_message,
        "name_messages": name_messages,
    }


# 捡取安全校验怪物名：必须完整等于 txt/monster.txt 中的一行，避免宝宝名被短关键字误伤。
def verify_monster_full_name_for_getitem_safety(monster, x, y, width, height, save_name_debug=False):
    keyword_status = load_monster_keywords(force=False)
    keywords = keyword_status.get("keywords", [])

    if not keywords:
        return {
            "allowed": False,
            "reason": "empty_keyword_list",
            "keywords": keywords,
            "text": "",
            "names": [],
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
            "names": [],
            "matched_keyword": "",
            "box": {},
            "position": {"x": x, "y": y},
            "message": "怪物缺少血条坐标，无法做名字过滤",
        }

    name_result = recognize_monster_name(x, y, blood_bar, save_debug=save_name_debug)
    move_success = name_result.get("move_success", True)
    move_message = name_result.get("move_message", "")
    name_message = name_result.get("message", "")
    name_messages = list(name_result.get("ocr_logs", []))
    names = get_monster_full_name_candidates(name_result)

    if name_message:
        name_messages.append(name_message)

    if not move_success:
        return {
            "allowed": False,
            "reason": "hover_failed",
            "keywords": keywords,
            "matched_keyword": "",
            "text": " ".join(names),
            "names": names,
            "box": name_result.get("ocr_box", {}),
            "blood_bar": name_result.get("blood_bar", {}),
            "position": name_result.get("position", {"x": x, "y": y}),
            "move_success": move_success,
            "move_message": move_message,
            "name_result": name_result,
            "name_message": name_message,
            "name_messages": name_messages,
        }

    if not name_result.get("success", False):
        return {
            "allowed": False,
            "reason": "monster_name_failed",
            "keywords": keywords,
            "matched_keyword": "",
            "text": " ".join(names),
            "names": names,
            "box": name_result.get("ocr_box", {}),
            "blood_bar": name_result.get("blood_bar", {}),
            "position": name_result.get("position", {"x": x, "y": y}),
            "move_success": move_success,
            "move_message": move_message,
            "name_result": name_result,
            "name_message": name_message,
            "name_messages": name_messages,
        }

    matched_keyword = get_matched_monster_full_name(name_result, keywords)

    return {
        "allowed": bool(matched_keyword),
        "reason": "" if matched_keyword else "full_name_not_found",
        "keywords": keywords,
        "matched_keyword": matched_keyword,
        "text": " ".join(names),
        "names": names,
        "box": name_result.get("ocr_box", {}),
        "blood_bar": name_result.get("blood_bar", {}),
        "position": name_result.get("position", {"x": x, "y": y}),
        "move_success": move_success,
        "move_message": move_message,
        "name_result": name_result,
        "name_message": name_message,
        "name_messages": name_messages,
    }


# 从统一怪物名识别结果里读取完整怪名候选。
def get_monster_full_name_candidates(name_result):
    names = []

    for key in ("name", "name_text", "raw_text", "mask_text"):
        name = str(name_result.get(key, "") or "").strip()

        if not name or name == "未识别" or name in names:
            continue

        names.append(name)

    return names


# 捡取安全用完整怪名匹配：忽略 OCR 空白，但不做包含匹配。
def get_matched_monster_full_name(name_result, keywords):
    keyword_map = {}

    for keyword in keywords:
        normalized = normalize_monster_full_name(keyword)

        if normalized and normalized not in keyword_map:
            keyword_map[normalized] = keyword

    for name in get_monster_full_name_candidates(name_result):
        normalized = normalize_monster_full_name(name)

        if normalized in keyword_map:
            return keyword_map[normalized]

    return ""


# 判断怪名是否像当前账号的召唤物，例如 变异骷髅(妖孽)。
def is_current_account_summon_name(name_result):
    account = normalize_monster_full_name(get_current_account())

    if not account:
        return False

    suffixes = [
        f"({account})",
        f"（{account}）",
    ]

    for name in get_monster_full_name_candidates(name_result):
        normalized = normalize_monster_full_name(name)

        if any(suffix in normalized for suffix in suffixes):
            return True

    return False


# 规范化完整怪名：只去掉空白，保留括号和其他字符，避免短词误匹配。
def normalize_monster_full_name(name):
    return re.sub(r"\s+", "", str(name or "").strip())


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


# 判断是否应该从 idle 进入捡取状态。
def should_enter_getitem(game_data):
    settings = game_data.get("settings", {})

    if not settings.get("getitem_enabled", True):
        return {
            "enter": False,
            "message": "",
        }

    if not (
        game_data.get("battle_control", {}).get("enabled", False)
        or game_data.get("patrol_control", {}).get("enabled", False)
    ):
        return {
            "enter": False,
            "message": "",
        }

    safety = check_getitem_safety()

    if not safety.get("success", False):
        message = f"捡取安全检测失败: {safety.get('message', '')}"
        set_getitem_runtime_status(message=message, target={})
        return {
            "enter": False,
            "message": "",
        }

    if not safety.get("safe", True):
        message = safety.get("message", "附近有清单内怪物，跳过捡取")
        set_getitem_runtime_status(message=message, target=safety.get("danger", {}))
        return {
            "enter": False,
            "message": "",
        }

    scan = scan_getitems(game_data.get("player"))

    if not scan.get("success", False):
        message = f"捡取物品扫描失败: {scan.get('message', '')}"
        set_getitem_runtime_status(message=message, target={})
        return {
            "enter": False,
            "message": "",
        }

    items = scan.get("items", [])

    if not items:
        set_getitem_runtime_status(message="可玩区域没有可捡物品", target={})
        return {
            "enter": False,
            "message": "",
        }

    target = choose_getitem_target(items)
    message = f"发现可捡物品 count={len(items)} target={format_getitem_target(target)}"
    set_getitem_runtime_status(message=message, target=target)
    return {
        "enter": True,
        "target": target,
        "message": message,
    }


# 捡取前安全检测：只把命中怪物清单的怪物当作危险。
def check_getitem_safety():
    context = get_getitem_safety_context()

    if not context.get("success", False):
        return {
            "success": False,
            "safe": False,
            "message": context.get("message", ""),
        }

    monster_result = scan_monsters()

    if not monster_result.get("success", False):
        return {
            "success": False,
            "safe": False,
            "message": monster_result.get("message", ""),
        }

    box = context["box"]
    client = context["client"]
    width, height = client["width"], client["height"]
    candidates = []

    for monster in monster_result.get("monsters", []):
        position = monster.get("position", {})

        if is_point_in_box(position.get("x"), position.get("y"), box):
            candidates.append(monster)

    logs = []

    for monster in candidates:
        position = monster.get("position", {})
        filter_result = verify_monster_full_name_for_getitem_safety(
            monster,
            position.get("x", 0),
            position.get("y", 0),
            width,
            height,
            save_name_debug=False,
        )
        logs.extend(filter_result.get("name_messages", []))

        if filter_result.get("allowed", False):
            danger = {
                "keyword": filter_result.get("matched_keyword", ""),
                "text": filter_result.get("text", ""),
                "position": filter_result.get("position", position),
                "monster": {
                    "id": monster.get("id", 0),
                    "distance": monster.get("distance", ""),
                    "hp_percent": monster.get("hp_percent", ""),
                },
            }
            return {
                "success": True,
                "safe": False,
                "danger": danger,
                "logs": logs,
                "message": (
                    f"附近有清单内怪物，暂停捡取 "
                    f"matched={danger['keyword']} text={danger['text']!r}"
                ),
            }

    return {
        "success": True,
        "safe": True,
        "candidate_count": len(candidates),
        "logs": logs,
        "message": f"捡取安全检测通过 candidates={len(candidates)}",
    }


# 扫描可拾取物品。
def scan_getitems(player_info=None):
    with monster_scan_lock:
        try:
            return scan_getitems_locked(player_info)
        except Exception as error:
            return {
                "success": False,
                "items": [],
                "message": f"捡取物品扫描异常: {error}",
            }


# 执行物品扫描：由锁保护 OP 找字流程。
def scan_getitems_locked(player_info=None):
    context = get_getitem_item_scan_context()

    if not context.get("success", False):
        return {
            "success": False,
            "items": [],
            "message": context.get("message", ""),
        }

    keyword_status = load_item_keywords(force=False)
    item_entries = keyword_status.get("entries", [])
    keywords = [entry["keyword"] for entry in item_entries]

    if not keywords:
        return {
            "success": True,
            "items": [],
            "count": 0,
            "search_box": context["box"],
            "player": context["player"],
            "message": keyword_status.get("message", "物品清单为空"),
        }

    colors = get_item_name_ocr_colors()
    box = context["box"]
    client = context["client"]
    width, height = client["width"], client["height"]
    player_x, player_y = context["player"]["x"], context["player"]["y"]
    find_text = "|".join(keywords)
    items = []

    for color in colors:
        matches = op.find_text(
            box["left"],
            box["top"],
            box["right"] - 1,
            box["bottom"] - 1,
            find_text,
            color=color,
            sim=ITEM_NAME_OCR_SIM,
        )

        for match in matches:
            item = make_getitem_from_match(
                match,
                item_entries,
                color,
                width,
                height,
                player_x,
                player_y,
                player_info,
            )
            add_unique_getitem(items, item)

    items.sort(key=lambda item: (item["distance"], item["keyword_index"], item["click"]["y"], item["click"]["x"]))
    return {
        "success": True,
        "items": items,
        "count": len(items),
        "search_box": context["box"],
        "player": context["player"],
        "colors": colors,
        "message": f"捡取物品扫描完成 count={len(items)} player={player_x},{player_y} box={format_box(box)}",
    }


# 获取捡取基础上下文：玩家脚底和窗口尺寸。
def get_getitem_base_context():
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

    try:
        player_x, player_y, position = get_bound_player_foot_point()
    except ValueError as error:
        return {
            "success": False,
            "client": client,
            "message": str(error),
        }

    return {
        "success": True,
        "client": client,
        "player": {
            "x": player_x,
            "y": player_y,
            "position": position,
        },
        "message": f"捡取基础上下文 player={player_x},{player_y} client={width}x{height}",
    }


# 获取捡取安全检测上下文：玩家脚底为中心 350x250。
def get_getitem_safety_context():
    context = get_getitem_base_context()

    if not context.get("success", False):
        return context

    client = context["client"]
    width, height = client["width"], client["height"]
    player_x, player_y = context["player"]["x"], context["player"]["y"]
    play_area_bottom = max(1, height - BOTTOM_UI_HEIGHT)
    box = clamp_box(
        player_x - GETITEM_SEARCH_WIDTH / 2,
        player_y - GETITEM_SEARCH_HEIGHT / 2,
        player_x + GETITEM_SEARCH_WIDTH / 2,
        player_y + GETITEM_SEARCH_HEIGHT / 2,
        width,
        play_area_bottom,
    )
    context["box"] = box
    context["message"] = f"捡取安全区域 player={player_x},{player_y} box={format_box(box)}"
    return context


# 获取物品扫描上下文：整个可玩区域，排除底部 UI。
def get_getitem_item_scan_context():
    context = get_getitem_base_context()

    if not context.get("success", False):
        return context

    client = context["client"]
    width, height = client["width"], client["height"]
    play_area_bottom = max(1, height - BOTTOM_UI_HEIGHT)
    box = clamp_box(0, 0, width, play_area_bottom, width, play_area_bottom)
    context["box"] = box
    context["message"] = f"捡取物品扫描区域 box={format_box(box)}"
    return context


# 从 OP 找字结果生成物品目标。
def make_getitem_from_match(match, item_entries, color, width, height, player_x, player_y, player_info=None):
    keyword_index = int(match.get("index", -1))
    config = item_entries[keyword_index] if 0 <= keyword_index < len(item_entries) else {}
    keyword = str(config.get("keyword") or match.get("text", ""))
    anchor = str(config.get("anchor") or keyword)
    x = int(match.get("x", 0))
    y = int(match.get("y", 0))
    text_box = make_item_text_box(x, y, keyword, width, height)
    anchor_box = make_item_anchor_box(x, y, keyword, anchor, width, height)
    click_x = clamp_number(round((anchor_box["left"] + anchor_box["right"]) / 2), 0, width - 1)
    click_y = clamp_number(text_box["top"] + ITEM_CLICK_OFFSET_Y, 0, height - 1)
    distance = round(math.dist((player_x, player_y), (click_x, click_y)))
    logic = estimate_getitem_logic_target(click_x, click_y, player_x, player_y, player_info)
    return {
        "keyword": keyword,
        "anchor": anchor,
        "keyword_index": keyword_index,
        "x": x,
        "y": y,
        "text_box": text_box,
        "anchor_box": anchor_box,
        "click": {
            "x": click_x,
            "y": click_y,
        },
        "logic": logic,
        "distance": distance,
        "color": color,
    }


# 根据 OP 找字左上角估算物品文字框。
def make_item_text_box(x, y, text, width, height):
    text_width = max(ITEM_NAME_TEXT_WIDTH, estimate_text_width(text))
    return clamp_box(
        int(x),
        int(y),
        int(x) + text_width,
        int(y) + ITEM_NAME_TEXT_HEIGHT,
        width,
        height,
    )


# 根据配置锚点估算物品文字里的有效水平中心。
def make_item_anchor_box(x, y, keyword, anchor, width, height):
    keyword = str(keyword or "")
    anchor = str(anchor or keyword)
    anchor_index = keyword.find(anchor)

    if anchor_index < 0:
        anchor = keyword
        anchor_index = 0

    prefix = keyword[:anchor_index]
    anchor_left = int(x) + estimate_text_width(prefix)
    anchor_width = max(ITEM_NAME_TEXT_WIDTH, estimate_text_width(anchor))
    return clamp_box(
        anchor_left,
        int(y),
        anchor_left + anchor_width,
        int(y) + ITEM_NAME_TEXT_HEIGHT,
        width,
        height,
    )


# 估算 OP 字库文字宽度：中文/全角 12px，ASCII/半角符号 6px。
def estimate_text_width(text):
    width = 0

    for char in str(text or ""):
        if ord(char) < 128:
            width += ITEM_NAME_TEXT_ASCII_WIDTH
        elif unicodedata.east_asian_width(char) in {"F", "W"}:
            width += ITEM_NAME_TEXT_WIDTH
        else:
            width += ITEM_NAME_TEXT_ASCII_WIDTH

    return width


# 用当前玩家逻辑坐标估算物品所在格子。
def estimate_getitem_logic_target(click_x, click_y, player_x, player_y, player_info=None):
    player_logic_x, player_logic_y = get_player_logic_coordinate(player_info)

    if player_logic_x is None or player_logic_y is None:
        return {}

    return screen_to_logic_point(
        click_x,
        click_y,
        player_x,
        player_y,
        player_logic_x,
        player_logic_y,
    )


# 加入去重后的物品命中：多颜色可能识别到同一段文字。
def add_unique_getitem(items, item):
    for old_item in items:
        if old_item["keyword"] != item["keyword"]:
            continue

        if abs(old_item["x"] - item["x"]) <= 4 and abs(old_item["y"] - item["y"]) <= 4:
            return

    items.append(item)


# 选择本轮要捡的物品：列表已经按距离和清单顺序排序。
def choose_getitem_target(items):
    return items[0] if items else None


# 从扫描结果里找同名物品：到达目标格后用于判断是否仍可见。
def find_same_keyword_getitem_target(items, target):
    if not target:
        return None

    keyword = str(target.get("keyword", ""))
    candidates = [item for item in items if item.get("keyword") == keyword]
    return choose_getitem_target(candidates)


# 从重新扫描结果里找回当前目标。
def find_matching_getitem_target(items, target):
    if not target:
        return None

    keyword = str(target.get("keyword", ""))
    candidates = [item for item in items if item.get("keyword") == keyword]

    if not candidates:
        return None

    click = target.get("click", {})

    try:
        target_x = int(click.get("x"))
        target_y = int(click.get("y"))
    except (TypeError, ValueError):
        return candidates[0]

    nearest = min(
        candidates,
        key=lambda item: math.dist((item["click"]["x"], item["click"]["y"]), (target_x, target_y)),
    )
    distance = math.dist((nearest["click"]["x"], nearest["click"]["y"]), (target_x, target_y))

    if distance > GETITEM_TARGET_MATCH_RADIUS:
        return None

    return nearest


# 判断物品目标是否已有逻辑坐标。
def has_getitem_target_logic(target):
    logic = (target or {}).get("logic", {})
    return parse_optional_int(logic.get("x")) is not None and parse_optional_int(logic.get("y")) is not None


# 判断玩家是否已走到当前物品目标逻辑坐标。
def is_getitem_target_reached(target, player_info):
    logic = (target or {}).get("logic", {})
    target_x = parse_optional_int(logic.get("x"))
    target_y = parse_optional_int(logic.get("y"))
    player_x, player_y = get_player_logic_coordinate(player_info)

    if target_x is None or target_y is None or player_x is None or player_y is None:
        return False

    return max(abs(target_x - player_x), abs(target_y - player_y)) <= GETITEM_TARGET_ARRIVAL_RADIUS


# 朝物品目标方向走一步：不直接点击物品，避免宝宝挡住物品点。
def move_getitem_toward_target(target, previous_direction="", player_info=None):
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

    try:
        player_x, player_y, player_position = get_bound_player_foot_point()
    except ValueError as error:
        return {
            "success": False,
            "message": str(error),
        }

    target_point = get_getitem_move_screen_point(target, player_info, player_x, player_y)

    if not target_point:
        return {
            "success": False,
            "message": f"物品坐标异常 target={target}",
        }

    item_x = int(target_point["x"])
    item_y = int(target_point["y"])
    direction, direction_message = get_direction_to_target(
        player_x,
        player_y,
        item_x,
        item_y,
        previous_direction,
    )
    action, logic_distance = get_getitem_move_action(target, player_info)
    move = calculate_move(action, direction, width, height, player_x, player_y)
    success, message = op.click_mouse_at(move["click_x"], move["click_y"], move["button"])
    message = (
        f"{message} action={action} logic_distance={logic_distance} "
        f"direction={direction} player={player_x},{player_y} item={item_x},{item_y} "
        f"move_click={move['click_x']},{move['click_y']} target_source={target_point['source']} "
        f"{direction_message}"
    )
    return {
        "success": success,
        "action": action,
        "logic_distance": logic_distance,
        "direction": direction,
        "player": {
            "x": player_x,
            "y": player_y,
            "position": player_position,
        },
        "item": {
            "x": item_x,
            "y": item_y,
        },
        "target_source": target_point["source"],
        "target_logic": dict(target.get("logic", {})),
        "move": move,
        "message": message,
    }


# 获取捡取移动动作：目标超过 2 格跑步，2 格以内走路。
def get_getitem_move_action(target, player_info):
    logic = (target or {}).get("logic", {})
    target_x = parse_optional_int(logic.get("x"))
    target_y = parse_optional_int(logic.get("y"))
    player_x, player_y = get_player_logic_coordinate(player_info)

    if target_x is None or target_y is None or player_x is None or player_y is None:
        return "walk", ""

    distance = max(abs(target_x - player_x), abs(target_y - player_y))

    if distance <= GETITEM_WALK_MAX_LOGIC_DISTANCE:
        return "walk", distance

    return "run", distance


# 获取物品移动用的当前屏幕目标点：优先用逻辑坐标重新投影，兜底用识别时点击点。
def get_getitem_move_screen_point(target, player_info, player_screen_x, player_screen_y):
    logic = (target or {}).get("logic", {})
    target_logic_x = parse_optional_int(logic.get("x"))
    target_logic_y = parse_optional_int(logic.get("y"))
    player_logic_x, player_logic_y = get_player_logic_coordinate(player_info)

    if (
        target_logic_x is not None
        and target_logic_y is not None
        and player_logic_x is not None
        and player_logic_y is not None
    ):
        point = logic_to_screen_point(
            target_logic_x,
            target_logic_y,
            player_logic_x,
            player_logic_y,
            player_screen_x,
            player_screen_y,
        )
        return {
            "x": point["x"],
            "y": point["y"],
            "source": "logic",
            "point": point,
        }

    click = (target or {}).get("click", {})

    try:
        return {
            "x": int(click.get("x")),
            "y": int(click.get("y")),
            "source": "screen",
        }
    except (TypeError, ValueError):
        return None


# 根据玩家脚点和物品点计算八方向。
def get_direction_to_target(player_x, player_y, item_x, item_y, previous_direction=""):
    dx = int(item_x) - int(player_x)
    dy = int(item_y) - int(player_y)

    if dx == 0 and dy == 0:
        if previous_direction in directions:
            return previous_direction, "target_overlap=1 use_previous_direction=1"

        return "down", "target_overlap=1 fallback_direction=down"

    ordered_directions = [
        "right",
        "down_right",
        "down",
        "down_left",
        "left",
        "up_left",
        "up",
        "up_right",
    ]
    angle = math.degrees(math.atan2(dy, dx))
    index = int(round(angle / 45.0)) % len(ordered_directions)
    return ordered_directions[index], f"vector={dx},{dy} angle={round(angle, 2)}"


# 格式化物品目标，供日志阅读。
def format_getitem_target(target):
    if not target:
        return "-"

    click = target.get("click", {})
    logic = target.get("logic", {})
    logic_text = ""

    if logic:
        logic_text = f" logic={logic.get('x', '')}:{logic.get('y', '')}"

    return (
        f"{target.get('keyword', '')}"
        f"@{click.get('x', '')},{click.get('y', '')}"
        f"{logic_text}"
        f" distance={target.get('distance', '')}"
    )


# 判断点是否在开区间矩形内。
def is_point_in_box(x, y, box):
    try:
        x = int(x)
        y = int(y)
    except (TypeError, ValueError):
        return False

    return box["left"] <= x < box["right"] and box["top"] <= y < box["bottom"]


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


# 更新怪物名 Debug 图保存开关。
def update_monster_name_debug_settings(app_settings, data):
    data = data if isinstance(data, dict) else {}
    enabled = normalize_bool(data.get("enabled", app_settings.get("monster_name_debug_enabled", False)))

    app_settings["monster_name_debug_enabled"] = enabled
    state_text = "开" if enabled else "关"
    message = f"怪物名Debug图保存已{state_text}"

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


# 更新宝宝加血设置：保存开关、触发血量和加血按键。
def update_pet_heal_settings(app_settings, pet_heal_state, data):
    data = data if isinstance(data, dict) else {}
    enabled = normalize_bool(data.get("enabled", app_settings.get("pet_heal_enabled", False)))
    threshold_percent = normalize_number(
        data.get("threshold_percent"),
        PET_HEAL_DEFAULT_THRESHOLD_PERCENT,
        PET_HEAL_MIN_THRESHOLD_PERCENT,
        PET_HEAL_MAX_THRESHOLD_PERCENT,
    )
    key = normalize_pet_heal_key(data.get("key", app_settings.get("pet_heal_key", PET_HEAL_DEFAULT_KEY)))

    app_settings["pet_heal_enabled"] = enabled
    app_settings["pet_heal_threshold_percent"] = threshold_percent
    app_settings["pet_heal_key"] = key

    state_text = "开" if enabled else "关"
    message = f"宝宝加血设置已更新: {state_text} threshold={threshold_percent}% key={key}"

    if pet_heal_state is not None:
        pet_heal_state["last_message"] = message

    return {
        "success": True,
        "message": message,
        "pet_heal": make_pet_heal_status(app_settings, pet_heal_state),
    }


# 规整宝宝加血按键：无效按键回退到默认值。
def normalize_pet_heal_key(key):
    text = str(key or "").strip().upper()

    if not text:
        text = PET_HEAL_DEFAULT_KEY

    try:
        key_name, _ = resolve_keyboard_key(text)
        return key_name
    except ValueError:
        return PET_HEAL_DEFAULT_KEY


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


# 更新战斗设置：当前只保存连续无怪跳点次数。
def update_battle_settings(app_settings, battle_runtime_state, data):
    data = data if isinstance(data, dict) else {}
    limit = normalize_number(
        data.get("no_monster_scan_limit"),
        NO_MONSTER_SCAN_LIMIT_DEFAULT,
        NO_MONSTER_SCAN_LIMIT_MIN,
        NO_MONSTER_SCAN_LIMIT_MAX,
    )

    app_settings["no_monster_scan_limit"] = limit
    message = f"战斗设置已更新: no_monster_scan_limit={limit}"

    if battle_runtime_state is not None:
        clamp_no_monster_count(battle_runtime_state, limit)
        battle_runtime_state["last_message"] = message

    return {
        "success": True,
        "message": message,
        "battle": make_battle_status({}, app_settings, battle_runtime_state),
    }


# 读取连续无怪跳点次数。
def get_no_monster_scan_limit(app_settings):
    return normalize_number(
        app_settings.get("no_monster_scan_limit"),
        NO_MONSTER_SCAN_LIMIT_DEFAULT,
        NO_MONSTER_SCAN_LIMIT_MIN,
        NO_MONSTER_SCAN_LIMIT_MAX,
    )


# 更新捡取物品设置：保存页面开关和每步等待间隔。
def update_getitem_settings(app_settings, data):
    data = data if isinstance(data, dict) else {}
    enabled = normalize_bool(data.get("enabled", app_settings.get("getitem_enabled", True)))
    step_wait_ms = normalize_number(
        data.get("step_wait_ms"),
        GETITEM_DEFAULT_STEP_WAIT_MS,
        GETITEM_MIN_STEP_WAIT_MS,
        GETITEM_MAX_STEP_WAIT_MS,
    )

    app_settings["getitem_enabled"] = enabled
    app_settings["getitem_step_wait_ms"] = step_wait_ms

    state_text = "开" if enabled else "关"
    message = f"捡取物品设置已更新: {state_text} step_wait_ms={step_wait_ms}"
    set_getitem_runtime_status(message=message)
    return {
        "success": True,
        "message": message,
        "getitem": make_getitem_status(app_settings),
    }


# 读取捡取点击后的等待间隔。
def get_getitem_step_wait_ms(app_settings):
    return normalize_number(
        app_settings.get("getitem_step_wait_ms"),
        GETITEM_DEFAULT_STEP_WAIT_MS,
        GETITEM_MIN_STEP_WAIT_MS,
        GETITEM_MAX_STEP_WAIT_MS,
    )


# 更新捡取物品运行状态。
def set_getitem_runtime_status(message="", target=None):
    with getitem_runtime_lock:
        if target is not None:
            getitem_runtime_state["last_target"] = make_getitem_target_status(target)

        if message:
            getitem_runtime_state["last_message"] = message

        return get_getitem_runtime_status_locked()


# 复制捡取物品运行状态。
def get_getitem_runtime_status():
    with getitem_runtime_lock:
        return get_getitem_runtime_status_locked()


# 在已持有锁时复制捡取物品运行状态。
def get_getitem_runtime_status_locked():
    return {
        "last_target": dict(getitem_runtime_state.get("last_target", {})),
        "last_message": getitem_runtime_state.get("last_message", ""),
    }


# 生成捡取目标状态。
def make_getitem_target_status(target):
    if not target:
        return {}

    click = target.get("click", {})
    position = target.get("position", {})
    text_box = target.get("text_box", {})
    anchor_box = target.get("anchor_box", {})
    logic = target.get("logic", {})
    move = target.get("move", {})
    move_click = move.get("click", {})
    move_player = move.get("player", {})
    move_item = move.get("item", {})
    return {
        "keyword": str(target.get("keyword", "")),
        "anchor": str(target.get("anchor", target.get("keyword", ""))),
        "keyword_index": int(target.get("keyword_index", -1)),
        "click_x": int(click.get("x", position.get("x", 0))),
        "click_y": int(click.get("y", position.get("y", 0))),
        "text_x": int(text_box.get("left", target.get("x", 0))),
        "text_y": int(text_box.get("top", target.get("y", 0))),
        "anchor_x": int(anchor_box.get("left", click.get("x", 0))),
        "anchor_y": int(anchor_box.get("top", click.get("y", 0))),
        "logic_x": int(logic.get("x", 0)) if logic else 0,
        "logic_y": int(logic.get("y", 0)) if logic else 0,
        "distance": int(target.get("distance", 0)),
        "action": str(move.get("action", "")),
        "logic_distance": move.get("logic_distance", ""),
        "direction": str(move.get("direction", "")),
        "move_click_x": int(move_click.get("x", 0)),
        "move_click_y": int(move_click.get("y", 0)),
        "player_x": int(move_player.get("x", 0)),
        "player_y": int(move_player.get("y", 0)),
        "item_x": int(move_item.get("x", click.get("x", 0))),
        "item_y": int(move_item.get("y", click.get("y", 0))),
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


# 找怪时识别到宝宝后，按血量阈值尝试给宝宝加血。
def maybe_heal_pet(monster, filter_result, app_settings, pet_heal_state):
    if not app_settings.get("pet_heal_enabled", False):
        return {
            "success": True,
            "healed": False,
            "message": "",
        }

    if pet_heal_state is None:
        pet_heal_state = {}

    hp_percent = get_monster_hp_percent(monster)
    pet_heal_state["last_hp_percent"] = hp_percent
    pet_heal_state["last_target"] = make_pet_heal_target_status(monster, filter_result)
    threshold_percent = normalize_number(
        app_settings.get("pet_heal_threshold_percent"),
        PET_HEAL_DEFAULT_THRESHOLD_PERCENT,
        PET_HEAL_MIN_THRESHOLD_PERCENT,
        PET_HEAL_MAX_THRESHOLD_PERCENT,
    )

    if hp_percent >= threshold_percent:
        message = f"宝宝血量正常: hp={hp_percent}% threshold={threshold_percent}%"
        pet_heal_state["last_message"] = message
        return {
            "success": True,
            "healed": False,
            "message": message,
        }

    now = time.time()
    last_healed_at = float(pet_heal_state.get("last_healed_at") or 0.0)

    if now - last_healed_at < PET_HEAL_COOLDOWN_SECONDS:
        message = (
            f"宝宝加血冷却中: hp={hp_percent}% threshold={threshold_percent}% "
            f"cooldown={PET_HEAL_COOLDOWN_SECONDS:g}s"
        )
        pet_heal_state["last_message"] = message
        return {
            "success": True,
            "healed": False,
            "message": message,
        }

    position = filter_result.get("position") or (monster or {}).get("position", {})

    try:
        x = int(position.get("x"))
        y = int(position.get("y"))
    except (TypeError, ValueError, AttributeError):
        message = f"宝宝加血失败: 位置异常 position={position}"
        pet_heal_state["last_message"] = message
        return {
            "success": False,
            "healed": False,
            "message": message,
        }

    move_success, move_message = op.move_mouse_to(x, y)

    if not move_success:
        message = f"宝宝加血移动鼠标失败: hp={hp_percent}% {move_message}"
        pet_heal_state["last_message"] = message
        return {
            "success": False,
            "healed": False,
            "message": message,
        }

    key = normalize_pet_heal_key(app_settings.get("pet_heal_key", PET_HEAL_DEFAULT_KEY))
    key_result = press_keyboard(key, hold_ms=120, repeat=1, interval_ms=80)

    if not key_result.get("success"):
        message = f"宝宝加血按键失败: hp={hp_percent}% key={key} {key_result.get('message', '')}"
        pet_heal_state["last_message"] = message
        return {
            "success": False,
            "healed": False,
            "message": message,
        }

    pet_heal_state["last_healed_at"] = now
    message = f"宝宝加血触发: hp={hp_percent}% threshold={threshold_percent}% mouse={x},{y} key={key}"
    pet_heal_state["last_message"] = message
    return {
        "success": True,
        "healed": True,
        "message": message,
    }


# 生成宝宝加血最近目标状态。
def make_pet_heal_target_status(monster, filter_result):
    monster = monster or {}
    filter_result = filter_result or {}
    position = filter_result.get("position") or monster.get("position", {})
    logic = monster.get("logic", {})
    x = parse_optional_int((position or {}).get("x")) or 0
    y = parse_optional_int((position or {}).get("y")) or 0
    return {
        "name": filter_result.get("text", ""),
        "hp_percent": get_monster_hp_percent(monster),
        "x": x,
        "y": y,
        "logic": make_logic_status(logic),
    }


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

        with Image.open(scan_file) as scan_image:
            hp_percent = calculate_health_bar_percent(scan_image, blood_bar, GREEN_HEALTH_BAR_RGB)

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


# 获取玩家自身血条匹配配置：宽度固定，高度用特征图。
def get_player_blood_feature_templates():
    feature = read_cv2_image(player_blood_feature_image)

    return [{
        "image": feature,
        "blood_width": HEALTH_BAR_WIDTH_PIXELS,
        "blood_height": feature.shape[0],
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
    screenshot_dir.mkdir(parents=True, exist_ok=True)

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
def scan_monsters(player_info=None):
    with monster_scan_lock:
        try:
            return scan_monsters_locked(player_info)
        except Exception as error:
            return {
                "success": False,
                "monsters": [],
                "message": f"怪物扫描异常: {error}",
            }


# 执行怪物扫描：由锁保护的实际扫描流程。
def scan_monsters_locked(player_info=None):
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

    blood_width, blood_height = get_blood_bar_match_size(monster_blood_feature_image)
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

    logic_available = add_monsters_logic(monsters, player_info, player_x, player_y)

    monsters.sort(key=lambda monster: (get_monster_logic_distance(monster), monster["distance"]))

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
        "player_logic": make_player_logic_status(player_info),
        "logic_available": logic_available,
        "client": client,
        "debug_points": debug_points,
        "message": (
            f"怪物扫描完成 count={len(monsters)} player={player_x},{player_y} "
            f"logic={'ok' if logic_available else 'missing'} client_size={width}x{height}"
        ),
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


# 给怪物扫描结果补充逻辑坐标；坐标不可用时保留空字典。
def add_monsters_logic(monsters, player_info, player_screen_x, player_screen_y):
    player_logic_x, player_logic_y = get_player_logic_coordinate(player_info)

    if player_logic_x is None or player_logic_y is None:
        for monster in monsters:
            monster["logic"] = {}
        return False

    for monster in monsters:
        position = monster.get("position", {})

        try:
            point = screen_to_logic_point(
                position.get("x"),
                position.get("y"),
                player_screen_x,
                player_screen_y,
                player_logic_x,
                player_logic_y,
            )
        except (TypeError, ValueError):
            monster["logic"] = {}
            continue

        logic_dx = int(point.get("logic_dx", 0))
        logic_dy = int(point.get("logic_dy", 0))
        monster["logic"] = {
            "x": int(point["x"]),
            "y": int(point["y"]),
            "dx": logic_dx,
            "dy": logic_dy,
            "distance": max(abs(logic_dx), abs(logic_dy)),
        }

    return True


# 生成玩家逻辑坐标状态。
def make_player_logic_status(player_info):
    player_x, player_y = get_player_logic_coordinate(player_info)

    if player_x is None or player_y is None:
        return {}

    return {
        "x": player_x,
        "y": player_y,
    }


# 怪物逻辑距离兜底值：没有逻辑坐标时排到后面。
def get_monster_logic_distance(monster):
    logic = (monster or {}).get("logic", {})

    try:
        return int(logic.get("distance"))
    except (TypeError, ValueError):
        return 999999


# 读取怪物血量百分比：异常时按满血处理。
def get_monster_hp_percent(monster):
    try:
        return int(float((monster or {}).get("hp_percent", 100)))
    except (TypeError, ValueError):
        return 100


# 判断逻辑坐标是否可用。
def is_valid_logic(logic):
    if not isinstance(logic, dict):
        return False

    try:
        int(logic.get("x"))
        int(logic.get("y"))
    except (TypeError, ValueError):
        return False

    return True


# 计算两个逻辑坐标的棋盘距离。
def get_logic_distance(first, second):
    if not is_valid_logic(first) or not is_valid_logic(second):
        return 999999

    return max(
        abs(int(first["x"]) - int(second["x"])),
        abs(int(first["y"]) - int(second["y"])),
    )


# 复制逻辑坐标，避免状态里保存扫描结果引用。
def copy_logic(logic):
    if not is_valid_logic(logic):
        return {}

    return {
        "x": int(logic["x"]),
        "y": int(logic["y"]),
    }


# 复制屏幕位置。
def copy_position(position):
    try:
        return {
            "x": int(position.get("x")),
            "y": int(position.get("y")),
        }
    except (AttributeError, TypeError, ValueError):
        return {}


# 复制血条矩形。
def copy_blood_bar(blood_bar):
    if not isinstance(blood_bar, dict):
        return {}

    try:
        return {
            "left": int(blood_bar["left"]),
            "top": int(blood_bar["top"]),
            "right": int(blood_bar["right"]),
            "bottom": int(blood_bar["bottom"]),
        }
    except (KeyError, TypeError, ValueError):
        return {}


# 根据成功点击的怪物创建锁定目标。
def make_locked_target(monster, now=None):
    now = time.time() if now is None else now
    logic = copy_logic((monster or {}).get("logic", {}))
    return {
        "origin_logic": dict(logic),
        "last_logic": dict(logic),
        "last_hp_percent": get_monster_hp_percent(monster),
        "last_blood_bar": copy_blood_bar((monster or {}).get("blood_bar", {})),
        "last_position": copy_position((monster or {}).get("position", {})),
        "miss_count": 0,
        "locked_at": now,
        "last_seen_at": now,
        "next_recheck_at": now + TARGET_RECHECK_SECONDS,
        "next_attack_at": now + ATTACK_CLICK_INTERVAL_SECONDS,
    }


# 用重新找回的怪物刷新锁定目标。
def update_locked_target(locked_target, monster, now=None):
    now = time.time() if now is None else now
    locked_target["last_logic"] = copy_logic((monster or {}).get("logic", {}))
    locked_target["last_hp_percent"] = get_monster_hp_percent(monster)
    locked_target["last_blood_bar"] = copy_blood_bar((monster or {}).get("blood_bar", {}))
    locked_target["last_position"] = copy_position((monster or {}).get("position", {}))
    locked_target["miss_count"] = 0
    locked_target["last_seen_at"] = now
    locked_target["next_recheck_at"] = now + TARGET_RECHECK_SECONDS
    return locked_target


# 写入当前锁定目标状态。
def set_battle_locked_target(battle_runtime_state, locked_target, message=""):
    if battle_runtime_state is None:
        return

    battle_runtime_state["last_target"] = locked_target or {}

    if message:
        battle_runtime_state["last_message"] = message


# 清空当前锁定目标。
def clear_battle_locked_target(battle_runtime_state, message=""):
    if battle_runtime_state is None:
        return

    battle_runtime_state["last_target"] = {}

    if message:
        battle_runtime_state["last_message"] = message


# 清空连续无怪计数。
def reset_no_monster_count(battle_runtime_state, reason=""):
    if battle_runtime_state is None:
        return

    battle_runtime_state["no_monster_count"] = 0

    if reason:
        battle_runtime_state["last_no_monster_reason"] = reason


# 增加连续无怪计数。
def increment_no_monster_count(battle_runtime_state, reason="", limit=None):
    if battle_runtime_state is None:
        return 0

    count = int(battle_runtime_state.get("no_monster_count") or 0) + 1
    battle_runtime_state["no_monster_count"] = count

    if limit is not None:
        count = clamp_no_monster_count(battle_runtime_state, limit)

    battle_runtime_state["last_no_monster_reason"] = reason

    if reason:
        battle_runtime_state["last_message"] = f"连续无怪 {count} 次: {reason}"

    return count


# 把连续无怪计数限制在当前设置范围内。
def clamp_no_monster_count(battle_runtime_state, limit):
    if battle_runtime_state is None:
        return 0

    limit = normalize_number(limit, NO_MONSTER_SCAN_LIMIT_DEFAULT, NO_MONSTER_SCAN_LIMIT_MIN, NO_MONSTER_SCAN_LIMIT_MAX)
    count = normalize_number(battle_runtime_state.get("no_monster_count"), 0, 0, limit)
    battle_runtime_state["no_monster_count"] = count
    return count


# 移动或停止自动流程时清理战斗运行状态。
def reset_battle_runtime(battle_runtime_state, reason=""):
    if battle_runtime_state is None:
        return

    battle_runtime_state["no_monster_count"] = 0
    battle_runtime_state["last_no_monster_reason"] = reason
    battle_runtime_state["last_target"] = {}
    battle_runtime_state["ignored_targets"] = []

    if reason:
        battle_runtime_state["last_message"] = reason


# 清理过期忽略目标。
def prune_ignored_targets(battle_runtime_state, now=None):
    if battle_runtime_state is None:
        return []

    now = time.time() if now is None else now
    targets = []

    for target in battle_runtime_state.get("ignored_targets", []):
        try:
            expires_at = float(target.get("expires_at") or 0)
        except (TypeError, ValueError):
            continue

        if expires_at > now:
            targets.append(target)

    battle_runtime_state["ignored_targets"] = targets
    return targets


# 添加临时忽略目标，避免失败点立刻被重新选择。
def add_ignored_target(battle_runtime_state, logic, reason="", now=None):
    if battle_runtime_state is None or not is_valid_logic(logic):
        return

    now = time.time() if now is None else now
    prune_ignored_targets(battle_runtime_state, now)
    battle_runtime_state.setdefault("ignored_targets", []).append({
        "logic": copy_logic(logic),
        "expires_at": now + IGNORED_TARGET_SECONDS,
        "reason": reason,
    })


# 判断某个逻辑点是否处于忽略期。
def is_logic_ignored(logic, battle_runtime_state, now=None):
    if not is_valid_logic(logic):
        return False

    for target in prune_ignored_targets(battle_runtime_state, now):
        if get_logic_distance(logic, target.get("logic", {})) <= IGNORED_TARGET_RADIUS:
            return True

    return False


# 判断怪物是否可作为新目标。
def is_attackable_monster(monster, battle_runtime_state=None, now=None):
    logic = (monster or {}).get("logic", {})

    if not is_valid_logic(logic):
        return False

    if get_monster_hp_percent(monster) <= 0:
        return False

    if is_logic_ignored(logic, battle_runtime_state, now):
        return False

    return True


# 在扫描结果中选择新攻击目标：近处优先，近处残血优先。
def choose_new_monster_target(monsters, battle_runtime_state=None, now=None):
    candidates = [
        monster
        for monster in monsters or []
        if is_attackable_monster(monster, battle_runtime_state, now)
    ]

    if not candidates:
        return None, "没有可攻击怪物"

    near = [
        monster
        for monster in candidates
        if get_monster_logic_distance(monster) <= NEAR_MONSTER_LOGIC_RADIUS
    ]
    group = near if near else candidates
    group_name = "近处" if near else "远处"
    wounded = [monster for monster in group if get_monster_hp_percent(monster) < 100]

    if wounded:
        target = sorted(
            wounded,
            key=lambda monster: (
                get_monster_hp_percent(monster),
                get_monster_logic_distance(monster),
                int(monster.get("distance", 999999)),
            ),
        )[0]
        return target, f"{group_name}残血优先"

    target = sorted(
        group,
        key=lambda monster: (
            get_monster_logic_distance(monster),
            int(monster.get("distance", 999999)),
        ),
    )[0]
    return target, f"{group_name}最近优先"


# 把逻辑点投影到当前屏幕坐标。
def project_logic_to_screen(logic, player_info, player_screen):
    if not is_valid_logic(logic):
        return None

    player_logic_x, player_logic_y = get_player_logic_coordinate(player_info)

    if player_logic_x is None or player_logic_y is None:
        return None

    try:
        return logic_to_screen_point(
            logic["x"],
            logic["y"],
            player_logic_x,
            player_logic_y,
            player_screen["x"],
            player_screen["y"],
        )
    except (KeyError, TypeError, ValueError):
        return None


# 计算屏幕点距离。
def get_screen_distance(first, second):
    try:
        return math.dist(
            (int(first.get("x")), int(first.get("y"))),
            (int(second.get("x")), int(second.get("y"))),
        )
    except (AttributeError, TypeError, ValueError):
        return 999999


# 从扫描结果里找回锁定目标。
def find_locked_monster(monsters, locked_target, player_info, player_screen):
    last_logic = (locked_target or {}).get("last_logic", {})

    if not is_valid_logic(last_logic):
        return None, "锁定目标缺少逻辑坐标"

    projected = project_logic_to_screen(last_logic, player_info, player_screen)
    strong = []
    weak = []

    for monster in monsters or []:
        logic = monster.get("logic", {})

        if not is_valid_logic(logic) or get_monster_hp_percent(monster) <= 0:
            continue

        logic_distance = get_logic_distance(logic, last_logic)
        screen_distance = 999999

        if projected:
            screen_distance = get_screen_distance(monster.get("position", {}), projected)

        item = {
            "monster": monster,
            "logic_distance": logic_distance,
            "screen_distance": screen_distance,
        }

        if logic_distance <= LOCK_STRONG_RADIUS:
            strong.append(item)
        elif logic_distance <= LOCK_WEAK_RADIUS and screen_distance <= LOCK_WEAK_SCREEN_RADIUS:
            weak.append(item)

    candidates = strong if strong else weak

    if not candidates:
        return None, "锁定目标附近没有匹配怪物"

    last_hp = get_monster_hp_percent({"hp_percent": locked_target.get("last_hp_percent", 100)})

    def sort_key(item):
        monster = item["monster"]
        hp = get_monster_hp_percent(monster)
        hp_rise_penalty = 1 if hp > last_hp + LOCK_HP_RISE_TOLERANCE else 0
        return (
            item["logic_distance"],
            hp_rise_penalty,
            item["screen_distance"],
            hp,
        )

    selected = sorted(candidates, key=sort_key)[0]
    match_type = "强匹配" if strong else "弱匹配"
    return selected["monster"], (
        f"{match_type} logic_distance={selected['logic_distance']} "
        f"screen_distance={round(selected['screen_distance'])}"
    )


# 识别单个怪物名称：按表格传入的位置和血条信息补充名称。
def recognize_monster_name(position_x, position_y, blood_bar=None, save_debug=False):
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
def recognize_monster_name_locked(position_x, position_y, blood_bar=None, save_debug=False):
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
        "ocr_logs": name_result.get("ocr_logs", []),
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


# 计算血条百分比：按第二行连续命中的填充像素计算。
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

    if bar_width <= HEALTH_BAR_FILL_START_X or bar_height <= HEALTH_BAR_FILL_START_Y:
        return 0

    fill_start = HEALTH_BAR_FILL_START_X
    fill_end = min(bar_width, fill_start + HEALTH_BAR_FULL_FILL_PIXELS)
    crop = pixels[box["top"]:box["bottom"], box["left"]:box["right"]]
    fill_pixels = 0

    for column_index in range(fill_start, fill_end):
        pixel = crop[HEALTH_BAR_FILL_START_Y, column_index, :]

        if not is_health_bar_fill_pixel(pixel, target_rgb, tolerance):
            break

        fill_pixels += 1

    percent = round(fill_pixels * 100 / HEALTH_BAR_FULL_FILL_PIXELS)
    return clamp_number(percent, 0, 100)

# 判断单个像素是否接近目标血条颜色。
def is_health_bar_fill_pixel(pixel, target_rgb, tolerance):
    target = np.array(target_rgb, dtype=np.int16)
    delta = np.abs(pixel.astype(np.int16) - target)
    return bool(np.all(delta <= tolerance))


# 识别怪物名区域：用 OP 大漠字库直接识别绑定窗口文字。
def recognize_monster_name_box(box, save_debug=False):
    empty_result = {
        "name": "未识别",
        "text": "",
        "raw_text": "",
        "mask_text": "",
        "color": "",
        "used_attempt": 0,
        "reject_reason": "",
        "debug_images": [],
        "ocr_logs": [],
    }

    if not is_valid_box(box):
        return empty_result

    if save_debug:
        debug_image_dir.mkdir(parents=True, exist_ok=True)
        debug_prefix = get_debug_image_prefix("monster_name")

    last_result = empty_result
    ocr_colors = get_monster_name_ocr_colors()
    ocr_logs = []

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
                ocr_logs.append(
                    f"怪物名OCR截图失败 attempt={attempt} "
                    f"box={box.get('left')},{box.get('top')},{box.get('right')},{box.get('bottom')} "
                    f"file={raw_file}"
                )
                last_result = {
                    **last_result,
                    "used_attempt": attempt,
                    "ocr_logs": list(ocr_logs),
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
                sim=MONSTER_NAME_OCR_SIM,
            )
            mask_text = ""
            selected_text = raw_text
            selected_name = selected_text or "未识别"
            reject_reason = get_monster_name_reject_reason(selected_name)
            ocr_logs.append(
                f"怪物名OCR调用 attempt={attempt} color={ocr_color} sim={MONSTER_NAME_OCR_SIM} "
                f"raw={raw_text!r} reject={reject_reason} "
                f"box={box.get('left')},{box.get('top')},{box.get('right')},{box.get('bottom')} "
                f"file={raw_file}"
            )
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
                    "ocr_logs": list(ocr_logs),
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
                "ocr_logs": list(ocr_logs),
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

    if not re.search(r"[\u4e00-\u9fff]", str(name or "")):
        return "no_chinese_text"

    player_name = get_bound_player_name()

    if not player_name:
        return ""

    if normalize_player_name_text(name) == player_name:
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


# 获取怪物血条匹配配置：宽度固定，高度用特征图。
def get_blood_feature_templates():
    feature = read_cv2_image(monster_blood_feature_image)

    return [{
        "image": feature,
        "blood_width": HEALTH_BAR_WIDTH_PIXELS,
        "blood_height": feature.shape[0],
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


# 获取血条匹配框尺寸：宽度固定，高度用实际特征图。
def get_blood_bar_match_size(feature_image_file):
    with Image.open(feature_image_file) as image:
        _, blood_height = image.size
    return HEALTH_BAR_WIDTH_PIXELS, blood_height


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


# 获取最近一次地图坐标 OCR 原文。
def get_map_coordinate_raw_text():
    return map_coordinate_debug_state.get("raw", "")


# 保存地图坐标 OCR 原文。
def set_map_coordinate_raw_text(text):
    map_coordinate_debug_state["raw"] = str(text or "")


# 读取地图坐标：从绑定窗口截图底部区域并交给 OCR 解析坐标。
def read_map_coordinate():
    if not op.is_window_bound():
        set_map_coordinate_raw_text("")
        return "", "", ""

    # 绑定窗口尺寸：用于确定坐标区域截图范围。
    width, height = get_bound_client_size()
    if width <= 0 or height <= 0:
        set_map_coordinate_raw_text("")
        return "", "", ""

    # 截图左上角：从窗口底部裁剪 18 像素高的坐标显示区域。
    x1, y1 = 0, max(0, height - 18)
    # 截图右下角：限制坐标区域宽度并覆盖底部最后一行。
    x2, y2 = min(width - 1, 170), height - 1

    coordinate_image.parent.mkdir(parents=True, exist_ok=True)
    success, _ = op.capture_bound_client(x1, y1, x2, y2, coordinate_image)

    if not success:
        set_map_coordinate_raw_text("")
        return "", "", ""

    # OP 字库文本：承载坐标区域识别出的原始文字。
    text = op.ocr_text(x1, y1, x2, y2)
    set_map_coordinate_raw_text(text)
    return parse_map_coordinate_text(text)


# 解析地图坐标文本：从 OCR 文本中提取地图名和 x/y 坐标。
def parse_map_coordinate_text(text):
    # 坐标匹配组：优先匹配“地图名:41:56”和“地图名 41:56”形式的 OCR 结果。
    pairs = re.findall(r"([^\d\s:：,，/\\]{1,20})\s*[:：,，]?\s*(\d{1,4})\s*[:：,，]\s*(\d{1,4})", text)

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

import math
import re
import tempfile
import threading
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

import ocr_client
import op
import overlay
import win32


# 项目根目录：业务脚本在 py/ 下，运行资源仍在项目根目录。
base_dir = Path(__file__).resolve().parent.parent
# 截图目录：保存绑定窗口截图和调试图片。
screenshot_dir = base_dir / "screenshots"
# 调试图片目录：保存怪物名 OCR 前后的输入图，便于排查识别失败。
debug_image_dir = base_dir / "DebugImage"
# 地图坐标截图路径：保存游戏底部坐标区域截图，供 OCR 识别使用。
coordinate_image = screenshot_dir / "map_coordinate.bmp"
# PNG 资源目录：保存血条特征图等图像匹配资源。
png_dir = base_dir / "png"
# 怪物血条特征图：血条最左侧小片段，用于统一查找满血和残血怪物。
monster_blood_feature_image = png_dir / "残血血条特征图.png"
# 红色血条模板：用于读取血条标准宽高。
red_blood_bar_image = png_dir / "红色血条.png"
# 坐标读取锁：串行化截图和 OCR 流程，避免并发读写同一张截图。
coordinate_lock = threading.Lock()
# 怪物扫描锁：串行化截图、鼠标悬停和 OCR 流程。
monster_scan_lock = threading.Lock()
# 底部界面高度：估算游戏底栏高度，用来计算角色移动点击原点。
BOTTOM_UI_HEIGHT = 155
# 默认键盘测试键：用于页面测试按钮验证后台键盘输入链路。
keyboard_test_key = "M"
# 怪物悬停偏移：血条底边到怪物名字中点的位置，兼作怪物位置和鼠标悬停点。
MONSTER_HOVER_OFFSET_Y = 45
# 怪物名 OCR 横向半宽：约 5.5 个中文字总宽，避免两侧复杂背景干扰。
MONSTER_NAME_HALF_WIDTH = 33
# 怪物名 OCR 上边距：血条底边向下到名字区域顶部的距离。
MONSTER_NAME_TOP_OFFSET = 30
# 怪物名 OCR 下边距：血条底边向下到名字区域底部的距离。
MONSTER_NAME_BOTTOM_OFFSET = 60
# 血条特征匹配阈值：0 表示完全一致，保留极小容差兼容截图格式差异。
MONSTER_FEATURE_MATCH_THRESHOLD = 0.001
# 怪物名字显示等待时间：鼠标悬停后等待游戏显示名字。
MONSTER_HOVER_WAIT_SECONDS = 0.25
# 怪物名字 OCR 最大截图次数：第一次未截到字或 OCR 为空时短暂重试。
MONSTER_NAME_OCR_MAX_ATTEMPTS = 2
# 怪物名字 OCR 重试等待时间：给 hover 名字显示留出额外缓冲。
MONSTER_NAME_OCR_RETRY_DELAY_SECONDS = 0.2
# 怪物名字白字阈值：用于从复杂背景中提取白色文字。
MONSTER_NAME_WHITE_THRESHOLD = 155
# 怪物名字白字像素阈值：低于此值时认为很可能还没有截到名字。
MONSTER_NAME_WHITE_PIXEL_MIN = 12
# 怪物名字白字连通块过滤：去除草地高光等单点噪声。
MONSTER_NAME_COMPONENT_PIXEL_MIN = 2
# 怪物名字 OCR 放大倍数：小号白字放大后再交给 PaddleOCR。
MONSTER_NAME_MASK_SCALE = 4
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


# 获取绑定窗口尺寸诊断：同时返回原始尺寸和 OP 有效坐标尺寸。
def get_bound_client_info():
    bound = op.get_bound_window()
    raw_width, raw_height = win32.get_client_size(bound["hwnd"])
    scale = op.get_bind_coordinate_scale()

    if raw_width <= 0 or raw_height <= 0:
        width, height = raw_width, raw_height
    else:
        width = max(1, round(raw_width * scale))
        height = max(1, round(raw_height * scale))

    screen = win32.get_screen_info()

    return {
        "width": width,
        "height": height,
        "raw_width": raw_width,
        "raw_height": raw_height,
        "bind_scale": scale,
        "screen_width": screen["width"],
        "screen_height": screen["height"],
        "dpi_scale_percent": screen["scale_percent"],
    }


# 获取大地图交互矩形：大地图固定 550x350，按 OP 有效客户区居中。
def get_map_rect(width, height):
    left = round((width - 550) / 2)
    top = round((height - 350) / 2)
    return left, top, left + 550, top + 350


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

    player_x, player_y = get_move_origin(width, height)

    return {
        "success": True,
        "player_x": player_x,
        "player_y": player_y,
        "client": client,
        "bottom_ui_height": BOTTOM_UI_HEIGHT,
        "message": f"玩家屏幕位置 x={player_x} y={player_y} client_size={width}x{height}",
    }


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
    success, message = capture_bound_client_checked(0, 0, width, height, screenshot_file)

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
def scan_monsters(show_overlay=True):
    with monster_scan_lock:
        try:
            return scan_monsters_locked(show_overlay)
        except Exception as error:
            return {
                "success": False,
                "monsters": [],
                "message": f"怪物扫描异常: {error}",
            }


# 执行怪物扫描：由锁保护的实际扫描流程。
def scan_monsters_locked(show_overlay=True):
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

    player_x, player_y = get_move_origin(width, height)
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

        matches = find_blood_feature_matches(scan_file)
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

    if show_overlay:
        show_scan_overlay(debug_points)

    return {
        "success": True,
        "monsters": monsters,
        "count": len(monsters),
        "player": {
            "x": player_x,
            "y": player_y,
        },
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
def recognize_monster_name(position_x, position_y, blood_bar=None, show_overlay=True):
    with monster_scan_lock:
        try:
            return recognize_monster_name_locked(position_x, position_y, blood_bar, show_overlay)
        except Exception as error:
            return {
                "success": False,
                "name": "未识别",
                "name_text": "",
                "message": f"怪物名称识别异常: {error}",
            }


# 执行单个怪物名称识别：只悬停并 OCR 当前指定怪物。
def recognize_monster_name_locked(position_x, position_y, blood_bar=None, show_overlay=True):
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

    if move_success:
        time.sleep(MONSTER_HOVER_WAIT_SECONDS)

    name_result = recognize_monster_name_box(name_box)
    name_text = name_result["text"]
    name = name_result["name"]
    debug_points = []

    if active_blood_bar:
        debug_points.append(make_debug_point(active_blood_bar["left"], active_blood_bar["top"], "red"))

    debug_points.extend([
        make_debug_point(hover_x, hover_y, "orange"),
        make_debug_point(*box_center(name_box), "purple"),
    ])

    if show_overlay:
        show_scan_overlay(debug_points)

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


# 获取血条内部填充行：排除上下黑边，兼容 64x8 和 dx2 半尺寸 32x4。
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


# 识别怪物名 OCR 框：保留调试图，并用白字 mask 放大图增强小字识别。
def recognize_monster_name_box(box):
    empty_result = {
        "name": "未识别",
        "text": "",
        "raw_text": "",
        "mask_text": "",
        "used_attempt": 0,
        "reject_reason": "",
        "debug_images": [],
    }

    if not is_valid_box(box):
        return empty_result

    debug_image_dir.mkdir(exist_ok=True)
    debug_prefix = get_debug_image_prefix("monster_name")
    last_result = empty_result

    for attempt in range(1, MONSTER_NAME_OCR_MAX_ATTEMPTS + 1):
        if attempt > 1:
            time.sleep(MONSTER_NAME_OCR_RETRY_DELAY_SECONDS)

        raw_file = debug_image_dir / f"{debug_prefix}_raw_{attempt}.bmp"
        mask_file = debug_image_dir / f"{debug_prefix}_mask_{attempt}.png"
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
                        "mask": "",
                        "raw_text": "",
                        "mask_text": "",
                        "white_pixels": 0,
                    },
                ],
            }
            continue

        raw_text = ocr_client.recognize_text(raw_file)
        white_pixels = create_monster_name_mask(raw_file, mask_file)
        mask_text = ""

        if white_pixels >= MONSTER_NAME_WHITE_PIXEL_MIN:
            mask_text = ocr_client.recognize_text(mask_file)

        selected_text = select_monster_name_text(raw_text, mask_text)
        selected_name = clean_monster_name(selected_text)
        reject_reason = get_monster_name_reject_reason(selected_name)
        debug_images = [
            *last_result["debug_images"],
            {
                "attempt": attempt,
                "raw": str(raw_file),
                "mask": str(mask_file),
                "raw_text": raw_text,
                "mask_text": mask_text,
                "white_pixels": white_pixels,
            },
        ]

        if reject_reason:
            return {
                "name": "未识别",
                "text": selected_text,
                "raw_text": raw_text,
                "mask_text": mask_text,
                "used_attempt": attempt,
                "reject_reason": reject_reason,
                "debug_images": debug_images,
            }

        last_result = {
            "name": selected_name,
            "text": selected_text,
            "raw_text": raw_text,
            "mask_text": mask_text,
            "used_attempt": attempt,
            "reject_reason": "",
            "debug_images": debug_images,
        }

        if selected_name != "未识别" and white_pixels >= MONSTER_NAME_WHITE_PIXEL_MIN:
            return last_result

    return last_result


# 创建本次调试图片文件名前缀：时间戳加短序号，便于按一次识别归档。
def get_debug_image_prefix(prefix):
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    sequence = time.time_ns() % 1_000_000
    return f"{prefix}_{timestamp}_{sequence:06d}"


# 生成黑底白字的怪物名 mask：去背景、去单点噪声并放大。
def create_monster_name_mask(raw_file, mask_file):
    with Image.open(raw_file) as image:
        pixels = np.array(image.convert("RGB"))

    white_mask = (
        (pixels[:, :, 0] >= MONSTER_NAME_WHITE_THRESHOLD)
        & (pixels[:, :, 1] >= MONSTER_NAME_WHITE_THRESHOLD)
        & (pixels[:, :, 2] >= MONSTER_NAME_WHITE_THRESHOLD)
    )
    filtered_mask = filter_small_components(white_mask, MONSTER_NAME_COMPONENT_PIXEL_MIN)
    white_pixels = int(filtered_mask.sum())
    mask_pixels = (filtered_mask.astype(np.uint8) * 255)
    mask_image = Image.fromarray(mask_pixels, mode="L")
    mask_image = crop_mask_with_margin(mask_image, filtered_mask, 6)
    mask_image = mask_image.resize(
        (
            max(1, mask_image.width * MONSTER_NAME_MASK_SCALE),
            max(1, mask_image.height * MONSTER_NAME_MASK_SCALE),
        ),
        Image.Resampling.NEAREST,
    )
    mask_image.save(mask_file)
    return white_pixels


# 过滤白色 mask 中的单点噪声。
def filter_small_components(mask, minimum_area):
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8),
        8,
    )
    filtered = np.zeros(mask.shape, dtype=np.uint8)

    for component_index in range(1, component_count):
        area = stats[component_index, cv2.CC_STAT_AREA]

        if area >= minimum_area:
            filtered[labels == component_index] = 1

    return filtered.astype(bool)


# 裁掉 mask 四周大块空白，保留少量边距帮助 OCR 检测文本。
def crop_mask_with_margin(mask_image, mask, margin):
    ys, xs = np.where(mask)

    if len(xs) == 0 or len(ys) == 0:
        return mask_image

    left = max(0, int(xs.min()) - margin)
    top = max(0, int(ys.min()) - margin)
    right = min(mask_image.width, int(xs.max()) + margin + 1)
    bottom = min(mask_image.height, int(ys.max()) + margin + 1)
    return mask_image.crop((left, top, right, bottom))


# 从原图 OCR 和 mask OCR 中选择更可信的怪物名文本。
def select_monster_name_text(raw_text, mask_text):
    candidates = [raw_text or "", mask_text or ""]
    return max(candidates, key=score_monster_name_text)


# 怪物名文本评分：优先中文更多、更长的候选。
def score_monster_name_text(text):
    name = clean_monster_name(text)

    if name == "未识别":
        return (0, 0, 0)

    chinese_count = len(re.findall(r"[\u4e00-\u9fff]", name))
    return (1 if chinese_count else 0, chinese_count, len(name))


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
    title = op.get_bound_window().get("title", "")
    match = re.search(r"[-－]\s*([^\s\-－]+)\s*$", title)

    if not match:
        return ""

    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9_]", "", match.group(1))


# 查找血条左侧特征：返回所有精确匹配的左上角坐标。
def find_blood_feature_matches(screen_file):
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

    if not matches:
        matches = find_red_bar_component_matches(screen)

    return dedupe_matches(matches)


# 获取血条特征模板：同时尝试原始尺寸和 dx2 有效截图里的半尺寸。
def get_blood_feature_templates():
    feature = read_cv2_image(monster_blood_feature_image)
    blood_width, blood_height = get_image_size(red_blood_bar_image)
    templates = []

    for scale in (1.0, 0.5):
        width = max(1, round(feature.shape[1] * scale))
        height = max(1, round(feature.shape[0] * scale))
        resized = cv2.resize(feature, (width, height), interpolation=cv2.INTER_NEAREST)
        templates.append({
            "image": resized,
            "blood_width": max(1, round(blood_width * scale)),
            "blood_height": max(1, round(blood_height * scale)),
        })

    return templates


# 查找红色水平血条组件：作为特征模板未命中时的兜底。
def find_red_bar_component_matches(screen):
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

        if y >= play_area_bottom:
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


# 截取绑定窗口中的裁剪区域并 OCR。
def recognize_bound_client_box(box, crop_file):
    if not is_valid_box(box):
        return ""

    success, _ = capture_bound_client_checked(
        box["left"],
        box["top"],
        box["right"] - 1,
        box["bottom"] - 1,
        crop_file,
    )

    if not success:
        return ""

    return ocr_client.recognize_text(crop_file)


# 清理怪物名 OCR 文本：优先取 4 个以内中文字符。
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


# 创建 Overlay 调试点。
def make_debug_point(x, y, color):
    return {
        "x": int(x),
        "y": int(y),
        "color": color,
    }


# 显示怪物扫描调试点。
def show_scan_overlay(points):
    try:
        bound = op.get_bound_window()
        overlay.show_points(
            bound["hwnd"],
            points,
            duration_ms=1500,
            scale=op.get_bind_coordinate_scale(),
        )
    except Exception:
        pass


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
    success, message = op.click_mouse_at(move["click_x"], move["click_y"], move["button"])

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

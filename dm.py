import os
import platform
import sys
import time
from pathlib import Path

import overlay

# OP 对象：缓存当前进程使用的 OP 自动化实例。
dm_object = None
# 绑定窗口句柄：记录当前已绑定的游戏窗口 hwnd。
bound_hwnd = None
# 绑定窗口标题：缓存当前绑定窗口的标题用于页面展示。
bound_title = ""
# OP DLL 目录句柄：保存 add_dll_directory 返回值，防止目录句柄被释放。
op_dll_directory = None
# 项目根目录：作为运行时、截图和 vendor 路径的基准目录。
base_dir = Path(__file__).resolve().parent
# OP 运行目录：定位免注册 OP 组件和 Python 包装文件。
op_runtime_dir = base_dir / "vendor" / "op"
# 截图目录：保存绑定窗口截图和调试图片。
screenshot_dir = Path(__file__).resolve().parent / "screenshots"
# 绑定模式候选：按优先级列出可尝试的显示、鼠标和键盘绑定组合。
bind_mode_candidates = [
    ("dx2", "windows", "windows", 0),
    ("gdi", "windows", "windows", 0),
    ("normal.dxgi", "windows", "windows", 0),
    ("normal", "windows", "windows", 0),
    ("dx2", "normal", "normal", 0),
    ("gdi", "normal", "normal", 1),
    ("gdi", "normal", "normal", 0),
    ("normal", "normal", "normal", 0),
]
# 当前绑定模式：记录成功绑定时采用的模式，供坐标缩放和点击方式判断。
active_bind_mode = None
# Overlay 开关：控制点击提示圆环是否绘制。
overlay_enabled = True


# 设置 Overlay 开关：更新点击提示状态并在关闭时隐藏现有提示。
def set_overlay_enabled(enabled):
    global overlay_enabled

    # Overlay 状态值：把外部输入规整为布尔开关。
    overlay_enabled = bool(enabled)

    if not overlay_enabled:
        try:
            overlay.hide()
        except Exception:
            pass


# 获取 Overlay 开关：返回当前点击提示是否启用。
def get_overlay_enabled():
    return overlay_enabled


# 创建 OP 对象：加载 pyop 并实例化 64 位免注册 OP。
def create_dm():
    if platform.architecture()[0] != "64bit":
        raise RuntimeError("OP 64 位免注册模式需要 64 位 Python。")

    # pyop 模块：提供 OP C++ 组件的 Python 包装入口。
    pyop = load_pyop()
    return pyop.libop()


# 加载 pyop：准备 DLL 搜索路径并导入 OP 包装模块。
def load_pyop():
    global op_dll_directory

    if not op_runtime_dir.exists():
        raise FileNotFoundError(f"找不到 OP 运行目录: {op_runtime_dir}")

    # OP 运行时路径：用于加入 sys.path 和 DLL 搜索路径。
    runtime_path = str(op_runtime_dir)

    if runtime_path not in sys.path:
        sys.path.insert(0, runtime_path)

    if op_dll_directory is None and hasattr(os, "add_dll_directory"):
        # OP DLL 目录句柄：注册运行目录到 Windows DLL 搜索路径。
        op_dll_directory = os.add_dll_directory(runtime_path)

    import pyop

    return pyop


# 启动 OP：创建并缓存 OP 实例，同时读取版本信息。
def start_dm():
    global dm_object

    # OP 实例：保存新创建的自动化对象供全局复用。
    dm_object = create_dm()
    dm_object.SetShowErrorMsg(0)
    # OP 版本号：用于确认当前加载的组件版本。
    version = dm_object.Ver()
    return True, version, "OP 初始化成功（64 位免注册）"


# 获取 OP 对象：惰性创建并返回全局 OP 实例。
def get_dm():
    global dm_object

    if dm_object is None:
        # OP 实例：在首次需要时创建自动化对象。
        dm_object = create_dm()

    return dm_object


# 获取 OP 版本：读取已有或临时 OP 实例的版本号。
def get_dm_version():
    if dm_object:
        return dm_object.Ver()

    # 临时 OP 实例：用于未初始化时单次读取版本信息。
    dm = create_dm()
    return dm.Ver()


# 判断窗口绑定：检查当前是否已有绑定窗口句柄。
def is_window_bound():
    return bound_hwnd is not None


# 获取绑定窗口：返回页面展示需要的绑定状态信息。
def get_bound_window():
    return {
        "is_bound": bound_hwnd is not None,
        "hwnd": bound_hwnd,
        "title": bound_title,
    }


# 获取绑定窗口尺寸：根据绑定模式修正客户端尺寸。
def get_bound_client_size():
    # 原始客户端尺寸：从 Win32 读取未缩放的客户区宽高。
    raw_width, raw_height = get_bound_raw_client_size()
    if raw_width <= 0 or raw_height <= 0:
        return raw_width, raw_height

    # 坐标缩放比例：补偿部分绑定模式下 OP 坐标减半的问题。
    scale = get_bind_coordinate_scale()
    return max(1, round(raw_width * scale)), max(1, round(raw_height * scale))


# 获取原始客户端尺寸：直接从绑定窗口读取客户区宽高。
def get_bound_raw_client_size():
    if not bound_hwnd:
        return 0, 0

    import win32gui

    # 客户区矩形：包含左上和右下坐标，用于计算窗口客户区大小。
    left, top, right, bottom = win32gui.GetClientRect(bound_hwnd)
    return right - left, bottom - top


# 获取绑定坐标缩放：依据当前显示绑定模式返回坐标换算比例。
def get_bind_coordinate_scale():
    if active_bind_mode and active_bind_mode[0] == "dx2":
        return 0.5

    return 1.0


# 点击绑定客户端：在已绑定窗口的客户区坐标执行鼠标点击。
def click_bound_client(x, y, button):
    if not bound_hwnd:
        return False, "还没有绑定窗口"

    if overlay_enabled:
        try:
            overlay.hide()
        except Exception:
            pass

    # OP 实例：执行鼠标移动、点击和错误码读取。
    dm = get_dm()
    # 移动结果：记录鼠标移动到目标坐标是否成功。
    move_result = dm.MoveTo(int(x), int(y))
    # 点击结果：记录按钮点击结果和实际使用的点击方法。
    click_result, click_method = click_button(dm, button)

    # 最后错误码：保留 OP 最近一次调用的错误码用于诊断。
    last_error = dm.GetLastError()

    if move_result == 1 and click_result == 1:
        if overlay_enabled:
            try:
                overlay.show_click(
                    bound_hwnd,
                    int(x),
                    int(y),
                    scale=get_bind_coordinate_scale(),
                )
            except Exception:
                pass

        return True, f"点击成功 button={button} method={click_method} x={int(x)} y={int(y)} last_error={last_error}"

    return False, f"点击失败 button={button} method={click_method} x={int(x)} y={int(y)} move={move_result} click={click_result} last_error={last_error}"


# 点击鼠标按钮：根据绑定模式选择直接点击或按下抬起方案。
def click_button(dm, button):
    if is_background_mouse_mode():
        return click_button_down_up(dm, button)

    if button == "left":
        # 左键点击结果：优先尝试 OP 的左键单击接口。
        click_result = dm.LeftClick()
        if click_result == 1:
            return click_result, "click"

        return click_button_down_up(dm, button)

    if button == "right":
        # 右键点击结果：优先尝试 OP 的右键单击接口。
        click_result = dm.RightClick()
        if click_result == 1:
            return click_result, "click"

        return click_button_down_up(dm, button)

    return 0, f"unknown({button})"


# 判断后台鼠标模式：识别当前绑定是否需要使用按下抬起点击。
def is_background_mouse_mode():
    return bool(active_bind_mode and active_bind_mode[1] == "windows")


# 按下抬起点击：用 down/up 组合模拟一次鼠标点击。
def click_button_down_up(dm, button):
    if button == "left":
        # 左键按下结果：记录 LeftDown 是否成功。
        down_result = dm.LeftDown()
        time.sleep(0.05)
        # 左键抬起结果：记录 LeftUp 是否成功。
        up_result = dm.LeftUp()
        return 1 if down_result == 1 and up_result == 1 else 0, f"down_up({down_result},{up_result})"

    if button == "right":
        # 右键按下结果：记录 RightDown 是否成功。
        down_result = dm.RightDown()
        time.sleep(0.05)
        # 右键抬起结果：记录 RightUp 是否成功。
        up_result = dm.RightUp()
        return 1 if down_result == 1 and up_result == 1 else 0, f"down_up({down_result},{up_result})"

    return 0, f"unknown({button})"


# 截取绑定窗口：保存当前绑定窗口画面用于调试。
def capture_bound_window():
    if not bound_hwnd:
        return False, "", "还没有绑定窗口"

    # 绑定窗口尺寸：确定截图范围是否有效。
    width, height = get_bound_client_size()

    if width <= 0 or height <= 0:
        return False, "", f"窗口尺寸异常 size={width}x{height}"

    # 截图文件路径：为本次截图选择一个未占用的文件名。
    screenshot_file = get_next_screenshot_file()
    # OP 实例：执行窗口截图操作。
    dm = get_dm()
    # 截图结果：记录 OP Capture 接口返回状态。
    result = dm.Capture(0, 0, width, height, str(screenshot_file))
    # 最后错误码：保留截图调用后的 OP 错误码。
    last_error = dm.GetLastError()

    if result == 1 and screenshot_file.exists():
        return True, str(screenshot_file), f"绑定窗口截图成功 path={screenshot_file} size={width}x{height} last_error={last_error}"

    return False, str(screenshot_file), f"截图失败 result={result} last_error={last_error}"


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


# 按标题绑定窗口：查找标题匹配的窗口并尝试多种 OP 绑定模式。
def bind_window_by_title(title_part):
    global bound_hwnd
    global bound_title
    global active_bind_mode

    # 绑定关键字：清理外部输入，避免空白影响窗口匹配。
    title_part = (title_part or "").strip()

    if not title_part:
        return False, "", "绑定关键字不能为空"

    # 目标窗口：保存按标题关键字找到的窗口句柄和标题。
    hwnd, title = find_window_by_title(title_part)

    if not hwnd:
        return False, "", f"找不到标题包含 {title_part} 的窗口"

    # OP 实例：用于解除旧绑定并尝试绑定目标窗口。
    dm = get_dm()

    # 解绑结果：记录切换窗口前解除旧绑定的结果。
    unbind_result = 0

    if bound_hwnd:
        # 旧窗口解绑结果：记录切换目标窗口前解除旧绑定是否成功。
        unbind_result = dm.UnBindWindow()
        # 绑定窗口句柄清空：移除旧窗口句柄，避免后续状态误用。
        bound_hwnd = None
        # 绑定窗口标题清空：移除旧窗口标题，等待新绑定写入。
        bound_title = ""
        # 当前绑定模式清空：移除旧模式，等待成功绑定后重设。
        active_bind_mode = None

    # 绑定尝试日志：收集每一种绑定模式的返回信息。
    attempts = []

    # 绑定模式参数：逐个尝试显示、鼠标、键盘和模式配置。
    for display_mode, mouse_mode, keypad_mode, mode in bind_mode_candidates:
        try:
            # 绑定结果：记录当前模式调用 BindWindow 是否成功。
            result = dm.BindWindow(hwnd, display_mode, mouse_mode, keypad_mode, mode)
            # 最后错误码：记录当前绑定尝试后的 OP 错误码。
            last_error = dm.GetLastError()
        # 绑定异常对象：保存当前模式抛出的异常内容。
        except Exception as error:
            attempts.append(
                f"{display_mode}/{mouse_mode}/{keypad_mode}/{mode}: exception={error}"
            )
            continue

        attempts.append(
            f"{display_mode}/{mouse_mode}/{keypad_mode}/{mode}: result={result} last_error={last_error}"
        )

        if result == 1:
            # 已绑定窗口句柄：缓存成功绑定的目标窗口句柄。
            bound_hwnd = hwnd
            # 已绑定窗口标题：缓存成功绑定的目标窗口标题。
            bound_title = title
            # 已生效绑定模式：保存成功绑定时采用的模式参数。
            active_bind_mode = (display_mode, mouse_mode, keypad_mode, mode)
            return (
                True,
                title,
                f"绑定成功 hwnd={hwnd} title={title} display={display_mode} mouse={mouse_mode} keypad={keypad_mode} mode={mode} unbind={unbind_result} last_error={last_error}",
            )

    return (
        False,
        title,
        f"绑定失败 hwnd={hwnd} title={title} unbind={unbind_result} attempts=" + " | ".join(attempts),
    )


# 解绑窗口：释放当前 OP 窗口绑定并清理本地状态。
def unbind_window():
    global bound_hwnd
    global bound_title
    global active_bind_mode

    if not bound_hwnd:
        return True, "", "当前没有绑定窗口"

    # 待解绑窗口句柄：保留解绑前的 hwnd 便于写入日志。
    hwnd = bound_hwnd
    # 待解绑窗口标题：保留解绑前的标题用于返回结果。
    title = bound_title
    # OP 实例：调用底层 UnBindWindow 接口。
    dm = get_dm()
    # 解绑结果：记录 OP 解除绑定是否成功。
    result = dm.UnBindWindow()
    # 最后错误码：记录解绑调用后的 OP 错误码。
    last_error = dm.GetLastError()

    if result == 1:
        # 绑定窗口句柄清空：解除绑定成功后移除当前 hwnd。
        bound_hwnd = None
        # 绑定窗口标题清空：解除绑定成功后移除当前标题。
        bound_title = ""
        # 当前绑定模式清空：解除绑定成功后移除模式记录。
        active_bind_mode = None

        try:
            overlay.hide()
        except Exception:
            pass

        return True, title, f"解除绑定成功 hwnd={hwnd} result={result} last_error={last_error}"

    return False, title, f"解除绑定失败 hwnd={hwnd} result={result} last_error={last_error}"


# 查找窗口标题：遍历可见窗口并返回第一个标题匹配项。
def find_window_by_title(title_part):
    import win32gui

    # 匹配结果列表：收集标题包含关键字的可见窗口。
    result = []

    # 检查单个窗口：作为 EnumWindows 回调用于筛选标题。
    def check_window(hwnd, extra):
        if not win32gui.IsWindowVisible(hwnd):
            return True

        # 当前窗口标题：读取候选窗口标题用于关键字匹配。
        title = win32gui.GetWindowText(hwnd)

        if title_part in title:
            result.append((hwnd, title))

        return True

    win32gui.EnumWindows(check_window, None)

    if result:
        return result[0]

    return None, ""

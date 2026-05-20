import os
import platform
import sys
import time
from pathlib import Path


# OP 对象：缓存当前进程使用的 OP 自动化实例。
op_object = None
# 绑定窗口句柄：记录当前已绑定的游戏窗口 hwnd。
bound_hwnd = None
# 绑定窗口标题：缓存当前绑定窗口的标题用于页面展示。
bound_title = ""
# OP DLL 目录句柄：保存 add_dll_directory 返回值，防止目录句柄被释放。
op_dll_directory = None
# 项目根目录：作为运行时和 vendor 路径的基准目录。
base_dir = Path(__file__).resolve().parent
# OP 运行目录：定位免注册 OP 组件和 Python 包装文件。
op_runtime_dir = base_dir / "vendor" / "op"
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


# 创建 OP 对象：加载 pyop 并实例化 64 位免注册 OP。
def create_op():
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
def start_op():
    global op_object

    # OP 实例：保存新创建的自动化对象供全局复用。
    op_object = create_op()
    op_object.SetShowErrorMsg(0)
    # OP 版本号：用于确认当前加载的组件版本。
    version = op_object.Ver()
    return True, version, "OP 初始化成功（64 位免注册）"


# 获取 OP 对象：惰性创建并返回全局 OP 实例。
def get_op():
    global op_object

    if op_object is None:
        # OP 实例：在首次需要时创建自动化对象。
        op_object = create_op()

    return op_object


# 获取 OP 版本：读取已有或临时 OP 实例的版本号。
def get_op_version():
    if op_object:
        return op_object.Ver()

    # 临时 OP 实例：用于未初始化时单次读取版本信息。
    op = create_op()
    return op.Ver()


# 判断窗口绑定：检查当前是否已有绑定窗口句柄。
def is_window_bound():
    return bound_hwnd is not None


# 获取绑定窗口：返回页面展示需要的绑定状态信息。
def get_bound_window():
    return {
        "is_bound": bound_hwnd is not None,
        "hwnd": bound_hwnd,
        "title": bound_title,
        "bind_mode": format_active_bind_mode(),
    }


# 格式化当前绑定模式：用于日志和状态接口展示 OP 当前采用的显示/鼠标/键盘模式。
def format_active_bind_mode():
    if not active_bind_mode:
        return ""

    display_mode, mouse_mode, keypad_mode, mode = active_bind_mode
    return f"{display_mode}/{mouse_mode}/{keypad_mode}/{mode}"


# 获取绑定坐标缩放：依据当前显示绑定模式返回坐标换算比例。
def get_bind_coordinate_scale():
    if active_bind_mode and active_bind_mode[0] == "dx2":
        return 0.5

    return 1.0


# 按句柄绑定窗口：尝试多种 OP 绑定模式并保存成功状态。
def bind_window(hwnd, title=""):
    global bound_hwnd
    global bound_title
    global active_bind_mode

    if not hwnd:
        return False, "", "绑定窗口句柄不能为空"

    # OP 实例：用于解除旧绑定并尝试绑定目标窗口。
    op = get_op()

    # 解绑结果：记录切换窗口前解除旧绑定的结果。
    unbind_result = 0

    if bound_hwnd:
        # 旧窗口解绑结果：记录切换目标窗口前解除旧绑定是否成功。
        unbind_result = op.UnBindWindow()
        # 绑定状态清空：移除旧窗口状态，等待新绑定写入。
        bound_hwnd = None
        bound_title = ""
        active_bind_mode = None

    # 绑定尝试日志：收集每一种绑定模式的返回信息。
    attempts = []

    # 绑定模式参数：逐个尝试显示、鼠标、键盘和模式配置。
    for display_mode, mouse_mode, keypad_mode, mode in bind_mode_candidates:
        try:
            # 绑定结果：记录当前模式调用 BindWindow 是否成功。
            result = op.BindWindow(hwnd, display_mode, mouse_mode, keypad_mode, mode)
            # 最后错误码：记录当前绑定尝试后的 OP 错误码。
            last_error = op.GetLastError()
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
            # 已绑定窗口状态：缓存成功绑定的目标窗口和模式。
            bound_hwnd = hwnd
            bound_title = title
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
    op = get_op()
    # 解绑结果：记录 OP 解除绑定是否成功。
    result = op.UnBindWindow()
    # 最后错误码：记录解绑调用后的 OP 错误码。
    last_error = op.GetLastError()

    if result == 1:
        # 绑定状态清空：解除绑定成功后移除当前状态。
        bound_hwnd = None
        bound_title = ""
        active_bind_mode = None
        return True, title, f"解除绑定成功 hwnd={hwnd} result={result} last_error={last_error}"

    return False, title, f"解除绑定失败 hwnd={hwnd} result={result} last_error={last_error}"


# 点击绑定客户端：在已绑定窗口的客户区坐标执行鼠标点击。
def click_bound_client(x, y, button):
    if not bound_hwnd:
        return False, "还没有绑定窗口"

    # OP 实例：执行鼠标移动、点击和错误码读取。
    op = get_op()
    # 移动结果：记录鼠标移动到目标坐标是否成功。
    move_result = op.MoveTo(int(x), int(y))
    # 点击结果：记录按钮点击结果和实际使用的点击方法。
    click_result, click_method = click_button(op, button)

    # 最后错误码：保留 OP 最近一次调用的错误码用于诊断。
    last_error = op.GetLastError()

    if move_result == 1 and click_result == 1:
        return True, f"点击成功 button={button} method={click_method} x={int(x)} y={int(y)} last_error={last_error}"

    return False, f"点击失败 button={button} method={click_method} x={int(x)} y={int(y)} move={move_result} click={click_result} last_error={last_error}"


# 点击鼠标按钮：根据绑定模式选择直接点击或按下抬起方案。
def click_button(op, button):
    if is_background_mouse_mode():
        return click_button_down_up(op, button)

    if button == "left":
        # 左键点击结果：优先尝试 OP 的左键单击接口。
        click_result = op.LeftClick()
        if click_result == 1:
            return click_result, "click"

        return click_button_down_up(op, button)

    if button == "right":
        # 右键点击结果：优先尝试 OP 的右键单击接口。
        click_result = op.RightClick()
        if click_result == 1:
            return click_result, "click"

        return click_button_down_up(op, button)

    return 0, f"unknown({button})"


# 判断后台鼠标模式：识别当前绑定是否需要使用按下抬起点击。
def is_background_mouse_mode():
    return bool(active_bind_mode and active_bind_mode[1] == "windows")


# 按下抬起点击：用 down/up 组合模拟一次鼠标点击。
def click_button_down_up(op, button):
    if button == "left":
        # 左键按下结果：记录 LeftDown 是否成功。
        down_result = op.LeftDown()
        time.sleep(0.05)
        # 左键抬起结果：记录 LeftUp 是否成功。
        up_result = op.LeftUp()
        return 1 if down_result == 1 and up_result == 1 else 0, f"down_up({down_result},{up_result})"

    if button == "right":
        # 右键按下结果：记录 RightDown 是否成功。
        down_result = op.RightDown()
        time.sleep(0.05)
        # 右键抬起结果：记录 RightUp 是否成功。
        up_result = op.RightUp()
        return 1 if down_result == 1 and up_result == 1 else 0, f"down_up({down_result},{up_result})"

    return 0, f"unknown({button})"


# 按下抬起键盘按键：后台键盘模式下用较真实的按住时长提升游戏识别率。
def press_bound_key(vk_code, key_name, hold_seconds):
    if not bound_hwnd:
        return False, "还没有绑定窗口"

    # OP 实例：执行绑定窗口的键盘按下和抬起。
    op = get_op()
    down_result = 0
    up_result = 0
    key_error = ""
    up_error = ""

    try:
        try:
            # 按键按下结果：记录 KeyDown 是否被 OP 接受。
            down_result = op.KeyDown(int(vk_code))
            time.sleep(max(0.01, float(hold_seconds)))
        # 键盘异常对象：捕获按下或等待阶段的底层错误。
        except Exception as error:
            key_error = str(error)
        finally:
            try:
                # 按键抬起结果：始终尝试释放，避免游戏里出现卡键。
                up_result = op.KeyUp(int(vk_code))
            # 抬起异常对象：保留释放按键失败的诊断信息。
            except Exception as error:
                up_error = str(error)

        # 最后错误码：保留键盘调用后的 OP 诊断信息。
        last_error = op.GetLastError()
    except Exception as error:
        return False, f"后台键盘异常 key={key_name} vk={vk_code} mode={format_active_bind_mode()} error={error}"

    if key_error or up_error:
        return False, f"后台键盘异常 key={key_name} vk={vk_code} down={down_result} up={up_result} mode={format_active_bind_mode()} key_error={key_error} up_error={up_error} last_error={last_error}"

    if down_result == 1 and up_result == 1:
        return True, f"后台键盘成功 key={key_name} vk={vk_code} method=KeyDown+KeyUp hold={hold_seconds}s mode={format_active_bind_mode()} last_error={last_error}"

    return False, f"后台键盘失败 key={key_name} vk={vk_code} down={down_result} up={up_result} mode={format_active_bind_mode()} last_error={last_error}"


# 截取绑定窗口区域：把指定客户区范围保存到给定文件路径。
def capture_bound_client(x1, y1, x2, y2, file_path):
    if not bound_hwnd:
        return False, "还没有绑定窗口"

    # OP 实例：执行窗口截图操作。
    op = get_op()
    # 截图结果：记录 OP Capture 接口返回状态。
    result = op.Capture(int(x1), int(y1), int(x2), int(y2), str(file_path))
    # 最后错误码：保留截图调用后的 OP 错误码。
    last_error = op.GetLastError()

    if result == 1:
        return True, f"截图调用成功 path={file_path} range={int(x1)},{int(y1)},{int(x2)},{int(y2)} last_error={last_error}"

    return False, f"截图调用失败 result={result} last_error={last_error}"

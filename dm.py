import os
import platform
import sys
import time
from pathlib import Path

import overlay

dm_object = None
bound_hwnd = None
bound_title = ""
op_dll_directory = None
base_dir = Path(__file__).resolve().parent
op_runtime_dir = base_dir / "vendor" / "op"
screenshot_dir = Path(__file__).resolve().parent / "screenshots"
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
active_bind_mode = None
overlay_enabled = True


def set_overlay_enabled(enabled):
    global overlay_enabled

    overlay_enabled = bool(enabled)

    if not overlay_enabled:
        try:
            overlay.hide()
        except Exception:
            pass


def get_overlay_enabled():
    return overlay_enabled


def create_dm():
    if platform.architecture()[0] != "64bit":
        raise RuntimeError("OP 64 位免注册模式需要 64 位 Python。")

    pyop = load_pyop()
    return pyop.libop()


def load_pyop():
    global op_dll_directory

    if not op_runtime_dir.exists():
        raise FileNotFoundError(f"找不到 OP 运行目录: {op_runtime_dir}")

    runtime_path = str(op_runtime_dir)

    if runtime_path not in sys.path:
        sys.path.insert(0, runtime_path)

    if op_dll_directory is None and hasattr(os, "add_dll_directory"):
        op_dll_directory = os.add_dll_directory(runtime_path)

    import pyop

    return pyop


def start_dm():
    global dm_object

    dm_object = create_dm()
    dm_object.SetShowErrorMsg(0)
    version = dm_object.Ver()
    return True, version, "OP 初始化成功（64 位免注册）"


def get_dm():
    global dm_object

    if dm_object is None:
        dm_object = create_dm()

    return dm_object


def get_dm_version():
    if dm_object:
        return dm_object.Ver()

    dm = create_dm()
    return dm.Ver()


def is_window_bound():
    return bound_hwnd is not None


def get_bound_window():
    return {
        "is_bound": bound_hwnd is not None,
        "hwnd": bound_hwnd,
        "title": bound_title,
    }


def get_bound_client_size():
    raw_width, raw_height = get_bound_raw_client_size()
    if raw_width <= 0 or raw_height <= 0:
        return raw_width, raw_height

    scale = get_bind_coordinate_scale()
    return max(1, round(raw_width * scale)), max(1, round(raw_height * scale))


def get_bound_raw_client_size():
    if not bound_hwnd:
        return 0, 0

    import win32gui

    left, top, right, bottom = win32gui.GetClientRect(bound_hwnd)
    return right - left, bottom - top


def get_bind_coordinate_scale():
    if active_bind_mode and active_bind_mode[0] == "dx2":
        return 0.5

    return 1.0


def click_bound_client(x, y, button):
    if not bound_hwnd:
        return False, "还没有绑定窗口"

    if overlay_enabled:
        try:
            overlay.hide()
        except Exception:
            pass

    dm = get_dm()
    move_result = dm.MoveTo(int(x), int(y))
    click_result, click_method = click_button(dm, button)

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


def click_button(dm, button):
    if is_background_mouse_mode():
        return click_button_down_up(dm, button)

    if button == "left":
        click_result = dm.LeftClick()
        if click_result == 1:
            return click_result, "click"

        return click_button_down_up(dm, button)

    if button == "right":
        click_result = dm.RightClick()
        if click_result == 1:
            return click_result, "click"

        return click_button_down_up(dm, button)

    return 0, f"unknown({button})"


def is_background_mouse_mode():
    return bool(active_bind_mode and active_bind_mode[1] == "windows")


def click_button_down_up(dm, button):
    if button == "left":
        down_result = dm.LeftDown()
        time.sleep(0.05)
        up_result = dm.LeftUp()
        return 1 if down_result == 1 and up_result == 1 else 0, f"down_up({down_result},{up_result})"

    if button == "right":
        down_result = dm.RightDown()
        time.sleep(0.05)
        up_result = dm.RightUp()
        return 1 if down_result == 1 and up_result == 1 else 0, f"down_up({down_result},{up_result})"

    return 0, f"unknown({button})"


def capture_bound_window():
    if not bound_hwnd:
        return False, "", "还没有绑定窗口"

    width, height = get_bound_client_size()

    if width <= 0 or height <= 0:
        return False, "", f"窗口尺寸异常 size={width}x{height}"

    screenshot_file = get_next_screenshot_file()
    dm = get_dm()
    result = dm.Capture(0, 0, width, height, str(screenshot_file))
    last_error = dm.GetLastError()

    if result == 1 and screenshot_file.exists():
        return True, str(screenshot_file), f"绑定窗口截图成功 path={screenshot_file} size={width}x{height} last_error={last_error}"

    return False, str(screenshot_file), f"截图失败 result={result} last_error={last_error}"


def get_next_screenshot_file():
    screenshot_dir.mkdir(exist_ok=True)

    index = 1

    while True:
        screenshot_file = screenshot_dir / f"screenshot_{index:04d}.bmp"

        if not screenshot_file.exists():
            return screenshot_file

        index += 1


def bind_window_by_title(title_part):
    global bound_hwnd
    global bound_title
    global active_bind_mode

    title_part = (title_part or "").strip()

    if not title_part:
        return False, "", "绑定关键字不能为空"

    hwnd, title = find_window_by_title(title_part)

    if not hwnd:
        return False, "", f"找不到标题包含 {title_part} 的窗口"

    dm = get_dm()

    unbind_result = 0

    if bound_hwnd:
        unbind_result = dm.UnBindWindow()
        bound_hwnd = None
        bound_title = ""
        active_bind_mode = None

    attempts = []

    for display_mode, mouse_mode, keypad_mode, mode in bind_mode_candidates:
        try:
            result = dm.BindWindow(hwnd, display_mode, mouse_mode, keypad_mode, mode)
            last_error = dm.GetLastError()
        except Exception as error:
            attempts.append(
                f"{display_mode}/{mouse_mode}/{keypad_mode}/{mode}: exception={error}"
            )
            continue

        attempts.append(
            f"{display_mode}/{mouse_mode}/{keypad_mode}/{mode}: result={result} last_error={last_error}"
        )

        if result == 1:
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


def unbind_window():
    global bound_hwnd
    global bound_title
    global active_bind_mode

    if not bound_hwnd:
        return True, "", "当前没有绑定窗口"

    hwnd = bound_hwnd
    title = bound_title
    dm = get_dm()
    result = dm.UnBindWindow()
    last_error = dm.GetLastError()

    if result == 1:
        bound_hwnd = None
        bound_title = ""
        active_bind_mode = None

        try:
            overlay.hide()
        except Exception:
            pass

        return True, title, f"解除绑定成功 hwnd={hwnd} result={result} last_error={last_error}"

    return False, title, f"解除绑定失败 hwnd={hwnd} result={result} last_error={last_error}"


def find_window_by_title(title_part):
    import win32gui

    result = []

    def check_window(hwnd, extra):
        if not win32gui.IsWindowVisible(hwnd):
            return True

        title = win32gui.GetWindowText(hwnd)

        if title_part in title:
            result.append((hwnd, title))

        return True

    win32gui.EnumWindows(check_window, None)

    if result:
        return result[0]

    return None, ""

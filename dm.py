import os
import platform
from pathlib import Path

import overlay


# 为了方便本地使用，你可以把注册码和附加码填在这里。
# 更安全的做法仍然是用环境变量 DM_REG_CODE 和 DM_EXTRA_CODE。
DM_REG_CODE = "hetufei41c42d8e1975be9acb4faccb77204e9a"
DM_EXTRA_CODE = "hyjrip4m5kzwao34"

dm_object = None
bound_hwnd = None
bound_title = ""
screenshot_dir = Path(__file__).resolve().parent / "screenshots"
display_mode = "dx2"
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
    if platform.architecture()[0] != "32bit":
        raise RuntimeError("当前是 64 位 Python，但 dm.dll 是 32 位。请用 32 位 Python 运行。")

    import win32com.client

    return win32com.client.Dispatch("dm.dmsoft")


def start_dm():
    global dm_object

    dm_object = create_dm()
    version = dm_object.Ver()
    success, message = register_dm(dm_object)

    return success, version, message


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


def register_dm(dm):
    reg_code = os.environ.get("DM_REG_CODE") or DM_REG_CODE
    extra_code = os.environ.get("DM_EXTRA_CODE") or DM_EXTRA_CODE

    if not reg_code:
        return False, "缺少注册码，请设置 DM_REG_CODE 或填写 dm.py 里的 DM_REG_CODE"

    if not extra_code:
        return False, "缺少附加码，请设置 DM_EXTRA_CODE 或填写 dm.py 里的 DM_EXTRA_CODE"

    result = dm.Reg(reg_code, extra_code)
    last_error = dm.GetLastError()

    if result == 1:
        return True, f"大漠注册成功 last_error={last_error}"

    return False, f"大漠注册失败 result={result} last_error={last_error}"


def is_window_bound():
    return bound_hwnd is not None


def get_bound_window():
    return {
        "is_bound": bound_hwnd is not None,
        "hwnd": bound_hwnd,
        "title": bound_title,
    }


def get_bound_client_size():
    if not bound_hwnd:
        return 0, 0

    import win32gui

    left, top, right, bottom = win32gui.GetClientRect(bound_hwnd)
    return right - left, bottom - top


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

    if button == "left":
        click_result = dm.LeftClick()
    elif button == "right":
        click_result = dm.RightClick()
    else:
        return False, f"未知鼠标按钮: {button}"

    last_error = dm.GetLastError()

    if move_result == 1 and click_result == 1:
        if overlay_enabled:
            try:
                overlay.show_click(bound_hwnd, int(x), int(y))
            except Exception:
                pass

        return True, f"点击成功 button={button} x={int(x)} y={int(y)} last_error={last_error}"

    return False, f"点击失败 button={button} x={int(x)} y={int(y)} move={move_result} click={click_result} last_error={last_error}"


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


def bind_game_window():
    return bind_window_by_title("闪电侠")


def bind_window_by_title(title_part):
    global bound_hwnd
    global bound_title

    hwnd, title = find_window_by_title(title_part)

    if not hwnd:
        return False, "", f"找不到标题包含 {title_part} 的窗口"

    dm = get_dm()

    force_result = dm.ForceUnBindWindow(hwnd)
    result = dm.BindWindowEx(
        hwnd,
        display_mode,
        "dx.mouse.position.lock.api|dx.mouse.input.lock.api3|dx.mouse.state.api|dx.mouse.api",
        "windows",
        "dx.public.active.api",
        0,
    )
    last_error = dm.GetLastError()

    if result == 1:
        bound_hwnd = hwnd
        bound_title = title
        return True, title, f"绑定成功 hwnd={hwnd} display={display_mode} force={force_result} last_error={last_error}"

    return False, title, f"绑定失败 hwnd={hwnd} display={display_mode} result={result} last_error={last_error}"


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

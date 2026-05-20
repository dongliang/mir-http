import ctypes

import win32api
import win32gui


# 查找窗口标题：遍历可见窗口并返回第一个标题匹配项。
def find_window_by_title(title_part):
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


# 获取客户区尺寸：直接从窗口读取未缩放的客户区宽高。
def get_client_size(hwnd):
    if not hwnd:
        return 0, 0

    # 客户区矩形：包含左上和右下坐标，用于计算窗口客户区大小。
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    return right - left, bottom - top


# 获取窗口标题：包装 Win32 标题读取，便于上层补充诊断信息。
def get_window_title(hwnd):
    if not hwnd:
        return ""

    return win32gui.GetWindowText(hwnd)


# 获取屏幕和 DPI 信息：用于页面调试坐标换算。
def get_screen_info():
    # 屏幕宽高：Win32 返回当前进程看到的桌面尺寸。
    width = win32api.GetSystemMetrics(0)
    height = win32api.GetSystemMetrics(1)
    # DPI 缩放：优先读取 Windows 的百分比缩放，失败时使用 100%。
    scale_percent = 100

    try:
        scale_percent = int(ctypes.windll.shcore.GetScaleFactorForDevice(0))
    except Exception:
        pass

    return {
        "width": width,
        "height": height,
        "scale_percent": scale_percent,
    }

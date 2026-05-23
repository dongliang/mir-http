import ctypes

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


# 客户区坐标转屏幕坐标：用于前台真实鼠标移动。
def client_to_screen(hwnd, x, y):
    if not hwnd:
        return 0, 0

    screen_x, screen_y = win32gui.ClientToScreen(hwnd, (int(x), int(y)))
    return int(screen_x), int(screen_y)


# 移动系统鼠标到屏幕坐标。
def move_cursor_to_screen(x, y):
    result = ctypes.windll.user32.SetCursorPos(int(x), int(y))
    return result != 0

import ctypes

import win32gui


# 不允许绑定的系统窗口标题片段。
IGNORED_WINDOW_TITLE_PARTS = [
    "文件资源管理器",
    "File Explorer",
]


# 查找窗口标题：遍历可见窗口并返回第一个标题匹配项。
def find_window_by_title(title_part):
    # 匹配结果列表：收集标题包含关键字的可见窗口。
    result = []
    title_part = str(title_part or "").strip()

    # 检查单个窗口：作为 EnumWindows 回调用于筛选标题。
    def check_window(hwnd, extra):
        if not win32gui.IsWindowVisible(hwnd):
            return True

        # 当前窗口标题：读取候选窗口标题用于关键字匹配。
        title = win32gui.GetWindowText(hwnd)

        if title_part in title and not is_ignored_window_title(title):
            result.append((hwnd, title))

        return True

    win32gui.EnumWindows(check_window, None)

    if result:
        return result[0]

    return None, ""


# 判断标题是否属于明显不该绑定的系统窗口。
def is_ignored_window_title(title):
    return any(part in str(title or "") for part in IGNORED_WINDOW_TITLE_PARTS)


# 客户区坐标转屏幕坐标：用于前台真实鼠标移动。
def client_to_screen(hwnd, x, y):
    if not hwnd:
        return 0, 0

    screen_x, screen_y = win32gui.ClientToScreen(hwnd, (int(x), int(y)))
    return int(screen_x), int(screen_y)


# 屏幕坐标转客户区坐标：用于判断真实鼠标是否在绑定窗口内。
def screen_to_client(hwnd, x, y):
    if not hwnd:
        return 0, 0

    client_x, client_y = win32gui.ScreenToClient(hwnd, (int(x), int(y)))
    return int(client_x), int(client_y)


# 获取系统真实鼠标屏幕坐标。
def get_cursor_pos():
    screen_x, screen_y = win32gui.GetCursorPos()
    return int(screen_x), int(screen_y)


# 获取虚拟桌面范围，兼容多显示器和负坐标显示器。
def get_virtual_screen_rect():
    left = ctypes.windll.user32.GetSystemMetrics(76)
    top = ctypes.windll.user32.GetSystemMetrics(77)
    width = ctypes.windll.user32.GetSystemMetrics(78)
    height = ctypes.windll.user32.GetSystemMetrics(79)
    return int(left), int(top), int(left + width - 1), int(top + height - 1)


# 移动系统鼠标到屏幕坐标。
def move_cursor_to_screen(x, y):
    result = ctypes.windll.user32.SetCursorPos(int(x), int(y))
    return result != 0

import threading
import time

import win32api
import win32con
import win32gui


# 圆环颜色：定义点击提示使用的黄色画笔颜色。
YELLOW = win32api.RGB(255, 220, 0)
# 圆环半径：控制点击提示圆环的显示大小。
RADIUS = 14
# 圆环线宽：控制点击提示圆环边线粗细。
LINE_WIDTH = 3
# 帧间隔：控制点击提示重复绘制的刷新节奏。
FRAME_INTERVAL = 0.016

# 标记锁：保护点击提示版本号的并发读写。
marker_lock = threading.Lock()
# 标记版本号：递增后可让旧的点击提示自动失效。
marker_version = 0


# 显示点击提示：在目标窗口客户区坐标闪烁黄色圆环。
def show_click(target_hwnd, x, y, duration_ms=700, scale=1.0):
    """Flash a yellow ring at a client-area click point without creating a window."""
    global marker_version

    with marker_lock:
        # 标记版本递增：让旧点击提示线程失效并标识本次提示。
        marker_version += 1
        # 当前提示版本：标识本次点击提示，防止旧线程继续绘制。
        version = marker_version

    # 绘制线程：后台重复绘制圆环直到持续时间结束。
    thread = threading.Thread(
        target=flash_ring,
        args=(target_hwnd, int(x), int(y), max(0.05, duration_ms / 1000), version),
        daemon=True,
    )
    thread.start()


# 隐藏点击提示：递增版本号使当前绘制线程停止生效。
def hide():
    global marker_version

    with marker_lock:
        # 标记版本递增：通知现有绘制线程停止继续绘制。
        marker_version += 1


# 闪烁圆环：在持续时间内按帧重绘点击提示。
def flash_ring(target_hwnd, x, y, duration_seconds, version):
    # 截止时间：控制本次点击提示最长显示多久。
    deadline = time.time() + duration_seconds

    while time.time() < deadline and is_current_marker(version):
        draw_ring(target_hwnd, x, y)
        time.sleep(FRAME_INTERVAL)


# 判断当前标记：确认绘制线程是否仍属于最新提示。
def is_current_marker(version):
    with marker_lock:
        return version == marker_version


# 绘制圆环：对外包装窗口绘制实现。
def draw_ring(target_hwnd, x, y):
    draw_ring_on_window(target_hwnd, x, y)


# 在窗口绘制圆环：获取窗口 DC 并确保释放资源。
def draw_ring_on_window(target_hwnd, x, y):
    # 窗口设备上下文：作为 Win32 绘图的目标画布。
    hdc = win32gui.GetDC(target_hwnd)

    try:
        draw_ring_on_dc(hdc, x, y)
    finally:
        win32gui.ReleaseDC(target_hwnd, hdc)


# 在 DC 绘制圆环：创建画笔并绘制空心椭圆。
def draw_ring_on_dc(hdc, x, y):
    # 黄色画笔：用于绘制点击提示圆环边线。
    pen = win32gui.CreatePen(win32con.PS_SOLID, LINE_WIDTH, YELLOW)
    # 原始画笔：保存 DC 原有画笔以便绘制后恢复。
    old_pen = win32gui.SelectObject(hdc, pen)
    # 原始画刷：保存 DC 原有画刷并切换为空心画刷。
    old_brush = win32gui.SelectObject(hdc, win32gui.GetStockObject(win32con.NULL_BRUSH))

    try:
        win32gui.Ellipse(
            hdc,
            x - RADIUS,
            y - RADIUS,
            x + RADIUS,
            y + RADIUS,
        )
    finally:
        win32gui.SelectObject(hdc, old_brush)
        win32gui.SelectObject(hdc, old_pen)
        win32gui.DeleteObject(pen)

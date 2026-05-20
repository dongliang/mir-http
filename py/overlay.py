import threading
import time

import win32api
import win32con
import win32gui


# 圆环颜色：定义点击提示使用的黄色画笔颜色。
YELLOW = win32api.RGB(255, 220, 0)
# 调试点颜色：用于怪物扫描时标记不同计算位置。
COLORS = {
    "blue": win32api.RGB(0, 120, 255),
    "red": win32api.RGB(255, 40, 40),
    "orange": win32api.RGB(255, 150, 0),
    "cyan": win32api.RGB(0, 210, 220),
    "purple": win32api.RGB(170, 70, 255),
    "yellow": YELLOW,
}
# 圆环半径：控制点击提示圆环的显示大小。
RADIUS = 14
# 调试点半径：控制怪物扫描标记点的显示大小。
POINT_RADIUS = 8
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
    draw_x, draw_y = scale_point(x, y, scale)
    thread = threading.Thread(
        target=flash_ring,
        args=(target_hwnd, draw_x, draw_y, max(0.05, duration_ms / 1000), version),
        daemon=True,
    )
    thread.start()


# 显示多个调试点：在目标窗口客户区坐标闪烁彩色小圆圈。
def show_points(target_hwnd, points, duration_ms=1500, scale=1.0):
    global marker_version

    with marker_lock:
        # 标记版本递增：让上一轮扫描点立即失效。
        marker_version += 1
        # 当前提示版本：标识本轮调试点。
        version = marker_version

    # 绘制点列表：预先换算坐标和颜色，降低绘制线程里的工作量。
    draw_points = []

    for point in points:
        draw_x, draw_y = scale_point(point.get("x", 0), point.get("y", 0), scale)
        draw_points.append({
            "x": draw_x,
            "y": draw_y,
            "color": resolve_color(point.get("color", "yellow")),
            "radius": int(point.get("radius", POINT_RADIUS)),
        })

    if not draw_points:
        return

    # 绘制线程：后台重复绘制所有点直到持续时间结束。
    thread = threading.Thread(
        target=flash_points,
        args=(target_hwnd, draw_points, max(0.05, duration_ms / 1000), version),
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


# 闪烁多个调试点：在持续时间内按帧重绘所有彩色圆圈。
def flash_points(target_hwnd, points, duration_seconds, version):
    # 截止时间：控制本轮调试点最长显示多久。
    deadline = time.time() + duration_seconds

    while time.time() < deadline and is_current_marker(version):
        draw_points_on_window(target_hwnd, points)
        time.sleep(FRAME_INTERVAL)


# 判断当前标记：确认绘制线程是否仍属于最新提示。
def is_current_marker(version):
    with marker_lock:
        return version == marker_version


# 缩放坐标：把 OP 有效坐标换成窗口 DC 使用的坐标。
def scale_point(x, y, scale):
    # 当前 Overlay 直接绘制在窗口 DC 上，沿用业务侧的有效客户区坐标。
    return int(x), int(y)


# 解析颜色：支持预设颜色名或 RGB 整数。
def resolve_color(color):
    if isinstance(color, int):
        return color

    return COLORS.get(str(color), YELLOW)


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


# 在窗口绘制多个调试点：获取窗口 DC 并确保释放资源。
def draw_points_on_window(target_hwnd, points):
    # 窗口设备上下文：作为 Win32 绘图的目标画布。
    hdc = win32gui.GetDC(target_hwnd)

    try:
        for point in points:
            draw_ring_on_dc(
                hdc,
                point["x"],
                point["y"],
                color=point["color"],
                radius=point["radius"],
            )
    finally:
        win32gui.ReleaseDC(target_hwnd, hdc)


# 在 DC 绘制圆环：创建画笔并绘制空心椭圆。
def draw_ring_on_dc(hdc, x, y, color=YELLOW, radius=RADIUS):
    # 黄色画笔：用于绘制点击提示圆环边线。
    pen = win32gui.CreatePen(win32con.PS_SOLID, LINE_WIDTH, color)
    # 原始画笔：保存 DC 原有画笔以便绘制后恢复。
    old_pen = win32gui.SelectObject(hdc, pen)
    # 原始画刷：保存 DC 原有画刷并切换为空心画刷。
    old_brush = win32gui.SelectObject(hdc, win32gui.GetStockObject(win32con.NULL_BRUSH))

    try:
        win32gui.Ellipse(
            hdc,
            x - radius,
            y - radius,
            x + radius,
            y + radius,
        )
    finally:
        win32gui.SelectObject(hdc, old_brush)
        win32gui.SelectObject(hdc, old_pen)
        win32gui.DeleteObject(pen)

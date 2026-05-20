import threading
import time

import win32api
import win32con
import win32gui


YELLOW = win32api.RGB(255, 220, 0)
RADIUS = 14
LINE_WIDTH = 3
FRAME_INTERVAL = 0.016

marker_lock = threading.Lock()
marker_version = 0


def show_click(target_hwnd, x, y, duration_ms=700, scale=1.0):
    """Flash a yellow ring at a client-area click point without creating a window."""
    global marker_version

    with marker_lock:
        marker_version += 1
        version = marker_version

    thread = threading.Thread(
        target=flash_ring,
        args=(target_hwnd, int(x), int(y), max(0.05, duration_ms / 1000), version),
        daemon=True,
    )
    thread.start()


def hide():
    global marker_version

    with marker_lock:
        marker_version += 1


def flash_ring(target_hwnd, x, y, duration_seconds, version):
    deadline = time.time() + duration_seconds

    while time.time() < deadline and is_current_marker(version):
        draw_ring(target_hwnd, x, y)
        time.sleep(FRAME_INTERVAL)


def is_current_marker(version):
    with marker_lock:
        return version == marker_version


def draw_ring(target_hwnd, x, y):
    draw_ring_on_window(target_hwnd, x, y)


def draw_ring_on_window(target_hwnd, x, y):
    hdc = win32gui.GetDC(target_hwnd)

    try:
        draw_ring_on_dc(hdc, x, y)
    finally:
        win32gui.ReleaseDC(target_hwnd, hdc)


def draw_ring_on_dc(hdc, x, y):
    pen = win32gui.CreatePen(win32con.PS_SOLID, LINE_WIDTH, YELLOW)
    old_pen = win32gui.SelectObject(hdc, pen)
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

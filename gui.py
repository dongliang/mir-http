from pathlib import Path
import platform
import tkinter as tk
from tkinter import scrolledtext

import api
import log
from dm import bind_game_window, get_dm_version, start_dm


debug_text = None
debug_menu = None
bind_label = None
map_label = None
coordinate_label = None


def run_gui(player_info, on_frame):
    global debug_text
    global debug_menu
    global bind_label
    global map_label
    global coordinate_label

    window = tk.Tk()
    window.title("Mir2Auto")
    window.geometry("760x800")

    button_area = tk.Frame(window)
    button_area.pack(fill="x", padx=12, pady=12)

    for index in range(1, 11):
        button_text = get_button_text(index)
        button = tk.Button(
            button_area,
            text=button_text,
            command=lambda number=index: on_test_button_click(number),
            height=1,
        )
        row = (index - 1) // 5
        column = (index - 1) % 5
        button.grid(row=row, column=column, sticky="ew", padx=3, pady=3)

    for column in range(5):
        button_area.columnconfigure(column, weight=1)

    bind_label = tk.Label(window, text="绑定窗口: 未绑定", anchor="w")
    bind_label.pack(fill="x", padx=16, pady=(0, 4))

    map_label = tk.Label(window, text="地图: 未知", anchor="w")
    map_label.pack(fill="x", padx=16, pady=(0, 4))

    coordinate_label = tk.Label(window, text="坐标: -:-", anchor="w")
    coordinate_label.pack(fill="x", padx=16, pady=(0, 8))

    debug_text = scrolledtext.ScrolledText(window, font=("Consolas", 11))
    debug_text.pack(fill="both", expand=True, padx=12, pady=(0, 12))
    debug_text.bind("<Control-a>", select_all_debug_text)
    debug_text.bind("<Button-3>", show_debug_menu)
    log.set_text_box(debug_text)
    log.start_log()

    debug_menu = tk.Menu(window, tearoff=0)
    debug_menu.add_command(label="复制", command=copy_debug_text)
    debug_menu.add_command(label="全选", command=select_all_debug_text)

    write_startup_debug()
    start_dm_on_startup()
    start_frame_loop(window, player_info, on_frame)
    window.mainloop()


def on_test_button_click(number):
    if number == 1:
        bind_game_window_from_button()
    elif number == 2:
        test_map_coordinate()
    else:
        log.write(f"测试按钮 {number} 被点击")


def get_button_text(number):
    if number == 1:
        return "绑定窗口"

    if number == 2:
        return "测试坐标"

    return f"测试按钮 {number}"


def bind_game_window_from_button():
    try:
        success, title, message = bind_game_window()
        log.write(message)

        if success:
            bind_label.config(text=f"绑定窗口: {title}")
        else:
            bind_label.config(text="绑定窗口: 失败")
    except Exception as error:
        log.write(f"绑定窗口异常: {error}")
        bind_label.config(text="绑定窗口: 异常")


def test_map_coordinate():
    map_name, x, y = api.get_map_coordinate()
    log.write(f"手动测试坐标: 地图={map_name} x={x} y={y}")


def test_dm_plugin():
    try:
        version = get_dm_version()
        log.write(f"大漠版本: {version}")
    except Exception as error:
        log.write(f"大漠测试失败: {error}")


def write_startup_debug():
    project_dir = Path(__file__).resolve().parent
    dm_path = project_dir / "dm.dll"

    log.write("程序启动")
    log.write(f"项目目录: {project_dir}")
    log.write(f"Python 位数: {platform.architecture()[0]}")
    log.write(f"dm.dll 存在: {dm_path.exists()}")


def copy_debug_text():
    debug_text.event_generate("<<Copy>>")


def select_all_debug_text(event=None):
    debug_text.tag_add("sel", "1.0", "end")
    return "break"


def show_debug_menu(event):
    debug_menu.tk_popup(event.x_root, event.y_root)


def start_dm_on_startup():
    log.write("开始初始化大漠")

    try:
        success, version, message = start_dm()
        log.write(f"大漠版本: {version}")
        log.write(message)

        if success:
            log.write("大漠初始化成功")
        else:
            log.write("大漠初始化失败")
    except Exception as error:
        log.write(f"大漠初始化异常: {error}")


def start_frame_loop(window, player_info, on_frame):
    on_frame()
    refresh_player_labels(player_info)
    window.after(100, lambda: start_frame_loop(window, player_info, on_frame))


def refresh_player_labels(player_info):
    map_label.config(text=f"地图: {player_info['map_name']}")
    coordinate_label.config(text=f"坐标: {player_info['x']}:{player_info['y']}")

import atexit
import ctypes
import os
import socket
import subprocess
import sys
import threading
import time

import api
import httpserver
import log
import player
from state import battle
from state import getitem
from state import idle
from state import move_to_next_patrol_point
from state import select_monster


# 当前玩家状态：保存页面和后台循环共享的地图坐标信息。
current_player = player.create_player()
# 应用设置：集中保存运行时可切换的界面和行为开关。
app_settings = api.create_default_app_settings()
# 当前加载的大地图状态：保存地图图片、地图矩形和最大逻辑坐标。
current_map = {}
# 当前识别到的地图名称：地图名变化时自动加载已保存地图。
current_map_name = {
    "name": "",
    "account": "",
}
# 当前地图巡逻点：保存网页确认后的逻辑坐标列表。
patrol_points = []
# 巡逻运行状态：记录下一次巡逻移动前的当前索引。
patrol_state = {
    "index": -1,
    "source": "",
    "path": "",
}
# 巡逻控制：由页面按钮切换，打开后 idle 会进入巡逻移动状态。
patrol_control = {
    "enabled": False,
}
# 战斗控制：由页面按钮切换，状态机会按它决定是否进入战斗。
battle_control = {
    "enabled": False,
}
# 战斗运行状态：保存连续无怪、当前战斗目标和计时信息。
battle_runtime_state = {
    "no_monster_count": 0,
    "last_no_monster_reason": "",
    "current_target": {},
    "battle_started_at": 0.0,
    "battle_ends_at": 0.0,
    "last_message": "",
}
# 自动加血状态：独立于状态机，记录检测节奏、最近血量和低血触发锁。
auto_heal_state = {
    "last_checked_at": 0.0,
    "last_hp_percent": "",
    "triggered_low": False,
    "last_message": "",
}
# 宝宝加血状态：由找怪流程识别当前账号召唤物时更新。
pet_heal_state = {
    "last_healed_at": 0.0,
    "last_hp_percent": "",
    "last_target": {},
    "last_message": "",
}
# idle 卡住保护状态：跨 idle/battle 保存坐标停留计时。
idle_stuck_state = {
    "last_coordinate": None,
    "stationary_started_at": 0.0,
    "stationary_seconds": 0,
    "last_message": "",
}
# 当前状态：name 保存状态名，data 保存该状态自己的运行数据。
current_state = {
    "name": "idle",
    "data": {},
}
# 状态模块表：状态名到模块的映射，供每帧调度。
state_modules = {
    "idle": idle,
    "selectMonster": select_monster,
    "battle": battle,
    "getitem": getitem,
    "move_to_next_patrol_point": move_to_next_patrol_point,
}
# 游戏数据：app.py 持有的共享运行数据，传给状态模块读取和更新。
game_data = {
    "player": current_player,
    "settings": app_settings,
    "current_map": current_map,
    "patrol_points": patrol_points,
    "patrol_state": patrol_state,
    "patrol_control": patrol_control,
    "battle_control": battle_control,
    "battle_runtime_state": battle_runtime_state,
    "auto_heal_state": auto_heal_state,
    "pet_heal_state": pet_heal_state,
    "idle_stuck_state": idle_stuck_state,
}
# 停止事件：通知后台刷新循环在程序退出时结束。
stop_event = threading.Event()
restart_lock = threading.Lock()
restart_requested = False
atexit.register(api.stop_map_corner_hotkey)
atexit.register(stop_event.set)


# 主入口：初始化日志、OP 绑定能力、后台刷新循环和 HTTP 服务。
def main() -> None:
    api.configure_initial_output_dir()
    log.use_run_dir(api.get_output_dir())
    log.start_log()
    log.write("程序启动: HTTP 服务模式")
    apply_app_settings()
    load_text_configs()
    start_op()
    start_update_loop()
    httpserver.run_server(
        current_player,
        update_frame,
        app_settings,
        current_map,
        patrol_points,
        patrol_state,
        patrol_control,
        battle_control,
        current_state,
        auto_heal_state,
        pet_heal_state,
        idle_stuck_state,
        battle_runtime_state,
        game_data,
        restart_app,
    )


# 等待旧进程退出：重启子进程启动时先等旧进程释放当前 HTTP 端口。
def wait_for_restart_parent():
    parent_pid_text = os.environ.pop("MIR2AUTO_RESTART_PARENT_PID", "").strip()

    if not parent_pid_text.isdigit():
        return

    parent_pid = int(parent_pid_text)
    deadline = time.time() + 30

    while time.time() < deadline:
        if not is_process_running(parent_pid) and is_server_port_free(httpserver.SERVER_PORT):
            return

        time.sleep(0.2)


# 判断进程是否仍在运行：仅用于 Windows 下的重启等待。
def is_process_running(pid):
    if pid <= 0 or pid == os.getpid():
        return False

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, int(pid))

    if not handle:
        return False

    exit_code = ctypes.c_ulong()

    try:
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False

        return exit_code.value == 259
    finally:
        kernel32.CloseHandle(handle)


# 判断 HTTP 端口是否空闲：新进程接管端口前避免和旧进程抢占。
def is_server_port_free(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        sock.bind((httpserver.SERVER_HOST, int(port)))
        return True
    except OSError:
        return False
    finally:
        sock.close()


# 网页触发的程序重启：启动新进程并安排当前进程退出。
def restart_app():
    global restart_requested

    with restart_lock:
        if restart_requested:
            return {
                "success": True,
                "message": "程序正在重启，请稍后刷新页面",
            }

        try:
            child = start_restart_child()
        except Exception as error:
            return {
                "success": False,
                "message": f"启动重启子进程失败: {error}",
            }

        restart_requested = True

    thread = threading.Thread(target=exit_after_restart_response, daemon=True)
    thread.start()

    return {
        "success": True,
        "message": f"程序正在重启，新进程 PID={child.pid}",
    }


# 启动接管用的新 Python 进程。
def start_restart_child():
    env = os.environ.copy()
    env["MIR2AUTO_RESTART_PARENT_PID"] = str(os.getpid())
    env["MIR2AUTO_HTTP_PORT"] = str(httpserver.SERVER_PORT)

    return subprocess.Popen(
        [sys.executable, str(api.base_dir / "py" / "app.py")],
        cwd=str(api.base_dir),
        env=env,
    )


# 给 HTTP 响应留出返回时间，然后清理并退出当前进程。
def exit_after_restart_response():
    time.sleep(0.5)
    cleanup_before_exit()
    os._exit(0)


# 退出前清理：停止后台循环、快捷键和当前 OP 绑定。
def cleanup_before_exit():
    stop_event.set()

    try:
        api.stop_map_corner_hotkey()
    except Exception as error:
        log.write(f"停止地图角点快捷键异常: {error}")

    try:
        result = api.unbind_window()
        log.write(result.get("message", ""))
    except Exception as error:
        log.write(f"重启前解绑窗口异常: {error}")


# 刷新一帧：读取当前地图坐标并写回玩家状态。
def update_frame():
    # 当前地图坐标：承接 OCR 识别出的地图名和 x/y 坐标。
    map_name, x, y = api.get_map_coordinate()
    player.set_map_coordinate(current_player, map_name, x, y)
    update_current_map(map_name)
    update_auto_heal()
    update_current_state()


# 更新当前地图：地图名变化时只加载已保存的 maps/<地图名>/image.png。
def update_current_map(map_name):
    name = str(map_name or "").strip()
    account = api.get_current_account()

    if not name:
        return

    if name == current_map_name.get("name", "") and account == current_map_name.get("account", ""):
        return

    current_map_name["name"] = name
    current_map_name["account"] = account
    current_map.clear()
    patrol_points.clear()
    patrol_state["index"] = -1
    patrol_state["source"] = ""
    patrol_state["path"] = ""
    patrol_control["enabled"] = False

    result = api.load_saved_map(name)

    if not result["success"]:
        log.write(result["message"])
        return

    current_map.update(result["map"])

    try:
        patrol_result = api.load_patrol_points_for_map(name, current_map)
    except Exception as error:
        patrol_result = {
            "success": False,
            "points": [],
            "message": f"读取巡逻点异常: {error}",
        }

    if patrol_result["success"]:
        patrol_points[:] = patrol_result.get("points", [])
        patrol_state["source"] = patrol_result.get("source", "")
        patrol_state["path"] = patrol_result.get("path", "")

    log.write(f"{result['message']}；{patrol_result['message']}")


# 更新自动加血：独立于状态机，每帧按设置判断是否需要检测。
def update_auto_heal():
    result = api.update_auto_heal(app_settings, auto_heal_state) or {}
    message = result.get("message", "")

    if message:
        log.write(message)


# 更新当前状态：调用状态模块并处理状态切换。
def update_current_state():
    state_name = current_state.get("name", "idle")
    state_module = state_modules.get(state_name, idle)
    stuck_result = None

    if state_name != "move_to_next_patrol_point":
        stuck_result = idle.update_idle_stuck(game_data)

    if stuck_result:
        handle_state_result(stuck_result)
        return

    # 状态结果：包含可选的下一状态和日志消息。
    result = state_module.update_frame(game_data, current_state["data"]) or {}
    handle_state_result(result)


# 处理状态返回：写日志并按需切换状态。
def handle_state_result(result):
    message = result.get("message", "")

    for entry in result.get("logs", []):
        if entry:
            log.write(entry)

    if message:
        log.write(message)

    next_state = result.get("state")

    if next_state:
        switch_state(next_state, result.get("data"))


# 切换状态：重置状态私有数据并写入切换日志。
def switch_state(next_state, next_data=None):
    if next_state not in state_modules:
        log.write(f"未知状态 {next_state}，回到 idle")
        next_state = "idle"

    old_state = current_state.get("name", "idle")

    if old_state == next_state:
        return

    current_state["name"] = next_state
    current_state["data"] = next_data if isinstance(next_data, dict) else {}
    log.write(f"状态1切换: {old_state} -> {next_state}")


# 启动刷新循环：创建后台线程定时更新坐标状态。
def start_update_loop():
    # 刷新线程：以守护线程运行后台坐标刷新逻辑。
    thread = threading.Thread(target=update_loop, daemon=True)
    thread.start()


# 应用运行设置：把内存中的应用设置同步到底层模块。
def apply_app_settings():
    api.apply_app_settings(app_settings)


# 加载 TXT 运行配置：启动时读取 txt/ 下的怪物和物品清单、颜色。
def load_text_configs():
    result = api.load_text_configs()
    log.write(result.get("message", ""))


# 后台刷新循环：按固定节奏刷新玩家坐标并控制退出。
def update_loop():
    while not stop_event.is_set():
        # 本轮开始时间：用于控制刷新间隔并补偿处理耗时。
        started = time.time()

        try:
            update_frame()
        # 刷新异常对象：记录后台坐标刷新失败的具体原因。
        except Exception as error:
            log.write(f"后台刷新坐标异常: {error}")

        # 本轮耗时：计算下一次刷新前还需要等待多久。
        elapsed = time.time() - started
        stop_event.wait(max(0.0, 0.5 - elapsed))


# 启动 OP：初始化 OP 自动化对象并记录初始化结果。
def start_op():
    log.write("开始初始化 OP")

    # OP 初始化结果：包含成功状态、版本号和说明消息。
    result = api.start_op()
    success = result["success"]
    version = result["version"]
    message = result["message"]

    if version:
        log.write(f"OP 版本: {version}")

    log.write(message)

    if success:
        log.write("OP 初始化成功")
        return True

    log.write("OP 初始化失败")
    return False


if __name__ == "__main__":
    wait_for_restart_parent()
    main()

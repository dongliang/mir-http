import atexit
import threading
import time

import api
import httpserver
import log
import move_to_next_patrol_point
import player
from state import battle
from state import find_monster
from state import getitem
from state import idle


# 当前玩家状态：保存页面和后台循环共享的地图坐标信息。
current_player = player.create_player()
# 应用设置：集中保存运行时可切换的界面和行为开关。
app_settings = {
    "map_corner_hotkey": api.MAP_CORNER_HOTKEY_DEFAULT,
    "auto_heal_enabled": False,
    "auto_heal_threshold_percent": 50,
    "auto_heal_interval_ms": 1000,
    "idle_stuck_enabled": True,
    "idle_stuck_seconds": 30,
    "monster_name_debug_enabled": False,
    "getitem_enabled": False,
    "getitem_step_wait_ms": api.GETITEM_DEFAULT_STEP_WAIT_MS,
    "no_monster_scan_limit": api.NO_MONSTER_SCAN_LIMIT_DEFAULT,
}
# 当前绑定的大地图状态：保存地图图片、地图矩形和最大逻辑坐标。
current_map = {}
# 当前地图巡逻点：保存网页确认后的逻辑坐标列表。
patrol_points = []
# 巡逻运行状态：记录下一次巡逻移动前的当前索引。
patrol_state = {
    "index": -1,
}
# 巡逻控制：由页面按钮切换，打开后 idle 会进入巡逻移动状态。
patrol_control = {
    "enabled": False,
}
# 战斗控制：由页面按钮切换，状态机会按它决定是否进入战斗。
battle_control = {
    "enabled": False,
}
# 战斗运行状态：保存连续无怪、锁定目标和临时忽略目标。
battle_runtime_state = {
    "no_monster_count": 0,
    "last_no_monster_reason": "",
    "ignored_targets": [],
    "last_target": {},
    "last_message": "",
}
# 自动加血状态：独立于状态机，记录检测节奏、最近血量和低血触发锁。
auto_heal_state = {
    "last_checked_at": 0.0,
    "last_hp_percent": "",
    "triggered_low": False,
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
    "find_monster": find_monster,
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
    "idle_stuck_state": idle_stuck_state,
}
# 停止事件：通知后台刷新循环在程序退出时结束。
stop_event = threading.Event()
atexit.register(api.stop_map_corner_hotkey)
atexit.register(stop_event.set)


# 主入口：初始化日志、OP 绑定能力、后台刷新循环和 HTTP 服务。
def main() -> None:
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
        idle_stuck_state,
        battle_runtime_state,
        game_data,
    )


# 刷新一帧：读取当前地图坐标并写回玩家状态。
def update_frame():
    # 当前地图坐标：承接 OCR 识别出的地图名和 x/y 坐标。
    map_name, x, y = api.get_map_coordinate()
    player.set_map_coordinate(current_player, map_name, x, y)
    update_auto_heal()
    update_current_state()


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
    log.write(f"状态切换: {old_state} -> {next_state}")


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
    main()

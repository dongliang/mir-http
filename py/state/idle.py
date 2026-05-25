import time

import api


# idle 卡住保护默认时间：页面设置缺失时使用。
IDLE_STUCK_DEFAULT_SECONDS = 30


# 空闲状态：先尝试捡物品，最后按开关进入找怪或巡逻移动状态。
def update_frame(game_data, state_data):
    battle_control = game_data["battle_control"]
    patrol_control = game_data["patrol_control"]

    getitem_result = api.should_enter_getitem(game_data)

    if getitem_result.get("enter", False):
        api.reset_no_monster_count(game_data.get("battle_runtime_state"), "进入捡取物品，清空无怪次数")
        return {
            "state": "getitem",
            "message": getitem_result.get("message", "发现可捡物品，进入捡取物品状态"),
        }

    if battle_control.get("enabled", False):
        return {
            "state": "find_monster",
            "message": "战斗开关已开启，进入找怪状态",
        }

    if patrol_control.get("enabled", False):
        return {
            "state": "move_to_next_patrol_point",
            "message": "巡逻开关已开启，进入下一个巡逻点移动状态",
        }

    return {}


# 更新 idle 卡住保护：同一地图坐标停留超过设置秒数时跳到下一个巡逻点。
def update_idle_stuck(game_data):
    settings = game_data["settings"]
    stuck_state = game_data.get("idle_stuck_state")

    if stuck_state is None:
        return None

    coordinate = get_player_coordinate(game_data)

    if coordinate is None:
        stuck_state["last_message"] = "卡住跳点等待有效坐标"
        return None

    now = time.time()
    last_coordinate = stuck_state.get("last_coordinate")

    if coordinate != last_coordinate:
        stuck_state["last_coordinate"] = coordinate
        stuck_state["stationary_started_at"] = now
        stuck_state["stationary_seconds"] = 0
        stuck_state["last_message"] = ""
        return None

    started_at = float(stuck_state.get("stationary_started_at") or now)
    stationary_seconds = max(0, int(now - started_at))
    stuck_state["stationary_seconds"] = stationary_seconds

    if not settings.get("idle_stuck_enabled", True):
        return None

    if not is_auto_flow_enabled(game_data):
        return None

    threshold_seconds = get_idle_stuck_seconds(settings)

    if stationary_seconds < threshold_seconds:
        return None

    if not game_data.get("current_map"):
        stuck_state["last_message"] = f"卡住跳点已达到 {stationary_seconds} 秒，但还没有加载地图"
        return None

    if not game_data.get("patrol_points"):
        stuck_state["last_message"] = f"卡住跳点已达到 {stationary_seconds} 秒，但还没有保存巡逻点"
        return None

    stuck_state["last_coordinate"] = None
    stuck_state["stationary_started_at"] = now
    stuck_state["stationary_seconds"] = 0
    api.reset_battle_runtime(game_data.get("battle_runtime_state"), "卡住跳点触发，清空战斗运行状态")
    map_name, x, y = coordinate
    message = f"玩家坐标 {map_name} {x}:{y} 连续 {stationary_seconds} 秒未变化，进入下一个巡逻点"
    stuck_state["last_message"] = message
    return {
        "state": "move_to_next_patrol_point",
        "message": message,
    }


# 获取玩家地图坐标：包含地图名，避免不同地图相同数字坐标误判。
def get_player_coordinate(game_data):
    player = game_data["player"]

    try:
        x = int(player.get("x"))
        y = int(player.get("y"))
    except (TypeError, ValueError):
        return None

    return str(player.get("map_name") or "未知"), x, y


# 判断当前是否处于需要自动流程兜底的状态。
def is_auto_flow_enabled(game_data):
    return (
        game_data["battle_control"].get("enabled", False)
        or game_data["patrol_control"].get("enabled", False)
    )


# 读取卡住保护秒数：设置接口会规整，这里保留兜底。
def get_idle_stuck_seconds(settings):
    try:
        seconds = int(float(settings.get("idle_stuck_seconds", IDLE_STUCK_DEFAULT_SECONDS)))
    except (TypeError, ValueError):
        seconds = IDLE_STUCK_DEFAULT_SECONDS

    return max(5, min(600, seconds))

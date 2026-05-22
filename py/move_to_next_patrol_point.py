import time

import api


# 到达判断时间：玩家逻辑坐标连续不变达到该时长后认为已到达。
ARRIVE_STATIONARY_SECONDS = 2.0


# 巡逻移动状态：移动到下一个巡逻点，并等待玩家坐标稳定。
def update_frame(game_data, state_data):
    if not game_data["battle_control"].get("enabled", False):
        return {
            "state": "idle",
            "message": "战斗开关已关闭，巡逻移动回到 idle",
        }

    if not state_data.get("move_started"):
        result = move_once(game_data)

        if not result.get("success"):
            return {
                "state": "idle",
                "message": f"巡逻移动失败，回到 idle: {result.get('message', '')}",
            }

        now = time.time()
        state_data["move_started"] = True
        state_data["move_started_at"] = now
        state_data["last_coordinate"] = get_player_coordinate(game_data)
        state_data["stationary_started_at"] = now
        return {
            "message": result.get("message", ""),
        }

    coordinate = get_player_coordinate(game_data)

    if coordinate is None:
        return {}

    now = time.time()
    last_coordinate = state_data.get("last_coordinate")

    if coordinate != last_coordinate:
        state_data["last_coordinate"] = coordinate
        state_data["stationary_started_at"] = now
        return {}

    stationary_started_at = state_data.get("stationary_started_at", now)

    if now - stationary_started_at >= ARRIVE_STATIONARY_SECONDS:
        return {
            "state": "idle",
            "message": f"玩家坐标 {coordinate[0]}:{coordinate[1]} 连续 {ARRIVE_STATIONARY_SECONDS:g} 秒未变化，回到 idle",
        }

    return {}


# 移动到下一个巡逻点：供自动状态和手动 HTTP 接口复用。
def move_once(game_data):
    current_map = game_data["current_map"]
    patrol_points = game_data["patrol_points"]
    patrol_state = game_data["patrol_state"]
    settings = game_data["settings"]

    if not current_map:
        return {
            "success": False,
            "message": "还没有绑定地图",
        }

    if not patrol_points:
        return {
            "success": False,
            "message": "还没有保存巡逻点",
        }

    current_index = int(patrol_state.get("index", -1))
    next_index = (current_index + 1) % len(patrol_points)
    point = patrol_points[next_index]
    move = api.move_to_logic_point(point, current_map, settings.get("overlay_enabled", True))

    if move.get("success"):
        patrol_state["index"] = next_index

    return {
        "success": move.get("success", False),
        "point": point,
        "move": move,
        "index": next_index,
        "message": f"巡逻点 index={next_index} {move.get('message', '')}",
    }


# 获取玩家逻辑坐标：坐标无效时返回 None。
def get_player_coordinate(game_data):
    player = game_data["player"]

    try:
        return int(player.get("x")), int(player.get("y"))
    except (TypeError, ValueError):
        return None

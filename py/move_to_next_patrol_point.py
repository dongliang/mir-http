import time

import api


# 到达判断时间：玩家逻辑坐标连续不变达到该时长后认为已到达。
ARRIVE_STATIONARY_SECONDS = 2.0


# 巡逻移动状态：移动到下一个巡逻点，并等待玩家坐标稳定。
def update_frame(game_data, state_data):
    battle_enabled = game_data["battle_control"].get("enabled", False)
    patrol_enabled = game_data["patrol_control"].get("enabled", False)

    if not battle_enabled and not patrol_enabled:
        return {
            "state": "idle",
            "message": "战斗和巡逻开关均已关闭，巡逻移动回到 idle",
        }

    if not state_data.get("move_started"):
        api.reset_battle_runtime(game_data.get("battle_runtime_state"), "开始移动到下一个巡逻点")
        result = move_once(game_data, commit_index=False)

        if not result.get("success"):
            return {
                "state": "idle",
                "message": f"巡逻移动失败，回到 idle: {result.get('message', '')}",
            }

        now = time.time()
        state_data["move_started"] = True
        state_data["move_started_at"] = now
        state_data["target_index"] = result.get("index", -1)
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
        target_index = commit_target_index(game_data, state_data.get("target_index", -1))
        return {
            "state": "idle",
            "message": (
                f"玩家坐标 {coordinate[0]}:{coordinate[1]} 连续 {ARRIVE_STATIONARY_SECONDS:g} 秒未变化，"
                f"巡逻点 index={target_index} 已完成，回到 idle"
            ),
        }

    return {}


# 移动到下一个巡逻点：供自动状态和手动 HTTP 接口复用。
def move_once(game_data, commit_index=True):
    current_map = game_data["current_map"]
    patrol_points = game_data["patrol_points"]
    patrol_state = game_data["patrol_state"]

    if not current_map:
        return {
            "success": False,
            "message": "还没有加载地图",
        }

    if not patrol_points:
        return {
            "success": False,
            "message": "还没有保存巡逻点",
        }

    current_index = int(patrol_state.get("index", -1))
    next_index = (current_index + 1) % len(patrol_points)
    point = patrol_points[next_index]
    move = api.move_to_logic_point(point, current_map)

    if move.get("success") and commit_index:
        commit_target_index(game_data, next_index)
        api.reset_battle_runtime(game_data.get("battle_runtime_state"), "手动移动到下一个巡逻点")

    return {
        "success": move.get("success", False),
        "point": point,
        "move": move,
        "index": next_index,
        "message": f"巡逻点 index={next_index} {move.get('message', '')}",
    }


# 选中指定巡逻点：只更新当前 index，不执行移动。
def select_index(game_data, target_index):
    valid = validate_patrol_index(game_data, target_index)

    if not valid["success"]:
        return valid

    index = commit_target_index(game_data, valid["index"])
    return {
        "success": True,
        "point": valid["point"],
        "index": index,
        "message": f"已选中巡逻点 index={index}",
    }


# 移动到当前巡逻点：当前 index 必须已经存在。
def move_current(game_data):
    patrol_state = game_data["patrol_state"]

    try:
        target_index = int(patrol_state.get("index", -1))
    except (TypeError, ValueError):
        target_index = -1

    if target_index < 0:
        return {
            "success": False,
            "message": "不存在当前巡逻点",
        }

    return move_to_index(game_data, target_index)


# 移动到指定巡逻点。
def move_to_index(game_data, target_index, commit_index=True):
    current_map = game_data["current_map"]

    if not current_map:
        return {
            "success": False,
            "message": "还没有加载地图",
        }

    valid = validate_patrol_index(game_data, target_index)

    if not valid["success"]:
        return valid

    index = valid["index"]
    point = valid["point"]
    move = api.move_to_logic_point(point, current_map)

    if move.get("success") and commit_index:
        commit_target_index(game_data, index)
        api.reset_battle_runtime(game_data.get("battle_runtime_state"), "手动移动到指定巡逻点")

    return {
        "success": move.get("success", False),
        "point": point,
        "move": move,
        "index": index,
        "message": f"巡逻点 index={index} {move.get('message', '')}",
    }


# 校验巡逻点索引并返回对应点。
def validate_patrol_index(game_data, target_index):
    patrol_points = game_data["patrol_points"]

    if not patrol_points:
        return {
            "success": False,
            "message": "还没有保存巡逻点",
        }

    try:
        index = int(target_index)
    except (TypeError, ValueError):
        return {
            "success": False,
            "message": f"巡逻点 index 无效: {target_index}",
        }

    if index < 0 or index >= len(patrol_points):
        return {
            "success": False,
            "message": f"巡逻点 index 不存在: {index}",
        }

    return {
        "success": True,
        "index": index,
        "point": patrol_points[index],
    }


# 提交已完成的巡逻点索引：自动巡逻在到达后调用，手动移动可立即调用。
def commit_target_index(game_data, target_index):
    patrol_points = game_data["patrol_points"]
    patrol_state = game_data["patrol_state"]

    try:
        index = int(target_index)
    except (TypeError, ValueError):
        index = -1

    if patrol_points:
        index = max(0, min(index, len(patrol_points) - 1))
    else:
        index = -1

    patrol_state["index"] = index
    return index


# 获取玩家逻辑坐标：坐标无效时返回 None。
def get_player_coordinate(game_data):
    player = game_data["player"]

    try:
        return int(player.get("x")), int(player.get("y"))
    except (TypeError, ValueError):
        return None

import time

import api


# 到达判断时间：玩家逻辑坐标连续不变达到该时长后认为已到达。
ARRIVE_STATIONARY_SECONDS = 2.0
# 边走边打：点击地图开始移动后等待 2 秒，再每秒扫描一次附近血条。
FIGHT_WHILE_MOVING_START_DELAY_SECONDS = 2.0
FIGHT_WHILE_MOVING_SCAN_INTERVAL_SECONDS = 1.0
FIGHT_WHILE_MOVING_BLOOD_BAR_LIMIT = 2


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
        state_data["next_walk_fight_scan_at"] = now + FIGHT_WHILE_MOVING_START_DELAY_SECONDS
        return {
            "message": result.get("message", ""),
        }

    fight_while_moving_result = update_fight_while_moving(game_data, state_data)

    if fight_while_moving_result:
        return fight_while_moving_result

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

    cancel_click = api.click_client_top_left()

    if not cancel_click.get("success", False):
        return {
            "success": False,
            "point": point,
            "index": next_index,
            "cancel_click": cancel_click,
            "message": f"取消当前攻击失败: {cancel_click.get('message', '')}",
        }

    move = api.move_to_logic_point(point, current_map)

    if move.get("success") and commit_index:
        commit_target_index(game_data, next_index)
        api.reset_battle_runtime(game_data.get("battle_runtime_state"), "手动移动到下一个巡逻点")

    return {
        "success": move.get("success", False),
        "point": point,
        "move": move,
        "cancel_click": cancel_click,
        "index": next_index,
        "message": f"巡逻点 index={next_index} {move.get('message', '')}",
    }


# 按玩家当前逻辑坐标选中最近巡逻点：只更新 index，不执行移动。
def select_nearest_to_player(game_data):
    if not game_data.get("current_map"):
        return {
            "success": False,
            "message": "最近巡逻点未设置: 还没有加载地图",
        }

    patrol_points = game_data["patrol_points"]

    if not patrol_points:
        return {
            "success": False,
            "message": "最近巡逻点未设置: 还没有保存巡逻点",
        }

    player = game_data.get("player", {})

    try:
        player_logic = {
            "x": int(player.get("x")),
            "y": int(player.get("y")),
        }
    except (TypeError, ValueError):
        return {
            "success": False,
            "message": "最近巡逻点未设置: 玩家坐标无效",
        }

    nearest = None

    for index, point in enumerate(patrol_points):
        distance = api.get_logic_distance(player_logic, point)
        item = {
            "index": index,
            "point": point,
            "distance": distance,
        }

        if nearest is None or (distance, index) < (nearest["distance"], nearest["index"]):
            nearest = item

    if nearest is None or nearest["distance"] >= 999999:
        return {
            "success": False,
            "message": "最近巡逻点未设置: 巡逻点坐标无效",
        }

    index = commit_target_index(game_data, nearest["index"])
    point = nearest["point"]
    return {
        "success": True,
        "point": point,
        "index": index,
        "distance": nearest["distance"],
        "message": (
            f"最近巡逻点 index={index} "
            f"logic={int(point.get('x'))}:{int(point.get('y'))} "
            f"distance={nearest['distance']}"
        ),
    }


# 边走边打扫描：发现附近血条超过阈值时取消移动，并让 idle 重新找怪。
def update_fight_while_moving(game_data, state_data):
    if not should_fight_while_moving(game_data):
        return None

    now = time.time()
    next_scan_at = float(state_data.get("next_walk_fight_scan_at") or 0)

    if next_scan_at <= 0:
        started_at = float(state_data.get("move_started_at") or now)
        state_data["next_walk_fight_scan_at"] = started_at + FIGHT_WHILE_MOVING_START_DELAY_SECONDS
        return None

    if now < next_scan_at:
        return None

    state_data["next_walk_fight_scan_at"] = now + FIGHT_WHILE_MOVING_SCAN_INTERVAL_SECONDS
    scan = api.findMiddleMonsterBloodBars(game_data.get("player", {}))

    if not scan.get("success", False):
        return None

    monsters = list(scan.get("monsters", []))

    if len(monsters) <= FIGHT_WHILE_MOVING_BLOOD_BAR_LIMIT:
        return None

    stop_click = api.click_player_foot_point()
    return {
        "state": "idle",
        "message": (
            f"边走边打触发，附近血条 {len(monsters)} 个，取消移动回到 idle: "
            f"{stop_click.get('message', '')}"
        ),
    }


# 判断本次巡逻移动是否启用边走边打。
def should_fight_while_moving(game_data):
    settings = game_data.get("settings", {})
    return (
        bool(settings.get("fight_while_moving_enabled", False))
        and bool(game_data["battle_control"].get("enabled", False))
    )


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

import time

import api


# 捡取物品状态：一次只追踪一个物品，点一下走一步，直到该目标消失。
def update_frame(game_data, state_data):
    settings = game_data.get("settings", {})
    manual_test = bool(state_data.get("manual_test", False))

    if not manual_test and not settings.get("getitem_enabled", False):
        message = "捡取物品开关已关闭，回到 idle"
        api.set_getitem_runtime_status(message=message, target={})
        return {
            "state": "idle",
            "message": message,
        }

    if not manual_test and not is_auto_flow_enabled(game_data):
        message = "战斗和巡逻开关均已关闭，捡取物品回到 idle"
        api.set_getitem_runtime_status(message=message, target={})
        return {
            "state": "idle",
            "message": message,
        }

    reset_idle_stuck_state(game_data)

    now = time.time()
    next_action_at = float(state_data.get("next_action_at") or 0.0)

    if next_action_at and now < next_action_at:
        return {}

    safety = api.check_getitem_safety()

    if not safety.get("success", False):
        message = f"捡取安全检测失败，回到 idle: {safety.get('message', '')}"
        api.set_getitem_runtime_status(message=message)
        return {
            "state": "idle",
            "message": message,
        }

    if not safety.get("safe", True):
        message = safety.get("message", "附近有清单内怪物，捡取物品回到 idle")
        api.set_getitem_runtime_status(message=message, target=safety.get("danger", {}))
        return {
            "state": "idle",
            "logs": safety.get("logs", []),
            "message": message,
        }

    player_info = game_data.get("player", {})
    target = state_data.get("target") or {}

    if target and not api.has_getitem_target_logic(target):
        target = {}
        state_data["target"] = {}

    picked_message = ""
    selected = target

    if target and api.is_getitem_target_reached(target, player_info):
        scan = api.scan_getitems(player_info)

        if not scan.get("success", False):
            message = f"捡取物品复查失败，回到 idle: {scan.get('message', '')}"
            api.set_getitem_runtime_status(message=message, target=target)
            return {
                "state": "idle",
                "message": message,
            }

        items = scan.get("items", [])
        selected = api.find_same_keyword_getitem_target(items, target)

        if selected is None:
            picked_message = f"物品已消失，认为已捡取 target={api.format_getitem_target(target)}"
            state_data["target"] = {}
            selected = api.choose_getitem_target(items)
        else:
            picked_message = f"物品仍存在，重新识别 target={api.format_getitem_target(selected)}"

    if not selected and not picked_message:
        scan = api.scan_getitems(player_info)

        if not scan.get("success", False):
            message = f"捡取物品扫描失败，回到 idle: {scan.get('message', '')}"
            api.set_getitem_runtime_status(message=message)
            return {
                "state": "idle",
                "message": message,
            }

        items = scan.get("items", [])
        selected = api.choose_getitem_target(items)

    if selected is None:
        message = "可玩区域可捡物品已处理完，回到 idle"

        if picked_message:
            message = f"{picked_message}；{message}"

        api.set_getitem_runtime_status(message=message, target={})
        return {
            "state": "idle",
            "message": message,
        }

    wait_ms = api.get_getitem_step_wait_ms(settings)

    if api.is_getitem_target_reached(selected, player_info):
        state_data["target"] = selected
        state_data["next_action_at"] = time.time() + wait_ms / 1000
        message = (
            f"{picked_message + '；' if picked_message else ''}"
            f"已到达物品逻辑坐标，等待拾取刷新 target={api.format_getitem_target(selected)} "
            f"wait={wait_ms}ms"
        )
        api.set_getitem_runtime_status(message=message, target=selected)
        return {
            "logs": [picked_message] if picked_message else [],
            "message": message,
        }

    move = api.move_getitem_toward_target(selected, state_data.get("last_direction", ""), player_info)

    if not move.get("success", False):
        message = f"捡取物品移动失败，回到 idle: {move.get('message', '')}"
        api.set_getitem_runtime_status(message=message, target=selected)
        return {
            "state": "idle",
            "message": message,
        }

    selected["move"] = {
        "direction": move.get("direction", ""),
        "player": move.get("player", {}),
        "item": move.get("item", {}),
        "target_source": move.get("target_source", ""),
        "target_logic": move.get("target_logic", {}),
        "click": {
            "x": move.get("move", {}).get("click_x", 0),
            "y": move.get("move", {}).get("click_y", 0),
        },
    }
    state_data["target"] = selected
    state_data["last_direction"] = move.get("direction", "")
    state_data["next_action_at"] = time.time() + wait_ms / 1000
    message = (
        f"捡取物品移动 target={api.format_getitem_target(selected)} "
        f"direction={move.get('direction', '')} wait={wait_ms}ms {move.get('message', '')}"
    )
    api.set_getitem_runtime_status(message=message, target=selected)

    logs = []

    if picked_message:
        logs.append(picked_message)

    return {
        "logs": logs,
        "message": message,
    }


# 判断当前是否有自动流程在运行。
def is_auto_flow_enabled(game_data):
    return (
        game_data.get("battle_control", {}).get("enabled", False)
        or game_data.get("patrol_control", {}).get("enabled", False)
    )


# 捡取期间重置 idle 卡住保护，避免走向物品时被误判卡住。
def reset_idle_stuck_state(game_data):
    stuck_state = game_data.get("idle_stuck_state")

    if stuck_state is None:
        return

    stuck_state["last_coordinate"] = None
    stuck_state["stationary_started_at"] = time.time()
    stuck_state["stationary_seconds"] = 0
    stuck_state["last_message"] = "捡取物品进行中，卡住跳点计时暂停"

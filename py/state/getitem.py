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

    scan = api.scan_getitems()

    if not scan.get("success", False):
        message = f"捡取物品扫描失败，回到 idle: {scan.get('message', '')}"
        api.set_getitem_runtime_status(message=message)
        return {
            "state": "idle",
            "message": message,
        }

    items = scan.get("items", [])
    target = state_data.get("target")
    picked_message = ""

    if target:
        selected = api.find_matching_getitem_target(items, target)

        if selected is None:
            picked_message = f"物品已消失，认为已捡取 target={api.format_getitem_target(target)}"
            state_data["target"] = {}
            selected = api.choose_getitem_target(items)
    else:
        selected = api.choose_getitem_target(items)

    if selected is None:
        message = "周围可捡物品已处理完，回到 idle"

        if picked_message:
            message = f"{picked_message}；{message}"

        api.set_getitem_runtime_status(message=message, target={})
        return {
            "state": "idle",
            "message": message,
        }

    click = api.click_getitem_target(selected)

    if not click.get("success", False):
        message = f"捡取物品点击失败，回到 idle: {click.get('message', '')}"
        api.set_getitem_runtime_status(message=message, target=selected)
        return {
            "state": "idle",
            "message": message,
        }

    wait_ms = api.get_getitem_step_wait_ms(settings)
    state_data["target"] = selected
    state_data["next_action_at"] = time.time() + wait_ms / 1000
    message = (
        f"捡取物品点击 target={api.format_getitem_target(selected)} "
        f"wait={wait_ms}ms {click.get('message', '')}"
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

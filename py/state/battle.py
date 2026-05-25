import time

import api


# 战斗状态：只追踪一个锁定目标，不重新做全局选怪。
def update_frame(game_data, state_data):
    runtime = game_data.get("battle_runtime_state")

    if not game_data["battle_control"].get("enabled", False):
        api.reset_battle_runtime(runtime, "战斗开关已关闭")
        return {
            "state": "idle",
            "message": "战斗开关已关闭，回到 idle",
        }

    locked_target = state_data.get("locked_target") or (runtime or {}).get("last_target", {})

    if not locked_target:
        return {
            "state": "find_monster",
            "message": "战斗状态缺少锁定目标，回到找怪",
        }

    now = time.time()
    next_recheck_at = float(locked_target.get("next_recheck_at") or 0)

    if now < next_recheck_at:
        return {}

    player_info = game_data.get("player", {})
    scan = api.scan_monsters(player_info)

    if not scan.get("success"):
        locked_target["next_recheck_at"] = now + api.TARGET_RECHECK_SECONDS
        api.set_battle_locked_target(runtime, locked_target)
        return {
            "message": f"锁定目标复查失败，不释放目标: {scan.get('message', '')}",
        }

    if not scan.get("logic_available", False):
        locked_target["next_recheck_at"] = now + api.TARGET_RECHECK_SECONDS
        api.set_battle_locked_target(runtime, locked_target)
        return {
            "message": "锁定目标复查缺少玩家逻辑坐标，本轮等待",
        }

    matched, match_message = api.find_locked_monster(
        scan.get("monsters", []),
        locked_target,
        player_info,
        scan.get("player", {}),
    )

    if matched is None:
        return handle_target_miss(game_data, state_data, locked_target, match_message)

    api.update_locked_target(locked_target, matched, now)
    next_attack_at = float(locked_target.get("next_attack_at") or 0)

    if now < next_attack_at:
        message = (
            f"锁定目标仍在 logic={format_logic(locked_target.get('last_logic', {}))} "
            f"hp={locked_target.get('last_hp_percent', '')}% {match_message}"
        )
        api.set_battle_locked_target(runtime, locked_target, message)
        state_data["locked_target"] = locked_target
        return {
            "message": message,
        }

    save_name_debug = bool(game_data.get("settings", {}).get("monster_name_debug_enabled", False))
    attack = api.attack_monster(matched, save_name_debug=save_name_debug)
    logs = []
    append_attack_logs(logs, attack)

    if attack.get("success"):
        locked_target["next_attack_at"] = now + api.ATTACK_CLICK_INTERVAL_SECONDS
        api.update_locked_target(locked_target, matched, now)
        state_data["locked_target"] = locked_target
        message = (
            f"续打锁定目标 logic={format_logic(locked_target.get('last_logic', {}))} "
            f"hp={locked_target.get('last_hp_percent', '')}% {match_message} {attack.get('message', '')}"
        )
        api.set_battle_locked_target(runtime, locked_target, message)
        return {
            "logs": logs,
            "message": message,
        }

    if attack.get("reason") == "monster_filter_mismatch":
        logic = locked_target.get("last_logic") or locked_target.get("origin_logic", {})
        api.add_ignored_target(runtime, logic, "locked_target_filter_mismatch")
        api.clear_battle_locked_target(runtime, "锁定目标名称不在清单内，释放目标")
        state_data["locked_target"] = {}
        return {
            "state": "find_monster",
            "logs": logs,
            "message": f"锁定目标名称不在清单内，释放目标: {attack.get('message', '')}",
        }

    locked_target["next_recheck_at"] = now + api.TARGET_RECHECK_SECONDS
    state_data["locked_target"] = locked_target
    api.set_battle_locked_target(runtime, locked_target)
    return {
        "logs": logs,
        "message": f"续打锁定目标失败，暂不释放: {attack.get('message', '')}",
    }


# 处理锁定目标丢失：连续达到阈值后释放并回到找怪。
def handle_target_miss(game_data, state_data, locked_target, reason, logs=None):
    logs = logs or []
    runtime = game_data.get("battle_runtime_state")
    miss_count = int(locked_target.get("miss_count") or 0) + 1
    locked_target["miss_count"] = miss_count
    locked_target["next_recheck_at"] = time.time() + api.TARGET_RECHECK_SECONDS
    state_data["locked_target"] = locked_target

    if miss_count < api.TARGET_LOST_SCAN_COUNT:
        message = f"锁定目标暂时丢失 {miss_count}/{api.TARGET_LOST_SCAN_COUNT}: {reason}"
        api.set_battle_locked_target(runtime, locked_target, message)
        return {
            "logs": logs,
            "message": message,
        }

    logic = locked_target.get("last_logic") or locked_target.get("origin_logic", {})
    api.add_ignored_target(runtime, logic, "locked_target_lost")
    api.clear_battle_locked_target(runtime, "锁定目标连续丢失，回到找怪")
    return {
        "state": "find_monster",
        "logs": logs,
        "message": f"锁定目标连续丢失，认为死亡或不可达: {reason}",
    }


# 收集攻击前名称识别日志。
def append_attack_logs(logs, attack):
    name_messages = attack.get("name_messages", [])
    name_message = attack.get("name_message", "")

    if name_messages:
        logs.extend(name_messages)
    elif name_message:
        logs.append(name_message)


# 格式化逻辑坐标。
def format_logic(logic):
    if not api.is_valid_logic(logic):
        return "-"

    return f"{int(logic['x'])}:{int(logic['y'])}"

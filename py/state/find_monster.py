import time

import api


# 找怪状态：扫描怪物，按逻辑距离选择新目标，点击成功后进入 battle 锁定追踪。
def update_frame(game_data, state_data):
    if not game_data["battle_control"].get("enabled", False):
        api.reset_battle_runtime(game_data.get("battle_runtime_state"), "战斗开关已关闭")
        return {
            "state": "idle",
            "message": "战斗开关已关闭，回到 idle",
        }

    getitem_result = api.should_enter_getitem(game_data)

    if getitem_result.get("enter", False):
        api.reset_no_monster_count(game_data.get("battle_runtime_state"), "找怪前进入捡取物品，清空无怪次数")
        return {
            "state": "getitem",
            "message": getitem_result.get("message", "找怪前发现可捡物品，进入捡取物品状态"),
        }

    player_info = game_data.get("player", {})
    runtime = game_data.get("battle_runtime_state")
    result = api.scan_monsters(player_info)

    if not result.get("success"):
        return {
            "state": "idle",
            "message": f"找怪扫描失败，不计入无怪次数: {result.get('message', '')}",
        }

    if not result.get("logic_available", False):
        return {
            "state": "idle",
            "message": "找怪需要有效玩家逻辑坐标，本轮不攻击也不计入无怪次数",
        }

    monsters = list(result.get("monsters", []))
    logs = []
    skipped = []
    save_name_debug = bool(game_data.get("settings", {}).get("monster_name_debug_enabled", False))

    while True:
        target, choose_reason = api.choose_new_monster_target(monsters, runtime)

        if target is None:
            return handle_no_target(game_data, runtime, len(result.get("monsters", [])), skipped, choose_reason, logs)

        attack = api.attack_monster(target, save_name_debug=save_name_debug)
        append_attack_logs(logs, attack)

        if attack.get("success"):
            now = time.time()
            locked_target = api.make_locked_target(target, now)
            message = (
                f"锁定怪物 logic={format_logic(locked_target.get('last_logic', {}))} "
                f"hp={target.get('hp_percent', '')}% logic_distance={api.get_monster_logic_distance(target)} "
                f"{choose_reason} {attack.get('message', '')}"
            )
            api.reset_no_monster_count(runtime, "成功攻击怪物，清空无怪次数")
            api.set_battle_locked_target(runtime, locked_target, message)
            return {
                "state": "battle",
                "data": {
                    "locked_target": locked_target,
                },
                "logs": logs,
                "message": message,
            }

        if attack.get("reason") == "monster_filter_mismatch":
            target_logic = target.get("logic", {})
            before_count = len(monsters)
            pet_heal = None
            skipped.append({
                "id": target.get("id", 0),
                "logic": target_logic,
                "message": attack.get("message", ""),
            })

            if attack.get("filter_reason") == "player_summon":
                pet_heal = api.maybe_heal_pet(
                    target,
                    attack.get("filter", {}),
                    game_data.get("settings", {}),
                    game_data.get("pet_heal_state"),
                )

                if pet_heal.get("message"):
                    logs.append(pet_heal["message"])

            api.add_ignored_target(runtime, target_logic, "monster_filter_mismatch")
            monsters = remove_same_logic_monsters(monsters, target_logic)
            removed_count = before_count - len(monsters)
            logs.append(
                f"非清单怪物已从本轮候选移除 logic={format_logic(target_logic)} removed={removed_count}"
            )

            if pet_heal and pet_heal.get("healed"):
                api.clear_battle_locked_target(runtime, "宝宝加血后重新找怪")
                return {
                    "state": "find_monster",
                    "logs": logs,
                    "message": "宝宝加血完成，重新找怪",
                }

            continue

        return {
            "state": "idle",
            "logs": logs,
            "message": f"攻击怪物失败，不计入无怪次数: {attack.get('message', '')}",
        }


# 处理没有新目标：累加无怪次数，达到阈值后跳巡逻点。
def handle_no_target(game_data, runtime, scan_count, skipped, choose_reason, logs):
    settings = game_data.get("settings", {})
    reason = make_no_target_reason(scan_count, skipped, choose_reason)
    limit = api.get_no_monster_scan_limit(settings)
    count = api.increment_no_monster_count(runtime, reason, limit)
    message = f"{reason}，连续无怪 {count}/{limit}"

    if count < limit:
        return {
            "state": "idle",
            "logs": logs,
            "message": message,
        }

    if not game_data.get("current_map"):
        return {
            "state": "idle",
            "logs": logs,
            "message": f"{message}，但还没有加载地图，无法跳巡逻点",
        }

    if not game_data.get("patrol_points"):
        return {
            "state": "idle",
            "logs": logs,
            "message": f"{message}，但还没有保存巡逻点，无法跳巡逻点",
        }

    api.reset_battle_runtime(runtime, "连续无怪达到阈值，移动到下一个巡逻点")
    return {
        "state": "move_to_next_patrol_point",
        "logs": logs,
        "message": f"{message}，移动到下一个巡逻点",
    }


# 生成无目标原因。
def make_no_target_reason(scan_count, skipped, choose_reason):
    if scan_count <= 0:
        return "近处和远处都没有扫描到怪物"

    if skipped:
        return f"扫描到 {scan_count} 个怪物，但没有符合怪物清单的目标"

    return choose_reason or f"扫描到 {scan_count} 个怪物，但都不可攻击"


# 收集攻击前名称识别日志。
def append_attack_logs(logs, attack):
    name_messages = attack.get("name_messages", [])
    name_message = attack.get("name_message", "")

    if name_messages:
        logs.extend(name_messages)
    elif name_message:
        logs.append(name_message)


# 从本轮候选列表里移除同一逻辑点附近的怪物。
def remove_same_logic_monsters(monsters, target_logic):
    if not api.is_valid_logic(target_logic):
        return [monster for monster in monsters if monster.get("logic", {}) != target_logic]

    return [
        monster
        for monster in monsters
        if api.get_logic_distance(monster.get("logic", {}), target_logic) > api.IGNORED_TARGET_RADIUS
    ]


# 格式化逻辑坐标。
def format_logic(logic):
    if not api.is_valid_logic(logic):
        return "-"

    return f"{int(logic['x'])}:{int(logic['y'])}"

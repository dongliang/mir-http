import api


# 选怪状态：扫全屏血条，按底层排序逐个悬停识别，命中清单后进入 battle。
def update_frame(game_data, state_data):
    if not game_data["battle_control"].get("enabled", False):
        api.reset_battle_runtime(game_data.get("battle_runtime_state"), "战斗开关已关闭")
        return {
            "state": "idle",
            "message": "战斗开关已关闭，回到 idle",
        }

    player_info = game_data.get("player", {})
    runtime = game_data.get("battle_runtime_state")
    result = api.findMonsterBloodBars(player_info)

    if not result.get("success"):
        return {
            "state": "idle",
            "message": f"选怪扫描失败，不计入无怪次数: {result.get('message', '')}",
        }

    width, height = api.get_bound_client_size()

    if width <= 0 or height <= 0:
        return {
            "state": "idle",
            "message": f"选怪窗口尺寸异常，不计入无怪次数 size={width}x{height}",
        }

    monsters = list(result.get("monsters", []))
    logs = []
    save_name_debug = bool(game_data.get("settings", {}).get("monster_name_debug_enabled", False))
    target = select_first_target(monsters, width, height, save_name_debug, logs)

    if target:
        message = (
            f"选中怪物 name={target.get('name', '')} "
            f"pos={format_position(target.get('position', {}))} "
            f"scan_count={len(monsters)}"
        )
        api.reset_no_monster_count(runtime, "成功选中怪物，清空无怪次数")
        api.set_battle_current_target(runtime, target, message=message)
        return {
            "state": "battle",
            "data": {
                "target": target,
            },
            "logs": logs,
            "message": message,
        }

    return handle_no_target(game_data, runtime, len(monsters), logs)


# 按血条顺序识别怪名，返回第一个完整匹配清单的目标。
def select_first_target(monsters, width, height, save_name_debug, logs):
    for monster in monsters:
        position = monster.get("position", {})

        try:
            x = int(position.get("x"))
            y = int(position.get("y"))
        except (AttributeError, TypeError, ValueError):
            logs.append(f"跳过血条 id={monster.get('id', 0)} position={position}")
            continue

        filter_result = api.verify_monster_name_before_attack(
            monster,
            x,
            y,
            width,
            height,
            save_name_debug=save_name_debug,
        )
        append_name_logs(logs, filter_result)

        if filter_result.get("allowed", False):
            return api.make_battle_target(monster, filter_result)

        logs.append(
            f"跳过血条 id={monster.get('id', 0)} "
            f"reason={filter_result.get('reason', '')} "
            f"text={filter_result.get('text', '')!r}"
        )

    return {}


# 处理没有目标：累计无怪次数，达到阈值后沿用巡逻跳点。
def handle_no_target(game_data, runtime, scan_count, logs):
    settings = game_data.get("settings", {})
    reason = make_no_target_reason(scan_count)
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
def make_no_target_reason(scan_count):
    if scan_count <= 0:
        return "没有扫描到怪物血条"

    return f"扫描到 {scan_count} 个血条，但没有符合怪物清单的目标"


# 收集怪名识别日志。
def append_name_logs(logs, filter_result):
    name_messages = filter_result.get("name_messages", [])
    name_message = filter_result.get("name_message", "")

    if name_messages:
        logs.extend(name_messages)
    elif name_message:
        logs.append(name_message)


# 格式化屏幕坐标。
def format_position(position):
    try:
        return f"{int(position.get('x'))},{int(position.get('y'))}"
    except (AttributeError, TypeError, ValueError):
        return "-"

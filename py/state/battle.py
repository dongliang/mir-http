import time

import api


# 攻击后等待时间：给角色跑向怪物并攻击，随后回到 idle 重新扫描。
ATTACK_RETURN_SECONDS = 3.0


# 战斗状态：扫描怪物，优先攻击最近残血怪，没有残血怪则攻击最近怪物。
def update_frame(game_data, state_data):
    if not game_data["battle_control"].get("enabled", False):
        return {
            "state": "idle",
            "message": "战斗开关已关闭，回到 idle",
        }

    now = time.time()
    attack_started_at = state_data.get("attack_started_at")

    if attack_started_at:
        if now - attack_started_at >= ATTACK_RETURN_SECONDS:
            return {
                "state": "idle",
                "message": "本轮攻击等待结束，回到 idle",
            }

        return {}

    result = api.scan_monsters()

    if not result.get("success"):
        return {
            "state": "idle",
            "message": f"战斗扫描失败，回到 idle: {result.get('message', '')}",
        }

    monsters = result.get("monsters", [])

    if not monsters:
        return {
            "state": "idle",
            "message": "没有扫描到怪物，回到 idle 等待卡住保护判断",
        }

    skipped = []
    logs = []
    target = None
    attack = None

    for candidate in choose_target_candidates(monsters):
        attack = api.attack_monster(candidate)
        name_messages = attack.get("name_messages", [])
        name_message = attack.get("name_message", "")

        if name_messages:
            logs.extend(name_messages)
        elif name_message:
            logs.append(name_message)

        if attack.get("success"):
            target = candidate
            break

        if attack.get("reason") == "monster_filter_mismatch":
            skipped.append({
                "id": candidate.get("id", 0),
                "message": attack.get("message", ""),
            })
            continue

        return {
            "state": "idle",
            "logs": logs,
            "message": f"攻击怪物失败，回到 idle: {attack.get('message', '')}",
        }

    if target is None:
        return {
            "state": "idle",
            "logs": logs,
            "message": f"扫描到 {len(monsters)} 个怪物，但没有符合怪物清单的目标，跳过 {len(skipped)} 个，留在原地继续扫描",
        }

    state_data["attack_started_at"] = now
    state_data["target"] = target
    return {
        "logs": logs,
        "message": f"开始攻击怪物 hp={target.get('hp_percent', '')}% distance={target.get('distance', '')} {attack.get('message', '')}",
    }


# 选择攻击目标列表：残血怪优先，怪物列表本身已经按距离排序。
def choose_target_candidates(monsters):
    wounded = [monster for monster in monsters if get_hp_percent(monster) < 100]
    normal = [monster for monster in monsters if get_hp_percent(monster) >= 100]

    return wounded + normal


# 读取怪物血量百分比：异常时按满血处理。
def get_hp_percent(monster):
    try:
        return int(float(monster.get("hp_percent", 100)))
    except (TypeError, ValueError):
        return 100

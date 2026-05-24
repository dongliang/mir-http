import time

import api


# 攻击后等待时间：给角色跑向怪物并攻击，随后回到 idle 重新扫描。
ATTACK_RETURN_SECONDS = 1.0


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
            "state": "move_to_next_patrol_point",
            "message": "没有扫描到怪物，进入下一个巡逻点移动状态",
        }

    target = choose_target(monsters)
    attack = api.attack_monster(target)

    if not attack.get("success"):
        return {
            "state": "idle",
            "message": f"攻击怪物失败，回到 idle: {attack.get('message', '')}",
        }

    state_data["attack_started_at"] = now
    state_data["target"] = target
    return {
        "message": f"开始攻击怪物 hp={target.get('hp_percent', '')}% distance={target.get('distance', '')} {attack.get('message', '')}",
    }


# 选择攻击目标：残血怪优先，怪物列表本身已经按距离排序。
def choose_target(monsters):
    wounded = [monster for monster in monsters if get_hp_percent(monster) < 100]

    if wounded:
        return wounded[0]

    return monsters[0]


# 读取怪物血量百分比：异常时按满血处理。
def get_hp_percent(monster):
    try:
        return int(float(monster.get("hp_percent", 100)))
    except (TypeError, ValueError):
        return 100

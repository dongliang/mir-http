# 空闲状态：只负责检查战斗开关，打开时进入战斗状态。
def update_frame(game_data, state_data):
    battle_control = game_data["battle_control"]

    if battle_control.get("enabled", False):
        return {
            "state": "battle",
            "message": "战斗开关已开启，进入战斗状态",
        }

    return {}

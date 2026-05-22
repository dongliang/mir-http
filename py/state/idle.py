# 空闲状态：按开关进入战斗或巡逻移动状态。
def update_frame(game_data, state_data):
    battle_control = game_data["battle_control"]
    patrol_control = game_data["patrol_control"]

    if battle_control.get("enabled", False):
        return {
            "state": "battle",
            "message": "战斗开关已开启，进入战斗状态",
        }

    if patrol_control.get("enabled", False):
        return {
            "state": "move_to_next_patrol_point",
            "message": "巡逻开关已开启，进入下一个巡逻点移动状态",
        }

    return {}

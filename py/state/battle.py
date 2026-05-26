import time

import api


# 战斗状态：点击已选目标一次，等待配置的战斗秒数后回到 idle。
def update_frame(game_data, state_data):
    runtime = game_data.get("battle_runtime_state")

    if not game_data["battle_control"].get("enabled", False):
        api.reset_battle_runtime(runtime, "战斗开关已关闭")
        return {
            "state": "idle",
            "message": "战斗开关已关闭，回到 idle",
        }

    target = state_data.get("target") or (runtime or {}).get("current_target", {})

    if not target:
        api.clear_battle_current_target(runtime, "战斗状态缺少目标，回到 idle")
        return {
            "state": "idle",
            "message": "战斗状态缺少目标，回到 idle",
        }

    now = time.time()
    duration = api.get_battle_duration_seconds(game_data.get("settings", {}))

    if not state_data.get("clicked", False):
        started_at = now
        ends_at = started_at + duration
        click = api.click_monster_hover(target)

        if not click.get("success", False):
            message = f"战斗点击失败，回到 idle: {click.get('message', '')}"
            api.clear_battle_current_target(runtime, message)
            return {
                "state": "idle",
                "message": message,
            }

        state_data["target"] = target
        state_data["clicked"] = True
        state_data["started_at"] = started_at
        state_data["ends_at"] = ends_at
        state_data["duration_seconds"] = duration
        message = (
            f"战斗开始 duration={duration}s "
            f"name={target.get('name', '')} {click.get('message', '')}"
        )
        api.set_battle_current_target(runtime, target, started_at, ends_at, message)
        return {
            "message": message,
        }

    ends_at = float(state_data.get("ends_at") or 0)

    if now < ends_at:
        api.set_battle_current_target(runtime, target, state_data.get("started_at", 0), ends_at)
        return {
            "data": state_data,
        }

    message = f"战斗计时结束 duration={duration}s，回到 idle"
    api.clear_battle_current_target(runtime, message)
    return {
        "state": "idle",
        "message": message,
    }

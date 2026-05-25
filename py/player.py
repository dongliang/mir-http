# 创建玩家状态：初始化页面展示需要的地图名和坐标字段。
def create_player():
    return {
        "map_name": "未知",
        "x": "-",
        "y": "-",
        "screen_blood_bar": {},
    }


# 设置地图坐标：把非空的地图名和坐标更新到玩家状态。
def set_map_coordinate(player_info, map_name, x, y):
    if map_name:
        # 玩家地图名：在 OCR 得到非空地图名时更新页面状态。
        player_info["map_name"] = map_name

    if x:
        # 玩家横坐标：在 OCR 得到非空 x 值时更新页面状态。
        player_info["x"] = x

    if y:
        # 玩家纵坐标：在 OCR 得到非空 y 值时更新页面状态。
        player_info["y"] = y


# 缓存玩家屏幕血条：绑定窗口时识别一次，后续扫描统一使用这份位置。
def set_screen_blood_bar(player_info, blood_bar):
    try:
        left = int(blood_bar["left"])
        top = int(blood_bar["top"])
        right = int(blood_bar["right"])
        bottom = int(blood_bar["bottom"])
    except (KeyError, TypeError, ValueError):
        clear_screen_blood_bar(player_info)
        return

    if right <= left or bottom <= top:
        clear_screen_blood_bar(player_info)
        return

    player_info["screen_blood_bar"] = {
        "blood_bar": {
            "left": left,
            "top": top,
            "right": right,
            "bottom": bottom,
        },
        "center": {
            "x": round((left + right) / 2),
            "y": round((top + bottom) / 2),
        },
        "right_top": {
            "x": right,
            "y": top,
        },
    }


# 清空玩家屏幕血条缓存。
def clear_screen_blood_bar(player_info):
    player_info["screen_blood_bar"] = {}

# 创建玩家状态：初始化页面展示需要的地图名和坐标字段。
def create_player():
    return {
        "map_name": "未知",
        "x": "-",
        "y": "-",
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

def create_player():
    return {
        "map_name": "未知",
        "x": "-",
        "y": "-",
    }


def set_map_coordinate(player_info, map_name, x, y):
    if map_name:
        player_info["map_name"] = map_name

    if x:
        player_info["x"] = x

    if y:
        player_info["y"] = y

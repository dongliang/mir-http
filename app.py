import api
import gui
import player


current_player = player.create_player()


def main() -> None:
    gui.run_gui(current_player, update_frame)


def update_frame():
    map_name, x, y = api.get_map_coordinate()
    player.set_map_coordinate(current_player, map_name, x, y)


if __name__ == "__main__":
    main()

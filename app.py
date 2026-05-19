import atexit
import threading
import time

import api
import httpserver
import log
import ocr_client
import player


current_player = player.create_player()
stop_event = threading.Event()
atexit.register(ocr_client.stop_ocr_worker)
atexit.register(stop_event.set)


def main() -> None:
    log.start_log()
    log.write("程序启动: HTTP 服务模式")
    if start_dm():
        start_bind_game_window()
    start_update_loop()
    httpserver.run_server(current_player, update_frame)


def update_frame():
    map_name, x, y = api.get_map_coordinate()
    player.set_map_coordinate(current_player, map_name, x, y)


def start_update_loop():
    thread = threading.Thread(target=update_loop, daemon=True)
    thread.start()


def start_bind_game_window():
    thread = threading.Thread(target=bind_game_window, daemon=True)
    thread.start()


def update_loop():
    while not stop_event.is_set():
        started = time.time()

        try:
            update_frame()
        except Exception as error:
            log.write(f"后台刷新坐标异常: {error}")

        elapsed = time.time() - started
        stop_event.wait(max(0.0, 0.5 - elapsed))


def start_dm():
    import dm

    log.write("开始初始化大漠")

    try:
        success, version, message = dm.start_dm()
        log.write(f"大漠版本: {version}")
        log.write(message)

        if success:
            log.write("大漠初始化成功")
            return True
        else:
            log.write("大漠初始化失败")
            return False
    except Exception as error:
        log.write(f"大漠初始化异常: {error}")
        return False


def bind_game_window():
    import dm

    log.write("启动时自动绑定窗口")

    try:
        success, title, message = dm.bind_game_window()
        log.write(message)

        if success:
            log.write(f"自动绑定窗口成功: {title}")
        else:
            log.write("自动绑定窗口失败")
    except Exception as error:
        log.write(f"自动绑定窗口异常: {error}")


if __name__ == "__main__":
    main()

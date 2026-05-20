import atexit
import threading
import time

import api
import httpserver
import log
import ocr_client
import player


current_player = player.create_player()
app_settings = {
    "overlay_enabled": True,
}
stop_event = threading.Event()
atexit.register(ocr_client.stop_ocr_worker)
atexit.register(stop_event.set)


def main() -> None:
    log.start_log()
    log.write("程序启动: HTTP 服务模式")
    apply_app_settings()
    start_dm()
    start_update_loop()
    httpserver.run_server(current_player, update_frame, app_settings)


def update_frame():
    map_name, x, y = api.get_map_coordinate()
    player.set_map_coordinate(current_player, map_name, x, y)


def start_update_loop():
    thread = threading.Thread(target=update_loop, daemon=True)
    thread.start()


def apply_app_settings():
    import dm

    dm.set_overlay_enabled(app_settings["overlay_enabled"])


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


if __name__ == "__main__":
    main()

import atexit
import threading
import time

import api
import httpserver
import log
import ocr_client
import player


# 当前玩家状态：保存页面和后台循环共享的地图坐标信息。
current_player = player.create_player()
# 应用设置：集中保存运行时可切换的界面和行为开关。
app_settings = {
    "overlay_enabled": True,
}
# 停止事件：通知后台刷新循环在程序退出时结束。
stop_event = threading.Event()
atexit.register(ocr_client.stop_ocr_worker)
atexit.register(stop_event.set)


# 主入口：初始化日志、OP 绑定能力、后台刷新循环和 HTTP 服务。
def main() -> None:
    log.start_log()
    log.write("程序启动: HTTP 服务模式")
    apply_app_settings()
    start_dm()
    start_update_loop()
    httpserver.run_server(current_player, update_frame, app_settings)


# 刷新一帧：读取当前地图坐标并写回玩家状态。
def update_frame():
    # 当前地图坐标：承接 OCR 识别出的地图名和 x/y 坐标。
    map_name, x, y = api.get_map_coordinate()
    player.set_map_coordinate(current_player, map_name, x, y)


# 启动刷新循环：创建后台线程定时更新坐标状态。
def start_update_loop():
    # 刷新线程：以守护线程运行后台坐标刷新逻辑。
    thread = threading.Thread(target=update_loop, daemon=True)
    thread.start()


# 应用运行设置：把内存中的应用设置同步到底层模块。
def apply_app_settings():
    import dm

    dm.set_overlay_enabled(app_settings["overlay_enabled"])


# 后台刷新循环：按固定节奏刷新玩家坐标并控制退出。
def update_loop():
    while not stop_event.is_set():
        # 本轮开始时间：用于控制刷新间隔并补偿处理耗时。
        started = time.time()

        try:
            update_frame()
        # 刷新异常对象：记录后台坐标刷新失败的具体原因。
        except Exception as error:
            log.write(f"后台刷新坐标异常: {error}")

        # 本轮耗时：计算下一次刷新前还需要等待多久。
        elapsed = time.time() - started
        stop_event.wait(max(0.0, 0.5 - elapsed))


# 启动 OP：初始化 OP 自动化对象并记录初始化结果。
def start_dm():
    import dm

    log.write("开始初始化 OP")

    try:
        # OP 初始化结果：包含成功状态、版本号和说明消息。
        success, version, message = dm.start_dm()
        log.write(f"OP 版本: {version}")
        log.write(message)

        if success:
            log.write("OP 初始化成功")
            return True
        else:
            log.write("OP 初始化失败")
            return False
    # OP 初始化异常：捕获底层依赖或加载失败的错误信息。
    except Exception as error:
        log.write(f"OP 初始化异常: {error}")
        return False


if __name__ == "__main__":
    main()

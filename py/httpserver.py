from fasthtml.common import *
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse
import os
import uvicorn

import api
import log
import move_to_next_patrol_point as patrol_move_state
import player as player_state


DEFAULT_SERVER_PORT = 8765
# 服务监听地址：限制 HTTP 控制台只在本机访问。
SERVER_HOST = "127.0.0.1"


# 读取 HTTP 端口：start.bat 可通过 MIR2AUTO_HTTP_PORT 覆盖默认端口。
def get_server_port():
    port_text = os.environ.get("MIR2AUTO_HTTP_PORT", "").strip()

    if not port_text:
        return DEFAULT_SERVER_PORT

    if not port_text.isdigit():
        return DEFAULT_SERVER_PORT

    port = int(port_text)

    if 1 <= port <= 65535:
        return port

    return DEFAULT_SERVER_PORT


# 服务监听端口：默认 8765，允许 start.bat 覆盖。
SERVER_PORT = get_server_port()


# 运行 HTTP 服务：创建应用并启动 uvicorn 本地服务。
def run_server(
    player_info,
    update_frame,
    app_settings,
    current_map,
    patrol_points,
    patrol_state,
    patrol_control,
    battle_control,
    current_state,
    auto_heal_state,
    pet_heal_state,
    idle_stuck_state,
    battle_runtime_state,
    game_data,
    restart_app,
):
    # FastHTML 应用：承载页面和所有 API 路由。
    app = create_server(
        player_info,
        update_frame,
        app_settings,
        current_map,
        patrol_points,
        patrol_state,
        patrol_control,
        battle_control,
        current_state,
        auto_heal_state,
        pet_heal_state,
        idle_stuck_state,
        battle_runtime_state,
        game_data,
        restart_app,
    )
    log.write_console(f"HTTP 服务启动: http://{SERVER_HOST}:{SERVER_PORT}")
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, log_level="warning")


# 创建 HTTP 服务：注册控制台页面和后端操作 API。
def create_server(
    player_info,
    update_frame,
    app_settings,
    current_map,
    patrol_points,
    patrol_state,
    patrol_control,
    battle_control,
    current_state,
    auto_heal_state,
    pet_heal_state,
    idle_stuck_state,
    battle_runtime_state,
    game_data,
    restart_app,
):
    # 应用和路由器：由 FastHTML 创建页面应用和路由装饰器。
    app, rt = fast_app(static_path=str(api.base_dir))

    # 当前页面状态：闭包绑定地图和巡逻运行时变量。
    def current_status():
        return get_status(
            player_info,
            app_settings,
            current_map,
            patrol_points,
            patrol_state,
            patrol_control,
            battle_control,
            current_state,
            auto_heal_state,
            pet_heal_state,
            idle_stuck_state,
            battle_runtime_state,
        )

    # 首页路由：渲染窗口绑定、移动控制和日志面板。
    @rt("/")
    def get():
        return Html(
            Head(
                Title("httpserver"),
                Style(PAGE_STYLE),
                Script(PAGE_SCRIPT),
            ),
            Body(
                H1("httpserver"),
                create_tabs(app_settings, player_info, current_state),
            ),
        )

    # 状态读取接口：返回玩家、窗口绑定和应用设置状态。
    @rt("/api/status")
    def get():
        return JSONResponse(current_status())

    # 帧状态接口：兼容前端 POST 轮询并返回当前状态。
    @rt("/api/frame")
    def post():
        return JSONResponse(current_status())

    # 开始战斗接口：打开战斗开关，后台状态机下一帧进入战斗。
    @rt("/api/battle/start")
    def post():
        battle_control["enabled"] = True
        patrol_control["enabled"] = False
        api.reset_battle_runtime(battle_runtime_state, "战斗开关已打开")
        message = "战斗开关已打开，巡逻开关已关闭"
        log.write(message)
        return JSONResponse({
            "success": True,
            "message": message,
            "status": current_status(),
        })

    # 结束战斗接口：关闭战斗开关，后台状态机下一帧回到 idle。
    @rt("/api/battle/stop")
    def post():
        battle_control["enabled"] = False
        api.reset_battle_runtime(battle_runtime_state, "战斗开关已关闭")
        message = "战斗开关已关闭"
        log.write(message)
        return JSONResponse({
            "success": True,
            "message": message,
            "status": current_status(),
        })

    # 战斗设置接口：保存连续无怪跳点次数和单次战斗等待秒数。
    @rt("/api/battle/settings")
    async def post(request: Request):
        try:
            data = await request.json()
        except Exception:
            data = {}

        result = api.update_battle_settings(app_settings, battle_runtime_state, data)
        result = save_account_settings_after_update(app_settings, result)
        log.write(result["message"])
        return JSONResponse({
            "success": result["success"],
            "message": result["message"],
            "battle": result.get("battle", {}),
            "status": current_status(),
        })

    # 当前地图图片：供网页巡逻面板显示 maps/<地图名>/image.png。
    @rt("/api/map/image")
    def get(name: str = ""):
        image_file = api.get_map_image_file(name)

        if not image_file.exists():
            return PlainTextResponse("map not found", status_code=404)

        return FileResponse(image_file, media_type="image/png")

    # 截取地图接口：手动截图当前大地图，保存到 maps/<地图名>/。
    @rt("/api/map/capture")
    def post():
        result = capture_map_and_reset(
            update_frame,
            player_info,
            current_map,
            patrol_points,
            patrol_state,
            patrol_control,
        )
        log.write(result["message"])

        return JSONResponse({
            "success": result["success"],
            "message": result["message"],
            "map": result.get("map", {}),
            "status": current_status(),
        })

    # 兼容旧路径：旧“绑定地图”等同于现在的“截取地图”。
    @rt("/api/map/bind")
    def post():
        result = capture_map_and_reset(
            update_frame,
            player_info,
            current_map,
            patrol_points,
            patrol_state,
            patrol_control,
        )
        log.write(result["message"])

        return JSONResponse({
            "success": result["success"],
            "message": result["message"],
            "map": result.get("map", {}),
            "status": current_status(),
        })

    # 保存巡逻点到全局 maps/<地图名>/巡逻点.txt。
    @rt("/api/patrol/save/global")
    async def post(request: Request):
        try:
            data = await request.json()
        except Exception:
            data = {}

        result = save_patrol_points(data, current_map, patrol_points, patrol_state, "global")

        if result["success"] and not result.get("points", []):
            patrol_control["enabled"] = False

        log.write(result["message"])
        return JSONResponse({
            "success": result["success"],
            "message": result["message"],
            "points": result.get("points", []),
            "status": current_status(),
        })

    # 移动到下一个巡逻点接口：按循环索引取点并触发游戏地图点击。
    @rt("/api/patrol/next")
    def post():
        result = move_to_next_patrol_point(game_data)
        log.write(result["message"])
        return JSONResponse({
            "success": result["success"],
            "message": result["message"],
            "point": result.get("point", {}),
            "index": patrol_state["index"],
            "move": result.get("move", {}),
            "status": current_status(),
        })

    # 选中巡逻点接口：只更新当前巡逻点 index。
    @rt("/api/patrol/select")
    def post(index: int = -1):
        result = patrol_move_state.select_index(game_data, index)
        log.write(result["message"])
        return JSONResponse({
            "success": result["success"],
            "message": result["message"],
            "point": result.get("point", {}),
            "index": result.get("index", patrol_state["index"]),
            "status": current_status(),
        })

    # 移动到指定巡逻点接口：移动成功后把该点设为当前巡逻点。
    @rt("/api/patrol/move")
    def post(index: int = -1):
        result = patrol_move_state.move_to_index(game_data, index)
        log.write(result["message"])
        return JSONResponse({
            "success": result["success"],
            "message": result["message"],
            "point": result.get("point", {}),
            "index": result.get("index", patrol_state["index"]),
            "move": result.get("move", {}),
            "status": current_status(),
        })

    # 移动到当前巡逻点接口：使用 patrol_state["index"]。
    @rt("/api/patrol/current")
    def post():
        result = patrol_move_state.move_current(game_data)
        log.write(result["message"])
        return JSONResponse({
            "success": result["success"],
            "message": result["message"],
            "point": result.get("point", {}),
            "index": result.get("index", patrol_state["index"]),
            "move": result.get("move", {}),
            "status": current_status(),
        })

    # 开始巡逻接口：打开巡逻开关，同时关闭战斗开关。
    @rt("/api/patrol/start")
    def post():
        battle_control["enabled"] = False
        api.reset_battle_runtime(battle_runtime_state, "开始巡逻，清空战斗运行状态")

        if not current_map:
            message = "战斗开关已关闭；还没有加载地图，不能开始巡逻"
            log.write(message)
            return JSONResponse({
                "success": False,
                "message": message,
                "status": current_status(),
            })

        if not patrol_points:
            message = "战斗开关已关闭；还没有保存巡逻点，不能开始巡逻"
            log.write(message)
            return JSONResponse({
                "success": False,
                "message": message,
                "status": current_status(),
            })

        patrol_control["enabled"] = True
        message = "巡逻开关已打开，战斗开关已关闭"
        log.write(message)
        return JSONResponse({
            "success": True,
            "message": message,
            "status": current_status(),
        })

    # 关闭巡逻接口：关闭巡逻开关，后台巡逻移动下一帧回到 idle。
    @rt("/api/patrol/stop")
    def post():
        patrol_control["enabled"] = False
        api.reset_no_monster_count(battle_runtime_state, "巡逻开关已关闭")
        message = "巡逻开关已关闭"
        log.write(message)
        return JSONResponse({
            "success": True,
            "message": message,
            "status": current_status(),
        })

    # OP 启动接口：初始化 OP 并返回版本与结果消息。
    @rt("/api/op/start")
    def post():
        # OP 启动结果：保存初始化成功状态、版本和说明。
        result = api.start_op()
        log.write(result["message"])
        return JSONResponse(result)

    # 窗口绑定接口：按标题关键字查找并绑定游戏窗口。
    @rt("/api/window/bind")
    def post(keyword: str = ""):
        # 绑定结果：记录窗口绑定是否成功、标题和说明消息。
        result = api.bind_window(keyword)
        messages = [result["message"]]

        if result["success"]:
            output_dir = result.get("output_dir", "")
            screen_blood_bar = result.get("screen_blood_bar", {})
            player_state.set_screen_blood_bar(player_info, screen_blood_bar.get("blood_bar", {}))

            if output_dir:
                log.use_run_dir(output_dir, clear=True)

            settings_result = load_account_settings_after_bind(
                app_settings,
                auto_heal_state,
                pet_heal_state,
                idle_stuck_state,
                battle_runtime_state,
            )
            messages.append(settings_result.get("message", ""))
            update_frame_safely(update_frame)
        else:
            player_state.clear_screen_blood_bar(player_info)

        message = "；".join(message for message in messages if message)
        log.write(message)
        return JSONResponse({
            "success": result["success"],
            "title": result["title"],
            "message": message,
            "status": current_status(),
        })

    # 窗口解绑接口：解除当前绑定窗口并返回最新状态。
    @rt("/api/window/unbind")
    def post():
        # 解绑结果：记录窗口解绑是否成功、标题和说明消息。
        result = api.unbind_window()
        output_dir = result.get("output_dir", "")

        if result["success"]:
            player_state.clear_screen_blood_bar(player_info)

        if output_dir:
            log.use_run_dir(output_dir)

        log.write(result["message"])
        return JSONResponse({
            "success": result["success"],
            "title": result["title"],
            "message": result["message"],
            "status": current_status(),
        })

    # 坐标读取接口：主动刷新一次 OCR 坐标并返回页面状态。
    @rt("/api/coordinate/read")
    def post():
        update_frame_safely(update_frame)
        return JSONResponse({
            "map_name": player_info["map_name"],
            "x": player_info["x"],
            "y": player_info["y"],
            "status": current_status(),
        })

    # 移动接口：根据动作和方向触发一次角色移动点击。
    @rt("/api/move/{action}/{direction}")
    def post(action: str, direction: str):
        # 移动结果：保存点击移动的成功状态和诊断消息。
        result = api.move_player(action, direction)
        log.write(result["message"])
        return JSONResponse({
            "move": result,
            "status": current_status(),
        })

    # 截图接口：截取当前绑定窗口并返回截图保存路径。
    @rt("/api/screenshot")
    def post():
        # 截图结果：记录截图是否成功、路径和说明消息。
        result = api.capture_screenshot()
        log.write(result["message"])
        return JSONResponse({
            "success": result["success"],
            "path": result["path"],
            "client": result.get("client", {}),
            "image": result.get("image", {}),
            "message": result["message"],
            "status": current_status(),
        })

    # 地图角点接口：把鼠标移动到大地图 rect 右下角，验证 OP 有效坐标。
    @rt("/api/map/rect-corner")
    def post():
        result = api.move_mouse_to_map_rect_corner()
        log.write(result["message"])
        return JSONResponse({
            "success": result["success"],
            "x": result.get("x", 0),
            "y": result.get("y", 0),
            "raw_x": result.get("raw_x", 0),
            "raw_y": result.get("raw_y", 0),
            "screen_x": result.get("screen_x", 0),
            "screen_y": result.get("screen_y", 0),
            "rect": result.get("rect", {}),
            "client": result.get("client", {}),
            "message": result["message"],
            "status": current_status(),
        })

    # 地图角点快捷键设置接口：保存网页配置并同步后台监听线程。
    @rt("/api/map/rect-corner/hotkey")
    async def post(request: Request):
        try:
            data = await request.json()
        except Exception:
            data = {}

        result = api.update_map_corner_hotkey_settings(app_settings, data)
        result = save_account_settings_after_update(app_settings, result)
        log.write(result["message"])
        return JSONResponse({
            "success": result["success"],
            "message": result["message"],
            "settings": result.get("settings", {}),
            "status": current_status(),
        })

    # 玩家屏幕位置接口：返回按移动原点算法计算出的角色屏幕坐标。
    @rt("/api/player/screen-position")
    def post():
        # 玩家屏幕位置结果：记录当前 OP 客户区诊断信息。
        result = api.get_player_screen_position()
        log.write(result["message"])
        return JSONResponse({
            "success": result["success"],
            "player_x": result["player_x"],
            "player_y": result["player_y"],
            "client": result.get("client", {}),
            "bottom_ui_height": result.get("bottom_ui_height", api.BOTTOM_UI_HEIGHT),
            "message": result["message"],
            "status": current_status(),
        })

    # 附近怪物扫描接口：查找人物血条附近的红色怪物血条。
    @rt("/api/monsters/scan-nearby")
    def post():
        result = api.findNearbyMonsterBloodBars(player_info)
        log.write(result["message"])
        log_monster_scan_details(result)
        return JSONResponse({
            "success": result["success"],
            "monsters": result.get("monsters", []),
            "count": result.get("count", 0),
            "player": result.get("player", {}),
            "screen_blood_bar": result.get("screen_blood_bar", {}),
            "search_box": result.get("search_box", {}),
            "client": result.get("client", {}),
            "debug_points": result.get("debug_points", []),
            "message": result["message"],
            "status": current_status(),
        })

    # 怪物扫描接口：查找除底部 UI 以外的怪物血条。
    @rt("/api/monsters/scan")
    def post():
        # 怪物扫描结果：记录扫描摘要并把明细写入日志。
        result = api.findMonsterBloodBars(player_info)
        log.write(result["message"])
        log_monster_scan_details(result)
        return JSONResponse({
            "success": result["success"],
            "monsters": result.get("monsters", []),
            "count": result.get("count", 0),
            "player": result.get("player", {}),
            "screen_blood_bar": result.get("screen_blood_bar", {}),
            "search_box": result.get("search_box", {}),
            "client": result.get("client", {}),
            "debug_points": result.get("debug_points", []),
            "message": result["message"],
            "status": current_status(),
        })

    # 怪物名称识别接口：按表格传入的单个怪物位置补充名称。
    @rt("/api/monsters/name")
    def post(
        x: int = 0,
        y: int = 0,
        bar_left: int = -1,
        bar_top: int = -1,
        bar_right: int = -1,
        bar_bottom: int = -1,
    ):
        # 血条信息：有完整血条坐标时用它计算名字 OCR 区域。
        blood_bar = None

        if bar_right > bar_left and bar_bottom > bar_top:
            blood_bar = {
                "left": bar_left,
                "top": bar_top,
                "right": bar_right,
                "bottom": bar_bottom,
            }

        save_debug = bool(app_settings.get("monster_name_debug_enabled", False))
        result = api.recognize_monster_name(x, y, blood_bar, save_debug=save_debug)
        for entry in result.get("ocr_logs", []):
            log.write(entry)

        log.write(result["message"])
        return JSONResponse({
            "success": result["success"],
            "name": result.get("name", "未识别"),
            "name_text": result.get("name_text", ""),
            "raw_text": result.get("raw_text", ""),
            "mask_text": result.get("mask_text", ""),
            "color": result.get("color", ""),
            "used_attempt": result.get("used_attempt", 0),
            "reject_reason": result.get("reject_reason", ""),
            "debug_images": result.get("debug_images", []),
            "position": result.get("position", {}),
            "ocr_box": result.get("ocr_box", {}),
            "blood_bar": result.get("blood_bar", {}),
            "message": result["message"],
            "status": current_status(),
        })

    # TXT 配置重载接口：重新读取怪物和物品清单、OCR 颜色。
    @rt("/api/monsters/reload-list")
    def post():
        result = api.reload_text_configs()
        log.write(result["message"])
        return JSONResponse({
            "success": True,
            "monster_filter": result["monster_filter"],
            "monster_name_colors": result["monster_name_colors"],
            "item_filter": result["item_filter"],
            "item_name_colors": result["item_name_colors"],
            "message": result["message"],
            "status": current_status(),
        })

    # 保存巡逻点到账号 accounts/<角色名>/maps/<地图名>/巡逻点.txt。
    @rt("/api/patrol/save/account")
    async def post(request: Request):
        try:
            data = await request.json()
        except Exception:
            data = {}

        result = save_patrol_points(data, current_map, patrol_points, patrol_state, "account")

        if result["success"] and not result.get("points", []):
            patrol_control["enabled"] = False

        log.write(result["message"])
        return JSONResponse({
            "success": result["success"],
            "message": result["message"],
            "points": result.get("points", []),
            "status": current_status(),
        })

    # 兼容旧路径：默认保存到全局巡逻点。
    @rt("/api/patrol/save")
    async def post(request: Request):
        try:
            data = await request.json()
        except Exception:
            data = {}

        result = save_patrol_points(data, current_map, patrol_points, patrol_state, "global")

        if result["success"] and not result.get("points", []):
            patrol_control["enabled"] = False

        log.write(result["message"])
        return JSONResponse({
            "success": result["success"],
            "message": result["message"],
            "points": result.get("points", []),
            "status": current_status(),
        })

    # 账号配置复写接口：用根目录 txt/*.txt 覆盖所有已存在账号配置。
    @rt("/api/accounts/overwrite-configs")
    def post():
        result = api.overwrite_account_configs()
        log.write(result["message"])
        text_config = result.get("text_config", {})
        return JSONResponse({
            "success": result["success"],
            "message": result["message"],
            "accounts": result.get("accounts", {}),
            "copied_files": result.get("copied_files", 0),
            "errors": result.get("errors", []),
            "monster_filter": text_config.get("monster_filter", api.get_monster_keyword_status()),
            "monster_name_colors": text_config.get("monster_name_colors", api.get_monster_name_color_status()),
            "item_filter": text_config.get("item_filter", api.get_item_keyword_status()),
            "item_name_colors": text_config.get("item_name_colors", api.get_item_name_color_status()),
            "status": current_status(),
        })

    # 后台键盘输入接口：向当前绑定窗口发送指定按键。
    @rt("/api/keyboard/press")
    def post(key: str = "", hold_ms: int = 120, repeat: int = 1, interval_ms: int = 80):
        # 键盘输入结果：记录 OP 后台按键是否成功发送。
        result = api.press_keyboard(key, hold_ms, repeat, interval_ms)
        log.write(result["message"])
        return JSONResponse({
            "success": result["success"],
            "message": result["message"],
            "keyboard": result,
            "status": current_status(),
        })

    # 后台键盘测试接口：用默认 M 按键复用通用键盘输入封装。
    @rt("/api/keyboard/test")
    def post():
        # 键盘测试结果：记录 OP 后台按键是否成功发送。
        result = api.test_keyboard()
        log.write(result["message"])
        return JSONResponse({
            "success": result["success"],
            "message": result["message"],
            "keyboard": result,
            "status": current_status(),
        })

    # 自动加血设置接口：保存页面开关、触发血量和检测间隔。
    @rt("/api/auto-heal/settings")
    async def post(request: Request):
        try:
            data = await request.json()
        except Exception:
            data = {}

        result = api.update_auto_heal_settings(app_settings, auto_heal_state, data)
        result = save_account_settings_after_update(app_settings, result)
        log.write(result["message"])
        return JSONResponse({
            "success": result["success"],
            "message": result["message"],
            "auto_heal": result.get("auto_heal", {}),
            "status": current_status(),
        })

    # 宝宝加血设置接口：保存页面开关、触发血量和加血按键。
    @rt("/api/pet-heal/settings")
    async def post(request: Request):
        try:
            data = await request.json()
        except Exception:
            data = {}

        result = api.update_pet_heal_settings(app_settings, pet_heal_state, data)
        result = save_account_settings_after_update(app_settings, result)
        log.write(result["message"])
        return JSONResponse({
            "success": result["success"],
            "message": result["message"],
            "pet_heal": result.get("pet_heal", {}),
            "status": current_status(),
        })

    # idle 卡住保护设置接口：保存页面开关和停留秒数。
    @rt("/api/idle-stuck/settings")
    async def post(request: Request):
        try:
            data = await request.json()
        except Exception:
            data = {}

        result = api.update_idle_stuck_settings(app_settings, idle_stuck_state, data)
        result = save_account_settings_after_update(app_settings, result)
        log.write(result["message"])
        return JSONResponse({
            "success": result["success"],
            "message": result["message"],
            "idle_stuck": result.get("idle_stuck", {}),
            "status": current_status(),
        })

    # 捡取物品设置接口：保存页面开关和每步等待间隔。
    @rt("/api/getitem/settings")
    async def post(request: Request):
        try:
            data = await request.json()
        except Exception:
            data = {}

        result = api.update_getitem_settings(app_settings, data)
        result = save_account_settings_after_update(app_settings, result)
        if current_state.get("name") == "getitem":
            current_state.get("data", {})["next_action_at"] = 0
        log.write(result["message"])
        return JSONResponse({
            "success": result["success"],
            "message": result["message"],
            "getitem": result.get("getitem", {}),
            "status": current_status(),
        })

    # 拾取测试接口：强制进入 getitem 状态，方便不启动战斗/巡逻时手动验证。
    @rt("/api/getitem/test")
    def post():
        current_state["name"] = "getitem"
        current_state["data"] = {
            "manual_test": True,
        }
        message = "拾取测试已进入 getitem 状态"
        api.set_getitem_runtime_status(message=message, target={})
        log.write(message)
        return JSONResponse({
            "success": True,
            "message": message,
            "status": current_status(),
        })

    # 怪物名 Debug 图开关接口：只控制是否保存本次运行的识别截图。
    @rt("/api/monster-name-debug/settings")
    async def post(request: Request):
        try:
            data = await request.json()
        except Exception:
            data = {}

        result = api.update_monster_name_debug_settings(app_settings, data)
        result = save_account_settings_after_update(app_settings, result)
        log.write(result["message"])
        return JSONResponse({
            "success": result["success"],
            "message": result["message"],
            "settings": result.get("settings", {}),
            "status": current_status(),
        })

    # 测试按钮接口：写入一条测试日志用于验证页面操作链路。
    @rt("/api/test/{number}")
    def post(number: int):
        # 测试消息：记录被点击的测试按钮编号。
        message = f"测试按钮 {number} 被点击"
        log.write(message)
        return JSONResponse({"success": True, "message": message})

    # 日志读取接口：返回当前日志文本供前端展示。
    @rt("/api/logs")
    def get():
        return PlainTextResponse(log.read())

    # 程序重启接口：由 app.py 负责实际进程重启和退出清理。
    @rt("/api/app/restart")
    def post():
        result = restart_app()
        log.write(result["message"])
        return JSONResponse(result)

    return app


# 创建首页标签页：把账号、状态、战斗、操控和调试功能分区。
def create_tabs(app_settings, player_info, current_state):
    return Div(
        Div(
            create_tab_button("account", "账号"),
            create_tab_button("status", "状态", active=True),
            create_tab_button("battle", "战斗"),
            create_tab_button("control", "操控"),
            create_tab_button("debug", "Debug"),
            cls="tabs",
        ),
        Div(
            create_tab_panel("account", create_account_panel()),
            create_tab_panel("status", create_status_panel(player_info, current_state), active=True),
            create_tab_panel("battle", create_battle_panel(app_settings)),
            create_tab_panel("control", create_control_panel()),
            create_tab_panel("debug", create_debug_panel(app_settings)),
            cls="tab-panels",
        ),
        cls="tab-shell",
    )


# 创建标签按钮。
def create_tab_button(tab_id, label, active=False):
    cls = "tab-button active" if active else "tab-button"
    selected = "true" if active else "false"
    return Button(
        label,
        type="button",
        onclick=f"switchTab('{tab_id}')",
        cls=cls,
        **{
            "data-tab": tab_id,
            "aria-selected": selected,
        },
    )


# 创建标签内容面板。
def create_tab_panel(tab_id, *children, active=False):
    cls = "tab-panel active" if active else "tab-panel"
    return Div(
        *children,
        id=f"tab-{tab_id}",
        cls=cls,
        **{"data-tab-panel": tab_id},
    )


# 创建账号页：账号选择、窗口绑定和账号配置操作。
def create_account_panel():
    return Div(
        Div(
            Select(
                Option("选择账号", value=""),
                id="account-select",
                onchange="selectAccountFromDropdown()",
            ),
            Input(
                id="bind-keyword",
                type="text",
                placeholder="窗口标题关键字",
                autocomplete="off",
            ),
            Button("绑定", onclick="bindWindow()"),
            Button("解除绑定", onclick="unbindWindow()"),
            cls="bind-controls",
        ),
        Div(
            Div("账号: ", Span("未选择", id="account-current")),
            Div("配置目录: ", Span("-", id="account-config-dir")),
            cls="status",
        ),
        Div(
            Button("复写配置", onclick="postApi('/api/accounts/overwrite-configs')"),
            Button("重载TXT配置", onclick="postApi('/api/monsters/reload-list')"),
            cls="utility-buttons",
        ),
    )


# 创建状态页：只读展示当前运行概况。
def create_status_panel(player_info, current_state):
    return Div(
        Div("绑定窗口: ", Span("未绑定", id="bound-title")),
        Div("地图: ", Span(player_info["map_name"], id="map-name")),
        Div("地图原文: ", Span("-", id="map-raw")),
        Div("坐标: ", Span(f"{player_info['x']}:{player_info['y']}", id="coordinate")),
        Div("状态: ", Span(current_state["name"], id="state-name")),
        Div("巡逻: ", Span("关", id="patrol-enabled")),
        Div("战斗: ", Span("关", id="battle-enabled")),
        Div("连续无怪: ", Span("-", id="battle-no-monster")),
        Div("自动加血: ", Span("关", id="auto-heal-enabled-text")),
        Div("卡住跳点: ", Span("开", id="idle-stuck-enabled-text")),
        Div("捡取物品: ", Span("开", id="getitem-enabled-text")),
        Div("怪物过滤: ", Span("-", id="monster-filter")),
        Div("怪物字色: ", Span("-", id="monster-name-colors")),
        Div("物品过滤: ", Span("-", id="item-filter")),
        Div("物品字色: ", Span("-", id="item-name-colors")),
        cls="status",
    )


# 创建战斗页：自动战斗相关开关、参数和怪物列表。
def create_battle_panel(app_settings):
    return Div(
        Div(
            Button("开始战斗", onclick="startBattle()"),
            Button("结束战斗", onclick="stopBattle()"),
            cls="utility-buttons",
        ),
        create_battle_controls(app_settings),
        create_auto_heal_controls(app_settings),
        create_pet_heal_controls(app_settings),
        create_getitem_controls(app_settings),
        create_idle_stuck_controls(app_settings),
        create_monster_panel(),
    )


# 创建操控页：手动移动、地图巡逻和巡逻点维护。
def create_control_panel():
    return Div(
        Div(
            Button("测试坐标", onclick="postApi('/api/coordinate/read')"),
            Button("测试键盘(M)", onclick="pressKeyboard('M')"),
            Button("截取地图", onclick="captureMap()"),
            Button("保存巡逻点到全局", onclick="savePatrolPoints('global')"),
            Button("保存巡逻点到账号", onclick="savePatrolPoints('account')"),
            Button("移动到下一个巡逻点", onclick="moveToNextPatrolPoint()"),
            Button("移动到当前巡逻点", onclick="moveToCurrentPatrolPoint()"),
            Button("开始巡逻", onclick="startPatrol()"),
            Button("关闭巡逻", onclick="stopPatrol()"),
            cls="utility-buttons",
        ),
        Div(
            create_move_pad("走", "walk"),
            create_move_pad("跑", "run"),
            cls="move-pads",
        ),
        create_patrol_panel(),
    )


# 创建 Debug 页：截图、OCR、坐标和程序诊断工具。
def create_debug_panel(app_settings):
    return Div(
        Div(
            Button("截图", onclick="takeScreenshot()"),
            Button("地图角点", onclick="postApi('/api/map/rect-corner')"),
            Button("找附近怪", onclick="scanMonsters('/api/monsters/scan-nearby')"),
            Button("找全屏怪", onclick="scanMonsters('/api/monsters/scan')"),
            Button("拾取测试", onclick="postApi('/api/getitem/test')"),
            Button("重启程序", onclick="restartApp()"),
            cls="utility-buttons",
        ),
        create_map_corner_hotkey_controls(app_settings),
        create_monster_name_debug_controls(app_settings),
        Div(
            Div("怪名Debug图: ", Span("关", id="monster-name-debug-enabled-text")),
            cls="status",
        ),
        Pre("", id="log-box"),
    )


# 创建怪物列表面板：战斗页展示扫描结果和单只怪物名称识别入口。
def create_monster_panel():
    return Div(
        H3("怪物列表"),
        Table(
            Thead(
                Tr(
                    Th("怪物名称"),
                    Th("距离玩家"),
                    Th("怪物血量"),
                    Th("怪物位置"),
                    Th("操作"),
                )
            ),
            Tbody(
                Tr(
                    Td("暂无数据", colspan="5"),
                ),
                id="monster-body",
            ),
        ),
        cls="monster-panel",
    )


# 创建地图角点快捷键控制栏。
def create_map_corner_hotkey_controls(app_settings):
    return Div(
        Label(
            Span("地图角点快捷键"),
            Input(
                id="map-corner-hotkey",
                type="text",
                value=str(app_settings.get("map_corner_hotkey", api.MAP_CORNER_HOTKEY_DEFAULT)),
                onchange="saveMapCornerHotkeySettings()",
            ),
            cls="map-corner-hotkey-field",
        ),
        Button("保存", onclick="saveMapCornerHotkeySettings()"),
        Div("", id="map-corner-hotkey-message", cls="map-corner-hotkey-message"),
        cls="map-corner-hotkey-controls",
    )


# 创建自动加血控制栏：开关、触发血量和检测间隔。
def create_auto_heal_controls(app_settings):
    enabled_attrs = {
        "id": "auto-heal-enabled",
        "type": "checkbox",
        "onchange": "saveAutoHealSettings()",
    }

    if app_settings.get("auto_heal_enabled", False):
        enabled_attrs["checked"] = True

    return Div(
        Label(
            Input(**enabled_attrs),
            Span("自动加血"),
            cls="auto-heal-toggle",
        ),
        Label(
            Span("触发血量%"),
            Input(
                id="auto-heal-threshold",
                type="number",
                min="1",
                max="100",
                step="1",
                value=str(app_settings.get("auto_heal_threshold_percent", api.AUTO_HEAL_DEFAULT_THRESHOLD_PERCENT)),
                onchange="saveAutoHealSettings()",
            ),
            cls="auto-heal-field",
        ),
        Label(
            Span("检测间隔ms"),
            Input(
                id="auto-heal-interval",
                type="number",
                min="500",
                max="60000",
                step="100",
                value=str(app_settings.get("auto_heal_interval_ms", 1000)),
                onchange="saveAutoHealSettings()",
            ),
            cls="auto-heal-field",
        ),
        Div("", id="auto-heal-message", cls="auto-heal-message"),
        cls="auto-heal-controls",
    )


# 创建宝宝加血控制栏：开关、触发血量和加血按键。
def create_pet_heal_controls(app_settings):
    enabled_attrs = {
        "id": "pet-heal-enabled",
        "type": "checkbox",
        "onchange": "savePetHealSettings()",
    }

    if app_settings.get("pet_heal_enabled", False):
        enabled_attrs["checked"] = True

    return Div(
        Label(
            Input(**enabled_attrs),
            Span("宝宝加血"),
            cls="pet-heal-toggle",
        ),
        Label(
            Span("触发血量%"),
            Input(
                id="pet-heal-threshold",
                type="number",
                min="1",
                max="100",
                step="1",
                value=str(app_settings.get("pet_heal_threshold_percent", api.PET_HEAL_DEFAULT_THRESHOLD_PERCENT)),
                onchange="savePetHealSettings()",
            ),
            cls="pet-heal-field",
        ),
        Label(
            Span("加血按键"),
            Input(
                id="pet-heal-key",
                type="text",
                value=str(app_settings.get("pet_heal_key", api.PET_HEAL_DEFAULT_KEY)),
                onchange="savePetHealSettings()",
            ),
            cls="pet-heal-field",
        ),
        Div("", id="pet-heal-message", cls="pet-heal-message"),
        cls="pet-heal-controls",
    )


# 创建战斗控制栏：连续无怪次数用于刷空跳点，战斗秒数用于单次点击后的等待。
def create_battle_controls(app_settings):
    return Div(
        Label(
            Span("连续无怪次数"),
            Input(
                id="no-monster-scan-limit",
                type="number",
                min=str(api.NO_MONSTER_SCAN_LIMIT_MIN),
                max=str(api.NO_MONSTER_SCAN_LIMIT_MAX),
                step="1",
                value=str(app_settings.get("no_monster_scan_limit", api.NO_MONSTER_SCAN_LIMIT_DEFAULT)),
                onchange="saveBattleSettings()",
            ),
            cls="battle-settings-field",
        ),
        Label(
            Span("战斗秒数"),
            Input(
                id="battle-duration-seconds",
                type="number",
                min=str(api.BATTLE_DURATION_SECONDS_MIN),
                max=str(api.BATTLE_DURATION_SECONDS_MAX),
                step="1",
                value=str(app_settings.get("battle_duration_seconds", api.BATTLE_DURATION_SECONDS_DEFAULT)),
                onchange="saveBattleSettings()",
                cls="battle-duration-input",
            ),
            cls="battle-settings-field battle-duration-field",
        ),
        Div("", id="battle-settings-message", cls="battle-settings-message"),
        cls="battle-settings-controls",
    )


# 创建 idle 卡住保护控制栏：开关和停留秒数。
def create_idle_stuck_controls(app_settings):
    enabled_attrs = {
        "id": "idle-stuck-enabled",
        "type": "checkbox",
        "onchange": "saveIdleStuckSettings()",
    }

    if app_settings.get("idle_stuck_enabled", True):
        enabled_attrs["checked"] = True

    return Div(
        Label(
            Input(**enabled_attrs),
            Span("卡住跳点"),
            cls="idle-stuck-toggle",
        ),
        Label(
            Span("停留秒数"),
            Input(
                id="idle-stuck-seconds",
                type="number",
                min="5",
                max="600",
                step="1",
                value=str(app_settings.get("idle_stuck_seconds", 30)),
                onchange="saveIdleStuckSettings()",
            ),
            cls="idle-stuck-field",
        ),
        Div("", id="idle-stuck-message", cls="idle-stuck-message"),
        cls="idle-stuck-controls",
    )


# 创建捡取物品控制栏：开关和每次点击后的走路等待。
def create_getitem_controls(app_settings):
    enabled_attrs = {
        "id": "getitem-enabled",
        "type": "checkbox",
        "onchange": "saveGetitemSettings()",
    }

    if app_settings.get("getitem_enabled", True):
        enabled_attrs["checked"] = True

    return Div(
        Label(
            Input(**enabled_attrs),
            Span("捡取物品"),
            cls="getitem-toggle",
        ),
        Label(
            Span("捡取等待ms"),
            Input(
                id="getitem-step-wait-ms",
                type="number",
                min=str(api.GETITEM_MIN_STEP_WAIT_MS),
                max=str(api.GETITEM_MAX_STEP_WAIT_MS),
                step="100",
                value=str(app_settings.get("getitem_step_wait_ms", api.GETITEM_DEFAULT_STEP_WAIT_MS)),
                oninput="queueSaveGetitemSettings()",
                onchange="saveGetitemSettings()",
            ),
            cls="getitem-field",
        ),
        Div("", id="getitem-message", cls="getitem-message"),
        cls="getitem-controls",
    )


# 创建怪物名 Debug 图控制栏：默认关闭，需要每次运行后手动打开。
def create_monster_name_debug_controls(app_settings):
    enabled_attrs = {
        "id": "monster-name-debug-enabled",
        "type": "checkbox",
        "onchange": "saveMonsterNameDebugSettings()",
    }

    if app_settings.get("monster_name_debug_enabled", False):
        enabled_attrs["checked"] = True

    return Div(
        Label(
            Input(**enabled_attrs),
            Span("保存怪物名Debug图"),
            cls="monster-name-debug-toggle",
        ),
        Div("", id="monster-name-debug-message", cls="monster-name-debug-message"),
        cls="monster-name-debug-controls",
    )


# 创建巡逻地图面板：显示当前地图图片和网页点选出的巡逻点。
def create_patrol_panel():
    return Div(
        H3("巡逻地图"),
        Div(
            Div(
                Div(
                    Img(id="patrol-map-image", cls="patrol-map-image", alt="当前地图"),
                    Div(id="patrol-map-points", cls="patrol-map-points"),
                    id="patrol-map-view",
                    cls="patrol-map-view empty",
                ),
                Div("未加载地图", id="patrol-map-info", cls="patrol-map-info"),
                cls="patrol-map-column",
            ),
            Div(
                Table(
                    Thead(
                        Tr(
                            Th("序号"),
                            Th("逻辑坐标"),
                            Th("删除"),
                            Th("移动到"),
                            Th("选中"),
                        )
                    ),
                    Tbody(
                        Tr(
                            Td("暂无巡逻点", colspan="5"),
                        ),
                        id="patrol-point-body",
                    ),
                    cls="patrol-point-table",
                ),
                cls="patrol-table-column",
            ),
            cls="patrol-content",
        ),
        cls="patrol-panel",
    )


# 创建移动九宫格：生成某个动作对应的八方向移动按钮。
def create_move_pad(title, action):
    # 移动按钮配置：定义按钮显示文字和对应方向参数。
    buttons = [
        ("左上", "up_left"),
        ("上", "up"),
        ("右上", "up_right"),
        ("左", "left"),
        (title, ""),
        ("右", "right"),
        ("左下", "down_left"),
        ("下", "down"),
        ("右下", "down_right"),
    ]

    return Div(
        *[
            Button(label, disabled=True, cls="move-center")
            if not direction
            else Button(label, onclick=f"postApi('/api/move/{action}/{direction}')")
            for label, direction in buttons
        ],
        cls="move-pad",
    )


# 绑定账号后加载 settings.json，并清掉上一个账号留下的运行态提示。
def load_account_settings_after_bind(
    app_settings,
    auto_heal_state,
    pet_heal_state,
    idle_stuck_state,
    battle_runtime_state,
):
    result = api.load_current_account_settings(app_settings)
    api.apply_app_settings(app_settings)
    api.reset_auto_heal_state(auto_heal_state)
    api.reset_pet_heal_state(pet_heal_state)
    api.reset_idle_stuck_state(idle_stuck_state)
    api.reset_battle_runtime(battle_runtime_state, "账号设置已加载，清空战斗运行状态")
    api.reset_getitem_runtime_status()
    return result


# 设置接口更新成功后，把当前账号设置保存到 settings.json。
def save_account_settings_after_update(app_settings, result):
    if not result.get("success"):
        return result

    save_result = api.save_current_account_settings(app_settings)
    result["settings_save"] = save_result

    if save_result.get("message"):
        result["message"] = "；".join(
            message
            for message in [result.get("message", ""), save_result.get("message", "")]
            if message
        )

    if not save_result.get("success", False):
        result["success"] = False

    return result


# 获取状态：聚合玩家坐标、绑定窗口、应用设置、地图、巡逻点和状态机。
def get_status(
    player_info,
    app_settings,
    current_map=None,
    patrol_points=None,
    patrol_state=None,
    patrol_control=None,
    battle_control=None,
    current_state=None,
    auto_heal_state=None,
    pet_heal_state=None,
    idle_stuck_state=None,
    battle_runtime_state=None,
):
    return api.get_status(
        player_info=player_info,
        app_settings=app_settings,
        current_map=current_map,
        patrol_points=patrol_points,
        patrol_state=patrol_state,
        patrol_control=patrol_control,
        battle_control=battle_control,
        current_state=current_state,
        auto_heal_state=auto_heal_state,
        pet_heal_state=pet_heal_state,
        idle_stuck_state=idle_stuck_state,
        battle_runtime_state=battle_runtime_state,
    )


# 保存巡逻点：校验网页传来的逻辑坐标，写入全局或账号巡逻点文件。
def save_patrol_points(data, current_map, patrol_points, patrol_state, target):
    points_data = data.get("points", []) if isinstance(data, dict) else []

    try:
        result = api.save_patrol_points_for_map(
            current_map.get("name", ""),
            current_map,
            points_data,
            target,
        )
    except ValueError as error:
        return {
            "success": False,
            "message": str(error),
        }
    except Exception as error:
        return {
            "success": False,
            "message": f"保存巡逻点异常: {error}",
        }

    if not result["success"]:
        return result

    patrol_points[:] = result["points"]
    patrol_state["index"] = -1
    patrol_state["source"] = result.get("source", "")
    patrol_state["path"] = result.get("path", "")
    return result


# 截取地图并重置依赖旧地图的巡逻状态。
def capture_map_and_reset(
    update_frame,
    player_info,
    current_map,
    patrol_points,
    patrol_state,
    patrol_control,
):
    update_frame_safely(update_frame)
    result = api.bind_current_map_with_auto_open(player_info)

    if result["success"]:
        current_map.clear()
        current_map.update(result["map"])
        patrol_result = load_patrol_points_for_current_map(
            current_map,
            patrol_points,
            patrol_state,
            patrol_control,
        )
        result["patrol"] = patrol_result
        result["message"] = f"{result['message']}；{patrol_result['message']}"

    return result


# 按当前地图加载巡逻点：账号文件优先，没有则读全局。
def load_patrol_points_for_current_map(current_map, patrol_points, patrol_state, patrol_control):
    patrol_points.clear()
    patrol_state["index"] = -1
    patrol_state["source"] = ""
    patrol_state["path"] = ""
    patrol_control["enabled"] = False

    if not current_map:
        return {
            "success": True,
            "points": [],
            "message": "未加载地图，巡逻点已清空",
        }

    try:
        result = api.load_patrol_points_for_map(current_map.get("name", ""), current_map)
    except Exception as error:
        return {
            "success": False,
            "points": [],
            "message": f"读取巡逻点异常: {error}",
        }

    if result["success"]:
        patrol_points[:] = result.get("points", [])
        patrol_state["source"] = result.get("source", "")
        patrol_state["path"] = result.get("path", "")

    return result


# 移动到下一个巡逻点：复用状态模块里的单次巡逻移动逻辑。
def move_to_next_patrol_point(game_data):
    return patrol_move_state.move_once(game_data)


# 安全刷新帧：调用刷新函数并把异常写入日志。
def update_frame_safely(update_frame):
    try:
        update_frame()
    # 刷新异常对象：记录页面主动刷新失败的具体原因。
    except Exception as error:
        log.write(f"刷新帧异常: {error}")


# 写入怪物扫描明细日志：表格之外的调试信息保留在日志里。
def log_monster_scan_details(result):
    if not result.get("success"):
        return

    for monster in result.get("monsters", []):
        bar = monster.get("blood_bar", {})
        position = monster.get("position", {})
        logic = monster.get("logic", {})
        log.write(
            "怪物 "
            f"name={monster.get('name', '')} "
            f"distance={monster.get('distance', '')} "
            f"logic={logic.get('x', '')}:{logic.get('y', '')} "
            f"logic_distance={logic.get('distance', '')} "
            f"hp={monster.get('hp_percent', '')}% "
            f"name_text={monster.get('name_text', '')} "
            f"bar={bar.get('left')},{bar.get('top')},{bar.get('right')},{bar.get('bottom')} "
            f"pos={position.get('x')},{position.get('y')}"
        )


# 页面样式：定义本地控制台的布局、按钮和日志区域样式。
PAGE_STYLE = """
body {
    margin: 16px;
    font-family: "Microsoft YaHei", Arial, sans-serif;
    background: #f6f6f6;
}
h1 {
    margin: 0 0 12px 0;
    font-size: 24px;
}
.tabs {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 12px;
    border-bottom: 1px solid #ccc;
}
.tab-button {
    min-width: 82px;
    border: 1px solid #ccc;
    border-bottom: 0;
    background: #e9e9e9;
}
.tab-button.active {
    background: white;
    font-weight: bold;
}
.tab-panel {
    display: none;
}
.tab-panel.active {
    display: block;
}
.controls {
    display: grid;
    gap: 8px;
    margin-bottom: 12px;
}
.bind-controls {
    display: grid;
    grid-template-columns: minmax(150px, 220px) minmax(180px, 1fr) 96px 96px;
    gap: 8px;
    margin-bottom: 12px;
}
.auto-heal-controls {
    display: grid;
    grid-template-columns: minmax(110px, 130px) minmax(120px, 150px) minmax(130px, 160px) minmax(180px, 1fr);
    gap: 8px;
    align-items: center;
}
.pet-heal-controls {
    display: grid;
    grid-template-columns: minmax(110px, 130px) minmax(120px, 150px) minmax(110px, 140px) minmax(180px, 1fr);
    gap: 8px;
    align-items: center;
}
.idle-stuck-controls {
    display: grid;
    grid-template-columns: minmax(110px, 130px) minmax(120px, 150px) minmax(180px, 1fr);
    gap: 8px;
    align-items: center;
}
.battle-settings-controls {
    display: grid;
    grid-template-columns: minmax(140px, 170px) max-content minmax(180px, 1fr);
    gap: 8px;
    align-items: center;
}
.getitem-controls {
    display: grid;
    grid-template-columns: minmax(110px, 130px) minmax(130px, 160px) minmax(180px, 1fr);
    gap: 8px;
    align-items: center;
}
.monster-name-debug-controls {
    display: grid;
    grid-template-columns: minmax(180px, 220px) minmax(180px, 1fr);
    gap: 8px;
    align-items: center;
}
.map-corner-hotkey-controls {
    display: grid;
    grid-template-columns: minmax(180px, 240px) 96px minmax(180px, 1fr);
    gap: 8px;
    align-items: center;
}
.auto-heal-toggle,
.auto-heal-field,
.pet-heal-toggle,
.pet-heal-field,
.idle-stuck-toggle,
.idle-stuck-field,
.battle-settings-field,
.getitem-toggle,
.getitem-field,
.monster-name-debug-toggle,
.map-corner-hotkey-field {
    display: flex;
    align-items: center;
    gap: 6px;
    min-height: 34px;
    box-sizing: border-box;
    border: 1px solid #ddd;
    background: white;
    padding: 0 8px;
    font-size: 12px;
}
.auto-heal-toggle input,
.pet-heal-toggle input,
.idle-stuck-toggle input,
.getitem-toggle input,
.monster-name-debug-toggle input {
    width: 16px;
    height: 16px;
    padding: 0;
}
.auto-heal-field input,
.pet-heal-field input,
.idle-stuck-field input,
.battle-settings-field input,
.getitem-field input,
.map-corner-hotkey-field input {
    min-width: 0;
    flex: 1;
}
.battle-duration-field {
    justify-self: start;
}
.battle-settings-field .battle-duration-input {
    flex: 0 0 52px;
    width: 52px;
    padding: 0 4px;
    text-align: center;
}
.auto-heal-message,
.pet-heal-message,
.idle-stuck-message,
.battle-settings-message,
.getitem-message,
.monster-name-debug-message,
.map-corner-hotkey-message {
    min-height: 34px;
    box-sizing: border-box;
    border: 1px solid #ddd;
    background: white;
    padding: 8px;
    font-size: 12px;
    color: #555;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.utility-buttons {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
    gap: 8px;
}
input {
    height: 34px;
    box-sizing: border-box;
    padding: 0 10px;
    border: 1px solid #bbb;
    background: white;
    font-size: 12px;
}
.move-pads {
    display: grid;
    grid-template-columns: repeat(2, minmax(180px, 260px));
    gap: 8px;
}
.move-pad {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 6px;
}
button {
    height: 34px;
    font-size: 12px;
    cursor: pointer;
}
.move-center {
    cursor: default;
    font-weight: bold;
}
.status {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 8px;
    margin-bottom: 12px;
}
.status div {
    background: white;
    border: 1px solid #ddd;
    padding: 8px;
}
.patrol-panel {
    margin-bottom: 12px;
}
.patrol-panel h3 {
    margin: 0 0 8px 0;
    font-size: 14px;
}
.patrol-content {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 190px;
    gap: 12px;
    align-items: start;
}
.patrol-map-column {
    min-width: 0;
}
.patrol-table-column {
    min-width: 0;
    width: 190px;
    justify-self: end;
}
.patrol-map-view {
    position: relative;
    width: 100%;
    aspect-ratio: 550 / 350;
    box-sizing: border-box;
    border: 1px solid #bbb;
    background: #222;
    overflow: hidden;
    cursor: crosshair;
}
.patrol-map-view.empty {
    cursor: default;
}
.patrol-map-image {
    display: none;
    width: 100%;
    height: 100%;
    object-fit: fill;
    user-select: none;
    -webkit-user-drag: none;
}
.patrol-map-points {
    position: absolute;
    inset: 0;
    pointer-events: none;
}
.patrol-point {
    position: absolute;
    width: 9px;
    height: 9px;
    box-sizing: border-box;
    border: 1px solid #111;
    border-radius: 50%;
    background: white;
    transform: translate(-50%, -50%);
}
.patrol-point.active {
    outline: 2px solid #2b7cff;
}
.patrol-map-info {
    width: 100%;
    box-sizing: border-box;
    margin-top: 6px;
    padding: 6px 8px;
    border: 1px solid #ddd;
    background: white;
    font-size: 12px;
}
.patrol-point-table {
    width: 100%;
    min-width: 0;
}
.patrol-point-table th:first-child,
.patrol-point-table td:first-child {
    width: 56px;
    text-align: center;
}
.patrol-point-table tr.active td {
    background: #e8f1ff;
    font-weight: bold;
}
.monster-panel {
    margin-bottom: 12px;
}
.monster-panel h3 {
    margin: 0 0 8px 0;
    font-size: 14px;
}
table {
    width: 100%;
    border-collapse: collapse;
    background: white;
    border: 1px solid #ddd;
}
th,
td {
    border: 1px solid #ddd;
    padding: 8px;
    text-align: left;
    font-size: 12px;
}
th {
    background: #eee;
}
#log-box {
    height: 420px;
    overflow: auto;
    white-space: pre-wrap;
    background: #111;
    color: #eee;
    padding: 12px;
}
@media (max-width: 640px) {
    .bind-controls,
    .auto-heal-controls,
    .pet-heal-controls,
    .battle-settings-controls,
    .idle-stuck-controls,
    .getitem-controls,
    .monster-name-debug-controls,
    .map-corner-hotkey-controls,
    .utility-buttons,
    .status,
    .patrol-content {
        grid-template-columns: 1fr;
    }
    .patrol-table-column {
        width: 100%;
    }
}
"""


# 页面脚本：定义前端轮询、按钮请求和状态刷新逻辑。
PAGE_SCRIPT = """
const POLL_INTERVAL_MS = 500;
const MAP_IMAGE_WIDTH = 550;
const MAP_IMAGE_HEIGHT = 350;
let currentMonsters = [];
let currentMap = null;
let currentMapUrl = "";
let patrolPoints = [];
let patrolIndex = -1;
let patrolDirty = false;
let appRestarting = false;

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function switchTab(tabId) {
    for (const button of document.querySelectorAll(".tab-button")) {
        const active = button.dataset.tab === tabId;
        button.classList.toggle("active", active);
        button.setAttribute("aria-selected", active ? "true" : "false");
    }

    for (const panel of document.querySelectorAll(".tab-panel")) {
        panel.classList.toggle("active", panel.dataset.tabPanel === tabId);
    }
}

async function postApi(url) {
    const response = await fetch(url, {method: "POST"});
    const data = await response.json();
    console.log(data);
    await refreshStatus();
    await refreshLogs();
}

async function bindWindow() {
    const input = document.getElementById("bind-keyword");
    const keyword = input.value.trim();
    const params = new URLSearchParams({keyword});

    await postApi("/api/window/bind?" + params.toString());

    if (!keyword) {
        input.focus();
    }
}

function selectAccountFromDropdown() {
    const select = document.getElementById("account-select");
    const input = document.getElementById("bind-keyword");

    if (select.value) {
        input.value = select.value;
    }
}

async function unbindWindow() {
    await postApi("/api/window/unbind");
}

async function restartApp() {
    if (!confirm("确定要重启程序并重新加载 Python 代码吗？")) {
        return;
    }

    appRestarting = true;
    const response = await fetch("/api/app/restart", {method: "POST"});
    const data = await response.json();
    console.log(data);
    await waitForRestartAndReload();
}

async function waitForRestartAndReload() {
    await sleep(1000);
    let sawOffline = false;
    const startedAt = Date.now();

    for (let i = 0; i < 30; i++) {
        try {
            const response = await fetch("/api/status", {cache: "no-store"});

            if (response.ok && (sawOffline || Date.now() - startedAt > 4000)) {
                window.location.reload();
                return;
            }
        } catch (error) {
            sawOffline = true;
            console.log(error);
        }

        await sleep(1000);
    }

    window.location.reload();
}

async function takeScreenshot() {
    const response = await fetch("/api/screenshot", {method: "POST"});
    const data = await response.json();
    console.log(data);
    await refreshStatus();
    await refreshLogs();
}

async function pressKeyboard(key) {
    const params = new URLSearchParams({key});
    await postApi("/api/keyboard/press?" + params.toString());
}

async function saveAutoHealSettings() {
    const enabled = document.getElementById("auto-heal-enabled").checked;
    const threshold = document.getElementById("auto-heal-threshold").value;
    const interval = document.getElementById("auto-heal-interval").value;
    const response = await fetch("/api/auto-heal/settings", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            enabled,
            threshold_percent: threshold,
            interval_ms: interval,
        }),
    });
    const data = await response.json();
    console.log(data);
    applyStatus(data.status || {});
    await refreshLogs();
}

async function saveBattleSettings() {
    const limit = document.getElementById("no-monster-scan-limit").value;
    const duration = document.getElementById("battle-duration-seconds").value;
    const response = await fetch("/api/battle/settings", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            no_monster_scan_limit: limit,
            battle_duration_seconds: duration,
        }),
    });
    const data = await response.json();
    console.log(data);
    applyStatus(data.status || {});
    await refreshLogs();
}

async function savePetHealSettings() {
    const enabled = document.getElementById("pet-heal-enabled").checked;
    const threshold = document.getElementById("pet-heal-threshold").value;
    const key = document.getElementById("pet-heal-key").value;
    const response = await fetch("/api/pet-heal/settings", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            enabled,
            threshold_percent: threshold,
            key,
        }),
    });
    const data = await response.json();
    console.log(data);
    applyStatus(data.status || {});
    await refreshLogs();
}

async function saveIdleStuckSettings() {
    const enabled = document.getElementById("idle-stuck-enabled").checked;
    const seconds = document.getElementById("idle-stuck-seconds").value;
    const response = await fetch("/api/idle-stuck/settings", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            enabled,
            seconds,
        }),
    });
    const data = await response.json();
    console.log(data);
    applyStatus(data.status || {});
    await refreshLogs();
}

let getitemSettingsTimer = null;

function queueSaveGetitemSettings() {
    const stepWaitMs = document.getElementById("getitem-step-wait-ms").value;

    if (stepWaitMs === "") {
        return;
    }

    clearTimeout(getitemSettingsTimer);
    getitemSettingsTimer = setTimeout(saveGetitemSettings, 300);
}

async function saveGetitemSettings() {
    clearTimeout(getitemSettingsTimer);
    const enabled = document.getElementById("getitem-enabled").checked;
    const stepWaitMs = document.getElementById("getitem-step-wait-ms").value;
    const response = await fetch("/api/getitem/settings", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            enabled,
            step_wait_ms: stepWaitMs,
        }),
    });
    const data = await response.json();
    console.log(data);
    applyStatus(data.status || {});
    await refreshLogs();
}

async function saveMonsterNameDebugSettings() {
    const enabled = document.getElementById("monster-name-debug-enabled").checked;
    const response = await fetch("/api/monster-name-debug/settings", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({enabled}),
    });
    const data = await response.json();
    console.log(data);
    applyStatus(data.status || {});
    await refreshLogs();
}

async function saveMapCornerHotkeySettings() {
    const hotkey = document.getElementById("map-corner-hotkey").value;
    const response = await fetch("/api/map/rect-corner/hotkey", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({hotkey}),
    });
    const data = await response.json();
    console.log(data);
    applyStatus(data.status || {});
    await refreshLogs();
}

async function captureMap() {
    const response = await fetch("/api/map/capture", {method: "POST"});
    const data = await response.json();
    console.log(data);
    applyStatus(data.status || {});
    await refreshLogs();
}

async function savePatrolPoints(target) {
    const response = await fetch("/api/patrol/save/" + target, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({points: patrolPoints}),
    });
    const data = await response.json();
    console.log(data);

    if (data.success) {
        patrolDirty = false;
    }

    applyStatus(data.status || {});
    await refreshLogs();
}

async function moveToNextPatrolPoint() {
    const response = await fetch("/api/patrol/next", {method: "POST"});
    const data = await response.json();
    console.log(data);
    applyStatus(data.status || {});
    updatePatrolIndexFromResponse(data);
    await refreshLogs();
}

async function moveToCurrentPatrolPoint() {
    const response = await fetch("/api/patrol/current", {method: "POST"});
    const data = await response.json();
    console.log(data);
    applyStatus(data.status || {});
    updatePatrolIndexFromResponse(data);
    await refreshLogs();
}

async function moveToPatrolPoint(index) {
    const response = await fetch("/api/patrol/move?index=" + encodeURIComponent(String(index)), {method: "POST"});
    const data = await response.json();
    console.log(data);
    applyStatus(data.status || {});
    updatePatrolIndexFromResponse(data);
    await refreshLogs();
}

async function selectPatrolPoint(index) {
    const response = await fetch("/api/patrol/select?index=" + encodeURIComponent(String(index)), {method: "POST"});
    const data = await response.json();
    console.log(data);
    applyStatus(data.status || {});
    updatePatrolIndexFromResponse(data);
    await refreshLogs();
}

function updatePatrolIndexFromResponse(data) {
    if (!data || !data.success || data.index === undefined || data.index === null) return;

    patrolIndex = Number(data.index);
    renderPatrolPoints();
    renderPatrolPointTable();
    updatePatrolMapInfo();
}

function deletePatrolPoint(index) {
    if (index < 0 || index >= patrolPoints.length) return;

    patrolPoints.splice(index, 1);

    if (patrolIndex === index) {
        patrolIndex = -1;
    } else if (patrolIndex > index) {
        patrolIndex -= 1;
    }

    patrolDirty = true;
    renderPatrolPoints();
    renderPatrolPointTable();
    updatePatrolMapInfo();
}

async function startPatrol() {
    const response = await fetch("/api/patrol/start", {method: "POST"});
    const data = await response.json();
    console.log(data);
    applyStatus(data.status || {});
    await refreshLogs();
}

async function stopPatrol() {
    const response = await fetch("/api/patrol/stop", {method: "POST"});
    const data = await response.json();
    console.log(data);
    applyStatus(data.status || {});
    await refreshLogs();
}

async function startBattle() {
    const response = await fetch("/api/battle/start", {method: "POST"});
    const data = await response.json();
    console.log(data);
    applyStatus(data.status || {});
    await refreshLogs();
}

async function stopBattle() {
    const response = await fetch("/api/battle/stop", {method: "POST"});
    const data = await response.json();
    console.log(data);
    applyStatus(data.status || {});
    await refreshLogs();
}

async function scanMonsters(url = "/api/monsters/scan") {
    const response = await fetch(url, {method: "POST"});
    const data = await response.json();
    console.log(data);
    updateMonsterTable(data.monsters || []);
    await refreshStatus();
    await refreshLogs();
}

function updateMonsterTable(monsters) {
    currentMonsters = monsters;
    const body = document.getElementById("monster-body");
    body.textContent = "";

    if (!monsters.length) {
        const row = document.createElement("tr");
        const cell = document.createElement("td");
        cell.colSpan = 5;
        cell.textContent = "暂无数据";
        row.appendChild(cell);
        body.appendChild(row);
        return;
    }

    for (const monster of monsters) {
        const row = document.createElement("tr");
        row.dataset.monsterId = String(monster.id);
        appendCell(row, monster.name || "未识别", "name");
        appendCell(row, String(monster.distance ?? ""));
        appendCell(row, String(monster.hp_percent ?? 100) + "%");
        appendCell(row, getMonsterPositionText(monster), "position");
        appendActionCell(row, monster);
        body.appendChild(row);
    }
}

function appendCell(row, text, role = "") {
    const cell = document.createElement("td");
    cell.textContent = text;
    if (role) {
        cell.dataset.role = role;
    }
    row.appendChild(cell);
}

function appendActionCell(row, monster) {
    const cell = document.createElement("td");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "识别名称";
    button.onclick = () => recognizeMonsterName(monster.id);
    cell.appendChild(button);
    row.appendChild(cell);
}

function getMonsterPositionText(monster) {
    const position = monster.position || {};
    return String(position.x ?? "") + "," + String(position.y ?? "");
}

async function recognizeMonsterName(id) {
    const monster = currentMonsters.find((item) => item.id === id);
    if (!monster || !monster.position) return;

    const row = document.querySelector(`tr[data-monster-id="${id}"]`);
    const button = row ? row.querySelector("button") : null;

    if (button) {
        button.disabled = true;
        button.textContent = "识别中";
    }

    const params = new URLSearchParams({
        x: String(monster.position.x),
        y: String(monster.position.y),
    });
    const bar = monster.blood_bar || {};

    for (const key of ["left", "top", "right", "bottom"]) {
        if (bar[key] !== undefined) {
            params.set("bar_" + key, String(bar[key]));
        }
    }

    try {
        const response = await fetch("/api/monsters/name?" + params.toString(), {method: "POST"});
        const data = await response.json();
        console.log(data);

        if (data.name) {
            monster.name = data.name;
            updateMonsterNameCell(id, data.name);
        }
        if (data.position && data.position.x !== undefined) {
            monster.position = data.position;
            updateMonsterPositionCell(id, getMonsterPositionText(monster));
        }
        if (data.blood_bar && data.blood_bar.left !== undefined) {
            monster.blood_bar = data.blood_bar;
        }

        await refreshLogs();
    } finally {
        if (button) {
            button.disabled = false;
            button.textContent = "识别名称";
        }
    }
}

function updateMonsterNameCell(id, name) {
    const row = document.querySelector(`tr[data-monster-id="${id}"]`);
    const cell = row ? row.querySelector('td[data-role="name"]') : null;

    if (cell) {
        cell.textContent = name || "未识别";
    }
}

function updateMonsterPositionCell(id, text) {
    const row = document.querySelector(`tr[data-monster-id="${id}"]`);
    const cell = row ? row.querySelector('td[data-role="position"]') : null;

    if (cell) {
        cell.textContent = text;
    }
}

function setupPatrolMapEvents() {
    const view = document.getElementById("patrol-map-view");
    if (!view) return;

    view.addEventListener("click", addPatrolPointFromEvent);
    view.addEventListener("contextmenu", clearPatrolPointsFromEvent);
}

function addPatrolPointFromEvent(event) {
    if (!currentMap || !currentMap.max_x || !currentMap.max_y) return;

    const view = document.getElementById("patrol-map-view");
    const rect = view.getBoundingClientRect();
    const pixelX = clampNumber((event.clientX - rect.left) / rect.width * (MAP_IMAGE_WIDTH - 1), 0, MAP_IMAGE_WIDTH - 1);
    const pixelY = clampNumber((event.clientY - rect.top) / rect.height * (MAP_IMAGE_HEIGHT - 1), 0, MAP_IMAGE_HEIGHT - 1);
    const point = mapPixelToLogic(pixelX, pixelY);

    patrolPoints.push(point);
    patrolIndex = -1;
    patrolDirty = true;
    renderPatrolPoints();
    renderPatrolPointTable();
    updatePatrolMapInfo();
}

function clearPatrolPointsFromEvent(event) {
    event.preventDefault();

    if (!currentMap) return;

    patrolPoints = [];
    patrolIndex = -1;
    patrolDirty = true;
    renderPatrolPoints();
    renderPatrolPointTable();
    updatePatrolMapInfo();
}

function applyStatus(data) {
    if (!data || !data.player) return;

    const boundTitle = data.bound_window.title || "";
    document.getElementById("map-name").textContent = data.player.map_name;
    document.getElementById("map-raw").textContent = data.player.map_raw || "-";
    document.getElementById("coordinate").textContent = data.player.x + ":" + data.player.y;
    document.getElementById("bound-title").textContent = boundTitle || "未绑定";
    document.getElementById("state-name").textContent = data.state ? data.state.name : "idle";
    document.getElementById("patrol-enabled").textContent = data.patrol && data.patrol.enabled ? "开" : "关";
    updateBattlePanel(data.battle || {});
    updateAccountsPanel(data.accounts || {});
    updateMonsterFilterPanel(data.monster_filter || {});
    updateMonsterNameColorPanel(data.monster_name_colors || {});
    updateItemFilterPanel(data.getitem || {});
    updateItemNameColorPanel(data.getitem || {});
    updateAutoHealPanel(data.auto_heal || {});
    updatePetHealPanel(data.pet_heal || {});
    updateIdleStuckPanel(data.idle_stuck || {});
    updateGetitemPanel(data.getitem || {});
    updateMonsterNameDebugPanel(data.settings || {});
    updateMapCornerHotkeyPanel(data.settings || {});

    const oldMapUrl = currentMapUrl;
    updatePatrolMap(data.map || {});

    if (data.patrol && (!patrolDirty || currentMapUrl !== oldMapUrl)) {
        patrolPoints = data.patrol.points || [];
        patrolIndex = data.patrol.index ?? -1;
        patrolDirty = false;
    }

    renderPatrolPoints();
    renderPatrolPointTable();
    updatePatrolMapInfo();
}

function updateAccountsPanel(accounts) {
    const current = accounts.current || "";
    const items = accounts.items || [];
    const configDir = accounts.config_dir || "";
    document.getElementById("account-current").textContent = current || "未选择";
    document.getElementById("account-config-dir").textContent = configDir || "-";

    const select = document.getElementById("account-select");
    const oldValue = select.value;
    const nextValue = current || oldValue;
    select.textContent = "";

    const emptyOption = document.createElement("option");
    emptyOption.value = "";
    emptyOption.textContent = "选择账号";
    select.appendChild(emptyOption);

    for (const item of items) {
        const option = document.createElement("option");
        option.value = item;
        option.textContent = item;
        select.appendChild(option);
    }

    select.value = items.includes(nextValue) ? nextValue : "";
}

function updateMonsterFilterPanel(monsterFilter) {
    const count = monsterFilter.count ?? 0;
    const keywords = monsterFilter.keywords || [];
    const preview = keywords.slice(0, 6).join("、");
    const suffix = keywords.length > 6 ? "..." : "";
    const detail = preview ? ` (${preview}${suffix})` : "";
    document.getElementById("monster-filter").textContent = `${count} 个${detail}`;
}

function updateMonsterNameColorPanel(colorConfig) {
    const count = colorConfig.count ?? 0;
    const colors = colorConfig.colors || [];
    const preview = colors.slice(0, 4).join("、");
    const suffix = colors.length > 4 ? "..." : "";
    const detail = preview ? ` (${preview}${suffix})` : "";
    document.getElementById("monster-name-colors").textContent = `${count} 个${detail}`;
}

function updateItemFilterPanel(getitem) {
    const itemFilter = getitem.item_filter || {};
    const count = itemFilter.count ?? 0;
    const keywords = itemFilter.keywords || [];
    const preview = keywords.slice(0, 6).join("、");
    const suffix = keywords.length > 6 ? "..." : "";
    const detail = preview ? ` (${preview}${suffix})` : "";
    document.getElementById("item-filter").textContent = `${count} 个${detail}`;
}

function updateItemNameColorPanel(getitem) {
    const colorConfig = getitem.item_name_colors || {};
    const count = colorConfig.count ?? 0;
    const colors = colorConfig.colors || [];
    const preview = colors.slice(0, 4).join("、");
    const suffix = colors.length > 4 ? "..." : "";
    const detail = preview ? ` (${preview}${suffix})` : "";
    document.getElementById("item-name-colors").textContent = `${count} 个${detail}`;
}

function updateAutoHealPanel(autoHeal) {
    const enabled = !!autoHeal.enabled;
    const lastHp = autoHeal.last_hp_percent;
    const hpText = lastHp === "" || lastHp === null || lastHp === undefined ? "-" : String(lastHp) + "%";
    const stateText = enabled ? "开" : "关";
    const triggeredText = autoHeal.triggered_low ? " 已触发" : "";
    document.getElementById("auto-heal-enabled-text").textContent = stateText;
    document.getElementById("auto-heal-enabled").checked = enabled;
    setInputValueIfIdle("auto-heal-threshold", autoHeal.threshold_percent ?? 85);
    setInputValueIfIdle("auto-heal-interval", autoHeal.interval_ms ?? 1000);
    document.getElementById("auto-heal-message").textContent =
        stateText + " hp=" + hpText + " threshold=" + (autoHeal.threshold_percent ?? 85) + "%" + triggeredText
        + (autoHeal.last_message ? " " + autoHeal.last_message : "");
}

function updatePetHealPanel(petHeal) {
    const enabled = !!petHeal.enabled;
    const stateText = enabled ? "开" : "关";
    const lastHp = petHeal.last_hp_percent;
    const hpText = lastHp === "" || lastHp === null || lastHp === undefined ? "-" : String(lastHp) + "%";
    const target = petHeal.last_target || {};
    const logic = target.logic || {};
    const logicText = logic.x === undefined ? "-" : String(logic.x) + ":" + String(logic.y);

    document.getElementById("pet-heal-enabled").checked = enabled;
    setInputValueIfIdle("pet-heal-threshold", petHeal.threshold_percent ?? 85);
    setInputValueIfIdle("pet-heal-key", petHeal.key ?? "F1");
    document.getElementById("pet-heal-message").textContent =
        stateText
        + " hp=" + hpText
        + " threshold=" + String(petHeal.threshold_percent ?? 85) + "%"
        + " key=" + String(petHeal.key ?? "F1")
        + " target=" + (target.name || "-")
        + " logic=" + logicText
        + (petHeal.last_message ? " " + petHeal.last_message : "");
}

function updateBattlePanel(battle) {
    const enabled = !!battle.enabled;
    const stateText = enabled ? "开" : "关";
    const count = battle.no_monster_count ?? 0;
    const limit = battle.no_monster_scan_limit ?? 3;
    const duration = battle.battle_duration_seconds ?? 5;
    const remaining = battle.battle_remaining_seconds ?? 0;
    const target = battle.current_target || {};
    const position = target.position || {};
    const positionText = position.x === undefined ? "-" : String(position.x) + "," + String(position.y);
    const targetName = target.name || target.matched_keyword || "-";
    const hpText = target.hp_percent === undefined || target.hp_percent === "" ? "-" : String(target.hp_percent) + "%";

    document.getElementById("battle-enabled").textContent = stateText;
    document.getElementById("battle-no-monster").textContent = String(count) + "/" + String(limit);
    setInputValueIfIdle("no-monster-scan-limit", limit);
    setInputValueIfIdle("battle-duration-seconds", duration);
    document.getElementById("battle-settings-message").textContent =
        "无怪=" + String(count) + "/" + String(limit)
        + " 战斗=" + String(duration) + "s"
        + " 剩余=" + String(remaining) + "s"
        + " target=" + targetName
        + " pos=" + positionText
        + " hp=" + hpText
        + (battle.last_no_monster_reason ? " " + battle.last_no_monster_reason : "")
        + (battle.last_message ? " " + battle.last_message : "");
}

function updateIdleStuckPanel(idleStuck) {
    const enabled = !!idleStuck.enabled;
    const stateText = enabled ? "开" : "关";
    const coordinate = idleStuck.coordinate || {};
    const coordinateText = coordinate.x === undefined
        ? "-"
        : String(coordinate.map_name || "未知") + " " + String(coordinate.x) + ":" + String(coordinate.y);
    document.getElementById("idle-stuck-enabled-text").textContent = stateText;
    document.getElementById("idle-stuck-enabled").checked = enabled;
    setInputValueIfIdle("idle-stuck-seconds", idleStuck.seconds ?? 30);
    document.getElementById("idle-stuck-message").textContent =
        stateText + " coordinate=" + coordinateText
        + " stationary=" + String(idleStuck.stationary_seconds ?? 0) + "s"
        + " threshold=" + String(idleStuck.seconds ?? 30) + "s"
        + (idleStuck.last_message ? " " + idleStuck.last_message : "");
}

function updateGetitemPanel(getitem) {
    const enabled = !!getitem.enabled;
    const stateText = enabled ? "开" : "关";
    const target = getitem.last_target || {};
    const targetText = target.keyword
        ? target.keyword
            + " item=" + String(target.item_x ?? target.click_x ?? "") + "," + String(target.item_y ?? target.click_y ?? "")
            + " dir=" + String(target.direction || "-")
            + " move=" + String(target.move_click_x ?? "") + "," + String(target.move_click_y ?? "")
        : "-";
    document.getElementById("getitem-enabled-text").textContent = stateText;
    document.getElementById("getitem-enabled").checked = enabled;
    setInputValueIfIdle("getitem-step-wait-ms", getitem.step_wait_ms ?? 100);
    document.getElementById("getitem-message").textContent =
        stateText + " wait=" + String(getitem.step_wait_ms ?? 100) + "ms"
        + " target=" + targetText
        + (getitem.last_message ? " " + getitem.last_message : "");
}

function updateMapCornerHotkeyPanel(settings) {
    const hotkey = settings.map_corner_hotkey ?? "F8";
    const hotkeyText = hotkey ? String(hotkey) : "禁用";
    setInputValueIfIdle("map-corner-hotkey", hotkey);
    document.getElementById("map-corner-hotkey-message").textContent =
        "快捷键=" + hotkeyText
        + (settings.map_corner_hotkey_last_message ? " " + settings.map_corner_hotkey_last_message : "");
}

function updateMonsterNameDebugPanel(settings) {
    const enabled = !!settings.monster_name_debug_enabled;
    const stateText = enabled ? "开" : "关";
    document.getElementById("monster-name-debug-enabled-text").textContent = stateText;
    document.getElementById("monster-name-debug-enabled").checked = enabled;
    document.getElementById("monster-name-debug-message").textContent = "Debug图保存=" + stateText;
}

function setInputValueIfIdle(id, value) {
    const input = document.getElementById(id);

    if (document.activeElement !== input) {
        input.value = String(value);
    }
}

function updatePatrolMap(mapInfo) {
    const image = document.getElementById("patrol-map-image");
    const view = document.getElementById("patrol-map-view");

    if (!mapInfo || !mapInfo.url) {
        currentMap = null;
        currentMapUrl = "";
        image.removeAttribute("src");
        image.style.display = "none";
        view.classList.add("empty");
        return;
    }

    currentMap = mapInfo;
    currentMapUrl = mapInfo.url;

    if (image.getAttribute("src") !== mapInfo.url) {
        image.src = mapInfo.url;
    }

    image.style.display = "block";
    view.classList.remove("empty");
}

function renderPatrolPoints() {
    const container = document.getElementById("patrol-map-points");
    container.textContent = "";

    if (!currentMap) return;

    patrolPoints.forEach((point, index) => {
        const pixel = logicToMapPixel(point.x, point.y);
        const marker = document.createElement("div");
        marker.className = "patrol-point" + (index === patrolIndex ? " active" : "");
        marker.style.left = String(pixel.x / (MAP_IMAGE_WIDTH - 1) * 100) + "%";
        marker.style.top = String(pixel.y / (MAP_IMAGE_HEIGHT - 1) * 100) + "%";
        marker.title = String(point.x) + ":" + String(point.y);
        container.appendChild(marker);
    });
}

function renderPatrolPointTable() {
    const body = document.getElementById("patrol-point-body");
    body.textContent = "";

    if (!patrolPoints.length) {
        const row = document.createElement("tr");
        const cell = document.createElement("td");
        cell.colSpan = 5;
        cell.textContent = "暂无巡逻点";
        row.appendChild(cell);
        body.appendChild(row);
        return;
    }

    patrolPoints.forEach((point, index) => {
        const row = document.createElement("tr");

        if (index === patrolIndex) {
            row.className = "active";
        }

        appendCell(row, String(index + 1));
        appendCell(row, String(point.x) + ":" + String(point.y));
        appendPatrolActionCell(row, "删除", () => deletePatrolPoint(index));
        appendPatrolActionCell(row, "移动到", () => moveToPatrolPoint(index));
        appendPatrolActionCell(row, "选中", () => selectPatrolPoint(index));
        body.appendChild(row);
    });
}

function appendPatrolActionCell(row, label, onClick) {
    const cell = document.createElement("td");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.onclick = onClick;
    cell.appendChild(button);
    row.appendChild(cell);
}

function updatePatrolMapInfo() {
    const info = document.getElementById("patrol-map-info");

    if (!currentMap) {
        info.textContent = "未加载地图";
        return;
    }

    const dirtyText = patrolDirty ? " 未保存" : "";
    info.textContent = "地图: " + (currentMap.name || "-")
        + " 最大坐标: " + currentMap.max_x + ":" + currentMap.max_y
        + " 巡逻点: " + patrolPoints.length + dirtyText;
}

function mapPixelToLogic(pixelX, pixelY) {
    const maxX = Number(currentMap.max_x || 0);
    const maxY = Number(currentMap.max_y || 0);

    return {
        x: Math.round(clampNumber(pixelX, 0, MAP_IMAGE_WIDTH - 1) * maxX / (MAP_IMAGE_WIDTH - 1)),
        y: Math.round(clampNumber(pixelY, 0, MAP_IMAGE_HEIGHT - 1) * maxY / (MAP_IMAGE_HEIGHT - 1)),
    };
}

function logicToMapPixel(logicX, logicY) {
    const maxX = Number(currentMap.max_x || 1);
    const maxY = Number(currentMap.max_y || 1);

    return {
        x: Math.round(clampNumber(logicX, 0, maxX) * (MAP_IMAGE_WIDTH - 1) / maxX),
        y: Math.round(clampNumber(logicY, 0, maxY) * (MAP_IMAGE_HEIGHT - 1) / maxY),
    };
}

function clampNumber(value, minimum, maximum) {
    return Math.max(minimum, Math.min(maximum, Number(value)));
}

async function refreshStatus() {
    if (appRestarting) return;
    if (refreshStatus.busy) return;
    refreshStatus.busy = true;

    try {
        const frameResponse = await fetch("/api/status");
        const data = await frameResponse.json();
        applyStatus(data);
    } finally {
        refreshStatus.busy = false;
    }
}

async function refreshLogs() {
    if (appRestarting) return;
    const response = await fetch("/api/logs");
    const text = await response.text();
    const box = document.getElementById("log-box");
    box.textContent = text;
    box.scrollTop = box.scrollHeight;
}

setInterval(refreshStatus, POLL_INTERVAL_MS);
setInterval(refreshLogs, POLL_INTERVAL_MS);
window.onload = async function() {
    setupPatrolMapEvents();
    await refreshStatus();
    await refreshLogs();
};
"""

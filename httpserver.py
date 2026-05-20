from fasthtml.common import *
from starlette.responses import JSONResponse, PlainTextResponse
import uvicorn

import api
import dm
import log


# 服务监听地址：限制 HTTP 控制台只在本机访问。
SERVER_HOST = "127.0.0.1"
# 服务监听端口：定义本地 HTTP 控制台的固定端口。
SERVER_PORT = 8765


# 运行 HTTP 服务：创建应用并启动 uvicorn 本地服务。
def run_server(player_info, update_frame, app_settings):
    # FastHTML 应用：承载页面和所有 API 路由。
    app = create_server(player_info, update_frame, app_settings)
    log.write_console(f"HTTP 服务启动: http://{SERVER_HOST}:{SERVER_PORT}")
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, log_level="warning")


# 创建 HTTP 服务：注册控制台页面和后端操作 API。
def create_server(player_info, update_frame, app_settings):
    # 应用和路由器：由 FastHTML 创建页面应用和路由装饰器。
    app, rt = fast_app()

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
                H2("httpserver"),
                Div(
                    *create_buttons(app_settings),
                    cls="controls",
                ),
                Div(
                    Div("绑定窗口: ", Span("未绑定", id="bound-title")),
                    Div("地图: ", Span(player_info["map_name"], id="map-name")),
                    Div("坐标: ", Span(f"{player_info['x']}:{player_info['y']}", id="coordinate")),
                    cls="status",
                ),
                Pre("", id="log-box"),
            ),
        )

    # 状态读取接口：返回玩家、窗口绑定和应用设置状态。
    @rt("/api/status")
    def get():
        return JSONResponse(get_status(player_info, app_settings))

    # 帧状态接口：兼容前端 POST 轮询并返回当前状态。
    @rt("/api/frame")
    def post():
        return JSONResponse(get_status(player_info, app_settings))

    # OP 启动接口：初始化 OP 并返回版本与结果消息。
    @rt("/api/dm/start")
    def post():
        # OP 启动结果：保存初始化成功状态、版本和说明。
        success, version, message = dm.start_dm()
        log.write(message)
        return JSONResponse({
            "success": success,
            "version": version,
            "message": message,
        })

    # 窗口绑定接口：按标题关键字查找并绑定游戏窗口。
    @rt("/api/window/bind")
    def post(keyword: str = ""):
        # 绑定结果：记录窗口绑定是否成功、标题和说明消息。
        success, title, message = dm.bind_window_by_title(keyword)
        log.write(message)
        return JSONResponse({
            "success": success,
            "title": title,
            "message": message,
            "status": get_status(player_info, app_settings),
        })

    # 窗口解绑接口：解除当前绑定窗口并返回最新状态。
    @rt("/api/window/unbind")
    def post():
        # 解绑结果：记录窗口解绑是否成功、标题和说明消息。
        success, title, message = dm.unbind_window()
        log.write(message)
        return JSONResponse({
            "success": success,
            "title": title,
            "message": message,
            "status": get_status(player_info, app_settings),
        })

    # 坐标读取接口：主动刷新一次 OCR 坐标并返回页面状态。
    @rt("/api/coordinate/read")
    def post():
        update_frame_safely(update_frame)
        return JSONResponse({
            "map_name": player_info["map_name"],
            "x": player_info["x"],
            "y": player_info["y"],
            "status": get_status(player_info, app_settings),
        })

    # 移动接口：根据动作和方向触发一次角色移动点击。
    @rt("/api/move/{action}/{direction}")
    def post(action: str, direction: str):
        # 移动结果：保存点击移动的成功状态和诊断消息。
        result = api.move_player(action, direction)
        log.write(result["message"])
        return JSONResponse({
            "move": result,
            "status": get_status(player_info, app_settings),
        })

    # Overlay 切换接口：反转点击提示开关并同步到底层模块。
    @rt("/api/overlay/toggle")
    def post():
        # Overlay 开关设置：反转当前点击提示启用状态。
        app_settings["overlay_enabled"] = not app_settings["overlay_enabled"]
        dm.set_overlay_enabled(app_settings["overlay_enabled"])
        # Overlay 状态文本：把布尔开关转换为用户可读中文状态。
        state = "开启" if app_settings["overlay_enabled"] else "关闭"
        # Overlay 返回消息：描述本次切换后的提示状态。
        message = f"点击提示 Overlay 已{state}"
        log.write(message)
        return JSONResponse({
            "success": True,
            "message": message,
            "status": get_status(player_info, app_settings),
        })

    # 截图接口：截取当前绑定窗口并返回截图保存路径。
    @rt("/api/screenshot")
    def post():
        # 截图结果：记录截图是否成功、路径和说明消息。
        success, path, message = dm.capture_bound_window()
        log.write(message)
        return JSONResponse({
            "success": success,
            "path": path,
            "message": message,
            "status": get_status(player_info, app_settings),
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

    return app


# 创建控制按钮：生成绑定、工具和移动控制区域。
def create_buttons(app_settings):
    # 工具按钮列表：保存坐标刷新、截图和 Overlay 切换按钮。
    utility_buttons = [
        Button("测试坐标", onclick="postApi('/api/coordinate/read')"),
        Button("截图", onclick="takeScreenshot()"),
        Button(get_overlay_button_text(app_settings), id="overlay-button", onclick="toggleOverlay()"),
    ]

    return [
        Div(
            Input(
                id="bind-keyword",
                type="text",
                value="闪电侠",
                placeholder="窗口标题关键字",
                autocomplete="off",
            ),
            Button("绑定", onclick="bindWindow()"),
            Button("解除绑定", onclick="unbindWindow()"),
            cls="bind-controls",
        ),
        Div(*utility_buttons, cls="utility-buttons"),
        Div(
            create_move_pad("走", "walk"),
            create_move_pad("跑", "run"),
            cls="move-pads",
        ),
    ]


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


# 获取状态：聚合玩家坐标、绑定窗口和应用设置。
def get_status(player_info, app_settings):
    # 绑定窗口状态：读取当前窗口绑定信息用于 API 返回。
    bound = dm.get_bound_window()

    return {
        "player": {
            "map_name": player_info["map_name"],
            "x": player_info["x"],
            "y": player_info["y"],
        },
        "bound_window": bound,
        "settings": {
            "overlay_enabled": app_settings["overlay_enabled"],
        },
    }


# 获取 Overlay 按钮文本：根据开关状态生成按钮显示文案。
def get_overlay_button_text(app_settings):
    return "Overlay: 开" if app_settings["overlay_enabled"] else "Overlay: 关"


# 安全刷新帧：调用刷新函数并把异常写入日志。
def update_frame_safely(update_frame):
    try:
        update_frame()
    # 刷新异常对象：记录页面主动刷新失败的具体原因。
    except Exception as error:
        log.write(f"刷新帧异常: {error}")


# 页面样式：定义本地控制台的布局、按钮和日志区域样式。
PAGE_STYLE = """
body {
    margin: 16px;
    font-family: "Microsoft YaHei", Arial, sans-serif;
    background: #f6f6f6;
}
h2 {
    margin: 0 0 12px 0;
}
.controls {
    display: grid;
    gap: 8px;
    margin-bottom: 12px;
}
.bind-controls {
    display: grid;
    grid-template-columns: minmax(180px, 1fr) 96px 96px;
    gap: 8px;
}
.utility-buttons {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
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
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
    margin-bottom: 12px;
}
.status div {
    background: white;
    border: 1px solid #ddd;
    padding: 8px;
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
    .utility-buttons,
    .status {
        grid-template-columns: 1fr;
    }
}
"""


# 页面脚本：定义前端轮询、按钮请求和状态刷新逻辑。
PAGE_SCRIPT = """
const POLL_INTERVAL_MS = 500;

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

async function unbindWindow() {
    await postApi("/api/window/unbind");
}

async function takeScreenshot() {
    const response = await fetch("/api/screenshot", {method: "POST"});
    const data = await response.json();
    console.log(data);
    await refreshStatus();
    await refreshLogs();
}

async function toggleOverlay() {
    await postApi("/api/overlay/toggle");
}

async function refreshStatus() {
    if (refreshStatus.busy) return;
    refreshStatus.busy = true;

    try {
        const frameResponse = await fetch("/api/status");
        const data = await frameResponse.json();
        document.getElementById("map-name").textContent = data.player.map_name;
        document.getElementById("coordinate").textContent = data.player.x + ":" + data.player.y;
        document.getElementById("bound-title").textContent = data.bound_window.title || "未绑定";
        document.getElementById("overlay-button").textContent = data.settings.overlay_enabled ? "Overlay: 开" : "Overlay: 关";
    } finally {
        refreshStatus.busy = false;
    }
}

async function refreshLogs() {
    const response = await fetch("/api/logs");
    const text = await response.text();
    const box = document.getElementById("log-box");
    box.textContent = text;
    box.scrollTop = box.scrollHeight;
}

setInterval(refreshStatus, POLL_INTERVAL_MS);
setInterval(refreshLogs, POLL_INTERVAL_MS);
window.onload = async function() {
    await refreshStatus();
    await refreshLogs();
};
"""

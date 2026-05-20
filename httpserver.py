from fasthtml.common import *
from starlette.responses import JSONResponse, PlainTextResponse
import uvicorn

import api
import dm
import log


SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8765


def run_server(player_info, update_frame, app_settings):
    app = create_server(player_info, update_frame, app_settings)
    log.write_console(f"HTTP 服务启动: http://{SERVER_HOST}:{SERVER_PORT}")
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, log_level="warning")


def create_server(player_info, update_frame, app_settings):
    app, rt = fast_app()

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

    @rt("/api/status")
    def get():
        return JSONResponse(get_status(player_info, app_settings))

    @rt("/api/frame")
    def post():
        return JSONResponse(get_status(player_info, app_settings))

    @rt("/api/dm/start")
    def post():
        success, version, message = dm.start_dm()
        log.write(message)
        return JSONResponse({
            "success": success,
            "version": version,
            "message": message,
        })

    @rt("/api/window/bind")
    def post(keyword: str = ""):
        success, title, message = dm.bind_window_by_title(keyword)
        log.write(message)
        return JSONResponse({
            "success": success,
            "title": title,
            "message": message,
            "status": get_status(player_info, app_settings),
        })

    @rt("/api/window/unbind")
    def post():
        success, title, message = dm.unbind_window()
        log.write(message)
        return JSONResponse({
            "success": success,
            "title": title,
            "message": message,
            "status": get_status(player_info, app_settings),
        })

    @rt("/api/coordinate/read")
    def post():
        update_frame_safely(update_frame)
        return JSONResponse({
            "map_name": player_info["map_name"],
            "x": player_info["x"],
            "y": player_info["y"],
            "status": get_status(player_info, app_settings),
        })

    @rt("/api/move/{action}/{direction}")
    def post(action: str, direction: str):
        result = api.move_player(action, direction)
        log.write(result["message"])
        return JSONResponse({
            "move": result,
            "status": get_status(player_info, app_settings),
        })

    @rt("/api/overlay/toggle")
    def post():
        app_settings["overlay_enabled"] = not app_settings["overlay_enabled"]
        dm.set_overlay_enabled(app_settings["overlay_enabled"])
        state = "开启" if app_settings["overlay_enabled"] else "关闭"
        message = f"点击提示 Overlay 已{state}"
        log.write(message)
        return JSONResponse({
            "success": True,
            "message": message,
            "status": get_status(player_info, app_settings),
        })

    @rt("/api/screenshot")
    def post():
        success, path, message = dm.capture_bound_window()
        log.write(message)
        return JSONResponse({
            "success": success,
            "path": path,
            "message": message,
            "status": get_status(player_info, app_settings),
        })

    @rt("/api/test/{number}")
    def post(number: int):
        message = f"测试按钮 {number} 被点击"
        log.write(message)
        return JSONResponse({"success": True, "message": message})

    @rt("/api/logs")
    def get():
        return PlainTextResponse(log.read())

    return app


def create_buttons(app_settings):
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


def create_move_pad(title, action):
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


def get_status(player_info, app_settings):
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


def get_overlay_button_text(app_settings):
    return "Overlay: 开" if app_settings["overlay_enabled"] else "Overlay: 关"


def update_frame_safely(update_frame):
    try:
        update_frame()
    except Exception as error:
        log.write(f"刷新帧异常: {error}")


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

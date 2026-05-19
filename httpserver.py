from fasthtml.common import *
from starlette.responses import JSONResponse, PlainTextResponse
import uvicorn

import api
import dm
import log


SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8765


def run_server(player_info, update_frame):
    app = create_server(player_info, update_frame)
    log.write(f"HTTP 服务启动: http://{SERVER_HOST}:{SERVER_PORT}")
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, log_level="warning")


def create_server(player_info, update_frame):
    app, rt = fast_app()

    @rt("/")
    def get():
        return Html(
            Head(
                Title("Mir2Auto"),
                Style(PAGE_STYLE),
                Script(PAGE_SCRIPT),
            ),
            Body(
                H2("Mir2Auto"),
                Div(
                    *create_buttons(),
                    cls="buttons",
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
        return JSONResponse(get_status(player_info))

    @rt("/api/frame")
    def post():
        return JSONResponse(get_status(player_info))

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
    def post():
        success, title, message = dm.bind_game_window()
        log.write(message)
        return JSONResponse({
            "success": success,
            "title": title,
            "message": message,
            "status": get_status(player_info),
        })

    @rt("/api/coordinate/read")
    def post():
        update_frame_safely(update_frame)
        return JSONResponse({
            "map_name": player_info["map_name"],
            "x": player_info["x"],
            "y": player_info["y"],
            "status": get_status(player_info),
        })

    @rt("/api/screenshot")
    def post():
        success, path, message = dm.capture_bound_window()
        log.write(message)
        return JSONResponse({
            "success": success,
            "path": path,
            "message": message,
            "status": get_status(player_info),
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


def create_buttons():
    buttons = [
        Button("绑定窗口", onclick="postApi('/api/window/bind')"),
        Button("测试坐标", onclick="postApi('/api/coordinate/read')"),
        Button("截图", onclick="takeScreenshot()"),
    ]

    for number in range(4, 11):
        buttons.append(Button(f"测试按钮 {number}", onclick=f"postApi('/api/test/{number}')"))

    return buttons


def get_status(player_info):
    bound = dm.get_bound_window()

    return {
        "player": {
            "map_name": player_info["map_name"],
            "x": player_info["x"],
            "y": player_info["y"],
        },
        "bound_window": bound,
    }


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
.buttons {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 8px;
    margin-bottom: 12px;
}
button {
    height: 30px;
    cursor: pointer;
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

async function takeScreenshot() {
    const response = await fetch("/api/screenshot", {method: "POST"});
    const data = await response.json();
    console.log(data);
    await refreshStatus();
    await refreshLogs();
}

async function refreshStatus() {
    if (refreshStatus.busy) return;
    refreshStatus.busy = true;

    try {
        const frameResponse = await fetch("/api/frame", {method: "POST"});
        const data = await frameResponse.json();
        document.getElementById("map-name").textContent = data.player.map_name;
        document.getElementById("coordinate").textContent = data.player.x + ":" + data.player.y;
        document.getElementById("bound-title").textContent = data.bound_window.title || "未绑定";
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

from fasthtml.common import *
from starlette.responses import JSONResponse, PlainTextResponse
import uvicorn

import api
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
                Div(
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
        log.write(result["message"])
        return JSONResponse({
            "success": result["success"],
            "title": result["title"],
            "message": result["message"],
            "status": get_status(player_info, app_settings),
        })

    # 窗口解绑接口：解除当前绑定窗口并返回最新状态。
    @rt("/api/window/unbind")
    def post():
        # 解绑结果：记录窗口解绑是否成功、标题和说明消息。
        result = api.unbind_window()
        log.write(result["message"])
        return JSONResponse({
            "success": result["success"],
            "title": result["title"],
            "message": result["message"],
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
        result = api.move_player(action, direction, app_settings["overlay_enabled"])
        log.write(result["message"])
        return JSONResponse({
            "move": result,
            "status": get_status(player_info, app_settings),
        })

    # Overlay 切换接口：反转点击提示开关并同步到底层模块。
    @rt("/api/overlay/toggle")
    def post():
        # Overlay 切换结果：由业务层维护开关并同步绘制层。
        result = api.toggle_overlay(app_settings)
        log.write(result["message"])
        return JSONResponse({
            "success": result["success"],
            "message": result["message"],
            "status": get_status(player_info, app_settings),
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
            "message": result["message"],
            "status": get_status(player_info, app_settings),
        })

    # 玩家屏幕位置接口：返回按移动原点算法计算出的角色屏幕坐标。
    @rt("/api/player/screen-position")
    def post():
        # 玩家屏幕位置结果：记录当前客户区和 DPI 诊断信息。
        result = api.get_player_screen_position()
        log.write(result["message"])
        return JSONResponse({
            "success": result["success"],
            "player_x": result["player_x"],
            "player_y": result["player_y"],
            "client": result.get("client", {}),
            "bottom_ui_height": result.get("bottom_ui_height", api.BOTTOM_UI_HEIGHT),
            "message": result["message"],
            "status": get_status(player_info, app_settings),
        })

    # 怪物扫描接口：快速查找屏幕怪物并返回位置、距离和血量百分比。
    @rt("/api/monsters/scan")
    def post():
        # 怪物扫描结果：记录扫描摘要并把明细写入日志。
        result = api.scan_monsters(app_settings["overlay_enabled"])
        log.write(result["message"])
        log_monster_scan_details(result)
        return JSONResponse({
            "success": result["success"],
            "monsters": result.get("monsters", []),
            "count": result.get("count", 0),
            "player": result.get("player", {}),
            "client": result.get("client", {}),
            "debug_points": result.get("debug_points", []),
            "message": result["message"],
            "status": get_status(player_info, app_settings),
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

        result = api.recognize_monster_name(x, y, blood_bar, app_settings["overlay_enabled"])
        log.write(result["message"])
        return JSONResponse({
            "success": result["success"],
            "name": result.get("name", "未识别"),
            "name_text": result.get("name_text", ""),
            "raw_text": result.get("raw_text", ""),
            "mask_text": result.get("mask_text", ""),
            "used_attempt": result.get("used_attempt", 0),
            "reject_reason": result.get("reject_reason", ""),
            "debug_images": result.get("debug_images", []),
            "position": result.get("position", {}),
            "ocr_box": result.get("ocr_box", {}),
            "blood_bar": result.get("blood_bar", {}),
            "message": result["message"],
            "status": get_status(player_info, app_settings),
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
            "status": get_status(player_info, app_settings),
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
        Button("测试键盘(M)", onclick="pressKeyboard('M')"),
        Button("检测怪物列表", onclick="scanMonsters()"),
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
    return api.get_status(player_info, app_settings)


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


# 写入怪物扫描明细日志：表格之外的调试信息保留在日志里。
def log_monster_scan_details(result):
    if not result.get("success"):
        return

    for monster in result.get("monsters", []):
        bar = monster.get("blood_bar", {})
        position = monster.get("position", {})
        log.write(
            "怪物 "
            f"name={monster.get('name', '')} "
            f"distance={monster.get('distance', '')} "
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
    grid-template-columns: repeat(5, 1fr);
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
    .utility-buttons,
    .status {
        grid-template-columns: 1fr;
    }
}
"""


# 页面脚本：定义前端轮询、按钮请求和状态刷新逻辑。
PAGE_SCRIPT = """
const POLL_INTERVAL_MS = 500;
let currentMonsters = [];

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

async function pressKeyboard(key) {
    const params = new URLSearchParams({key});
    await postApi("/api/keyboard/press?" + params.toString());
}

async function scanMonsters() {
    const response = await fetch("/api/monsters/scan", {method: "POST"});
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

# Agent

- 代码要少、直白，适合 Python 新手。
- 先用函数，少用类，别提前复杂化。
- `app.py` 是入口/网关/服务器启动。
- `httpserver.py` 放 FastHTML 页面和 API。
- `dm.py` 只封装大漠，优先用大漠识别、截图、后台点击。
- `api.py` 放游戏数据读取接口。
- `player.py` 保存玩家状态，先用简单 dict。
- `log.py` 统一写 `log.txt`。
- 服务地址固定 `http://127.0.0.1:8765`。
- 用 32 位 Python 运行，因为 `dm.dll` 是 32 位。
- 大漠绑定窗口标题包含 `闪电侠`。
- 绑定模式用 `gdi2`，截图才是游戏窗口。
- 截图 API 只保存到 `screenshots/screenshot_0001.bmp` 这种自增文件，并返回路径。
- 方便 Codex 自动调用 HTTP API 测试，不依赖人工点界面。

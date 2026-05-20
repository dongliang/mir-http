# Agent

- 代码要少、直白，适合 Python 新手。
- 先用函数，少用类，别提前复杂化。
- `app.py` 是入口/网关/服务器启动。
- `httpserver.py` 放 FastHTML 页面和 API。
- `op.py` 只封装 OP 64 位免注册插件，负责窗口绑定、截图、后台点击。
- `api.py` 放游戏数据读取接口。
- `player.py` 保存玩家状态，先用简单 dict。
- `log.py` 统一写 `log.txt`。
- 服务地址固定 `http://127.0.0.1:8765`。
- 用项目内 `runtime/python310/python.exe` 运行，因为 OP 的 `_pyop.pyd` 依赖 `python310.dll`。
- `vendor/` 是第三方 OP 文件，`runtime/` 是内置 Python/依赖运行时；搜索和改代码默认排除这两个目录。
- OP 绑定模式自动尝试，优先 `dx2/windows/windows` 做后台鼠标；`windows` 鼠标模式下不要用 `LeftClick/RightClick`，要用 `Down + Up`。
- `dx2` 下 OP/Win32 返回的窗口尺寸是 2 倍，点击、截图和 OCR 使用 0.5 后的有效客户区尺寸。
- 截图 API 只保存到 `screenshots/screenshot_0001.bmp` 这种自增文件，并返回路径。
- 方便 Codex 自动调用 HTTP API 测试，不依赖人工点界面。

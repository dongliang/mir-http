# Agent

## 编码偏好

- 代码要少、直白，适合 Python 新手。
- 先用函数，少用类，别提前复杂化。
- 用项目内 `runtime/python310/python.exe` 运行，因为 OP 的 `_pyop.pyd` 依赖 `python310.dll`。
- 搜索和改代码默认排除 `vendor/`、`runtime/`、`screenshots/`。
- 服务地址固定 `http://127.0.0.1:8765`。

## 依赖架构

- `app.py` 是入口，只负责启动、后台刷新循环、退出清理。
- `httpserver.py` 是 HTTP 和页面层，只调用 `api.py`，不要直接调用 `op.py`。
- `api.py` 是业务层，统一封装窗口绑定、截图、坐标读取、移动、键盘输入、Overlay 开关和状态聚合。
- `op.py` 只封装 OP 插件能力：加载 OP、绑定/解绑、截图调用、鼠标输入、键盘输入、绑定模式状态。
- `win32.py` 只封装 Win32 API：窗口查找、窗口标题、客户区尺寸等。
- `overlay.py` 只负责点击提示绘制，不属于 OP 插件功能。
- `ocr_client.py` 管理 OCR 子进程，`ocr_worker.py` 执行 OCR 识别。
- `player.py` 保存玩家状态，先用简单 dict。
- `log.py` 统一写 `log.txt`。

## 依赖方向

- `app.py -> api.py / httpserver.py / player.py / ocr_client.py / log.py`
- `httpserver.py -> api.py / log.py`
- `api.py -> op.py / win32.py / overlay.py / ocr_client.py`
- `op.py -> vendor/op/pyop.py`
- `overlay.py -> pywin32`
- `ocr_client.py -> ocr_worker.py`

不要让 `app.py` 或 `httpserver.py` 直接依赖 `op.py`。
不要让 `op.py` 依赖 `overlay.py` 或业务层模块。

## OP 细节

- OP 绑定模式自动尝试，优先 `dx2/windows/windows` 做后台鼠标和键盘。
- `windows` 鼠标模式下不要用 `LeftClick/RightClick`，要用 `Down + Up`。
- 后台键盘优先用绑定后的 `KeyDown + 短暂停留 + KeyUp`，不要只依赖过短的 `KeyPress`。
- `dx2` 下 OP/Win32 返回的窗口尺寸是 2 倍，点击、截图和 OCR 使用 0.5 后的有效客户区尺寸。
- 后台键盘 HTTP API 是 `/api/keyboard/press?key=M&hold_ms=120&repeat=1&interval_ms=80`。
- 截图 API 保存到 `screenshots/screenshot_0001.bmp` 这种自增文件，并返回路径。

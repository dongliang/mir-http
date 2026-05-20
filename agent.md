# Agent

## 编码偏好

- 代码要少、直白，适合 Python 新手。
- 先用函数，少用类，别提前复杂化。
- 用项目内 `runtime/python310/python.exe` 运行，因为 OP 的 `_pyop.pyd` 依赖 `python310.dll`。
- 搜索和改代码默认排除 `vendor/`、`runtime/`、`screenshots/`。
- 业务 Python 脚本统一放在 `py/`，启动入口是 `py/app.py`。
- `py/` 内脚本的路径基准仍然是项目根目录，`runtime/`、`vendor/`、`screenshots/`、`log.txt` 都留在根目录。
- 服务地址固定 `http://127.0.0.1:8765`。

## 依赖架构

- `py/app.py` 是入口，只负责启动、后台刷新循环、退出清理。
- `py/httpserver.py` 是 HTTP 和页面层，只调用 `api.py`，不要直接调用 `op.py`。
- `py/api.py` 是业务层，统一封装窗口绑定、截图、坐标读取、移动、键盘输入、Overlay 开关和状态聚合。
- `py/op.py` 只封装 OP 插件能力：加载 OP、绑定/解绑、截图调用、鼠标输入、键盘输入、绑定模式状态。
- `py/win32.py` 只封装 Win32 API：窗口查找、窗口标题、客户区尺寸等。
- `py/overlay.py` 只负责点击提示绘制，不属于 OP 插件功能。
- `py/ocr_client.py` 管理 OCR 子进程，`py/ocr_worker.py` 执行 OCR 识别。
- `py/player.py` 保存玩家状态，先用简单 dict。
- `py/log.py` 统一写根目录的 `log.txt`。

## 依赖方向

- `py/app.py -> api.py / httpserver.py / player.py / ocr_client.py / log.py`
- `py/httpserver.py -> api.py / log.py`
- `py/api.py -> op.py / win32.py / overlay.py / ocr_client.py`
- `py/op.py -> vendor/op/pyop.py`
- `py/overlay.py -> pywin32`
- `py/ocr_client.py -> py/ocr_worker.py`

不要让 `py/app.py` 或 `py/httpserver.py` 直接依赖 `op.py`。
不要让 `py/op.py` 依赖 `overlay.py` 或业务层模块。

## OP 细节

- OP 绑定、点击、截图、OCR 坐标统一优先使用 `dx2/windows/windows/0`，不要在后续任务里随意切到其它显示模式。
- `windows` 鼠标模式下不要用 `LeftClick/RightClick`，要用 `Down + Up`。
- 后台键盘优先用绑定后的 `KeyDown + 短暂停留 + KeyUp`，不要只依赖过短的 `KeyPress`。
- `dx2` 下 OP/Win32 返回的窗口尺寸是 2 倍，点击、截图和 OCR 使用 0.5 后的有效客户区尺寸。
- `gdi` 在当前环境截图会黑屏；截图黑屏时优先重启 OP 并重新绑定 `dx2/windows/windows/0`。
- Overlay 直接沿用业务有效客户区坐标，不额外再乘除 DPI。
- 后台键盘 HTTP API 是 `/api/keyboard/press?key=M&hold_ms=120&repeat=1&interval_ms=80`。
- 截图 API 保存到 `screenshots/screenshot_0001.bmp` 这种自增文件，并返回路径。

## 截图测量调试

- 遇到坐标偏移、OCR 区域不准、悬停点不准时，默认先用当前 OP 截图做测量图，不只靠口述经验值。
- 测量图用 `PIL.Image` 打开截图，用 `PIL.ImageDraw` 画辅助线。
- 用 `draw.rectangle(...)` 标出血条框、当前 OCR 框、候选 OCR 框。
- 用 `draw.ellipse(...)` 标出当前悬停点、候选悬停点、玩家位置等关键点。
- 用 `draw.text(...)` 给怪物或目标编号，方便对照日志里的 `bar`、`pos`、`distance`。
- 测量图写到系统临时目录，例如 `%TEMP%\mir2_monster_measure.png`，不要提交到项目。

# Agent

## 仓库贡献指南

### 项目结构与模块组织

- 这是一个 Windows Python 自动化项目，业务代码统一放在 `py/`。
- `py/app.py` 是启动入口，负责应用启动、后台刷新循环和退出清理。
- `py/httpserver.py` 负责 HTTP 与页面层，只调用 `api.py`。
- `py/api.py` 是业务层，封装窗口绑定、截图、坐标读取、移动、键盘输入、Overlay 和状态聚合。
- `py/op.py` 只封装 OP 插件能力，`py/win32.py` 只封装 Win32 API。
- 找字统一使用 OP 大漠字库，字库文件放在 `fonts/main.txt`。
- 资源图片放在 `png/` 和 `ref/`；大漠字库放在 `fonts/`；文本清单放在 `txt/`；OP 依赖放在 `vendor/op/`；内置 Python 运行时放在 `runtime/`。
- `screenshots/`、`DebugImage/`、`log.txt` 是运行输出，不要提交。

### 构建、测试与本地运行

- `start.bat`：使用内置 Python 启动 `py/app.py`，通常会以管理员权限运行。
- `runtime\python310\python.exe py\app.py`：从项目根目录直接启动服务。
- `safe_shutdown.bat`：停止本项目 Python 服务进程，并检查它们占用过的监听端口。
- `runtime\python310\python.exe -m compileall py`：快速检查 `py/` 代码语法。

`start.bat` 每次启动会随机选择一个可用四位端口，终端会显示实际服务地址。

### 代码风格与命名

- 使用 Python 3.10、四空格缩进。
- 函数和变量用 `snake_case`，常量用 `UPPER_CASE`。
- 代码保持直白，优先函数，只有在明显降低复杂度时才引入类。
- 项目路径优先使用 `pathlib.Path`，路径基准保持为项目根目录。
- 遵守下方依赖方向：页面层调用业务层，业务层调用底层封装，不要跨层直接调用。

### 测试与验证

- 当前没有正式测试框架或覆盖率要求。
- 提交前至少运行 `runtime\python310\python.exe -m compileall py`。
- 修改 HTTP、页面、OCR、截图、坐标或 Overlay 逻辑时，要手动验证相关功能。
- OCR 和坐标类问题应使用新截图对照 `png/` 或 `ref/`，临时诊断图不要提交。

### 提交与 PR 规范

- Git 历史使用简短中文提交信息，例如 `新增大地图交互区域矩形计算函数`。
- 提交信息应描述实际行为变化，不要只写工具操作。
- PR 需要说明改动摘要、验证步骤、影响模块；涉及 UI、OCR、Overlay 或坐标变化时，补充截图或调试说明。
- 修改 `runtime/` 或 `vendor/` 时必须明确说明原因，因为这些文件影响 OP 和 OCR 运行。

### 安全与配置

- 不要提交 `.sesskey`、日志、截图、调试图或本地运行输出。
- 不要随意替换 `runtime/` 和 `vendor/` 下的二进制或依赖文件。

## 编码偏好

- 代码要少、直白，适合 Python 新手。
- 先用函数，少用类，别提前复杂化。
- 用项目内 `runtime/python310/python.exe` 运行，因为 OP 的 `_pyop.pyd` 依赖 `python310.dll`。
- 搜索和改代码默认排除 `vendor/`、`runtime/`、`screenshots/`。
- 业务 Python 脚本统一放在 `py/`，启动入口是 `py/app.py`。
- `py/` 内脚本的路径基准仍然是项目根目录，`runtime/`、`vendor/`、`screenshots/`、`log.txt` 都留在根目录。
- `start.bat` 每次启动随机选择一个可用四位端口，服务地址以终端输出为准。

## 依赖架构

- `py/app.py` 是入口，只负责启动、后台刷新循环、退出清理。
- `py/httpserver.py` 是 HTTP 和页面层，只调用 `api.py`，不要直接调用 `op.py`。
- `py/api.py` 是业务层，统一封装窗口绑定、截图、坐标读取、移动、键盘输入、Overlay 开关和状态聚合。
- `py/op.py` 只封装 OP 插件能力：加载 OP、绑定/解绑、截图调用、鼠标输入、键盘输入、绑定模式状态和大漠字库找字。
- `py/win32.py` 只封装 Win32 API：窗口查找、窗口标题、客户区尺寸等。
- `py/overlay.py` 只负责点击提示绘制，不属于 OP 插件功能。
- `py/player.py` 保存玩家状态，先用简单 dict。
- `py/log.py` 统一写根目录的 `log.txt`。

## 依赖方向

- `py/app.py -> api.py / httpserver.py / player.py / log.py`
- `py/httpserver.py -> api.py / log.py`
- `py/api.py -> op.py / win32.py / overlay.py`
- `py/op.py -> vendor/op/pyop.py`
- `py/overlay.py -> pywin32`

不要让 `py/app.py` 或 `py/httpserver.py` 直接依赖 `op.py`。
不要让 `py/op.py` 依赖 `overlay.py` 或业务层模块。

## OP 细节

- OP 绑定、点击、截图、OCR 坐标统一优先使用 `dx2/windows/windows/0`，不要在后续任务里随意切到其它显示模式。
- `windows` 鼠标模式下不要用 `LeftClick/RightClick`，要用 `Down + Up`。
- 后台键盘优先用绑定后的 `KeyDown + 短暂停留 + KeyUp`，不要只依赖过短的 `KeyPress`。
- `dx2` 下不要额外把窗口尺寸、点击、截图或 OCR 坐标乘以 `0.5`，直接使用 OP/Win32 返回的客户区坐标。
- OP 找字统一加载 `fonts/main.txt`，缺字时补大漠字库，不要重新引入 PaddleOCR。
- 怪物攻击前按 `txt/monster.txt` 做白名单过滤，每行一个怪物关键字；怪物名 OCR 颜色按 `txt/monster_name_colors.txt` 加载，每行一个 OP 颜色格式。
- 页面按钮“重载TXT配置”会运行时重新读取 `txt/` 下的怪物清单和怪物名 OCR 颜色。
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

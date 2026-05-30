# cli/ — CLI 交互界面

> 更新时间：2026-05-30

CLI 模块负责本地交互式命令行体验，包括输入读取、命令分发、流式输出和富文本展示。它是用户进入 F-Agent 的主要界面层。

## 文件职责

| 文件 | 职责 |
|------|------|
| `__init__.py` | 标记 `cli` 为 Python 包。 |
| `interface.py` | 基于 prompt_toolkit 和 rich 处理交互输入、内置命令、输出渲染和会话操作。 |

## 注意事项

- CLI 命令行为变更后，需要同步检查 `tests/test_cli_commands.py`。

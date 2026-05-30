# cron/ — 定时任务调度

> 更新时间：2026-05-30

定时任务模块负责把自然语言延迟、间隔、ISO 时间和 cron 表达式解析为可持久化任务，并在 CLI 常驻期间扫描和执行到期 prompt。它与 `tools/cron.py` 提供的 LLM 工具接口配合使用。

## 文件职责

| 文件 | 职责 |
|------|------|
| `__init__.py` | 标记 `cron` 为 Python 包。 |
| `models.py` | 定义定时任务模型、任务类型、任务状态和运行记录。 |
| `parser.py` | 解析延迟、间隔、ISO 时间和 5 字段 cron 表达式。 |
| `runner.py` | 在独立会话中执行到期任务 prompt，并记录执行结果。 |
| `scheduler.py` | 在 CLI 常驻期间周期性扫描任务，处理到期、错过和重复调度。 |
| `store.py` | 使用 SQLite 存储任务定义和运行记录。 |

## 注意事项

- `cron/` 只负责调度领域逻辑；LLM 可调用的创建、查看和删除入口在 `tools/cron.py`。
- 调度语义变更时需要同步运行 `tests/test_cron_*.py`。

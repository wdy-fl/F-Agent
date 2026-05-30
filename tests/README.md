# tests/ — 测试

> 更新时间：2026-05-30

测试目录使用 pytest 覆盖 Agent 主循环、CLI 命令、配置、上下文压缩、数据库、记忆、技能、工具、安全审批和定时任务。测试文件按被测模块或功能命名。

## 文件职责

| 文件 | 职责 |
|------|------|
| `__init__.py` | 标记 `tests` 为 Python 包。 |
| `test_agent_full.py` | 覆盖 Agent 端到端流程。 |
| `test_agent_loop.py` | 覆盖 Agent 主循环和工具调用流程。 |
| `test_approval.py` | 覆盖危险命令识别和审批策略。 |
| `test_cli_commands.py` | 覆盖 CLI 内置命令。 |
| `test_compressor.py` | 覆盖上下文压缩策略。 |
| `test_config_settings.py` | 覆盖配置加载、默认值和路径派生。 |
| `test_context_fence.py` | 覆盖记忆上下文围栏。 |
| `test_cron_parser.py` | 覆盖定时表达式解析。 |
| `test_cron_runner.py` | 覆盖定时任务执行器。 |
| `test_cron_scheduler.py` | 覆盖后台调度器。 |
| `test_cron_store.py` | 覆盖定时任务持久化。 |
| `test_cron_tool.py` | 覆盖定时任务 LLM 工具接口。 |
| `test_llm_client.py` | 覆盖 LLM 客户端封装。 |
| `test_logging_config.py` | 覆盖日志配置。 |
| `test_memory_manager.py` | 覆盖记忆管理器。 |
| `test_memory_tool.py` | 覆盖记忆 LLM 工具。 |
| `test_session.py` | 覆盖会话数据库读写。 |
| `test_skill_hub.py` | 覆盖技能外部安装工具。 |
| `test_skill_loader.py` | 覆盖技能扫描和 frontmatter 解析。 |
| `test_skill_tools.py` | 覆盖技能管理 LLM 工具。 |
| `test_skill_utils.py` | 覆盖技能路径和名称工具函数。 |
| `test_tools.py` | 覆盖工具注册表和基础工具行为。 |

## 注意事项

- 运行完整测试前先激活项目虚拟环境：`source .venv/bin/activate && python3 -m pytest`。

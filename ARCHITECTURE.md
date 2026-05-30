# F-Agent（阿福）架构设计文档

> 本地 CLI 个人 Agent 的核心闭环架构

## 1. 概述

### 1.1 定位

F-Agent（阿福）是一个面向个人研发场景的本地 CLI 智能助手。当前版本聚焦 Agent 核心闭环：对话、工具调用、会话持久化、历史召回、记忆同步、技能复用、上下文压缩和 CLI 常驻定时任务。

项目吸收 Hermes-Agent 的设计思想，但刻意避免生产级 God Class 和过早平台化。当前架构优先保证模块边界清晰、代码可读、功能可测试、运行路径可恢复。

### 1.2 当前核心能力

| 能力 | 当前实现 |
|------|----------|
| 智能对话 | `llm/client.py` 基于 OpenAI SDK 封装，支持 OpenAI 兼容模型服务 |
| CLI 交互 | `cli/interface.py` 使用 prompt_toolkit + rich，支持流式输出和会话命令 |
| Agent 主循环 | `agent/loop.py` 负责 LLM 调用、工具执行、预算控制、持久化和压缩检查 |
| 工具系统 | `tools/registry.py` 提供显式注册和串行调度 |
| 命令审批 | `tools/approval.py` 检测危险命令，CLI 提供一次允许 / 会话记住 / 拒绝 |
| 会话持久化 | `db/session.py` + `db/schema.py` 使用 SQLite（WAL + FTS5）保存会话和消息 |
| 记忆系统 | `memory/manager.py` 统一维护历史召回和工作区记忆文件 |
| 上下文围栏 | `memory/context_fence.py` 使用 `<memory-context>` 隔离召回内容 |
| 技能系统 | `skill/loader.py` 扫描 `workspace/skills/` 下的 `SKILL.md` 并注入索引 |
| 上下文压缩 | `context/compressor.py` 负责工具结果裁剪、结构化摘要、头尾保护和状态恢复 |
| 定时任务 | `cron/` + `tools/cron.py` 支持 CLI 常驻期间创建、持久化、扫描并串行执行定时 Agent prompt |

### 1.3 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 使用场景 | 本地 CLI 助手 | 聚焦核心 Agent 能力，避免过早引入多平台网关 |
| LLM SDK | OpenAI SDK | 通过 `base_url` 兼容不同 OpenAI 风格模型服务 |
| 工具调度 | 串行执行 | 保持工具调用顺序与模型规划一致，降低副作用风险 |
| 数据库 | SQLite + WAL + FTS5 | 零部署、便于本地持久化和全文搜索 |
| 记忆 | SQLite 历史召回 + Markdown 工作区记忆 | 同时覆盖对话检索和长期用户/Agent 信息沉淀 |
| 技能 | 渐进式披露 | 系统提示词只注入技能索引，相关时再按需加载完整内容 |
| 安全 | 审批优先 | 对终端高风险命令默认交互确认，定时任务只能使用任务级显式授权的危险操作 |

## 2. 分层架构

### 2.1 整体分层

```text
CLI 层（prompt_toolkit + rich + 定时任务通知）
  ↓
Agent 核心层（主循环 + 提示词 + 预算控制 + 压缩检查）
  ↓
能力调度层（工具注册/调度 + 记忆管理 + 技能管理 + 审批 + 定时任务调度）
  ↓
基础设施层（LLM Client + SQLite + YAML 配置 + 工作区文件）
```

### 2.2 模块划分

```text
F-Agent/
├── main.py                    # 入口：加载配置、校验 API Key、启动 CLI
├── agent/
│   ├── loop.py                # Agent 主循环：LLM 调用、工具执行、持久化、压缩
│   ├── prompt.py              # 系统提示词构建：身份、工具、技能、记忆文件
│   └── budget.py              # ReAct 迭代预算与中断标志
├── cli/
│   └── interface.py           # CLI 交互、斜杠命令、流式输出、命令审批回调
├── config/
│   └── settings.py            # YAML 配置加载、默认路径、配置 dataclass
├── context/
│   └── compressor.py          # 上下文压缩：工具结果裁剪 + LLM 摘要 + 头尾保护
├── cron/
│   ├── models.py              # 定时任务和执行记录 dataclass / 状态常量
│   ├── parser.py              # 延迟、间隔、ISO 时间和 5 字段 cron 表达式解析
│   ├── store.py               # cron_jobs / cron_runs 持久化读写
│   ├── runner.py              # 为到期任务创建独立 Agent 会话并记录结果
│   └── scheduler.py           # CLI 常驻期间后台扫描并串行执行到期任务
├── db/
│   ├── schema.py              # SQLite schema、FTS5、迁移
│   └── session.py             # 会话 CRUD、消息读写、搜索、恢复
├── llm/
│   └── client.py              # OpenAI SDK 封装、流式响应、token 估算
├── memory/
│   ├── manager.py             # 历史召回、记忆同步、工作区记忆文件读写
│   └── context_fence.py       # <memory-context> 注入与剥离
├── skill/
│   ├── loader.py              # SKILL.md 扫描与技能索引构建
│   └── skill_utils.py         # frontmatter、名称、路径等工具函数
├── tools/
│   ├── registry.py            # 工具注册表和串行调度器
│   ├── terminal.py            # 终端执行工具
│   ├── file_ops.py            # 文件读写与目录查看
│   ├── web_search.py          # Web 搜索与网页抓取
│   ├── memory.py              # 记忆工具入口
│   ├── skill.py               # 技能列表、查看、管理工具
│   ├── skill_hub.py           # 从 GitHub / URL 安装外部技能
│   ├── mysql.py               # MySQL 只读查询工具
│   ├── think.py               # Agent 结构化思考工具
│   ├── cron.py                # 定时任务管理工具：create/list/pause/resume/remove
│   └── approval.py            # 危险命令检测与审批状态
└── tests/                     # pytest 测试
```

### 2.3 关键边界

- `AgentLoop` 只编排流程，不直接实现具体工具逻辑。
- `ToolRegistry` 只负责注册、参数解析、调用和结果包装，不理解业务语义。
- `MemoryManager` 统一管理历史召回和工作区记忆文件，`tools/memory.py` 只是暴露给 LLM 的工具入口。
- `skill/` 负责技能文件解析和索引，`tools/skill.py` 负责技能的 LLM 工具操作。
- CLI 层负责用户交互、审批回调、定时任务创建确认和执行完成通知，不把提示词构建、工具调度等逻辑塞进界面代码。
- `cron/` 负责定时任务领域逻辑，`tools/cron.py` 只提供给 LLM 调用的管理入口。

## 3. 启动与主循环

### 3.1 启动流程

```text
main.py
  ├── get_config() 加载 workspace/config.yaml 或默认配置
  ├── 校验 llm.api_key
  ├── ensure_config_dir() 确保 workspace/ 存在
  ├── configure_logging() 写入 workspace/logs/agent.log
  └── CLIInterface().run()
```

`main.py` 顶层导入 `tools`，触发 `tools/__init__.py` 显式导入各工具模块，各工具在模块加载时调用 `registry.register()` 完成注册。

### 3.2 CLI 交互流程

```text
CLIInterface.run()
  ├── 打印启动横幅
  ├── prompt_toolkit 读取用户输入
  ├── 处理 /help /sessions /resume /stats /clear /quit
  ├── 普通输入交给 AgentLoop.run()
  └── rich Live 渲染流式输出
```

CLI 和前台 AgentLoop 共享同一个 `SessionDB` 实例。定时任务调度器使用独立的 `SessionDB` / SQLite 连接，避免后台线程与前台交互共享连接。CLI 同时注册命令审批回调和定时任务创建确认回调，在终端工具遇到危险命令或 Agent 尝试创建定时任务时展示 rich Panel 并等待用户选择。

### 3.3 Agent 主循环

```text
AgentLoop.run(original_message)
  ├── 确保会话已创建或恢复
  ├── turn_count +1 并写入 sessions
  ├── MemoryManager.prefetch() 搜索历史相关消息
  ├── inject_context() 将记忆上下文包入 <memory-context>
  ├── 写入原始用户消息到 SQLite
  ├── 重置 IterationBudget
  ├── while budget.can_continue():
  │   ├── 调用 LLM 流式接口
  │   ├── 无 tool_calls：持久化 assistant，触发记忆同步，返回最终回复
  │   ├── 有 tool_calls：持久化 assistant，registry.dispatch_batch() 串行执行
  │   ├── 写入工具结果和统计信息
  │   └── 检查是否触发上下文压缩
  └── 预算耗尽时执行 grace call 生成最终回复
```

### 3.4 会话恢复

`AgentLoop.restore_session(session_id)` 从 SQLite 读取历史消息并转换回 OpenAI 消息格式，同时恢复：

- `compressed_tokens`：用于压缩反抖动判断。
- `turn_count`：用于跨恢复延续轮次统计。
- system prompt：由当前配置重新构建，历史消息追加在其后。

## 4. 工具系统

### 4.1 注册接口

当前工具采用显式导入 + 模块顶层注册。`ToolRegistry.register()` 的接口为：

```python
registry.register(
    name="terminal",
    schema={...},
    handler=run_terminal,
    max_result_size=50000,
)
```

字段说明：

| 字段 | 说明 |
|------|------|
| `name` | 工具名称，全局唯一，也是 LLM tool call 中的函数名 |
| `schema` | OpenAI function calling 格式的工具定义 |
| `handler` | 接收参数 dict、返回字符串或可 JSON 序列化对象的处理函数 |
| `max_result_size` | 单个工具返回结果最大字符数，超出截断 |

当前没有 `is_async`、`parallel_safe` 参数，也没有并行调度逻辑。

### 4.2 调度流程

```text
LLM 返回 tool_calls
  ↓
AgentLoop._execute_tool_calls()
  ↓
registry.dispatch_batch(tool_calls)
  ↓
按原始顺序逐个解析 arguments 并调用 dispatch(name, args)
  ↓
包装为 role=tool、tool_call_id=... 的 OpenAI 消息
  ↓
追加回 message_list，并写入 SQLite
```

串行调度的目标是保持模型规划顺序，避免终端、文件、数据库、记忆等有副作用工具并发执行带来的不可控行为。

### 4.3 内置工具清单

| 工具 | 来源文件 | 用途 |
|------|----------|------|
| `terminal` | `tools/terminal.py` | 执行终端命令，执行前经过命令审批检查 |
| `read_file` | `tools/file_ops.py` | 读取文件内容 |
| `write_file` | `tools/file_ops.py` | 写入文件内容 |
| `list_files` | `tools/file_ops.py` | 列出目录内容 |
| `web_search` | `tools/web_search.py` | Web 搜索 |
| `web_fetch` | `tools/web_search.py` | 抓取网页内容 |
| `memory` | `tools/memory.py` | 搜索历史、更新用户画像、读写记忆/身份/行为指引 |
| `skills_list` | `tools/skill.py` | 列出技能索引 |
| `skill_view` | `tools/skill.py` | 查看技能完整内容或关联文件 |
| `skill_manage` | `tools/skill.py` | 创建、编辑、删除技能或技能关联文件 |
| `skill_hub_install` | `tools/skill_hub.py` | 从 GitHub / URL 安装外部技能 |
| `mysql_query` | `tools/mysql.py` | 执行 MySQL 只读查询 |
| `think` | `tools/think.py` | 记录结构化思考内容并回传给模型 |
| `cron` | `tools/cron.py` | 创建、查看、暂停、恢复和删除定时 Agent prompt |

### 4.4 命令审批

`tools/approval.py` 将终端命令分为三类：

| 类型 | 行为 |
|------|------|
| safe | 直接执行 |
| dangerous | 触发 CLI 审批，可本次允许、会话记住或拒绝 |
| hardline | 直接阻断，不进入用户审批 |

审批状态按会话记录，`approval.mode = off` 时可关闭危险命令审批，但 hardline 规则仍由检测逻辑优先判断。后台定时任务不会调用前台 CLI 的交互式审批回调，只能使用创建任务时绑定的 `allowed_dangerous_keys` 放行匹配的危险操作，hardline 命令始终阻断。

### 4.5 定时任务工具

`tools/cron.py` 向 LLM 暴露 `cron` 工具，用于管理定时 Agent prompt：

| action | 行为 |
|--------|------|
| `create` | 创建定时任务，必须提供 `name`、`prompt`、`schedule`，并经过用户确认 |
| `list` | 列出当前持久化任务 |
| `pause` | 暂停指定任务 |
| `resume` | 恢复指定任务 |
| `remove` | 删除指定任务，同时级联删除执行记录 |

`schedule` 不直接接收自然语言时间。模型需要先把“明天上午九点”这类表达转换为受支持格式后再调用工具：

- 延迟：`10m`、`2h`。
- 间隔：`every 1h`、`every 30m`。
- ISO 时间：`2026-05-31T09:00:00+08:00`。
- 5 字段 cron：`0 9 * * *`。

创建任务时 CLI 会展示任务名称、prompt、调度表达式、下一次运行时间和危险命令授权键，用户确认后才写入 SQLite。

## 5. 记忆系统

### 5.1 记忆来源

| 类型 | 存储位置 | 内容 | 更新方式 |
|------|----------|------|----------|
| 会话历史 | SQLite `messages` | 用户、助手、工具消息 | 每轮对话自动写入 |
| 历史索引 | SQLite FTS5 `messages_fts` | 消息全文索引 | INSERT / UPDATE / DELETE 触发器维护 |
| 用户画像 | `workspace/USER.md` | 用户偏好、习惯、项目上下文 | `memory.update_profile` 或自动同步提取 |
| Agent 笔记 | `workspace/MEMORY.md` | 长期笔记和经验 | `memory.append_memory` 或自动同步提取 |
| 身份描述 | `workspace/SOUL.md` | Agent 身份和能力描述 | `memory.update_soul` |
| 行为指引 | `workspace/AGENT.md` | Agent 工作规则和行为约束 | `memory.update_agent` |

### 5.2 预取与注入

```text
用户输入 original_message
  ↓
MemoryManager.prefetch(original_message)
  ├── SessionDB.search_messages() 从 FTS5 搜索相关历史
  └── 拼接为记忆上下文片段
  ↓
inject_context(original_message, memory_context)
  ↓
< memory-context >历史片段< /memory-context > + 当前用户输入
```

SQLite 中保存的是原始用户输入，不包含 `<memory-context>`，避免召回内容污染历史消息。

### 5.3 同步策略

`AgentLoop._sync_memory()` 按 `memory.nudge_interval` 间隔触发：

1. 提取最近若干轮 user / assistant 对话。
2. 使用 LLM 判断是否有值得持久化的信息。
3. 将提取结果写入 `USER.md` 或 `MEMORY.md`。
4. 如果 LLM 主动调用 `memory` 工具，则重置同步计数器。

这使记忆更新既能由模型主动调用，也能通过对话节奏进行低频自动提取。

## 6. 技能系统

### 6.1 技能目录

```text
workspace/skills/
  <category>/
    <skill-name>/
      SKILL.md          # 必需：YAML frontmatter + Markdown 指令
      references/       # 可选：参考资料
      templates/        # 可选：模板文件
      scripts/          # 可选：脚本
      assets/           # 可选：附件
```

### 6.2 SKILL.md 格式

```yaml
---
name: python-testing
description: "Use when writing Python tests. Covers pytest fixtures and coverage."
category: dev
tags: [python, testing, pytest]
created_at: 2026-05-29
updated_at: 2026-05-29
---
# Python Testing Skill

## When to Use
...

## Instructions
...
```

### 6.3 渐进式披露

启动时，`skill/loader.py` 扫描技能目录并构建技能索引。系统提示词只注入技能的名称和描述，避免把所有技能全文塞进上下文。

当模型判断某个技能相关时，通过 `skill_view(name)` 加载完整 `SKILL.md` 或关联文件。技能创建、编辑、删除和关联文件写入由 `skill_manage` 执行。

### 6.4 Skills Hub

`skill_hub_install` 支持从两类来源安装技能：

- `github`：`owner/repo/path/to/skill` 形式，递归下载目录内容。
- `url`：直接下载单个 `SKILL.md`。

安装过程会检查：

- `SKILL.md` 是否存在。
- frontmatter 中是否有技能名称。
- category 是否包含路径穿越字符。
- 本地技能目录和 `.hub/lock.json` 是否已有同名或同源技能。

## 7. 上下文压缩

### 7.1 触发条件

`ContextCompressor.should_compress(current_tokens)` 在当前估算 token 数达到 `context_window * threshold` 时触发压缩。默认配置为 128000 上下文窗口、50% 阈值。

### 7.2 压缩流程

```text
messages
  ↓
按 OpenAI tool call 约束切分消息组，避免 assistant/tool 配对被拆散
  ↓
保留 protected_head 组和 protected_tail_tokens 对应尾部消息
  ↓
对 middle 区域旧工具结果替换为 [工具结果已压缩]
  ↓
拆出旧 <context-summary>，与新增 middle 对话一起交给 LLM 生成结构化摘要
  ↓
组装为 head + summary_msg + tail
  ↓
保存 compressed_tokens，用于恢复和反抖动判断
```

### 7.3 摘要结构

摘要固定使用中文结构，便于跨压缩轮次迭代：

- 当前任务
- 已完成
- 进行中
- 关键决策
- 待解决问题
- 相关文件
- 剩余工作

如果摘要生成失败，压缩器会保留旧摘要和新增对话摘录作为退化结果。

## 8. 定时任务运行机制

### 8.1 调度生命周期

定时任务只在 CLI 进程常驻期间运行，不启动独立系统守护进程。

```text
CLIInterface 初始化
  ├── 前台 SessionDB / CronStore：供 CLI 和 cron 工具管理任务
  ├── 后台 SessionDB / CronStore：供 CronScheduler 和 CronRunner 使用
  ├── 注册 cron 创建确认回调
  └── CronScheduler.start()
      └── 后台线程按 cron.tick_interval_seconds 扫描到期任务
```

`CronScheduler.tick()` 每次扫描 `cron_jobs.next_run_at <= now` 的 active 任务，并按查询顺序串行处理。若当前时间超过计划时间 `cron.grace_seconds`，任务不会补跑，而是标记为 `missed`，等待用户后续决定。

### 8.2 独立 Agent 会话执行

`CronRunner` 为每次任务执行创建独立 Agent 会话，并在 `cron_runs` 中记录计划时间、开始时间、结束时间、状态、摘要和错误信息。后台执行上下文会清理前台交互式回调，避免后台线程阻塞在 CLI 输入上。

定时任务执行完成后，CLI 通过轻量通知展示成功或失败结果。多个到期任务串行运行，单个任务异常会记录日志并隔离，不阻断后续任务。

### 8.3 安全边界

- 创建任务必须经过用户确认。
- 任务级 `allowed_dangerous_keys` 只对匹配的 dangerous 命令生效。
- hardline 命令始终阻断，不能被任务级授权绕过。
- 定时任务没有独立 daemon，CLI 退出后不会继续执行。
- 错过宽限窗口的任务不自动补跑。

## 9. 数据存储

### 9.1 SQLite 表

当前 schema 版本为 5。

```sql
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    model TEXT,
    system_prompt TEXT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    message_count INTEGER DEFAULT 0,
    tool_call_count INTEGER DEFAULT 0,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    title TEXT,
    tags TEXT,
    compressed_tokens INTEGER DEFAULT 0,
    turn_count INTEGER DEFAULT 0
);

CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    role TEXT NOT NULL,
    content TEXT,
    reasoning_content TEXT,
    tool_call_id TEXT,
    tool_calls TEXT,
    tool_name TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    token_count INTEGER DEFAULT 0,
    finish_reason TEXT
);

CREATE VIRTUAL TABLE messages_fts USING fts5(
    content,
    content='messages',
    content_rowid='id'
);

CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE cron_jobs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    prompt TEXT NOT NULL,
    schedule_expr TEXT NOT NULL,
    schedule_type TEXT NOT NULL,
    interval_seconds INTEGER,
    cron_expr TEXT,
    next_run_at TEXT,
    state TEXT NOT NULL,
    allowed_dangerous_keys TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_run_at TEXT,
    last_status TEXT,
    last_error TEXT
);

CREATE TABLE cron_runs (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES cron_jobs(id) ON DELETE CASCADE,
    session_id TEXT,
    scheduled_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    status TEXT NOT NULL,
    summary TEXT,
    error TEXT
);
```

### 9.2 迁移

`db/schema.py` 当前包含以下迁移：

| 版本 | 变更 |
|------|------|
| v1 → v2 | 创建 FTS5 全文索引和 messages 触发器，并同步旧消息 |
| v2 → v3 | 为 sessions 添加 `tags`、`compressed_tokens` |
| v3 → v4 | 为 sessions 添加 `turn_count` |
| v4 → v5 | 创建 `cron_jobs` 和 `cron_runs` 定时任务表 |

此外，初始化时会兼容检查 `messages.reasoning_content`，缺失时自动添加。

### 9.3 工作区文件

```text
workspace/
├── config.yaml           # 用户配置
├── state.db              # SQLite 数据库
├── history               # prompt_toolkit 输入历史
├── USER.md               # 用户画像
├── MEMORY.md             # Agent 长期笔记
├── SOUL.md               # Agent 身份描述
├── AGENT.md              # Agent 行为指引
├── skills/               # 技能库
│   └── <category>/<skill>/SKILL.md
└── logs/
    └── agent.log         # 调试日志
```

## 10. 配置系统

`config/settings.py` 使用 dataclass 描述配置，并按以下顺序加载：

1. 内置默认值。
2. `workspace/config.yaml` 中的 YAML 覆盖值。
3. 调用方通过 `set_config()` 注入的测试配置。

主要配置分组：

| 分组 | 说明 |
|------|------|
| `llm` | 模型、base_url、api_key、上下文窗口、迭代次数、温度、超时 |
| `tools` | 工具结果大小限制 |
| `memory` | 历史召回数量、自动同步间隔 |
| `compressor` | 压缩阈值、最小收益、头尾保护范围 |
| `approval` | 命令审批模式 |
| `cron` | CLI 常驻定时任务开关、扫描间隔和错过宽限时间 |
| `skills_hub` | GitHub token |
| `mysql` | 可选 MySQL 连接配置 |
| 路径配置 | 数据库、用户画像、记忆、身份、行为指引、技能、日志路径 |

## 11. 与 Hermes-Agent 的取舍

| 方面 | Hermes-Agent | F-Agent 当前选择 |
|------|--------------|------------------|
| Agent 主循环 | 大型生产级主类 | 拆分为 loop / prompt / budget 等小模块 |
| 模型支持 | 多 Provider 适配 | OpenAI SDK + `base_url` 兼容服务 |
| 多平台 | Gateway + 多平台适配器 | 当前仅本地 CLI，后续按需探索 |
| 工具执行 | 更复杂的生产级调度 | 串行调度，优先可控和可测试 |
| 记忆 | 完整生产记忆体系 | SQLite 历史召回 + Markdown 工作区记忆 |
| 技能 | 更复杂生命周期 | 本地技能加载、管理和外部安装基础能力 |
| 定时任务 | 可包含更完整的生产调度体系 | CLI 常驻期间执行，不做独立 daemon；错过任务标记 missed，不自动补跑 |
| 安全 | 生产级隔离能力 | 本地命令审批、定时任务任务级授权和外部技能安装防护 |

## 12. 当前边界与路线图

当前版本不包含以下能力的完整实现：

- 多平台消息网关。
- 子 Agent 并行委托。
- 定时任务独立守护进程、任务更新、立即运行、自动补跑和多端通知。
- MCP 协议接入。
- Web Dashboard。
- IDE 集成。
- Docker / SSH / 云沙箱执行后端。
- 语音交互和 RL 训练环境。

这些能力属于 `GOAL.md` 中的长期路线图，只有在核心 CLI Agent 闭环稳定后再逐步评估和实现。

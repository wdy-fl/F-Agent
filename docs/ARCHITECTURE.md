# F-Agent（阿福）架构设计文档

> 可运行、可扩展、可进化的个人智能助手

## 1. 概述

### 1.1 定位

阿福是一个本地 CLI 智能助手，具备对话记忆、用户建模、技能自创与自改进能力。

### 1.2 核心能力

| 能力 | 说明 |
|------|------|
| 智能对话 | 通过 OpenAI SDK 接入 LLM，支持 base_url 切换模型 |
| 工具调用 | 自注册工具系统，内置终端/文件/Web/记忆/技能等工具 |
| 持久记忆 | SQLite + FTS5 存储对话历史，支持全文搜索召回 |
| 用户建模 | USER.md 自动维护用户画像，LLM 驱动更新 |
| 技能系统 | 从经验自动创建技能，技能随使用自改进，完整生命周期管理 |
| 上下文压缩 | 工具结果裁剪 + LLM 结构化摘要 + 头尾保护 |

### 1.3 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 使用场景 | 本地 CLI 助手 | 聚焦核心能力，暂不需要多平台网关 |
| LLM SDK | 仅 OpenAI SDK | 通过 base_url 可兼容大多数模型，避免多 SDK 适配复杂度 |
| 记忆 | 会话记忆 + FTS5 搜索 + 用户建模 | 完整记忆能力，支持跨会话召回和个性化 |
| 技能 | 完整技能系统 | 这是阿福"可进化"的核心，包含自动创建和自改进 |
| 数据库 | SQLite（WAL + FTS5） | 零部署、高性能、可移植，Python 标准库自带 |
| 架构风格 | 分层模块架构 | 职责清晰，每层可独立开发测试 |

## 2. 架构设计

### 2.1 整体架构

采用分层模块架构，避免 Hermes-Agent 的 God Class 问题：

```
CLI 层 (prompt_toolkit + rich)
  ↓
Agent 核心层 (主循环 + 预算控制 + 中断)
  ↓
调度层 (工具注册/调度 + 记忆管理 + 技能管理)
  ↓
基础设施层 (LLM 调用 + SQLite 持久化 + 配置管理)
```

### 2.2 模块划分

```
F-Agent/
├── main.py                    # 入口：解析配置 → 启动 CLI
├── agent/
│   ├── loop.py                # Agent 主循环：迭代 LLM 调用 + 工具执行
│   ├── prompt.py              # 系统提示词构建：身份 + 技能 + 记忆 + 上下文文件
│   └── budget.py              # 迭代预算控制 + 中断信号
├── tools/
│   ├── registry.py            # 工具注册表：自注册 + 发现 + 调度
│   ├── terminal.py            # 终端执行
│   ├── file_ops.py            # 文件读写
│   ├── web_search.py          # Web 搜索
│   ├── memory.py              # 记忆读写工具（供 LLM 调用）
│   └── skill.py               # 技能管理工具（供 LLM 调用）
├── memory/
│   ├── manager.py             # 记忆管理器：prefetch + sync + 上下文注入
│   ├── user_profile.py        # 用户建模：USER.md 读写 + LLM 驱动更新
│   └── context_fence.py       # 上下文围栏：<memory-context> 标签注入/剥离
├── skills/
│   ├── loader.py              # 技能加载：扫描 SKILL.md → 解析 frontmatter
│   ├── curator.py             # 技能策展：自动创建 + 生命周期管理 + 自改进
│   └── builtin/               # 内置技能目录
│       └── <category>/
│           └── <skill>/
│               └── SKILL.md
├── context/
│   └── compressor.py          # 上下文压缩：工具结果裁剪 + LLM 摘要 + 头尾保护
├── db/
│   ├── session.py             # 会话持久化：SQLite + FTS5
│   └── schema.py              # 建表 + 迁移
├── llm/
│   └── client.py              # LLM 客户端：OpenAI SDK 封装 + Token 计数
├── config/
│   └── settings.py            # 配置管理：YAML + 环境变量
├── cli/
│   └── interface.py           # CLI 交互：prompt_toolkit 输入 + rich 输出
└── tests/
```

### 2.3 关键设计原则

- **AIAgent 不做上帝类** — 拆成 loop.py（流程控制）、prompt.py（提示词构建）、budget.py（预算控制），各自 < 300 行
- **记忆与工具解耦** — 记忆是独立子系统，tools/memory.py 只是对 LLM 暴露的调用入口
- **技能与 Agent 解耦** — skills/curator.py 是后台服务，不在主循环热路径上

## 3. Agent 主循环

### 3.1 核心流程

```
1. 初始化
   ├── 加载配置 → 创建 LLM Client
   ├── 恢复/创建会话
   ├── 加载技能索引 → 构建系统提示词
   └── 预取记忆 → 注入上下文

2. 主循环
   while budget.remaining > 0 and not interrupted:
   ├── 检查中断信号
   ├── 消耗预算
   ├── 注入记忆到当前用户消息
   ├── 调用 LLM API
   ├── 响应处理：
   │   ├── 有工具调用 → 执行工具 → 追加结果 → 继续循环
   │   └── 无工具调用 → 返回最终回复
   └── 后处理：
       ├── 同步记忆（user_msg + assistant_msg）
       ├── 检查是否需要上下文压缩
       └── 技能策展检查（完成复杂任务后）

3. 返回最终回复
```

### 3.2 与 Hermes-Agent 的简化

- 去掉多 Provider 适配 — 只用 OpenAI SDK
- 去掉流式健康检查 — 非必要复杂度
- 去掉 Anthropic prompt caching — 单 SDK 无需兼容
- 预算控制独立模块 — 不嵌入主循环

### 3.3 工具执行策略

- 默认并行执行（ThreadPoolExecutor），只读工具可并行
- 有副作用的工具（文件写入、终端执行）顺序执行
- 工具结果过大时自动截断（max_result_size 配置项）

### 3.4 预算控制

- 每次对话设定最大迭代次数（默认 50）
- 预算耗尽后允许一次额外调用（grace call），让 LLM 产出最终回复
- 中断信号通过线程安全的标志位实现，用户按 Ctrl+C 可打断

## 4. 记忆与用户建模

### 4.1 记忆类型

| 类型 | 存储位置 | 内容 | 更新时机 |
|------|---------|------|---------|
| 会话记忆 | SQLite messages 表 | 所有对话消息 | 每轮对话自动存储 |
| 会话搜索 | SQLite FTS5 索引 | 消息全文索引 | INSERT 触发器自动维护 |
| 用户画像 | `~/.fagent/USER.md` | 偏好/习惯/项目上下文 | LLM 通过 memory 工具主动更新 |

### 4.2 记忆流程

```
对话开始前（prefetch）:
  1. 从 FTS5 搜索与当前话题相关的历史片段
  2. 读取 USER.md 用户画像
  3. 包装在 <memory-context> 标签内注入用户消息
  4. LLM 看到的是：<memory-context>历史片段+画像</memory-context> + 实际用户输入

对话结束后（sync）:
  1. 存储 user_msg + assistant_msg 到 SQLite
  2. FTS5 触发器自动索引
  3. LLM 可通过 memory 工具写入/更新 USER.md
```

### 4.3 用户画像更新机制

- LLM 通过 memory 工具调用 update_profile action
- 工具内部读取当前 USER.md + 新观察 → 调用 LLM 生成合并后的画像 → 写回
- 不在每轮都触发，只在 LLM 主动调用时更新
- 画像长度上限控制（超出时 LLM 压缩旧条目）

### 4.4 上下文围栏

`<memory-context>` 标签将召回的记忆与用户实际输入区分开，防止 LLM 将历史片段误认为当前输入。围栏在流式输出中也能正确剥离（处理标签跨 chunk 的情况）。

## 5. 技能系统

### 5.1 技能结构

```
~/.fagent/skills/
  <category>/
    <skill-name>/
      SKILL.md          # 必需：YAML frontmatter + Markdown 指令
      references/       # 可选：参考资料
      templates/        # 可选：文件模板
```

### 5.2 SKILL.md 格式

```yaml
---
name: python-testing
description: "Use when writing Python tests. Covers pytest fixtures, mocking, and coverage."
version: 1.0.0
category: software-development
tags: [python, testing, pytest]
lifecycle: active       # active → stale → archived
created_at: 2025-05-13
updated_at: 2025-05-13
usage_count: 0
---
# Python Testing Skill
## When to Use
...
## Instructions
...
```

### 5.3 技能生命周期

```
[Agent 完成复杂任务]
      ↓
[curator 判断是否值得创建技能]
      ↓ active
[技能在对话中被引用 → usage_count++]
      ↓
[长时间未用 → lifecycle: stale]
      ↓
[再次使用 → lifecycle: active，触发自改进]
      ↓
[持续未用 → lifecycle: archived]
```

- 技能不会自动删除，只做状态流转
- archived 技能不注入系统提示词，但可通过搜索召回

### 5.4 自改进机制

- 技能被引用时，curator 评估当前指令与实际使用效果的差距
- 如果发现技能指令不精确或过时，LLM 重写 SKILL.md 的 Instructions 部分
- 版本号自增，updated_at 更新

### 5.5 技能注入方式

- 会话启动时扫描 `~/.fagent/skills/`，构建技能索引
- 技能描述（name + description）注入系统提示词的技能索引区
- 匹配到的技能全文指令注入系统提示词

## 6. 上下文压缩

### 6.1 触发条件

`当前 Token 数 >= 上下文窗口 × 阈值比例（默认 50%）`

### 6.2 压缩算法

```
1. 裁剪旧工具结果（无需 LLM）
   ├── 从尾部向前扫描，保护最近 N token 的消息
   └── 旧工具结果替换为摘要（如 "[terminal] npm test → exit 0, 47 lines"）

2. 确定压缩边界
   ├── head: 保护前 3 条消息（系统提示词 + 首轮对话）
   └── tail: 保护最近 ~20K token 的消息

3. LLM 生成摘要
   ├── 结构化模板：当前任务/已完成/进行中/关键决策/待解决问题
   ├── 首次压缩：从头生成摘要
   └── 后续压缩：基于旧摘要 + 新对话迭代更新

4. 组装压缩后消息
   ├── head 消息 + 摘要消息 + tail 消息
   └── 反抖动：连续两次压缩节省 <10% 则跳过
```

### 6.3 结构化摘要模板

摘要使用固定结构，保证跨压缩轮次的信息连贯性：

- Active Task — 当前正在执行的任务
- Goal — 任务目标
- Completed Actions — 已完成的操作
- In Progress — 正在进行的工作
- Key Decisions — 做出的关键决策
- Pending Questions — 待解决的问题
- Relevant Files — 涉及的文件
- Remaining Work — 剩余工作

## 7. 工具系统

### 7.1 注册机制

```python
# tools/terminal.py
from tools.registry import registry

registry.register(
    name="terminal",
    schema={
        "type": "function",
        "function": {
            "name": "terminal",
            "description": "Execute a terminal command",
            "parameters": { ... }
        }
    },
    handler=run_terminal,
    is_async=False,
    parallel_safe=False,  # 有副作用，不可并行
)
```

### 7.2 发现机制

> **2026-05-13 调整**：MVP 阶段采用显式注册，AST 发现留到后续。

- MVP：在 `tools/__init__.py` 中显式 import 各工具模块触发注册
- 后续：启动时扫描 `tools/*.py`，用 AST 检测文件中是否包含 `registry.register` 调用，有则 import 触发注册

### 7.3 调度流程

```
LLM 返回 tool_calls
  ↓
loop.py 遍历 tool_calls
  ↓ 并行安全判断
安全 → ThreadPoolExecutor 并行执行
不安全 → 顺序执行
  ↓
registry.dispatch(name, args) → handler → result
  ↓
结果追加到消息列表
```

### 7.4 MVP 工具集

| 工具 | 用途 | 并行安全 |
|------|------|---------|
| terminal | 终端命令执行 | 否 |
| read_file | 读文件 | 是 |
| write_file | 写文件 | 否 |
| list_files | 列目录 | 是 |
| web_search | Web 搜索 | 是 |
| web_fetch | 抓取网页内容 | 是 |
| memory | 记忆读写/画像更新 | 否 |
| skill | 技能管理 | 否 |

## 8. 数据存储

### 8.1 SQLite Schema

```sql
-- 会话表
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
    title TEXT
);

-- 消息表
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id),
    role TEXT NOT NULL,
    content TEXT,
    tool_call_id TEXT,
    tool_calls TEXT,
    tool_name TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    token_count INTEGER DEFAULT 0,
    finish_reason TEXT
);

-- FTS5 全文索引
CREATE VIRTUAL TABLE messages_fts USING fts5(
    content,
    content='messages',
    content_rowid='id'
);

-- 自动同步触发器
CREATE TRIGGER messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, COALESCE(new.content, ''));
END;

CREATE TRIGGER messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.id, COALESCE(old.content, ''));
END;

CREATE TRIGGER messages_au AFTER UPDATE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.id, COALESCE(old.content, ''));
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, COALESCE(new.content, ''));
END;
```

### 8.2 文件存储

```
~/.fagent/
├── config.yaml           # 配置文件
├── state.db              # SQLite 数据库
├── USER.md               # 用户画像
├── skills/               # 技能库
│   └── <category>/
│       └── <skill>/
│           └── SKILL.md
└── logs/                 # 日志
    └── agent.log
```

## 9. 实现步骤规划

### Phase 1 — 最小可运行 Agent（MVP）

> **2026-05-13 调整记录**：基于开发讨论，对 Phase 1 做了以下调整：
> 1. 增加早期检查点（Checkpoint），尽早验证 LLM 调用链路
> 2. 合并推进会话持久化与 Agent 核心，会话存储先做最小版（无 FTS5）
> 3. 工具注册采用显式注册（非 AST 发现），降低 MVP 复杂度
> 4. 增加测试要求：每个模块至少一个冒烟测试
> 5. 明确配置 schema，覆盖 MVP 所需全部配置项

#### Step 1 — 基础设施搭建

- 项目结构初始化 + 依赖管理（pyproject.toml / requirements.txt）
- `config/settings.py`：YAML 配置加载 + 环境变量覆盖
  - MVP 配置 schema：model、base_url、api_key、context_window、max_iterations、max_result_size
- `llm/client.py`：OpenAI SDK 封装，支持 base_url 切换模型
- **测试**：LLM Client 冒烟测试（mock API 验证调用链路）

#### Checkpoint — 最简主循环可运行

- `agent/loop.py`：最简主循环（只处理纯文本对话，无工具调用）
- `agent/prompt.py`：基础系统提示词
- `main.py`：`python3 main.py` 能启动并完成一轮对话
- **价值**：尽早验证 LLM SDK 调用链路、API Key 配置、流式输出等基础能力

#### Step 2 — 工具系统

- `tools/registry.py`：注册表 + 显式注册 + 调度
  - MVP 阶段用显式注册（在 `tools/__init__.py` 中 import 各工具模块触发注册）
  - AST 自动发现留到工具数量增多时再加
- `tools/terminal.py`：终端执行
- `tools/file_ops.py`：文件读写 + 列目录
- `tools/web_search.py`：Web 搜索 + 网页抓取
- **测试**：工具调度冒烟测试（并发安全判断 + 结果截断）

#### Step 3 — 会话持久化（最小版）

- `db/schema.py`：建表（sessions + messages，暂不含 FTS5）
- `db/session.py`：会话 CRUD + 消息 INSERT/SELECT
- FTS5 全文索引和搜索召回留到 Phase 2 补全
- **测试**：SQLite 操作冒烟测试

#### Step 4 — 完整 Agent 核心

- `agent/budget.py`：预算控制 + 中断信号
- `agent/loop.py`：扩展主循环（加入工具执行 + 消息管理）
- `agent/prompt.py`：扩展提示词构建（加入工具 schema）
- 集成会话持久化到主循环
- **测试**：预算控制边界测试 + 主循环集成测试

#### Step 5 — CLI 界面

- `cli/interface.py`：prompt_toolkit 输入 + rich 输出
- `main.py`：完整入口集成
- **交付标准**：`python3 main.py` 启动后，能对话、能调用工具、能持久化会话。

### Phase 2 — 记忆与用户建模

> Phase 2 先于 Phase 3，因为技能系统的"自改进"依赖记忆系统的 FTS5 搜索来评估技能效果。

1. **记忆基础设施**
   - `db/schema.py`：补全 FTS5 全文索引 + 自动同步触发器
   - `db/session.py`：补全 FTS5 搜索召回
   - `memory/context_fence.py`：上下文围栏
   - `memory/manager.py`：记忆 prefetch + sync
   - FTS5 搜索召回集成到主循环
   - **测试**：FTS5 搜索准确性测试 + 围栏注入/剥离测试

2. **用户建模**
   - `memory/user_profile.py`：USER.md 读写 + LLM 驱动更新
   - `tools/memory.py`：记忆工具（供 LLM 调用）
   - **测试**：画像更新流程测试

3. **上下文压缩**
   - `context/compressor.py`：工具结果裁剪 + LLM 结构化摘要
   - **测试**：压缩边界条件测试（阈值触发、反抖动、头尾保护）

**交付标准**：阿福能回忆过去对话、自动维护用户画像、长对话自动压缩。

### Phase 3 — 技能系统

1. **技能加载**
   - `skills/loader.py`：SKILL.md 解析 + 索引构建
   - 技能注入到系统提示词

2. **技能管理工具**
   - `tools/skill.py`：创建/编辑/查询技能

3. **技能策展**
   - `skills/curator.py`：自动创建 + 生命周期管理 + 自改进

**交付标准**：阿福能从经验中创建技能，技能随使用自改进，完整生命周期流转。

## 10. 与 Hermes-Agent 的对比

| 方面 | Hermes-Agent | F-Agent |
|------|-------------|---------|
| Agent 主循环 | 14000+ 行 God Class | 拆分为 loop/prompt/budget，各 < 300 行 |
| 模型支持 | 30+ Provider 适配 | 仅 OpenAI SDK，base_url 兼容 |
| 多平台 | Gateway + 20+ 平台适配器 | 仅 CLI，后续按需扩展 |
| 代码量 | ~50K+ 行 | 预估 ~3K 行（MVP）~ 5K 行（完整） |
| 复杂度 | 生产级，大量容错和边界处理 | 学习级，聚焦核心路径 |

# F-Agent 项目规范

## Git 仓库

- 项目 git 仓库根目录：`/Users/wangdeyu/Desktop/agent/F-Agent`
- 提交代码时必须 cd 到此目录，不要在父目录 `/Users/wangdeyu/Desktop/agent` 操作 git

## 环境要求

- 使用 `python3` 命令，不要使用 `python`
- Python 3.11+

## 技术栈

| 层级 | 技术选型 |
|------|---------|
| 语言 | Python 3.11+ |
| LLM SDK | OpenAI SDK（兼容多模型） |
| CLI | prompt_toolkit + rich |
| 数据库 | SQLite（WAL + FTS5） |
| Web | FastAPI + Vite |
| 消息平台 | 按需接入 |
| 浏览器自动化 | Playwright |
| 容器化 | Docker |

## 开发原则

### 1. 三思而后行原则

当用户指出一个问题时，不要直接擅自修改，而是应该先调研分析问题的原因和真实性，然后与用户讨论修改方案，达成一致之后再采取行动。

### 2. 知识靠近代码原则

全局文档写在项目工作目录，模块文档写在模块文件夹，对函数和代码块的描述写在代码附近。

### 3. AICD 原则

- **原子性（Atomicity）**：每次更改用一个 git commit 原子化，以便更改失败时回滚
- **一致性（Consistency）**：代码更新后，必须同步更新相关的进度文档、知识文档、测试用例，自测通过才能提交
- **隔离性（Isolation）**：不同的任务实施，使用独立的进度文档记录实施进度，或者使用 git 分支隔离
- **持久性（Durability）**：跨会话的知识必须写到知识文档里

### 4. 渐进式披露原则

避免巨型文档，每个文档保证最小但完备。对于过大的文档应进行拆分，同时在 CLAUDE.md 里维护文档路由，方便按需定位。

### 5. 任务点提交原则

每完成一个任务点（实现计划中的一个具体步骤），必须主动询问用户是否需要提交 git commit，不要连续完成多个任务点后再统一提交。

## 文档路由

| 文档 | 位置 | 说明 |
|------|------|------|
| 项目目标 | `docs/GOAL.md` | 项目愿景、学习目标、实现阶段、设计原则 |
| 架构设计 | `docs/ARCHITECTURE.md` | 整体架构、模块划分、核心流程、数据存储 |
| Agent 开发 SOP | `docs/dev-sop.md` | Agent 开发工作流规范，5原则 + 9环节完整闭环 |
| 需求对齐与设计 | `docs/superpowers/specs/` | 需求澄清结论与设计方案文档 |
| 任务规划与进度 | `docs/superpowers/plans/` | 任务分解、执行计划与进度状态 |

## 参考资源

- Hermes-Agent 源码：`../hermes-agent`
- Hermes-Agent 核心文件：
  - `run_agent.py` — Agent 主循环
  - `model_tools.py` — 工具调度层
  - `tools/registry.py` — 工具注册表
  - `hermes_state.py` — 会话持久化
  - `agent/prompt_builder.py` — 提示词构建
  - `agent/context_compressor.py` — 上下文压缩
  - `agent/memory_manager.py` — 记忆管理
  - `gateway/run.py` — 消息网关

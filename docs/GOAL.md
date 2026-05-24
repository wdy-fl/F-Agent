# F-Agent 项目目标

## 项目愿景

基于 Hermes-Agent 的设计理念与架构思想，复刻一个属于自己的 AI Agent —— F-Agent。通过学习 Hermes-Agent 的核心机制，理解自改进 Agent 的完整闭环，最终构建一个可运行、可扩展、可进化的个人智能助手。

## 学习目标

### 1. 理解核心架构

- [ ] 掌握 Agent 主循环（Agent Loop）的工作机制：LLM 调用 → 工具选择 → 执行 → 结果回传 → 继续推理
- [ ] 理解工具注册与调度系统（Tool Registry）：自注册、发现、调度、异步桥接
- [ ] 理解上下文压缩（Context Compression）：如何在有限 Token 窗口内保持长对话的连贯性
- [ ] 理解会话持久化（Session Persistence）：SQLite + FTS5 全文搜索实现跨会话记忆

### 2. 掌握关键子系统

- [ ] **记忆系统**：持久化记忆（MEMORY.md）、用户建模（USER.md）、会话搜索召回
- [ ] **技能系统**：从经验中自动创建技能、技能生命周期管理、技能自改进
- [ ] **委托与并行**：子 Agent 派生、隔离上下文、结果汇总
- [ ] **多平台网关**：统一消息网关架构，支持多平台同时接入
- [ ] **定时任务**：Cron 调度器，支持自然语言定时任务

### 3. 理解工程实践

- [ ] 模型无关设计：如何通过 Provider 适配层支持 30+ 模型提供商
- [ ] 插件化架构：工具、记忆、上下文引擎、模型提供者均可插拔
- [ ] 安全机制：上下文注入扫描、命令审批系统、容器隔离
- [ ] 多环境执行：本地、Docker、SSH、云沙箱等终端后端

## 实现目标

### Phase 1 — 最小可运行 Agent（MVP）

> ✅ 已完成

- 基础设施搭建：`config/settings.py` + `llm/client.py`
- 工具系统：`tools/registry.py` + `terminal.py` + `file_ops.py` + `web_search.py`
- 会话持久化（含 FTS5）：`db/schema.py` + `db/session.py`
- Agent 核心：`agent/loop.py` + `agent/prompt.py` + `agent/budget.py`
- CLI 界面：`cli/interface.py` + `main.py`

### Phase 2 — 记忆与用户建模

> ✅ 已完成

- 记忆基础设施：FTS5 全文索引 + 自动同步触发器 + `memory/context_fence.py`
- 记忆管理器：`memory/manager.py`（prefetch + sync）
- 用户建模：`memory/user_profile.py` + `tools/memory.py`
- 上下文压缩：`context/compressor.py`（工具结果裁剪 + LLM 结构化摘要 + 头尾保护）

### Phase 3 — 技能系统

1. **技能加载**
   - `skills/loader.py`：SKILL.md 解析 + 索引构建
   - 技能注入到系统提示词

2. **技能管理工具**
   - `tools/skill.py`：创建/编辑/查询技能

3. **技能策展**
   - `skills/curator.py`：自动创建 + 生命周期管理 + 自改进

**交付标准**：阿福能从经验中创建技能，技能随使用自改进，完整生命周期流转。

### Phase 4 — 多平台与扩展

- 多平台消息网关（Telegram / Discord / Web）
- 子 Agent 委托与并行执行
- 插件系统
- 定时任务调度
- MCP 协议支持

### Phase 5 — 高级特性

- 多环境执行后端
- Web Dashboard
- IDE 集成
- 语音交互（STT / TTS）
- RL 训练环境

## 设计原则

1. **先理解再实现** — 每个模块先读懂 Hermes-Agent 的实现，提炼核心设计思想，再用自己的方式实现
2. **最小可用优先** — 每个阶段交付可运行的系统，而非半成品框架
3. **保持简洁** — 不照搬全部代码，只实现核心路径，去除不必要复杂度
4. **可扩展性** — 关键子系统（工具、模型、记忆）采用插件化设计，方便后续扩展
5. **Python 优先** — 主语言使用 Python 3.11+，前端按需引入 TypeScript
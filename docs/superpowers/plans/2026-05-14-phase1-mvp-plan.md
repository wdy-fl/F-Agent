# Phase 1 MVP 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现 Phase 1 最小可运行 Agent，`python3 main.py` 能对话、能调用工具、能持久化会话

**Architecture:** 分层模块架构，参考 Hermes-Agent 模式但大幅简化

**Tech Stack:** Python 3.11+, OpenAI SDK, prompt_toolkit, rich, SQLite

---

### Task 1: 基础设施搭建

**Files:**
- Create: `pyproject.toml`, `requirements.txt`
- Create: `config/settings.py`
- Create: `llm/client.py`
- Create: `tests/test_llm_client.py`

- [x] **Step 1:** 创建 `pyproject.toml` 和 `requirements.txt`，声明依赖 ✅ 2026-05-14
- [x] **Step 2:** 实现 `config/settings.py`，YAML 配置加载 + 环境变量覆盖 ✅ 2026-05-14
- [x] **Step 3:** 实现 `llm/client.py`，OpenAI SDK 封装 + Token 计数 ✅ 2026-05-14
- [x] **Step 4:** 编写 LLM Client 冒烟测试 ✅ 2026-05-14（4 tests passed）
- [x] **Step 5:** 自测验证，提交 git ✅ 2026-05-14

### Task 2: Checkpoint — 最简主循环可运行

**Files:**
- Create: `agent/loop.py`
- Create: `agent/prompt.py`
- Create: `main.py`

- [x] **Step 1:** 实现 `agent/prompt.py`，基础系统提示词构建 ✅ 2026-05-14
- [x] **Step 2:** 实现 `agent/loop.py`，最简主循环（纯文本对话，流式输出） ✅ 2026-05-14
- [x] **Step 3:** 实现 `main.py`，入口集成 ✅ 2026-05-14
- [x] **Step 4:** 自测：`python3 main.py` 能启动并完成一轮对话 ✅ 2026-05-14（3 tests passed）
- [ ] **Step 5:** 提交 git

### Task 3: 工具系统

**Files:**
- Create: `tools/registry.py`
- Modify: `tools/__init__.py`
- Create: `tools/terminal.py`
- Create: `tools/file_ops.py`
- Create: `tools/web_search.py`
- Create: `tests/test_tools.py`

- [x] **Step 1:** 实现 `tools/registry.py`，注册表 + 调度 ✅ 2026-05-14
- [x] **Step 2:** 实现 `tools/terminal.py` ✅ 2026-05-14
- [x] **Step 3:** 实现 `tools/file_ops.py`（read_file, write_file, list_files） ✅ 2026-05-14
- [x] **Step 4:** 实现 `tools/web_search.py`（web_search, web_fetch） ✅ 2026-05-14
- [x] **Step 5:** 更新 `tools/__init__.py` 显式注册 ✅ 2026-05-14
- [x] **Step 6:** 编写工具调度冒烟测试 ✅ 2026-05-14（8 tests passed）
- [x] **Step 7:** 自测验证，提交 git

### Task 4: 会话持久化（最小版）

**Files:**
- Create: `db/schema.py`
- Create: `db/session.py`
- Create: `tests/test_session.py`

- [x] **Step 1:** 实现 `db/schema.py`，建表（sessions + messages，不含 FTS5） ✅ 2026-05-14
- [x] **Step 2:** 实现 `db/session.py`，会话 CRUD + 消息 INSERT/SELECT ✅ 2026-05-14
- [x] **Step 3:** 编写 SQLite 操作冒烟测试 ✅ 2026-05-14（8 tests passed）
- [x] **Step 4:** 自测验证，提交 git

### Task 5: 完整 Agent 核心

**Files:**
- Create: `agent/budget.py`
- Modify: `agent/loop.py`
- Modify: `agent/prompt.py`
- Modify: `main.py`

- [ ] **Step 1:** 实现 `agent/budget.py`，预算控制 + 中断信号
- [ ] **Step 2:** 扩展 `agent/loop.py`，加入工具执行 + 消息管理
- [ ] **Step 3:** 扩展 `agent/prompt.py`，加入工具 schema
- [ ] **Step 4:** 集成会话持久化到主循环
- [ ] **Step 5:** 编写预算控制边界测试
- [ ] **Step 6:** 自测：完整 Agent 循环可运行
- [ ] **Step 7:** 提交 git

### Task 6: CLI 界面

**Files:**
- Create: `cli/interface.py`
- Modify: `main.py`

- [ ] **Step 1:** 实现 `cli/interface.py`，prompt_toolkit 输入 + rich 输出
- [ ] **Step 2:** 更新 `main.py` 完整入口集成
- [ ] **Step 3:** 自测：`python3 main.py` 完整体验验证
- [ ] **Step 4:** 提交 git

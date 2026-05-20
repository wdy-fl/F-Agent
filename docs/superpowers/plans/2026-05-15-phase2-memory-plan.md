# Phase 2 记忆与用户建模 实施计划

**Goal:** 阿福能回忆过去对话、自动维护用户画像、长对话自动压缩

**Architecture:** 在 Phase 1 MVP 基础上扩展记忆子系统，FTS5 全文搜索 + 上下文围栏 + 用户画像 + 压缩

**Tech Stack:** Python 3.11+, SQLite FTS5, OpenAI SDK

---

### Task 1: FTS5 全文索引 + 搜索召回

**Files:**
- Modify: `db/schema.py`（补全 FTS5 虚拟表 + 自动同步触发器）
- Modify: `db/session.py`（补全 FTS5 搜索方法）

**接口契约:**

`schema.py`:
- `init_db(conn)` 增加创建 `messages_fts` 虚拟表和 3 个触发器（INSERT/UPDATE/DELETE）
- `SCHEMA_VERSION` 从 1 升到 2，增加迁移逻辑（检测已有表是否存在 FTS5，不存在则创建）

`session.py`:
- `search_messages(query: str, limit: int = 5, session_id: str | None = None) -> list[dict]`
  - 后置条件：返回按相关性排序的消息列表，每条含 session_id、role、content、rank
  - 前置条件：FTS5 索引已创建
  - 异常约定：FTS5 查询语法错误返回空列表（不抛异常）

**测试:** FTS5 搜索准确性测试（插入消息 → 搜索 → 验证召回排序）

- [x] **Step 1:** 修改 `db/schema.py`，SCHEMA_VERSION 升到 2，增加 FTS5 虚拟表和触发器，实现 v1→v2 迁移 ✅ 2026-05-20
- [x] **Step 2:** 修改 `db/session.py`，增加 `search_messages` 方法 ✅ 2026-05-20
- [x] **Step 3:** 编写 FTS5 搜索测试（5 tests：基本搜索/会话过滤/无匹配/非法查询/迁移） ✅ 2026-05-20
- [x] **Step 4:** 自测验证（42 tests all passed） ✅ 2026-05-20

---

### Task 2: 上下文围栏

**Files:**
- Create: `memory/context_fence.py`

**接口契约:**

`context_fence.py`:
- `inject_context(user_message: str, memory_context: str) -> str`
  - 后置条件：返回 `<memory-context>\n{memory_context}\n</memory-context>\n{user_message}`
- `strip_context(message: str) -> tuple[str, str]`
  - 后置条件：返回 (clean_message, memory_part)，去除 `<memory-context>` 标签内容
  - 异常约定：标签不完整时返回 (原消息, "")

**测试:** 围栏注入/剥离测试（正常注入、嵌套标签、跨 chunk 剥离）

---

### Task 3: 记忆管理器

**Files:**
- Create: `memory/manager.py`

**接口契约:**

`manager.py`:
- `MemoryManager.__init__(session_db: SessionDB, user_profile_path: str, llm: LLMClient | None = None)`
- `prefetch(user_message: str, limit: int = 5) -> str`
  - 后置条件：返回拼装好的记忆上下文字符串（FTS5 搜索结果 + 用户画像），供注入到围栏
  - 数据流向：user_message → FTS5 搜索 → 结果拼接 + 画像读取 → 返回
- `sync(session_id: str, user_msg: str, assistant_msg: str) -> None`
  - 后置条件：消息已持久化到 SQLite（实际持久化由 loop.py 完成，sync 仅做 FTS5 索引检查等辅助工作）
  - 前置条件：消息已写入 messages 表
- `get_user_profile() -> str`
  - 后置条件：返回 USER.md 内容，文件不存在返回空字符串
- `update_user_profile(new_content: str) -> None`
  - 后置条件：USER.md 已写入新内容，目录不存在则创建

**测试:** prefetch 流程测试（mock SessionDB.search_messages → 验证拼接格式）、画像读写测试

---

### Task 4: 记忆集成到主循环

**Files:**
- Modify: `agent/loop.py`（注入记忆 prefetch + sync）
- Modify: `agent/prompt.py`（扩展记忆指引）
- Modify: `main.py`（初始化 MemoryManager）
- Modify: `cli/interface.py`（传递 MemoryManager）

**接口契约:**

`loop.py` 修改：
- `AgentLoop.__init__` 增加 `memory_manager: MemoryManager | None = None` 参数
- `run()` 中用户消息发送前调用 `memory_manager.prefetch()` → `inject_context()` 注入记忆
- `run()` 结束后调用 `memory_manager.sync()`
- 记忆注入逻辑：仅当 memory_manager 不为 None 时执行

`prompt.py` 修改：
- `build_system_prompt()` 增加 `include_memory_guidance: bool = True`（默认启用）

`main.py` / `cli/interface.py` 修改：
- 创建 MemoryManager 实例并注入到 AgentLoop

**测试:** 集成测试（mock LLM → 验证消息中包含 `<memory-context>` 标签）

---

### Task 5: 用户建模

**Files:**
- Create: `memory/user_profile.py`
- Create: `tools/memory.py`

**接口契约:**

`user_profile.py`:
- `UserProfileManager.__init__(profile_path: str, llm: LLMClient | None = None)`
- `read_profile() -> str`
  - 后置条件：返回 USER.md 内容，不存在返回 ""
- `write_profile(content: str) -> None`
  - 后置条件：内容已写入 USER.md
- `update_profile(observations: str) -> str`
  - 后置条件：调用 LLM 合并当前画像 + 新观察 → 写入 → 返回新画像内容
  - 前置条件：llm 不为 None
  - 异常约定：LLM 调用失败时保留原画像，返回原画像内容
  - 画像长度上限：5000 字符，超出时 LLM 压缩旧条目

`tools/memory.py`:
- 注册 `memory` 工具到 registry
- schema: `{ action: "search" | "save" | "update_profile", query?: str, content?: str }`
- handler 调用 MemoryManager / UserProfileManager 的方法

**测试:** 画像更新流程测试（mock LLM → 写入新观察 → 验证合并结果）、memory 工具注册和调用测试

---

### Task 6: 上下文压缩

**Files:**
- Create: `context/compressor.py`
- Modify: `agent/loop.py`（集成压缩检查）
- Modify: `config/settings.py`（增加压缩配置项）

**接口契约:**

`compressor.py`:
- `ContextCompressor.__init__(llm: LLMClient, context_window: int, threshold: float = 0.5, min_saving: float = 0.1)`
- `should_compress(messages: list[dict], current_tokens: int) -> bool`
  - 后置条件：`current_tokens >= context_window * threshold` 时返回 True
- `compress(messages: list[dict], current_tokens: int) -> list[dict]`
  - 后置条件：返回压缩后的消息列表（head + 摘要 + tail），token 数显著减少
  - 数据流向：head 保护前 3 条 → tail 保护最近 ~20K token → 中间部分 LLM 摘要 → 组装
  - 异常约定：LLM 调用失败时返回原始消息（不丢失数据）
- `trim_tool_results(messages: list[dict], max_tokens: int) -> list[dict]`
  - 后置条件：旧工具结果替换为摘要行，tail 消息不受影响

`config/settings.py`:
- `CompressorConfig` dataclass: `threshold: float = 0.5`, `min_saving: float = 0.1`, `protected_head: int = 3`, `protected_tail_tokens: int = 20000`

`loop.py` 修改：
- 每轮工具执行后检查 `should_compress()`，满足条件则调用 `compress()`

**测试:** 压缩边界条件测试（阈值触发、反抖动、头尾保护、LLM 失败降级）

---

### 依赖关系

```
Task 1 (FTS5) ──→ Task 2 (围栏) ──→ Task 3 (管理器) ──→ Task 4 (集成)
                                                          ↑
                                         Task 5 (用户建模) ─┘
Task 6 (压缩) ──→ 集成到 loop.py（依赖 Task 4 完成后的 loop.py）
```

执行顺序：Task 1 → Task 2 → Task 3 → Task 4 → Task 5 → Task 6

### 交付标准

- FTS5 搜索能准确召回历史对话片段
- `<memory-context>` 围栏正确注入/剥离
- 用户画像通过 LLM 驱动更新
- 长对话触发上下文压缩，头尾保护正常
- 所有新增模块有对应测试

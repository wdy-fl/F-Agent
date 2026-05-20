# 进程内连续对话上下文修复实施计划

> **给 agentic workers：** 执行本计划时必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 子技能，按任务逐项实施。步骤使用复选框（`- [ ]`）语法跟踪进度。

**目标：** 让 F-Agent 在同一次 CLI 进程内保留多轮对话上下文，并让多轮用户输入复用同一个 SQLite session。

**架构：** 对话状态继续由 `AgentLoop` 持有，因为 `CLIInterface` 当前在一个进程内只创建一个 `AgentLoop` 实例，并在所有用户轮次中复用它。`AgentLoop.run()` 只在当前 AgentLoop 生命周期内首次调用时初始化 system message 和 SQLite session，后续每轮只追加新的 user / assistant / tool 消息。本计划明确不包含跨进程记忆、FTS5 召回、USER.md 用户画像、memory 工具和输出重复问题。

**技术栈：** Python 3.11+、pytest、现有 `SessionDB` SQLite 持久化、mock 后的 `LLMClient.chat_stream`。

---

## 文件结构

- 修改：`agent/loop.py`
  - 职责：在一个 `AgentLoop` 实例生命周期内维护一个内存对话列表和一个 SQLite session。
  - 主要变更：把每轮重置 messages / session 的逻辑改为只初始化一次 conversation / session。
- 修改：`tests/test_agent_full.py`
  - 职责：通过 mock LLM 调用和 `SessionDB` 验证 `AgentLoop` 集成行为。
  - 主要变更：新增测试，证明上下文连续、session 复用、system prompt 只加入一次。

---

### Task 1：为进程内连续上下文添加失败测试

**文件：**
- 修改：`tests/test_agent_full.py`

- [ ] **Step 1：添加新测试需要的 import**

在 `tests/test_agent_full.py` 顶部，把：

```python
"""预算控制和完整 Agent 循环测试"""

from unittest.mock import patch
```

改为：

```python
"""预算控制和完整 Agent 循环测试"""

from copy import deepcopy
from unittest.mock import patch
```

- [ ] **Step 2：添加测试，证明第二次 LLM 调用能收到上一轮上下文**

在 `tests/test_agent_full.py` 的 `test_agent_loop_with_session_persistence` 后追加：

```python
def test_agent_loop_preserves_context_between_runs():
    """测试同一个 AgentLoop 的多次 run 会保留上一轮上下文"""
    config = LLMConfig(api_key="sk-test")
    llm = LLMClient(config)
    agent = AgentLoop(llm, max_iterations=10, output_callback=lambda t: None)

    captured_messages = []

    def fake_chat_stream(messages, tools=None):
        captured_messages.append(deepcopy(messages))
        if len(captured_messages) == 1:
            return iter([
                {"type": "content_delta", "content": "好的，当当大人"},
                {"type": "done", "finish_reason": "stop", "content": "好的，当当大人", "tool_calls": None},
            ])
        return iter([
            {"type": "content_delta", "content": "知道，您是王当当"},
            {"type": "done", "finish_reason": "stop", "content": "知道，您是王当当", "tool_calls": None},
        ])

    with patch.object(llm, "chat_stream", side_effect=fake_chat_stream):
        agent.run("我的名字是王当当，你可以叫我当当大人", "You are a helper")
        result = agent.run("现在你知道我是谁了吗？", "You are a helper")

    assert result == "知道，您是王当当"
    assert len(captured_messages) == 2
    second_call_messages = captured_messages[1]
    assert second_call_messages == [
        {"role": "system", "content": "You are a helper"},
        {"role": "user", "content": "我的名字是王当当，你可以叫我当当大人"},
        {"role": "assistant", "content": "好的，当当大人"},
        {"role": "user", "content": "现在你知道我是谁了吗？"},
    ]
```

- [ ] **Step 3：添加测试，证明多次 run 复用同一个 SQLite session**

在 `test_agent_loop_preserves_context_between_runs` 后追加：

```python
def test_agent_loop_reuses_session_across_runs(tmp_path):
    """测试同一个 AgentLoop 的多次 run 写入同一个 SQLite session"""
    config = LLMConfig(api_key="sk-test")
    llm = LLMClient(config)
    session_db = SessionDB(tmp_path / "test.db")
    agent = AgentLoop(llm, max_iterations=10, session_db=session_db, output_callback=lambda t: None)

    call_count = 0

    def fake_chat_stream(messages, tools=None):
        nonlocal call_count
        call_count += 1
        content = f"回复{call_count}"
        return iter([
            {"type": "content_delta", "content": content},
            {"type": "done", "finish_reason": "stop", "content": content, "tool_calls": None},
        ])

    with patch.object(llm, "chat_stream", side_effect=fake_chat_stream):
        agent.run("第一轮", "You are a helper")
        first_session_id = agent.session_id
        agent.run("第二轮", "You are a helper")

    assert first_session_id is not None
    assert agent.session_id == first_session_id

    sessions = session_db.list_sessions(limit=10)
    assert len(sessions) == 1

    messages = session_db.get_messages(first_session_id)
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "第一轮"),
        ("assistant", "回复1"),
        ("user", "第二轮"),
        ("assistant", "回复2"),
    ]
    session_db.close()
```

- [ ] **Step 4：添加测试，证明 system prompt 在内存中只保存一次**

在 `test_agent_loop_reuses_session_across_runs` 后追加：

```python
def test_agent_loop_keeps_single_system_prompt_across_runs():
    """测试连续 run 不会重复追加 system prompt"""
    config = LLMConfig(api_key="sk-test")
    llm = LLMClient(config)
    agent = AgentLoop(llm, max_iterations=10, output_callback=lambda t: None)

    def fake_chat_stream(messages, tools=None):
        return iter([
            {"type": "content_delta", "content": "ok"},
            {"type": "done", "finish_reason": "stop", "content": "ok", "tool_calls": None},
        ])

    with patch.object(llm, "chat_stream", side_effect=fake_chat_stream):
        agent.run("第一轮", "You are a helper")
        agent.run("第二轮", "You are a helper")

    system_messages = [m for m in agent.messages if m["role"] == "system"]
    assert system_messages == [{"role": "system", "content": "You are a helper"}]
```

- [ ] **Step 5：运行新增测试，确认实现前失败**

运行：

```bash
source /Users/wangdeyu/Desktop/agent/F-Agent/.venv/bin/activate && python3 -m pytest /Users/wangdeyu/Desktop/agent/F-Agent/tests/test_agent_full.py::test_agent_loop_preserves_context_between_runs /Users/wangdeyu/Desktop/agent/F-Agent/tests/test_agent_full.py::test_agent_loop_reuses_session_across_runs /Users/wangdeyu/Desktop/agent/F-Agent/tests/test_agent_full.py::test_agent_loop_keeps_single_system_prompt_across_runs -v
```

预期：FAIL。失败应体现当前只把本轮用户消息发送给 LLM、创建了多个 session，或无法满足 system prompt 单例要求。

---

### Task 2：实现每个 AgentLoop 实例一个进程内连续 conversation

**文件：**
- 修改：`agent/loop.py`
- 测试：`tests/test_agent_full.py`

- [ ] **Step 1：把每轮重置 messages / session 改为一次性初始化**

在 `agent/loop.py` 中，把 `AgentLoop.run()` 开头的：

```python
        # 初始化预算
        self.budget.reset()

        # 初始化消息列表
        self.messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        # 创建会话记录
        if self.session_db:
            self.session_id = str(uuid.uuid4())
            self.session_db.create_session(
                self.session_id,
                self.llm.model,
                system_prompt,
                title=user_message[:50],
            )
            self.session_db.append_message(self.session_id, "user", content=user_message)
```

替换为：

```python
        # 初始化预算
        self.budget.reset()

        self._ensure_conversation_started(system_prompt, user_message)

        user_msg = {"role": "user", "content": user_message}
        self.messages.append(user_msg)

        if self.session_db and self.session_id:
            self.session_db.append_message(self.session_id, "user", content=user_message)
```

- [ ] **Step 2：添加 conversation 初始化辅助方法**

在 `agent/loop.py` 中，把以下方法添加到 `_default_output()` 和 `run()` 之间：

```python
    def _ensure_conversation_started(self, system_prompt: str, first_user_message: str) -> None:
        """初始化当前 AgentLoop 生命周期内的连续对话"""
        if not self.messages:
            self.messages.append({"role": "system", "content": system_prompt})

        if self.session_db and not self.session_id:
            self.session_id = str(uuid.uuid4())
            self.session_db.create_session(
                self.session_id,
                self.llm.model,
                system_prompt,
                title=first_user_message[:50],
            )
```

- [ ] **Step 3：运行新增测试，确认通过**

运行：

```bash
source /Users/wangdeyu/Desktop/agent/F-Agent/.venv/bin/activate && python3 -m pytest /Users/wangdeyu/Desktop/agent/F-Agent/tests/test_agent_full.py::test_agent_loop_preserves_context_between_runs /Users/wangdeyu/Desktop/agent/F-Agent/tests/test_agent_full.py::test_agent_loop_reuses_session_across_runs /Users/wangdeyu/Desktop/agent/F-Agent/tests/test_agent_full.py::test_agent_loop_keeps_single_system_prompt_across_runs -v
```

预期：PASS。

- [ ] **Step 4：运行现有 AgentLoop 和会话持久化测试**

运行：

```bash
source /Users/wangdeyu/Desktop/agent/F-Agent/.venv/bin/activate && python3 -m pytest /Users/wangdeyu/Desktop/agent/F-Agent/tests/test_agent_loop.py /Users/wangdeyu/Desktop/agent/F-Agent/tests/test_agent_full.py /Users/wangdeyu/Desktop/agent/F-Agent/tests/test_session.py -v
```

预期：PASS。

- [ ] **Step 5：确认没有引入 Phase 2 记忆代码**

运行：

```bash
find /Users/wangdeyu/Desktop/agent/F-Agent/memory -maxdepth 1 -type f -name '*.py' -print && find /Users/wangdeyu/Desktop/agent/F-Agent/tools -maxdepth 1 -type f -name 'memory.py' -print
```

预期：除了已存在的 `__init__.py` 之外，不应出现新文件；尤其不能新增 `memory/manager.py`、`memory/context_fence.py`、`memory/user_profile.py` 或 `tools/memory.py`。

---

### Task 3：最终验证并询问是否提交任务点 commit

**文件：**
- 验证：`agent/loop.py`
- 验证：`tests/test_agent_full.py`
- 验证：`docs/superpowers/specs/2026-05-20-process-context-continuity-design.md`
- 验证：`docs/superpowers/plans/2026-05-20-process-context-continuity-plan.md`

- [ ] **Step 1：运行完整现有测试套件**

运行：

```bash
source /Users/wangdeyu/Desktop/agent/F-Agent/.venv/bin/activate && python3 -m pytest /Users/wangdeyu/Desktop/agent/F-Agent/tests -v
```

预期：所有测试 PASS。

- [ ] **Step 2：检查变更范围**

运行：

```bash
git -C /Users/wangdeyu/Desktop/agent/F-Agent diff -- agent/loop.py tests/test_agent_full.py docs/superpowers/specs/2026-05-20-process-context-continuity-design.md docs/superpowers/plans/2026-05-20-process-context-continuity-plan.md
```

预期：diff 只包含进程内连续上下文修复、相关测试、设计文档和计划文档；不能包含输出重复修复或 Phase 2 记忆系统实现。

- [ ] **Step 3：询问用户是否提交当前任务点**

询问：

```text
进程内连续对话上下文修复已完成并通过测试。是否需要我现在提交一个 git commit？
```

除非用户明确确认，否则不要提交。

---

## 自审

- 规格覆盖：已覆盖进程内消息连续、SQLite session 复用、system prompt 单例、Phase 2 记忆和输出重复问题非目标。
- 占位扫描：没有 TBD、TODO、fill-in-later；每个代码变更步骤都有具体代码，每个验证步骤都有明确命令。
- 类型一致性：计划中使用的 `AgentLoop`、`LLMConfig`、`LLMClient`、`SessionDB`、`self.messages`、`self.session_id` 均与当前代码一致。

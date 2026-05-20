# 进程内连续对话上下文修复设计

## 背景

当前 Phase 1 已实现会话和消息落库，但 `AgentLoop.run()` 每轮都会重置 `self.messages` 并创建新的 `session_id`。这导致同一次 CLI 运行期间，阿福也看不到上一轮用户和助手消息。

本设计只修复同一次 `python3 main.py` 运行期间的连续对话上下文。跨进程、跨重启的历史召回、FTS5、USER.md 用户画像和 memory 工具仍属于 Phase 2 记忆系统范围。

## 目标

- 同一 CLI 进程内，多轮用户输入共享同一个上下文消息列表。
- 同一 CLI 进程内，多轮用户输入写入同一个 SQLite session。
- system prompt 在同一个 AgentLoop 生命周期内只加入一次。
- 不改变工具调用执行流程。
- 不处理流式输出重复问题。

## 非目标

- 不实现跨会话历史召回。
- 不实现 FTS5 搜索。
- 不实现 MemoryManager。
- 不实现 USER.md 用户画像。
- 不实现 memory 工具。
- 不修改 CLI 输出重复行为。

## 方案

`AgentLoop` 继续作为对话状态持有者。`CLIInterface` 当前在进程内复用同一个 `AgentLoop` 实例，因此上下文连续性应放在 `AgentLoop` 内维护，避免把消息状态泄漏到 CLI 层。

### AgentLoop 状态

`AgentLoop` 保留：

- `self.messages`: 当前进程内连续对话的 OpenAI 消息列表。
- `self.session_id`: 当前进程内 SQLite session id。

新增或调整内部初始化逻辑：

- 当 `self.messages` 为空时，加入 system message。
- 当 `self.session_id` 为空且存在 `session_db` 时，创建 SQLite session。
- 后续 `run()` 调用不再重置 `self.messages`，也不再创建新的 session。

### 单轮 run 数据流

每次 `run(user_message, system_prompt)`：

1. 重置迭代预算。
2. 若当前 messages 为空，追加 system message。
3. 若当前没有 session，创建 session，title 使用第一轮用户消息前 50 字符。
4. 追加当前 user message 到 `self.messages`。
5. 将当前 user message 写入当前 session。
6. 调用 LLM。
7. 若有 assistant 回复，追加到 `self.messages` 并写入当前 session。
8. 若有 tool calls，执行工具，将 tool 结果追加到 `self.messages` 并写入当前 session。
9. 后续轮次继续复用上述上下文。

### 会话边界

- 一个 `CLIInterface` 实例对应一个 `AgentLoop` 实例。
- 一个 `AgentLoop` 实例对应一个进程内连续 conversation。
- 退出 CLI 后，下次启动不恢复旧 session。
- 暂不新增 `/new` 命令。

## 测试设计

### 连续上下文测试

构造同一个 `AgentLoop`，连续调用两次 `run()`：

1. 第一次输入：`我的名字是王当当`。
2. 第二次输入：`现在你知道我是谁了吗？`。
3. mock 第二次 `llm.chat_stream()`，断言传入 messages 包含：
   - system message；
   - 第一轮 user message；
   - 第一轮 assistant message；
   - 第二轮 user message。

### session 复用测试

构造带 `SessionDB` 的 `AgentLoop`，连续调用两次 `run()`：

- 断言两次后 `agent.session_id` 未变化。
- 查询该 session 下消息，断言至少包含 4 条 user/assistant 消息。
- 断言没有创建第二个 session。

### system prompt 单例测试

连续调用两次 `run()` 后：

- 断言 `agent.messages` 中 `role == "system"` 的消息只有一条。

## 验收标准

- 同一进程内，阿福能基于上一轮对话回答用户身份问题。
- 现有测试通过。
- 新增连续上下文相关测试通过。
- 代码不包含 Phase 2 记忆能力实现。
- 输出重复问题保持现状，不在本次修改中处理。

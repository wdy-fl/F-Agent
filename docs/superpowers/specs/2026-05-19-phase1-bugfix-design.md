# Phase 1 MVP Bug 修复方案

> 状态：实施中 | 2026-05-19 开始，2026-05-20 继续

## 背景

2026-05-19 对 Phase 1 MVP 进行了人工验证，发现 4 个问题。本文档记录问题根因与修复方案（逐个讨论确认后实施）。

---

## 问题清单总览

| # | 问题 | 严重度 | 影响范围 |
|---|------|--------|---------|
| 1 | 流式输出后内容重复渲染两遍 | 高 | 所有对话回复 |
| 2 | DeepSeek V4 调用工具时 400 报错 | 阻断 | 工具调用场景 |
| 3 | 会话统计始终为 0 | 中 | /stats 命令 |
| 4 | 系统提示词承诺了未实现的功能 | 低 | 用户预期管理 |

---

## 问题 #1：流式输出后内容重复渲染

### 现象

每次对话，阿福的回复都会出现两遍：
- 第一遍：流式逐字输出（正确）
- 第二遍：流式结束后，Rich Markdown 再次完整渲染（多余）

```
阿福: 你好！我是阿福（F-Agent），你的个人智能助手。  ← 流式输出（正确）
       ...
你好！我是阿福（F-Agent），你的个人智能助手。      ← Markdown 二次渲染（多余）
```

### 根因

`cli/interface.py` 第 76-94 行：

```python
# run() 中
result = self.agent.run(user_input, self.system_prompt)  # 流式输出已在回调中打印

self._is_streaming = False
if self._stream_buffer:       # ← _stream_buffer 在收到 "\n" 回调时被重置为 ""
    self.console.print()
elif result:                  # ← 空字符串为 falsy，误入此分支
    self.console.print()
    self.console.print(Markdown(result))  # ← 二次渲染
```

交互链路：
1. `agent/loop.py` 的 `_call_llm_stream()` 流式完成内容输出后，调用 `self.output_callback("\n")`
2. `_on_stream_delta("\n")` 执行 `self.console.print()`（换行），并将 `self._stream_buffer = ""`
3. 回到 `run()`，`if self._stream_buffer:` → 空字符串 falsy → 落入 `elif result:` → 再次渲染

### 修复方案（已确认）

**目标**：流式打底 + 最终 Markdown 升级，同一位置，无缝切换，不重复。

**实现**：用 `rich.live.Live` 管理输出区域。

- 流式中：Live 区域实时显示纯文本（用户看到文字逐字出现）
- 流式完成后：Live 区域刷新成 `Markdown(content)`（纯文本"升级"为格式化内容）
- Live 结束后：Markdown 内容自然留在终端上

改动集中在 `cli/interface.py`：
1. 移除直接的 `console.print(text, end="")` 逐字输出方式
2. `run()` 中创建 `Live` 上下文，`_on_stream_delta` 改为往 Live 里刷新纯文本
3. 流式完成后 `live.update(Markdown(content))`，再结束 Live

`agent/loop.py` 不需要改。

---

## 问题 #2：DeepSeek V4 reasoning_content 400 报错

### 现象

当 Agent 尝试调用工具时，DeepSeek API 返回 400：

```
openai.BadRequestError: Error code: 400 - {'error': {'message':
'The `reasoning_content` in the thinking mode must be passed back to the API.'}}
```

纯文本对话（不调用工具）正常，一旦涉及工具调用就崩溃。

### 根因

DeepSeek V4（deepseek-v4-pro）开启 thinking 模式后，API 返回的 assistant 消息中除了 `content` 和 `tool_calls`，还包含 `reasoning_content` 字段。DeepSeek 要求这个字段在后续请求中**必须原样回传**给 API。

当前代码链路有两处丢失 `reasoning_content`：

**丢失点 1 — `llm/client.py` 流式解析（`chat_stream`）：**

```python
# 第 96-113 行：只处理了 delta.content 和 delta.tool_calls
# delta.reasoning_content 被完全忽略
if delta.content:
    current_content += delta.content
    yield {"type": "content_delta", "content": delta.content}
```

流式模式下，`reasoning_content` 也以增量形式出现在 `delta.reasoning_content` 中，需要拼接到完整值。

**丢失点 2 — `llm/client.py` 非流式解析（`_parse_response`）：**

```python
# 第 142-165 行：只提取了 content 和 tool_calls
# message.reasoning_content 被忽略
result = {
    "finish_reason": choice.finish_reason,
    "content": message.content or "",
}
```

**丢失点 3 — `agent/loop.py` 消息构造（`_call_llm_stream`）：**

```python
# 第 122-125 行：构造 assistant 消息时未包含 reasoning_content
assistant_msg = {"role": "assistant", "content": full_content}
if tool_calls:
    assistant_msg["tool_calls"] = tool_calls
```

需要将 `reasoning_content` 字段加入 assistant 消息中一并发送回 API。

**丢失点 4 — `db/session.py` SessionDB：**

`append_message()` 和 `get_messages_as_conversation()` 未处理 `reasoning_content`。如果恢复历史会话继续对话，同样会触发 400。

### 修复方案（已确认）

打通 4 个环节：

| 环节 | 文件 | 改动 |
|------|------|------|
| 1 | `llm/client.py` chat_stream | 流式中拼接 `delta.reasoning_content`，done 事件中携带 |
| 2 | `llm/client.py` _parse_response | 非流式从 `message.reasoning_content` 取值 |
| 3 | `agent/loop.py` _call_llm_stream | 构造 assistant 消息时携带 `reasoning_content` |
| 4 | `db/schema.py` + `db/session.py` | messages 表加 `reasoning_content TEXT` 列，append_message 增加参数，get_messages_as_conversation 回传时携带 |

---

## 问题 #3：会话统计始终为 0

### 现象

`/stats` 命令输出始终为 0：

```
会话统计
  消息数: 0
  工具调用: 0
  输入 Token: 0
  输出 Token: 0
```

### 根因

`db/session.py` 提供了 `update_session_stats()` 方法，但 `agent/loop.py` 中从未调用它。

### 修复方案（已确认）

- `llm/client.py` chat_stream：请求增加 `stream_options={"include_usage": True}`，捕获最后 chunk 的 usage，done 事件携带
- `agent/loop.py`：每次消息持久化后调用 `update_session_stats(message_count=1)`，工具调用轮次追加 `tool_call_count=N`，拿到 done 事件的 usage 后更新 token 统计

---

## 问题 #4：系统提示词承诺了未实现功能

### 现象

系统提示词声称：

```
- 持久记忆：跨会话记住用户偏好和历史对话
- 技能自创：完成复杂任务后提炼可复用技能
```

但 Phase 1 中 `memory/`、`context/`、`skills/` 目录只有空的 `__init__.py`，实际无任何实现。用户体验落差大——告诉 Agent 自己叫什么，下一轮问"你还记得我吗"，Agent 回答"不认识"。

### 修复方向

### 修复方案（已确认）

采用方案 A：从 `AGENT_IDENTITY` 中移除"持久记忆"和"技能自创"，如实描述 Phase 1 实际能力。

```python
## 核心能力
- 智能对话：理解用户意图，提供有帮助的回答
- 工具调用：通过工具与系统交互（终端执行、文件操作、Web 搜索等）
```

同时检查 `MEMORY_GUIDANCE` 段落，如果不需要就一并移除。

---

## 讨论记录

| 问题 | 日期 | 结论 |
|------|------|------|
| #1 输出重复 | 2026-05-19 | 采用 `rich.live.Live` 方案：流式纯文本 → 完成后原地升级为 Markdown，同一区域无缝切换 |
| #2 reasoning_content 400 报错 | 2026-05-19 | 打通 4 环节：流式/非流式解析捕获 → 消息构造携带 → messages 表加列持久化 |
| #3 会话统计始终为 0 | 2026-05-19 | DeepSeek 流式开启 `include_usage` 获取真实 usage，loop.py 在各持久化点调用 update_session_stats |
| #4 提示词承诺未实现功能 | 2026-05-19 | 方案 A：移除"持久记忆"和"技能自创"能力描述，如实写 Phase 1 实际能力 |

## 实施进度

| Task | 状态 | 提交 | 备注 |
|------|------|------|------|
| Task 1: prompt.py | ✅ 完成 | c0586c9 | AGENT_IDENTITY 缩减 + MEMORY_GUIDANCE 移除 |
| Task 2: client.py | ✅ 完成 | eeddd2d | reasoning_content + usage 捕获，token 计数器更新 |
| Task 3: loop.py | ✅ 完成 | defa062, 9909631 | reasoning_content 携带 + stats 更新 + 进程内上下文连续性 |
| Task 4: db/ | ✅ 完成 | 待提交 | messages 表加 reasoning_content 列 + SessionDB 存取 + loop.py 持久化 |
| Task 5: cli/interface.py | ✅ 完成 | 待提交 | Live 流式 + Markdown 升级，消除重复渲染 |

> **全部 5 个 Task 已完成，37 个测试全部通过。**

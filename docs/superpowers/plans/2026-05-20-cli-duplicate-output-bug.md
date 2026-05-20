# CLI 流式输出重复打印 Bug 记录

## 背景

用户在真实运行阿福 CLI 时发现，每次助手回复会显示两遍：第一遍是流式输出，第二遍是同一内容再次以 rich Markdown 形式渲染输出。

该问题与进程内连续上下文修复无直接依赖，之前已在手动验证中稳定出现。用户已明确要求不纳入本次连续上下文修复，后续单独处理。

## 现象

示例：

```text
你: 你好，你是谁？
阿福: 你好！我是阿福（F-Agent），你的个人智能助手。
...

你好！我是阿福（F-Agent），你的个人智能助手。
...
```

同一段 assistant 回复出现两次：

1. 第一遍：流式 delta 回调实时打印。
2. 第二遍：`AgentLoop.run()` 返回完整 `result` 后，CLI 再次 Markdown 渲染打印。

## 初步根因

当前数据流大致如下：

```text
LLMClient.chat_stream()
  ↓ content_delta
AgentLoop._call_llm_stream()
  ↓ self.output_callback(event["content"])
CLIInterface._on_stream_delta()
  ↓ 实时打印文本

LLM 流结束
  ↓ AgentLoop.run() 返回完整 result
CLIInterface.run()
  ↓ 如果 _stream_buffer 为空且 result 非空，再次 Markdown 打印 result
```

关键位置：

- `agent/loop.py`
  - `_call_llm_stream()` 中对每个 `content_delta` 调用 `self.output_callback(event["content"])`。
  - 流结束后调用 `self.output_callback("\n")`。

- `cli/interface.py`
  - `_on_stream_delta()` 收到普通文本时追加到 `_stream_buffer`。
  - `_on_stream_delta()` 收到 `"\n"` 时会清空 `_stream_buffer`。
  - `run()` 中流式结束后，如果 `_stream_buffer` 为空且 `result` 非空，会再次打印 Markdown。

因此，`_stream_buffer` 被换行回调清空后，CLI 误判为“本轮没有流式输出”，于是又打印了一次完整结果。

## 涉及文件

- `agent/loop.py`
  - `_call_llm_stream()` 的输出回调行为。

- `cli/interface.py`
  - `_on_stream_delta()` 的缓冲区维护。
  - `run()` 中根据 `_stream_buffer` 和 `result` 决定是否补充渲染的逻辑。

## 建议修复范围

建议只修复 CLI 输出状态判断，不改变 AgentLoop 的核心流式调用语义。

可选最小方案：

1. 在 `CLIInterface` 中新增一个布尔标记，例如：

```python
self._stream_had_output = False
```

2. 每轮调用前重置：

```python
self._stream_had_output = False
```

3. `_on_stream_delta()` 收到非换行文本时设置：

```python
self._stream_had_output = True
```

4. `run()` 中决定是否打印 Markdown 时，不再依赖 `_stream_buffer` 是否为空，而是判断：

```python
if not self._stream_had_output and result:
    self.console.print()
    self.console.print(Markdown(result))
```

## 测试建议

新增 CLI 层单元测试或轻量集成测试：

- 模拟 `AgentLoop.run()` 通过 `_on_stream_delta()` 输出过内容，并返回同样的 `result`。
- 断言 CLI 不会再次 Markdown 打印完整结果。
- 模拟无流式输出但有 `result` 的情况，断言 CLI 仍会 Markdown 打印结果。

## 非目标

本问题不处理：

- DeepSeek thinking mode 的 `reasoning_content` 丢失问题。
- Phase 2 跨会话记忆系统。
- 提示词中“跨对话记忆”能力描述超前问题。
- AgentLoop 进程内连续上下文能力。

## 当前状态

- 问题已在真实 CLI 运行中复现。
- 尚未修复。
- 应作为独立任务处理。

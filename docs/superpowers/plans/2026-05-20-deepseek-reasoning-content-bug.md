# DeepSeek thinking mode reasoning_content 丢失 Bug 记录

## 背景

在 `fix/process-context-continuity` 分支上，已实现进程内连续对话上下文：同一个 `AgentLoop` 生命周期内会保留历史 user / assistant / tool 消息，并在后续请求中回传给 LLM。

该修复通过了 mock 测试，但用户使用真实 DeepSeek thinking mode 模型手动验证时触发 400 错误。

## 现象

启动阿福后连续对话：

```text
你: 你好，你是谁？
阿福: ...
你: 你知道我是谁吗？
阿福: ...
你: 我的名字是王当当，你可以叫我当当大人
阿福:
Traceback ...
openai.BadRequestError: Error code: 400 - {'error': {'message': 'The `reasoning_content` in the thinking mode must be passed back to the API.', 'type': 'invalid_request_error', 'param': None, 'code': 'invalid_request_error'}}
```

## 复现条件

- 使用 DeepSeek thinking mode 相关模型。
- `workspace/config.yaml` 中模型配置指向 DeepSeek：

```yaml
llm:
  base_url: "https://api.deepseek.com"
  model: "deepseek-v4-pro"
```

- 使用当前进程内连续上下文实现，即后续请求会带上历史 assistant 消息。

## 初步根因

当前 `LLMClient.chat_stream()` 只解析并返回：

- `delta.content`
- `delta.tool_calls`

没有解析或保留 DeepSeek thinking mode 返回的：

- `delta.reasoning_content`

当前数据流断点：

```text
DeepSeek 返回 reasoning_content
  ↓
llm/client.py 的 chat_stream() 未收集该字段
  ↓
agent/loop.py 构造历史 assistant message 时只保存 content / tool_calls
  ↓
下一轮请求把缺少 reasoning_content 的 assistant 历史消息发回 DeepSeek
  ↓
DeepSeek 返回 400：reasoning_content in thinking mode must be passed back
```

## 涉及文件

- `llm/client.py`
  - `LLMClient.chat_stream()` 需要收集并在 done event 中返回 `reasoning_content`。
  - 非流式 `_parse_response()` 后续也可能需要检查是否存在 `message.reasoning_content`，但当前崩溃路径来自流式调用。

- `agent/loop.py`
  - `_call_llm_stream()` 需要接收 done event 中的 `reasoning_content`。
  - 构造 assistant 历史消息时，如存在 `reasoning_content`，需要保留该字段。

- `tests/test_llm_client.py`
  - 增加流式 `reasoning_content` 聚合测试。

- `tests/test_agent_full.py`
  - 增加多轮对话测试：第一轮 assistant 带 `reasoning_content`，第二轮传给 LLM 的历史 messages 必须保留该字段。

## 建议修复范围

仅修复 DeepSeek thinking mode 下 `reasoning_content` 丢失导致的真实运行崩溃。

建议最小修复：

1. `LLMClient.chat_stream()` 中新增 `reasoning_content_parts` 累积。
2. 对每个 chunk，使用安全方式读取 `delta.reasoning_content`。
3. done event 中如果存在 reasoning 内容，则返回：

```python
{
    "type": "done",
    "finish_reason": "stop",
    "content": current_content,
    "reasoning_content": reasoning_content,
}
```

4. `AgentLoop._call_llm_stream()` 在构造 assistant message 时保留：

```python
assistant_msg = {"role": "assistant", "content": full_content}
if reasoning_content:
    assistant_msg["reasoning_content"] = reasoning_content
```

5. 对持久化到 SQLite 的内容暂不扩 schema；当前目标是保证内存上下文回传可用。是否持久化 `reasoning_content` 可留给后续会话持久化增强单独设计。

## 非目标

本 bug 修复不处理以下问题：

- CLI 流式输出重复打印问题。
- Phase 2 跨会话记忆、FTS5 搜索召回、USER.md 用户画像。
- memory 工具实现。
- 提示词中“跨对话记忆”能力描述超前问题。

## 当前状态

- 进程内连续上下文修复尚未提交。
- 当前分支：`fix/process-context-continuity`。
- 完整测试曾通过：`32 passed`，但真实 DeepSeek thinking mode 手动验证失败。
- 下一会话应优先补充失败测试，再实现最小修复。

"""LLM Client 冒烟测试：验证 OpenAI SDK 调用链路"""

from unittest.mock import MagicMock, patch

from config.settings import LLMConfig
from llm.client import LLMClient


def _make_mock_response(content: str | None = "你好", tool_calls=None, finish_reason="stop", usage=None):
    """构造 mock 的 OpenAI 响应对象"""
    message = MagicMock()
    message.content = content
    message.tool_calls = tool_calls

    choice = MagicMock()
    choice.message = message
    choice.finish_reason = finish_reason

    response = MagicMock()
    response.choices = [choice]
    response.usage = usage

    return response


def test_chat_basic():
    """测试非流式基础对话"""
    mock_response = _make_mock_response(
        content="你好！我是阿福。",
        usage=MagicMock(prompt_tokens=10, completion_tokens=5),
    )

    config = LLMConfig(api_key="sk-test", model="gpt-4o-mini")
    client = LLMClient(config)

    with patch.object(client.client.chat.completions, "create", return_value=mock_response):
        result = client.chat([{"role": "user", "content": "你好"}])

    assert result["content"] == "你好！我是阿福。"
    assert result["finish_reason"] == "stop"
    assert result.get("tool_calls") is None
    assert client.total_input_tokens == 10
    assert client.total_output_tokens == 5


def test_chat_with_tool_calls():
    """测试非流式工具调用响应"""
    tc = MagicMock()
    tc.id = "call_123"
    tc.function.name = "terminal"
    tc.function.arguments = '{"command": "ls"}'

    mock_response = _make_mock_response(
        content=None,
        tool_calls=[tc],
        finish_reason="tool_calls",
        usage=MagicMock(prompt_tokens=15, completion_tokens=8),
    )

    config = LLMConfig(api_key="sk-test")
    client = LLMClient(config)

    with patch.object(client.client.chat.completions, "create", return_value=mock_response):
        result = client.chat(
            [{"role": "user", "content": "列出当前目录"}],
            tools=[{"type": "function", "function": {"name": "terminal", "parameters": {}}}],
        )

    assert result["finish_reason"] == "tool_calls"
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["function"]["name"] == "terminal"


def test_chat_stream():
    """测试流式对话"""
    config = LLMConfig(api_key="sk-test")
    client = LLMClient(config)

    # 构造流式 chunk 序列
    chunks = []
    for text in ["你", "好", "！"]:
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta = MagicMock(content=text, reasoning_content=None, tool_calls=None)
        chunk.choices[0].finish_reason = None
        chunks.append(chunk)

    # 结束 chunk
    end_chunk = MagicMock()
    end_chunk.choices = [MagicMock()]
    end_chunk.choices[0].delta = MagicMock(content=None, reasoning_content=None, tool_calls=None)
    end_chunk.choices[0].finish_reason = "stop"
    chunks.append(end_chunk)

    with patch.object(client.client.chat.completions, "create", return_value=iter(chunks)):
        events = list(client.chat_stream([{"role": "user", "content": "你好"}]))

    content_deltas = [e for e in events if e["type"] == "content_delta"]
    done_event = [e for e in events if e["type"] == "done"][0]

    assert len(content_deltas) == 3
    assert done_event["content"] == "你好！"
    assert done_event["finish_reason"] == "stop"


def test_count_tokens():
    """测试 Token 估算"""
    config = LLMConfig(api_key="sk-test")
    client = LLMClient(config)

    # 纯英文
    assert client.count_tokens("hello world") > 0

    # 包含中文
    assert client.count_tokens("你好世界") > 0


def test_chat_stream_with_reasoning_content():
    """测试流式响应中 reasoning_content 的捕获"""
    config = LLMConfig(api_key="sk-test")
    client = LLMClient(config)

    chunks = []
    # 第一个 chunk 带 reasoning_content
    chunk1 = MagicMock()
    chunk1.choices = [MagicMock()]
    chunk1.choices[0].delta = MagicMock(content=None, reasoning_content="Let me think", tool_calls=None)
    chunk1.choices[0].finish_reason = None
    chunk1.usage = None
    chunks.append(chunk1)

    # 第二个 chunk 带 content
    chunk2 = MagicMock()
    chunk2.choices = [MagicMock()]
    chunk2.choices[0].delta = MagicMock(content="Hello", reasoning_content=None, tool_calls=None)
    chunk2.choices[0].finish_reason = None
    chunk2.usage = None
    chunks.append(chunk2)

    # 结束 chunk 带 usage（DeepSeek-style: usage appears on final chunk at top level）
    end_chunk = MagicMock()
    end_chunk.choices = [MagicMock()]
    end_chunk.choices[0].delta = MagicMock(content=None, reasoning_content=None, tool_calls=None)
    end_chunk.choices[0].finish_reason = "stop"
    from openai.types.completion_usage import CompletionUsage
    end_chunk.usage = CompletionUsage(prompt_tokens=12, completion_tokens=8, total_tokens=20)
    chunks.append(end_chunk)

    with patch.object(client.client.chat.completions, "create", return_value=iter(chunks)):
        events = list(client.chat_stream([{"role": "user", "content": "Hi"}]))

    done_event = [e for e in events if e["type"] == "done"][0]
    assert done_event["content"] == "Hello"
    assert done_event.get("reasoning_content") == "Let me think"
    assert done_event.get("usage") == {"prompt_tokens": 12, "completion_tokens": 8}
    assert client.total_input_tokens == 12
    assert client.total_output_tokens == 8


def test_chat_with_reasoning_content():
    """测试非流式响应中 reasoning_content 的捕获"""
    message = MagicMock()
    message.content = "Hello"
    message.tool_calls = None
    message.reasoning_content = "Let me think"

    choice = MagicMock()
    choice.message = message
    choice.finish_reason = "stop"

    response = MagicMock()
    response.choices = [choice]
    response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)

    config = LLMConfig(api_key="sk-test")
    client = LLMClient(config)

    with patch.object(client.client.chat.completions, "create", return_value=response):
        result = client.chat([{"role": "user", "content": "Hi"}])

    assert result["content"] == "Hello"
    assert result.get("reasoning_content") == "Let me think"

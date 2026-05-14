"""Agent 主循环冒烟测试：验证最小循环可运行"""

from unittest.mock import patch

from agent.loop import AgentLoop
from agent.prompt import build_system_prompt
from config.settings import LLMConfig
from llm.client import LLMClient


def _make_stream_events(content="你好！我是阿福。", tool_calls=None):
    """构造流式事件序列"""
    events = []
    for char in content:
        events.append({"type": "content_delta", "content": char})
    events.append({
        "type": "done",
        "finish_reason": "stop",
        "content": content,
        "tool_calls": tool_calls,
    })
    return events


def test_agent_loop_basic(capsys):
    """测试基础对话流程"""
    config = LLMConfig(api_key="sk-test")
    llm = LLMClient(config)
    agent = AgentLoop(llm, max_iterations=10)

    stream_events = _make_stream_events("你好！我是阿福。")
    with patch.object(llm, "chat_stream", return_value=iter(stream_events)):
        result = agent.run("你好", build_system_prompt())

    assert result == "你好！我是阿福。"
    assert len(agent.messages) == 3  # system + user + assistant


def test_agent_loop_with_tool_calls(capsys):
    """测试收到工具调用时的处理（最小循环不支持工具，应返回提示）"""
    config = LLMConfig(api_key="sk-test")
    llm = LLMClient(config)
    agent = AgentLoop(llm, max_iterations=10)

    stream_events = _make_stream_events(
        content="",
        tool_calls=[{
            "id": "call_1",
            "type": "function",
            "function": {"name": "terminal", "arguments": '{"command": "ls"}'},
        }],
    )
    with patch.object(llm, "chat_stream", return_value=iter(stream_events)):
        result = agent.run("列出当前目录", build_system_prompt())

    assert "暂不支持" in result


def test_build_system_prompt():
    """测试系统提示词构建"""
    prompt = build_system_prompt()
    assert "阿福" in prompt
    assert "当前时间" in prompt

    prompt_with_tools = build_system_prompt(include_tools=True)
    assert "工具使用" in prompt_with_tools

    prompt_with_memory = build_system_prompt(include_memory_guidance=True)
    assert "记忆工具" in prompt_with_memory

"""Agent 主循环冒烟测试：验证最小循环可运行"""

from unittest.mock import patch

from agent.loop import AgentLoop
from agent.prompt import build_system_prompt
from config.settings import LLMConfig
from llm.client import LLMClient


def _make_stream_events(content="你好！我是阿福。", tool_calls=None, finish_reason="stop"):
    """构造流式事件序列"""
    events = []
    for char in content:
        events.append({"type": "content_delta", "content": char})
    events.append({
        "type": "done",
        "finish_reason": finish_reason if tool_calls else "stop",
        "content": content,
        "tool_calls": tool_calls,
    })
    return events


def test_agent_loop_basic():
    """测试基础对话流程"""
    config = LLMConfig(api_key="sk-test")
    llm = LLMClient(config)
    agent = AgentLoop(llm, max_iterations=10, output_callback=lambda t: None)

    stream_events = _make_stream_events("你好！我是阿福。")
    with patch.object(llm, "chat_stream", return_value=iter(stream_events)):
        result = agent.run("你好", build_system_prompt())

    assert result == "你好！我是阿福。"
    assert len(agent.messages) == 3  # system + user + assistant


def test_agent_loop_tool_calls_execute():
    """测试工具调用会被执行，循环继续直到获得最终回复"""
    config = LLMConfig(api_key="sk-test")
    llm = LLMClient(config)
    agent = AgentLoop(llm, max_iterations=10, output_callback=lambda t: None)

    # 确保终端工具已注册
    import tools.terminal
    import importlib
    importlib.reload(tools.terminal)

    # 第一次返回工具调用
    tool_events = _make_stream_events(
        content="",
        tool_calls=[{
            "id": "call_1",
            "type": "function",
            "function": {"name": "terminal", "arguments": '{"command": "echo hello"}'},
        }],
        finish_reason="tool_calls",
    )
    # 第二次返回最终回复
    final_events = _make_stream_events("命令执行成功，输出 hello")

    with patch.object(llm, "chat_stream", side_effect=[iter(tool_events), iter(final_events)]):
        result = agent.run("运行命令", build_system_prompt(include_tools=True))

    assert result == "命令执行成功，输出 hello"
    # 消息列表应包含工具结果
    assert any(msg.get("role") == "tool" for msg in agent.messages)


def test_build_system_prompt():
    """测试系统提示词构建"""
    prompt = build_system_prompt()
    assert "阿福" in prompt
    assert "当前时间" in prompt

    prompt_with_tools = build_system_prompt(include_tools=True)
    assert "工具使用" in prompt_with_tools

    prompt_with_memory = build_system_prompt(include_memory_guidance=True)
    assert "记忆工具" in prompt_with_memory

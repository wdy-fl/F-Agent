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


def test_agent_loop_budget_exhaustion_uses_single_grace_call():
    """预算耗尽后只进行一次 grace call，不额外放行正常调用。"""
    config = LLMConfig(api_key="sk-test")
    llm = LLMClient(config)
    agent = AgentLoop(llm, max_iterations=1, output_callback=lambda t: None)

    tool_events = _make_stream_events(
        content="",
        tool_calls=[{
            "id": "call_1",
            "type": "function",
            "function": {"name": "terminal", "arguments": '{"command": "echo hello"}'},
        }],
        finish_reason="tool_calls",
    )
    grace_events = _make_stream_events("预算已耗尽，这是最终总结。")

    import importlib
    import tools.terminal
    importlib.reload(tools.terminal)

    with patch.object(llm, "chat_stream", side_effect=[iter(tool_events), iter(grace_events)]) as chat_stream:
        result = agent.run("运行命令", build_system_prompt(include_tools=True))

    assert result == "预算已耗尽，这是最终总结。"
    assert chat_stream.call_count == 2
    assert agent.budget.remaining == 0
    assert any(
        msg.get("role") == "user" and msg.get("content") == "请总结当前进展并给出最终回复。"
        for msg in agent.messages
    )


def test_agent_loop_grace_call_does_not_expose_tools():
    """预算耗尽后的最终总结调用不再暴露工具定义。"""
    config = LLMConfig(api_key="sk-test")
    llm = LLMClient(config)
    agent = AgentLoop(llm, max_iterations=1, output_callback=lambda t: None)

    tool_events = _make_stream_events(
        content="",
        tool_calls=[{
            "id": "call_1",
            "type": "function",
            "function": {"name": "terminal", "arguments": '{"command": "echo hello"}'},
        }],
        finish_reason="tool_calls",
    )
    grace_events = _make_stream_events("预算已耗尽，这是最终总结。")

    import importlib
    import tools.terminal
    importlib.reload(tools.terminal)

    with patch.object(llm, "chat_stream", side_effect=[iter(tool_events), iter(grace_events)]) as chat_stream:
        agent.run("运行命令", build_system_prompt(include_tools=True))

    assert chat_stream.call_args_list[0].kwargs["tools"]
    assert chat_stream.call_args_list[1].kwargs["tools"] is None


def test_agent_loop_preserves_reasoning_content():
    """测试 reasoning_content 在 assistant 消息中被保留"""
    config = LLMConfig(api_key="sk-test")
    llm = LLMClient(config)
    agent = AgentLoop(llm, max_iterations=10, output_callback=lambda t: None)

    events = _make_stream_events(content="Hello")
    # 手动注入 reasoning_content 到 done 事件
    events[-1]["reasoning_content"] = "I should greet the user"

    with patch.object(llm, "chat_stream", return_value=iter(events)):
        agent.run("Hi", build_system_prompt())

    assistant_msgs = [m for m in agent.messages if m["role"] == "assistant"]
    assert len(assistant_msgs) == 1
    assert assistant_msgs[0].get("reasoning_content") == "I should greet the user"


def test_agent_loop_restore_session_loads_persisted_messages(tmp_path):
    """恢复历史会话后，AgentLoop 使用持久化消息继续对话。"""
    from db.session import SessionDB

    db = SessionDB(tmp_path / "test.db")
    db.create_session("sess-restore", "deepseek-v4-pro", "old system")
    db.append_message("sess-restore", "user", content="之前的问题")
    db.append_message("sess-restore", "assistant", content="之前的回答")

    config = LLMConfig(api_key="sk-test")
    llm = LLMClient(config)
    agent = AgentLoop(llm, session_db=db, output_callback=lambda t: None)

    restored_count = agent.restore_session("sess-restore", "new system")

    assert restored_count == 2
    assert agent.session_id == "sess-restore"
    assert agent.messages[0] == {"role": "system", "content": "new system"}
    assert agent.messages[1] == {"role": "user", "content": "之前的问题"}
    assert agent.messages[2] == {"role": "assistant", "content": "之前的回答"}
    db.close()


def test_agent_loop_restore_session_rejects_missing_session(tmp_path):
    """恢复不存在的会话时抛出清晰错误。"""
    from db.session import SessionDB
    import pytest

    db = SessionDB(tmp_path / "test.db")
    config = LLMConfig(api_key="sk-test")
    llm = LLMClient(config)
    agent = AgentLoop(llm, session_db=db, output_callback=lambda t: None)

    with pytest.raises(ValueError, match="Session not found"):
        agent.restore_session("missing", "system")
    db.close()


def test_agent_loop_restore_session_requires_session_db():
    """未配置 SessionDB 时不能恢复会话。"""
    import pytest

    config = LLMConfig(api_key="sk-test")
    llm = LLMClient(config)
    agent = AgentLoop(llm, output_callback=lambda t: None)

    with pytest.raises(ValueError, match="Session DB not configured"):
        agent.restore_session("sess", "system")


def test_agent_loop_restore_session_continues_same_session(tmp_path):
    """恢复后继续对话时复用原 session 写入新消息。"""
    from db.session import SessionDB

    db = SessionDB(tmp_path / "test.db")
    db.create_session("sess-continue", "deepseek-v4-pro", "old system")
    db.append_message("sess-continue", "user", content="之前的问题")
    db.append_message("sess-continue", "assistant", content="之前的回答")

    config = LLMConfig(api_key="sk-test")
    llm = LLMClient(config)
    agent = AgentLoop(llm, session_db=db, output_callback=lambda t: None)
    agent.restore_session("sess-continue", "new system")

    stream_events = _make_stream_events("继续后的回答")
    with patch.object(llm, "chat_stream", return_value=iter(stream_events)):
        result = agent.run("继续提问", "new system")

    assert result == "继续后的回答"
    assert agent.session_id == "sess-continue"
    assert len(db.list_sessions()) == 1
    conversation = db.get_messages_as_conversation("sess-continue")
    assert [msg["role"] for msg in conversation] == ["user", "assistant", "user", "assistant"]
    assert conversation[-2]["content"] == "继续提问"
    assert conversation[-1]["content"] == "继续后的回答"
    db.close()


def test_build_system_prompt():
    """测试系统提示词构建"""
    prompt = build_system_prompt()
    assert "阿福" in prompt
    assert "当前时间" in prompt

    prompt_with_tools = build_system_prompt(include_tools=True)
    assert "工具使用" in prompt_with_tools

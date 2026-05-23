"""预算控制和完整 Agent 循环测试"""

from copy import deepcopy
from unittest.mock import patch

from agent.budget import IterationBudget
from agent.loop import AgentLoop
from config.settings import LLMConfig
from db.session import SessionDB
from llm.client import LLMClient


def test_budget_basic():
    """测试基础预算消耗"""
    budget = IterationBudget(max_iterations=3)

    assert budget.remaining == 3
    assert budget.consume()  # 3 → 2
    assert budget.consume()  # 2 → 1
    assert budget.consume()  # 1 → 0
    assert not budget.consume()  # 已耗尽


def test_budget_can_continue_only_checks_normal_iterations():
    """测试预算耗尽后不再放行正常迭代。"""
    budget = IterationBudget(max_iterations=1)

    assert budget.can_continue()
    budget.consume()  # 耗尽

    assert budget.remaining == 0
    assert not budget.can_continue()


def test_budget_interrupt():
    """测试中断信号"""
    budget = IterationBudget(max_iterations=10)

    assert budget.can_continue()
    budget.interrupt()
    assert budget.is_interrupted
    assert not budget.can_continue()


def test_budget_reset():
    """测试预算重置"""
    budget = IterationBudget(max_iterations=2)
    budget.consume()
    budget.consume()
    budget.interrupt()

    budget.reset()
    assert budget.remaining == 2
    assert not budget.is_interrupted


def test_agent_loop_with_tool_execution():
    """测试完整的工具执行循环"""
    config = LLMConfig(api_key="sk-test")
    llm = LLMClient(config)

    # 第一次调用返回工具调用
    tool_call_events = [
        {"type": "content_delta", "content": "让我查看一下"},
        {"type": "done", "finish_reason": "tool_calls", "content": "让我查看一下", "tool_calls": [{
            "id": "call_1",
            "type": "function",
            "function": {"name": "terminal", "arguments": '{"command": "echo hi"}'},
        }]},
    ]
    # 第二次调用返回最终回复
    final_events = [
        {"type": "content_delta", "content": "命令执行成功"},
        {"type": "done", "finish_reason": "stop", "content": "命令执行成功", "tool_calls": None},
    ]

    agent = AgentLoop(llm, max_iterations=10, output_callback=lambda t: None)

    # 导入工具模块以确保注册
    import tools.terminal
    import importlib
    importlib.reload(tools.terminal)

    with patch.object(llm, "chat_stream", side_effect=[iter(tool_call_events), iter(final_events)]):
        result = agent.run("运行命令")

    assert result == "命令执行成功"
    # 验证消息列表包含工具结果
    assert any(msg.get("role") == "tool" for msg in agent.messages)


def test_agent_loop_with_session_persistence(tmp_path):
    """测试 Agent 循环集成会话持久化"""
    config = LLMConfig(api_key="sk-test")
    llm = LLMClient(config)
    session_db = SessionDB(tmp_path / "test.db")

    events = [
        {"type": "content_delta", "content": "你好！"},
        {"type": "done", "finish_reason": "stop", "content": "你好！", "tool_calls": None},
    ]

    agent = AgentLoop(llm, max_iterations=10, session_db=session_db, output_callback=lambda t: None)

    with patch.object(llm, "chat_stream", return_value=iter(events)):
        result = agent.run("你好")

    assert result == "你好！"
    assert agent.session_id is not None

    # 验证会话已持久化
    session = session_db.get_session(agent.session_id)
    assert session is not None

    messages = session_db.get_messages(agent.session_id)
    assert len(messages) >= 2  # user + assistant
    session_db.close()


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
        agent.run("我的名字是王当当，你可以叫我当当大人")
        result = agent.run("现在你知道我是谁了吗？")

    assert result == "知道，您是王当当"
    assert len(captured_messages) == 2
    second_call_messages = captured_messages[1]
    assert second_call_messages == [
        {"role": "system", "content": agent.system_prompt},
        {"role": "user", "content": "我的名字是王当当，你可以叫我当当大人"},
        {"role": "assistant", "content": "好的，当当大人"},
        {"role": "user", "content": "现在你知道我是谁了吗？"},
    ]


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
        agent.run("第一轮")
        first_session_id = agent.session_id
        agent.run("第二轮")

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
        agent.run("第一轮")
        agent.run("第二轮")

    system_messages = [m for m in agent.messages if m["role"] == "system"]
    assert system_messages == [{"role": "system", "content": agent.system_prompt}]

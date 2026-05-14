"""预算控制和完整 Agent 循环测试"""

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


def test_budget_can_continue_with_grace():
    """测试 grace call：预算耗尽后仍允许一次继续"""
    budget = IterationBudget(max_iterations=1)

    budget.consume()  # 耗尽
    assert budget.remaining == 0

    # grace call
    assert budget.can_continue()
    # 第二次不再允许
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
        result = agent.run("运行命令", "You are a helper")

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
        result = agent.run("你好", "You are a helper")

    assert result == "你好！"
    assert agent.session_id is not None

    # 验证会话已持久化
    session = session_db.get_session(agent.session_id)
    assert session is not None

    messages = session_db.get_messages(agent.session_id)
    assert len(messages) >= 2  # user + assistant
    session_db.close()

"""CLI 命令测试"""
from unittest.mock import patch, MagicMock

from cli.interface import CLIInterface
from config.settings import AppConfig, LLMConfig, set_config


def make_cli(tmp_path):
    config = AppConfig(
        llm=LLMConfig(api_key="sk-test"),
        db_path=str(tmp_path / "state.db"),
        user_profile_path=str(tmp_path / "USER.md"),
        memory_path=str(tmp_path / "MEMORY.md"),
        soul_path=str(tmp_path / "SOUL.md"),
        agent_guidance_path=str(tmp_path / "AGENT.md"),
        skills_dir=str(tmp_path / "skills"),
        log_dir=str(tmp_path / "logs"),
    )
    set_config(config)
    return CLIInterface()


def test_list_sessions_with_indices():
    """验证 /sessions 输出带有序号"""
    config = AppConfig(llm=LLMConfig(api_key="sk-test"))
    set_config(config)
    cli = CLIInterface()

    mock_sessions = [
        {"id": "aaa-bbb-ccc", "title": "测试会话", "message_count": 5},
        {"id": "ddd-eee-fff", "title": None, "message_count": 2},
    ]
    cli.session_db.list_sessions = MagicMock(return_value=mock_sessions)

    with patch.object(cli.console, "print") as mock_print:
        cli._list_sessions()

    calls = [str(args[0]) if args else "" for args, _ in mock_print.call_args_list]
    combined = " ".join(calls)
    assert "1[/bold cyan]" in combined
    assert "2[/bold cyan]" in combined
    cli.close()


def test_resume_interactive_valid_choice():
    """验证交互式恢复选择有效序号"""
    config = AppConfig(llm=LLMConfig(api_key="sk-test"))
    set_config(config)
    cli = CLIInterface()

    mock_sessions = [
        {"id": "sess-001", "title": "测试会话1", "message_count": 3},
        {"id": "sess-002", "title": "测试会话2", "message_count": 1},
    ]
    cli.session_db.list_sessions = MagicMock(return_value=mock_sessions)

    with patch.object(cli.prompt_session, "prompt", return_value="1"):
        with patch.object(cli, "_resume_session") as mock_resume:
            cli._resume_interactive()

    mock_resume.assert_called_once_with("sess-001")
    cli.close()


def test_resume_interactive_invalid_choice():
    """验证交互式恢复选择无效序号时提示错误"""
    config = AppConfig(llm=LLMConfig(api_key="sk-test"))
    set_config(config)
    cli = CLIInterface()

    mock_sessions = [
        {"id": "sess-001", "title": "测试会话", "message_count": 3},
    ]
    cli.session_db.list_sessions = MagicMock(return_value=mock_sessions)

    with patch.object(cli.prompt_session, "prompt", return_value="5"):
        with patch.object(cli.console, "print") as mock_print:
            cli._resume_interactive()

    calls = [str(args[0]) if args else "" for args, _ in mock_print.call_args_list]
    assert any("无效的序号" in c for c in calls)
    cli.close()


def test_resume_interactive_empty_sessions():
    """验证无历史会话时的提示"""
    config = AppConfig(llm=LLMConfig(api_key="sk-test"))
    set_config(config)
    cli = CLIInterface()

    cli.session_db.list_sessions = MagicMock(return_value=[])

    with patch.object(cli.console, "print") as mock_print:
        cli._resume_interactive()

    calls = [str(args[0]) if args else "" for args, _ in mock_print.call_args_list]
    assert any("暂无历史会话" in c for c in calls)
    cli.close()


def test_print_conversation_formats_roles():
    """验证对话历史按角色打印"""
    config = AppConfig(llm=LLMConfig(api_key="sk-test"))
    set_config(config)
    cli = CLIInterface()

    messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！有什么可以帮助你的？"},
        {"role": "tool", "content": "命令输出", "tool_call_id": "call_123"},
    ]

    with patch.object(cli.console, "print") as mock_print:
        cli._print_conversation(messages)

    calls = [str(args[0]) if args else "" for args, _ in mock_print.call_args_list]
    combined = " ".join(calls)
    assert "历史对话" in combined
    assert "你:" in combined
    assert "阿福:" in combined
    assert "工具:" in combined
    cli.close()


def test_print_conversation_truncates_long_tool_output():
    """验证长工具输出被截断"""
    config = AppConfig(llm=LLMConfig(api_key="sk-test"))
    set_config(config)
    cli = CLIInterface()

    long_content = "x" * 300
    messages = [
        {"role": "tool", "content": long_content, "tool_call_id": "call_abc"},
    ]

    with patch.object(cli.console, "print") as mock_print:
        cli._print_conversation(messages)

    calls = [str(args[0]) if args else "" for args, _ in mock_print.call_args_list]
    combined = " ".join(calls)
    assert "..." in combined
    assert long_content[:200] in combined
    cli.close()


def test_close_marks_active_session_and_closes_db(tmp_path):
    cli = make_cli(tmp_path)
    cli.agent.session_id = "sess-active"
    cli.session_db.end_session = MagicMock()
    cli.session_db.close = MagicMock()

    cli.close()

    cli.session_db.end_session.assert_called_once_with("sess-active")
    cli.session_db.close.assert_called_once_with()


def test_close_is_idempotent(tmp_path):
    cli = make_cli(tmp_path)
    cli.agent.session_id = "sess-active"
    cli.session_db.end_session = MagicMock()
    cli.session_db.close = MagicMock()

    cli.close()
    cli.close()

    cli.session_db.end_session.assert_called_once_with("sess-active")
    cli.session_db.close.assert_called_once_with()


def test_close_without_session_only_closes_db(tmp_path):
    cli = make_cli(tmp_path)
    cli.agent.session_id = None
    cli.session_db.end_session = MagicMock()
    cli.session_db.close = MagicMock()

    cli.close()

    cli.session_db.end_session.assert_not_called()
    cli.session_db.close.assert_called_once_with()


def test_close_continues_to_close_db_when_end_session_fails(tmp_path):
    cli = make_cli(tmp_path)
    cli.agent.session_id = "sess-active"
    cli.session_db.end_session = MagicMock(side_effect=RuntimeError("end failed"))
    cli.session_db.close = MagicMock()

    cli.close()

    cli.session_db.end_session.assert_called_once_with("sess-active")
    cli.session_db.close.assert_called_once_with()

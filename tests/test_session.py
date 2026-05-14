"""会话持久化冒烟测试：验证 SQLite CRUD 操作"""

from db.session import SessionDB


def test_create_and_get_session(tmp_path):
    """测试创建和查询会话"""
    db = SessionDB(tmp_path / "test.db")

    db.create_session("sess-1", "gpt-4o-mini", "You are a helper", title="测试会话")
    session = db.get_session("sess-1")

    assert session is not None
    assert session["id"] == "sess-1"
    assert session["model"] == "gpt-4o-mini"
    assert session["title"] == "测试会话"
    db.close()


def test_end_session(tmp_path):
    """测试结束会话"""
    db = SessionDB(tmp_path / "test.db")

    db.create_session("sess-2", "gpt-4o-mini", "test")
    db.end_session("sess-2")

    session = db.get_session("sess-2")
    assert session is not None
    assert session["ended_at"] is not None
    db.close()


def test_update_session_stats(tmp_path):
    """测试更新会话统计"""
    db = SessionDB(tmp_path / "test.db")

    db.create_session("sess-3", "gpt-4o-mini", "test")
    db.update_session_stats("sess-3", message_count=3, input_tokens=100, output_tokens=50)

    session = db.get_session("sess-3")
    assert session["message_count"] == 3
    assert session["input_tokens"] == 100
    assert session["output_tokens"] == 50
    db.close()


def test_append_and_get_messages(tmp_path):
    """测试追加和查询消息"""
    db = SessionDB(tmp_path / "test.db")

    db.create_session("sess-4", "gpt-4o-mini", "test")
    db.append_message("sess-4", "user", content="你好")
    db.append_message("sess-4", "assistant", content="你好！我是阿福。")

    messages = db.get_messages("sess-4")
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "你好"
    assert messages[1]["role"] == "assistant"
    db.close()


def test_messages_with_tool_calls(tmp_path):
    """测试带工具调用的消息存储"""
    db = SessionDB(tmp_path / "test.db")

    db.create_session("sess-5", "gpt-4o-mini", "test")
    db.append_message(
        "sess-5",
        "assistant",
        tool_calls=[{
            "id": "call_1",
            "type": "function",
            "function": {"name": "terminal", "arguments": '{"command": "ls"}'},
        }],
    )
    db.append_message(
        "sess-5",
        "tool",
        content='{"exit_code": 0, "stdout": "file1.txt"}',
        tool_call_id="call_1",
        tool_name="terminal",
    )

    messages = db.get_messages("sess-5")
    assert len(messages) == 2
    assert messages[0]["tool_calls"] is not None
    assert messages[0]["tool_calls"][0]["function"]["name"] == "terminal"
    assert messages[1]["tool_call_id"] == "call_1"
    db.close()


def test_get_messages_as_conversation(tmp_path):
    """测试获取 OpenAI 格式的对话消息"""
    db = SessionDB(tmp_path / "test.db")

    db.create_session("sess-6", "gpt-4o-mini", "You are a helper")
    db.append_message("sess-6", "user", content="列出文件")
    db.append_message(
        "sess-6",
        "assistant",
        tool_calls=[{
            "id": "call_1",
            "type": "function",
            "function": {"name": "terminal", "arguments": '{"command": "ls"}'},
        }],
    )
    db.append_message(
        "sess-6",
        "tool",
        content='{"exit_code": 0}',
        tool_call_id="call_1",
    )

    conv = db.get_messages_as_conversation("sess-6")
    assert len(conv) == 3
    assert conv[0] == {"role": "user", "content": "列出文件"}
    assert "tool_calls" in conv[1]
    assert conv[2]["role"] == "tool"
    db.close()


def test_list_sessions(tmp_path):
    """测试列出会话"""
    db = SessionDB(tmp_path / "test.db")

    for i in range(3):
        db.create_session(f"sess-{i}", "gpt-4o-mini", "test", title=f"会话{i}")

    sessions = db.list_sessions()
    assert len(sessions) == 3
    db.close()


def test_nonexistent_session(tmp_path):
    """测试查询不存在的会话"""
    db = SessionDB(tmp_path / "test.db")
    session = db.get_session("nonexistent")
    assert session is None
    db.close()

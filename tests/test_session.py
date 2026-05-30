"""会话持久化冒烟测试：验证 SQLite CRUD 操作"""

from db.session import SessionDB


def test_create_and_get_session(tmp_path):
    """测试创建和查询会话"""
    db = SessionDB(tmp_path / "test.db")

    db.create_session("sess-1", "deepseek-v4-pro", "You are a helper", title="测试会话")
    session = db.get_session("sess-1")

    assert session is not None
    assert session["id"] == "sess-1"
    assert session["model"] == "deepseek-v4-pro"
    assert session["title"] == "测试会话"
    db.close()


def test_end_session(tmp_path):
    """测试结束会话"""
    db = SessionDB(tmp_path / "test.db")

    db.create_session("sess-2", "deepseek-v4-pro", "test")
    db.end_session("sess-2")

    session = db.get_session("sess-2")
    assert session is not None
    assert session["ended_at"] is not None
    db.close()


def test_update_session_stats(tmp_path):
    """测试更新会话统计"""
    db = SessionDB(tmp_path / "test.db")

    db.create_session("sess-3", "deepseek-v4-pro", "test")
    db.update_session_stats("sess-3", message_count=3, input_tokens=100, output_tokens=50)

    session = db.get_session("sess-3")
    assert session["message_count"] == 3
    assert session["input_tokens"] == 100
    assert session["output_tokens"] == 50
    db.close()


def test_append_and_get_messages(tmp_path):
    """测试追加和查询消息"""
    db = SessionDB(tmp_path / "test.db")

    db.create_session("sess-4", "deepseek-v4-pro", "test")
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

    db.create_session("sess-5", "deepseek-v4-pro", "test")
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

    db.create_session("sess-6", "deepseek-v4-pro", "You are a helper")
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
        db.create_session(f"sess-{i}", "deepseek-v4-pro", "test", title=f"会话{i}")

    sessions = db.list_sessions()
    assert len(sessions) == 3
    db.close()


def test_nonexistent_session(tmp_path):
    """测试查询不存在的会话"""
    db = SessionDB(tmp_path / "test.db")
    session = db.get_session("nonexistent")
    assert session is None
    db.close()


def test_reasoning_content_roundtrip(tmp_path):
    """测试 reasoning_content 的存储和回传"""
    db = SessionDB(tmp_path / "test.db")
    db.create_session("sess-7", "deepseek-v4-pro", "test")

    db.append_message(
        "sess-7",
        "assistant",
        content="Hello",
        reasoning_content="Let me think about this",
        tool_calls=[{
            "id": "call_1",
            "type": "function",
            "function": {"name": "terminal", "arguments": '{"command": "ls"}'},
        }],
    )
    db.append_message(
        "sess-7",
        "user",
        content="What files?",
    )

    conv = db.get_messages_as_conversation("sess-7")
    assert len(conv) == 2
    assert conv[0].get("reasoning_content") == "Let me think about this"
    assert conv[0].get("tool_calls") is not None
    assert "reasoning_content" not in conv[1]
    db.close()


# ---- FTS5 全文搜索测试 ----


def test_fts5_search_basic(tmp_path):
    """测试 FTS5 基本搜索召回"""
    db = SessionDB(tmp_path / "test.db")

    db.create_session("sess-a", "deepseek-v4-pro", "test", title="搜索测试")
    db.append_message("sess-a", "user", content="我喜欢用 Python 写代码")
    db.append_message("sess-a", "assistant", content="Python 是一门很好的编程语言")
    db.append_message("sess-a", "user", content="今天天气不错")

    results = db.search_messages("Python")
    assert len(results) == 2
    # 相关性排序：两条 Python 相关消息应排在前面
    assert all("Python" in r["content"] for r in results)
    db.close()


def test_fts5_search_with_session_filter(tmp_path):
    """测试 FTS5 搜索时限定会话"""
    db = SessionDB(tmp_path / "test.db")

    db.create_session("sess-a", "deepseek-v4-pro", "test")
    db.append_message("sess-a", "user", content="Python 异步编程")
    db.create_session("sess-b", "deepseek-v4-pro", "test")
    db.append_message("sess-b", "user", content="Python 装饰器")

    results = db.search_messages("Python", session_id="sess-a")
    assert len(results) == 1
    assert results[0]["content"] == "Python 异步编程"
    assert results[0]["session_id"] == "sess-a"
    db.close()


def test_fts5_search_no_match(tmp_path):
    """测试 FTS5 无匹配结果"""
    db = SessionDB(tmp_path / "test.db")

    db.create_session("sess-a", "deepseek-v4-pro", "test")
    db.append_message("sess-a", "user", content="Hello world")

    results = db.search_messages("nonexistent_xyz")
    assert results == []
    db.close()


def test_fts5_search_invalid_query(tmp_path):
    """测试 FTS5 非法查询语法：返回空列表，不抛异常"""
    db = SessionDB(tmp_path / "test.db")

    db.create_session("sess-a", "deepseek-v4-pro", "test")
    db.append_message("sess-a", "user", content="test")

    # FTS5 中未配对的引号会导致语法错误
    results = db.search_messages('"unclosed quote')
    assert results == []
    db.close()


def test_fts5_migration_from_v1(tmp_path):
    """测试从 v1 数据库迁移到 v2：已有消息应被索引"""
    import sqlite3
    from db.schema import init_db, SCHEMA_VERSION

    db_path = tmp_path / "migrate.db"
    # 手动创建 v1 schema（无 FTS5）
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY)")
    conn.execute("""CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT, role TEXT, content TEXT
    )""")
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO schema_version (version) VALUES (1)")
    conn.execute("INSERT INTO sessions (id) VALUES ('sess-1')")
    conn.execute("INSERT INTO messages (session_id, role, content) VALUES ('sess-1', 'user', 'Hello from v1')")
    conn.execute("INSERT INTO messages (session_id, role, content) VALUES ('sess-1', 'assistant', 'Hi there')")
    conn.commit()
    conn.close()

    # 用 SessionDB 打开，应触发迁移
    db = SessionDB(db_path)
    results = db.search_messages("Hello")
    assert len(results) == 1
    assert results[0]["content"] == "Hello from v1"

    # 验证版本号已更新
    cur = db.conn.execute("SELECT version FROM schema_version")
    assert cur.fetchone()[0] == SCHEMA_VERSION
    db.close()


def test_end_session_with_tags(tmp_path):
    db = SessionDB(tmp_path / "test.db")
    db.create_session("sess-tags", "deepseek-v4-pro", "test", title="原始标题")
    db.end_session_with_tags("sess-tags", title="新标题", tags="python,debug")
    session = db.get_session("sess-tags")
    assert session["title"] == "新标题"
    assert session["tags"] == "python,debug"
    assert session["ended_at"] is not None
    db.close()


def test_update_compressed_tokens(tmp_path):
    db = SessionDB(tmp_path / "test.db")
    db.create_session("sess-comp", "deepseek-v4-pro", "test")
    db.update_compressed_tokens("sess-comp", 50000)
    session = db.get_session("sess-comp")
    assert session["compressed_tokens"] == 50000
    db.close()


def test_cron_schema_tables_created(tmp_path):
    from db.schema import SCHEMA_VERSION

    db = SessionDB(tmp_path / "test.db")

    cron_jobs = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='cron_jobs'"
    ).fetchone()
    cron_runs = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='cron_runs'"
    ).fetchone()
    version_row = db.conn.execute("SELECT version FROM schema_version").fetchone()

    assert cron_jobs is not None
    assert cron_runs is not None
    assert version_row is not None
    assert version_row[0] == SCHEMA_VERSION
    db.close()


def test_cron_runs_cascade_delete_with_job(tmp_path):
    db = SessionDB(tmp_path / "test.db")
    db.conn.execute(
        """INSERT INTO cron_jobs
           (id, name, prompt, schedule_expr, schedule_type, next_run_at, state, allowed_dangerous_keys, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("job-1", "测试", "hello", "10m", "once", "2026-05-30T10:00:00+08:00", "active", "[]", "2026-05-30T09:50:00+08:00", "2026-05-30T09:50:00+08:00"),
    )
    db.conn.execute(
        """INSERT INTO cron_runs
           (id, job_id, scheduled_at, status)
           VALUES (?, ?, ?, ?)""",
        ("run-1", "job-1", "2026-05-30T10:00:00+08:00", "success"),
    )
    db.conn.commit()

    db.conn.execute("DELETE FROM cron_jobs WHERE id = ?", ("job-1",))
    db.conn.commit()

    row = db.conn.execute("SELECT * FROM cron_runs WHERE id = ?", ("run-1",)).fetchone()
    assert row is None
    db.close()

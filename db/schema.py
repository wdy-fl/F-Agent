"""数据库 Schema：建表 + 迁移管理"""

import sqlite3

SCHEMA_VERSION = 2

CREATE_SESSIONS = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    model TEXT,
    system_prompt TEXT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    message_count INTEGER DEFAULT 0,
    tool_call_count INTEGER DEFAULT 0,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    title TEXT
);
"""

CREATE_MESSAGES = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    role TEXT NOT NULL,
    content TEXT,
    reasoning_content TEXT,
    tool_call_id TEXT,
    tool_calls TEXT,
    tool_name TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    token_count INTEGER DEFAULT 0,
    finish_reason TEXT
);
"""

CREATE_MESSAGES_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content,
    content='messages',
    content_rowid='id'
);
"""

CREATE_TRIGGER_AI = """
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, COALESCE(new.content, ''));
END;
"""

CREATE_TRIGGER_AD = """
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.id, COALESCE(old.content, ''));
END;
"""

CREATE_TRIGGER_AU = """
CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.id, COALESCE(old.content, ''));
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, COALESCE(new.content, ''));
END;
"""

CREATE_SCHEMA_VERSION = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
"""


def init_db(conn: sqlite3.Connection) -> None:
    """初始化数据库，创建所有表

    Args:
        conn: SQLite 连接
    """
    # 启用 WAL 模式
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    conn.executescript(CREATE_SESSIONS)
    conn.executescript(CREATE_MESSAGES)
    conn.executescript(CREATE_SCHEMA_VERSION)

    # 兼容旧表：如果 messages 表缺少 reasoning_content 列则添加
    cur = conn.execute("PRAGMA table_info(messages)")
    columns = {row[1] for row in cur.fetchall()}
    if "reasoning_content" not in columns:
        conn.execute("ALTER TABLE messages ADD COLUMN reasoning_content TEXT")

    # 读取当前 schema 版本
    cur = conn.execute("SELECT version FROM schema_version")
    row = cur.fetchone()
    current_version = row[0] if row else 0

    # 迁移：v1 → v2，添加 FTS5 全文索引
    if current_version < 2:
        _migrate_v1_to_v2(conn)

    # 更新 schema 版本
    if current_version < SCHEMA_VERSION:
        conn.execute("DELETE FROM schema_version")
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))

    conn.commit()


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """v1 → v2 迁移：创建 FTS5 全文索引和自动同步触发器"""
    conn.execute(CREATE_MESSAGES_FTS)
    conn.execute(CREATE_TRIGGER_AI)
    conn.execute(CREATE_TRIGGER_AD)
    conn.execute(CREATE_TRIGGER_AU)

    # 将现有消息内容同步到 FTS5 索引
    cur = conn.execute("SELECT id, content FROM messages WHERE content IS NOT NULL AND content != ''")
    rows = cur.fetchall()
    for msg_id, content in rows:
        conn.execute(
            "INSERT INTO messages_fts(rowid, content) VALUES (?, ?)",
            (msg_id, content),
        )

"""数据库 Schema：建表 + 迁移管理"""

import sqlite3

SCHEMA_VERSION = 1

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

    # 记录 schema 版本
    cur = conn.execute("SELECT version FROM schema_version")
    row = cur.fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))

    conn.commit()

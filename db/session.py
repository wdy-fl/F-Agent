"""会话持久化：会话 CRUD + 消息 INSERT/SELECT"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from db.schema import init_db

logger = logging.getLogger(__name__)


class SessionDB:
    """SQLite 会话存储，支持会话和消息的 CRUD 操作"""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)

    def close(self) -> None:
        """关闭数据库连接"""
        self.conn.close()

    # ---- 会话操作 ----

    def create_session(
        self,
        session_id: str,
        model: str,
        system_prompt: str,
        title: str | None = None,
    ) -> None:
        """创建新会话

        Args:
            session_id: 会话唯一标识
            model: 使用的模型名称
            system_prompt: 系统提示词
            title: 会话标题（可选）
        """
        self.conn.execute(
            "INSERT INTO sessions (id, model, system_prompt, title) VALUES (?, ?, ?, ?)",
            (session_id, model, system_prompt, title),
        )
        self.conn.commit()

    def end_session(self, session_id: str) -> None:
        """结束会话，记录结束时间"""
        self.conn.execute(
            "UPDATE sessions SET ended_at = CURRENT_TIMESTAMP WHERE id = ?",
            (session_id,),
        )
        self.conn.commit()

    def update_session_stats(
        self,
        session_id: str,
        message_count: int | None = None,
        tool_call_count: int | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        """更新会话统计信息"""
        updates = []
        values: list[Any] = []
        if message_count is not None:
            updates.append("message_count = message_count + ?")
            values.append(message_count)
        if tool_call_count is not None:
            updates.append("tool_call_count = tool_call_count + ?")
            values.append(tool_call_count)
        if input_tokens is not None:
            updates.append("input_tokens = input_tokens + ?")
            values.append(input_tokens)
        if output_tokens is not None:
            updates.append("output_tokens = output_tokens + ?")
            values.append(output_tokens)

        if not updates:
            return

        values.append(session_id)
        self.conn.execute(
            f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?",
            values,
        )
        self.conn.commit()

    def get_session(self, session_id: str) -> dict | None:
        """获取会话信息"""
        cur = self.conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def list_sessions(self, limit: int = 20) -> list[dict]:
        """列出最近的会话"""
        cur = self.conn.execute(
            "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]

    # ---- 消息操作 ----

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str | None = None,
        tool_call_id: str | None = None,
        tool_calls: list[dict] | None = None,
        tool_name: str | None = None,
        token_count: int = 0,
        finish_reason: str | None = None,
    ) -> int:
        """追加消息到会话

        Args:
            session_id: 会话 ID
            role: 消息角色（system/user/assistant/tool）
            content: 消息文本内容
            tool_call_id: 工具调用 ID（role=tool 时）
            tool_calls: 工具调用列表（assistant 消息）
            tool_name: 工具名称
            token_count: Token 数量
            finish_reason: 结束原因

        Returns:
            插入的消息 ID
        """
        tool_calls_str = json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None
        cur = self.conn.execute(
            """INSERT INTO messages
               (session_id, role, content, tool_call_id, tool_calls, tool_name, token_count, finish_reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, role, content, tool_call_id, tool_calls_str, tool_name, token_count, finish_reason),
        )
        self.conn.commit()
        return cur.lastrowid or 0

    def get_messages(
        self,
        session_id: str,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]:
        """获取会话的消息列表

        Args:
            session_id: 会话 ID
            limit: 最大返回条数
            offset: 偏移量

        Returns:
            消息列表，每条包含 role、content 等字段
        """
        query = "SELECT * FROM messages WHERE session_id = ? ORDER BY id ASC"
        params: list[Any] = [session_id]

        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])

        cur = self.conn.execute(query, params)
        messages = []
        for row in cur.fetchall():
            msg = dict(row)
            # 解析 tool_calls JSON
            if msg.get("tool_calls"):
                msg["tool_calls"] = json.loads(msg["tool_calls"])
            messages.append(msg)
        return messages

    def get_messages_as_conversation(self, session_id: str) -> list[dict[str, Any]]:
        """获取会话消息，转换为 OpenAI API 格式

        Returns:
            OpenAI 消息格式的列表
        """
        raw_messages = self.get_messages(session_id)
        result = []
        for msg in raw_messages:
            api_msg: dict[str, Any] = {"role": msg["role"]}
            if msg.get("content"):
                api_msg["content"] = msg["content"]
            if msg.get("tool_calls"):
                api_msg["tool_calls"] = msg["tool_calls"]
            if msg.get("tool_call_id"):
                api_msg["tool_call_id"] = msg["tool_call_id"]
            result.append(api_msg)
        return result

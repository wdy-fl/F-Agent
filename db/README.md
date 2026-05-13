# db/ — 会话持久化

SQLite + FTS5 全文搜索。

| 模块 | 职责 |
|------|------|
| schema.py | 建表 + 迁移 + FTS5 索引 |
| session.py | 会话 CRUD + 消息存储 + FTS5 搜索 |

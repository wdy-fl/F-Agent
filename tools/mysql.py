"""MySQL 只读查询工具"""

import json
import logging
import os
import re

import pymysql

from config.settings import get_config
from tools.registry import registry

logger = logging.getLogger(__name__)

_READ_ONLY_PATTERNS = [
    r"^\s*SELECT\b",
    r"^\s*SHOW\b",
    r"^\s*DESCRIBE\b",
    r"^\s*DESC\b",
    r"^\s*EXPLAIN\b",
]


def _is_read_only(sql: str) -> bool:
    """检查 SQL 是否为只读语句"""
    # 去除注释和多余空白后进行匹配
    cleaned = re.sub(r"--.*$|/\*.*?\*/", "", sql, flags=re.DOTALL | re.MULTILINE).strip()
    for pattern in _READ_ONLY_PATTERNS:
        if re.match(pattern, cleaned, re.IGNORECASE):
            return True
    return False


def mysql_query(args: dict) -> str:
    """执行 MySQL 只读查询

    Args:
        args: {"query": str, "database": str (可选)}

    Returns:
        查询结果 JSON
    """
    query = args.get("query", "")
    database = args.get("database", "")

    if not query:
        return json.dumps({"error": "No query provided"}, ensure_ascii=False)

    if not _is_read_only(query):
        return json.dumps({
            "error": "Only read-only queries are allowed (SELECT/SHOW/DESCRIBE/EXPLAIN)",
            "query": query[:200],
        }, ensure_ascii=False)

    config = _get_config()
    if config is None:
        return json.dumps({
            "error": "MySQL not configured. Add 'mysql' section to config.yaml.",
        }, ensure_ascii=False)

    password = os.environ.get(config["password_env"], "")

    target_db = database or config["database"]

    try:
        conn = pymysql.connect(
            host=config["host"],
            port=config["port"],
            user=config["user"],
            password=password,
            database=target_db,
            charset="utf8mb4",
            connect_timeout=10,
            read_timeout=30,
        )
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                row_count = len(rows)

                # 截断过大结果
                max_rows = 200
                if row_count > max_rows:
                    rows = rows[:max_rows]

                return json.dumps({
                    "columns": columns,
                    "rows": rows,
                    "row_count": row_count,
                    "truncated": row_count > max_rows,
                }, ensure_ascii=False, default=str)
        finally:
            conn.close()
    except pymysql.err.OperationalError as e:
        return json.dumps({"error": f"MySQL connection failed: {e}"}, ensure_ascii=False)
    except pymysql.err.ProgrammingError as e:
        return json.dumps({"error": f"SQL error: {e}"}, ensure_ascii=False)
    except Exception as e:
        logger.exception("mysql_query failed")
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _get_config() -> dict | None:
    """从全局配置获取 MySQL 连接参数"""
    # 通过 registry 的 _app_config 钩子获取配置
    # 在 CLI 初始化时由 interface.py 注入
    app_config = get_config()
    if app_config.mysql is None:
        return None

    mysql_cfg = app_config.mysql
    return {
        "host": mysql_cfg.host,
        "port": mysql_cfg.port,
        "user": mysql_cfg.user,
        "database": mysql_cfg.database,
        "password_env": mysql_cfg.password_env,
    }


registry.register(
    name="mysql_query",
    schema={
        "type": "function",
        "function": {
            "name": "mysql_query",
            "description": (
                "查询本地 MySQL 数据库，仅支持只读操作（SELECT/SHOW/DESCRIBE/EXPLAIN），最多返回 20 行。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "SQL 查询语句（仅允许 SELECT/SHOW/DESCRIBE/EXPLAIN）",
                    },
                    "database": {
                        "type": "string",
                        "description": "目标数据库名，不指定则使用配置中的默认数据库",
                    },
                },
                "required": ["query"],
            },
        },
    },
    handler=mysql_query,
)
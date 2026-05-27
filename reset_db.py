#!/usr/bin/env python3
"""重置 F-Agent 的 SQLite 数据库。

用法:
    python3 reset_db.py              # 使用默认路径 workspace/state.db
    python3 reset_db.py --force      # 跳过确认提示
    python3 reset_db.py --db-path /custom/path/state.db
"""

import argparse
import sqlite3
import sys
from pathlib import Path

# 将项目根目录加入 sys.path，确保能导入 db.schema
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.schema import init_db

DEFAULT_DB_PATH = PROJECT_ROOT / "workspace" / "state.db"


def reset_database(db_path: Path, force: bool = False) -> None:
    """删除旧数据库文件并重建空库。"""
    if not force:
        response = input(f"即将删除数据库 {db_path} 及其 WAL/SHM 文件，不可恢复。确认？[y/N] ")
        if response.strip().lower() not in ("y", "yes"):
            print("已取消。")
            return

    # 删除主数据库文件和 WAL/SHM 附属文件
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(db_path) + suffix)
        if p.exists():
            p.unlink()
            print(f"已删除: {p}")

    # 确保父目录存在
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # 重建数据库
    conn = sqlite3.connect(str(db_path))
    try:
        init_db(conn)
        print(f"数据库已重建: {db_path} (schema version 2)")
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="重置 F-Agent SQLite 数据库")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"数据库文件路径 (默认: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="跳过确认提示，直接重置",
    )
    args = parser.parse_args()

    reset_database(args.db_path, force=args.force)


if __name__ == "__main__":
    main()
"""F-Agent 入口：解析配置 → 启动 CLI"""

import logging
import sys
from pathlib import Path

from cli.interface import CLIInterface
from config.settings import get_config, ensure_config_dir
import tools  # noqa: F401 — 触发工具自注册


FIRST_PARTY_LOGGER_NAMES = (
    "main",
    "agent",
    "cli",
    "config",
    "context",
    "db",
    "llm",
    "memory",
    "tools",
)


def configure_logging(log_dir):
    if not log_dir:
        return

    log_path = Path(log_dir) / "agent.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        filename=str(log_path),
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )

    for logger_name in FIRST_PARTY_LOGGER_NAMES:
        logging.getLogger(logger_name).setLevel(logging.DEBUG)


def main():
    """启动 F-Agent"""
    # 加载配置
    config = get_config()

    # 验证 API Key
    if not config.llm.api_key:
        print("错误：未配置 API Key。请在 workspace/config.yaml 中设置 llm.api_key")
        sys.exit(1)

    # 确保配置目录
    ensure_config_dir()

    # 配置日志
    log_dir = getattr(config, "log_dir", None)
    configure_logging(log_dir)

    # 启动 CLI
    cli = CLIInterface()
    cli.run()


if __name__ == "__main__":
    main()

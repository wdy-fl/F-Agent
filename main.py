"""F-Agent 入口：解析配置 → 启动 CLI"""

import logging
import sys
from pathlib import Path

from cli.interface import CLIInterface
from config.settings import load_config, ensure_config_dir
import tools  # noqa: F401 — 触发工具自注册


def main():
    """启动 F-Agent"""
    # 加载配置
    config = load_config()

    # 验证 API Key
    if not config.llm.api_key:
        print("错误：未配置 API Key。请在 workspace/config.yaml 中设置 llm.api_key")
        sys.exit(1)

    # 确保配置目录
    ensure_config_dir()

    # 配置日志
    log_dir = getattr(config, "log_dir", None)
    if log_dir:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=f"{log_dir}/agent.log",
            level=logging.DEBUG,
            format="%(asctime)s %(name)s %(levelname)s %(message)s",
        )

    # 启动 CLI
    cli = CLIInterface(config)
    cli.run()


if __name__ == "__main__":
    main()

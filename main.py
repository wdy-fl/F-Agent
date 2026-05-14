"""F-Agent 入口：解析配置 → 启动 Agent"""

import logging
import sys
from pathlib import Path

from agent.loop import AgentLoop
from agent.prompt import build_system_prompt
from config.settings import load_config, ensure_config_dir
from db.session import SessionDB
from llm.client import LLMClient
import tools  # noqa: F401 — 触发工具自注册


def main():
    """启动 F-Agent"""
    # 加载配置
    config = load_config()

    # 验证 API Key
    if not config.llm.api_key:
        print("错误：未配置 API Key。请通过以下方式之一设置：")
        print("  1. 环境变量：export FAGENT_API_KEY=your-key")
        print("  2. 配置文件：~/.fagent/config.yaml 中设置 llm.api_key")
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

    # 创建 LLM 客户端
    llm = LLMClient(config.llm)

    # 创建会话数据库
    session_db = SessionDB(config.db_path)

    # 创建 Agent 循环
    agent = AgentLoop(
        llm,
        max_iterations=config.llm.max_iterations,
        session_db=session_db,
    )

    # 构建系统提示词（含工具指引）
    system_prompt = build_system_prompt(include_tools=True)

    # 简单的 REPL
    print("阿福（F-Agent）已启动，输入消息开始对话，输入 /quit 退出\n")
    while True:
        try:
            user_input = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue
        if user_input == "/quit":
            print("再见！")
            break

        # 运行 Agent
        print("阿福: ", end="")
        agent.run(user_input, system_prompt)
        print()

    # 关闭数据库
    session_db.close()


if __name__ == "__main__":
    main()

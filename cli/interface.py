"""CLI 交互：prompt_toolkit 输入 + rich 输出"""

import logging

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.text import Text

from agent.loop import AgentLoop
from agent.prompt import build_system_prompt
from config.settings import AppConfig, ensure_config_dir
from db.session import SessionDB
from llm.client import LLMClient

logger = logging.getLogger(__name__)


class CLIInterface:
    """F-Agent CLI 界面，使用 prompt_toolkit + rich"""

    def __init__(self, config: AppConfig):
        self.config = config
        self.console = Console()

        # 创建 LLM 客户端
        self.llm = LLMClient(config.llm)

        # 创建会话数据库
        self.session_db = SessionDB(config.db_path)

        # 创建 Agent 循环
        self.agent = AgentLoop(
            self.llm,
            max_iterations=config.llm.max_iterations,
            session_db=self.session_db,
            output_callback=self._on_stream_delta,
        )

        # 构建系统提示词
        self.system_prompt = build_system_prompt(include_tools=True)

        # prompt_toolkit 会话
        history_path = ensure_config_dir() / "history"
        self.prompt_session = PromptSession(history=FileHistory(str(history_path)))

        # 流式输出状态
        self._stream_buffer = ""
        self._live: Live | None = None

        # 中断标志
        self._interrupted = False

    def run(self) -> None:
        """启动 CLI 交互循环"""
        self._print_banner()

        while True:
            try:
                user_input = self.prompt_session.prompt("你: ").strip()
            except (EOFError, KeyboardInterrupt):
                self._print_goodbye()
                break

            if not user_input:
                continue

            # 命令处理
            if user_input.startswith("/"):
                if self._handle_command(user_input):
                    break
                continue

            # 运行 Agent
            self._interrupted = False
            self.console.print("阿福: ", style="bold green")
            self._stream_buffer = ""

            try:
                with Live(Text(""), console=self.console, transient=False, refresh_per_second=15) as live:
                    self._live = live
                    try:
                        result = self.agent.run(user_input, self.system_prompt)
                    except KeyboardInterrupt:
                        self.agent.budget.interrupt()
                        live.stop()
                        self.console.print("[已中断]", style="yellow")
                        self._live = None
                        continue

                    if result:
                        live.update(Markdown(result))
            except Exception:
                self._live = None
                raise
            finally:
                self._live = None

        self.session_db.close()

    def _on_stream_delta(self, text: str) -> None:
        """流式输出回调：将文本增量刷新到 Live 区域"""
        if text == "\n":
            return
        self._stream_buffer += text
        if self._live:
            self._live.update(Text(self._stream_buffer))

    def _handle_command(self, command: str) -> bool:
        """处理斜杠命令

        Returns:
            True 表示应退出循环
        """
        cmd = command.strip().lower()

        if cmd in ("/quit", "/exit", "/q"):
            self._print_goodbye()
            return True
        elif cmd == "/help":
            self._print_help()
        elif cmd == "/clear":
            self.console.clear()
            self._print_banner()
        elif cmd == "/sessions":
            self._list_sessions()
        elif cmd == "/stats":
            self._show_stats()
        else:
            self.console.print(f"未知命令: {command}，输入 /help 查看帮助", style="yellow")

        return False

    def _print_banner(self) -> None:
        """打印启动横幅"""
        self.console.print("\n[bold cyan]阿福（F-Agent）[/bold cyan] 已启动", style="bold")
        self.console.print("输入消息开始对话，输入 [bold]/help[/bold] 查看命令，[bold]/quit[/bold] 退出\n")

    def _print_goodbye(self) -> None:
        """打印退出信息"""
        self.console.print("\n再见！", style="bold cyan")

    def _print_help(self) -> None:
        """打印帮助信息"""
        self.console.print("\n[bold]可用命令[/bold]")
        self.console.print("  /help     - 显示帮助信息")
        self.console.print("  /quit     - 退出程序")
        self.console.print("  /clear    - 清屏")
        self.console.print("  /sessions - 列出历史会话")
        self.console.print("  /stats    - 显示当前会话统计")
        self.console.print()

    def _list_sessions(self) -> None:
        """列出历史会话"""
        sessions = self.session_db.list_sessions(limit=10)
        if not sessions:
            self.console.print("暂无历史会话", style="dim")
            return

        self.console.print("\n[bold]最近会话[/bold]")
        for s in sessions:
            title = s.get("title") or s["id"][:8]
            msg_count = s.get("message_count", 0)
            self.console.print(f"  {title} ({msg_count} 条消息)")
        self.console.print()

    def _show_stats(self) -> None:
        """显示当前会话统计"""
        if not self.agent.session_id:
            self.console.print("当前无活跃会话", style="dim")
            return

        session = self.session_db.get_session(self.agent.session_id)
        if session:
            self.console.print(f"\n[bold]会话统计[/bold]")
            self.console.print(f"  消息数: {session.get('message_count', 0)}")
            self.console.print(f"  工具调用: {session.get('tool_call_count', 0)}")
            self.console.print(f"  输入 Token: {session.get('input_tokens', 0)}")
            self.console.print(f"  输出 Token: {session.get('output_tokens', 0)}")
            self.console.print()

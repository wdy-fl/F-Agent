"""CLI 交互：prompt_toolkit 输入 + rich 输出"""

import logging

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.text import Text

from agent.loop import AgentLoop
from config.settings import ensure_config_dir, get_config
from cron.models import RUN_SUCCESS, CronJob, CronRun
from cron.runner import CronRunner
from cron.scheduler import CronScheduler
from cron.store import CronStore
from tools.approval import set_approval_callback, set_approval_context
from tools.cron import set_cron_confirm_callback, set_cron_store
from db.session import SessionDB

logger = logging.getLogger(__name__)


class CLIInterface:
    """F-Agent CLI 界面，使用 prompt_toolkit + rich"""

    def __init__(self):
        config = get_config()
        self.config = config
        self.console = Console()

        # 创建会话数据库（CLIInterface 和 AgentLoop 共享）
        self.session_db = SessionDB(config.db_path)

        self.cron_store = CronStore(self.session_db.conn)
        self.cron_session_db = SessionDB(config.db_path)
        self.cron_scheduler_store = CronStore(self.cron_session_db.conn)
        self.cron_runner = CronRunner(self.cron_scheduler_store, self.cron_session_db)
        self.cron_scheduler = CronScheduler(
            self.cron_scheduler_store,
            self.cron_runner,
            config.cron,
            completion_callback=self._on_cron_completed,
        )

        # 创建 Agent 循环（AgentLoop 内部自行创建 llm/memory/compressor 等依赖）
        self.agent = AgentLoop(
            session_db=self.session_db,
            output_callback=self._on_stream_delta,
        )

        # prompt_toolkit 会话
        history_path = ensure_config_dir() / "history"
        self.prompt_session = PromptSession(history=FileHistory(str(history_path)))

        # 流式输出状态
        self._stream_buffer = ""
        self._live: Live | None = None

        # 中断标志
        self._interrupted = False

        # 关闭状态
        self._closed = False

        set_approval_callback(self._approval_callback)
        set_approval_context(mode=self.config.approval.mode)
        set_cron_store(self.cron_store)
        set_cron_confirm_callback(self._cron_confirm_callback)
        self.cron_scheduler.start()

    def run(self) -> None:
        """启动 CLI 交互循环"""
        self._print_banner()

        try:
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
                            set_approval_context(session_id=self.agent.session_id)
                            result = self.agent.run(user_input)
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
        finally:
            self.close()

    def close(self) -> None:
        """清理各组件资源"""
        if self._closed:
            return
        self._closed = True

        session_id = self.agent.session_id
        if session_id:
            try:
                self.session_db.end_session(session_id)
            except Exception:
                logger.exception("结束会话失败: session_id=%s", session_id)

        try:
            self.cron_scheduler.stop()
        except Exception:
            logger.exception("停止定时任务调度器失败")

        set_cron_confirm_callback(None)
        set_cron_store(None)

        try:
            self.cron_session_db.close()
        except Exception:
            logger.exception("关闭定时任务数据库失败")

        try:
            self.session_db.close()
        except Exception:
            logger.exception("关闭会话数据库失败")

    def _on_stream_delta(self, text: str) -> None:
        """流式输出回调：将文本增量刷新到 Live 区域"""
        if text == "\n":
            return
        self._stream_buffer += text
        if self._live:
            self._live.update(Text(self._stream_buffer))

    def _cron_confirm_callback(self, payload: dict) -> bool:
        from rich.panel import Panel
        from rich.text import Text

        text = Text()
        text.append("创建定时任务\n\n", style="bold cyan")
        text.append("名称: ", style="dim")
        text.append(f"{payload.get('name', '')}\n", style="white")
        text.append("调度: ", style="dim")
        text.append(f"{payload.get('schedule', '')}\n", style="white")
        text.append("类型: ", style="dim")
        text.append(f"{payload.get('schedule_type', '')}\n", style="white")
        text.append("下次运行: ", style="dim")
        text.append(f"{payload.get('next_run_at', '')}\n", style="white")
        allowed_keys = payload.get("allowed_dangerous_keys") or []
        if allowed_keys:
            text.append("危险命令授权: ", style="dim")
            text.append(f"{', '.join(allowed_keys)}\n", style="yellow")
        text.append("\nPrompt:\n", style="dim")
        text.append(f"{payload.get('prompt', '')}\n\n", style="white")
        text.append("[y] 确认创建\n", style="green")
        text.append("[n] 取消\n", style="red")

        panel = Panel(text, title="定时任务确认", border_style="cyan")
        self.console.print(panel)

        while True:
            try:
                choice = self.prompt_session.prompt("确认创建定时任务? (y/n): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return False

            if choice in ("y", "yes"):
                return True
            if choice in ("n", "no"):
                return False
            self.console.print("无效选择，请输入 y/n", style="red")

    def _on_cron_completed(self, job: CronJob, run: CronRun) -> None:
        is_success = run.status == RUN_SUCCESS
        status_style = "green" if is_success else "red"
        status = "完成" if is_success else "失败"
        self.console.print(
            f"\n[bold cyan]定时任务[/bold cyan] {job.name} {status}: {run.summary or run.error or ''}",
            style=status_style,
        )

    def _approval_callback(self, command: str, description: str, pattern_key: str) -> str:
        """审批回调：展示危险命令面板，获取用户选择。

        Returns:
            "once" | "session" | "deny"
        """
        from rich.panel import Panel
        from rich.text import Text

        text = Text()
        text.append("危险命令\n\n", style="bold yellow")
        text.append(f"命令: ", style="dim")
        text.append(f"{command}\n", style="white")
        text.append(f"原因: ", style="dim")
        text.append(f"{description}\n", style="white")
        text.append(f"授权键: ", style="dim")
        text.append(f"{pattern_key}\n\n", style="white")
        text.append("[o] 本次允许  (once)\n", style="green")
        text.append("[s] 会话记住  (session)\n", style="cyan")
        text.append("[d] 拒绝      (deny)\n", style="red")

        panel = Panel(text, title="命令审批", border_style="yellow")
        self.console.print(panel)

        while True:
            try:
                choice = self.prompt_session.prompt("请选择 (o/s/d): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return "deny"

            if choice in ("o", "once"):
                return "once"
            if choice in ("s", "session"):
                return "session"
            if choice in ("d", "deny"):
                return "deny"
            self.console.print("无效选择，请输入 o/s/d", style="red")

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
        elif cmd == "/resume":
            self._resume_interactive()
        elif cmd.startswith("/resume "):
            session_id = command.strip().split(maxsplit=1)[1]
            self._resume_session(session_id)
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
        self.console.print("  /resume [id] - 恢复历史会话（无参数时交互选择）")
        self.console.print("  /stats    - 显示当前会话统计")
        self.console.print()

    def _resume_session(self, session_id: str) -> None:
        """恢复历史会话。"""
        try:
            restored_count = self.agent.restore_session(session_id)
        except ValueError as e:
            self.console.print(str(e), style="red")
            return
        self.console.print(
            f"已恢复会话 {session_id}（{restored_count} 条历史消息）",
            style="green",
        )
        non_system = [m for m in self.agent.message_list if m.get("role") != "system"]
        self._print_conversation(non_system)

    def _print_conversation(self, messages: list[dict]) -> None:
        """打印对话历史到终端。"""
        self.console.print("\n[bold]--- 历史对话 ---[/bold]")
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "") or ""
            if role == "user":
                self.console.print(f"\n[bold cyan]你:[/bold cyan] {content}")
            elif role == "assistant":
                reasoning = msg.get("reasoning_content", "")
                if reasoning:
                    self.console.print(f"[dim]  (思考: {reasoning})[/dim]")
                self.console.print("[bold green]阿福:[/bold green]")
                self.console.print(Markdown(content))
            elif role == "tool":
                tool_name = msg.get("tool_call_id", "") or "tool"
                preview = content[:200] + "..." if len(content) > 200 else content
                self.console.print(f"[dim]  [工具: {tool_name}] {preview}[/dim]")
        self.console.print("\n[bold]--- 以上为历史对话 ---[/bold]\n")

    def _list_sessions(self) -> None:
        """列出历史会话"""
        sessions = self.session_db.list_sessions(limit=10)
        if not sessions:
            self.console.print("暂无历史会话", style="dim")
            return

        self.console.print("\n[bold]最近会话[/bold]")
        for i, s in enumerate(sessions, 1):
            title = s.get("title") or s["id"][:8]
            msg_count = s.get("message_count", 0)
            self.console.print(f"  [bold cyan]{i}[/bold cyan]. {s['id']}  {title} ({msg_count} 条消息)")
        self.console.print()

    def _resume_interactive(self) -> None:
        """无参数 /resume：展示会话列表并交互式选择恢复。"""
        sessions = self.session_db.list_sessions(limit=10)
        if not sessions:
            self.console.print("暂无历史会话", style="dim")
            return

        self.console.print("\n[bold]选择要恢复的会话（输入序号）[/bold]")
        for i, s in enumerate(sessions, 1):
            title = s.get("title") or s["id"][:8]
            msg_count = s.get("message_count", 0)
            self.console.print(f"  [bold cyan]{i}[/bold cyan]. {title} ({msg_count} 条消息)")

        try:
            choice = self.prompt_session.prompt("\n序号: ").strip()
            idx = int(choice) - 1
            if idx < 0 or idx >= len(sessions):
                self.console.print("无效的序号", style="red")
                return
        except (ValueError, EOFError, KeyboardInterrupt):
            self.console.print("已取消", style="yellow")
            return

        session_id = sessions[idx]["id"]
        self._resume_session(session_id)

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

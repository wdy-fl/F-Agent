"""Agent 主循环：迭代 LLM 调用 + 工具执行 + 会话持久化"""

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Callable

from agent.budget import IterationBudget
from agent.prompt import build_system_prompt
from config.settings import get_config
from context.compressor import ContextCompressor
from db.session import SessionDB
from llm.client import LLMClient
from memory.context_fence import inject_context
from memory.manager import MemoryManager
from tools.memory import set_managers
from tools.registry import registry
from tools.skill import set_skills_dir
from tools.skill_hub import set_skills_dir as set_skill_hub_dir, set_github_token

logger = logging.getLogger(__name__)


class AgentLoop:
    """Agent 主循环，驱动 LLM 与工具的交互"""

    def __init__(
        self,
        session_db: SessionDB | None = None,
        output_callback: Callable[[str], None] | None = None,
    ):
        config = get_config()
        self.llm = LLMClient(config.llm)
        self.config = config
        self.max_iterations = config.llm.max_iterations
        self.session_db = session_db
        self.memory_manager = (
            MemoryManager(
                session_db,
                config.user_profile_path,
                memory_path=config.memory_path,
                soul_path=config.soul_path,
                agent_path=config.agent_guidance_path,
                llm=self.llm,
            )
            if session_db
            else None
        )
        self.compressor = ContextCompressor(
            self.llm,
            context_window=config.llm.context_window,
            threshold=config.compressor.threshold,
            min_saving=config.compressor.min_saving,
            protected_head=config.compressor.protected_head,
            protected_tail_tokens=config.compressor.protected_tail_tokens,
        )

        set_managers(memory_manager=self.memory_manager)

        set_skills_dir(Path(config.skills_dir))
        set_skill_hub_dir(Path(config.skills_dir))
        set_github_token(config.skills_hub.github_token)

        self.output_callback = output_callback or (lambda t: print(t, end="", flush=True))
        self.system_prompt = build_system_prompt(
            include_tools=True,
            include_skills=True,
            skills_dir=config.skills_dir,
            user_profile_path=config.user_profile_path,
            memory_path=config.memory_path,
            soul_path=config.soul_path,
            agent_guidance_path=config.agent_guidance_path,
        )
        self._tools_definitions = registry.get_definitions()
        self.messages: list[dict[str, Any]] = []
        self.session_id: str | None = None
        self.budget = IterationBudget(self.max_iterations)
        self.turn_count = 0
        self._turns_since_sync = 0

    def run(self, user_message: str) -> str:
        """运行一轮对话，返回最终回复文本

        Args:
            user_message: 用户原始输入

        Returns:
            Agent 的最终文本回复
        """
        logger.info("=== run 开始, user_message=%r", user_message[:80])

        self.turn_count += 1
        if self.session_db and self.session_id:
            self.session_db.update_turn_count(self.session_id, self.turn_count)

        original_message = user_message

        self._ensure_conversation_started(user_message)
        logger.debug("会话已初始化, session_id=%s", self.session_id)

        # 预取记忆并注入到用户消息
        enhanced_message = user_message
        if self.memory_manager:
            logger.debug("正在预取记忆上下文")
            memory_context = self.memory_manager.prefetch(user_message, limit=self.config.memory.prefetch_limit)
            if memory_context:
                logger.debug("记忆上下文内容: %s", memory_context)
                enhanced_message = inject_context(user_message, memory_context)
                logger.debug("注入后完整消息: %s", enhanced_message)

        user_msg = {"role": "user", "content": enhanced_message}
        self.messages.append(user_msg)
        logger.debug("用户消息已追加: %s", user_msg)

        if self.session_db and self.session_id:
            # DB 存储原始用户消息，不含 nudge 和记忆上下文，保证搜索干净
            self.session_db.append_message(self.session_id, "user", content=original_message)
            self.session_db.update_session_stats(self.session_id, message_count=1)
            logger.debug("用户消息已持久化到 DB")

        tools = self._tools_definitions

        # 初始化预算，进入主循环
        self.budget.reset()
        logger.debug("ReAct循环轮数已重置, 轮数限制=%d轮", self.max_iterations)

        # 主循环
        while self.budget.can_continue():
            self.budget.consume()
            logger.info("本次ReAct循环剩余轮数 %d/%d, 消息列表长度=%d",
                        self.budget.remaining, self.max_iterations, len(self.messages))

            # 调用 LLM（流式）
            logger.debug("正在调用 LLM 流式接口")
            try:
                response = self._call_llm_stream(tools=tools if tools else None)
            except Exception as e:
                logger.error("LLM 调用未预期异常: %s", e, exc_info=True)
                self.output_callback(f"\n[错误] LLM 调用失败：{e}\n")
                return f"抱歉，调用模型时遇到错误：{e}"
            logger.debug("LLM 响应已收到, content=%s, has_tool_calls=%s, finish_reason=%s",
                         response.get("content", ""),
                         bool(response.get("tool_calls")),
                         response.get("finish_reason"))

            # 更新 token 统计
            if self.session_db and self.session_id:
                usage = response.get("usage")
                if usage:
                    self.session_db.update_session_stats(
                        self.session_id,
                        input_tokens=usage.get("prompt_tokens", 0),
                        output_tokens=usage.get("completion_tokens", 0),
                    )
                    logger.debug("token 统计已更新, input=%d, output=%d",
                                usage.get("prompt_tokens", 0),
                                usage.get("completion_tokens", 0))

            # 无工具调用 → 返回最终回复
            if not response.get("tool_calls"):
                self._persist_assistant_message(response)
                result = response.get("content", "")
                self._sync_memory()
                logger.info("=== run 结束, 无工具调用, result=%s", result)
                return result

            # 有工具调用 → 执行工具
            logger.info("正在执行工具调用: %s", response["tool_calls"])
            self._persist_assistant_message(response)
            tool_results = self._execute_tool_calls(response["tool_calls"])
            self.messages.extend(tool_results)

            # 持久化工具结果
            if self.session_db and self.session_id:
                for tr in tool_results:
                    self.session_db.append_message(
                        self.session_id,
                        "tool",
                        content=tr.get("content", ""),
                        tool_call_id=tr.get("tool_call_id"),
                    )
                    self.session_db.update_session_stats(self.session_id, message_count=1)
                self.session_db.update_session_stats(
                    self.session_id,
                    tool_call_count=len(response["tool_calls"]),
                )
                logger.debug("工具结果已持久化: %s", tool_results)

            # 检查是否需要上下文压缩
            if self.compressor:
                self._check_compression()

        # 预算耗尽
        logger.warning("预算已耗尽, max_iterations=%d, 进入兜底调用", self.max_iterations)
        result = self._grace_call()
        self._sync_memory()
        logger.info("=== run 结束, 兜底调用完成, result=%s", result)
        return result

    def restore_session(self, session_id: str) -> int:
        """恢复历史会话到当前 AgentLoop。"""
        if not self.session_db:
            raise ValueError("Session DB not configured")

        session = self.session_db.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        restored = self.session_db.get_messages_as_conversation(session_id)
        self.session_id = session_id
        self.messages = [{"role": "system", "content": self.system_prompt}]
        self.messages.extend(restored)

        # 恢复压缩状态
        compressed = session.get("compressed_tokens")
        if compressed:
            self.compressor.set_last_compressed_tokens(compressed)

        # 恢复对话轮数
        self.turn_count = session.get("turn_count", 0)

        return len(restored)

    def _ensure_conversation_started(self, first_user_message: str) -> None:
        """初始化当前 AgentLoop 生命周期内的连续对话"""
        if not self.messages:
            self.messages.append({"role": "system", "content": self.system_prompt})

        if self.session_db and not self.session_id:
            self.session_id = str(uuid.uuid4())
            self.session_db.create_session(
                self.session_id,
                self.llm.model,
                self.system_prompt,
                title=first_user_message[:50],
            )


    def _sync_memory(self) -> None:
        """每 nudge_interval 轮触发一次记忆提取与持久化"""
        if not self.memory_manager or not self.session_id:
            return

        self._turns_since_sync += 1
        if self._turns_since_sync < self.config.memory.nudge_interval:
            return

        self._turns_since_sync = 0

        recent = self._get_recent_conversation(self.config.memory.nudge_interval)
        if not recent:
            return

        self.memory_manager.sync(self.session_id, recent)

    def _get_recent_conversation(self, n_turns: int) -> list[dict]:
        """从 self.messages 提取最近 n 轮 user+assistant 对话"""
        pairs: list[dict] = []
        for msg in reversed(self.messages):
            if msg.get("role") in ("user", "assistant"):
                pairs.append(msg)
                if len(pairs) >= n_turns * 2:
                    break
        pairs.reverse()
        return pairs

    def _estimate_total_tokens(self) -> int:
        """估算当前消息列表的总 token 数"""
        total = 0
        for msg in self.messages:
            try:
                text = json.dumps(msg, ensure_ascii=False)
            except (TypeError, ValueError):
                text = str(msg)
            total += max(1, int(len(text) / 2.5))
        return total

    def _check_compression(self) -> None:
        """检查是否需要压缩，需要则执行"""
        if not self.compressor:
            return
        estimated_tokens = self._estimate_total_tokens()
        if self.compressor.should_compress(estimated_tokens):
            self.messages = self.compressor.compress(self.messages, estimated_tokens)
            if self.session_db and self.session_id:
                last = self.compressor.get_last_compressed_tokens()
                if last:
                    self.session_db.update_compressed_tokens(self.session_id, last)

    def _call_llm_stream(self, tools: list[dict] | None = None) -> dict[str, Any]:
        """流式调用 LLM，实时输出内容，返回完整响应"""
        content_parts: list[str] = []
        tool_calls = None
        finish_reason = None
        reasoning_content = None
        usage = None

        for event in self.llm.chat_stream(self.messages, tools=tools):
            if event["type"] == "content_delta":
                content_parts.append(event["content"])
                self.output_callback(event["content"])
            elif event["type"] == "reasoning_delta":
                self.output_callback(event["content"])
            elif event["type"] == "done":
                tool_calls = event.get("tool_calls")
                finish_reason = event.get("finish_reason", "stop")
                reasoning_content = event.get("reasoning_content")
                usage = event.get("usage")

        full_content = "".join(content_parts)
        self.output_callback("\n")

        # 错误响应不追加到消息历史
        if finish_reason == "error":
            return {
                "content": full_content,
                "tool_calls": None,
                "finish_reason": "error",
            }

        # 构造助手消息并追加
        assistant_msg: dict[str, Any] = {"role": "assistant", "content": full_content}
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls
        if reasoning_content:
            assistant_msg["reasoning_content"] = reasoning_content
        self.messages.append(assistant_msg)

        result: dict[str, Any] = {
            "content": full_content,
            "tool_calls": tool_calls,
            "finish_reason": finish_reason,
        }
        if reasoning_content:
            result["reasoning_content"] = reasoning_content
        if usage:
            result["usage"] = usage

        return result

    def _execute_tool_calls(self, tool_calls: list[dict]) -> list[dict[str, Any]]:
        """执行工具调用列表

        Args:
            tool_calls: LLM 返回的 tool_calls

        Returns:
            工具结果消息列表
        """
        logger.info("正在执行 %d 个工具调用", len(tool_calls))
        results = registry.dispatch_parallel(tool_calls)
        for i, result in enumerate(results):
            tool_name = tool_calls[i]["function"]["name"] if i < len(tool_calls) else "unknown"
            logger.info("工具 %s 结果: %s", tool_name, result.get("content", "")[:100])

        # LLM 主动调用 memory 工具时重置计数器
        for tc in tool_calls:
            if tc["function"]["name"] == "memory":
                self._turns_since_sync = 0
                break

        return results

    def _persist_assistant_message(self, response: dict[str, Any]) -> None:
        """持久化助手消息"""
        if not self.session_db or not self.session_id:
            return

        self.session_db.append_message(
            self.session_id,
            "assistant",
            content=response.get("content"),
            reasoning_content=response.get("reasoning_content"),
            tool_calls=response.get("tool_calls"),
            finish_reason=response.get("finish_reason"),
        )
        self.session_db.update_session_stats(self.session_id, message_count=1)

    def _grace_call(self) -> str:
        """预算耗尽后的最后一次调用，让 LLM 产出最终回复"""
        logger.info("正在执行兜底调用")
        self.messages.append({
            "role": "user",
            "content": "请总结当前进展并给出最终回复。",
        })

        if self.session_db and self.session_id:
            self.session_db.append_message(
                self.session_id, "user", content="请总结当前进展并给出最终回复。"
            )
            self.session_db.update_session_stats(self.session_id, message_count=1)

        response = self._call_llm_stream(tools=None)

        if self.session_db and self.session_id:
            usage = response.get("usage")
            if usage:
                self.session_db.update_session_stats(
                    self.session_id,
                    input_tokens=usage.get("prompt_tokens", 0),
                    output_tokens=usage.get("completion_tokens", 0),
                )

        self._persist_assistant_message(response)
        return response.get("content", "")

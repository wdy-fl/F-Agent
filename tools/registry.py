"""工具注册表：自注册、发现和串行调度"""

import json
import logging
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ToolEntry:
    """单个工具的注册信息"""

    def __init__(
        self,
        name: str,
        schema: dict[str, Any],
        handler: Callable,
        parallel_safe: bool = True,
        max_result_size: int = 50000,
    ):
        self.name = name
        self.schema = schema
        self.handler = handler
        self.parallel_safe = parallel_safe
        self.max_result_size = max_result_size


class ToolRegistry:
    """线程安全的工具注册表，支持注册和串行调度"""

    def __init__(self):
        self._tools: dict[str, ToolEntry] = {}
        self._lock = threading.RLock()
        self._generation = 0

    def register(
        self,
        name: str,
        schema: dict[str, Any],
        handler: Callable,
        parallel_safe: bool = True,
        max_result_size: int = 50000,
    ) -> None:
        """注册一个工具

        Args:
            name: 工具名称，全局唯一
            schema: OpenAI function calling 格式的工具定义
            handler: 工具执行函数，接收 dict 参数，返回 str 结果
            parallel_safe: 是否可并行执行（只读工具为 True）
            max_result_size: 结果最大字符数，超出截断
        """
        with self._lock:
            if name in self._tools:
                logger.warning("Tool %s already registered, overwriting", name)
            self._tools[name] = ToolEntry(
                name=name,
                schema=schema,
                handler=handler,
                parallel_safe=parallel_safe,
                max_result_size=max_result_size,
            )
            self._generation += 1
            logger.debug("Registered tool: %s (parallel_safe=%s)", name, parallel_safe)

    def deregister(self, name: str) -> None:
        """注销一个工具"""
        with self._lock:
            if name in self._tools:
                del self._tools[name]
                self._generation += 1
                logger.debug("Deregistered tool: %s", name)

    def get_definitions(self) -> list[dict[str, Any]]:
        """获取所有注册工具的 OpenAI schema 列表"""
        with self._lock:
            return [entry.schema for entry in self._tools.values()]

    def dispatch(self, name: str, args: dict[str, Any]) -> str:
        """调度执行指定工具

        Args:
            name: 工具名称
            args: 工具参数

        Returns:
            工具执行结果（JSON 字符串）
        """
        with self._lock:
            entry = self._tools.get(name)

        if entry is None:
            return json.dumps({"error": f"Unknown tool: {name}"}, ensure_ascii=False)

        try:
            result = entry.handler(args)
            if not isinstance(result, str):
                result = json.dumps(result, ensure_ascii=False)
            # 结果截断
            if len(result) > entry.max_result_size:
                result = result[:entry.max_result_size] + "\n...[truncated]"
            return result
        except Exception as e:
            logger.exception("Tool %s execution failed", name)
            return json.dumps({"error": f"Tool {name} failed: {e}"}, ensure_ascii=False)

    def dispatch_parallel(
        self,
        tool_calls: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """按原始顺序串行调度多个工具调用

        保留历史方法名以兼容现有调用方，但不再并行执行，
        也不根据 parallel_safe 元数据重排工具调用顺序。

        Args:
            tool_calls: OpenAI 格式的 tool_calls 列表

        Returns:
            工具结果消息列表（role=tool 格式）
        """
        tool_results = []

        for tc in tool_calls:
            func = tc["function"]
            call_id = tc["id"]
            try:
                args = json.loads(func["arguments"]) if isinstance(func["arguments"], str) else func["arguments"]
            except json.JSONDecodeError:
                content = json.dumps({"error": "Invalid JSON arguments"})
            else:
                content = self.dispatch(func["name"], args)

            tool_results.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": content,
            })

        return tool_results

    def has_tool(self, name: str) -> bool:
        """检查工具是否已注册"""
        with self._lock:
            return name in self._tools


# 全局单例
registry = ToolRegistry()

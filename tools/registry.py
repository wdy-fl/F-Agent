"""工具注册表：自注册 + 发现 + 调度"""

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    """线程安全的工具注册表，支持注册、调度和并行执行"""

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
        """并行调度多个工具调用

        将 tool_calls 分为并行安全组和不安全组：
        - 并行安全组用 ThreadPoolExecutor 并行执行
        - 不安全组顺序执行

        Args:
            tool_calls: OpenAI 格式的 tool_calls 列表

        Returns:
            工具结果消息列表（role=tool 格式）
        """
        safe_calls = []
        unsafe_calls = []

        with self._lock:
            for tc in tool_calls:
                func = tc["function"]
                name = func["name"]
                entry = self._tools.get(name)
                if entry and entry.parallel_safe:
                    safe_calls.append(tc)
                else:
                    unsafe_calls.append(tc)

        results: dict[str, str] = {}

        # 并行执行安全的工具
        if safe_calls:
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {}
                for tc in safe_calls:
                    func = tc["function"]
                    call_id = tc["id"]
                    try:
                        args = json.loads(func["arguments"]) if isinstance(func["arguments"], str) else func["arguments"]
                    except json.JSONDecodeError:
                        results[call_id] = json.dumps({"error": "Invalid JSON arguments"})
                        continue
                    futures[executor.submit(self.dispatch, func["name"], args)] = call_id

                for future in as_completed(futures):
                    call_id = futures[future]
                    results[call_id] = future.result()

        # 顺序执行不安全的工具
        for tc in unsafe_calls:
            func = tc["function"]
            call_id = tc["id"]
            try:
                args = json.loads(func["arguments"]) if isinstance(func["arguments"], str) else func["arguments"]
            except json.JSONDecodeError:
                results[call_id] = json.dumps({"error": "Invalid JSON arguments"})
                continue
            results[call_id] = self.dispatch(func["name"], args)

        # 按 tool_calls 原始顺序组装结果
        tool_results = []
        for tc in tool_calls:
            call_id = tc["id"]
            tool_results.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": results.get(call_id, json.dumps({"error": "No result"})),
            })

        return tool_results

    def has_tool(self, name: str) -> bool:
        """检查工具是否已注册"""
        with self._lock:
            return name in self._tools


# 全局单例
registry = ToolRegistry()

"""工具系统冒烟测试：验证注册、调度和并行执行"""

import importlib
import json

from tools.registry import ToolRegistry, registry as global_registry


def _clean_registry():
    """清空全局注册表并重载工具模块（测试用）"""
    global_registry._tools.clear()
    global_registry._generation = 0


def test_register_and_dispatch():
    """测试工具注册和调度"""
    reg = ToolRegistry()
    reg.register(
        name="echo",
        schema={"type": "function", "function": {"name": "echo", "parameters": {}}},
        handler=lambda args: json.dumps({"echo": args.get("msg", "")}),
        parallel_safe=True,
    )

    assert reg.has_tool("echo")
    result = reg.dispatch("echo", {"msg": "hello"})
    assert "hello" in result


def test_dispatch_unknown_tool():
    """测试调度未注册的工具"""
    reg = ToolRegistry()
    result = reg.dispatch("nonexistent", {})
    parsed = json.loads(result)
    assert "error" in parsed


def test_dispatch_tool_error():
    """测试工具执行异常时的错误处理"""
    reg = ToolRegistry()
    reg.register(
        name="fail_tool",
        schema={"type": "function", "function": {"name": "fail_tool", "parameters": {}}},
        handler=lambda args: (_ for _ in ()).throw(ValueError("boom")),
        parallel_safe=True,
    )

    result = reg.dispatch("fail_tool", {})
    parsed = json.loads(result)
    assert "error" in parsed
    assert "boom" in parsed["error"]


def test_result_truncation():
    """测试工具结果截断"""
    reg = ToolRegistry()
    long_result = "x" * 1000
    reg.register(
        name="verbose_tool",
        schema={"type": "function", "function": {"name": "verbose_tool", "parameters": {}}},
        handler=lambda args: long_result,
        parallel_safe=True,
        max_result_size=100,
    )

    result = reg.dispatch("verbose_tool", {})
    assert len(result) <= 150  # 截断 + 尾部提示
    assert "truncated" in result


def test_parallel_dispatch():
    """测试并行调度：安全工具并行，不安全工具顺序"""
    reg = ToolRegistry()

    call_order = []

    def safe_handler(args):
        call_order.append(f"safe_{args.get('id')}")
        return json.dumps({"ok": True})

    def unsafe_handler(args):
        call_order.append(f"unsafe_{args.get('id')}")
        return json.dumps({"ok": True})

    reg.register(
        name="safe_read",
        schema={"type": "function", "function": {"name": "safe_read", "parameters": {}}},
        handler=safe_handler,
        parallel_safe=True,
    )
    reg.register(
        name="unsafe_write",
        schema={"type": "function", "function": {"name": "unsafe_write", "parameters": {}}},
        handler=unsafe_handler,
        parallel_safe=False,
    )

    tool_calls = [
        {"id": "call_1", "function": {"name": "safe_read", "arguments": '{"id": 1}'}},
        {"id": "call_2", "function": {"name": "safe_read", "arguments": '{"id": 2}'}},
        {"id": "call_3", "function": {"name": "unsafe_write", "arguments": '{"id": 3}'}},
    ]

    results = reg.dispatch_parallel(tool_calls)

    assert len(results) == 3
    assert all(r["role"] == "tool" for r in results)
    # 每个结果都应该有对应的 call_id
    call_ids = {r["tool_call_id"] for r in results}
    assert call_ids == {"call_1", "call_2", "call_3"}


def test_builtin_tools_registered():
    """测试内置工具是否正确注册"""
    _clean_registry()
    # 重载工具模块触发注册
    import tools.terminal
    import tools.file_ops
    import tools.web_search
    importlib.reload(tools.terminal)
    importlib.reload(tools.file_ops)
    importlib.reload(tools.web_search)

    assert global_registry.has_tool("terminal")
    assert global_registry.has_tool("read_file")
    assert global_registry.has_tool("write_file")
    assert global_registry.has_tool("list_files")
    assert global_registry.has_tool("web_search")
    assert global_registry.has_tool("web_fetch")

    # terminal 不可并行
    assert not global_registry._tools["terminal"].parallel_safe
    # read_file 可并行
    assert global_registry._tools["read_file"].parallel_safe


def test_terminal_tool():
    """测试终端执行工具"""
    _clean_registry()
    import tools.terminal
    importlib.reload(tools.terminal)

    result = global_registry.dispatch("terminal", {"command": "echo hello"})
    parsed = json.loads(result)
    assert parsed["exit_code"] == 0
    assert "hello" in parsed["stdout"]


def test_file_ops_tools(tmp_path):
    """测试文件操作工具"""
    _clean_registry()
    import tools.file_ops
    importlib.reload(tools.file_ops)

    test_file = str(tmp_path / "test.txt")

    # 写文件
    result = global_registry.dispatch("write_file", {"path": test_file, "content": "hello world"})
    parsed = json.loads(result)
    assert "written" in parsed["action"]

    # 读文件
    result = global_registry.dispatch("read_file", {"path": test_file})
    parsed = json.loads(result)
    assert "hello world" in parsed["content"]

    # 列目录
    result = global_registry.dispatch("list_files", {"path": str(tmp_path)})
    parsed = json.loads(result)
    assert parsed["count"] >= 1

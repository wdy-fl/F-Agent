"""工具系统冒烟测试：验证注册、调度和串行执行"""

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

    def fail_handler(args):
        assert args == {}
        raise ValueError("boom")

    reg.register(
        name="fail_tool",
        schema={"type": "function", "function": {"name": "fail_tool", "parameters": {}}},
        handler=fail_handler,
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

    def verbose_handler(args):
        assert args == {}
        return long_result

    reg.register(
        name="verbose_tool",
        schema={"type": "function", "function": {"name": "verbose_tool", "parameters": {}}},
        handler=verbose_handler,
        parallel_safe=True,
        max_result_size=100,
    )

    result = reg.dispatch("verbose_tool", {})
    assert len(result) <= 150  # 截断 + 尾部提示
    assert "truncated" in result


def test_parallel_dispatch_executes_calls_serially_in_original_order():
    """测试历史并行方法名下，工具仍按 LLM 返回顺序串行执行"""
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
        {"id": "call_1", "function": {"name": "unsafe_write", "arguments": '{"id": 1}'}},
        {"id": "call_2", "function": {"name": "safe_read", "arguments": '{"id": 2}'}},
        {"id": "call_3", "function": {"name": "unsafe_write", "arguments": '{"id": 3}'}},
    ]

    results = reg.dispatch_parallel(tool_calls)

    assert call_order == ["unsafe_1", "safe_2", "unsafe_3"]
    assert [r["role"] for r in results] == ["tool", "tool", "tool"]
    assert [r["tool_call_id"] for r in results] == ["call_1", "call_2", "call_3"]


def test_parallel_dispatch_continues_after_invalid_json_arguments():
    """测试非法 JSON 参数返回错误结果，后续合法调用继续执行"""
    reg = ToolRegistry()

    received_args = []

    def handler(args):
        received_args.append(args)
        return json.dumps({"ok": True})

    reg.register(
        name="echo",
        schema={"type": "function", "function": {"name": "echo", "parameters": {}}},
        handler=handler,
        parallel_safe=True,
    )

    tool_calls = [
        {"id": "call_1", "function": {"name": "echo", "arguments": "{not-json"}},
        {"id": "call_2", "function": {"name": "echo", "arguments": '{"msg": "hello"}'}},
    ]

    results = reg.dispatch_parallel(tool_calls)

    assert [r["tool_call_id"] for r in results] == ["call_1", "call_2"]
    assert json.loads(results[0]["content"]) == {"error": "Invalid JSON arguments"}
    assert json.loads(results[1]["content"]) == {"ok": True}
    assert received_args == [{"msg": "hello"}]


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

    # parallel_safe 元数据保留，但当前调度器严格串行执行
    assert not global_registry._tools["terminal"].parallel_safe
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


def test_terminal_blocks_dangerous_without_callback():
    """无回调时危险命令被拒绝"""
    from tools.approval import set_approval_callback, set_approval_context
    _clean_registry()
    import tools.terminal
    importlib.reload(tools.terminal)

    set_approval_callback(None)
    set_approval_context(mode="manual")

    result = global_registry.dispatch("terminal", {"command": "rm -rf /tmp/test"})
    parsed = json.loads(result)
    assert parsed["exit_code"] == -1
    assert parsed["stdout"] == ""


def test_terminal_blocks_hardline_with_callback():
    """硬限制命令即使有回调也被阻止"""
    from tools.approval import set_approval_callback, set_approval_context
    _clean_registry()
    import tools.terminal
    importlib.reload(tools.terminal)

    def approve_cb(cmd, desc, key):
        return "once"

    set_approval_callback(approve_cb)
    set_approval_context(mode="manual")

    result = global_registry.dispatch("terminal", {"command": "shutdown --help"})
    parsed = json.loads(result)
    assert parsed["exit_code"] == -1


def test_terminal_dangerous_allowed_with_callback():
    """有回调且批准时危险命令可执行"""
    from tools.approval import set_approval_callback, set_approval_context
    _clean_registry()
    import tools.terminal
    importlib.reload(tools.terminal)

    def approve_cb(cmd, desc, key):
        return "once"

    set_approval_callback(approve_cb)
    set_approval_context(mode="manual")

    # "rm -rf --help" matches dangerous pattern but is harmless to execute
    result = global_registry.dispatch("terminal", {"command": "rm -rf --help"})
    parsed = json.loads(result)
    assert parsed["exit_code"] != -1 or "block" not in parsed.get("stderr", "")


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

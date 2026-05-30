"""工具系统冒烟测试：验证注册、调度和串行执行"""

import importlib
import json

from tools.registry import ToolRegistry, registry as global_registry


def _clean_registry():
    """清空全局注册表并重载工具模块（测试用）"""
    global_registry._tools.clear()


def test_register_and_dispatch():
    """测试工具注册和调度"""
    reg = ToolRegistry()
    reg.register(
        name="echo",
        schema={"type": "function", "function": {"name": "echo", "parameters": {}}},
        handler=lambda args: json.dumps({"echo": args.get("msg", "")}),
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
        max_result_size=100,
    )

    result = reg.dispatch("verbose_tool", {})
    assert len(result) <= 150  # 截断 + 尾部提示
    assert "truncated" in result


def test_dispatch_batch_executes_calls_serially_in_original_order():
    """测试批量调度按 LLM 返回顺序串行执行"""
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
    )
    reg.register(
        name="unsafe_write",
        schema={"type": "function", "function": {"name": "unsafe_write", "parameters": {}}},
        handler=unsafe_handler,
    )

    tool_calls = [
        {"id": "call_1", "function": {"name": "unsafe_write", "arguments": '{"id": 1}'}},
        {"id": "call_2", "function": {"name": "safe_read", "arguments": '{"id": 2}'}},
        {"id": "call_3", "function": {"name": "unsafe_write", "arguments": '{"id": 3}'}},
    ]

    results = reg.dispatch_batch(tool_calls)

    assert call_order == ["unsafe_1", "safe_2", "unsafe_3"]
    assert [r["role"] for r in results] == ["tool", "tool", "tool"]
    assert [r["tool_call_id"] for r in results] == ["call_1", "call_2", "call_3"]


def test_dispatch_batch_continues_after_invalid_json_arguments():
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
    )

    tool_calls = [
        {"id": "call_1", "function": {"name": "echo", "arguments": "{not-json"}},
        {"id": "call_2", "function": {"name": "echo", "arguments": '{"msg": "hello"}'}},
    ]

    results = reg.dispatch_batch(tool_calls)

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
    import tools.cron
    importlib.reload(tools.terminal)
    importlib.reload(tools.file_ops)
    importlib.reload(tools.web_search)
    importlib.reload(tools.cron)

    assert global_registry.has_tool("terminal")
    assert global_registry.has_tool("read_file")
    assert global_registry.has_tool("write_file")
    assert global_registry.has_tool("list_files")
    assert global_registry.has_tool("web_search")
    assert global_registry.has_tool("web_fetch")
    assert global_registry.has_tool("cron")



class _FakeToolConfig:
    def __init__(self, api_key="", timeout=30.0):
        self.baidu_ai_search_api_key = api_key
        self.baidu_ai_search_timeout = timeout


class _FakeAppConfig:
    def __init__(self, api_key="", timeout=30.0):
        self.tools = _FakeToolConfig(api_key=api_key, timeout=timeout)


def test_web_search_requires_baidu_ai_search_api_key(monkeypatch):
    _clean_registry()
    import tools.web_search
    importlib.reload(tools.web_search)

    def fail_urlopen(req, timeout):
        raise AssertionError("urlopen should not be called without API key")

    monkeypatch.setattr(tools.web_search, "get_config", lambda: _FakeAppConfig())
    monkeypatch.setattr(tools.web_search, "urlopen", fail_urlopen)

    result = tools.web_search.web_search({"query": "北京天气", "max_results": 1})
    parsed = json.loads(result)

    assert parsed == {"error": "Search failed: missing tools.baidu_ai_search_api_key"}


def test_web_search_uses_baidu_ai_search_api(monkeypatch):
    _clean_registry()
    import tools.web_search
    importlib.reload(tools.web_search)

    response_body = json.dumps(
        {
            "request_id": "req-1",
            "code": 0,
            "references": [
                {
                    "title": "北京天气预报_中国天气网",
                    "url": "https://www.weather.com.cn/weather/101010100.shtml",
                    "content": "31日（明天） 多云 31 / 20℃",
                }
            ],
        }
    ).encode("utf-8")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return response_body

    captured = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(req.header_items())
        captured["data"] = json.loads(req.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(tools.web_search, "get_config", lambda: _FakeAppConfig(api_key="sk-baidu-test", timeout=12.5))
    monkeypatch.setattr(tools.web_search, "urlopen", fake_urlopen)

    result = tools.web_search.web_search({"query": "北京天气", "max_results": 1})
    parsed = json.loads(result)

    assert captured["url"] == "https://qianfan.baidubce.com/v2/ai_search/web_search"
    assert captured["timeout"] == 12.5
    assert captured["headers"]["X-appbuilder-authorization"] == "Bearer sk-baidu-test"
    assert captured["headers"]["Content-type"] == "application/json"
    assert captured["data"] == {
        "messages": [{"content": "北京天气", "role": "user"}],
        "search_source": "baidu_search_v2",
        "resource_type_filter": [{"type": "web", "top_k": 1}],
        "edition": "standard",
    }
    assert parsed == {
        "query": "北京天气",
        "results": [
            {
                "title": "北京天气预报_中国天气网",
                "url": "https://www.weather.com.cn/weather/101010100.shtml",
                "snippet": "31日（明天） 多云 31 / 20℃",
            }
        ],
        "count": 1,
    }


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

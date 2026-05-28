"""memory 工具测试：工具注册 + handler 各 action"""

from unittest.mock import MagicMock

from tools.memory import handle_memory, set_managers


def setup_manager():
    mock_memory = MagicMock()
    mock_memory.session_db.search_messages.return_value = [
        {"role": "user", "content": "测试消息"},
    ]
    mock_memory.update_profile.return_value = "更新后的画像"
    mock_memory.update_soul.return_value = "更新后的身份"
    mock_memory.update_agent.return_value = "更新后的指引"
    mock_memory.get_memory.return_value = "笔记内容"
    mock_memory.get_soul.return_value = "身份内容"
    mock_memory.get_agent.return_value = "指引内容"
    set_managers(memory_manager=mock_memory)
    return mock_memory


def test_memory_tool_is_registered():
    from tools.registry import registry
    defs = registry.get_definitions()
    names = [d["function"]["name"] for d in defs]
    assert "memory" in names


def test_handle_search():
    mock_memory = setup_manager()
    import json
    result = json.loads(handle_memory({"action": "search", "query": "测试"}))
    assert len(result) == 1
    assert result[0]["content"] == "测试消息"


def test_handle_search_no_query():
    import json
    result = json.loads(handle_memory({"action": "search"}))
    assert "error" in result


def test_handle_search_no_manager():
    set_managers(memory_manager=None)
    import json
    result = json.loads(handle_memory({"action": "search", "query": "x"}))
    assert "error" in result


def test_handle_update_profile():
    mock_memory = setup_manager()
    import json
    result = json.loads(handle_memory({"action": "update_profile", "observations": "偏好终端"}))
    assert result["status"] == "updated"
    mock_memory.update_profile.assert_called_once_with("偏好终端")


def test_handle_update_profile_no_observations():
    import json
    result = json.loads(handle_memory({"action": "update_profile"}))
    assert "error" in result


def test_handle_read_memory():
    mock_memory = setup_manager()
    import json
    result = json.loads(handle_memory({"action": "read_memory"}))
    assert result["content"] == "笔记内容"


def test_handle_append_memory():
    mock_memory = setup_manager()
    import json
    result = json.loads(handle_memory({"action": "append_memory", "content": "新笔记"}))
    assert result["status"] == "appended"
    mock_memory.append_to_memory.assert_called_once_with("新笔记")


def test_handle_append_memory_no_content():
    import json
    result = json.loads(handle_memory({"action": "append_memory"}))
    assert "error" in result


def test_handle_update_soul():
    mock_memory = setup_manager()
    import json
    result = json.loads(handle_memory({"action": "update_soul", "content": "新身份"}))
    assert result["status"] == "updated"
    mock_memory.update_soul.assert_called_once_with("新身份")


def test_handle_update_agent():
    mock_memory = setup_manager()
    import json
    result = json.loads(handle_memory({"action": "update_agent", "content": "新指引"}))
    assert result["status"] == "updated"
    mock_memory.update_agent.assert_called_once_with("新指引")


def test_handle_unknown_action():
    import json
    result = json.loads(handle_memory({"action": "unknown"}))
    assert "error" in result
    assert "available_actions" in result


def test_save_action_removed():
    import json
    result = json.loads(handle_memory({"action": "save", "content": "test"}))
    assert "error" in result
    assert "Unknown action" in result["error"]


def test_no_manager_returns_error():
    set_managers(memory_manager=None)
    import json
    for action in ["update_profile", "read_memory", "append_memory", "read_soul", "update_soul", "read_agent", "update_agent"]:
        args = {"action": action}
        if action in ("update_profile",):
            args["observations"] = "x"
        elif action.startswith("update_") or action == "append_memory":
            args["content"] = "x"
        result = json.loads(handle_memory(args))
        assert "error" in result, f"{action} should return error without manager"
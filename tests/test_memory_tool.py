"""memory 工具测试：工具注册 + handler 各 action"""

from unittest.mock import MagicMock

from tools.memory import handle_memory, set_managers


def setup_managers(tmp_path):
    """辅助：设置 mock 管理器"""
    mock_memory = MagicMock()
    mock_memory.session_db.search_messages.return_value = [
        {"role": "user", "content": "测试消息"},
    ]
    profile_path = tmp_path / "USER.md"
    from memory.user_profile import UserProfileManager
    mock_profile = UserProfileManager(str(profile_path), llm=None)
    set_managers(memory_manager=mock_memory, profile_manager=mock_profile)
    return mock_memory, mock_profile


def test_memory_tool_is_registered():
    """验证 memory 工具已注册到 registry"""
    from tools.registry import registry
    defs = registry.get_definitions()
    names = [d["function"]["name"] for d in defs]
    assert "memory" in names


def test_handle_search(tmp_path):
    """测试 search action"""
    mock_memory, _ = setup_managers(tmp_path)

    import json
    result = json.loads(handle_memory({"action": "search", "query": "测试"}))

    assert len(result) == 1
    assert result[0]["content"] == "测试消息"
    mock_memory.session_db.search_messages.assert_called_once()


def test_handle_search_no_query():
    """search 缺少 query 参数时返回错误"""
    import json
    result = json.loads(handle_memory({"action": "search"}))

    assert "error" in result


def test_handle_search_no_manager():
    """未注入管理器时返回错误"""
    set_managers(memory_manager=None, profile_manager=None)

    import json
    result = json.loads(handle_memory({"action": "search", "query": "x"}))

    assert "error" in result


def test_handle_save(tmp_path):
    """测试 save action"""
    mock_memory, _ = setup_managers(tmp_path)

    import json
    result = json.loads(handle_memory({"action": "save", "content": "新内容"}))
    assert result["status"] == "saved"
    mock_memory.update_user_profile.assert_called_once_with("新内容")


def test_handle_save_no_content():
    """save 缺少 content 参数时返回错误"""
    import json
    result = json.loads(handle_memory({"action": "save"}))

    assert "error" in result


def test_handle_update_profile(tmp_path):
    """测试 update_profile action"""
    _, mock_profile = setup_managers(tmp_path)

    import json
    result = json.loads(handle_memory({"action": "update_profile", "observations": "喜欢终端"}))

    assert result["status"] == "updated"


def test_handle_update_profile_no_manager():
    """未注入 ProfileManager 时返回错误"""
    set_managers(memory_manager=None, profile_manager=None)

    import json
    result = json.loads(handle_memory({"action": "update_profile", "observations": "x"}))

    assert "error" in result


def test_handle_unknown_action():
    """未知 action 返回错误"""
    import json
    result = json.loads(handle_memory({"action": "unknown"}))

    assert "error" in result
    assert "available_actions" in result

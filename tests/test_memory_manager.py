"""记忆管理器测试：prefetch + 用户画像读写"""

from unittest.mock import MagicMock

from memory.manager import MemoryManager


def test_prefetch_with_search_results(tmp_path):
    """测试 prefetch：FTS5 搜索结果"""
    profile_path = tmp_path / "USER.md"

    mock_db = MagicMock()
    mock_db.search_messages.return_value = [
        {"role": "user", "content": "如何用 pytest 做 mock？"},
        {"role": "assistant", "content": "使用 unittest.mock.MagicMock"},
    ]

    mgr = MemoryManager(mock_db, str(profile_path))
    result = mgr.prefetch("pytest mock")

    assert "[历史相关对话]" in result
    assert "pytest" in result
    assert "MagicMock" in result


def test_prefetch_no_search_results(tmp_path):
    """测试 prefetch：无搜索结果时返回空字符串"""
    profile_path = tmp_path / "USER.md"

    mock_db = MagicMock()
    mock_db.search_messages.return_value = []

    mgr = MemoryManager(mock_db, str(profile_path))
    result = mgr.prefetch("不存在的关键词")

    assert result == ""


def test_prefetch_no_profile(tmp_path):
    """测试 prefetch：无用户画像时仅返回搜索结果"""
    profile_path = tmp_path / "USER.md"

    mock_db = MagicMock()
    mock_db.search_messages.return_value = [
        {"role": "user", "content": "测试消息"},
    ]

    mgr = MemoryManager(mock_db, str(profile_path))
    result = mgr.prefetch("测试")

    assert "[历史相关对话]" in result
    assert "[用户画像]" not in result


def test_prefetch_empty(tmp_path):
    """测试 prefetch：无结果无画像时返回空字符串"""
    profile_path = tmp_path / "USER.md"

    mock_db = MagicMock()
    mock_db.search_messages.return_value = []

    mgr = MemoryManager(mock_db, str(profile_path))
    result = mgr.prefetch("无匹配")

    assert result == ""


def test_get_user_profile_exists(tmp_path):
    """测试读取已存在的用户画像"""
    profile_path = tmp_path / "USER.md"
    profile_path.write_text("用户偏好：终端操作", encoding="utf-8")

    mock_db = MagicMock()
    mgr = MemoryManager(mock_db, str(profile_path))
    assert mgr.get_user_profile() == "用户偏好：终端操作"


def test_get_user_profile_not_exists(tmp_path):
    """测试读取不存在的用户画像返回空字符串"""
    profile_path = tmp_path / "nonexistent" / "USER.md"

    mock_db = MagicMock()
    mgr = MemoryManager(mock_db, str(profile_path))
    assert mgr.get_user_profile() == ""


def test_update_user_profile(tmp_path):
    """测试写入用户画像"""
    profile_path = tmp_path / "USER.md"

    mock_db = MagicMock()
    mgr = MemoryManager(mock_db, str(profile_path))
    mgr.update_user_profile("新画像内容")

    assert profile_path.exists()
    assert profile_path.read_text(encoding="utf-8") == "新画像内容"


def test_update_user_profile_creates_dir(tmp_path):
    """测试写入画像时目录不存在则创建"""
    profile_path = tmp_path / "subdir" / "USER.md"

    mock_db = MagicMock()
    mgr = MemoryManager(mock_db, str(profile_path))
    mgr.update_user_profile("内容")

    assert profile_path.exists()
    assert profile_path.read_text(encoding="utf-8") == "内容"


def test_sync_is_harmless(tmp_path):
    """测试 sync 方法是可安全调用的钩子"""
    profile_path = tmp_path / "USER.md"
    mock_db = MagicMock()

    mgr = MemoryManager(mock_db, str(profile_path))
    # sync 不抛异常即为通过
    mgr.sync("sess-1", "用户消息", "助手回复")

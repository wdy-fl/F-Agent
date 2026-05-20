"""用户画像测试：LLM 驱动画像更新 + 边界情况"""

from unittest.mock import MagicMock

from memory.user_profile import UserProfileManager, MAX_PROFILE_LENGTH


def test_read_profile_exists(tmp_path):
    """测试读取已存在的画像"""
    path = tmp_path / "USER.md"
    path.write_text("用户是一名 Python 开发者", encoding="utf-8")

    mgr = UserProfileManager(str(path))
    assert mgr.read_profile() == "用户是一名 Python 开发者"


def test_read_profile_not_exists(tmp_path):
    """测试读取不存在的画像返回空字符串"""
    mgr = UserProfileManager(str(tmp_path / "nonexistent" / "USER.md"))
    assert mgr.read_profile() == ""


def test_write_profile(tmp_path):
    """测试写入画像"""
    path = tmp_path / "USER.md"
    mgr = UserProfileManager(str(path))
    mgr.write_profile("新画像内容")

    assert path.read_text(encoding="utf-8") == "新画像内容"


def test_write_profile_creates_dir(tmp_path):
    """测试写入时自动创建目录"""
    path = tmp_path / "sub" / "USER.md"
    mgr = UserProfileManager(str(path))
    mgr.write_profile("test")

    assert path.exists()


def test_write_profile_truncates(tmp_path):
    """超长画像截断"""
    path = tmp_path / "USER.md"
    mgr = UserProfileManager(str(path))
    long_content = "x" * (MAX_PROFILE_LENGTH + 100)
    mgr.write_profile(long_content)

    saved = path.read_text(encoding="utf-8")
    assert len(saved) == MAX_PROFILE_LENGTH


def test_update_profile_with_llm(tmp_path):
    """LLM 驱动的画像更新：验证 LLM 调用 + 结果写入"""
    path = tmp_path / "USER.md"
    path.write_text("用户使用 Python", encoding="utf-8")

    mock_llm = MagicMock()
    mock_llm.chat.return_value = MagicMock(content="用户使用 Python，偏好 VS Code")

    mgr = UserProfileManager(str(path), llm=mock_llm)
    result = mgr.update_profile("偏好 VS Code")

    assert "VS Code" in result
    mock_llm.chat.assert_called_once()
    assert path.read_text(encoding="utf-8") == "用户使用 Python，偏好 VS Code"


def test_update_profile_without_llm(tmp_path):
    """无 LLM 时直接追加观察"""
    path = tmp_path / "USER.md"
    path.write_text("原始画像", encoding="utf-8")

    mgr = UserProfileManager(str(path), llm=None)
    result = mgr.update_profile("新观察")

    assert "原始画像" in result
    assert "新观察" in result


def test_update_profile_llm_failure(tmp_path):
    """LLM 调用失败时保留原画像"""
    path = tmp_path / "USER.md"
    path.write_text("原始画像", encoding="utf-8")

    mock_llm = MagicMock()
    mock_llm.chat.side_effect = RuntimeError("API error")

    mgr = UserProfileManager(str(path), llm=mock_llm)
    result = mgr.update_profile("新观察")

    assert result == "原始画像"
    assert path.read_text(encoding="utf-8") == "原始画像"

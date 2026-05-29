"""记忆管理器测试：LLM 合并 + 文件读写 + prefetch + sync"""

from unittest.mock import MagicMock

from memory.manager import MemoryManager


def test_prefetch_with_search_results(tmp_path):
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


def test_prefetch_no_results(tmp_path):
    profile_path = tmp_path / "USER.md"
    mock_db = MagicMock()
    mock_db.search_messages.return_value = []
    mgr = MemoryManager(mock_db, str(profile_path))
    assert mgr.prefetch("nope") == ""


def test_get_user_profile(tmp_path):
    path = tmp_path / "USER.md"
    path.write_text("用户偏好：终端操作", encoding="utf-8")
    mgr = MemoryManager(MagicMock(), str(path))
    assert mgr.get_user_profile() == "用户偏好：终端操作"


def test_get_user_profile_not_exists(tmp_path):
    mgr = MemoryManager(MagicMock(), str(tmp_path / "nope" / "USER.md"))
    assert mgr.get_user_profile() == ""


def test_update_profile_with_llm(tmp_path):
    path = tmp_path / "USER.md"
    path.write_text("用户使用 Python", encoding="utf-8")
    mock_llm = MagicMock()
    mock_llm.chat.return_value = {"content": "用户使用 Python，偏好 VS Code"}
    mgr = MemoryManager(MagicMock(), str(path), llm=mock_llm)
    result = mgr.update_profile("偏好 VS Code")
    assert "VS Code" in result
    mock_llm.chat.assert_called_once()


def test_update_profile_without_llm(tmp_path):
    path = tmp_path / "USER.md"
    path.write_text("原始", encoding="utf-8")
    mgr = MemoryManager(MagicMock(), str(path), llm=None)
    result = mgr.update_profile("新观察")
    assert "原始" in result
    assert "新观察" in result


def test_update_profile_llm_failure_fallback(tmp_path):
    path = tmp_path / "USER.md"
    path.write_text("原始画像", encoding="utf-8")
    mock_llm = MagicMock()
    mock_llm.chat.side_effect = RuntimeError("API error")
    mgr = MemoryManager(MagicMock(), str(path), llm=mock_llm)
    result = mgr.update_profile("新观察")
    assert "原始画像" in result


def test_update_soul_with_llm(tmp_path):
    path = tmp_path / "SOUL.md"
    path.write_text("你是测试助手", encoding="utf-8")
    mock_llm = MagicMock()
    mock_llm.chat.return_value = {"content": "你是测试助手，擅长自动化测试"}
    mgr = MemoryManager(MagicMock(), "", soul_path=str(path), llm=mock_llm)
    result = mgr.update_soul("擅长自动化测试")
    assert "自动化测试" in result


def test_update_agent_with_llm(tmp_path):
    path = tmp_path / "AGENT.md"
    path.write_text("## 工具使用\n使用工具完成任务", encoding="utf-8")
    mock_llm = MagicMock()
    mock_llm.chat.return_value = {"content": "## 工具使用\n使用工具完成任务\n新规则：先确认再执行"}
    mgr = MemoryManager(MagicMock(), "", agent_path=str(path), llm=mock_llm)
    result = mgr.update_agent("新规则：先确认再执行")
    assert "先确认再执行" in result


def test_append_to_memory(tmp_path):
    path = tmp_path / "MEMORY.md"
    mgr = MemoryManager(MagicMock(), "", memory_path=str(path))
    mgr.append_to_memory("测试条目")
    content = mgr.get_memory()
    assert "测试条目" in content


def test_append_to_memory_triggers_consolidation(tmp_path):
    path = tmp_path / "MEMORY.md"
    long_content = "条目\n" * 6000
    path.write_text(long_content, encoding="utf-8")
    mock_llm = MagicMock()
    mock_llm.chat.return_value = {"content": "整理后的笔记"}
    mgr = MemoryManager(MagicMock(), "", memory_path=str(path), llm=mock_llm)
    mgr.append_to_memory("新条目")
    assert mock_llm.chat.called


def test_sync_extracts_and_writes_profile(tmp_path):
    profile_path = tmp_path / "USER.md"
    profile_path.write_text("", encoding="utf-8")
    mock_llm = MagicMock()
    mock_llm.chat.return_value = {
        "content": '{"extractions": [{"target": "profile", "content": "用户偏好 VS Code"}]}'
    }
    mgr = MemoryManager(MagicMock(), str(profile_path), llm=mock_llm)
    mgr.sync("sess-1", [
        {"role": "user", "content": "我喜欢用 VS Code"},
        {"role": "assistant", "content": "好的，记住了"},
    ])
    # update_profile 被调用，会触发第二次 LLM chat（合并 prompt）
    assert mock_llm.chat.call_count >= 1


def test_sync_extracts_and_appends_memory(tmp_path):
    profile_path = tmp_path / "USER.md"
    memory_path = tmp_path / "MEMORY.md"
    mock_llm = MagicMock()
    mock_llm.chat.return_value = {
        "content": '{"extractions": [{"target": "memory", "content": "项目使用 FastAPI"}]}'
    }
    mgr = MemoryManager(MagicMock(), str(profile_path), memory_path=str(memory_path), llm=mock_llm)
    mgr.sync("sess-1", [
        {"role": "user", "content": "我们后端用的是 FastAPI"},
        {"role": "assistant", "content": "了解"},
    ])
    content = memory_path.read_text(encoding="utf-8")
    assert "项目使用 FastAPI" in content


def test_sync_no_extractions_does_nothing(tmp_path):
    profile_path = tmp_path / "USER.md"
    profile_path.write_text("原始内容", encoding="utf-8")
    mock_llm = MagicMock()
    mock_llm.chat.return_value = {"content": '{"extractions": []}'}
    mgr = MemoryManager(MagicMock(), str(profile_path), llm=mock_llm)
    mgr.sync("sess-1", [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好"},
    ])
    assert profile_path.read_text(encoding="utf-8") == "原始内容"


def test_sync_without_llm_does_nothing(tmp_path):
    profile_path = tmp_path / "USER.md"
    mgr = MemoryManager(MagicMock(), str(profile_path), llm=None)
    mgr.sync("sess-1", [{"role": "user", "content": "hello"}])
    # 不应抛异常
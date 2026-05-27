"""上下文围栏测试：注入 / 边界情况"""

from memory.context_fence import inject_context


def test_inject_basic():
    """测试基本注入"""
    result = inject_context("用户消息", "历史记忆")
    assert result == "<memory-context>\n历史记忆\n</memory-context>\n用户消息"


def test_inject_empty_memory():
    """空记忆内容时直接返回用户消息"""
    result = inject_context("用户消息", "")
    assert result == "用户消息"

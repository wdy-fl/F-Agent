"""上下文围栏测试：注入/剥离 + 边界情况"""

from memory.context_fence import inject_context, strip_context


def test_inject_basic():
    """测试基本注入"""
    result = inject_context("用户消息", "历史记忆")
    assert result == "<memory-context>\n历史记忆\n</memory-context>\n用户消息"


def test_inject_empty_memory():
    """空记忆内容时直接返回用户消息"""
    result = inject_context("用户消息", "")
    assert result == "用户消息"


def test_strip_basic():
    """测试基本剥离"""
    message = "<memory-context>\n历史记忆\n</memory-context>\n用户消息"
    clean, memory = strip_context(message)
    assert clean == "用户消息"
    assert memory == "历史记忆"


def test_strip_no_tag():
    """消息不含标签时原样返回"""
    message = "普通消息"
    clean, memory = strip_context(message)
    assert clean == "普通消息"
    assert memory == ""


def test_strip_incomplete_open():
    """只有开始标签，无结束标签 → 返回原消息"""
    message = "<memory-context>\n内容"
    clean, memory = strip_context(message)
    assert clean == "<memory-context>\n内容"
    assert memory == ""


def test_strip_incomplete_close():
    """无开始标签，只有结束标签 → 返回原消息"""
    message = "内容\n</memory-context>"
    clean, memory = strip_context(message)
    assert clean == "内容\n</memory-context>"
    assert memory == ""


def test_strip_multiline_memory():
    """记忆内容多行"""
    message = "<memory-context>\n行1\n行2\n行3\n</memory-context>\n用户消息"
    clean, memory = strip_context(message)
    assert clean == "用户消息"
    assert memory == "行1\n行2\n行3"


def test_strip_trailing_after_tag():
    """标签后有额外内容"""
    message = "前置文本<memory-context>\n记忆\n</memory-context>\n用户消息"
    clean, memory = strip_context(message)
    assert clean == "前置文本用户消息"
    assert memory == "记忆"

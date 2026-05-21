"""上下文压缩测试：阈值触发/头尾保护/反抖动/LLM 降级"""

from unittest.mock import MagicMock

from context.compressor import ContextCompressor


def make_messages(count: int) -> list[dict]:
    """生成测试消息列表"""
    msgs = [{"role": "system", "content": "You are a helpful assistant."}]
    for i in range(1, count):
        role = "user" if i % 2 == 1 else "assistant"
        msgs.append({
            "role": role,
            "content": f"这是第 {i} 条消息，包含一些中文内容来增加 token 估算值。" * 10,
        })
    return msgs


def test_should_compress_below_threshold():
    """token 低于阈值时不触发压缩"""
    llm = MagicMock()
    comp = ContextCompressor(llm, context_window=128000, threshold=0.5)
    assert not comp.should_compress(1000)


def test_should_compress_above_threshold():
    """token 达到阈值时触发压缩"""
    llm = MagicMock()
    comp = ContextCompressor(llm, context_window=128000, threshold=0.5)
    assert comp.should_compress(70000)


def test_compress_too_few_messages():
    """消息太少时跳过压缩"""
    llm = MagicMock()
    comp = ContextCompressor(llm)
    messages = make_messages(4)  # system + 3 messages
    result = comp.compress(messages, 70000)
    assert result == messages  # 原样返回


def test_compress_with_llm_summary():
    """正常压缩流程：head + summary + tail"""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = MagicMock(content="压缩后的摘要内容")

    # 生成足够多的消息触发压缩
    messages = make_messages(20)
    comp = ContextCompressor(
        mock_llm,
        context_window=10000,
        threshold=0.1,
        protected_head=3,
        protected_tail_tokens=1000,
    )

    result = comp.compress(messages, 5000)

    # 验证结果结构：head 保护 + summary + tail
    assert len(result) < len(messages)
    assert result[0] == messages[0]  # head 第 1 条被保护
    assert result[1] == messages[1]  # head 第 2 条被保护
    assert result[2] == messages[2]  # head 第 3 条被保护
    # summary 消息
    assert "摘要" in result[3]["content"]
    mock_llm.chat.assert_called_once()


def test_compress_llm_failure_fallback():
    """LLM 摘要失败时返回基本摘要并继续"""
    mock_llm = MagicMock()
    mock_llm.chat.side_effect = RuntimeError("API error")

    messages = make_messages(20)
    comp = ContextCompressor(
        mock_llm,
        context_window=10000,
        threshold=0.1,
        protected_head=3,
        protected_tail_tokens=100,
    )

    result = comp.compress(messages, 5000)
    # 不应抛异常
    assert len(result) < len(messages)


def test_compress_anti_jitter():
    """反抖动：连续压缩节省 < 10% 时跳过"""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = MagicMock(content="摘要")

    messages = make_messages(20)
    comp = ContextCompressor(
        mock_llm,
        context_window=10000,
        threshold=0.1,
        min_saving=0.1,
        protected_head=3,
        protected_tail_tokens=100,
    )

    # 第一次压缩
    result1 = comp.compress(messages, 5000)
    assert len(result1) < len(messages)

    # 第二次压缩（token 数接近上次压缩后），应跳过
    result2 = comp.compress(result1, 4900)
    assert result2 == result1  # 跳过，原样返回


def test_trim_tool_results():
    """工具结果裁剪"""
    llm = MagicMock()
    comp = ContextCompressor(llm)

    messages = [
        {"role": "user", "content": "hello"},
        {"role": "tool", "content": "x" * 1000, "tool_call_id": "call_1"},
        {"role": "assistant", "content": "done"},
    ]

    result = comp.trim_tool_results(messages, max_tokens=500)
    assert len(result) == 3
    # tool 消息被截断
    assert "截断" in result[1]["content"]
    assert len(result[1]["content"]) < 1000
    # 非 tool 消息不变
    assert result[0]["content"] == "hello"


def test_trim_tool_results_no_trim_short():
    """短工具结果不裁剪"""
    llm = MagicMock()
    comp = ContextCompressor(llm)

    messages = [
        {"role": "tool", "content": "short", "tool_call_id": "call_1"},
    ]

    result = comp.trim_tool_results(messages, max_tokens=500)
    assert result[0]["content"] == "short"


def test_estimate_tokens():
    """token 估算不为 0"""
    llm = MagicMock()
    comp = ContextCompressor(llm)
    tokens = comp._estimate_tokens({"role": "user", "content": "你好世界"})
    assert tokens > 0


def test_head_protection():
    """验证头部消息被保护"""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = MagicMock(content="摘要")

    messages = make_messages(30)
    comp = ContextCompressor(
        mock_llm,
        context_window=10000,
        threshold=0.1,
        protected_head=3,
        protected_tail_tokens=200,
    )

    result = comp.compress(messages, 5000)
    # 前 3 条（protected_head）应原样保留
    for i in range(3):
        assert result[i] == messages[i]

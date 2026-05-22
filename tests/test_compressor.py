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


def test_compress_trims_old_tool_results_before_summary():
    """压缩前裁剪长工具结果，摘要 prompt 不包含完整工具输出"""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = MagicMock(content="摘要")

    long_tool_output = "工具输出" * 300
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "开始任务"},
        {"role": "assistant", "content": "我来调用工具"},
        {"role": "tool", "content": long_tool_output, "tool_call_id": "call_1"},
        {"role": "assistant", "content": "工具调用完成"},
        {"role": "user", "content": "继续"},
    ]
    comp = ContextCompressor(
        mock_llm,
        context_window=10000,
        threshold=0.1,
        protected_head=1,
        protected_tail_tokens=10,
    )

    comp.compress(messages, 5000)

    prompt = mock_llm.chat.call_args.kwargs["messages"][0]["content"]
    assert "截断" in prompt
    assert long_tool_output not in prompt


def test_compress_iteratively_updates_existing_summary():
    """已有摘要参与下一次压缩，新摘要基于旧摘要和新增对话迭代更新"""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = MagicMock(content="更新后的摘要")

    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "assistant", "content": "[对话摘要]\n旧摘要内容"},
        {"role": "user", "content": "新增需求：实现迭代压缩"},
        {"role": "assistant", "content": "正在修改 context/compressor.py"},
        {"role": "user", "content": "请继续"},
    ]
    comp = ContextCompressor(
        mock_llm,
        context_window=10000,
        threshold=0.1,
        protected_head=1,
        protected_tail_tokens=10,
    )

    result = comp.compress(messages, 5000)

    prompt = mock_llm.chat.call_args.kwargs["messages"][0]["content"]
    assert "旧摘要" in prompt
    assert "旧摘要内容" in prompt
    assert "新增对话" in prompt
    assert "新增需求：实现迭代压缩" in prompt
    assert result[1]["content"] == "[对话摘要]\n更新后的摘要"


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


def test_tool_call_group_is_not_split_by_tail_boundary():
    """assistant(tool_calls) 与对应 tool 结果作为不可拆分组保留，tail 不从孤立 tool 开始"""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = MagicMock(content="摘要")

    long_tool_output = "tail 工具输出" * 200
    assistant_tool_call = {
        "role": "assistant",
        "content": "调用 tail 工具",
        "tool_calls": [
            {"id": "call_tail", "type": "function", "function": {"name": "read", "arguments": "{}"}}
        ],
    }
    tool_result = {"role": "tool", "content": long_tool_output, "tool_call_id": "call_tail"}
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "需要工具"},
        {"role": "assistant", "content": "普通回复"},
        {"role": "user", "content": "准备调用"},
        assistant_tool_call,
        tool_result,
    ]
    comp = ContextCompressor(
        mock_llm,
        context_window=10000,
        threshold=0.1,
        protected_head=1,
        protected_tail_tokens=10,
    )

    result = comp.compress(messages, 5000)

    assert result[-2] == assistant_tool_call
    assert result[-1] == tool_result
    assert result[-1]["content"] == long_tool_output
    assert result[2]["role"] != "tool"


def test_compressed_result_does_not_leave_orphan_tool_message():
    """压缩结果不能留下没有前置 tool_calls assistant 的孤立 tool 消息"""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = MagicMock(content="摘要")

    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "head"},
        {
            "role": "assistant",
            "content": "调用工具",
            "tool_calls": [
                {"id": "call_mid", "type": "function", "function": {"name": "search", "arguments": "{}"}}
            ],
        },
        {"role": "tool", "content": "middle 工具结果", "tool_call_id": "call_mid"},
        {"role": "assistant", "content": "工具结束"},
        {"role": "user", "content": "tail"},
    ]
    comp = ContextCompressor(
        mock_llm,
        context_window=10000,
        threshold=0.1,
        protected_head=3,
        protected_tail_tokens=10,
    )

    result = comp.compress(messages, 5000)

    for index, message in enumerate(result):
        if message["role"] == "tool":
            assert index > 0
            previous = result[index - 1]
            tool_call_ids = {call["id"] for call in previous.get("tool_calls", [])}
            assert message["tool_call_id"] in tool_call_ids


def test_llm_failure_with_previous_summary_keeps_new_middle_content():
    """旧摘要存在且 LLM 失败时，fallback 不能丢失新增 middle 对话关键信息"""
    mock_llm = MagicMock()
    mock_llm.chat.side_effect = RuntimeError("API error")

    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "assistant", "content": "[对话摘要]\n旧摘要内容"},
        {"role": "user", "content": "新增关键需求：保留失败时的新增对话"},
        {"role": "assistant", "content": "已记录新增需求"},
        {"role": "user", "content": "tail"},
    ]
    comp = ContextCompressor(
        mock_llm,
        context_window=10000,
        threshold=0.1,
        protected_head=1,
        protected_tail_tokens=10,
    )

    result = comp.compress(messages, 5000)

    summary_content = result[1]["content"]
    assert "旧摘要内容" in summary_content
    assert "新增关键需求" in summary_content
    assert "保留失败时的新增对话" in summary_content


def test_existing_summary_with_new_middle_bypasses_anti_jitter():
    """首次压缩后追加新增 middle 对话，再次压缩应迭代更新而非被反抖动跳过"""
    mock_llm = MagicMock()
    mock_llm.chat.side_effect = [MagicMock(content="第一次摘要"), MagicMock(content="第二次摘要")]

    messages = make_messages(20)
    comp = ContextCompressor(
        mock_llm,
        context_window=10000,
        threshold=0.1,
        min_saving=0.1,
        protected_head=3,
        protected_tail_tokens=100,
    )

    result1 = comp.compress(messages, 5000)
    messages_with_new_middle = result1[:4] + [
        {"role": "user", "content": "新增迭代内容：需要再次压缩"},
        {"role": "assistant", "content": "准备更新摘要"},
    ] + result1[4:]

    result2 = comp.compress(messages_with_new_middle, 4900)

    assert mock_llm.chat.call_count == 2
    assert any(message.get("content") == "[对话摘要]\n第二次摘要" for message in result2)


def test_protected_tail_tool_result_kept_original_but_middle_tool_result_trimmed_in_prompt():
    """tail 内长工具结果原样保护；middle 内长工具结果进入摘要 prompt 前裁剪"""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = MagicMock(content="摘要")

    middle_tool_output = "middle 工具输出" * 300
    tail_tool_output = "tail 工具输出" * 300
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "middle tool"},
        {
            "role": "assistant",
            "content": "调用 middle 工具",
            "tool_calls": [
                {"id": "call_middle", "type": "function", "function": {"name": "middle", "arguments": "{}"}}
            ],
        },
        {"role": "tool", "content": middle_tool_output, "tool_call_id": "call_middle"},
        {"role": "assistant", "content": "middle 完成"},
        {
            "role": "assistant",
            "content": "调用 tail 工具",
            "tool_calls": [
                {"id": "call_tail", "type": "function", "function": {"name": "tail", "arguments": "{}"}}
            ],
        },
        {"role": "tool", "content": tail_tool_output, "tool_call_id": "call_tail"},
    ]
    comp = ContextCompressor(
        mock_llm,
        context_window=10000,
        threshold=0.1,
        protected_head=1,
        protected_tail_tokens=10,
    )

    result = comp.compress(messages, 5000)

    prompt = mock_llm.chat.call_args.kwargs["messages"][0]["content"]
    assert "截断" in prompt
    assert middle_tool_output not in prompt
    assert result[-1]["content"] == tail_tool_output


def test_summary_prompt_uses_explicit_empty_placeholders():
    """空旧摘要和空新增对话在 prompt 中使用显式占位文本"""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = MagicMock(content="摘要")
    comp = ContextCompressor(mock_llm)

    comp._generate_summary([], "")

    prompt = mock_llm.chat.call_args.kwargs["messages"][0]["content"]
    assert "旧摘要：（无旧摘要）" in prompt
    assert "新增对话：（无新增对话）" in prompt

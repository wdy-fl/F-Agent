"""上下文围栏：<memory-context> 标签注入与剥离，防止 LLM 混淆历史记忆与当前输入"""

import re

CONTEXT_OPEN = "<memory-context>"
CONTEXT_CLOSE = "</memory-context>"


def inject_context(user_message: str, memory_context: str) -> str:
    """将记忆上下文包装在围栏标签中，注入到用户消息前

    Args:
        user_message: 用户的原始输入
        memory_context: 预取的记忆内容（FTS5 搜索结果 + 用户画像）

    Returns:
        带记忆上下文的完整消息
    """
    if not memory_context:
        return user_message
    return f"{CONTEXT_OPEN}\n{memory_context}\n{CONTEXT_CLOSE}\n{user_message}"


def strip_context(message: str) -> tuple[str, str]:
    """从消息中剥离 <memory-context> 标签，分离记忆部分和用户消息

    Args:
        message: 可能包含 <memory-context> 标签的消息

    Returns:
        (clean_message, memory_part) — clean_message 是去除标签后的用户消息，
        memory_part 是标签内的记忆内容。标签不完整时返回 (原消息, "")
    """
    if CONTEXT_OPEN not in message:
        return message, ""

    pattern = re.compile(
        re.escape(CONTEXT_OPEN) + r"\n(.*?)\n" + re.escape(CONTEXT_CLOSE) + r"\n",
        re.DOTALL,
    )
    match = pattern.search(message)
    if not match:
        # 标签不完整
        return message, ""

    memory_part = match.group(1)
    clean = message[:match.start()] + message[match.end():]
    return clean, memory_part

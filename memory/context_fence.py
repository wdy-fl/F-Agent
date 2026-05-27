"""上下文围栏：<memory-context> 标签注入，防止 LLM 混淆历史记忆与当前输入"""

CONTEXT_OPEN = "<memory-context>"
CONTEXT_CLOSE = "</memory-context>"


def inject_context(user_message: str, memory_context: str) -> str:
    """将记忆上下文包装在围栏标签中，注入到用户消息前

    Args:
        user_message: 用户的原始输入
        memory_context: 预取的记忆内容（FTS5 搜索结果）

    Returns:
        带记忆上下文的完整消息
    """
    if not memory_context:
        return user_message
    return f"{CONTEXT_OPEN}\n{memory_context}\n{CONTEXT_CLOSE}\n{user_message}"

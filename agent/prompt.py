"""系统提示词构建：身份 + 技能索引 + 上下文文件"""

from datetime import datetime

from tools.registry import registry

AGENT_IDENTITY = """\
你是阿福（F-Agent），一个智能个人助手。

## 核心能力
- 智能对话：理解用户意图，提供有帮助的回答
- 工具调用：通过工具与系统交互（终端执行、文件操作、Web 搜索等）

## 行为准则
- 用中文与用户交流，除非用户明确要求其他语言
- 回答简洁有用，不啰嗦
- 需要执行操作时主动使用工具，不要只描述计划
- 遇到不确定的问题，坦诚说明而不是猜测
"""

TOOL_USE_GUIDANCE = """\
## 工具使用
你有可用的工具来完成任务。当需要执行操作时，直接调用工具，不要只是描述你将要做什么。

### 可用工具
{tool_index}

### 工具使用规则
- 需要执行命令时使用 terminal 工具
- 需要读写文件时使用 read_file / write_file 工具
- 需要搜索信息时使用 web_search 工具
- 多个独立的只读操作可以并行执行
- 有副作用的操作（写入文件、执行命令）会顺序执行
"""

MEMORY_GUIDANCE = """\
## 记忆系统
你的用户消息可能包含 `<memory-context>` 标签，其中注入了：
- 与当前话题相关的历史对话片段
- 用户的偏好画像

使用这些信息来个性化回复，但不要在回复中引用标签格式本身。
"""


def build_system_prompt(
    include_tools: bool = False,
    include_memory_guidance: bool = True,
) -> str:
    """构建系统提示词

    Args:
        include_tools: 是否包含工具使用指引
        include_memory_guidance: 是否包含记忆系统指引
    """
    parts = [AGENT_IDENTITY]

    if include_tools:
        tool_index = _build_tool_index()
        parts.append(TOOL_USE_GUIDANCE.format(tool_index=tool_index))

    if include_memory_guidance:
        parts.append(MEMORY_GUIDANCE)

    # 时间戳
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts.append(f"\n当前时间：{now}")

    return "\n".join(parts)


def _build_tool_index() -> str:
    """构建工具索引列表"""
    definitions = registry.get_definitions()
    if not definitions:
        return "（暂无可用工具）"

    lines = []
    for defn in definitions:
        func = defn.get("function", {})
        name = func.get("name", "unknown")
        desc = func.get("description", "")
        lines.append(f"- **{name}**: {desc}")
    return "\n".join(lines)

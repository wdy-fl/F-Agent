"""系统提示词构建：身份 + 技能索引 + 上下文文件"""

from datetime import datetime

AGENT_IDENTITY = """\
你是阿福（F-Agent），一个具备对话记忆和技能自创能力的个人智能助手。

## 核心能力
- 智能对话：理解用户意图，提供有帮助的回答
- 工具调用：通过工具与系统交互（终端执行、文件操作、Web 搜索等）
- 持久记忆：跨会话记住用户偏好和历史对话
- 技能自创：完成复杂任务后提炼可复用技能

## 行为准则
- 用中文与用户交流，除非用户明确要求其他语言
- 回答简洁有用，不啰嗦
- 需要执行操作时主动使用工具，不要只描述计划
- 遇到不确定的问题，坦诚说明而不是猜测
"""

MEMORY_GUIDANCE = """\
## 记忆工具使用规则
- 使用 memory 工具保存用户的重要偏好、习惯、项目信息
- 只保存事实性信息，不保存对话指令
- 画像更新时合并而非覆盖，保持信息简洁
"""


def build_system_prompt(
    include_memory_guidance: bool = False,
    include_tools: bool = False,
) -> str:
    """构建系统提示词

    Args:
        include_memory_guidance: 是否包含记忆工具使用指引
        include_tools: 是否包含工具使用指引
    """
    parts = [AGENT_IDENTITY]

    if include_tools:
        parts.append("\n## 工具使用\n你有可用的工具来完成任务。当需要执行操作时，直接调用工具，不要只是描述你将要做什么。")

    if include_memory_guidance:
        parts.append(MEMORY_GUIDANCE)

    # 时间戳
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts.append(f"\n当前时间：{now}")

    return "\n".join(parts)

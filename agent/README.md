# agent/ — Agent 核心层

Agent 主循环及核心控制模块。

| 模块 | 职责 |
|------|------|
| loop.py | Agent 主循环：迭代 LLM 调用 + 工具执行 + 消息管理 |
| prompt.py | 系统提示词构建：身份 + 技能 + 记忆 + 上下文文件 |
| budget.py | 迭代预算控制 + 中断信号 |

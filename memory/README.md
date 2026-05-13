# memory/ — 记忆与用户建模

跨会话记忆召回与用户画像管理。

| 模块 | 职责 |
|------|------|
| manager.py | 记忆管理器：prefetch + sync + 上下文注入 |
| user_profile.py | 用户建模：USER.md 读写 + LLM 驱动更新 |
| context_fence.py | 上下文围栏：`<memory-context>` 标签注入/剥离 |

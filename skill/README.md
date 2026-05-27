# skill/ — 技能系统

从经验自动创建技能，技能随使用自改进。

| 模块 | 职责 |
|------|------|
| loader.py | 技能加载：扫描 SKILL.md → 解析 frontmatter → 构建索引 |
| curator.py | 技能策展：自动创建 + 生命周期管理 + 自改进 |
| builtin/ | 内置技能目录，按类别组织 |

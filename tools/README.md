# tools/ — 工具系统

自注册工具集，供 LLM 调用。

| 模块 | 职责 |
|------|------|
| registry.py | 工具注册表：自注册 + AST 发现 + 调度 |
| terminal.py | 终端命令执行 |
| file_ops.py | 文件读写 + 列目录 |
| web_search.py | Web 搜索 + 网页抓取 |
| memory.py | 记忆读写/画像更新（供 LLM 调用） |
| skill.py | 技能管理（供 LLM 调用） |

## 注册方式

每个工具文件在模块顶层调用 `registry.register()`，启动时由 `registry` 通过 AST 扫描自动发现并导入。

# F-Agent 项目规范

## Git 仓库

- 项目 git 仓库根目录：`/Users/wangdeyu/Desktop/agent/F-Agent`
- 提交代码时必须 cd 到此目录，不要在父目录 `/Users/wangdeyu/Desktop/agent` 操作 git

## 环境要求

- 使用 `python3` 命令，不要使用 `python`
- Python 3.11+
- 虚拟环境：项目根目录下 `.venv/`，激活命令 `source .venv/bin/activate`
- 运行测试前需先激活虚拟环境：`source .venv/bin/activate && python3 -m pytest`
- 安装开发依赖：`source .venv/bin/activate && pip install -e ".[dev]"`

## 技术栈

| 层级 | 技术选型 |
|------|---------|
| 语言 | Python 3.11+ |
| LLM SDK | OpenAI SDK（兼容多模型） |
| CLI | prompt_toolkit + rich |
| 数据库 | SQLite（WAL + FTS5） |
| Web | FastAPI + Vite |
| 消息平台 | 按需接入 |
| 浏览器自动化 | Playwright |
| 容器化 | Docker |

## 开发原则

### 1. 三思而后行原则

当用户指出一个问题时，不要直接擅自修改，而是应该先调研分析问题的原因和真实性，然后与用户讨论修改方案，达成一致之后再采取行动。

### 2. 知识靠近代码原则

全局文档写在项目工作目录，模块文档写在模块文件夹，对函数和代码块的描述写在代码附近。

### 3. AICD 原则

- **原子性（Atomicity）**：每次更改用一个 git commit 原子化，以便更改失败时回滚
- **一致性（Consistency）**：代码更新后，必须同步更新相关的进度文档、知识文档、测试用例，自测通过才能提交
- **隔离性（Isolation）**：不同的任务实施，使用独立的进度文档记录实施进度，或者使用 git 分支隔离
- **持久性（Durability）**：跨会话的知识必须写到知识文档里

### 4. 渐进式披露原则

避免巨型文档，每个文档保证最小但完备。对于过大的文档应进行拆分，同时在 CLAUDE.md 里维护文档路由，方便按需定位。

### 5. 任务点提交原则

每完成一个任务点（实现计划中的一个具体步骤），必须主动询问用户是否需要提交 git commit，不要连续完成多个任务点后再统一提交。

## 文档路由

| 文档 | 位置 | 说明 |
|------|------|------|
| 项目目标 | `docs/GOAL.md` | 项目愿景、学习目标、实现阶段、设计原则 |
| 架构设计 | `docs/ARCHITECTURE.md` | 整体架构、模块划分、核心流程、数据存储 |
| Agent 开发 SOP | `docs/dev-sop.md` | Agent 开发工作流规范，5原则 + 9环节完整闭环 |
| 子 Agent Prompt 模板 | `docs/prompt-templates/` | 子 agent 分工的 prompt 模板（implement / explore），分配任务时读取并填充 |
| 需求对齐与设计 | `docs/superpowers/specs/` | 需求澄清结论与设计方案文档 |
| 任务规划与进度 | `docs/superpowers/plans/` | 任务分解、执行计划与进度状态 |

## 子 Agent 分工规范

开发过程中采用主 agent 统筹 + 子 agent 执行的分工模式，质量优先。所有子 agent 任务统一串行执行，不并行。

### 分工原则

| 角色 | 职责 | 适用场景 |
|------|------|---------|
| 主 agent | 规划、方案设计、任务拆分、约束编写、集成审查、进度更新 | 所有规划、协调与审查工作 |
| `general-purpose` 子 agent | 具体模块实现 + 测试编写 | 新模块开发、独立文件实现 |
| `Explore` 子 agent | 只读代码探索与信息调研 | 了解参考项目实现、搜索代码模式 |

### 任务分配流程

1. 主 agent 拆分任务，确定每个子任务的目标文件和接口契约
2. 读取对应的 prompt 模板文件，填充 `{{task_description}}`、`{{interface_contract}}`、`{{context_snapshot}}` 等变量
3. 调用 Agent 工具分配给子 agent 执行（统一串行，不并行）
4. 子 agent 返回后，主 agent 按**审查清单**逐项检查实际代码变更（不信任子 agent 的口头报告）
5. 审查不通过 → 按**回退策略**处理；审查通过 → 更新进度文档 → 询问用户是否提交 git commit

### 接口契约结构

主 agent 为每个子任务定义接口契约，最小结构如下：

- **函数签名**（必填）：`function_name(param1: Type, param2: Type) -> ReturnType`
- **后置条件**（必填）：正常返回时的保证（如"返回非空列表"）
- **前置条件**：调用方必须满足的条件（如"config 已初始化"）
- **异常约定**：什么情况抛什么异常（如"文件不存在抛 FileNotFoundError"）
- **数据流向**：输入从哪来、输出到哪去、是否有副作用

主 agent 按必要性选择填写，但函数签名和后置条件为必填项。

### 审查清单

主 agent 审查子 agent 代码变更时，逐项对照：

1. **接口兑现**：函数签名、返回值、异常是否与契约一致
2. **测试覆盖**：核心路径和边界情况是否有对应测试
3. **范围合规**：是否引入未授权的依赖、文件、或任务范围外的改动
4. **编码规范**：是否符合模板中的通用约束（先读后改、文件小巧、无过度设计等）
5. **回归风险**：是否可能影响已有功能

有一项不通过即判定偏差，按回退策略处理。全部通过则标记任务完成。

### 回退策略

| 偏差程度 | 判断标准 | 处理方式 |
|---------|---------|---------|
| 小偏差 | 接口契约正确，局部逻辑或风格问题 | 主 agent 直接修正 |
| 中偏差 | 接口契约部分偏离，但整体方向可回收 | 通知用户 → 附带审查意见重新派发给子 agent，限1次重试 |
| 大偏差 | 方向错误、架构不符、或重试仍不达标 | 通知用户 → 主 agent 接手实现，记录失败原因 |

### 任务粒度

- 粒度为**一个模块文件 + 对应测试**，如"实现 tools/terminal.py + tests/test_terminal.py"
- 不拆到单个函数级别（调度开销不值），也不大到整个子系统（上下文隔离失效）

### 不使用子 agent 的场景

- 规划和进度文档更新
- 跨模块的集成修改（如修改 loop.py 后同步改 prompt.py）
- 小改动（几行 fix）
- git commit 操作

## 参考资源

- Hermes-Agent 源码：`../hermes-agent`
- Hermes-Agent 核心文件：
  - `run_agent.py` — Agent 主循环
  - `model_tools.py` — 工具调度层
  - `tools/registry.py` — 工具注册表
  - `hermes_state.py` — 会话持久化
  - `agent/prompt_builder.py` — 提示词构建
  - `agent/context_compressor.py` — 上下文压缩
  - `agent/memory_manager.py` — 记忆管理
  - `gateway/run.py` — 消息网关

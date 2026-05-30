# F-Agent（阿福）

> 面向个人研发场景的本地 CLI 智能助手

F-Agent（阿福）是一个可运行、可扩展、可进化的个人 Agent。它通过本地 CLI 与用户交互，围绕多轮对话、工具调用、会话持久化、记忆、技能和上下文压缩构建核心闭环。

聚焦本地研发助手能力，当前已支持 CLI 常驻期间的定时 Agent prompt 调度；子 Agent 委托、MCP、Web Dashboard、多平台接入 等能力仍处于后续规划阶段。

## 核心理念

**可运行** — 一条命令启动本地 CLI，完成真实对话、工具调用和会话恢复。

**可扩展** — 工具、记忆、技能、配置、上下文压缩等能力按模块拆分，便于按需演进。

**可进化** — 通过持久记忆、技能沉淀和长上下文压缩，让 Agent 能在使用中积累经验。

## 当前能力

| 能力 | 说明 |
|------|------|
| 智能对话 | 通过 OpenAI SDK 接入兼容模型，支持 `base_url` 切换模型服务 |
| CLI 交互 | 基于 prompt_toolkit + rich，支持流式输出、历史输入和 Markdown 渲染 |
| 工具调用 | 内置终端、文件、Web、记忆、技能、MySQL、反思、定时任务等工具 |
| 命令审批 | 对高风险终端命令进行检测、阻断或交互式审批，定时任务可绑定任务级危险命令授权 |
| 定时任务 | CLI 常驻期间后台扫描到期任务，支持延迟、间隔、ISO 时间和 5 字段 cron 表达式 |
| 会话持久化 | 使用 SQLite 保存会话、消息、工具调用、统计信息、恢复状态和定时任务记录 |
| 历史搜索 | 基于 SQLite FTS5 对历史消息建立全文索引，用于相关上下文召回 |
| 记忆系统 | 维护 `USER.md`、`MEMORY.md`、`SOUL.md`、`AGENT.md` 等工作区记忆文件 |
| 上下文围栏 | 使用 `<memory-context>` 区分召回记忆和用户当前输入 |
| 上下文压缩 | 支持工具结果裁剪、结构化摘要、头尾保护和压缩状态恢复 |
| 技能系统 | 扫描 `workspace/skills/` 下的 `SKILL.md`，按需加载技能内容 |
| 技能管理 | 提供技能列表、查看、创建、编辑、删除和外部安装能力 |
| 会话命令 | 支持 `/help`、`/sessions`、`/resume`、`/stats`、`/clear`、`/quit` |

## 快速开始

```bash
# 克隆项目
git clone https://github.com/yourname/F-Agent.git
cd F-Agent

# 创建虚拟环境并安装依赖
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 创建配置文件
mkdir -p workspace
cp config.yaml.example workspace/config.yaml

# 编辑 workspace/config.yaml，填入 llm.api_key

# 启动阿福
python3 main.py
# 或使用启动脚本
./start.sh
```


## 配置说明

默认配置文件位于 `workspace/config.yaml`，可从 `config.yaml.example` 复制得到。常用配置包括：

| 配置 | 说明 |
|------|------|
| `llm.api_key` | 模型服务 API Key，必填 |
| `llm.base_url` | OpenAI 兼容接口地址 |
| `llm.model` | 模型名称 |
| `llm.context_window` | 上下文窗口大小 |
| `llm.max_iterations` | 单轮任务最大 ReAct 迭代次数 |
| `memory.prefetch_limit` | 每轮对话召回的历史消息数量 |
| `compressor.*` | 上下文压缩阈值、保护区和最小收益配置 |
| `approval.mode` | 命令审批模式，默认 `manual` |
| `cron.enabled` | 是否启动 CLI 内置定时任务调度器，默认开启 |
| `cron.tick_interval_seconds` | 定时任务后台扫描间隔，默认 60 秒 |
| `cron.grace_seconds` | 到期任务允许执行的宽限秒数，超出后标记为 missed，默认 120 秒 |
| `skills_hub.github_token` | 从 GitHub 安装技能时使用的可选 token |
| `mysql` | 可选 MySQL 只读查询配置，密码通过环境变量提供 |

## 项目结构

```text
F-Agent/
├── main.py                    # 入口：加载配置并启动 CLI
├── agent/                     # Agent 核心循环、提示词构建、预算控制
│   ├── loop.py
│   ├── prompt.py
│   └── budget.py
├── cli/                       # prompt_toolkit + rich 交互界面
│   └── interface.py
├── config/                    # YAML 配置加载与默认配置
│   └── settings.py
├── context/                   # 上下文压缩
│   └── compressor.py
├── cron/                      # 定时任务模型、解析、存储、执行器和后台调度器
├── db/                        # SQLite schema、迁移、会话读写
│   ├── schema.py
│   └── session.py
├── llm/                       # OpenAI SDK 封装
│   └── client.py
├── memory/                    # 记忆管理与上下文围栏
│   ├── manager.py
│   └── context_fence.py
├── skill/                     # 技能扫描、解析、路径处理
│   ├── loader.py
│   └── skill_utils.py
├── tools/                     # 内置工具与工具注册表
│   ├── registry.py
│   ├── terminal.py
│   ├── file_ops.py
│   ├── web_search.py
│   ├── memory.py
│   ├── skill.py
│   ├── skill_hub.py
│   ├── mysql.py
│   ├── think.py
│   ├── cron.py
│   └── approval.py
├── tests/                     # pytest 测试
├── workspace/                 # 运行时配置、数据库、日志、记忆和技能
│   ├── config.yaml            # 本地运行配置，通常由 config.yaml.example 复制生成
│   ├── state.db               # SQLite 运行时数据库，保存会话、工具调用、统计和定时任务等数据
│   ├── USER.md                # 用户画像与长期偏好
│   ├── MEMORY.md              # 长期记忆索引与内容
│   ├── SOUL.md                # Agent 自我设定与长期原则
│   ├── AGENT.md               # Agent 行为指引
│   ├── logs/                  # 运行日志
│   │   └── agent.log
│   ├── history/               # CLI 输入历史等本地历史数据
│   └── skills/                # 本地技能目录，按分类组织 SKILL.md
│       ├── .hub/              # 外部技能源安装状态与锁文件
│       │   └── lock.json
│       └── uncategorized/     # 未分类技能
```

## 测试

```bash
source .venv/bin/activate
python3 -m pytest
```

测试覆盖 Agent 主循环、CLI 命令、会话持久化、上下文压缩、记忆工具、技能系统、定时任务、工具注册与安全审批等核心模块。

## 在线文档

详细设计文档与开发指南：[F-Agent 在线文档](https://icnzw2ffzpws.feishu.cn/docx/M4vmdKKD3oQvrxx3HQZcN6qUnLg?from=from_copylink)

## 路线图能力

以下能力是后续规划，不代表当前版本已经完整实现：

- 多平台消息网关（Telegram / Discord / Web 等）。
- 子 Agent 派生、并行委托和结果汇总。
- 定时任务的独立守护进程、补跑策略、任务更新和立即运行等高级调度能力。
- MCP 协议接入。
- Web Dashboard 与 IDE 集成。
- Docker / SSH / 云沙箱等多环境执行后端。
- 语音交互和 RL 训练环境。

## 作者

邮箱：1839519776@qq.com

## License

MIT

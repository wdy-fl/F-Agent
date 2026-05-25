# F-Agent（阿福）

> 可运行、可扩展、可进化的个人智能助手

阿福是一个具备自我学习与进化能力的 AI Agent。它能记忆过往对话、从经验中提炼技能、在交互中持续成长，是你真正意义上的数字伙伴。

## 核心理念

**可运行** — 开箱即用，一条命令启动对话，无需复杂配置。

**可扩展** — 工具、模型、记忆、平台均采用插件化设计，按需接入、自由组合。

**可进化** — 闭环学习：对话产生经验 → 经验沉淀为技能 → 技能在使用中自改进 → 更强的能力反哺下一次对话。

## 能力概览

| 能力 | 说明 |
|------|------|
| 智能对话 | 接入多种 LLM，模型可随时切换 |
| 工具调用 | 内置终端执行、文件操作、Web 搜索等工具，支持 MCP 协议扩展 |
| 持久记忆 | 跨会话记忆用户偏好与历史上下文，支持全文搜索召回 |
| 技能自创 | 完成复杂任务后主动提议提炼可复用技能，渐进式披露在对话中复用 |
| 上下文压缩 | 长对话自动压缩，在有限 Token 窗口内保持连贯性 |
| 多平台接入 | 统一消息网关，同一 Agent 同时服务 CLI / Telegram / Web 等多端 |
| 并行委托 | 将子任务派生给独立 Agent 并行执行，汇总结果 |
| 定时任务 | 自然语言描述即可创建定时调度，无人值守自动执行 |

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

# 启动阿福
python3 main.py
# 或使用启动脚本（自动激活虚拟环境）
./start.sh          # macOS / Linux
./start.ps1         # Windows PowerShell
```

## 项目结构

```
F-Agent/
├── main.py              # 入口
├── agent/               # Agent 核心
│   ├── loop.py          # 主循环
│   ├── prompt.py        # 提示词构建
│   └── budget.py        # 预算控制
├── tools/               # 工具集
│   ├── registry.py      # 工具注册表
│   ├── terminal.py      # 终端执行
│   ├── file_ops.py      # 文件操作
│   ├── web_search.py    # Web 搜索
│   ├── memory.py        # 记忆读写
│   └── skill.py         # 技能管理
├── memory/              # 记忆子系统
│   ├── manager.py       # 记忆管理器
│   ├── user_profile.py  # 用户画像
│   └── context_fence.py # 上下文围栏
├── skills/              # 技能系统
│   ├── loader.py        # 技能扫描与索引
│   └── skill_utils.py   # 共享工具
├── context/             # 上下文压缩
│   └── compressor.py
├── db/                  # 会话持久化
│   ├── session.py
│   └── schema.py
├── config/              # 配置管理
│   └── settings.py
├── workspace/           # 运行时数据
│   ├── config.yaml
│   └── skills/          # 技能库
└── tests/               # 测试
```

## 技术栈

- **语言**: Python 3.11+
- **LLM**: OpenAI SDK（兼容多模型提供商）
- **CLI**: prompt_toolkit + rich
- **存储**: SQLite（WAL + FTS5 全文搜索）
- **Web**: FastAPI + Vite
- **浏览器自动化**: Playwright
- **容器化**: Docker

## 灵感来源

F-Agent 的架构设计受 [Hermes-Agent](https://github.com/nousresearch/hermes-agent) 启发，在理解其核心机制的基础上，以更简洁的方式重新实现，聚焦个人助手场景。

## License

MIT

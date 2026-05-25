# F-Agent Skills Hub 设计方案

> 技能 Hub（Skills Hub）——支持从外部源安装技能，丰富 F-Agent 的技能生态。
> 所属阶段：Phase 3 — 技能系统

## 1. 概述

### 1.1 背景

Phase 3 技能系统已支持 Agent 前台主动创建技能（`skill_manage(action='create')`），但技能来源仅有「用户自创」一种。引入 Skills Hub 后，用户可在对话中让 Agent 从 GitHub 仓库或直接 URL 安装外部技能。

### 1.2 与 Hermes-Agent Hub 的对比

Hermes-Agent 的 Hub 是一个完整的技能市场系统（3000+ 行），支持 9 种来源、3 层安全扫描、CLI + 聊天内安装、更新/卸载/审计等。F-Agent 做最小可用版本：

| 维度 | Hermes-Agent | F-Agent |
|------|-------------|---------|
| 技能来源 | 9 种（GitHub、skills.sh、ClawHub、LobeHub 等） | 2 种（GitHub、直接 URL） |
| 安全扫描 | 3 层（Skills Guard + Tirith + File Safety） | 不做 |
| search/browse | CLI + 聊天内 | 先不做 |
| 更新/卸载/审计 | 完整支持 | 先不做 |
| 入口 | CLI 命令 + `/skills` 斜杠命令 | Agent 工具（`skill_hub_install`） |
| 追踪 | lock.json + audit.log + bundled_manifest | lock.json |

### 1.3 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 技能来源 | GitHub + URL | 覆盖 90% 实用场景，openai/skills 和 anthropics/skills 已有大量高质量技能 |
| 安全扫描 | 不做 | 学习项目，安全机制后续按需追加 |
| 安装入口 | 纯 Agent 工具 | 对话中自然触发，Agent 可主动推荐技能 |
| 冲突处理 | 直接拒绝 | 简洁，用户可手动删除后再装 |
| 追踪机制 | lock.json | 记录来源信息，为后续升级/卸载预留数据基础 |
| search/browse | 不做 | MVP 用户知道自己要装什么 |

## 2. 安装流程

### 2.1 整体流程

```
用户: "帮我安装 openai/skills/skill-creator"
  ↓
Agent 调用 skill_hub_install(source="github", identifier="openai/skills/skill-creator")
  ↓
1. 解析 identifier → owner=openai, repo=skills, path=skill-creator
2. 调 GitHub Contents API 获取 skill-creator/ 目录文件列表
3. 逐文件下载 → 内存中构建 skill bundle
4. 解析 SKILL.md frontmatter 获取 name/description
5. 检查冲突：workspace/skills/ 下是否已有同名技能
6. 检查 lock.json：是否已安装
7. 写入 workspace/skills/{category}/{name}/
8. 记录 lock.json
9. 返回结果，提示"重启会话后生效"
```

### 2.2 GitHub 源

- **标识格式**：`owner/repo/path/to/skill`
- **API**：GitHub Contents API（`GET /repos/{owner}/{repo}/contents/{path}`）
- **认证**：优先使用 `skills_hub.github_token` 配置，不填则匿名访问（60 req/hr）
- **下载策略**：先获取目录文件列表，再逐文件下载内容

### 2.3 URL 源

- **标识格式**：`https://.../SKILL.md`
- **下载策略**：HTTP GET 获取 SKILL.md 正文
- **限制**：仅支持单文件技能（无 references/templates/scripts/assets 子目录）

## 3. 数据结构

### 3.1 lock.json

路径：`workspace/skills/.hub/lock.json`

```json
{
  "version": 1,
  "installed": {
    "<skill-name>": {
      "source": "github",
      "identifier": "openai/skills/skill-creator",
      "installed_at": "2026-05-25T12:00:00Z",
      "content_hash": "sha256:abc123..."
    }
  }
}
```

| 字段 | 说明 |
|------|------|
| `version` | 格式版本号 |
| `source` | 安装来源：`"github"` 或 `"url"` |
| `identifier` | 来源标识：GitHub 为 `"owner/repo/path"`，URL 为原始 URL |
| `installed_at` | 安装时间（ISO 8601） |
| `content_hash` | 所有文件内容的 SHA256，用于将来检测上游更新 |

### 3.2 配置

config.yaml 新增段：

```yaml
skills_hub:
  github_token: ""            # GitHub personal access token（可选，不填则匿名访问，60 req/hr 限制）
```

## 4. 工具设计

### 4.1 `skill_hub_install`

在 `tools/skill_hub.py` 中实现，注册到全局 registry。

**Schema：**

```json
{
  "name": "skill_hub_install",
  "description": "从 GitHub 或 URL 安装外部技能，安装后重启会话生效",
  "parameters": {
    "type": "object",
    "properties": {
      "source": {
        "type": "string",
        "description": "技能来源：github 或 url",
        "enum": ["github", "url"]
      },
      "identifier": {
        "type": "string",
        "description": "技能标识。github 格式为 owner/repo/path/to/skill，url 格式为 https://.../SKILL.md"
      },
      "name": {
        "type": "string",
        "description": "可选：覆盖 frontmatter 中的技能名称"
      },
      "category": {
        "type": "string",
        "description": "可选：指定安装分类，不填则使用 frontmatter 中的 category 或默认值"
      }
    },
    "required": ["source", "identifier"]
  }
}
```

**返回值示例（成功）：**

```json
{
  "status": "installed",
  "name": "skill-creator",
  "category": "dev",
  "path": "workspace/skills/dev/skill-creator",
  "files": ["SKILL.md", "references/api.md"],
  "note": "重启会话后生效"
}
```

**返回值示例（冲突）：**

```json
{
  "error": "技能已存在: skill-creator",
  "hint": "如需重新安装，请先手动删除该技能"
}
```

### 4.2 错误处理

| 场景 | 返回 |
|------|------|
| 技能已存在 | `{"error": "技能已存在: {name}"}` |
| GitHub API 失败 | `{"error": "GitHub API 请求失败: {status_code} {message}"}` |
| URL 请求失败 | `{"error": "URL 请求失败: {status_code}"}` |
| SKILL.md 无 name 字段 | `{"error": "SKILL.md 缺少 name 字段"}` |
| identifier 格式错误 | `{"error": "无效的 identifier 格式"}` |

## 5. 系统提示词

在 `agent/prompt.py` 的 `SKILLS_GUIDANCE` 中补充 Hub 指引：

```
### 安装外部技能
用户要求安装外部技能时，使用 skill_hub_install 工具：
- GitHub 源：skill_hub_install(source="github", identifier="owner/repo/path/to/skill")
- URL 源：skill_hub_install(source="url", identifier="https://.../SKILL.md")
安装前告知用户技能名称和来源，安装后提示重启会话生效。
```

## 6. 文件变更清单

### 新增

| 文件 | 说明 |
|------|------|
| `tools/skill_hub.py` | `skill_hub_install` 工具实现 |

### 修改

| 文件 | 变更 |
|------|------|
| `config.yaml.example` | 新增 `skills_hub` 配置段 |
| `config/settings.py` | 新增 `SkillsHubConfig` dataclass + `AppConfig` 字段 |
| `agent/prompt.py` | `SKILLS_GUIDANCE` 补充 Hub 安装指引 |
| `tools/__init__.py` | 新增 `import tools.skill_hub` |

## 7. 后续扩展

以下能力预留了数据基础（lock.json），后续按需实现：

- `skill_hub_list` — 列出所有 Hub 安装的技能
- `skill_hub_update` — 基于 content_hash 检测上游更新并升级
- `skill_hub_uninstall` — 卸载 Hub 安装的技能
- `skill_hub_search` — 搜索外部技能市场
- GitHub App 认证 — 更高 API 速率
- URL 源多文件支持 — 处理 ZIP/tarball 形式的 URL 源
- 安全扫描 — 按信任级别分级检查
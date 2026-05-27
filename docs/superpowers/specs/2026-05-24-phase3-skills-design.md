# Phase 3 技能系统设计方案

> 2026-05-24 | 需求讨论结论

## 1. 概述

Phase 3 实现技能系统的最小可用版本，Agent 从经验中创建技能并复用。

**范围限定：**
- 仅保留前台 Agent 主动创建机制（用户可见、需确认）
- 不包含内置技能和可选技能
- 不包含技能生命周期管理（stale/archived 等状态流转）
- 不包含安全扫描机制

## 2. 核心决策

| 决策点 | 结论 |
|---|---|
| 注入方式 | 渐进式披露（`<available_skills>` 索引 + `skill_view` 按需加载） |
| 工具粒度 | 统一 `skill_manage(action=...)` |
| action | `create` / `edit` / `delete` / `write_file` / `remove_file` |
| 创建触发 | 提示词引导（`SKILLS_GUIDANCE`），与 Hermes 一致 |
| 技能注入对话方式 | `skill_view` 结果作为系统消息追加 |
| 权限控制 | `skill_manage` 需要用户批准；`skills_list`/`skill_view` 自动批准 |
| 缓存策略 | 会话期间索引不变，变更后提示用户重启生效 |

## 3. 新增/修改文件

```
skill/skill_utils.py   # 新增：frontmatter 解析、名称校验、路径解析
skill/loader.py        # 新增：扫描 workspace/skills/、构建索引、格式化提示词
tools/skill.py          # 新增：skills_list / skill_view / skill_manage 三个工具
agent/prompt.py         # 修改：注入 SKILLS_GUIDANCE + <available_skills>
workspace/skills/       # 新增：运行时技能目录（Agent 自创技能存这里）
```

## 4. 技能存储

### 4.1 目录结构

```
workspace/skills/
  <category>/
    <skill-name>/
      SKILL.md          # 必需
      references/       # 可选：参考资料
      templates/        # 可选：文件模板
      scripts/          # 可选：脚本
      assets/           # 可选：附件
```

技能名（`<skill-name>`）仅含字母/数字/连字符/下划线，最长 64 字符。

### 4.2 SKILL.md 格式

YAML frontmatter + Markdown 正文：

```yaml
---
name: python-testing
description: "Use when writing Python tests. Covers pytest fixtures, mocking, and coverage."
category: software-development
tags: [python, testing, pytest]
created_at: 2025-05-13
updated_at: 2025-05-13
---
# Python Testing Skill

## When to Use
...

## Instructions
...
```

**字段说明：**

| 字段 | 必需 | 说明 |
|------|------|------|
| `name` | 是 | 唯一标识，最长 64 字符 |
| `description` | 是 | 简要描述，最长 1024 字符 |
| `category` | 是 | 分类目录名 |
| `tags` | 否 | 标签列表 |
| `created_at` | 是 | 创建日期 |
| `updated_at` | 是 | 最后更新日期 |

## 5. 工具设计

### 5.1 skills_list

用例：Agent 浏览可用技能。

```
无参数
→ [{name, description, category}]
```

直接从磁盘扫描，不依赖缓存。

### 5.2 skill_view

用例：Agent 加载技能完整内容或关联文件。

```
参数:
  name (必填): 技能名
  file_path (可选): 关联文件相对路径，如 "references/foo.md"
→ SKILL.md 正文（不含 frontmatter）或关联文件内容
```

结果作为系统消息注入对话。

### 5.3 skill_manage

用例：Agent 创建/编辑/删除技能或关联文件。**所有 action 需要用户批准。**

```
参数:
  action (必填): "create" | "edit" | "delete" | "write_file" | "remove_file"
  name (必填): 目标技能名
  content (视 action 而定): SKILL.md 全文或文件内容

action 行为:
  create      — 创建 {category}/{name}/SKILL.md，content 为含 frontmatter 的全文
  edit        — 整体替换目标技能 SKILL.md，content 为新全文
  delete      — 删除整个技能目录
  write_file  — 在技能目录下创建关联文件，content 为文件内容
  remove_file — 删除技能目录下的指定关联文件
```

执行成功后内存索引不变，Agent 告知用户"技能已保存，重启会话后生效"。

## 6. 技能加载

### 6.1 loader.py

| 函数 | 职责 |
|---|---|
| `scan_skills(root)` | 遍历 `workspace/skills/`，找到所有 SKILL.md |
| `build_index(root)` | 扫描 → 解析所有 frontmatter → `[{name, description, category, path}]` |
| `load_skill(path)` | 读取 SKILL.md，解析 frontmatter，返回完整数据 |
| `get_skills_prompt(index)` | 将索引格式化为 `<available_skills>` 文本 |

### 6.2 skill_utils.py

| 函数 | 职责 |
|---|---|
| `parse_frontmatter(content)` | 解析 YAML frontmatter → `(dict, body)` |
| `validate_skill_name(name)` | 校验名称合法性 |
| `resolve_skill_dir(root, name)` | 根据名称找到技能目录路径 |

## 7. 系统提示词注入

`agent/prompt.py` 注入两部分内容：

### 7.1 SKILLS_GUIDANCE

```
## 技能系统

- 回复前先检查 <available_skills> 索引，有相关技能则调用 skill_view(name) 加载完整指令
- 完成复杂任务（5+ 次工具调用）、克服棘手错误、发现非平凡工作流程后，用 skill_manage 保存方法
- 创建/删除前必须征求用户确认
- 使用技能时发现内容过时、不完整或错误，用 skill_manage(action='edit') 修正
- 创造新技能时，应让内容具体、可执行，避免泛泛而谈。好的技能是"配方"而非"常识"
```

### 7.2 <available_skills> 索引

按 category 分组，每项仅 name + description：

```
<available_skills>
## software-development
- python-testing: Use when writing Python tests...
- git-workflow: Use when managing git branches...

## data-science
- data-analysis: Use when analyzing CSV/JSON data...
</available_skills>
```

无技能时显示：`<available_skills>(暂无可用技能)</available_skills>`

## 8. 核心流程

```
启动时:
  loader.build_index() → prompt.py 注入 <available_skills> 到系统提示词
  索引缓存在内存，会话期间不变

对话中:
  1. Agent 看到技能索引 → 判断相关 → 调用 skill_view(name)
  2. skill_view 返回 SKILL.md 正文 → 作为系统消息注入对话
  3. Agent 遵循技能指令执行任务
  4. 完成复杂任务后 → SKILLS_GUIDANCE 触发 → Agent 提议创建技能
  5. 用户批准 → skill_manage(action="create", ...) → 提示重启生效
```

## 9. 与 Hermes-Agent 的对比

| 方面 | Hermes-Agent | F-Agent Phase 3 |
|------|-------------|-----------------|
| 创建机制 | 前台 + 后台审查分叉 + Curator | 仅前台 |
| 内置技能 | 27 个分类，大量内置 | 无 |
| 生命周期 | active → stale → archived | 无 |
| 安全扫描 | 100+ 威胁模式 | 无 |
| action | 6 个（含 patch） | 5 个（无 patch） |
| 缓存 | 二级缓存 | 会话内缓存，不变更 |
| 权限 | 提示词引导 | 权限控制 |
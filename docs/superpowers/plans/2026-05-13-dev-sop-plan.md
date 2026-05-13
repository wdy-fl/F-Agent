# Agent 开发 SOP 落地实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将已确认的设计文档落地为 `docs/dev-sop.md` 并在 CLAUDE.md 中建立文档路由

**Architecture:** 直接照搬设计文档内容，调整格式适配已有的 CLAUDE.md 风格。2 个文件变更。

**Tech Stack:** Markdown

---

### Task 1: 写入 dev-sop.md

**Files:**
- Create: `docs/dev-sop.md`

- [ ] **Step 1: 写入文件**

将设计文档中的核心原则和环节规则写入 `docs/dev-sop.md`，以项目规范风格呈现。

- [ ] **Step 2: 验证文件可读**

Run: `head -5 docs/dev-sop.md`
Expected: 显示文件标题和摘要

- [ ] **Step 3: 提交**

```bash
git add docs/dev-sop.md
git commit -m "feat: 添加 Agent 开发 SOP 文档"
```

### Task 2: 更新 CLAUDE.md 文档路由

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: 在文档路由表格新增一行**

在文档路由表格末尾添加：

```
| Agent 开发 SOP | `docs/dev-sop.md` | Agent 开发工作流规范，9 环节完整闭环 |
```

- [ ] **Step 2: 验证路由完整性**

确认 CLAUDE.md 中路由表格包含所有文档引用。

- [ ] **Step 3: 提交**

```bash
git add CLAUDE.md
git commit -m "docs: 添加 dev-sop.md 到文档路由"
```
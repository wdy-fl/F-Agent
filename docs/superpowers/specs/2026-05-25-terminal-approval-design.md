# F-Agent 终端命令审批系统设计

> 日期：2026-05-25 | 参考：Hermes-Agent `tools/approval.py`

## 1. 目标

为 F-Agent 的 `terminal` 工具增加命令审批机制，在 Agent 执行终端命令前进行安全检查。危险命令需要用户确认，灾难性命令永远阻止。

## 2. 模块划分

| 文件 | 操作 | 职责 | 预估行数 |
|------|------|------|---------|
| `tools/approval.py` | 新建 | 硬限制/危险模式匹配、`check_all_guards()` 编排、会话级审批状态、回调注册 | ~120 |
| `tools/terminal.py` | 改动 | `run_terminal()` 执行前调用审批守卫 | +10 |
| `config/settings.py` | 改动 | 新增 `ApprovalConfig` dataclass | +10 |
| `cli/interface.py` | 改动 | 注册审批回调，用 rich + prompt_toolkit 渲染审批面板 | +40 |

`AgentLoop` 和 `ToolRegistry` 不感知审批逻辑。审批模块通过回调与 CLI 层对接。

## 3. 审批流程

```
check_all_guards(command)
  │
  ├─ 1. 硬限制匹配?
  │    → 命中 → 返回 {"approved": False, "status": "hardline"}
  │
  ├─ 2. approvals.mode == "off"?
  │    → 跳过审批，返回 {"approved": True}
  │
  ├─ 3. 危险命令匹配?
  │    → 未命中 → 安全命令，返回 {"approved": True}
  │
  ├─ 4. 会话已批准?
  │    → pattern_key in _session_approved → 返回 {"approved": True}
  │
  └─ 5. 调用审批回调
       → callback(command, description, pattern_key)
       → 用户选 "session" → 写入 _session_approved
       → 返回用户选择
```

### 3.1 两级检查

| 级别 | 示例 | 用户可绕过 |
|------|------|-----------|
| **硬限制** | `rm -rf /`、`mkfs /dev/sda`、fork 炸弹、`shutdown` | **永远不能** |
| **危险** | `rm -rf <path>`、`chmod 777`、`curl URL \| sh`、`git push --force` | 审批面板确认，mode=off 可跳过 |

### 3.2 回调约定

```python
ApprovalCallback = Callable[[str, str, str], str]
# (command, description, pattern_key) -> "once" | "session" | "deny"
```

CLI 层通过 `set_approval_callback(fn)` 注入具体实现。

## 4. 审批面板 UI

使用 rich Panel 展示 + prompt_toolkit prompt 获取输入：

```
╔══════════════════════════════════════════════════════════╗
║  ⚠ 危险命令                                             ║
║                                                          ║
║  命令: rm -rf node_modules/                              ║
║  原因: 递归强制删除目录                                   ║
║                                                          ║
║  [o] 本次允许  (once)                                    ║
║  [s] 会话记住  (session)                                 ║
║  [d] 拒绝      (deny)                                    ║
╚══════════════════════════════════════════════════════════╝
```

- 输入 o/s/d 以外的按键 → 重新提示
- Esc/Ctrl+C → 等同 deny
- 回调在 AgentLoop 的 Live 上下文中同步阻塞调用，不影响 UI

## 5. 配置

```yaml
# workspace/config.yaml
approval:
  mode: manual   # "manual" | "off"
```

```python
@dataclass
class ApprovalConfig:
    mode: str = "manual"   # "manual" | "off"
```

- `manual`：危险命令弹出审批面板
- `off`：跳过所有非硬限制审批（硬限制仍生效）

不实现 smart 模式（LLM 辅助判断），CLI 场景不需要。

## 6. 审查要点

1. **接口兑现**：`check_all_guards(command: str) -> dict` 返回 `{"approved": bool, "message": str, "status": str}`
2. **测试覆盖**：硬限制阻止、危险命令审批通过/拒绝、会话记住、mode=off 跳过、安全命令直接放行
3. **范围合规**：不改 AgentLoop、不改 ToolRegistry、不改其他工具
4. **编码规范**：`tools/approval.py` < 150 行，`cli/interface.py` 新增 < 50 行

## 7. 关键不变项

- `AgentLoop` 零改动
- `ToolRegistry` 零改动
- 其他工具（file_ops、web_search 等）不受影响
- 审批仅作用于 `terminal` 工具

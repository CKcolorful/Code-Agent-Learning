# Long-Running Agent：跨 Context、跨进程、跨会话持续推进

当任务超过一个 Context Window，问题不再是“如何摘要对话”，而是：**一个随时可能终止、压缩或换执行者的 Agent，怎样在没有完整记忆的情况下继续正确工作？**

长任务必须假设模型调用、进程、网络、工具和人工交互都可能中断。可靠性来自外部持久状态、幂等执行和可验证交接，而不是让模型“记住前面发生过什么”。

## 一、先区分四种连续性

| 连续性 | 需要保留什么 | 常见误区 |
| --- | --- | --- |
| Context continuity | 当前推理需要的高价值信息 | 保存完整聊天就够了 |
| Task continuity | 目标、计划、进度、未知项 | 让摘要兼任数据库 |
| Workspace continuity | 精确文件、环境和 Git 状态 | 只记录“改过几个文件” |
| Execution continuity | 已执行副作用、审批、外部操作 | 重启后把全部工具重跑 |

Context Manager 解决第一项；Long-Running Harness 要把后面三项做成可恢复协议。

## 二、Session 不是 Task

一个 Task 可以跨多个 Session。Session 是一次有边界的执行租约：它加载 checkpoint，推进有限工作，留下 artifact，再退出或续租。

```python
@dataclass
class TaskRecord:
    task_id: str
    objective: str
    repository: str
    base_revision: str
    plan_version: int
    current_revision: str
    status: Literal["active", "blocked", "verifying", "complete", "failed"]
    acceptance_criteria: list[str]
    checkpoints: list[str]

@dataclass
class SessionRecord:
    session_id: str
    task_id: str
    started_at: str
    lease_owner: str
    lease_expires_at: str
    start_checkpoint: str
    end_checkpoint: str | None
    stop_reason: str | None
```

把 session id 当 task id，会导致新上下文无法继承任务，或旧 session 重试时重复提交副作用。

## 三、Checkpoint 应包含什么

一个可恢复 checkpoint 至少包含：

- Task 与 Acceptance Criteria；
- 结构化 Plan 和节点状态；
- 当前 Git revision、branch/worktree 和 dirty state；
- 已产生 artifact 及内容 hash；
- 最近一次有效验证报告及其绑定 revision；
- 未解决问题、失败尝试和禁止重复的路径；
- 已执行外部副作用和 idempotency key；
- Token、时间、工具和成本预算；
- 继续工作的推荐入口，而不是强制下一条命令。

```json
{
  "checkpoint_version": 4,
  "task_id": "T-184",
  "workspace_revision": "4ac7...",
  "plan_version": 3,
  "passed_nodes": ["locate", "edit-parser"],
  "ready_nodes": ["add-regression-test"],
  "unknowns": ["legacy format compatibility"],
  "verification": {"revision": "4ac7...", "status": "partial"},
  "side_effects": [{"key": "issue-comment:T-184:1", "status": "committed"}]
}
```

Checkpoint 自身要原子写入、带 schema version 和校验和。写到一半的 JSON 不能成为恢复依据。

## 四、Event Log + Snapshot

只保存最新 snapshot 很难审计“为什么变成这样”；只保存所有事件又会让恢复越来越慢。常见组合是：

```text
append-only Event Log  ----fold---->  periodic Snapshot
         │                                │
         └----------- audit/replay -------┘
```

事件示例：`PlanCreated`、`ToolRequested`、`ToolCompleted`、`PatchApplied`、`VerificationPassed`、`ApprovalGranted`、`CheckpointCreated`。

事件必须带：全局序号、时间、task/session、因果父事件、输入摘要、artifact 引用和 revision。大日志或 diff 保存为内容寻址 artifact，事件只存 hash 和位置。

恢复时：读取最近有效 snapshot，按顺序重放后续确定性事件，再核对现实工作区。不要重放会再次执行 shell、发消息或创建 PR 的命令。

## 五、恢复不是“把摘要发给模型”

恢复流程应先由 Harness 校验：

1. checkpoint schema 和 hash 有效；
2. 仓库 HEAD、dirty files 与记录一致；
3. 已完成 artifact 仍存在；
4. 验证报告仍绑定当前 revision；
5. 外部副作用状态可查询或已记录；
6. 过期 lease 已释放；
7. 预算和权限仍允许继续。

然后 Context Manager 生成 Resume Brief：

```text
目标与不可变约束
当前 revision 与已有修改
已验证完成的节点
当前 ready / blocked 节点
过去失败及原因
仍需用户决定的问题
可重新获取的 artifact 引用
```

Resume Brief 是视图，不是持久真相。模型可以质疑它，但无法直接篡改 checkpoint 中的事实。

## 六、Initializer 与 Incremental Worker

长任务的首次会话与后续会话职责不同：

### Initializer

- 验证环境能否构建和运行；
- 建立仓库地图与基线测试；
- 恢复需求、验收条件和计划；
- 创建稳定的进度 artifact；
- 不急于在环境尚未可复现时大改代码。

### Incremental Worker

- 读取 checkpoint 和当前代码，而不是相信旧叙述；
- 选择一个可在本 session 完成并验证的节点；
- 产生小而完整的增量；
- 更新测试、计划和交接信息；
- 在上下文耗尽前主动 checkpoint。

这种“换班”模型比让一个会话一直滚动压缩更容易审计和恢复。

## 七、什么是好的增量？

一个 session 的理想输出是可合并、可验证、可撤销的 vertical slice，而不是大量半成品。

好的增量通常满足：

- 对应一个明确 PlanNode；
- 修改范围可 review；
- 至少通过相关快速检查；
- 没有隐藏的临时 mock 或关闭测试；
- 下一会话无需重读全部轨迹；
- 如果未完成，半成品被明确隔离或 feature flag 保护。

“代码写了很多”不是进展。进展应以通过的 criterion、减少的未知项和可复用 artifact 衡量。

## 八、幂等性与 Exactly-Once 幻觉

崩溃可能发生在外部 API 已成功、结果尚未写入 event log 之间。分布式系统很难保证真正 exactly-once，因此工具需要：

- 客户端生成 idempotency key；
- 查询已存在结果；
- 将 `prepared` 与 `committed` 状态分开；
- 重试前先 reconcile；
- 对不可查询副作用请求人工确认。

```python
def resume_side_effect(op):
    remote = adapter.lookup(op.idempotency_key)
    if remote.exists:
        event_log.append(SideEffectReconciled(op.id, remote.id))
        return remote
    if op.risk == "high" and op.last_state == "unknown":
        raise NeedsHumanReview(op.id)
    return adapter.execute(op, idempotency_key=op.idempotency_key)
```

本地编译可以安全重跑，发布、付款、删数据、发评论不能使用同一种重试策略。

## 九、Workspace 与 Git 边界

Git 是优秀的代码快照和 diff 协议，但不是完整任务数据库。建议：

- 每个并发任务使用独立 worktree/branch；
- checkpoint 记录 HEAD 和 dirty patch hash；
- 只在 coherent increment 后创建 commit；
- 不为“保存进度”提交无法构建的垃圾状态，必要时保存私有 patch artifact；
- 恢复时先确认分支没有被用户或远端改写；
- 合并前重新验证目标 branch 的最新基线。

长期任务不能把 `git reset --hard` 当恢复工具，因为工作区可能含用户或其他 Agent 的修改。

## 十、租约、并发与脑裂

两个 worker 同时从同一 checkpoint 继续，会产生脑裂。Task Store 应提供带过期时间的 lease：

```text
acquire(task_id, worker_id, ttl)
renew(lease_id)
checkpoint(expected_version, new_state)
release(lease_id)
```

Checkpoint 写入使用 compare-and-swap：只有基于当前 state version 的 worker 能提交。过期 worker 返回时必须重新读取状态，不能覆盖新 checkpoint。

如果允许多 Agent 并发，则锁的是 PlanNode 和 workspace partition，而不是让所有 worker 共享整任务写权限。

## 十一、主动换窗时机

不要等 Context 完全耗尽才压缩。可以根据以下信号 checkpoint：

- 上下文使用超过软阈值；
- 一个 PlanNode 已完整通过；
- 即将执行高风险或昂贵步骤；
- 工具输出开始重复；
- 连续多步无进展；
- 用户输入会改变计划；
- session 达到时间预算。

过于频繁 checkpoint 会增加延迟，过晚则使摘要质量和恢复可靠性下降。应通过实验选择阈值。

## 十二、怎样评测 Long-Running Harness？

### 基础指标

- crash recovery success rate；
- 恢复后重复工具/副作用次数；
- checkpoint 创建和恢复延迟；
- state divergence rate；
- handoff 后首个有效动作所需 Token；
- 跨 session resolved rate；
- coherent increment 数量。

### 故障注入矩阵

在这些边界随机终止进程：

- 模型响应前后；
- patch 应用一半；
- 测试运行中；
- 外部副作用成功但日志未写；
- snapshot 写入中；
- lease 续租前；
- context compaction 前后。

恢复后核对：文件、事件、计划、验证和外部系统是否一致。只测“正常跨两次会话”不足以证明恢复机制可靠。

### 对照组

1. 单会话直到上下文耗尽；
2. 仅聊天摘要；
3. 结构化 checkpoint；
4. event log + snapshot + incremental worker；
5. Oracle handoff brief。

## 十三、常见误区

### 更长 Context 就不需要持久状态

长窗口仍会污染、终止和失效，而且无法表示外部副作用的确定性提交状态。

### 每一步都 Git Commit

Commit 太细会制造噪声，且不能替代任务、审批和副作用记录。

### 保存完整轨迹就能恢复

轨迹用于审计，不等于可重放程序。重新调用工具会重复副作用。

### 新 Agent 接着旧 Agent 的总结做

总结可能陈旧或遗漏。新 worker 必须先核对现实 workspace 和验证 revision。

### 长任务等于无限循环

长任务仍要有 session、budget、lease、checkpoint 和终止边界。

## 十四、从当前 Harness 演进

### v0.2：Task 与 Session 分离

增加 task id、session id、stop reason 和结构化 Resume Brief。

### v0.3：原子 Checkpoint

保存 Plan、workspace revision、verification 和 unknowns；恢复时做一致性检查。

### v0.4：Event Log 与幂等工具

为副作用添加 idempotency key 和 reconcile，快照只负责加速恢复。

### v0.5：故障注入

随机杀死 Harness 并自动恢复，以 state divergence 和重复副作用为核心指标。

## 十五、检查题

1. 为什么 Session ID 不能替代 Task ID？
2. 恢复时哪些事件可以重放，哪些只能 reconcile？
3. Git 能保存哪些状态，不能保存哪些状态？
4. 如何防止两个 worker 从同一 checkpoint 同时继续？
5. 为什么一个长 session 不如一系列 coherent increments 容易管理？

## 参考资料

- [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps)
- [NL2Repo-Bench: Long-Horizon Repository Generation](https://arxiv.org/abs/2512.12730)
- [OpenHands: An Open Platform for AI Software Developers](https://arxiv.org/abs/2407.16741)

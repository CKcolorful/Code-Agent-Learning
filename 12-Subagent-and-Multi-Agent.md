# Subagent 与 Multi-Agent：并行不是复制多个 Agent Loop

把任务交给多个 Agent 很容易，证明它们比单 Agent 更快、更准、更便宜却很难。每个 Subagent 都会消耗模型调用、工具时间和上下文；协调、重复探索、冲突修改和结果合并还会产生新的失败面。

Multi-Agent 的价值不是“更多智能”，而是：**把能独立推进、会污染主上下文或需要不同能力配置的工作分区，并通过明确协议重新汇总。**

## 一、先区分四种并行

| 模式 | 例子 | 主要风险 |
| --- | --- | --- |
| 只读探索并行 | 分别研究 API、测试、依赖 | 重复检索、结论冲突 |
| 候选并行 | 多个 Agent 独立提出 patch | 成本高、选择器过拟合 |
| 分区实现并行 | 各自修改独立模块 | 隐式共享文件和接口冲突 |
| 专业角色流水线 | explorer→implementer→reviewer | 交接损失、角色成为瓶颈 |

只读探索通常最安全；共享工作区并发写最危险。不要用同一个“spawn agent”抽象掩盖不同一致性要求。

## 二、何时值得委派

可以对候选子任务计算粗略收益：

```text
expected_gain = parallel_time_saved
              + context_pollution_avoided
              + specialization_gain
              + diversity_value
              - coordination_cost
              - duplicate_work
              - merge_risk
              - extra_tokens
```

适合委派：

- 任务能定义独立输入和验收输出；
- 多个方向可并行调查；
- 中间日志很多但最终可压缩成小 artifact；
- 需要安全、测试、性能等不同审查视角；
- 子任务失败不会破坏主任务状态。

不适合委派：

- 下一步依赖尚未做出的核心设计决定；
- 修改高度集中在同一文件或接口；
- 主 Agent 自己几分钟即可完成；
- 无法定义什么结果算完成；
- 子 Agent 必须继承整条嘈杂历史才能理解任务。

## 三、委派协议

```python
@dataclass
class Delegation:
    delegation_id: str
    parent_task_id: str
    objective: str
    scope: list[str]
    read_set: list[str]
    write_set: list[str]
    constraints: list[str]
    expected_artifacts: list[str]
    acceptance_criteria: list[str]
    budget: dict[str, int]
    base_revision: str
    return_schema: str
```

“看看这个模块”不是合格委派。Subagent 应知道目标、边界、禁止事项、基础 revision、交付格式和预算。主 Agent 应传递任务所需最小上下文，而不是复制完整对话。

返回值也不能只有自然语言总结：

```python
@dataclass
class DelegationResult:
    status: Literal["complete", "partial", "blocked", "failed"]
    claims: list[EvidenceBackedClaim]
    artifacts: list[str]
    changed_revision: str | None
    verification: list[str]
    unknowns: list[str]
    consumed_budget: dict[str, int]
```

## 四、Coordinator 的职责

主 Agent/Coordinator 不是把子结果拼接起来。它负责：

1. 从 Plan DAG 选择可独立节点；
2. 为每个节点裁剪上下文和权限；
3. 检查 read/write set 冲突；
4. 分配模型、工具、预算和 workspace；
5. 监控 lease、超时和停滞；
6. 验证返回 artifact 的 revision 与证据；
7. 解决冲突或请求重新工作；
8. 将有效结论合并进 Task State，而非直接复制聊天。

Coordinator 自身上下文应该保存决策和接口，不保存每个 worker 的所有搜索输出。

## 五、上下文隔离

Subagent 的一大价值是减少 context pollution，但前提是回传摘要有协议：

- 事实必须带路径、行号、命令或 artifact；
- 区分观察、推断、建议和未知项；
- 不回传无关尝试和完整日志；
- 关键失败要保留，避免其他 Agent 重复；
- 所有引用绑定 base revision。

主 Agent 合并前应检查不同结果是否基于同一代码版本。旧 worktree 的正确结论在新接口上可能已失效。

## 六、Workspace 隔离与合并

### 只读 Subagent

共享只读仓库即可，但缓存和构建输出仍可能写入。最好提供只读源码 + 独立临时目录。

### 写入 Subagent

使用独立 Git worktree、分支、容器或 overlay；不要让多个 Agent 共享一个 dirty working tree。

合并前检查：

- base commit 是否相同；
- changed file/write set 是否越界；
- patch 能否 clean apply；
- 公共接口是否产生语义冲突；
- 各自测试是否只在旧 base 上通过；
- 合并后的全量 Verifier 是否重新运行。

文本无冲突不等于语义无冲突。两个 patch 分别改变 producer 和 consumer，Git 可自动合并，但协议可能不一致。

## 七、调度策略

### Fan-out / Fan-in

主 Agent 把独立问题发出，等待结果后统一综合。适合代码探索和多视角 review。

### Pipeline

Explorer→Planner→Implementer→Verifier。可解释，但每次交接都会压缩信息，前一角色错误会向后传播。

### Debate / Candidate Selection

多个 Agent 独立提出方案，由确定性测试或 selector 选择。适合解空间多、验证便宜的任务；不适合验证弱而候选昂贵的任务。

### Hierarchical Team

Coordinator 再派 Coordinator。只有任务规模足够大时才值得，否则层级会吞噬上下文和预算。

## 八、专业化应包括能力和权限

角色不只是不同 system prompt。可以配置：

- 模型与推理预算；
- 只读/写入/网络权限；
- 可用工具和 MCP；
- Context Budget；
- 验收 grader；
- 最大并发和超时。

例如 Security Reviewer 可以读取 diff 和运行扫描，但不应直接推送代码；Implementer 可以写 worktree，但不能访问生产日志凭据。

## 九、失败与取消传播

子 Agent 失败要结构化区分：预算耗尽、环境失败、任务阻塞、策略拒绝、验证失败。Coordinator 决定：

- 重试同配置；
- 改用不同 Agent/模型；
- 缩小任务；
- 接受 partial artifact；
- 取消依赖节点；
- 请求用户输入。

当主任务取消时，应取消未提交工具、释放 lease 和 workspace；已产生外部副作用必须 reconcile，不能假设取消等于撤销。

## 十、一个最小调度器

```python
def schedule(plan, pool):
    ready = plan.ready_nodes()
    safe = conflict_graph.independent_set(ready)
    for node in safe[:pool.capacity]:
        delegation = build_delegation(node, current_revision())
        worker = pool.select(node.kind, node.risk)
        workspace = workspace_manager.allocate(delegation)
        worker.start(delegation, workspace)

def integrate(result):
    validate_return_schema(result)
    validate_evidence(result.claims)
    if result.changed_revision:
        patch = workspace_manager.export_patch(result.changed_revision)
        merge_queue.add(patch, base=result.base_revision)
    task_state.merge_claims(result.claims)
```

并发上限不是越高越好，应考虑 API rate limit、机器资源、测试锁和 Coordinator 的合并能力。

## 十一、怎样评测 Multi-Agent？

必须与**相同或明确不同预算**的单 Agent 比较：

- resolved rate；
- wall-clock time；
- 总 Token/API 成本；
- duplicate search/work rate；
- context returned to coordinator；
- merge conflict 与 semantic conflict；
- subtask success 和 integration success；
- main-agent idle time；
- 每解决任务成本。

### 对照实验

1. 单 Agent；
2. 单 Agent + 更高 Token 预算；
3. 两个只读 explorer；
4. explorer + implementer；
5. 多候选 patch + deterministic verifier；
6. 多写入 Agent + worktree。

如果 Multi-Agent 只比低预算单 Agent 好，却不如同成本单 Agent，就不能宣称协调本身带来增益。

### 任务切片

分别测可并行探索、多模块独立修改、高耦合修改和简单局部修复。预期 Multi-Agent 只在部分切片上占优，这是正常结论。

## 十二、常见误区

### 多 Agent 自动带来多样性

相同 prompt、模型和检索路径可能产生高度相关的失败。多样性需要不同证据源、角色或采样策略。

### 每个角色都需要一个 Agent

确定性 formatter、test runner 和 policy checker 不应为了“角色完整”改成 LLM Agent。

### 子 Agent 的总结可以直接信任

所有重要 claim 仍需证据和 revision；协调器不能把自然语言状态当事实。

### Git 无冲突就可以合并

接口和行为冲突可能不触发文本冲突，合并后必须重新验证。

### 并行只看墙钟时间

速度必须同时报告成本、质量和失败恢复，否则只是用资源换时间。

## 十三、从当前 Harness 演进

### v0.2：只读探索委派

定义 Delegation/Result schema，两个 explorer 研究互不相同的问题，主 Agent 验证引用。

### v0.3：PlanNode 调度

只对 DAG 中独立 ready 节点委派，记录预算和重复工作。

### v0.4：独立 Worktree

支持写入 Agent 导出 patch，主分支串行合并并重新验证。

### v0.5：成本匹配实验

在相同总 Token 下比较单 Agent、多 Explorer、多候选和专业角色流水线。

## 十四、检查题

1. 为什么探索并行通常比修改并行安全？
2. Delegation 为什么必须包含 base revision 和 write set？
3. 如何证明 Multi-Agent 的提升不是单纯来自更多 Token？
4. Git 自动合并后为什么仍可能有语义冲突？
5. 哪些“角色”应该用确定性程序而不是 Agent？

## 参考资料

- [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)
- [Building Effective AI Agents](https://www.anthropic.com/engineering/building-effective-agents)
- [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [OpenAI Codex documentation: Subagents](https://developers.openai.com/codex/)
- [MetaGPT: Meta Programming for Multi-Agent Collaborative Framework](https://arxiv.org/abs/2308.00352)

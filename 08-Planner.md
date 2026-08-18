# Planner：计划不是一段 Markdown，而是可执行任务状态

许多 Agent 会先输出一个编号列表，然后边做边把步骤标成完成。这种文本计划对人类沟通有用，但不自动具备依赖检查、失败恢复、证据绑定、并发调度和动态重规划能力。

Planner 的核心不是让模型“想得更久”，而是把任务从模糊目标转换为 Harness 可以管理的工作图，并在环境变化时保持目标、约束和执行状态一致。

## 一、什么时候需要 Planner？

不是每个任务都值得先规划。计划有模型调用、上下文和维护成本。

适合直接执行：

- 单文件、局部、可逆修改；
- 下一步动作由错误信息唯一决定；
- 探索成本低，修改后能快速验证。

适合显式计划：

- 多文件、多包或跨服务修改；
- 有顺序依赖、迁移或兼容阶段；
- 需求含多个验收条件；
- 某些步骤昂贵、危险或需要审批；
- 任务可能跨会话、跨 Agent；
- 需要向用户展示范围和检查点。

可先用一个简单触发器：预估修改文件数、验收条件数、风险等级、依赖深度和预计时长超过阈值时进入规划阶段。

## 二、Plan、State 和 Narrative 要分开

```text
Plan Graph     Harness 执行和校验的结构化任务图
Run State      每个节点当前状态、证据、预算和负责人
Narrative      给模型/用户阅读的简洁计划说明
```

文本 Narrative 可以随时重新生成；Plan Graph 才是系统真相。不要通过解析模型上一轮的 Markdown 勾选框恢复状态。

## 三、任务节点协议

```python
@dataclass
class AcceptanceCriterion:
    id: str
    statement: str
    verifier: str | None
    source: Literal["user", "repo", "derived"]

@dataclass
class PlanNode:
    id: str
    goal: str
    kind: Literal["explore", "edit", "verify", "approval", "handoff"]
    depends_on: list[str]
    inputs: list[str]
    expected_artifacts: list[str]
    criteria: list[str]
    risk: Literal["low", "medium", "high"]
    estimated_budget: dict[str, int]
    status: Literal["pending", "ready", "running", "passed", "failed", "blocked", "stale"]
    evidence_ids: list[str]
```

节点目标要描述可观察结果，例如“新增数据库列并提供可回滚迁移”，而不是“处理数据库”。完成状态必须由 artifact 和 criterion 的证据决定，不能由执行 Agent 自己口头宣布。

## 四、先恢复需求，再拆任务

规划失败常常不是拆分算法问题，而是缺少隐含需求。Planner 开始前应构建 Requirement Ledger：

| 字段 | 含义 |
| --- | --- |
| 显式目标 | 用户直接要求的行为 |
| 不变量 | 不能破坏的兼容性、安全或性能约束 |
| 仓库约定 | 从测试、文档、接口和相邻实现提取 |
| 假设 | 尚未证实但当前依赖的判断 |
| 未知项 | 必须探索或询问的问题 |
| 验收条件 | 如何证明需求已满足 |

如果一个未知项会导致完全不同的 API、数据模型或破坏性迁移，Planner 应先安排探索或询问节点，而不是替用户选择。

## 五、任务分解的原则

### 按可验证边界切分

好的节点执行后能产生独立证据，例如 schema 迁移可 dry-run、解析器修改有目标测试、公共 API 修改可运行契约测试。

### 按耦合度而不是文件数切分

同一个行为跨三个文件可能属于一个原子节点；两个互不相关的修改即便在同一文件，也可以是两个节点。

### 把探索和修改分开

“研究缓存实现并修好它”难以判断何时探索充分。可以拆成：定位读写路径、确认失效约定、修改实现、验证并发场景。

### 显式表示不可逆操作

发布、删除、迁移生产数据、修改权限和发送外部消息应成为 `approval` 节点，不能隐藏在普通 shell 步骤里。

### 避免过度分解

每个节点都有调度、上下文和验证成本。把一个十行修改拆成十个微步骤，会让 Agent 花更多精力维护计划而不是解决问题。

## 六、DAG 不只是展示图

依赖边应表达真实前置条件：

```text
clarify-contract
      ↓
update-schema ──→ update-model ──→ update-api
      │                    │             │
      └──────────────→ migration-test    │
                                           ↓
                                  regression-verification
```

调度器只能运行 `depends_on` 已通过的节点。上游 artifact 改变后，下游已完成节点可能变为 `stale`，需要重新验证，而不是继续保持绿色。

每条边最好注明依赖类型：

- `data`：需要上游产物；
- `decision`：依赖上游选择；
- `verification`：必须先通过某检查；
- `resource`：不能与另一个节点并发；
- `approval`：等待用户或策略授权。

## 七、动态重规划

执行环境会推翻计划：符号不存在、测试暴露隐藏约束、依赖无法安装、用户在中途修改需求。重规划流程应是：

1. 保存触发重规划的证据；
2. 标记受影响节点，而不是清空全部进度；
3. 找出从变化点可达的下游节点；
4. 保留仍有效的 artifact 和验证结果；
5. 生成最小 plan delta；
6. 对新增高风险节点重新请求审批；
7. 记录 plan version。

```python
def replan(plan, event):
    affected = dependency_graph.downstream(event.changed_artifacts)
    for node in affected:
        node.status = "stale"
    delta = planner.propose_delta(plan.snapshot(), event)
    validate_plan_delta(delta)
    return plan.apply(delta, new_version=plan.version + 1)
```

重规划不是让模型重新输出一份全新列表。全量重写会丢失已完成证据、审批和失败历史。

## 八、进度必须由证据驱动

节点状态转换可定义为：

```text
pending -> ready -> running -> passed
                    │  │
                    │  ├-> failed -> ready (retry)
                    │  └-> blocked
                    └-> stale (dependency changed)
```

`passed` 的条件是：预期 artifact 存在、节点验收条件通过、证据绑定当前 revision。模型返回“完成”只是一条 completion request。

计划更新要记录原因：

```json
{
  "node_id": "update-api",
  "from": "running",
  "to": "blocked",
  "reason": "public response schema is ambiguous",
  "evidence": ["obs-184"],
  "required_input": "whether legacy clients must remain compatible"
}
```

## 九、Planner 与 Agent Loop 的关系

Planner 不应该接管每个工具调用。合理分层是：

- Planner 决定阶段、节点、依赖和验收；
- Agent Loop 在一个节点内自主探索和执行；
- Scheduler 选择下一个 ready 节点和执行者；
- Verifier 决定节点是否通过；
- Context Manager 为当前节点投影相关计划和证据。

这样既避免把所有控制写进 prompt，也不会把 Agent 降级为只能执行固定脚本的工作流。

## 十、计划与并行

只有满足以下条件的 ready 节点才适合并发：

- 不修改重叠文件或共享生成物；
- 不依赖彼此尚未产生的决策；
- 有独立 workspace 或只读探索；
- 合并结果的协议明确；
- 并发收益超过额外 Token 和协调成本。

探索节点通常比编辑节点更容易并行。两个 Agent 同时研究不同子系统可以减少主上下文污染；两个 Agent 在共享分支修改依赖文件则可能制造难以检测的语义冲突。

## 十一、一个最小 Planner 骨架

```python
class Planner:
    def create(self, task, repo_brief) -> Plan:
        ledger = self.requirements.recover(task, repo_brief)
        draft = self.model.propose_plan(ledger)
        validate_dag(draft)
        validate_criteria_coverage(draft, ledger.criteria)
        validate_risk_nodes(draft)
        return freeze_plan(draft, version=1)

class PlanScheduler:
    def next(self, plan, resources) -> list[PlanNode]:
        ready = [n for n in plan.nodes if dependencies_passed(n, plan)]
        return select_non_conflicting(ready, resources)

    def complete(self, node, report):
        if report.revision != current_revision():
            node.status = "stale"
        elif report.criteria_passed(node.criteria):
            node.status = "passed"
            node.evidence_ids += report.evidence_ids
        else:
            node.status = "failed"
```

## 十二、怎样评测 Planner？

不要只让另一个模型给计划打“合理性”分。至少评估：

- 需求覆盖率：显式和隐式 criterion 是否有对应节点；
- 依赖正确率：执行顺序是否满足真实约束；
- 可验证率：节点是否有可运行或可检查的完成条件；
- 重规划效率：环境变化后重做了多少无关节点；
- 计划遵循率与必要偏离率；
- retry cost；
- 最终解决率、Token、墙钟时间；
- `false_progress_rate`：标记完成但无证据的节点比例。

### 实验组

1. 无显式计划，Agent 直接循环；
2. 一次性 Markdown 计划；
3. 结构化线性计划；
4. 带依赖和动态重规划的 DAG；
5. Oracle 需求与参考计划。

任务要同时包含简单局部修复和多阶段修改。否则 Planner 可能只在复杂集上获益，却被错误宣传为所有任务的默认增益。

### 故障注入

- 中途让一个工具不可用；
- 修改上游接口使下游节点陈旧；
- 增加一条用户约束；
- 让某节点验证失败两次；
- 让两个可并行节点争用同一文件；
- 在昂贵节点前触发预算不足。

## 十三、常见误区

### 步骤越详细越可靠

过细计划会快速陈旧并增加维护成本。计划应固定目标和边界，局部策略交给节点内 Loop。

### 计划一旦生成就必须遵守

环境反馈优先于旧计划。关键是受控重规划，而不是盲从或无记录偏离。

### 模型自己更新状态就够了

模型可能遗忘、重复或提前宣布完成。状态转换必须由 Harness 根据证据执行。

### Planner 等于 Subagent

Planner 产生工作图；是否分配给子 Agent 是 Scheduler 的部署决定。单 Agent 也可以执行 DAG。

### 所有未知项都问用户

能从仓库、测试和文档安全推断的应先探索；只有会实质改变结果且无法验证的选择才需要用户输入。

## 十四、从当前 Harness 演进

### v0.2：Requirement Ledger

把任务拆成目标、约束、假设、未知项和验收条件，结束前检查覆盖。

### v0.3：结构化节点状态

增加 `PlanNode`、状态转换和 evidence id，不再从聊天文本恢复进度。

### v0.4：依赖与失效传播

支持 DAG、ready 调度和 artifact 变化后的 `stale` 状态。

### v0.5：重规划实验

对任务注入环境变化，比较无计划、静态计划和 plan delta 的重复工作与成功率。

## 十五、检查题

1. 文本计划为什么不能直接作为 Harness 状态？
2. 什么样的任务不值得支付规划成本？
3. 上游 artifact 变化后，为什么下游 `passed` 节点可能变成 `stale`？
4. 如何区分合理重规划和 Agent 随意偏离计划？
5. 为什么任务应按可验证边界而不是文件数拆分？

## 参考资料

- [Building Effective AI Agents](https://www.anthropic.com/engineering/building-effective-agents)
- [SWE-RPG: Requirement Clarification, Planning, and Code Generation](https://arxiv.org/abs/2608.09072)
- [Runtime-Structured Task Decomposition for Agentic Coding Systems](https://openreview.net/forum?id=HcHZboihF5)
- [CodePlan: Repository-level Coding using LLMs and Planning](https://arxiv.org/abs/2309.12499)
- [SWE-agent](https://arxiv.org/abs/2405.15793)
- [OpenAI Codex: Introducing Codex](https://openai.com/index/introducing-codex/)

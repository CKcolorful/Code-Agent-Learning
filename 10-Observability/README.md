# Observability：看见 Agent 为什么成功、为什么失败

普通应用通常观察请求、日志、延迟和错误；Code Agent 还要观察一个更难的问题：**在多轮模型决策、工具调用、工作区变化和验证之间，哪一步让轨迹偏离了正确方向？**

只保存终端文本无法稳定比较版本；只看最终 patch 会把定位、计划、路由和环境失败都压成“任务没通过”。Observability 的目标，是建立一条从任务到证据的因果链，让失败可以定位、运行可以重放、成本可以归因、安全事件可以审计。

## 一、Log、Event、Span、Trace、Trajectory

| 概念 | 用途 |
| --- | --- |
| Log | 人类可读诊断文本 |
| Event | 某个离散事实，带结构化字段 |
| Span | 有开始、结束和父子关系的耗时操作 |
| Trace | 一次端到端运行的 span/event 集合 |
| Trajectory | 模型观察、决策、动作、环境变化的语义序列 |

Trace 回答系统发生了什么；Trajectory 还用于分析 Agent 为什么选择这条路径。两者可以共享 ID，但不要把完整 Chain-of-Thought 当成可观测性前提。工具选择、参数、结果、状态转换和简洁决策摘要已经能支持大量诊断。

## 二、统一事件信封

```python
@dataclass
class AgentEvent:
    event_id: str
    trace_id: str
    span_id: str
    parent_span_id: str | None
    task_id: str
    session_id: str
    sequence: int
    timestamp: str
    event_type: str
    attributes: dict
    artifact_refs: list[str]
    schema_version: int
```

所有模块都发事件，但不自创互不兼容格式：

- Loop：step、phase、stop reason、progress；
- Context：输入 Token、裁剪、压缩、命中 artifact；
- Router：工具候选、schema/policy 决策、批准；
- Executor：命令、环境指纹、exit code、资源使用；
- Editing：before/after hash、diff、冲突；
- Verifier：criterion、检查命令、报告 revision；
- Planner：plan version、状态转换、重规划；
- Security：网络、凭据、越权和注入信号。

## 三、一次 Agent Run 的 Span 树

```text
agent.run
├── context.assemble
├── model.generate
│   ├── provider.request
│   └── output.parse
├── tool.route
│   ├── schema.validate
│   ├── policy.evaluate
│   └── approval.wait
├── tool.execute
│   ├── sandbox.start
│   └── artifact.capture
├── state.update
└── verifier.run
    ├── targeted.tests
    └── regression.tests
```

有了父子关系，才能回答 Token 花在探索还是修复、延迟来自模型还是测试、审批等待是否被误算为执行时间。

## 四、Artifact 必须内容寻址

不要把所有命令输出、diff、截图和测试报告塞进 event attributes。使用 artifact store：

```json
{
  "artifact_id": "sha256:...",
  "kind": "command-output",
  "mime_type": "text/plain",
  "size": 48392,
  "redaction": "secrets-v2",
  "retention_class": "debug-30d"
}
```

事件保存摘要、截断标记和 artifact ref。内容寻址可以去重，并证明 Verifier 阅读的是哪一份输出。敏感 artifact 要分级、加密和限制访问，不能因为“调试方便”永久保存用户源码与凭据。

## 五、Workspace 状态也是遥测

每个写操作和验证点应记录：

- Git HEAD、branch/worktree；
- dirty file 集合；
- patch hash；
- 目标文件 before/after hash；
- 环境镜像、依赖锁和测试命令；
- verifier report revision。

否则看到“测试通过”也无法判断测试是在最新 patch、旧工作区还是另一个容器上运行。

## 六、Token、成本和延迟归因

聚合总 Token 不足以优化 Harness。至少拆分：

- 固定 system/instruction；
- 工具 schema；
- 仓库代码与检索结果；
- 历史消息与摘要；
- 模型输出；
- cache read/write；
- 主 Agent 与各 Subagent；
- 重试和重复查询。

延迟也要区分模型队列、生成、工具运行、sandbox 启动、测试、网络和等待批准。只有按 phase 归因，才知道该优化 prompt、缓存、并行还是测试选择。

## 七、从“看日志”到轨迹诊断

建议建立失败分类器，但分类依据来自证据：

```text
requirement_miss     遗漏或误解验收条件
localization_error   未读取关键区域或改错文件
planning_error       依赖/顺序/范围错误
tool_error           名称、参数、结果解释错误
edit_protocol_error  patch 未应用或冲突处理错误
environment_error    依赖、构建、sandbox 或 flaky infra
verification_error   验证不足、过期或 grader 错误
security_block       策略正确阻止或攻击得逞
budget_exhausted     未在预算内完成
```

允许一条轨迹有多个标签，并记录“首个致命偏离点”。最终失败可能发生在测试，但根因可能是早期漏读接口契约。

## 八、Replay 的三个层级

### 1. UI Replay

按时间展示模型消息、工具、diff 和验证，适合人工审查，不重新执行。

### 2. Deterministic Component Replay

固定模型输出，重新运行 parser、router、policy、context budgeter 或 verifier，适合回归测试确定性组件。

### 3. Counterfactual Replay

从某个 checkpoint 更换模型、prompt、工具描述或检索策略继续运行，用于 A/B。它不是原轨迹的确定重放，必须创建新的 trial id 并记录分叉点。

禁止默认重放外部副作用。Replay 环境应使用 mock、sandbox 或只读 adapter。

## 九、隐私和最小收集

Agent 遥测可能包含源码、用户 prompt、环境变量、终端输出、客户数据和密钥。设计原则：

- 默认记录长度、hash、类型而非完整内容；
- prompt 内容显式 opt-in；
- 写入前 secrets redaction；
- 区分运营指标、调试 artifact 和安全审计的保留期；
- 基于角色限制源码与 prompt 访问；
- 支持用户删除和租户隔离；
- 不把 Chain-of-Thought 当必需遥测。

Redaction 本身也要测试。仅匹配 `API_KEY=` 无法覆盖 token、连接串、证书和命令输出中的隐式秘密。

## 十、指标面板应该回答问题

### 可靠性

- resolved rate、false success rate；
- tool failure / retry / timeout；
- no-progress steps；
- crash recovery；
- verifier stale report。

### 效率

- Token/cost/time per resolved task；
- time to first relevant file；
- time to first valid patch；
- context compression ratio；
- sandbox startup 与 test time。

### 修改质量

- changed files、diff size、unrelated change ratio；
- rollback / conflict；
- targeted vs regression test coverage。

### 安全

- approval requested/granted/denied；
- sandbox denial；
- network allow/deny；
- MCP/tool 来源；
- secret redaction；
- destructive action attempts。

指标要按模型、Harness 版本、仓库、语言、任务类型和风险分层。只看全局平均数会掩盖某类任务退化。

## 十一、OpenTelemetry 如何落地

可以把标准基础设施事件映射到 OTel：run 为 trace，模型和工具为 span，Token/结果为 attributes 和 metrics。业务 artifact 仍由专用 store 管理。

```python
with tracer.start_as_current_span("tool.execute") as span:
    span.set_attribute("agent.tool.name", request.name)
    span.set_attribute("agent.tool.risk", request.risk)
    result = executor.run(request)
    span.set_attribute("agent.tool.success", result.ok)
    span.set_attribute("agent.tool.duration_ms", result.duration_ms)
    span.add_event("artifact.created", {"artifact_id": result.output_ref})
```

注意高基数字段：完整 path、task id、错误文本不适合作为 metrics label，可保留在 log/event。否则监控成本会失控。

## 十二、怎样测试 Observability？

### Schema Tests

每种事件验证必填字段、版本兼容、父子关系和序号单调性。

### Correlation Tests

从 Verifier 报告能反查 patch、命令、环境和 task；从工具调用能找到审批和策略决策。

### Failure Injection

模型超时、工具异常、进程崩溃、artifact 上传失败时，trace 仍应闭合并保存明确状态，而不是静默缺尾。

### Redaction Tests

在 prompt、环境、URL、stdout、diff 中注入假密钥，检查存储和导出端都不泄漏。

### Replay Tests

固定一条轨迹重跑确定性组件，输出应一致；对有副作用工具应证明不会再次执行。

## 十三、常见误区

### 把 stdout 当 Event Store

文本日志缺 schema、关联 ID 和版本，很难稳定查询或比较。

### 所有内容全部保存

这会造成隐私、成本和安全问题。观测能力来自结构和关联，不来自无限收集。

### 只在失败时打开详细日志

没有成功基线就无法判断失败轨迹哪里异常；临时开启也可能改变系统行为。

### Dashboard 指标越多越好

指标应对应可执行问题。无人负责、没有阈值和处置动作的图表只是噪声。

### Observability 等于 Evaluation

Observability 提供事实和诊断；Evaluation 定义任务、trial、grader 和统计比较。

## 十四、从当前 Harness 演进

### v0.2：统一 JSONL 事件

加入 trace/task/session/sequence、event type 和 revision，stdout 只做展示。

### v0.3：Span 与 Artifact Store

为模型、工具、编辑和验证建立父子 span，大输出内容寻址保存。

### v0.4：轨迹查看与失败分类

实现时间线、diff、Token 和验证证据视图，人工标注首个致命偏离点。

### v0.5：OTel 与回归告警

导出低敏结构事件，按 Harness 版本比较成本、成功率和安全信号。

## 十五、检查题

1. Trace 和 Trajectory 的区别是什么？
2. 为什么测试通过事件必须绑定 workspace revision？
3. 哪些字段适合 metrics label，哪些只适合 event？
4. Counterfactual Replay 为什么必须创建新 trial？
5. 怎样在可调试性和源码隐私之间做最小收集？

## 参考资料

- [OpenTelemetry Specification](https://opentelemetry.io/docs/specs/)
- [Running Codex safely at OpenAI](https://openai.com/index/running-codex-safely/)
- [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- [OpenAI Agents SDK: Tracing](https://openai.github.io/openai-agents-python/tracing/)
- [OpenHands: An Open Platform for AI Software Developers](https://arxiv.org/abs/2407.16741)

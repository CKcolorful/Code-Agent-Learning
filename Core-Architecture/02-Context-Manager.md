# Context Manager：有限窗口里的信息调度系统

> Context Manager 的任务不是“尽量塞入更多内容”，而是在每一步把最能改变下一步决策的信息放到模型面前，同时保证目标、约束和执行证据不会在压缩中被改写。

## 一、上下文长，不代表可以不管理

最小 Harness 把所有消息线性追加：

```python
messages = [system_prompt, user_task]

messages.append(model_output)
messages.append(tool_result)
```

对一个六步的小 bug，这足够好。但真实仓库很快会产生：

- 几百个文件名；
- 多次代码搜索结果；
- 大段源码；
- 安装和构建日志；
- 重复的测试失败；
- 已经过时的假设；
- 修改前和修改后的不同文件版本；
- 工具 Schema、项目规则和技能说明。

如果全部保留，问题不只是超过模型窗口。即使文本仍放得下，模型也不一定能同等利用每个位置的信息。[Lost in the Middle](https://arxiv.org/abs/2307.03172) 的实验说明，相关信息在长输入中的位置会显著影响检索表现。因此，上下文管理同时是容量问题、相关性问题、版本一致性问题和注意力分配问题。

[Claude Code 的公开文档](https://code.claude.com/docs/en/how-claude-code-works)描述了一种分层处理：先清理旧工具输出，再在需要时总结对话；项目根指令和记忆从磁盘重新注入。Codex 也公开提供自动压缩和 `/compact`，并建议把持久规则放在 `AGENTS.md`，而不是依赖早期聊天记录。值得学习的不是某个压缩阈值，而是原则：**不同来源的信息有不同生命周期，不能统一当聊天文本处理。**

## 二、Context 不等于 Messages

一个更准确的划分是：

```text
Context = Instructions
        + Task State
        + Selected Evidence
        + Recent Interaction
        + Tool Interface
        + Memory
```

它们的可靠性和生命周期不同：

| 类型 | 示例 | 生命周期 | 是否可以摘要 |
| --- | --- | --- | --- |
| 系统协议 | 权限、完成协议、输出格式 | 整个运行 | 原则上不应由模型摘要 |
| 项目指令 | 构建命令、编码规范 | 项目级 | 可按路径选择，不应改写含义 |
| 用户目标 | issue、验收标准 | 整个任务 | 保留原文或受控结构化版本 |
| 任务状态 | 当前假设、待办、修改文件 | 随步骤更新 | 可以重建，但必须有 Schema |
| 执行证据 | 退出码、diff、测试失败 | 与工作区版本绑定 | 大输出可裁剪，事实字段不可改写 |
| 最近交互 | 模型上一轮解释、工具错误 | 短期 | 可压缩或淘汰 |
| 长期记忆 | 项目惯例、历史调试经验 | 跨会话 | 按需检索，必须标注来源与时效 |
| 工具定义 | 名称、描述、Schema | 能力级 | 可以延迟加载，不应自然语言压缩 Schema |

如果系统只保存 `messages`，就很难回答：某条“测试已通过”是模型说的，还是终端真的返回了退出码 0？它对应修改前还是修改后的工作区？压缩以后还可信么？

## 三、三个必须分开的存储层

### 1. Event Store：不可变事实

记录发生过什么：模型请求、工具调用、文件变更、退出码、审批和验证结果。事件追加后不修改，大输出单独存 artifact，并保存哈希。

```python
ToolCompleted(
    call_id="call_17",
    tool="run_command",
    exit_code=1,
    stdout_artifact="artifacts/call_17.stdout",
    stderr_artifact="artifacts/call_17.stderr",
    workspace_revision="diff:8f31...",
)
```

### 2. Task State：Harness 的结构化工作记忆

记录当前仍然有效的状态：

```yaml
goal: 修复 token 过期单位错误
acceptance_criteria:
  - token 在创建 30 分钟后过期
phase: verify
hypotheses:
  active: timedelta 使用了错误单位
  rejected:
    - 常量值配置错误
files:
  inspected: [app.py, test_app.py]
  modified: [app.py]
verification:
  workspace_revision: "diff:8f31..."
  command: pytest -q
  status: failed
  failing_tests: [test_token_expires_after_thirty_minutes]
next_actions:
  - 检查测试使用的 timezone
```

它由确定性 reducer 和受约束的模型摘要共同维护，不能把全部更新权交给模型。

### 3. Prompt View：本轮模型真正看到的内容

Context Manager 根据预算和当前阶段，从前两层生成临时视图。这个视图可以丢弃，下一轮重新构建：

```text
[system protocol]
[task and acceptance criteria]
[project instructions relevant to app.py]
[structured task state]
[latest relevant code excerpts]
[latest test failure]
[recent two turns]
[currently available tool schemas]
```

这种分层让“压缩上下文”不再等于“删除历史事实”。被移出 Prompt 的证据仍在 Event Store 中，需要时可以重新加载。

## 四、上下文预算应该怎样分配？

假设模型窗口为 `W`，不能直接把 `W` 全部用作输入。需要为模型输出和安全余量预留空间：

```text
input_budget = W - reserved_output - safety_margin
```

输入预算再按类别分配。下面只是一种起始策略：

| 区域 | 初始占比 | 说明 |
| --- | ---: | --- |
| 系统和安全协议 | 8% | 小而稳定，不能被动态内容覆盖 |
| 任务与验收条件 | 7% | 保留原始语义 |
| 项目指令 | 5% | 只加载当前路径相关规则 |
| 工具定义 | 10% | 工具多时改为按需发现 |
| 结构化任务状态 | 10% | 目标、假设、文件、验证状态 |
| 代码与文档证据 | 35% | 当前阶段最相关的仓库内容 |
| 最近工具结果 | 15% | 优先保留失败尾部和退出码 |
| 最近对话 | 5% | 保证局部连贯性 |
| 余量 | 5% | 防止估算误差和突然的大结果 |

固定比例不是最终答案。探索阶段需要更多搜索与代码；编辑阶段需要目标文件和调用关系；验证阶段需要 diff、测试和需求。Context Manager 应基于 phase 动态调整，而不是所有回合使用同一模板。

## 五、选择信息：相关性之外还有五个维度

一个 observation 是否进入本轮上下文，可以计算近似价值：

```text
value(x) = relevance
         × reliability
         × freshness
         × actionability
         × uniqueness
         / token_cost
```

- **相关性**：是否与当前目标、文件或失败测试有关；
- **可靠性**：来自真实执行、静态分析、用户还是模型猜测；
- **新鲜度**：是否对应当前工作区 revision；
- **可行动性**：能否直接支持下一步搜索、编辑或验证；
- **独特性**：是否只是已有信息的重复；
- **Token 成本**：占用多少窗口。

这解释了为什么“最近 200 行日志”不总比“失败测试名 + 末尾堆栈 + 退出码”更有价值；也解释了为什么旧的测试通过记录在代码修改后必须降为过期，而不是继续作为完成证据。

## 六、代码上下文：不要默认做全仓库 RAG

Code Agent 的检索对象不是静态文档。符号、调用关系、测试和未提交 diff 会持续变化。一个实用的分层检索顺序是：

### 第 0 层：仓库先验

- 根目录文件；
- README、项目指令；
- 构建配置；
- Git 状态；
- 语言和包管理器。

### 第 1 层：词法定位

- issue 中的报错文本；
- 函数、类、配置键；
- 测试名；
- `rg`/grep 搜索。

词法搜索便宜、可解释，而且对于精确符号常常优于 embedding。

### 第 2 层：结构定位

- definition/reference；
- import 和调用关系；
- AST 或 LSP；
- 测试与实现的邻接关系。

### 第 3 层：语义检索

当任务描述和代码词汇不一致、仓库巨大或需要查找类似实现时，再使用 embedding、摘要索引或 repo map。

### 第 4 层：执行驱动检索

通过失败堆栈、coverage、日志和动态调用路径，把注意力缩到真实执行相关区域。

“先把仓库所有文件嵌入向量库”不是默认最佳方案。索引会过期，切块可能破坏代码结构，还会把大量语义相似但任务无关的内容送进上下文。检索策略应当可追踪：每段代码为什么被选中、对应哪个查询、来自哪个 revision。

## 七、Observation 应该怎样压缩？

不同工具需要不同压缩器。

### 文件树

保留：顶层结构、目标目录、文件类型统计、被忽略目录。不要列出 `node_modules` 的每个文件。

### 搜索结果

按文件聚类，保留匹配行及小范围上下文；相同生成文件或 vendor 结果降权；记录“总命中数”和“展示命中数”。

### 源文件

优先保留完整语义单元，而不是机械字符截断：函数、类、相邻 imports、相关测试。超长函数再按行范围切分，并带路径、行号和文件哈希。

### 命令输出

结构化提取：

```yaml
command: pytest -q
exit_code: 1
duration_ms: 842
summary: 1 failed, 12 passed
failures:
  - test: tests/test_token.py::test_expiry
    message: expected 30 minutes, got 30 seconds
tail_artifact: artifacts/call_17.stderr
truncated_chars: 18240
```

原始日志仍存 artifact。模型需要更多细节时再请求特定区间。

### Diff

保留文件级统计和当前相关 hunk；不要同时保留修改前完整文件、修改后完整文件以及完整 diff。三份内容高度重复。

## 八、Compaction：总结什么，绝不能总结什么？

压缩不是生成一段“到目前为止我们做了很多工作”的散文。一个可恢复摘要需要固定 Schema：

```python
class CompactState(BaseModel):
    goal: str
    acceptance_criteria: list[str]
    confirmed_facts: list[FactRef]
    active_hypothesis: str | None
    rejected_hypotheses: list[str]
    inspected_files: list[FileRef]
    modified_files: list[FileRef]
    latest_verification: VerificationRef | None
    unresolved_questions: list[str]
    next_actions: list[str]
```

### 必须保留原始引用的内容

- 用户原始任务和明确约束；
- 安全与权限协议；
- 当前 diff 或它的可重取引用；
- 命令、退出码、测试名；
- 错误消息中的关键字面量；
- 审批结果；
- artifact 哈希与 workspace revision。

### 可以由模型摘要的内容

- 探索过程；
- 已否定假设的理由；
- 多次相似搜索的合并结果；
- 长日志的错误主题；
- 下一步计划。

### 压缩后的验证

不要直接相信摘要。可以运行确定性检查：

- 摘要引用的文件是否存在；
- 修改文件集合是否与 Git diff 一致；
- 最新验证 revision 是否等于当前 revision；
- 引用的事件 ID 是否存在；
- 摘要是否遗漏用户 acceptance criteria；
- 是否把失败状态写成成功。

摘要是索引，不是证据本身。

## 九、什么时候触发压缩？

只按 Token 百分比触发太迟，也可能造成反复压缩。建议组合信号：

```text
token_pressure      上下文接近预算
phase_transition    从探索进入编辑或从编辑进入验证
redundancy_pressure 重复观察过多
staleness_pressure  大量证据已因工作区变化过期
checkpoint_event    即将暂停、转交或恢复
```

还要避免 compaction thrashing：刚压缩完，模型又读入同一巨型文件或日志，窗口立即再次爆满。检测方式包括：

- 短时间连续压缩次数；
- 压缩前后 Token 减少比例；
- 最大单条 observation 占比；
- 同一 artifact 被重复全量加载次数。

解决方法不是继续压缩，而是改变 observation 接口：分页读取、结构化错误提取、artifact 查询和按需工具发现。

## 十、Memory、Context 和 State 不要混为一谈

| 概念 | 回答的问题 | 典型内容 |
| --- | --- | --- |
| Context | 模型这一轮看见什么？ | 当前 Prompt View |
| State | 系统现在处于什么状态？ | phase、diff、预算、验证结果 |
| Memory | 未来任务可能复用什么？ | 项目惯例、调试经验、用户偏好 |

长期记忆有两个额外风险：

1. **过时**：上个月的构建命令已经失效；
2. **污染**：一次任务中的偶然结论被当作项目规则。

因此 memory item 至少要带：

```python
MemoryItem(
    content="integration tests require Redis",
    scope="repo",
    source_event="run_42:tool_9",
    created_at="...",
    last_verified_at="...",
    confidence="observed",
    expires_at=None,
)
```

必须执行的团队规则应放在版本控制中的项目指令，而不是只存在自动记忆里。Claude Code 的 `CLAUDE.md` 与 Codex 的 `AGENTS.md` 都体现了这一分工：持久规则由人维护，记忆只是辅助召回层。

## 十一、一个可实现的 Context Manager 接口

```python
class ContextManager(Protocol):
    def build(self, state: RunState) -> ModelInput:
        """在预算内生成本轮模型视图。"""

    def ingest(self, event: RunEvent) -> None:
        """把新事件归档、索引并更新派生状态。"""

    def compact(self, state: RunState, reason: str) -> CompactState:
        """生成可校验的结构化摘要。"""

    def retrieve(self, query: ContextQuery) -> list[EvidenceRef]:
        """按目标、路径、符号、事件和 revision 检索证据。"""
```

一个简单的 `build` 流程：

```python
def build(state: RunState) -> ModelInput:
    budget = token_budget.for_phase(state.phase)
    blocks = [
        immutable_system_protocol(),
        original_task(state),
        relevant_project_rules(state.focus_paths),
        render_task_state(state),
    ]

    candidates = retrieve_candidates(state)
    candidates = discard_stale(candidates, state.workspace_revision)
    candidates = deduplicate(candidates)
    candidates = rank_by_value_per_token(candidates, state)
    blocks += pack_until_budget(candidates, budget.remaining(blocks))

    return ModelInput(blocks=blocks, manifest=build_manifest(blocks))
```

`manifest` 很有价值：它记录本轮究竟给模型看了什么、每个 block 占多少 Token、为什么入选。没有 manifest，就无法判断失败来自模型能力还是错误的上下文选择。

## 十二、怎样评测 Context Manager？

### 实验 A：三种历史策略

固定模型、Loop 和工具，在 10～30 个需要至少两轮修改的任务上比较：

```text
A 组：完整线性历史
B 组：超过阈值后删除最旧工具输出
C 组：结构化状态 + 分类型裁剪 + artifact 按需恢复
```

记录：

- 成功率；
- 输入 Token；
- 重复读取次数；
- 忘记验收条件的比例；
- 重复已失败方案的比例；
- 压缩后恢复成功率；
- false success。

### 实验 B：关键信息位置

把同一条验收条件或失败原因分别放在上下文开头、中间和末尾，观察模型是否稳定使用。然后比较是否把它提升到结构化任务状态区。

### 实验 C：过期证据

让测试先通过，再修改相关文件，使旧结果失效。检查 Context Manager 是否仍把旧 `exit_code=0` 当作当前证据。这是很多“声称通过但实际失败”的根源。

### 实验 D：检索消融

比较：

- 只用文件树和 grep；
- grep + LSP/调用图；
- grep + embedding；
- 执行堆栈驱动检索。

不要只看最终成功率，还要统计目标文件进入上下文的召回率、首次定位步数和无关代码 Token。

## 十三、常见误区

### 误区 1：上下文越长，Agent 越强

长窗口提供容量，不提供自动的信息组织。噪声、冲突版本和位置偏差仍会降低有效利用率。

### 误区 2：摘要可以替代原始日志

摘要会遗漏字面量、顺序和反例。正确做法是摘要负责导航，原始 artifact 负责证据与复查。

### 误区 3：向量检索就是 Context Manager

embedding 只是候选召回方式之一。预算、版本、可靠性、去重、压缩和生命周期才构成完整上下文管理。

### 误区 4：Memory 是无限扩展的 Prompt

无选择地加载记忆会制造新的上下文污染。记忆需要作用域、来源、时效和按需检索。

### 误区 5：工具输出按统一字符数截断就够了

源码、测试、文件树和命令日志的信息分布不同。统一截断会删除最重要的结构；至少应按类型处理，并保留退出码、尾部错误和截断计数。

## 十四、从当前 Harness 演进的最小改动

1. 给每次工具结果增加 `kind`、`exit_code`、`artifact_path`、`workspace_revision`；
2. 把“目标、已修改文件、最近验证、下一步”维护为独立结构；
3. 为文件、搜索、命令和 diff 分别实现压缩器；
4. 上下文达到阈值时生成结构化摘要，并用 Git diff 与事件 ID 校验；
5. 为每轮保存 context manifest 和估算 Token；
6. 先做 grep/LSP/执行反馈的分层检索，再考虑全仓库向量索引。

## 十五、检查题

1. 为什么一条测试通过记录在代码修改后应被视为过期？
2. 哪些信息可以由模型摘要，哪些必须保存原始引用？
3. Context、State 和 Memory 分别由谁维护，生命周期有什么不同？
4. 为什么给日志做“头尾截断”仍然不如结构化解析？
5. 如何证明一次失败来自 Context Manager，而不是模型能力不足？

## 参考资料

- [Lost in the Middle: How Language Models Use Long Contexts](https://arxiv.org/abs/2307.03172)
- [Claude Code: How Claude Code works](https://code.claude.com/docs/en/how-claude-code-works)
- [Claude Code: Explore the context window](https://code.claude.com/docs/en/context-window)
- [Claude Code: Scale to many tools with tool search](https://code.claude.com/docs/en/agent-sdk/tool-search)
- [Codex: Custom instructions with AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
- [Codex: Memories](https://learn.chatgpt.com/docs/customization/memories)
- [SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering](https://arxiv.org/abs/2405.15793)

# Repository Intelligence：Code Agent 如何理解陌生仓库

前五篇解决了 Agent 如何循环、管理上下文、调用工具、安全执行和验证结果，但这些能力仍然是通用 Agent 的基础设施。Code Agent 真正特殊的第一道门槛是：**在尚未理解仓库时，找出任务相关的最小代码切片，并形成足以指导修改的结构化解释。**

这不是“给仓库做一次向量检索”。真实任务里的线索会分散在 Issue、异常栈、测试、配置、接口声明、调用方和历史约定中。文件级定位看似正确，行级上下文仍可能漏掉关键约束；找到实现位置，也不等于理解修改影响面。

## 一、模块边界：探索不是把文件塞进 Context

Repository Intelligence 接收任务和仓库快照，输出带证据的 `RepositoryBrief`：

```python
@dataclass
class CodeRegion:
    path: str
    start_line: int
    end_line: int
    symbol: str | None
    role: Literal["definition", "caller", "test", "config", "contract"]
    relevance: float
    evidence: list[str]

@dataclass
class RepositoryBrief:
    repository_revision: str
    task_hypotheses: list[str]
    relevant_regions: list[CodeRegion]
    dependency_edges: list[tuple[str, str, str]]
    conventions: list[str]
    unknowns: list[str]
    suggested_checks: list[str]
```

它不负责：

- 决定最终 patch 内容，那是 Editing Engine 的职责；
- 把全部搜索结果永久留在 prompt，那是 Context Manager 的职责；
- 判断任务是否完成，那是 Verifier 的职责；
- 用自然语言猜测代码关系而不保留来源位置。

关键设计是让每条结论都能回到 `revision + path + lines`。没有出处的“仓库使用工厂模式”只是暂时假设，不能成为强约束。

## 二、理解仓库的六层信号

### 1. 目录和构建拓扑

先识别语言、包管理器、入口、测试目录、生成代码、工作区和部署边界。目录名只是弱信号，应结合构建文件、模块声明和 CI 命令。

输出至少包括：

- 可编辑源码与生成物的边界；
- 单仓、多包或多服务结构；
- 测试与实现的映射习惯；
- 仓库级、子目录级指令文件；
- 可能影响验证环境的锁文件和配置。

### 2. 词法搜索

`rg`、文件名搜索和错误文本搜索便宜、可解释、召回稳定。它们特别适合：

- 精确异常消息；
- 配置键、路由、环境变量；
- 用户给出的类名、函数名；
- 测试断言和公开 API。

词法搜索的问题是同义词、封装层和动态生成。它应当是探索起点，而不是唯一检索器。

### 3. 符号和语法结构

AST、Tree-sitter、LSP 或语言编译器可以回答文本搜索难以可靠回答的问题：

- 符号定义在哪里；
- 哪些地方引用该符号；
- 类、函数、类型和模块的包含关系；
- 修改签名会影响哪些调用点；
- 当前片段是不是注释、字符串或真实语法节点。

符号索引必须绑定具体提交和编译配置。条件编译、宏、动态导入、反射和代码生成会让“引用图”不完整，因此图边也应携带来源与置信度。

### 4. 行为证据

测试、异常栈、覆盖率、运行日志和最小复现提供动态依赖。静态图说“可能调用”，运行轨迹说“这次确实经过”。

行为探针要尽量窄：

```text
复现失败 -> 捕获 stack trace -> 定位首个仓库帧
          -> 读取相邻定义与调用方 -> 运行目标测试带覆盖率
          -> 把新增执行区域加入候选集
```

不要为了理解一个函数先跑全量测试。探索阶段的目标是提高信息增益，不是提前完成所有验证。

### 5. 语义检索

Embedding 适合寻找概念相近但词面不同的内容，例如“令牌过期”和 `ttl`、`expiry`、`valid_until`。但它有三个限制：

- 相似不等于因果相关；
- Chunk 边界可能截断类型或调用关系；
- 索引陈旧会返回已经不存在的代码。

更可靠的用途是**生成候选**，再用符号、调用、测试或精确文本证据重排，而不是直接把向量 Top-K 当成最终上下文。

### 6. 历史与约定

`git log`、`blame`、相邻 patch 和仓库文档可以解释“为什么这么写”，但历史不是当前需求。探索器应提取：

- 相同模块过去的修改和测试模式；
- API 兼容策略；
- 反复出现的 review 约束；
- 当前分支上的用户未提交修改。

历史内容和 Issue/网页一样是不可信数据，不能把其中的自然语言当成高优先级指令。

## 三、从 Candidate Generation 到 Evidence Ranking

不要让单个检索器决定一切。一个可解释的排序可以写成：

```text
score(region) =
    w1 * lexical_match
  + w2 * symbol_relation
  + w3 * dynamic_evidence
  + w4 * test_proximity
  + w5 * semantic_similarity
  + w6 * task_constraint_coverage
  - w7 * generated_or_vendor_penalty
  - w8 * redundancy
```

这不是要求手工调出完美权重，而是迫使系统区分信号来源。最终输出还要做多样性约束：十段来自同一文件的高分代码，可能不如“实现、调用方、测试、配置”各一段。

推荐流水线：

1. 解析任务中的实体、行为、错误和约束；
2. 建立仓库地图，排除 vendor、构建产物和大文件；
3. 用词法、文件名和测试映射生成高召回候选；
4. 用符号引用、调用图和运行证据扩展一跳邻居；
5. 对候选区域而不是整文件做语义重排；
6. 去重并控制代码行预算；
7. 让模型形成假设、缺口和下一条查询；
8. 直到新增查询的信息增益下降或定位预算耗尽。

## 四、Agentic Search：检索是一个闭环

一次 Top-K 检索无法处理“看到 A 才知道应该搜索 B”的任务。更实际的是：

```python
while budget.has_search_capacity():
    query = explorer.next_query(task, brief, observations)
    result = tools.search(query)
    observations.append(compress(result))
    brief = evidence_merger.update(brief, result)

    if brief.has_edit_location and brief.constraints_covered:
        break
```

每个查询应记录：目的、预期区分的假设、结果和下一步。如果连续查询只是换同义词却没有改变候选排序，应触发停滞检测。

### Query 类型要显式

| 类型 | 例子 | 适合的工具 |
| --- | --- | --- |
| 定位定义 | `TokenStore` 在哪里实现 | symbol / grep |
| 查找调用 | 谁调用 `validate()` | references / AST |
| 寻找行为 | 哪个测试覆盖过期逻辑 | test-name / grep |
| 验证假设 | 失败是否经过缓存层 | targeted run / trace |
| 寻找约束 | 项目如何处理时区 | docs / history / sibling code |

让工具接受 `query_type`，比把所有意图都塞进一个 `search(query)` 更容易评测和路由。

## 五、影响面分析

定位修改点之后，还要回答“改它可能破坏什么”。影响面至少覆盖：

- 直接调用者和实现者；
- 接口、类型、序列化格式与数据库 schema；
- 公共 API 和 CLI 参数；
- 测试夹具、mock 与快照；
- 配置、文档和迁移脚本；
- 跨语言或跨服务协议。

影响分析不是把整个反向依赖图读进模型。可以按风险逐层扩展：私有函数只查直接调用；公开接口继续查实现、调用、契约测试和兼容层；数据格式修改再查消费者和迁移路径。

## 六、上下文预算如何分配

建议把检索结果拆成三种形态：

1. **索引项**：路径、符号、摘要，长期保留；
2. **证据片段**：当前推理所需的精确代码行；
3. **可重新获取引用**：需要时通过路径和行号加载。

这与把所有文件内容放进 `messages` 的区别在于，系统保存的是可寻址事实，Prompt View 只投影当前最有价值的片段。

代码片段必须带前后文和行号。只返回函数体会漏掉 decorator、类型参数、导入和相邻约定；直接返回整文件又会浪费预算。可以先给符号签名、注释和依赖，再按模型请求展开具体区域。

## 七、一个最小实现协议

```python
class RepositoryIntelligence:
    def explore(self, task: str, revision: str, line_budget: int) -> RepositoryBrief:
        entities = self.task_parser.extract(task)
        repo_map = self.mapper.build(revision)
        candidates = self.lexical.retrieve(entities, repo_map)

        for candidate in candidates[: self.expand_limit]:
            candidates += self.symbols.neighbors(candidate, depth=1)
            candidates += self.tests.related(candidate)

        ranked = self.ranker.rank(task, dedupe(candidates))
        regions = self.budgeter.select(ranked, line_budget)
        brief = self.reasoner.synthesize(task, regions)
        return self.evidence_checker.attach_sources(brief, revision)
```

生产版还需要缓存失效、语言适配器、工具超时、二进制文件过滤、索引版本和权限控制，但这个接口已经把检索结果从聊天文本提升为可测试的数据结构。

## 八、怎样评测 Repository Intelligence？

不要只用“最终任务是否修好”反推检索质量。可以建立独立的探索数据集：给定 Issue 和仓库，要求系统在固定行预算内返回排序后的相关区域。

### 指标

- `file_recall@k`：参考修改/阅读文件是否进入前 K；
- `line_coverage@budget`：固定行预算覆盖多少关键代码；
- `MRR` 或 `NDCG`：关键区域是否排在前面；
- `context_efficiency`：每千行或每千 Token 的有效证据量；
- `wrong_file_edit_rate`：下游 Agent 是否在错误文件修改；
- `time_to_first_correct_region`；
- 最终 resolved rate 与成本。

### 对照实验

至少比较：

1. `rg` + 文件阅读；
2. Embedding Top-K；
3. 词法 + 符号图；
4. Agentic Search + 动态证据；
5. Oracle 文件列表。

Oracle 组能回答：失败究竟来自定位还是后续编辑。如果给出正确文件仍失败，就不应继续优化检索器。

## 九、常见失败模式

### 只找到参考 patch 的文件

参考 patch 不是唯一正确路径，也不一定包含 Agent 为理解问题必须阅读的代码。评测应允许多个有效证据集合。

### 把测试文件排除在检索外

测试经常比实现更准确地表达行为契约。只检索生产代码会漏掉边界条件。

### Repo Map 成为陈旧真相

每次编辑后，符号位置、引用图和文件摘要都可能失效。所有索引项都要带 revision，并支持增量更新。

### 搜索结果污染上下文

重复命中、压缩后的长日志和无关 vendor 代码会挤走任务约束。Repository Intelligence 负责排序，Context Manager 仍要执行最终预算。

### 模型过早锁定假设

找到第一个看似相关的文件就开始编辑，是典型 anchoring。要求 brief 明确列出反证和未知项，并至少寻找一个调用方或测试证据。

## 十、从当前 Harness 演进

### v0.2：结构化搜索结果

为 `search` 返回路径、行号、匹配类型和截断信息；记录查询目的。

### v0.3：Repository Map

加入语言、构建、测试、入口和生成目录扫描；缓存绑定 Git SHA。

### v0.4：符号与测试关系

接入 Tree-sitter/LSP 或语言编译器，建立 `definition/reference/test` 边。

### v0.5：独立探索评测

从仓库历史构造任务，在固定行预算下比较不同检索策略，再观察它们对下游解决率的真实贡献。

## 十一、检查题

1. 为什么 Embedding 相似度不能直接代表代码相关性？
2. Repository Map、Prompt Context 和任务状态分别保存什么？
3. 如何证明一个检索优化提高的是定位能力，而不是偶然提高最终通过率？
4. 修改公共接口时，影响面分析为什么必须跨越直接调用者？
5. 索引没有绑定 Git revision 会产生什么错误？

## 参考资料

- [SWE-Explore: Benchmarking How Coding Agents Explore Repositories](https://arxiv.org/abs/2606.07297)
- [Agentless: Demystifying LLM-based Software Engineering Agents](https://arxiv.org/abs/2407.01489)
- [SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering](https://arxiv.org/abs/2405.15793)
- [Lost in the Middle: How Language Models Use Long Contexts](https://arxiv.org/abs/2307.03172)
- [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Codex use cases: Understand large codebases](https://developers.openai.com/codex/use-cases)

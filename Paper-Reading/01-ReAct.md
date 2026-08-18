# ReAct 详读：把推理、行动与环境反馈接成闭环

论文：[ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629)

官方代码：[ysymyth/ReAct](https://github.com/ysymyth/ReAct)

作者：Shunyu Yao 等｜首次提交：2022 年 10 月｜发表于 ICLR 2023

## 一句话结论

ReAct 的核心不是“让模型多写几句思维过程”，而是把语言推理变成一种不会直接改变环境的内部动作，再与真实工具动作交替执行。Thought 决定下一步要验证什么，Action 获取外部证据，Observation 又迫使模型修正计划。

## 1. 论文究竟在回答什么问题

ReAct 出现之前，语言模型解决复杂任务主要有两条路线。

第一条是 reasoning-only。典型方法是 Chain-of-Thought（CoT）：模型先在文本中分解问题，再给答案。这种方法能展示中间推理，却基本依赖参数记忆。只要早期引用了错误事实，后面的逻辑即使形式正确，也会把错误一路放大。

第二条是 act-only。模型观察环境后直接选择动作，例如在游戏中移动、在网页中点击。它能获得真实反馈，却缺少显式的高层计划和工作记忆，容易忘记子目标、重复动作，或在异常出现后不知道为何要改变策略。

论文的研究问题可以压缩成三句：

1. 能否把语言推理和外部行动放进同一条生成轨迹？
2. 语言形式的 Thought 能否帮助行动规划，而 Observation 能否让推理更有事实依据？
3. 这种互补关系在“知识问答”和“长程决策”两类不同任务上是否都成立？

注意，ReAct 并没有训练一个新的搜索器或规划器。论文主要通过 few-shot prompt，把一个通用语言模型诱导成会交替输出 Thought 与 Action 的策略。

## 2. 形式化：Thought 为什么也被称为 Action

设环境在时间步 `t` 给出观察 `o_t`，此前的交互历史为：

```text
c_t = (o_1, a_1, o_2, a_2, ..., o_t)
```

普通行动策略根据历史选择一个环境动作：

```text
a_t ~ π(a_t | c_t),  a_t ∈ A
```

其中 `A` 是能改变环境的动作集合。ReAct 把动作空间扩成：

```text
Â = A ∪ L
```

`L` 是语言空间。若模型生成 `a_t ∈ L`，这个动作就是 Thought：它不改变外部环境，只把一段语言写入上下文。若生成 `a_t ∈ A`，环境才真正执行动作并返回下一条 Observation。

这个定义有两个重要含义。

- Thought 不是单独运行的隐藏规划模块；它与 Action 一样，都是策略按当前上下文生成的 token。
- Thought 虽不改变世界，却改变了下一步策略的输入，因此相当于可读写的工作记忆。

从控制系统角度看，CoT 更像开环推演，act-only 更像缺少显式状态估计的反馈控制，ReAct 则把“状态估计—控制动作—传感反馈”连了起来。

## 3. 一条轨迹是怎样运行的

论文在知识任务中只给模型三个 Wikipedia 动作：

- `search[entity]`：搜索实体并返回页面开头；
- `lookup[string]`：在当前页面中查找字符串；
- `finish[answer]`：结束并提交答案。

下面是一条抽象化轨迹：

```text
Question: A 的导演出生在哪个国家？

Thought 1: 先确认作品 A 的导演是谁。
Action 1: search[A]
Observation 1: 页面说明 A 由 B 执导……

Thought 2: 现在需要 B 的出生地。
Action 2: search[B]
Observation 2: B 出生于城市 C……

Thought 3: 还要把城市映射到国家。
Action 3: search[C]
Observation 3: C 是国家 D 的城市……

Thought 4: 证据链闭合，可以作答。
Action 4: finish[D]
```

Thought 在不同位置承担不同功能：

1. **分解目标**：把原问题拆成实体识别、属性查询、关系组合。
2. **选择工具**：判断此时应搜索新页面、在页内查找，还是直接作答。
3. **压缩观察**：把长文本中真正有用的证据写成短状态。
4. **维护进度**：记录哪些子问题已解决、还差哪一环。
5. **处理例外**：搜索无结果时重写查询，而不是机械重复。
6. **决定终止**：只有证据链闭合时才调用 `finish`。

在 ALFWorld 这类长程任务中，Thought 可以是稀疏的。模型不需要每次移动前都解释，而是在找到物品、完成子目标、遇到失败等关键节点更新计划。论文由此说明：有效的 reasoning 不是字数越多越好，而是要出现在会改变决策的位置。

## 4. 实验设计：四种方法到底在对照什么

论文主要比较四种提示方式：

| 方法 | 有语言推理 | 有外部行动 | 它控制的变量 |
| --- | --- | --- | --- |
| Standard | 否 | 否 | 模型直接回答的基础能力 |
| CoT | 是 | 否 | 只有推理、没有外部反馈时的上限与风险 |
| Act | 否 | 是 | 只有工具交互、没有显式计划时的表现 |
| ReAct | 是 | 是 | 推理与行动交替是否产生互补 |

这个对照比单纯拿 ReAct 和标准 prompting 比更有价值，因为它能回答提升来自“多了思考”还是“多了工具”。

论文使用的主要模型是 PaLM-540B，并通过少量人工轨迹作为 in-context examples。这里的实验结论不能直接外推成“任何小模型加 ReAct 都会提升”：模型首先要能稳定模仿动作语法、理解 Observation，并维持多轮状态。

## 5. 知识任务：HotpotQA 与 FEVER

### 5.1 两个任务分别测什么

- **HotpotQA** 是多跳问答，常需要跨多个 Wikipedia 页面组合事实，以 Exact Match（EM）衡量答案。
- **FEVER** 要判断一条陈述是支持、反驳还是信息不足，以分类准确率衡量。

二者都需要知识，但错误结构不同。HotpotQA 对开放式证据链和答案字符串更敏感；FEVER 的输出空间小，更适合用检索证据约束判断。

### 5.2 主结果逐项解读

论文表 1 的核心结果如下：

| 方法 | HotpotQA EM | FEVER Accuracy |
| --- | ---: | ---: |
| Standard | 28.7 | 57.1 |
| CoT | 29.4 | 56.3 |
| CoT-SC | 33.4 | 60.4 |
| Act | 25.7 | 58.9 |
| ReAct | 27.4 | 60.9 |
| CoT-SC → ReAct | 34.2 | 64.6 |
| ReAct → CoT-SC | 35.1 | 62.0 |

不能把这张表读成“ReAct 全面胜过 CoT”。更准确的解释是：

- 在 HotpotQA 上，纯 ReAct 的 27.4 低于 CoT 的 29.4。受限的 `search/lookup` 交互会让轨迹变长，也可能把模型带到错误页面。
- 在 FEVER 上，ReAct 的 60.9 高于 CoT 的 56.3。事实核验更直接受益于外部证据。
- CoT-SC 通过多条推理链投票，减少单次推理偶然性；ReAct 则通过环境反馈减少无依据事实。二者的错误不完全重合，所以串联后的 34.2/64.6 或 35.1/62.0 更高。
- “先 ReAct 还是先 CoT-SC”在两个数据集上结果不同，说明系统应根据任务结构设计 fallback，而不是迷信固定 loop。

### 5.3 失败分析为什么比平均分更重要

论文人工比较了 ReAct 与 CoT 的错误。在所分析的案例中，CoT 错误有很大一部分来自事实幻觉；ReAct 几乎消除了这类无依据陈述，却引入了新的错误来源：检索不到、检索到错误页面、根据局部证据过早结束，以及陷入动作循环。

论文报告的错误构成中，ReAct 的主要问题约为推理错误 47%、搜索结果错误 23%；CoT 的错误中约 56% 与 hallucination 有关。数字的价值不在于精确比例能否跨模型复现，而在于它揭示了**错误迁移**：工具没有消灭错误，只是把错误从“内部编事实”转移成“搜错、读错、停错”。

## 6. 决策任务：ALFWorld 与 WebShop

### 6.1 ALFWorld

ALFWorld 是文字化家庭环境。任务可能要求把某件物品清洗、加热后放到指定位置。agent 必须探索房间、记住物体位置，并按正确顺序执行多步操作。

论文中最佳 ReAct 设置成功率为 71%，Act-only 为 45%。这 26 个百分点说明 Thought 的价值主要出现在长程状态管理：

- 把最终目标拆成“找到—拿起—处理—放置”；
- 记录已经探索过的位置；
- 操作失败后根据前置条件重新计划；
- 防止完成局部步骤后忘记总目标。

### 6.2 WebShop

WebShop 要根据自然语言偏好在模拟购物网站中搜索、筛选并购买商品。它同时包含语义匹配和网页操作。

| 方法 | 平均得分 | 成功率 |
| --- | ---: | ---: |
| Act | 62.3 | 30.1% |
| ReAct | 66.6 | 40.0% |
| Expert human | 82.1 | 59.6% |

ReAct 明显优于 Act，但仍远低于人类。这表明“会解释下一步”并不足以解决细粒度页面理解、属性约束匹配和长动作链的所有问题。

## 7. 微调实验告诉了我们什么

论文还从 3,000 条正确轨迹中构造训练数据，对较小的 PaLM-8B 和 PaLM-62B 进行微调。目的不是证明 ReAct 必须靠大模型，而是测试轨迹格式能否通过监督学习内化。

这里应区分三种训练对象：

- 只训练最终答案，模型学到“结果长什么样”；
- 训练 Thought，模型学到如何维护中间状态；
- 训练 Thought + Action + Observation 轨迹，模型学到在什么状态调用什么动作。

Observation 来自环境，训练时不应被当作模型目标胡乱生成。一个现代实现通常只对模型产生的 Thought/Action token 计算损失，并在 rollout 时用真实工具结果补入 Observation。

## 8. 映射到 Code Agent：逐项对应，而非比喻

| ReAct 元素 | Coding agent 中的具体对象 |
| --- | --- |
| Task | issue、需求、仓库约束、验收标准 |
| Thought | 故障假设、下一步搜索目的、测试策略 |
| Action | `rg`、打开文件、编辑、运行测试、查看 diff |
| Observation | 代码片段、退出码、堆栈、测试摘要、diff |
| Environment state | 当前 commit、工作树、依赖与运行进程 |
| Finish | 提交 patch，并说明验证结果 |

一条更可靠的 coding trajectory 应像这样：

```text
Thought: 报错出现在 serializer，但根因可能是上游传入 None；先找调用点。
Action: search("serialize_user(")
Observation: 3 个调用点，其中 api/users.py 未做空值校验。

Thought: 先读测试与函数契约，确认 None 应该被拒绝还是跳过。
Action: view(tests/test_users.py, 120, 210)
Observation: 既有测试期望缺失字段返回 400。

Thought: 应在 API 边界校验，避免把业务错误变成 serializer 崩溃。
Action: edit(...)
Observation: patch applied; syntax check passed.

Thought: 先运行最小回归，再运行相关模块。
Action: run("pytest tests/test_users.py -q")
Observation: 18 passed.
```

关键不在于向用户展示全部私有推理，而在于系统内部必须保存功能等价的结构化状态：当前假设、证据、已尝试动作、下一步目的与完成条件。

## 9. 四类典型失败及工程补丁

### 9.1 循环

症状：重复相同搜索、相同测试或近似 Thought。原因常是 Observation 没有提供新信息，策略却没有显式失败计数。

工程补丁：对规范化后的 `(action, arguments)` 做短期去重；连续两次无状态变化时要求生成新假设；给搜索、编辑、测试分别设置预算。

### 9.2 坏 Observation 污染后续

症状：一次被截断的日志或错误搜索结果被当成事实，后续全部围绕它展开。

工程补丁：Observation 附带退出码、截断标记、来源位置；把“观察到的事实”和“模型推断”分字段保存。

### 9.3 过早终止

症状：改完代码就 `finish`，没有复现 bug，也没有回归测试。

工程补丁：把 finish 变成有条件动作；至少要求存在 diff、最小相关测试已运行，并显式记录未验证项。

### 9.4 轨迹越长，状态越乱

症状：旧文件内容、旧报错和新状态同时留在上下文中，模型依据过期信息编辑。

工程补丁：保留结构化摘要和最近原始 Observation；文件编辑要有 old-text/version 前置条件；每次修改后返回当前 diff。

## 10. 源码怎么读

官方仓库是论文实验代码，不是完整通用 agent 框架。建议按以下顺序：

1. [`prompts/`](https://github.com/ysymyth/ReAct/tree/master/prompts)：先看 few-shot 轨迹如何规定 Thought/Action 格式。
2. [`wikienv.py`](https://github.com/ysymyth/ReAct/blob/master/wikienv.py)：看 `search`、`lookup` 等动作怎样与环境交互。
3. [`wrappers.py`](https://github.com/ysymyth/ReAct/blob/master/wrappers.py)：看环境如何被包装、Observation 如何返回。
4. [`hotpotqa.ipynb`](https://github.com/ysymyth/ReAct/blob/master/hotpotqa.ipynb) 与 [`FEVER.ipynb`](https://github.com/ysymyth/ReAct/blob/master/FEVER.ipynb)：对照论文重放知识任务。
5. [`alfworld.ipynb`](https://github.com/ysymyth/ReAct/blob/master/alfworld.ipynb) 与 [`WebShop.ipynb`](https://github.com/ysymyth/ReAct/blob/master/WebShop.ipynb)：观察长程任务的提示和终止逻辑。

读源码时重点记录四件事：动作是怎样被解析的、非法动作怎样处理、最大步数在哪里限制、完整轨迹如何保存。它们比 prompt 中某个具体措辞更可迁移。

## 11. 常见误读

- **“ReAct 就是 CoT 加工具。”** 不完整。关键是 Observation 会进入下一轮决策，形成闭环，而不是推理完再一次性调用工具。
- **“Thought 越详细越好。”** 错。冗长 Thought 会消耗上下文，并可能把未经验证的假设固化。
- **“有搜索就不会 hallucinate。”** 错。错误会迁移为查询错误、证据误读和无证据终止。
- **“ReAct 在所有任务上都优于 CoT。”** 与表 1 不符；纯 ReAct 在 HotpotQA 上低于 CoT。
- **“论文已经解决 agent 的记忆问题。”** 没有。它证明语言状态有用，但长轨迹的压缩、冲突和过期仍需工程处理。

## 12. 可复现练习

### 最小练习：实现一个三动作 agent

只实现 `search(query)`、`open(path, lines)`、`finish(answer)`，并记录每轮 action、observation、耗时和 token。用 20 个需要跨文件定位的问题测试：

1. 不允许 Thought 的 act-only 版本；
2. 每步都有 Thought 的版本；
3. 只有定位失败或状态变化时才写摘要的稀疏 Thought 版本。

比较成功率、平均步数、重复动作率和无效 Observation 比例。这个实验比只比较最终准确率更能验证 ReAct 机制。

### 进阶练习：加入终止门禁

为 coding agent 规定：只有“工作树存在变更 + 至少一个相关测试通过 + diff 已查看”时才能提交。观察过早终止率是否下降，以及是否带来更多无意义测试。

## 13. 读完后的检查题

1. Thought 为什么能改变策略，却不改变外部环境？
2. ReAct 在 FEVER 上收益比 HotpotQA 更明显，可能由哪些任务差异造成？
3. CoT-SC 与 ReAct 为什么互补？它们分别降低什么类型的错误？
4. 如果 Observation 被截断，agent 应如何知道自己的证据不完整？
5. 在 coding agent 中，哪些状态应该结构化保存，而不是依赖自由文本 Thought？

## 14. 最终要带走的观点

ReAct 给 Code Agent 的不是完整架构，而是一条最小系统定律：**模型只有通过“提出假设—作用于环境—读取真实反馈—更新假设”的闭环，推理才能落到真实仓库；但闭环会同时制造循环、噪声、过期状态和成本，因此必须被接口、预算与验证门禁约束。**

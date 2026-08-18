# SWE-bench 详读：Code Agent 究竟在优化什么

论文：[SWE-bench: Can Language Models Resolve Real-World GitHub Issues?](https://arxiv.org/abs/2310.06770)

官方代码：[SWE-bench/SWE-bench](https://github.com/SWE-bench/SWE-bench)

项目与榜单：[swebench.com](https://www.swebench.com/)

作者：Carlos E. Jimenez 等｜首次提交：2023 年 10 月｜发表于 ICLR 2024

## 一句话结论

SWE-bench 把代码生成任务定义成：在某个真实仓库的指定历史提交上，根据自然语言 issue 生成一个可应用的 patch；该 patch 不必复刻开发者答案，但必须让目标失败测试转为通过，同时不破坏原有行为。

## 1. 先理解它改变了什么

HumanEval 一类函数级 benchmark 通常已经替模型完成了三件最难的事：选定文件、选定函数、写好明确函数契约。模型主要负责补齐局部算法。

SWE-bench 则只给出人类 issue 和完整代码库。issue 可能包含错误现象、期望行为、堆栈、复现步骤，也可能表述模糊。模型必须自己完成：

```text
理解问题
  -> 在仓库中定位责任模块
  -> 还原历史版本的运行条件
  -> 理解跨文件调用和既有契约
  -> 生成可应用的修改
  -> 验证目标行为与回归行为
```

因此它评测的并非狭义 code generation，而是一个压缩的软件维护过程。

## 2. 任务形式化：输入、输出与隐藏信息

对每个实例，记：

- `P`：自然语言问题描述；
- `C`：位于 `base_commit` 的完整仓库状态；
- `δ*`：真实开发者的 solution patch；
- `T*`：从 PR 中抽取、用于验证修复的 test patch；
- `δ̂`：系统生成的候选 patch。

系统只根据 `P` 和可访问的 `C` 生成 `δ̂`：

```text
δ̂ = Agent(P, C)
```

评测器并不要求 `δ̂ = δ*`。它在隔离环境中执行测试，判断候选修改是否满足行为约束：

```text
Resolved(δ̂) =
  all FAIL_TO_PASS pass
  AND all PASS_TO_PASS remain pass
```

这个定义允许多个语义等价修复，也说明 gold patch 不是唯一答案。`δ*` 的作用主要是帮助数据构造与验证，而不是作为字符串匹配目标。

## 3. 一个实例是怎样从 GitHub 历史生成的

原始论文从 12 个流行 Python 仓库的约 90,000 个 pull request 开始筛选，最后得到 2,294 个可执行实例。构造过程可以拆成七步。

### 3.1 建立 issue 与 PR 的关系

研究者识别会解决某个 issue 的 PR。真实项目中的链接可能来自 PR 描述、closing keyword、提交信息或 GitHub 元数据。问题描述来自 issue，而开发者修改来自 PR。

### 3.2 选择 `base_commit`

`base_commit` 是应用开发者修复之前的代码状态。它必须满足：issue 对应的 bug 仍然存在，同时代码与后续测试 patch 的上下文相容。

如果这里选错，任务会出现三种伪失败：bug 尚未出现、bug 已被其他提交修复、测试 patch 无法应用。

### 3.3 拆分 solution patch 与 test patch

目标 PR 的 diff 被概念上拆为：

- solution patch：产品代码或修复逻辑；
- test patch：新增或修改的验证代码。

二者必须分开，因为评测时模型不能直接看到开发者修复，但评测器需要利用新增测试判断行为。

### 3.4 构建历史环境

每个仓库在不同 release version 可能依赖不同 Python 与第三方包。论文按版本建立 conda 环境和安装步骤，而不是强迫所有历史提交使用统一最新依赖。

### 3.5 在修复前运行测试

在 `base_commit` 上应用 test patch。新增测试中至少要有一个失败，否则它没有证明 issue 能被复现。

### 3.6 应用开发者 patch 再运行

应用 `δ*` 后，目标失败测试应通过，同时既有测试不能发生不合理回归。只有能完成这种“失败→通过”的状态转移，实例才具有可执行判据。

### 3.7 保存可重放元数据

一个实例最终至少需要 repository、instance id、base commit、problem statement、solution patch、test patch、版本/环境信息与测试集合。也就是说，benchmark 收集的不是一对文本，而是**一个可重放的软件状态转换**。

## 4. FAIL_TO_PASS 与 PASS_TO_PASS 到底是什么

这是读 SWE-bench 最容易被略过、却最关键的一部分。

### FAIL_TO_PASS

这些测试在未修复状态失败，在应用 gold patch 后通过。它们代表 issue 的目标行为。候选 patch 若不能让它们全部通过，就没有解决任务。

### PASS_TO_PASS

这些测试在未修复状态已经通过，修复后也应继续通过。它们代表回归约束。只让目标测试变绿、却破坏既有功能的 patch 不能算成功。

设目标集合为 `F2P`，回归集合为 `P2P`，则一个简化判据为：

```text
score(δ̂) = 1[
  ∀t ∈ F2P, run(C + T* + δ̂, t) = PASS
  ∧
  ∀t ∈ P2P, run(C + T* + δ̂, t) = PASS
]
```

这里的 `+` 表示按正确顺序应用 patch。实际 harness 还要处理安装、超时、日志解析与不同测试框架。

## 5. 完整评测流水线

对一个预测 patch，harness 大致执行：

1. 创建干净容器或隔离环境；
2. checkout 镜像仓库到 `base_commit`；
3. 安装与该历史版本匹配的依赖；
4. 应用 test patch；
5. 应用模型 patch；
6. 运行仓库指定的测试命令；
7. 解析测试日志并区分 F2P/P2P；
8. 输出 resolved、unresolved 或 infrastructure failure。

顺序不能随意交换。若先应用模型 patch 再应用测试 patch，二者可能冲突；若不回到干净工作树，前一实例的文件、缓存或构建产物可能污染下一实例。

## 6. 为什么环境是任务定义，而非外围工程

可以把一个 SWE-bench 任务写成四元组：

```text
Task = (Issue, Repository Snapshot, Environment, Tests)
```

缺失任何一项都会改变任务：

- 仓库正确但 Python 版本错误，安装会失败；
- 依赖正确但系统库缺失，测试可能在 import 阶段退出；
- 测试命令不完整，会漏掉真正的目标测试；
- 超时太短，会把慢测试误判成失败；
- 日志 parser 不认识某个框架，会把通过误报为 unresolved。

因此评价一个 agent 时，要把“模型失败”和“基础设施失败”分开统计。否则优化模型 prompt 可能只是在补偿不稳定的评测环境。

## 7. 原论文基线是怎样做的

原论文并没有使用今天常见的自主工具循环。它评估的是以检索和单次生成为主的系统。

### 7.1 文件检索

由于完整仓库远超上下文窗口，系统先用 BM25 根据 issue 检索相关文件。检索阶段隐含一个强假设：问题描述中的词与责任代码有足够词面重合。

这对报错包含函数名的 issue 有效，但对概念性 bug 较弱。例如“日期在夏令时切换时偏移”未必直接出现内部 timezone helper 的符号名。

### 7.2 上下文拼接

被检索出的文件按预算拼入 prompt。论文比较不同上下文长度，研究“多给代码是否能提升修复率”。结论并非越多越好：长上下文增加覆盖，也会挤占推理与输出预算并引入无关实现。

### 7.3 Patch 生成

模型读取 issue 与检索代码后输出修改。系统还要把生成内容转换为可应用 diff。格式错误、定位错误或上下文不一致都会导致 patch 无法应用，即使修改意图正确。

### 7.4 早期结果应怎样解释

论文初版强调 Claude 2 约解决 1.96% 的任务；后续版本表格加入 Claude 3 Opus 后报告 3.79%。这些是特定日期、模型、提示、检索与 harness 下的历史结果，不能直接与今天榜单上的 agent 比较。

真正稳定的结论是：**“检索几个看似相关的文件，再让强模型一次性写 patch”远远不够。** 失败可能发生在定位、上下文选择、修改范围、patch 格式或验证任一环节。

## 8. Oracle retrieval 实验在诊断什么

论文还使用 gold patch 涉及的文件作为 oracle context。Claude 2 在这种理想定位条件下也只有约 4.8% 的解决率。

这个实验不是现实系统，因为真实推理时不能查看 gold patch。它是一个诊断上界：

- 普通检索与 oracle 的差距，近似反映定位和上下文选择的损失；
- oracle 条件下仍失败，说明即使“给对文件”，跨函数理解、修改推理和输出 patch 仍很难；
- oracle file 不等于 oracle line/function，文件内部仍可能有数千行搜索空间；
- gold 修改文件也不保证包含理解问题所需的全部上下文，调用方、测试和文档可能在其他位置。

所以不能从 oracle 低分得出“定位不重要”，而应得出：定位是必要条件，但不是充分条件。

## 9. 为什么它比 HumanEval 难：逐层拆解

| 难度层 | HumanEval 常见设置 | SWE-bench |
| --- | --- | --- |
| 问题理解 | 明确 docstring | 非结构化 issue，可能不完整 |
| 搜索空间 | 已指定函数 | 整个仓库 |
| 上下文 | 局部代码 | 跨文件调用、配置、文档、测试 |
| 环境 | 统一轻量 | 历史依赖与仓库特定命令 |
| 修改 | 通常单函数 | 可能跨模块、测试、配置 |
| 验证 | 少量公开单测 | 隐藏目标测试 + 回归测试 |
| 输出 | 函数体 | 可应用 repository diff |
| 终止判断 | 执行给定测试 | agent 常需自己先构造复现 |

更深一层，SWE-bench 的成功是多个条件的乘积。假设文件定位成功率 70%、在正确位置上修复成功率 60%、patch 可应用率 90%、最终验证/选择正确率 80%，端到端成功率只有：

```text
0.70 × 0.60 × 0.90 × 0.80 = 30.24%
```

这解释了为何某个局部模块提升很多，最终 resolved rate 可能只增加几个百分点。

## 10. Hidden tests 与 agent 自验证的鸿沟

目标 PR 中的测试 patch 属于评测端信息。若 agent 完整看到它，就可能针对测试写特例，甚至从测试结构反推出 gold fix。

现实中的 agent 通常只能看到仓库原有测试，因此必须自己建立可见 verifier：

- 从 issue 写最小复现脚本；
- 找到相邻测试并补一个本地用例；
- 运行静态检查和相关回归；
- 用行为断言而不是“代码看起来对”判断修改。

但本地验证通过仍不等于 hidden tests 通过。它只是在不可见判据下提高置信度。后续 Agentless 会显式生成 reproduction test 选 patch，SWE-Gym 则把可执行环境用于训练 policy 和 verifier。

## 11. 数据污染与 benchmark 偏差

### 11.1 预训练污染

issue、PR、commit 与 patch 都公开存在于 GitHub，可能进入模型预训练语料。模型有可能回忆答案，而非现场理解仓库。

原论文训练 SWE-Llama 时让训练仓库与评测仓库互斥，以降低直接泄漏，但这不能证明基础模型从未见过公开评测 PR。

### 11.2 反复调 benchmark 造成的系统过拟合

即使模型没有记住 patch，研究者也可能围绕固定仓库反复调整 prompt、工具和安装脚本。最终系统会熟悉 Django、SymPy 等仓库的惯例，却未必泛化到新项目。

### 11.3 实例本身的歧义

真实 issue 可能缺少必要信息；gold patch 也可能夹带重构或非必要修改。测试覆盖有限时，一个投机 patch 可能通过但不符合维护者意图。

### 11.4 排行榜数字的正确读法

比较系统时至少核对：数据子集、实例版本、模型版本、每题采样数、工具预算、是否使用外部检索、是否可见测试、是否过滤环境失败、成本与轨迹是否公开。

SWE-bench、SWE-bench Lite（300 题）与 SWE-bench Verified 不是同一个分母，不能只拿百分比横向排列。

## 12. 对 Code Agent 架构的直接启示

SWE-bench 把端到端 agent 暗含地分成五个模块：

1. **问题建模**：从 issue 提取症状、期望、约束与可复现条件。
2. **Fault localization**：从仓库到文件、符号、代码行逐级缩小范围。
3. **Patch synthesis**：在理解契约后生成最小且可维护的修改。
4. **Environment operation**：稳定安装、执行、超时与捕获日志。
5. **Verification/selection**：用复现与回归选择候选，并决定是否终止。

这也是后续论文的分工图：

- SWE-agent 主要优化 agent 与环境之间的工具界面；
- Agentless 把定位、修复、验证显式拆成 pipeline；
- OpenHands 把 runtime、event stream 与 sandbox 做成平台；
- SWE-Gym 把任务环境和轨迹变成训练资产。

## 13. 官方代码怎么读

官方仓库持续演进，目录可能随版本变化。不要从 leaderboard 页面开始，先沿评测数据流阅读：

1. [`swebench/`](https://github.com/SWE-bench/SWE-bench/tree/main/swebench)：主 Python 包。
2. [`swebench/harness/`](https://github.com/SWE-bench/SWE-bench/tree/main/swebench/harness)：实例如何构建镜像、执行预测并收集结果。
3. [`swebench/harness/run_evaluation.py`](https://github.com/SWE-bench/SWE-bench/blob/main/swebench/harness/run_evaluation.py)：评测入口与预测格式。
4. [`swebench/harness/test_spec/`](https://github.com/SWE-bench/SWE-bench/tree/main/swebench/harness/test_spec)：仓库/实例特定测试规格。
5. [`swebench/collect/`](https://github.com/SWE-bench/SWE-bench/tree/main/swebench/collect)：数据收集与任务构造相关代码。

源码阅读时画出一条实例生命周期：dataset row → test spec → image → container → patch apply → test log → report。若无法解释其中任一转换，就还没有真正理解 benchmark 分数。

## 14. 常见误读

- **“SWE-bench 比较谁生成的 diff 更像 gold patch。”** 错，它比较可执行行为。
- **“测试通过就证明修复完全正确。”** 只能证明通过当前测试集合，测试本身仍可能不完备。
- **“环境问题不算模型问题，所以可以忽略。”** 对模型研究可单列，但对可交付 agent，它就是产品可靠性问题。
- **“oracle retrieval 只有 4.8%，所以定位没价值。”** 错；它说明定位之后仍有巨大修复难度。
- **“所有 SWE-bench 百分比可直接比较。”** 错；必须对齐子集、版本、模型、预算与评测设置。
- **“解决 issue 只需改产品代码。”** 不一定；真实任务可能涉及配置、迁移、文档或多个模块，但 benchmark 的测试判据会影响哪些变化可计分。

## 15. 可复现练习

### 练习一：手工重放一个实例

任选一个公开实例，依次 checkout `base_commit`、应用 test patch、运行目标测试、应用 gold patch、再次运行。记录每一步的工作树和测试状态。目标是亲眼验证 F2P 的状态转换，而不是只运行现成评分脚本。

### 练习二：拆解失败归因

对 20 个 agent 失败实例标注：环境未构建、定位错误、修改逻辑错误、patch 不可应用、测试超时、过早终止、回归失败。统计各类别占比。只有做到这一步，才知道下一轮该优化模型、检索、ACI 还是 harness。

### 练习三：测量定位上界

分别给模型：BM25 top-k 文件、人工选定文件、gold patch 涉及文件。保持其余 prompt 与生成预算不变，比较 resolved rate 和 token 成本。这样可以把“定位损失”与“修复损失”部分分离。

## 16. 读完后的检查题

1. 为什么 solution patch 与 test patch 必须分开？
2. F2P 全过但 P2P 有一个失败，为什么仍不能算 resolved？
3. gold patch 文件为什么只是 oracle file localization，不是完整 oracle？
4. 环境失败与模型失败在报告中应如何分层？
5. 若公开测试全过但 hidden test 失败，下一步应改进哪个模块？答案不一定只有一个。

## 17. 最终要带走的观点

SWE-bench 最大的贡献不是某个排行榜，而是一个可执行的 Code Agent 定义：**在正确的历史环境中，把不完整的人类问题描述转化成经目标测试和回归测试共同验证的仓库状态变化。** 从此以后，搜索、编辑、sandbox、轨迹训练和 verifier 都能围绕同一个外部目标被比较。

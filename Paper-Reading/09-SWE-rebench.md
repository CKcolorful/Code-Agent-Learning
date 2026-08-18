# SWE-rebench 详读：持续生成可执行任务与时间去污染评测

论文：[SWE-rebench: An Automated Pipeline for Task Collection and Decontaminated Evaluation of Software Engineering Agents](https://arxiv.org/abs/2505.20411)

项目与代码：[SWE-rebench](https://github.com/SWE-rebench)｜[Benchmark](https://swe-rebench.com/)

发表：NeurIPS 2025 Datasets & Benchmarks Track｜作者：Ibragim Badertdinov、Alexander Golubev、Maksim Nekrashevich 等

## 一句话结论

SWE-rebench 同时解决训练数据和评测老化问题：自动从不断产生的 GitHub issue/PR 中恢复可执行环境，形成 21,336 个训练任务；再按模型发布日期选择更晚出现的任务、固定 scaffold 并重复运行，构造随时间滚动的评测。它让“污染”从模糊怀疑变成可记录的时间关系，但时间新鲜并不能单独证明或排除污染。

## 1. 这篇论文解决两个不同问题

很多介绍把 SWE-rebench 只当成新 benchmark，实际上它有两层产物：

```text
自动任务收集流水线
  ├─ 大规模公开数据集：21,336 个任务，用于训练/RL
  └─ 严格筛选评测集：294 个任务、169 个仓库，用于滚动评测
```

训练集追求规模、可执行性与元数据；评测集还要追求新鲜度、质量、可比较性和独立验证。两者不能用同一质量门槛，也不能混用任务。

## 2. 第一阶段：从海量 GitHub 事件找候选

流水线结合 GitHub Archive 和完整 git clone：前者恢复 issue、PR、讨论与时间信息，后者恢复 base commit、patch 和历史代码。

作者从 30,000 多个宽松许可证、Python 占比超过 75% 的仓库中下载约 450,000 个 issue-linked PR，过滤条件包括：

- issue 已解决，PR 已合入主分支；
- 一个 PR 不同时关联多个 issue；
- issue 描述长度足够；
- PR 同时修改测试和非测试代码；
- 变更文件数在 1–15 之间。

过滤后约剩 153,400 个候选。PR patch 被分为 solution patch 与 test patch，为后续 F2P/P2P 状态验证做准备。

## 3. 最难自动化的其实是环境安装

SWE-bench 依赖人为维护仓库版本与安装规则，规模一大就不可持续。SWE-rebench 先根据 git tag 将任务归入 `major.minor` 版本组，用组内较新的 base commit 共享环境；约 95% 的任务能取得 tag，其余独立建环境。

安装 recipe 通过 Agentless 风格流水线生成：

1. 找 README、Dockerfile、setup.py 等安装相关文件；
2. 拼接内容，让 Qwen2.5-72B-Instruct 输出结构化 JSON recipe；
3. 每个任务最多生成 3 个候选 recipe；
4. 执行安装与测试，把错误日志交给模型修正 recipe；
5. 成功后记录 `pip freeze`、`conda env export` 与最终镜像。

至少一个任务成功安装的仓库占 31%。作者也试过让交互式 agent 直接装环境，偶尔成功率更高，但成本过大，最终选择可并行、可缓存的固定流水线。

这揭示了规模化系统的一条规律：环境构建任务需要推理，但不一定需要完整自主 Agent Loop；结构化候选生成 + 执行反馈更适合批处理。

## 4. 执行验证到底检查什么

流水线在隔离容器中执行 test patch，解析测试级状态，并要求：

1. 未应用 solution patch 前，至少一个新增/修改测试失败；
2. 应用 solution patch 后，这些 F2P 测试全部通过；
3. 原来已经通过的相关测试仍然通过。

可以写成：

```text
valid = |F2P| > 0
        and all(F2P become pass after solution)
        and all(P2P stay pass)
```

它能过滤不可执行或无法验证修复的 PR，但仍可能存在测试过度绑定官方实现、issue 不清楚、solution patch 混入重构等问题。

## 5. 用模型近似人工质量审核

规模超过两万后，不可能像 SWE-bench Verified 那样逐条人工审核。作者用 SWE-bench Verified 的人工标注微调 Qwen2.5-72B-Instruct，分别预测：

- Issue Clarity；
- Task Complexity；
- Test Patch Correctness。

验证集上，复杂度、issue 清晰度和测试正确性的准确率分别约为 81%、79% 和 67%。这些标签作为 metadata 供训练者过滤，而不是把模型判断当成真值。

这点非常关键：质量模型是**可扩展代理指标**，尤其测试正确性只有 67% 准确率，不能替代最终人工审计。用这个数据做 RL 时，错误任务会把正确行为标成失败，形成 reward noise。

## 6. “Decontaminated” 是怎样定义的

静态 benchmark 发布后可能进入预训练、SFT 数据或人工 prompt 调优。SWE-rebench 记录 issue/PR 创建时间、模型发布日期和评测窗口：若任务晚于模型训练/发布可能接触的时间，直接记忆的可能性显著下降。

但要区分三个概念：

```text
temporal freshness  ≠  mathematically proven no contamination
lower fresh score   ≠  proof of memorization on old benchmark
same fresh score    ≠  proof of perfect generalization
```

模型可能通过持续训练接触更晚数据，仓库模式也可能与训练数据高度相似；而新任务本身可能更难。论文更严谨的贡献是提供时间标记和滚动窗口，让风险可见，而不是声称拥有绝对无污染标签。

## 7. 固定 scaffold 才能比较模型

SWE-bench 榜单常把模型、prompt、工具、重试、selector 和测试预算混在一个系统分数里。SWE-rebench 使用同一个最小 ReAct scaffold、相同系统提示和默认超参数，对模型进行五次完整运行，并同时报告：

- mean resolved rate；
- 标准误 SEM；
- Pass@5。

于是比较更接近：

```text
固定 Environment + Tools + Prompt + Budget
只替换 Model
```

这适合研究底层模型能力，却不等价于比较“最佳可部署 Agent 系统”。一个对特定模型高度优化的原生 scaffold 可能在真实使用中更强。

## 8. 结果中的三个信号

论文的 294 题 benchmark 来自 169 个仓库。对 January 2025 与 March–April 2025 两个时间片，GPT-4.1 的 mean resolved 从 31.1% 降到 26.7%，Pass@5 从 44.4% 降到 39.0%；其他模型变化方向并不一致。

与 SWE-bench Verified 横向比较时：

- DeepSeek-V3-0324：39.7% 对 fresh slice 21.3%；
- DeepSeek-V3-1226：35.2% 对 21.9%；
- Llama-3.3-70B-Instruct：18.1% 对 11.2%。

这个差距可能来自污染、任务/仓库分布、环境难度、scaffold 适配或它们的组合，不能单因归因。更有价值的是稳定性信息：Llama-4-Maverick 的 Pass@5 相对 mean resolved 很高，说明它有能力偶尔产生正确解，但跨运行可靠性不足。

轨迹还显示 Qwen2.5-Coder-32B 经常伪造环境反馈或陷入格式错误循环。这是仅看 patch 无法看见的 Agent 能力缺陷。

## 9. 这篇论文对 Verifier 的扩展

SWE-rebench 的 verifier 不只是“跑测试”，而是一条分层链路：

```text
license/time/repo filters
        ↓
environment recipe verifier
        ↓
F2P/P2P execution verifier
        ↓
LLM quality metadata
        ↓
benchmark temporal policy
        ↓
repeated evaluation + SEM/Pass@5
```

任何一层有噪声都会影响最终结论。一个成熟 benchmark 应把 environment failure、agent failure、test failure 和 infrastructure failure 分开记录，不能统统算 0。

## 10. 与 SWE-smith 的根本差别

| 维度 | SWE-smith | SWE-rebench |
| --- | --- | --- |
| 任务来源 | 在可运行仓库中合成 bug | 真实 issue/PR 软件演化 |
| 扩展单位 | 一个环境生成很多任务 | 自动恢复大量版本与环境 |
| 核心优势 | 便宜、大规模、可控 | 真实、持续更新、可按时间去污染 |
| 主要风险 | synthetic-to-real gap | 安装成功率与自动质量标签噪声 |
| 更适合 | 轨迹 SFT、RL 数据扩展 | 真实训练数据、fresh evaluation |

二者不是替代关系。一个强训练配方可以用 SWE-smith 扩大行为覆盖，用 SWE-rebench 提供真实任务，再在严格时间切分上评测。

## 11. 论文局限

1. 自动安装 prompt 只在有限仓库上调试，31% 仓库成功率也意味着显著选择偏差；容易安装的 Python 项目被过度代表。
2. 质量标签继承 SWE-bench Verified 的标注定义与误差，尤其 Test Patch Correctness 仍不可靠。
3. 同一 scaffold 对不同模型未必同样友好，固定接口控制了变量，也可能系统性压低某些模型。
4. 五次运行能估计随机性，但 294 题和多个时间片仍可能有较大分布变化。
5. 公开的新鲜 benchmark 最终也会变旧，所以核心能力是持续更新流程，而不是某个固定 split。

## 12. 最小复现实验

选择 50 个在两个连续月份合入的 Python issue/PR：

1. 自动抽取 base commit、solution/test patch 和时间戳；
2. 让 LLM 从仓库文档生成 JSON 安装 recipe，并允许两轮错误修正；
3. 用 F2P/P2P 规则筛选；
4. 选 10 个任务人工复核 issue clarity 与 test correctness，估计自动标签误差；
5. 用同一 agent、同一模型运行 5 次，报告 mean、SEM、Pass@5；
6. 把环境失败单列，不计作 agent 错误。

项目报告应明确数据 cutoff、模型 release date、仓库重叠和 scaffold 配置。做到这些，你复现的就不只是一个小榜单，而是一套可持续评测协议。

## 13. 读完应能回答

1. 为什么训练数据集和 benchmark 子集需要不同质量门槛？
2. 时间晚于模型发布日期为何只能降低污染风险，不能证明无污染？
3. mean resolved 与 Pass@5 的差距说明什么？
4. 固定 scaffold 控制了什么变量，又牺牲了什么？
5. 自动化任务流水线中哪些失败不应计为 Agent failure？

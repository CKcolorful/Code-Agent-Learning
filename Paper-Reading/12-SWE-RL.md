# SWE-RL 详读：用软件演化数据和补丁相似度训练推理模型

论文：[SWE-RL: Advancing LLM Reasoning via Reinforcement Learning on Open Software Evolution](https://arxiv.org/abs/2502.18449)

官方代码：[facebookresearch/swe-rl](https://github.com/facebookresearch/swe-rl)

发表：NeurIPS 2025 Main Conference｜作者：Yuxiang Wei、Olivier Duchenne、Jade Copet 等

## 一句话结论

SWE-RL 绕开了为几十万 PR 构建执行环境的昂贵步骤：给模型 issue 与已定位代码，要求一次生成 search/replace patch，用预测 patch 与真实 PR patch 的字符串相似度作为连续奖励做 GRPO。它把 Llama-3.3-70B-Instruct 训练成更强的修复 reasoner，并在 Agentless Mini 中达到 SWE-bench Verified 41.0%；但它优化的是补丁代理奖励，不是多轮工具交互或真实测试正确性。

## 1. 先澄清：它不是完整 Agent Loop 上的 RL

SWE-RL 的训练样本已经包含 issue、要修复文件的完整内容以及相关但不修改的文件。模型在一次 rollout 中输出 reasoning 与 search/replace edits，生成期间没有执行搜索、编辑或测试，也没有获得中间环境 Observation。

训练问题更接近：

```text
(issue, oracle-localized context) -> reasoning + patch
```

部署到 SWE-bench 时，外部 Agentless Mini 再负责文件级定位、生成复现测试、选择回归测试和候选重排。论文的核心贡献是底层 patch policy，不应把 41.0% 全部解释为“模型经 RL 学会自主操作终端”。

## 2. 为什么软件演化数据适合规模化

GitHub PR 天然记录：修改前快照、issue/讨论、多个 commit 与最终 merged patch。作者从 GH Archive 收集 2015-01-01 到 2024-08-31 的事件，并克隆、处理约 460 万个仓库。

数据漏斗大致为：

```text
GitHub events + full git histories
        ↓
24M aggregated PRs
        ↓ filtering bots/noisy/non-code changes
11M unique PR instances
        ↓ high-quality issue-linked bug-fix selection
273k RL seeds
```

同时排除 SWE-bench 使用的仓库。为避免模型形成“输入中每个文件都必须修改”的偏差，作者让 Llama-3.1-70B-Instruct预测相关但未修改文件，把这些 hard negatives 加入上下文。

这一步值得注意：SWE-RL 不依赖 GPT-4/Claude 蒸馏轨迹，但数据预处理仍使用开源模型辅助，不是完全无模型数据工程。

## 3. Reward 是怎样定义的

若输出格式错误，奖励为 `-1`；否则提取预测与 ground-truth patch，用 Python `difflib.SequenceMatcher` 计算 `[0,1]` 相似度：

```text
R(o) = -1                                      if wrong_format
       similarity(patch_pred, patch_groundtruth) otherwise
```

同一问题采样一组输出，组内标准化 reward 得到 advantage，再用 GRPO 的 clipped objective 与 KL regularization 更新 policy。

这个 reward 极其便宜：不用构建 Docker、安装依赖、运行测试，也不需要奖励模型。它让 273k 规模的 PR 数据进入 RL 成为可能。

## 4. 连续相似度为什么比 exact match 更能训练

真实 patch 通常存在多个等价实现，exact match 奖励几乎总为 0。论文对照显示：

| Reward | 正确格式 | Oracle-file repair |
| --- | ---: | ---: |
| Exact-match 离散奖励 | 94.2% | 29.0% |
| Sequence similarity 连续奖励 | 95.6% | 34.8% |

连续 reward 能给部分正确的文件、代码块和文本变化提供渐进信号，训练增长更快。

但它仍不是语义正确性：复制官方 patch 的表面形式会高分，一个功能等价但写法不同的 patch 可能低分；加入无关文本、格式变化或大规模重构也会影响相似度。它是可扩展 proxy，不是 verifier 的替代品。

## 5. 模型学到的是定位还是修复

训练输入包含所有待修改文件的完整内容，所以细粒度定位发生在文件内部，文件级 localization 则已由数据提供。模型需要：

- 理解 issue；
- 在混入相关未修改文件时找到真正 edit location；
- 形成推理过程；
- 输出可应用的 search/replace block。

论文在 oracle-file repair 对照中显示：基础 Llama-3.3-70B greedy 只有 12.2% 格式正确、修复 5.4%；20 样本多数投票后为 44.6%/16.6%；SFT 为 96.2%/29.6%；SWE-RL 为 95.6%/34.8%。

因此 SFT 主要解决格式与任务适应，RL 在格式已接近饱和后继续提升修复推理。

## 6. Agentless Mini 怎样把模型接回系统

Agentless Mini 是一个可并行扩展的固定流水线：

```text
repo tree + issue
  -> 多样本文件定位
  -> 多样本 repair edits
  -> 生成并筛选 reproduction tests
  -> 选择 regression tests
  -> 执行 patches × tests
  -> consensus reranking
  -> final patch
```

相比完整 Agentless，它简化多级定位和 embedding retrieval，直接采样多个候选文件集合；生成测试时额外检索相关测试文件；重排同时参考回归测试与复现测试，并按 patch/test 共识组打分。

这意味着最终结果同时依赖模型能力与很强的 inference-time scaling。

## 7. 41.0% 到底用了多少推理预算

Llama3-SWE-RL-70B + Agentless Mini 在 SWE-bench Verified 达到 41.0%，对照 SFT 模型为 36.2%。论文的 scaling curve 显示：

- repair samples 从 20 增到 160，分数从 33.6% 增到 40.0%；
- 从 160 再增到 500，只从 40.0% 增到 41.0%；
- reproduction test samples 从 1 增到 20，约从 38.8% 增到 41.0%，20 后饱和。

所以 41.0% 不是单次模型调用的 Pass@1，而是大量 repair/test 候选经过执行与共识选择的系统 Best@1。公平比较时必须对齐 sample count、测试预算、oracle context 与 reranker。

## 8. 为什么作者强调 RL 而不是 SFT

作者用同一基础模型训练一个强 SFT baseline，混合合成 localization/editing、通用 coding 与 Llama 通用 SFT 数据。SFT 在主任务达到 36.2%，但部分域外任务下降。

SWE-RL 模型在 HumanEval+、CRUXEval、MATH 与 MMLU 等多个任务上相对基础模型保持或提升，尤其 MATH strict 从 63.2 提到 73.7，CRUXEval-I 从 60.5 提到 71.6；SFT 分别为 54.0 与 68.4。

这支持“RL 可能强化更一般的推理策略，而 SFT 更容易拟合输出分布”的解释。但域外增益的机制仍主要靠行为观察；不能从若干 benchmark 直接证明统一推理能力已经形成。

## 9. 与环境执行奖励相比的取舍

| 维度 | Patch similarity | Test execution |
| --- | --- | --- |
| 成本 | 很低，可扩到几十万 PR | 高，需可复现环境 |
| 信号密度 | 连续、容易学习 | 通常稀疏二值 |
| 语义正确性 | 弱，偏向官方写法 | 强，直接检查行为 |
| 多解容忍 | 较差 | 测试覆盖内较好 |
| Reward hacking | 模仿文本/格式 | 修改测试、利用环境漏洞 |

最佳路线可能是分阶段：先用相似度 reward 大规模学习 patch prior，再用少量可执行任务做 environment RL 或 rejection filtering 校正语义。

## 10. 论文局限与常见误读

1. **Oracle context**：训练时知道相关文件，部署时文件定位由外部 scaffold 完成。
2. **非交互 RL**：模型没有在训练 rollout 内调用终端和读取中间反馈。
3. **Proxy reward**：字符串相似并不保证测试通过，也会惩罚等价解。
4. **系统预算较大**：41.0% 使用最多 500 repair 与 30 test samples 的扩展配方，不能与单次 agent 直接横比。
5. **数据许可与时间**：海量 PR 数据需严格记录许可证、删除策略、cutoff 与仓库排除列表。
6. **推理“涌现”解释**：更长思考与域外分数提升是证据，不足以定位内部机制。
7. **评测是历史快照**：论文发表时的 SOTA 声明不应当作当前排行榜。

## 11. 对 Code Agent 项目的启示

SWE-RL 展示了一个实用的训练分层：

```text
Layer 1: PR-scale patch policy training
Layer 2: Harness localization / tool behavior
Layer 3: Execution verifier and candidate selection
```

不要期待一个训练目标同时解决三层。若项目只训练 repair model，就应在 README 中明确 oracle 文件条件；若声称训练 Agent，则必须把工具轨迹和环境 Observation 纳入训练或至少评测。

Verifier 也可以分级：训练早期用便宜的 patch similarity 提供 dense reward，后期用 compile/tests、静态分析和人工偏好纠偏。

## 12. 最小复现实验

选择 5,000 个许可清晰的 issue-linked PR，按仓库切分训练/验证：

1. 构造 issue、changed files、相关未修改文件和 ground-truth patch；
2. 让 3B–7B 模型输出统一 search/replace 格式；
3. 比较 exact-match、SequenceMatcher、AST edit distance 三种 reward；
4. 在 100 个可构建任务上额外跑测试，测 proxy reward 与真实成功的相关性；
5. 对相似度高但测试失败、相似度低但测试成功的样本做 error analysis；
6. 用同一个定位/重排 scaffold 比较 Base、SFT、RL。

这个实验最有价值的结果未必是最终分数，而是回答：什么 proxy 在多大程度上预测真实执行正确性，以及 reward mismatch 会训练出什么偏差。

## 13. 读完应能回答

1. SWE-RL 的 rollout 为什么不是多轮环境交互？
2. 连续 patch similarity 解决了 exact match 的什么问题，又引入什么偏差？
3. 41.0% 中模型训练与 inference-time scaling 各扮演什么角色？
4. 为什么训练时要加入相关但未修改的文件？
5. 如何把便宜 proxy reward 与昂贵 test reward 组合成分阶段训练？

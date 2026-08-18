# SWE-Gym：训练 Agent，也训练 Verifier

论文：[Training Software Engineering Agents and Verifiers with SWE-Gym](https://arxiv.org/abs/2412.21139)

官方代码与数据入口：[SWE-Gym/SWE-Gym](https://github.com/SWE-Gym/SWE-Gym)

## 一句话结论

训练 Code Agent 需要的不只是“issue 到 gold patch”的静态样本，而是带可执行环境、测试奖励和多轮 action/observation 的任务；同一批轨迹还能训练 verifier，在推理时从多个候选解中选出更可能成功的一个。

## 1. SWE-Gym 补上了什么缺口

SWE-bench 最初主要是评测集。虽然可以收集大量 GitHub issue/PR 对做监督训练，但没有可安装环境和可靠测试，就无法让 agent 在任务中执行命令、得到增量反馈，也无法自动判断整条轨迹是否成功。

SWE-Gym 提供 2,438 个来自 11 个 Python 仓库的真实任务，每个任务包含：

- 自然语言 issue；
- 指定版本的完整代码库；
- 预配置可执行环境；
- 专家编写并验证的测试；
- 可用于训练的成功/失败奖励。

这些仓库与 SWE-bench 评测仓库分离，以降低直接数据污染。另有 64,689 条 SWE-Gym Raw issue，但它们没有完整可执行环境和可靠测试保证，所以价值与可验证的 2,438 条不同。

## 2. 为什么静态 Patch SFT 不够

只训练：

```text
Issue + Code Context -> Gold Patch
```

模型学到的是一次性映射，却未必学会：怎样搜索文件、怎样读取测试失败、何时停止无效方向、怎样修改后再验证。真正 agent 的监督单位更像：

```text
Task
  -> Action 1 / Observation 1
  -> Action 2 / Observation 2
  -> ...
  -> Git Diff
  -> Tests / Reward
```

论文中成功轨迹平均约 19 轮、约 19k tokens。训练这些轨迹，不只是教模型“最后 patch 长什么样”，还在教控制策略：工具格式、探索顺序、错误恢复和终止行为。

## 3. 论文怎样训练 Policy

作者使用两个 scaffold：

- **OpenHands CodeAct**：通用 ReAct 风格，由模型自己规划并使用 bash 与文件编辑器；
- **MoatlessTools**：更结构化的专业工作流。

基础算法很简单：**rejection sampling fine-tuning**，也叫 filtered behavior cloning。

1. 用较强模型在 SWE-Gym 环境中采样完整轨迹；
2. 执行测试，保留成功轨迹；
3. 用成功轨迹微调目标模型；
4. 在同一 scaffold 中部署并评测。

论文用 GPT-4o 与 Claude 3.5 Sonnet 采样到 491 条成功轨迹，微调 Qwen2.5-Coder-Instruct。32B 模型在 OpenHands scaffold 下，SWE-bench Lite 从 3.0% 提升到 15.3%，Verified 从 7.0% 提升到 20.6%。

除了成功率，行为指标也有意义：微调通常降低 empty patch 比例和连续重复同一 action 的 stuck-in-loop 比例。这证明 trajectory SFT 学到了一部分“如何作为 agent 行动”，而不只是更好的代码先验。

## 4. Verifier 是什么

即使 policy 单次成功率不高，只要多次采样能产生至少一个正确候选，就可以通过选择器提升最终结果。SWE-Gym 用测试把轨迹标为成功或失败，然后训练 outcome-supervised reward model（ORM）。

对 OpenHands 轨迹，verifier 输入包括：

- 问题描述；
- 交替的 observations 与 actions；
- 命令输出和错误；
- 当前 git diff。

模型输出 `<YES>` 或 `<NO>`，其概率作为成功分数。推理时对同一任务采样 `k` 条轨迹，由 verifier 选择最高分候选：

```text
Task
  -> Policy samples trajectory_1 ... trajectory_k
  -> Verifier scores each trajectory
  -> choose argmax(score)
  -> submit selected patch
```

这就是 inference-time scaling：不改变一次 rollout 的模型规模，而是用更多采样计算换取更高的“至少一个正确候选”概率，再由 verifier 尽量找出来。

## 5. Pass@k、Best@k 与 Selector Gap

理解这篇论文要区分三个概念：

- **Pass@k**：k 个候选中是否至少有一个正确，代表生成器的候选覆盖上限。
- **Best@k**：由现实 verifier 从 k 个候选选一个后的实际成绩。
- **Selector gap**：Pass@k 与 Best@k 的差，反映 verifier 没能认出正确候选。

论文报告结合微调 agent 与 verifier 后，达到 SWE-bench Verified 32.0%、Lite 26.0% 的历史结果。更重要的是，32B verifier 随 k 增大继续提升，而 7B verifier 较早平台，说明 selector 能力本身会限制推理扩展。

## 6. Verifier 训练数据为什么讲究 on-policy

论文把两类数据混合：

- **off-policy**：由更强的 GPT/Claude 生成；
- **on-policy**：由当前微调 Qwen policy 生成。

只用强模型轨迹，verifier 可能不熟悉目标 policy 特有的失败方式；只用 on-policy，样本多样性和成功模式又不足。论文消融中两者混合最好，而且成功/失败样本需要合理平衡。

这是通用规律：verifier 要在部署分布上识别“看起来合理但实际上失败”的解，训练数据必须包含目标 agent 真正会犯的错。

## 7. Environment 为什么是训练资产

测试提供可扩展奖励：无需人工逐条阅读轨迹，就能判断最终仓库状态是否满足要求。但环境构建非常昂贵：历史依赖可能失效，不同仓库安装方式不一，测试可能不稳定，镜像和运行资源消耗巨大。

SWE-Gym 的贡献因此不仅是数据条目数，而是把每个任务变成可重复执行的 MDP-like 环境。只有这样才能做：

- 在线 rollout；
- 失败重试和策略改进；
- rejection sampling；
- verifier 标注；
- 强化学习；
- 训练时与推理时计算扩展。

## 8. 局限与风险

- 2,438 个任务仍集中在 Python 和 11 个仓库，语言与项目分布有限。
- 491 条成功轨迹受采样成本限制，不能证明数据规模已充分。
- 测试是结果奖励，不一定覆盖可维护性、安全性和隐藏语义。
- outcome verifier 可能学习表面相关性，例如“测试输出看起来更干净”，而非真正理解 patch。
- 反复在固定 benchmark 上调 scaffold、训练和选择器会形成 benchmark overfitting。
- 论文主要评测自主完成，不涵盖真实开发中重要的需求澄清、代码评审与人机协作。

## 9. 自己做训练系统的最小数据结构

每条轨迹至少应保存：

```text
task_id / repository / base_commit
issue_text
environment_image + dependency metadata
ordered actions and observations
tool errors / timeouts / token and cost usage
final git diff
visible test results
held-out evaluator results
success label + failure category
model / scaffold / prompt / sampling configuration
```

如果没有这些元数据，后续很难判断提升来自模型、工具、环境、数据泄漏还是 verifier 偏差。

## 10. 十分钟速读

1. 看 Table 1，理解“静态真实任务”和“可执行训练环境”的差别。
2. 读 Section 3，关注环境构建、仓库隔离和数据难度。
3. 读 Section 4.2，理解 491 条成功轨迹怎样用于 SFT。
4. 精读 Section 5.1，画出 policy sampling 与 verifier reranking。
5. 看 on/off-policy verifier 消融和 scaling 曲线。

## 11. 读完应该带走什么

SWE-Gym 把 Code Agent 训练的最小单位从 patch 改成了**可验证的交互轨迹**。它也指出下一阶段的核心竞争不只是更强 policy，而是三者共同扩展：高质量环境产生可靠奖励，policy 提高候选覆盖，verifier 缩小 selector gap。

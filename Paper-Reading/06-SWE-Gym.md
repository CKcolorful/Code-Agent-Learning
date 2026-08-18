# SWE-Gym 详读：训练 Software Engineering Agent 与 Verifier

论文：[Training Software Engineering Agents and Verifiers with SWE-Gym](https://arxiv.org/abs/2412.21139)

官方代码：[SWE-Gym/SWE-Gym](https://github.com/SWE-Gym/SWE-Gym)

作者：Michael H. Jimenez 等｜首次提交：2024 年 12 月

## 一句话结论

SWE-Gym 把真实仓库问题、可执行环境、完整 agent trajectory 和测试奖励连接成训练闭环。它表明训练 Code Agent 不能只拿最终 gold patch 做 SFT；还要让 policy 学会多轮工具行为，并训练 verifier 从多个候选轨迹中选择更可能真正解决任务的结果。

## 1. 它补的是哪一块缺口

前五篇逐步定义了：循环、任务、接口、pipeline 与平台。但这些工作大多把底层 LLM 当作现成能力。SWE-Gym 追问：怎样让模型本身更适合在真实软件环境中行动？

静态 code instruction 数据通常是：

```text
problem + code context -> final answer/patch
```

而软件工程 agent 的真实数据结构是：

```text
issue + repository state
  -> action_1 -> observation_1
  -> action_2 -> observation_2
  -> ...
  -> patch
  -> executable reward
```

二者的差别在于：模型不仅要学“正确代码是什么”，还要学“未知责任位置时先做什么”“测试失败后怎样恢复”“什么时候该停止”。

## 2. 数据集：三个规模对应三种用途

SWE-Gym 从真实 GitHub issue/PR 构造训练任务，核心数据规模为：

- **SWE-Gym**：2,438 个有可执行环境的真实任务，来自 11 个 Python 仓库；
- **SWE-Gym Lite**：230 个较轻量的任务子集，便于快速实验；
- **SWE-Gym Raw**：64,689 个尚未构建可执行环境的原始问题。

Raw 规模大，却不能直接提供可靠执行奖励；2,438 个可执行任务规模较小，但每个任务能在真实历史环境中验证 patch。论文因此强调：对于 agent 训练，环境可执行性是一种昂贵、高价值标注。

## 3. 任务环境是怎样构造的

构造逻辑与 SWE-bench 相似：找到解决 issue 的 PR，确定修复前 base commit，分离 solution/test patch，建立依赖环境，并验证测试状态转换。

但训练场景比评测多一层要求：环境会被反复 rollout。它必须支持：

- 每次采样从干净 base state 开始；
- 工具动作能稳定读写同一 workspace；
- 轨迹结束后提取候选 diff；
- 自动执行测试得到 reward；
- 保存失败原因，而不是只保存 0 分；
- 训练仓库与最终评测仓库保持适当隔离。

一个任务可表示为 MDP/POMDP：

- 状态 `s_t`：文件系统、进程、依赖、当前目录等完整环境；
- 观察 `o_t`：工具暴露给模型的有限文本；
- 动作 `a_t`：搜索、查看、编辑、执行、提交；
- 转移 `s_{t+1} = f(s_t, a_t)`；
- 终局奖励 `r ∈ {0,1}`：patch 是否通过目标与回归测试。

模型看不到完整 `s_t`，只能从历史观察估计状态，所以软件 agent 实际更接近部分可观测决策过程。

## 4. 为什么只用 Gold Patch 做 SFT 不够

Gold patch 告诉模型“维护者最终改了哪些行”，却隐藏了完成任务所需的行为：

- 如何从 issue 找到文件；
- 阅读了哪些调用方与测试；
- 哪个早期假设被证伪；
- 怎样构造复现；
- 编辑后跑了哪些命令；
- 何时有足够证据提交。

若只训练最终 patch，推理时模型仍面对一个 distribution gap：训练输入已经包含正确上下文，部署输入却是整个仓库。

轨迹监督将目标改为学习条件策略：

```text
πθ(a_t | issue, o_1, a_1, ..., o_t)
```

每一步都学习在当前观察下的下一动作。环境 Observation 不是模型自由生成的标签，而是执行真实动作后返回的状态。

## 5. 成功轨迹从哪里来：Rejection Sampling

论文先用强模型在 SWE-Gym 环境中 rollout，执行测试判断结果，再保留成功轨迹作为监督数据。

报告的数据包括约 491 条成功轨迹，平均约 19 个交互轮次、19k token。轨迹由 GPT-4o、Claude 等强模型采样得到，再用于微调 Qwen2.5-Coder 系列开源模型。

这个流程叫 rejection sampling：

```text
for task in SWE-Gym:
    trajectories = rollout(teacher_policy, task)
    for τ in trajectories:
        reward = execute_and_test(τ.final_patch)
        if reward == 1:
            keep(τ)
```

优点是标签由环境验证，不依赖人工逐步标注。缺点是只保留成功会产生选择偏差：学生主要看到老师能解决的任务和路径，较少学习如何从失败恢复。

## 6. Policy 微调到底学习了什么

训练样本包含问题、工具规范和多轮 trajectory。监督损失可抽象为只在模型动作 token 上计算交叉熵：

```text
L_policy(θ) = - Σ_t log πθ(a_t^* | h_t)
```

其中 `h_t` 是截至当前的 issue、动作与真实 Observation 历史。实际实现还要决定：

- Thought 是否参与 loss；
- Observation 和系统 prompt 是否 mask；
- 超长轨迹如何截断；
- 是否保留失败后成功恢复的片段；
- tool schema 是否与部署时完全一致。

ACI 不一致会破坏迁移：训练时学的是一种命令语言，部署时换成另一种 editor 或 Observation 格式，模型即使理解任务也可能不会正确操作。

## 7. Policy 结果：数字逐项解释

论文报告基于 OpenHands 工具环境训练的 32B 模型，在 SWE-bench Lite 上从约 3% 提升到 15.3%，在 SWE-bench Verified 上从约 7% 提升到 20.6%。

这不是只说明“模型更会写 patch”。轨迹分析还观察到训练后：

- 空 patch/未修改就提交减少；
- 重复动作与无效循环减少；
- agent 更常执行符合任务阶段的搜索、编辑和测试；
- 在相同工具环境中，完成任务的行为更稳定。

这些行为指标很重要。若 resolved rate 上升但循环率、空 patch 和环境错误不变，就难以判断模型是否真正学会 agent 行为，还是只记住了某些仓库模式。

## 8. Tool specialization：为什么更窄的环境可能更易学

论文还比较 OpenHands 这种通用环境与 MoatlessTools 等更专门的工具设置。零样本时，7B/32B 模型在专用工具上的 Lite 表现约为 7%/19%，而在 OpenHands 通用环境约为 1%/3%。

合理解释是 action horizon 和动作熵：

- 专用工具把定位、查看或编辑压缩为更少、更规则的动作；
- 通用 shell/code action 表达力强，但模型需要同时学命令语法、输出处理与任务策略；
- 对较小模型，减少无关动作空间比增加自由度更有帮助。

这延续了 SWE-agent 的 ACI 结论：工具接口不仅影响推理时表现，也影响训练难度和所需数据量。

## 9. Verifier 的任务定义

当 policy 对同一 issue 采样多个候选时，Pass@k 可能很高，但系统必须从不可见 hidden tests 的条件下选出一个提交。SWE-Gym 训练 Outcome Reward Model（ORM）作为 verifier。

Verifier 的输入包括：

- problem statement；
- agent trajectory；
- 最终 git diff。

输出是该轨迹/patch 是否会成功的判断，例如 `YES/NO` 或成功分数：

```text
vφ(issue, trajectory, diff) -> P(success)
```

训练标签来自真实执行结果，而不是另一个模型的主观偏好。

## 10. Pass@k、Best@k 与 Selector Gap

对每个任务采样 `k` 条轨迹：

- **Pass@k**：只要其中至少一条正确就算成功，是使用 oracle 选择器的生成上界；
- **Best@k**：用 verifier 选最高分候选，看选中者是否正确，是实际可部署指标。

若单条独立成功概率为 `p`，理想独立采样下：

```text
Pass@k = 1 - (1 - p)^k
```

真实候选高度相关，因此增长通常低于该公式。Best@k 还受 verifier 限制：候选越多，既增加正确答案出现概率，也增加“看起来合理”的干扰项。

```text
Selector Gap = Pass@k - Best@k
```

Agentless 已展示 candidate oracle 42% 对最终 32% 的差距；SWE-Gym 则尝试用学习式 verifier 缩小它。

## 11. 为什么 verifier 训练数据必须接近 on-policy

Verifier 若只看 gold patch 与随机错误 patch，很容易学到肤浅线索：patch 是否短、格式是否规范、是否含测试。部署时它面对的却是同一个 policy 生成的、彼此都很合理的 hard negatives。

因此论文混合：

- **off-policy 轨迹**：来自其他模型/策略，增加覆盖和规模；
- **on-policy 轨迹**：来自当前待选择 policy，匹配真实错误分布。

这与分类器数据分布一致性相同。Verifier 必须见过“当前 policy 最擅长犯的错”，才能在多个近似 patch 中区分。

训练损失可抽象为二分类：

```text
L_verifier(φ) = - y log vφ(x) - (1-y) log(1-vφ(x))
```

但任务级样本不平衡、同一 issue 内候选相关、执行标签偶有基础设施噪声，都需要在采样和评估时处理。

## 12. Verifier 结果怎么读

论文中 32B verifier 通过 best-of-k selection 在 SWE-bench Verified 上达到约 32%、Lite 上约 26%。同时观察到：

- 7B verifier 到 `k=4` 左右趋于平台；
- 32B verifier 在 `k=8` 仍能从更多候选中获益。

这说明 selector capacity 会决定 inference-time scaling 是否兑现。生成更多候选并不自动提升提交质量；弱 verifier 可能在候选增多后被 hard negatives 迷惑。

比较 verifier 时还要确认候选 generator 是否相同。更强生成器会同时提高 Pass@k，也可能制造更难区分的错误候选。

## 13. 为什么 trajectory 是 verifier 的有用输入

只看 final diff，两个候选可能都很合理。轨迹提供过程证据：

- agent 是否成功复现 issue；
- 修改前是否读过相关契约；
- 测试是否真的执行且退出码为 0；
- 是否只跑了无关测试；
- 是否在最后一步引入未验证修改；
- 是否出现循环、错误被忽略或空 patch。

但 trajectory 也可能误导：模型会写出很有说服力的解释，测试日志可能截断，长轨迹会淹没关键证据。因此 verifier 应优先利用可验证事件和 diff，而非把流畅 reasoning 当作正确性证明。

## 14. Environment 为什么是训练资产

一个可执行环境同时提供四类监督：

1. **终局奖励**：patch 是否解决任务。
2. **中间反馈**：命令退出码、测试失败、语法错误。
3. **候选比较**：同一 issue 下不同轨迹的相对结果。
4. **错误数据**：失败轨迹可训练 verifier 或恢复策略。

因此构建环境的成本可以被多次摊销到 SFT、拒绝采样、best-of-k、verifier 和强化学习。相比只发布静态 patch 对，SWE-Gym 更像一个可重复采样的训练场。

## 15. 数据污染与泛化

SWE-Gym 来自公开 GitHub，仍存在预训练记忆风险。更重要的是，训练任务集中在有限 Python 仓库：模型可能学会这些项目的目录、测试命令和常见修复模式。

评估设计要区分：

- **instance-disjoint**：新 issue，但可能同一仓库；
- **time-disjoint**：训练截止时间之后的任务；
- **repo-disjoint**：完全不同的仓库；
- **language-disjoint**：不同编程语言与构建生态。

repo-disjoint 的下降能更直接衡量“软件工程策略”是否迁移，而不是仓库记忆。

## 16. 方法局限

- 2,438 个可执行任务相对模型规模仍小，成功轨迹更只有数百条。
- Rejection sampling 丢弃大量失败信息，不直接教模型怎样恢复。
- Teacher 成功分布限制 student 上限，难题几乎没有正轨迹。
- 二元终局奖励稀疏，不能指出是哪一步导致失败。
- Verifier 可能学习 repository/style shortcut，而非真正语义正确性。
- 测试标签受环境和测试覆盖质量限制；“通过”不等于完整正确。
- 轨迹长达约 19k token，训练成本高，截断策略会影响行为学习。
- 工具接口绑定明显，换 ACI 可能需要重新采样或适配训练。

## 17. 从这篇论文推导出的训练路线

一个务实路线不是直接上在线 RL，而是分层构建：

```text
1. 构建可重放任务环境
2. 用强模型采样多条轨迹
3. 执行测试，保存成功与失败
4. 用成功轨迹 SFT policy
5. 用混合 on/off-policy 结果训练 verifier
6. 对 policy 重新采样，做 best-of-k
7. 分析 selector gap 与失败轨迹
8. 再决定是否需要 DPO/RL 或过程奖励
```

每一步都有独立指标，避免把所有问题都归因于“训练不够”。

## 18. 官方代码怎么读

SWE-Gym 仓库主要提供数据、环境和训练/评测脚本。建议：

1. [`README.md`](https://github.com/SWE-Gym/SWE-Gym/blob/main/README.md)：先确认数据集、模型和发布资源。
2. [`docs/`](https://github.com/SWE-Gym/SWE-Gym/tree/main/docs)：读取数据与运行说明。
3. [`scripts/`](https://github.com/SWE-Gym/SWE-Gym/tree/main/scripts)：追踪轨迹生成、处理和评测命令。
4. 查看发布 trajectory 的字段：problem、messages/actions、observations、patch、reward、instance id。
5. 对一个 instance 对齐 SWE-Gym 数据、OpenHands rollout 和 SWE-bench evaluator 的输入输出。

源码阅读重点是数据 lineage：一个 GitHub PR 如何变成环境，一个 rollout 如何变成训练样本，一个测试结果如何变成 verifier 标签。

## 19. 常见误读

- **“SWE-Gym 就是更大的 SWE-bench。”** 它主要面向训练，强调环境和轨迹，而非只做排行榜。
- **“用 gold patch SFT 与用成功轨迹 SFT 差不多。”** 前者没有工具决策和错误恢复状态。
- **“Pass@k 高说明系统提交能力强。”** Pass@k 使用 oracle，真实系统还受 selector 限制。
- **“Verifier 看过测试结果，所以等同运行 hidden tests。”** 它只从可见轨迹/diff预测，不能访问评测隐藏判据。
- **“候选越多，Best@k 一定越高。”** 弱 verifier 会随 hard negatives 增多而饱和或下降。
- **“成功轨迹全是高质量示范。”** 轨迹可能绕路、偶然通过或包含不必要动作，仍需过滤。
- **“32B 的提升都来自代码生成。”** 行为指标表明工具使用、终止和循环也发生变化。

## 20. 可复现练习

### 练习一：构造最小 trajectory dataset

选择 30 个可执行任务，每题采样 4 条轨迹。保存完整事件、最终 diff、测试结果、token 和耗时。只将模型动作作为训练 target，mask 环境 Observation。

### 练习二：画 Pass@k / Best@k 曲线

用同一批候选计算 `k=1,2,4,8` 的 oracle Pass@k 和 verifier Best@k。若两条曲线逐渐分离，优先优化 verifier；若一起很低，优先优化 policy 或候选多样性。

### 练习三：On-policy verifier 消融

分别用 off-policy、on-policy、混合数据训练相同 verifier，再在当前 policy 候选上比较 AUROC、任务级 top-1 与 Best@k。分类准确率高不一定意味着任务内排序好，后者更重要。

### 练习四：失败轨迹再利用

把失败分成定位错、编辑格式错、测试失败、空 patch、超时和循环。尝试只用“失败后成功恢复”的片段做 SFT，比较是否降低对应行为错误。

## 21. 读完后的检查题

1. 为什么可执行环境比静态 patch 对提供更丰富监督？
2. Rejection sampling 为什么会产生 teacher-selection bias？
3. Policy 与 verifier 的 on-policy 分布分别指什么？
4. Pass@k 上升而 Best@k 不变时，最可能的瓶颈在哪里？
5. 为什么工具接口改变后，旧 trajectory 可能不再是有效训练数据？
6. Verifier 应怎样区分“测试真的通过”和“模型声称测试通过”？

## 22. 最终要带走的观点

SWE-Gym 把 Code Agent 训练从“模仿一个最终 diff”推进到“学习在可执行世界中的状态化行为”：**环境产生可信奖励，轨迹教会 policy 如何行动，多候选扩大搜索，verifier 决定 inference-time compute 能否转化为真实成功率。** 训练系统的核心资产不是单一模型权重，而是任务环境、轨迹数据、执行标签与选择器共同构成的闭环。

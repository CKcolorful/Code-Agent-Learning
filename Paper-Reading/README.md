# Code Agent 论文阅读路线：从 Agent Loop 到数据、评测与强化学习

如果这里的 Code Agent 指的是“能进入真实环境、搜索代码、调用终端、修改文件、运行测试并迭代完成任务”的 coding agent，那么值得学习的并不是某一张榜单，而是支撑系统演进的几条主线：**交互循环、任务定义、动作接口、上下文与运行时、可执行数据、持续评测、终端泛化、policy training 与 verifier**。

这里的 12 篇文档不是摘要合集。每篇都试图回答：论文修正了什么假设、方法的数据流与公式是什么、对照实验控制了哪些变量、数字能推出什么和不能推出什么、失败发生在哪个模块、怎样映射回真实 harness，以及用什么小实验能复现关键因果关系。

## 12 篇主线索引

| 顺序 | 论文 | 发表 | 它回答的核心问题 | 详细解读 |
| --- | --- | --- | --- | --- |
| 1 | [ReAct](https://arxiv.org/abs/2210.03629) | ICLR 2023 | 模型如何在推理、行动和环境反馈之间形成闭环？ | [01-ReAct.md](./01-ReAct.md) |
| 2 | [SWE-bench](https://arxiv.org/abs/2310.06770) | ICLR 2024 | 仓库级 issue resolution 怎样构造任务并判定成功？ | [02-SWE-bench.md](./02-SWE-bench.md) |
| 3 | [SWE-agent](https://arxiv.org/abs/2405.15793) | NeurIPS 2024 | 搜索、浏览、编辑和执行工具怎样设计得适合模型？ | [03-SWE-agent.md](./03-SWE-agent.md) |
| 4 | [Agentless](https://arxiv.org/abs/2407.01489) | FSE 2025 | 结构化 pipeline 何时能替代复杂自主循环？ | [04-Agentless.md](./04-Agentless.md) |
| 5 | [OpenHands](https://arxiv.org/abs/2407.16741) | ICLR 2025 | 怎样把研究原型扩展为事件驱动、可隔离的平台？ | [05-OpenHands.md](./05-OpenHands.md) |
| 6 | [SWE-Gym](https://arxiv.org/abs/2412.21139) | ICML 2025 | 怎样用可执行轨迹训练 Agent 与 outcome verifier？ | [06-SWE-Gym.md](./06-SWE-Gym.md) |
| 7 | [CodeAct](https://proceedings.mlr.press/v235/wang24h.html) | ICML 2024 | 为什么可执行代码可以成为统一、可组合的动作空间？ | [07-CodeAct.md](./07-CodeAct.md) |
| 8 | [SWE-smith](https://arxiv.org/abs/2504.21798) | NeurIPS 2025 D&B Spotlight | 怎样在可复用环境中规模化合成可执行训练任务？ | [08-SWE-smith.md](./08-SWE-smith.md) |
| 9 | [SWE-rebench](https://arxiv.org/abs/2505.20411) | NeurIPS 2025 D&B | 怎样持续采集真实任务，并按时间控制评测污染？ | [09-SWE-rebench.md](./09-SWE-rebench.md) |
| 10 | [Terminal-Bench 2.0](https://arxiv.org/abs/2601.11868) | ICLR 2026 | 离开固定 issue-to-patch 形式后，怎样评测通用终端工作？ | [10-Terminal-Bench-2.md](./10-Terminal-Bench-2.md) |
| 11 | [Training Long-Context, Multi-Turn SWE Agents with RL](https://arxiv.org/abs/2508.03501) | arXiv 2025 | 怎样在长上下文、多轮环境交互上稳定做 on-policy RL？ | [11-Long-Context-Multi-Turn-SWE-RL.md](./11-Long-Context-Multi-Turn-SWE-RL.md) |
| 12 | [SWE-RL](https://arxiv.org/abs/2502.18449) | NeurIPS 2025 | 怎样用海量 PR 和补丁相似度训练软件修复推理模型？ | [12-SWE-RL.md](./12-SWE-RL.md) |

> 发表信息以论文版本与官方 proceedings 为准。第 11 篇当前按预印本标注；“进入阅读路线”不等于“已经发表于顶会”。

## 不必机械按编号读

### 想实现最小 Code Agent harness

建议顺序：**ReAct → SWE-agent → CodeAct → OpenHands → Terminal-Bench 2.0**。

这条路线依次回答 Agent Loop、ACI、可编程动作、事件/运行时架构和终端评测。读完后应该能实现一个带预算、隔离、轨迹记录和 verifier 的最小系统，而不只是 `while + LLM + shell`。

### 想做训练数据与 benchmark

建议顺序：**SWE-bench → SWE-Gym → SWE-smith → SWE-rebench → Terminal-Bench 2.0**。

这条路线从历史任务恢复，走到环境优先的合成数据、持续真实任务和 outcome-based 终端评测。重点追踪 F2P/P2P、环境复现、任务质量、时间污染与评分完整性。

### 想训练开源 SWE 模型

建议顺序：**SWE-Gym → SWE-smith → SWE-rebench → Long-Context Multi-Turn SWE RL → SWE-RL**。

先理解 trajectory SFT 与 verifier，再比较两种规模化数据源，最后对照两类 RL：一个优化完整多轮行为，一个优化单轮 patch policy。两者名字相近，训练对象和奖励完全不同。

### 想研究 pipeline 与 autonomous agent 的边界

建议顺序：**SWE-agent → Agentless → CodeAct → SWE-RL → Long-Context Multi-Turn SWE RL**。

这条路线能看到三种不同的计算放置方式：模型逐步决策、人工固定阶段、模型在一次代码动作内组合工具。没有一种结构在所有模型和任务上统治。

## 12 篇怎样拼成一张系统图

```text
ReAct
  Thought -> Action -> Observation 的最小闭环
      |
      v
SWE-bench ---- 定义 Issue + Repo -> Patch -> Tests
      |
      +----------------------+----------------------+
      |                      |                      |
      v                      v                      v
SWE-agent                Agentless               CodeAct
优化 ACI/自主交互        固定定位-修复流水线       可编程动作空间
      \                      |                     /
       \                     |                    /
        +--------------------v-------------------+
                             OpenHands
                 Agent + Event Stream + Runtime + Sandbox
                                  |
                +-----------------+------------------+
                |                                    |
                v                                    v
             SWE-Gym                            Terminal-Bench 2.0
        轨迹训练 + Verifier                 通用终端任务 + Harbor
                |
        +-------+------------------+
        |                          |
        v                          v
   SWE-smith                  SWE-rebench
环境优先的合成任务          真实任务自动恢复 + 滚动评测
        \                          /
         +-----------+------------+
                     |
          +----------+-----------+
          |                      |
          v                      v
Long-Context Multi-Turn RL     SWE-RL
真实多轮执行 + 测试奖励       单轮补丁 + 相似度奖励
```

## 阅读时始终追踪的八个问题

1. **状态是什么？** 模型当前能看见 issue、哪些文件、哪些历史动作、哪些进程与测试输出？
2. **动作空间是什么？** 任意 shell、专用工具、JSON call、可执行代码，还是固定 pipeline 阶段？
3. **观察怎样压缩？** 搜索结果、文件片段、stdout/stderr 怎样避免挤爆上下文？
4. **正确性由谁判断？** 公开测试、隐藏测试、生成测试、补丁相似度、学习式 verifier，还是人工？
5. **数据从哪里来？** 真实 PR、合成 bug、老师成功轨迹，还是当前 policy 的 on-policy rollout？
6. **失败怎样恢复？** 重试、回滚、重新定位、多候选、切换策略、退出循环，还是 abstain？
7. **预算花在哪里？** 模型轮次、解释器内工具调用、并行候选、长上下文、测试执行还是 verifier？
8. **分数绑定哪些配置？** model、scaffold、prompt、task revision、sample count、测试预算和时间 cutoff 是否完整？

## 新增六篇的核心差异

| 论文 | 研究对象 | 任务/数据来源 | 环境是否逐步反馈 | 主要监督或奖励 | 主要风险 |
| --- | --- | --- | --- | --- | --- |
| CodeAct | 动作语言与 tool use | API-Bank、82 个 M3ToolEval 任务、7k 轨迹 | 是 | 答案/任务成功与轨迹 SFT | 任意代码执行与审计边界 |
| SWE-smith | 可执行训练数据生成 | 128 个真实仓库中的合成 bug | rollout 时是 | 既有测试 + 老师成功轨迹 | synthetic-to-real gap、测试泄漏 |
| SWE-rebench | 真实任务收集与滚动评测 | GitHub issue/PR | 是 | F2P/P2P + 质量标签 | 自动安装/标签噪声、时间不等于绝对无污染 |
| Terminal-Bench 2.0 | 通用终端 Agent | 89 个专家工作流任务 | 是 | 终局容器状态测试 | verifier exploit、公开任务污染 |
| Long-Context Multi-Turn RL | 完整多轮 policy | 7,249 个 SWE-rebench 任务 | **是** | 终局测试二值奖励 + 步数惩罚 | 稀疏信用分配、rollout 分布偏差 |
| SWE-RL | 单轮 patch reasoner | 273k PR seed | **否** | 与 oracle patch 的字符串相似度 | proxy reward 与语义正确性错位 |

## 关键数字索引

这些数字用于快速回到原论文的实验上下文，不用于跨年份直接排名：

| 论文 | 关键数字 | 用来理解什么 |
| --- | --- | --- |
| ReAct | ALFWorld 71% vs Act 45%；WebShop 40.0% vs 30.1% | 显式状态维护对长程行动的作用 |
| SWE-bench | 2,294 个任务、12 个 Python 仓库；早期 Claude 2 约 1.96% | 仓库级修复与环境恢复的难度 |
| SWE-agent | Lite 18.0% vs shell-only 11.0%；去 editor 后 10.3% | 固定模型下 ACI 的因果影响 |
| Agentless | 最终 96/300；候选 oracle 126/300 | 生成上界与 selector gap |
| OpenHands | 统一评测 15 个 benchmark | 平台重点是统一承载与复现 |
| SWE-Gym | 2,438 个环境；约 491 条成功轨迹 | 可执行任务怎样变成 policy/verifier 数据 |
| CodeAct | 82 个复杂任务；最高绝对提升 20.7 点，少 2.1 轮 | 控制流/数据流对工具组合的作用 |
| SWE-smith | 50,137 任务、128 仓库；32B 模型 Verified 40.2% | Environment-first 的数据扩展能力 |
| SWE-rebench | 21,336 训练任务；294 题/169 仓库评测 | 真实任务自动恢复与滚动评测 |
| Terminal-Bench 2.0 | 89 题、32,155 trials；最佳组合仍低于 65% | 通用终端长程任务仍未饱和 |
| Long-Context Multi-Turn RL | 11.4 → 20.5 → 35.7 → 39.0；131k/80 轮 | RFT、两阶段 DAPO 与长程交互训练 |
| SWE-RL | 273k PR seed；Agentless Mini Verified 41.0% | 便宜连续 proxy reward 的规模优势 |

## 哪些分数不能直接横比

```text
Pass@1  vs Pass@k / Best@k
单次 agent rollout vs 数百 repair samples + reranking
oracle localized files vs 从整个仓库定位
固定中性 scaffold vs 每个模型最佳原生 agent
老 benchmark vs 发布时间后的 fresh tasks
patch similarity training reward vs executable test reward
```

看到一个新分数时，先找 model、scaffold、task revision、attempt count、context limit、测试可见性和 selector。缺少这些条件的“超过某模型”没有可靠解释力。

## 配套实践路线

按成本从低到高，可以把阅读转成一个连续项目：

1. 实现 `observe -> act -> execute -> append observation` 最小循环，保存结构化 trajectory。
2. 暴露 `search/view/edit/test/submit`，对照专用 ACI 与纯 shell。
3. 增加受限 Python CodeAct，比较 JSON、Code、Hybrid 三种动作协议。
4. 把执行放进容器，加入 CPU/内存/网络/时间限制、快照和重放。
5. 从真实 PR 构造 20 个 F2P/P2P 任务，分离公开信息与隐藏测试。
6. 在 3 个仓库中合成 100 个 SWE-smith 风格 bug，按仓库做 held-out 评测。
7. 建一个按月份更新的小型 rebench，报告五次运行的 mean、SEM、Pass@5。
8. 适配 Harbor，跑 3–5 个 Terminal-Bench 任务并审计 verifier exploit。
9. 对同一任务采样多个 patch，训练或实现一个简单 outcome selector。
10. 比较成功轨迹 SFT、patch-similarity RL 与 test-reward RL 的学习信号。
11. 为重复动作、无信息增益和超长轨迹增加过程诊断，不要只看最终 0/1。
12. 写完整实验报告：假设、控制变量、成本、失败分类、局限和可复现配置。

完成前八步已经是一项完整的 Code Agent systems 项目；再加入数据切分、RL 或 verifier 对照，就具备研究型简历项目的深度。

## 一个重要提醒

论文分数是特定时间、模型、数据切分和执行配置的历史结果。真正值得迁移的不是排行榜名次，而是实验揭示的因果关系：**定位质量、动作接口、环境可复现性、任务数据分布、采样一致性和验证信号，通常比单纯让模型多想几轮更决定系统表现。**

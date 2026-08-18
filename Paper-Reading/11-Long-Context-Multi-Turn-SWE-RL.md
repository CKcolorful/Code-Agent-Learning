# Long-Context Multi-Turn SWE RL 详读：在真实 Agent Loop 上做强化学习

论文：[Training Long-Context, Multi-Turn Software Engineering Agents with Reinforcement Learning](https://arxiv.org/abs/2508.03501)

作者：Alexander Golubev、Maria Trofimova、Sergei Polezhaev 等｜首次提交：2025 年 8 月｜论文未提供独立官方代码仓库

## 一句话结论

这篇工作把 RL 的优化对象从“一次生成完整 patch”推进到真正的多轮 Agent Loop：模型执行命令、接收 stdout/stderr、继续决策，最长 80 轮、131k 上下文，最后才获得测试奖励。Qwen2.5-72B-Instruct 经 RFT 从 11.4% 提到 20.5%，再经两阶段 DAPO 达到 SWE-bench Verified 39.0%；更重要的是论文公开了长轨迹 RL 中采样偏差、循环轨迹和同步 straggler 等系统问题。

## 1. 多轮 RL 与“token 是多轮”的区别

单次数学回答也可以把每个 token 看成一个 action，但生成期间环境不会返回新的外部事实。论文把这称为退化的 multi-turn。

软件 Agent 则是 POMDP：

- 隐状态 `z_t`：文件系统、源码、进程、依赖和工作目录；
- 观察 `o_t`：issue、stdout、stderr、exit code、工具返回；
- 动作 `a_t`：shell、search、open、edit、submit；
- 历史 `h_t=(o_0,a_0,...,o_t)`；
- 策略 `πθ(a_t|h_t)`；
- 奖励：终局 patch 是否通过验证测试。

Observation 会改变下一步决策分布，这才是环境交互式 RL 的关键：模型必须学会把失败测试、命令错误和搜索结果转化为后续动作。

## 2. Agent scaffold 被固定成什么样

论文采用类似 SWE-agent 的 ReAct loop，暴露：

- 任意 shell command；
- 按行替换的 `edit`；
- `search_file`、`open`、`goto` 等导航工具；
- 无参数 `submit` 终止任务。

每轮只允许一个可解析动作。基础 Qwen 常出现“推理正确但命令 fence 不合法”或一次输出多个命令的错误。这说明 RL 前先要让模型学会 ACI 协议，否则大部分 rollout 都死在格式层，测试奖励无法提供有效任务学习信号。

## 3. 数据从 SWE-rebench 怎样筛到 7,249 题

论文从 SWE-rebench 的 21,336 个任务出发，过滤：

- 导入错误、无效引用等任务本身问题；
- 修改超过 7 个文件或 500 行的过复杂任务；
- issue、测试或复杂度的自动质量标签较差者；
- 重复 50 次执行仍会波动的 flaky tests。

最终得到 7,249 个训练任务。评测使用 SWE-bench Verified、其中随机 50 题的中间 checkpoint 子集，以及训练截止时间之外的 SWE-rebench May/June split。

这里数据过滤不是附属步骤。二值 RL 奖励假设 `0` 表示策略失败；若测试 flaky 或任务不可解，梯度会把基础设施噪声当成行为错误。

## 4. Phase 1：RFT 先教模型正确交互

基础 Qwen2.5-72B-Instruct 在 Verified 上约 11.4%。作者对训练任务各运行 10 次，只保留测试成功轨迹，得到 6,548 条 trajectory，做一轮 supervised fine-tuning。

训练时屏蔽触发环境格式错误的 assistant turn，只对有效动作计算 loss。RFT 后 Verified Pass@1 达到 20.5%。

RFT 的角色不是替代 RL，而是把初始策略移入“能产生可学习 rollout”的区域：

```text
Base model: 大量 action parsing failure
      ↓ RFT
Valid tool-use policy: 能完成一部分任务
      ↓ RL
On-policy exploration: 从成功/失败差异中优化策略
```

如果初始成功率接近 0，同一任务组的奖励全相同，GRPO/DAPO 就几乎没有相对优势信号。

## 5. Phase 2：多轮 DAPO 如何计算奖励

每次迭代为同一问题采样 `G=10` 条完整轨迹。测试产生 `R(τ)∈{0,1}`，再加入按交互步数计算的超长惩罚：

```text
R_final(τ) = R_test(τ) + R_length(τ)
```

当轨迹超过阈值后，惩罚随步数线性增加。组内标准化得到共享给整条轨迹 token 的 advantage：

```text
A_i = (R_i - mean(R_1...R_G)) / (std(R_1...R_G) + δ)
```

零 advantage 组被动态过滤；优化使用 DAPO 的非对称 clipping 和 token-level loss。与 PPO 相比不训练 critic，代价是同一个终局 advantage 广播给数万 token，credit assignment 很粗。

## 6. 为什么分 65k 与 131k 两个阶段

Stage 1 使用 65k context、最多 40 轮；Stage 2 扩到 131k、最多 80 轮，并提高 batch size、调整 clip、筛掉长期从未解出或过于容易的任务。

结果是：

| Checkpoint | Verified Pass@1 | Pass@10 |
| --- | ---: | ---: |
| Base Qwen2.5-72B | 11.4% | 31.0% |
| + RFT @ 65k | 20.5% | 43.0% |
| + Stage 1 RL @ 65k | 35.7% | 54.6% |
| + Stage 2 RL @ 131k | 39.0% | 58.4% |

最终模型在 SWE-rebench May/June 的 Pass@1 分别为 35.0% 和 31.7%。39.0 与 58.4 的 selector gap 表明生成器经常能在 10 次中产生正确 patch，但尚缺少可靠的候选选择器。

不能把 Stage 2 的 3.3 点提升全部归因于 context length，因为同时变化了最大轮数、任务难度、batch 和 clipping。这是组合配方结果，不是单变量消融。

## 7. DAPO 在长轨迹上最危险的实现细节

论文给出一个很有价值的失败案例：训练中升级 vLLM 后，默认启用了来自模型配置的 `top_k`/`min_p`。短期评测看似上升，5–10 次迭代后性能下降。

DAPO 的 importance ratio 假设 rollout 来自旧策略 `π_old`。若真实采样分布经过 top-k 截断：

```text
τ ~ π_rollout != π_old
```

训练却仍用 `π_old` 计算概率比，估计就有偏。作者恢复 temperature=1 且关闭 top_p/top_k/min_p 等截断后，训练才恢复。

这说明 rollout server 的解码配置是 RL 算法的一部分，不是普通部署参数。版本升级必须做概率分布一致性回归测试。

## 8. 为什么不能简单丢弃超长失败轨迹

长轨迹经常来自 agent 卡在重复循环。直觉上可以删除超出 context 的样本以降低噪声，但这样也删除了“循环会失败”的负例，模型就得不到惩罚，循环反而可能越来越频繁。

处理方法应该保留失败语义，例如：

- 在达到上下文上限前明确终止并给负奖励；
- 对重复动作和无信息增益提前检测；
- 使用 step penalty 或过程 reward；
- 保存截断原因，而不是把样本静默 mask 掉。

Context Manager 与 RL data pipeline 必须共享截断语义，否则生产中的坏轨迹在训练中会消失。

## 9. 系统成本是真正的门槛

论文使用同步 on-policy pipeline：完成整个 batch 的 rollout 与验证后才更新模型，消除了 policy lag，却产生 straggler——最慢轨迹决定整轮耗时。

全参数 131k 训练依赖 context parallelism，实验使用 16 个 H200 节点、每节点 8 GPU；每个 Agent rollout 运行在独立 Kubernetes pod 中。训练框架基于 JAX，推理由 vLLM 加速。

因此这篇论文提供的是规模化方法证据，不是低成本复现配方。个人项目应复现因果结构，而不是声称复现 72B 全参数结果。

## 10. 与 SWE-RL 的关键区别

| 维度 | 本文 | SWE-RL |
| --- | --- | --- |
| 优化对象 | 多轮 action-observation trajectory | 单轮 reasoning + search/replace patch |
| 环境反馈 | 每一步执行命令后返回 | 生成期间无状态环境反馈 |
| 终局奖励 | 测试成功 + 长度惩罚 | 与 oracle patch 的字符串相似度 |
| 数据 | 7,249 个可执行 SWE-rebench 任务 | 273k PR seed |
| 主要挑战 | 131k 上下文、稀疏信用分配、rollout 系统 | 奖励代理质量、海量单轮 GRPO |

二者都叫 SWE RL，但研究问题并不相同。本文更接近训练完整 Code Agent policy；SWE-RL 更接近训练一个强 patch reasoner，再由 Agentless Mini 编排。

## 11. 局限

1. 终局二值奖励不能知道哪一步定位、编辑或验证真正有贡献。
2. 长度惩罚可能误伤确实需要长程操作的难题。
3. Stage 2 同时改变多个变量，131k context 的独立贡献不清楚。
4. 训练耗费巨大，未发布完整独立代码，外部复现难度高。
5. 同一 SWE-agent 风格 ACI 上的收益不保证迁移到不同 tool schema。
6. 训练倾向“无论如何提交”，没有学习不确定性与 abstain。

## 12. 可完成的最小复现实验

用 3B–7B 模型和 100 个可执行任务：

1. 先采样成功轨迹做一轮 RFT，测 action parse error 的下降；
2. 对同一题采样 4 条轨迹，用测试成功和超过 15 步惩罚做 group-relative 更新；
3. 比较保留超长失败轨迹与直接丢弃时的重复循环率；
4. 故意在一组实验启用 top-k，验证 off-policy mismatch 是否导致不稳定；
5. 报告 task success、parse error、submit rate、平均步数、重复率和 infrastructure failure。

即使最终分数不高，只要能展示“格式 warm-up—on-policy RL—循环负例—采样一致性”的因果链，这就是有研究含量的复现。

## 13. 读完应能回答

1. 为什么 token-level MDP 不等价于有环境反馈的多轮 Agent？
2. RFT 为什么是 RL warm-up，而不只是额外 SFT？
3. 为何 top-k 会破坏 importance ratio 的假设？
4. 丢弃超长轨迹为什么可能强化循环行为？
5. 39.0% Pass@1 与 58.4% Pass@10 暗示还缺哪个模块？

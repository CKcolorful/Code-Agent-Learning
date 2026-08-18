# Code Agent 论文阅读路线：从 Agent Loop 到训练与验证

如果这里的 Code Agent 指的是“能进入真实代码仓库、搜索代码、调用终端、修改文件、运行测试并迭代修复”的 coding agent，那么不必一开始铺开几十篇论文。下面六篇已经能串起一条完整主线：**交互循环 → 任务与评测 → 工具接口 → 结构化流水线 → 系统平台 → 训练与验证器**。

> 建议按顺序阅读。每篇先看本文档中的“十分钟速读”，再回到论文重点章节，最后结合实现问题思考。

## 最小必读：6 篇

| 顺序 | 论文 | 它回答的核心问题 | 详细解读 |
| --- | --- | --- | --- |
| 1 | [ReAct](https://arxiv.org/abs/2210.03629) | 模型如何在推理、行动和环境反馈之间形成闭环？ | [01-ReAct.md](./01-ReAct.md) |
| 2 | [SWE-bench](https://arxiv.org/abs/2310.06770) | Code Agent 到底在解决什么任务，又怎样判定成功？ | [02-SWE-bench.md](./02-SWE-bench.md) |
| 3 | [SWE-agent](https://arxiv.org/abs/2405.15793) | 怎样为模型设计搜索、浏览、编辑、执行工具？ | [03-SWE-agent.md](./03-SWE-agent.md) |
| 4 | [Agentless](https://arxiv.org/abs/2407.01489) | 复杂自主循环是否一定优于结构化 pipeline？ | [04-Agentless.md](./04-Agentless.md) |
| 5 | [OpenHands](https://arxiv.org/abs/2407.16741) | 怎样把研究原型扩展成可运行、可扩展的平台？ | [05-OpenHands.md](./05-OpenHands.md) |
| 6 | [SWE-Gym](https://arxiv.org/abs/2412.21139) | 怎样用真实环境、轨迹和 verifier 训练 Code Agent？ | [06-SWE-Gym.md](./06-SWE-Gym.md) |

## 这六篇如何拼成一张图

```text
ReAct
  定义最小闭环：Thought -> Action -> Observation -> ...
      |
      v
SWE-bench
  定义任务：Issue + Repository -> Patch -> Tests
      |
      v
SWE-agent                  Agentless
  优化自主交互接口          把任务拆成固定流水线
  Search/Edit/Execute       Localization/Repair/Validation
           \                /
            v              v
              OpenHands
       Agent + Event Stream + Runtime
      Sandbox + Skills + Evaluation
                   |
                   v
                SWE-Gym
       Environment + Trajectory + Reward
        Policy Training + Verifier + Best-of-N
```

## 阅读时始终追踪的五个问题

1. **状态是什么？** 模型当前能看见 issue、哪些文件、哪些历史动作和哪些测试输出？
2. **动作空间是什么？** 是任意 shell、专用编辑器、结构化函数调用，还是固定阶段的 pipeline？
3. **观察如何压缩？** 搜索结果、文件片段和测试日志怎样避免挤爆上下文？
4. **正确性由谁判断？** 模型自评、生成的复现测试、已有回归测试、隐藏测试，还是学习到的 verifier？
5. **失败如何恢复？** 重试、回滚、重新定位、生成多个候选、切换策略，还是请求人工介入？

## 建议的实践顺序

读论文时同步做一个极小原型，认知会更牢：

1. 用 ReAct 形式实现 `观察仓库 -> 选择命令 -> 执行 -> 回填输出`。
2. 用一个真实 GitHub issue 构造类似 SWE-bench 的 `base commit + tests + patch` 任务。
3. 先只暴露 `search / view / edit / test / submit` 五类动作，记录完整 trajectory。
4. 再实现 Agentless 风格的固定流水线，和自主 agent 在成功率、成本、步数上对照。
5. 把执行放进隔离环境，建立事件日志、预算、超时、回滚和可重放机制。
6. 对同一任务采样多个 patch，用测试和简单 verifier 进行排序。

## 一个重要提醒

论文中的分数是特定时间、模型、数据切分和执行配置下的历史结果，不应直接当作今天的排行榜。真正值得迁移的是实验揭示的因果关系：**定位质量、上下文选择、工具设计、环境可复现性和验证信号，往往比“让模型多想几步”更决定系统表现。**

# Code-Agent-Learning

一个面向 Code Agent 的学习与实践仓库。主要记录 Code Agent 经典论文、最小 Harness 实现，以及从 Agent Loop、代码库理解、编辑协议到评测与安全的完整工程机制。

这个仓库不只整理产品功能，而是尝试回答：一个基础模型如何借助 Harness 逐步获得观察仓库、调用工具、修改代码、验证结果、跨会话推进和安全协作的能力；这些能力应如何实现、怎样失败，又该如何用实验验证。

## 三条学习线

- [Code Agent 论文阅读路线](./Paper-Reading/README.md)：从 ReAct、SWE-bench 到 SWE-Gym，理解交互、工具、平台、训练与验证的研究主线。
- [从零构建一个 Code Agent：最小 Harness 实践](./最小Code%20Agent%20Harness实践/README.md)：用约 300 行 Python 跑通搜索、阅读、编辑、测试与轨迹记录。
- **Code Agent 架构系列 01–14**：每个主题都是仓库根目录下的独立 Markdown 文件，包含模块边界、协议、伪代码、失败模式、实验和演进路径。

## Code Agent 架构系列

### 第一部分：可信运行内核

| 编号 | 主题 | 核心问题 |
| --- | --- | --- |
| 01 | [Agent Loop](./01-Agent-Loop.md) | 如何把模型、工具和环境组织成有预算、可恢复、可停止的状态机？ |
| 02 | [Context Manager](./02-Context-Manager.md) | 如何在有限窗口中调度任务状态、代码证据、历史与记忆？ |
| 03 | [Tool Router](./03-Tool-Router.md) | 如何将模型意图转换成经过 Schema、策略和调度的确定性调用？ |
| 04 | [Sandboxed Executor](./04-Sandboxed-Executor.md) | 如何让不可信代码获得真实反馈，同时限制文件、网络、进程、资源和凭据？ |
| 05 | [Verifier](./05-Verifier.md) | 谁有权宣布任务完成，证据如何绑定当前 revision？ |

### 第二部分：代码理解、修改与长期推进

| 编号 | 主题 | 核心问题 |
| --- | --- | --- |
| 06 | [Repository Intelligence](./06-Repository-Intelligence.md) | 如何定位相关代码、建立符号与行为关系，并分析修改影响面？ |
| 07 | [Editing Engine](./07-Editing-Engine.md) | 如何将修改意图转换成可审计、可冲突检测、可回滚的 Patch Transaction？ |
| 08 | [Planner](./08-Planner.md) | 如何将计划从 Markdown 列表提升为有依赖、证据和重规划能力的任务图？ |
| 09 | [Long-Running Agent](./09-Long-Running-Agent.md) | 如何通过 Checkpoint、Event Log、幂等性和增量交付跨会话继续工作？ |

### 第三部分：规模化、评测与安全

| 编号 | 主题 | 核心问题 |
| --- | --- | --- |
| 10 | [Observability](./10-Observability.md) | 如何用 Trace、Trajectory、Artifact 和 Replay 定位首个致命偏离点？ |
| 11 | [Evaluation](./11-Evaluation.md) | 如何用可复现 Trial、多 Grader、统计与 Ablation 证明系统真的变好？ |
| 12 | [Subagent 与 Multi-Agent](./12-Subagent-and-Multi-Agent.md) | 哪些任务值得并行，如何隔离上下文和工作区，并证明收益不是来自更多 Token？ |
| 13 | [Instructions、Skills、Hooks 与 MCP](./13-Instructions-Skills-Hooks-MCP.md) | 长期约定、复用流程、确定性 Hook、外部能力和分发包应如何分层？ |
| 14 | [Security](./14-Security.md) | 如何切断从不可信内容到越权工具、数据外传、破坏和持久化的攻击链？ |

## 十四个模块如何协作

```text
Task / Instructions / Skills
              │
              ▼
      Planner + Agent Loop
              │
     ┌────────┼─────────┐
     ▼        ▼         ▼
Repository  Context   Tool Router ── Policy / Approval
Intelligence Manager       │
     │                      ▼
     └──────► Editing Engine / Sandboxed Executor
                            │
                            ▼
                         Verifier
                            │
           ┌────────────────┴───────────────┐
           ▼                                ▼
 Long-Running State                  Observability / Evaluation
           │                                │
           └──── Subagent / Multi-Agent ────┘

Security、Revision、Budget 与 Evidence 贯穿所有模块。
```

## 建议学习方式

1. 先运行最小 Harness，观察一次完整轨迹和失败案例。
2. 阅读 01–05，理解“能跑起来”和“可信运行”之间的差距。
3. 阅读 06–09，把通用 Agent 变成真正理解仓库、可靠编辑并能长期推进的 Code Agent。
4. 阅读 10–14，建立观测、评测、并行扩展和安全治理能力。
5. 每读一篇，选择其中一个实验加入 Harness；不要只增加功能，不测它是否改善结果。

评价任何 Code Agent 时，可以持续追问六件事：它保存了什么状态、看到了什么上下文、允许执行什么动作、动作在哪个环境运行、完成由什么证据决定、失败和成本如何被观测。

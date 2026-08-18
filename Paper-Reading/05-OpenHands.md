# OpenHands：从 Agent 算法到可运行平台

论文：[OpenHands: An Open Platform for AI Software Developers as Generalist Agents](https://arxiv.org/abs/2407.16741)

官方代码：[OpenHands/OpenHands](https://github.com/OpenHands/OpenHands)

## 一句话结论

一个真正可用的 Code Agent 不只是 prompt 和 while-loop，还需要稳定的 action/observation 协议、可重放事件流、隔离 runtime、技能层、用户交互、评测适配和系统级测试。

## 1. 这篇论文的定位

SWE-agent 更像围绕 ACI 做因果实验的研究系统；OpenHands（早期名 OpenDevin）关注怎样把不同 agent、工具、环境和 benchmark 放在一个统一平台中。它不只解决 GitHub issue，还覆盖终端操作、Python、网页浏览、数据分析等一般数字任务。

论文的主贡献应从系统架构理解，而不是只看某个 SWE-bench 数字。平台核心被拆成三部分：

1. **Agent abstraction**：读取状态并产生下一条 action；
2. **Event stream**：按时间记录 action、observation 和用户消息；
3. **Runtime**：实际执行 action 并返回 observation。

这种解耦使 agent 逻辑不必关心 Docker、终端会话和浏览器的底层实现，runtime 也不必理解模型为什么发出某条动作。

## 2. State、Event 与可重放性

OpenHands 的 State 不只是聊天历史。核心 event stream 记录：

- agent 采取的 action；
- runtime 返回的 observation；
- 用户指令、反馈和中断；
- 累积模型调用成本；
- 多 agent 委派等执行元数据。

Agent 的 `step(state)` 读取这些事件，构造模型输入，再返回一个结构化 Action。最小 agent 因而可以写成：

```text
state/history
  -> render messages
  -> LLM completion
  -> parse response
  -> Action
  -> runtime execution
  -> Observation appended to event stream
  -> next step
```

事件流的价值是统一日志、UI、恢复、评测和调试。一次失败不再只是一段终端输出，而是一条可重放轨迹，可以检查模型看到了什么、动作是否被正确解析、runtime 是否按预期执行。

## 3. Action / Observation 抽象

OpenHands 采用少量通用原语：

- `CmdRunAction`：在 sandbox 中运行 shell 命令；
- `IPythonRunCellAction`：保持交互状态地执行 Python；
- `BrowserInteractiveAction`：通过浏览器动作语言操作网页；
- `MessageAction`：与用户交流；
- `AgentFinishAction`：结束任务；
- `AgentDelegateAction`：把特定子任务交给另一个 agent。

这些动作足够通用，因为 shell 和 Python 可以进一步调用包、API 或 agent 自己创建的小工具。代价是通用动作的搜索空间大，因此平台又提供 AgentSkills，封装那些模型直接写代码不够可靠、或者需要外部模型的操作。

## 4. Runtime 与 Sandbox

每个任务会在隔离的 Docker 容器中执行。workspace 被挂载到容器，容器内运行 action execution API，维护：

- 可持续的 bash shell；
- IPython/Jupyter 执行服务；
- 浏览器交互能力；
- 文件访问和编辑环境。

平台支持在任意基础镜像上注入执行 API，从而适配不同操作系统、依赖和 benchmark。这一点对真实代码任务至关重要：agent 的动作必须发生在与目标项目兼容的环境中。

同时要保持工程上的清醒：Docker 隔离是安全边界的一部分，不代表任意不可信命令天然安全。生产系统还需要网络策略、凭据隔离、只读挂载、资源配额、超时、危险 syscall/命令控制和审计。

## 5. AgentSkills：通用原语与专用工具的折中

OpenHands 没有把所有 Python 包都重新包装成工具。论文给出的准则是：只有当操作不容易由模型直接可靠完成，或需要调用外部模型时，才值得加入 skill。

例如文件编辑、滚动查看、图像/PDF 解析适合封装；普通 CSV 读取则可以直接让模型写 Python。这种分层能避免工具列表无限膨胀：

```text
通用底座：bash / Python / browser
        +
高价值技能：edit_file / scroll / parse_pdf / ...
        +
任务级策略：CodeAct、浏览 specialist、micro-agent
```

它与 SWE-agent 的 ACI 观点并不冲突。SWE-agent强调“关键操作要做成模型友好的接口”；OpenHands进一步解决这些接口如何被多个 agent 共享、扩展和部署。

## 6. 多 Agent 与人类协作

通过 `AgentDelegateAction`，generalist 可以把网页任务交给浏览 specialist。平台还允许用户在运行过程中观察命令、文件和浏览器活动并提供反馈。

但多 agent 不是免费能力：委派需要清晰的子任务边界、输入输出契约和共享状态，否则只是把一个上下文问题变成多个上下文问题。适合委派的是可独立验证的专业任务，例如“查 API 文档并返回版本约束”，而不是模糊的“帮我把问题解决掉”。

## 7. Evaluation 是平台接口，不是一次性脚本

论文集成了 15 个涵盖软件工程、Web 和通用助手能力的 benchmark。统一评测要求平台把不同任务都映射成：初始化 runtime、注入 task、运行 agent、收集产物、调用 task-specific evaluator。

OpenHands 还强调 agent 软件本身的质量控制。完整 benchmark 运行昂贵且非确定，因此它用 mock LLM 响应做端到端集成测试，检查 prompt 构造、消息传递、action 解析和 sandbox 执行。这是容易被研究 demo 忽略、但产品化必需的一层。

## 8. Context 管理应怎样理解

论文架构用 event stream 保存完整事实历史，但这不意味着每轮都把完整事件流塞给模型。应区分：

- **持久状态**：完整、可审计、可重放；
- **模型上下文**：针对当前决策选择和压缩后的工作集。

一个健壮实现会保留原始日志，同时生成短期窗口、结构化任务状态、文件摘要和关键错误。把“存储历史”和“提示模型”分开，是长任务可扩展的前提。

## 9. 从论文到产品还缺什么

- 多租户隔离与秘密管理；
- 对外部网络和写操作的权限策略；
- 中断后恢复与幂等执行；
- repo/依赖缓存的一致性；
- 费用、延迟和失败率的可观测性；
- patch 审核、许可与供应链安全；
- 对不确定结果的人工审批门槛。

论文也承认 agent 在复杂任务和长文件编辑上仍有明显困难，工作流仍需较多手工设计。

## 10. 十分钟速读

1. 看 Figure 2，记住 Agent、Event Stream、Runtime 三件套。
2. 读 State/Action/Observation 和最小 agent 代码。
3. 精读 Docker runtime 与 action execution API。
4. 看 AgentSkills 的纳入准则和多 agent delegation。
5. 看 evaluation 与 integration test，理解平台工程边界。

## 11. 读完应该带走什么

OpenHands 把 Code Agent 从“模型会不会修 bug”提升为一个系统问题：**怎样让动作可执行、状态可追踪、环境可隔离、能力可扩展、结果可评测、过程可由人监督。** 自己做平台时，事件协议和 runtime 边界往往比 agent 类本身更值得先设计。
